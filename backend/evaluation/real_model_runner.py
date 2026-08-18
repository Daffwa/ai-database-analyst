"""Opt-in, split-isolated real-provider evaluation for the Stage 7 corpus."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

from backend.core.config import AppSettings
from backend.core.errors import AppError
from backend.evaluation.case_loader import EvaluationDataset, validate_sealed_holdout_manifest
from backend.evaluation.stage7_runner import (
    CHINOOK_SHA256,
    CHINOOK_VERSION,
    analytical_evaluation_result,
    calculate_evaluation_metrics,
)
from backend.llm.adapters import ProviderRequestBudget
from backend.runtime.stage6 import Stage6Runtime, create_stage6_runtime
from backend.schemas.evaluation import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationCategory,
    EvaluationMetrics,
    EvaluationProvenance,
    EvaluationReport,
    EvaluationSplit,
    RealEvaluationCandidate,
    RealEvaluationReport,
    RealEvaluationSummary,
    RealEvaluationThresholds,
    ResultComparisonPolicy,
    SealedHoldoutManifest,
)
from backend.schemas.llm import QueryResponse, QueryStatus

REAL_EVALUATION_REPORT_VERSION = "stage-7-real-provider-report-v3"
REAL_EVALUATION_CANDIDATE_VERSION = "stage-7-real-provider-candidate-v3"
REAL_EVALUATION_SUMMARY_VERSION = "stage-7-real-provider-summary-v3"
ProgressCallback = Callable[[int, int, EvaluationCaseResult, int], None]


def cases_for_split(
    dataset: EvaluationDataset,
    split: EvaluationSplit,
) -> tuple[EvaluationCase, ...]:
    """Return only one split so development and holdout cannot mix accidentally."""

    return tuple(case for case in dataset.cases if case.split is split)


def planned_provider_requests(
    cases: tuple[EvaluationCase, ...],
    *,
    prompt_version: str = "v4",
) -> int:
    """Return the exact hard cap needed by the selected generation strategy."""

    calls_per_generated_case = 2 if prompt_version == "v5-plan" else 1
    return (
        sum(case.category is not EvaluationCategory.AMBIGUITY for case in cases)
        * calls_per_generated_case
    )


def planned_provider_requests_from_counts(
    category_counts: dict[EvaluationCategory, int],
    *,
    prompt_version: str = "v4",
) -> int:
    """Calculate a hard call cap from a sealed manifest without opening its payload."""

    generated = sum(category_counts.values()) - category_counts.get(
        EvaluationCategory.AMBIGUITY,
        0,
    )
    calls_per_generated_case = 2 if prompt_version == "v5-plan" else 1
    return generated * calls_per_generated_case


async def run_real_model_evaluation(
    root: Path,
    settings: AppSettings,
    dataset: EvaluationDataset,
    *,
    split: EvaluationSplit,
    request_limit: int,
    request_interval_seconds: float,
    case_limit: int | None = None,
    case_ids: tuple[str, ...] = (),
    thresholds: RealEvaluationThresholds | None = None,
    candidate: RealEvaluationCandidate | None = None,
    development_report_path: Path | None = None,
    existing_results: tuple[EvaluationCaseResult, ...] = (),
    progress: ProgressCallback | None = None,
    comparison_policy: ResultComparisonPolicy = ResultComparisonPolicy.STRICT_V1,
    holdout_manifest_sha256: str | None = None,
) -> RealEvaluationReport:
    """Run one live split sequentially under an adapter-enforced hard call cap."""

    split_cases = cases_for_split(dataset, split)
    if case_limit is not None and case_ids:
        raise ValueError("case limit and explicit case IDs are mutually exclusive")
    if case_ids:
        if split is EvaluationSplit.HOLDOUT:
            raise ValueError("holdout does not permit explicit case IDs")
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("explicit case IDs must not contain duplicates")
        by_id = {case.case_id: case for case in split_cases}
        unknown = tuple(case_id for case_id in case_ids if case_id not in by_id)
        if unknown:
            raise ValueError("explicit case IDs are outside the development split")
    if case_limit is not None:
        if split is EvaluationSplit.HOLDOUT:
            raise ValueError("holdout does not permit a partial case limit")
        if case_limit <= 0 or case_limit > len(split_cases):
            raise ValueError("case limit is outside the development split")
    if case_ids:
        selected = tuple(by_id[case_id] for case_id in case_ids)
    else:
        selected = split_cases[:case_limit] if case_limit is not None else split_cases
    planned = planned_provider_requests(selected, prompt_version=settings.prompt_version)
    active_thresholds = thresholds or RealEvaluationThresholds()
    source_hash_at_start = evaluation_source_sha256(root)
    _validate_existing_results(selected, existing_results, comparison_policy)
    _validate_live_configuration(
        settings,
        split=split,
        planned_requests=planned,
        request_limit=request_limit,
        request_interval_seconds=request_interval_seconds,
        candidate=candidate,
        dataset=dataset,
        development_report_path=development_report_path,
        comparison_policy=comparison_policy,
        holdout_manifest_sha256=holdout_manifest_sha256,
    )

    prior_attempts = sum(_provider_calls(result) for result in existing_results)
    budget = ProviderRequestBudget(
        request_limit,
        initial_attempted=prior_attempts,
        interval_seconds=request_interval_seconds,
    )
    started = datetime.now(UTC)
    runtime = create_stage6_runtime(root, settings, request_budget=budget)
    try:
        if candidate is not None:
            _validate_runtime_against_candidate(
                runtime,
                candidate,
                evaluation_source_hash=source_hash_at_start,
            )
        results: list[EvaluationCaseResult] = list(existing_results)
        for index, case in enumerate(selected[len(existing_results) :], start=len(results) + 1):
            invokes_llm = case.category is not EvaluationCategory.AMBIGUITY
            attempted_before = budget.attempted
            result = await _run_real_case(
                runtime,
                case,
                llm_invoked=invokes_llm,
                comparison_policy=comparison_policy,
            )
            provider_calls = budget.attempted - attempted_before
            result = result.model_copy(
                update={
                    "llm_invoked": provider_calls > 0,
                    "provider_request_count": provider_calls,
                }
            )
            results.append(result)
            if progress is not None:
                progress(index, len(selected), result, budget.attempted)

        completed = datetime.now(UTC)
        requests_attempted = budget.attempted
        result_tuple = tuple(results)
        metrics = calculate_evaluation_metrics(result_tuple)
        gate_failures = list(_threshold_failures(active_thresholds, metrics, result_tuple))
        if len(result_tuple) != len(selected) or requests_attempted > planned:
            gate_failures.append("incomplete_run")
        if evaluation_source_sha256(root) != source_hash_at_start:
            gate_failures.append("source_changed_during_run")
        failures_by_category: defaultdict[str, list[str]] = defaultdict(list)
        for result in result_tuple:
            if not result.passed:
                failures_by_category[result.category.value].append(result.case_id)
        return RealEvaluationReport(
            report_version=REAL_EVALUATION_REPORT_VERSION,
            split=split,
            provenance=_real_provenance(
                root,
                settings,
                dataset,
                runtime,
                split=split,
                selected_case_count=len(selected),
                requests_attempted=requests_attempted,
                request_limit=request_limit,
                request_interval_seconds=request_interval_seconds,
                evaluation_source_hash=source_hash_at_start,
                comparison_policy=comparison_policy,
                started=started,
                completed=completed,
            ),
            comparison_policy=comparison_policy,
            thresholds=active_thresholds,
            category_counts=dict(sorted(Counter(case.category.value for case in selected).items())),
            metrics=metrics,
            cases=result_tuple,
            failed_case_ids=tuple(result.case_id for result in result_tuple if not result.passed),
            error_analysis={
                category: tuple(case_ids)
                for category, case_ids in sorted(failures_by_category.items())
            },
            requests_planned=planned,
            requests_attempted=requests_attempted,
            request_limit=request_limit,
            request_interval_seconds=request_interval_seconds,
            completed=len(result_tuple) == len(selected) and requests_attempted <= planned,
            gate_passed=not gate_failures,
            gate_failures=tuple(gate_failures),
            limitations=(
                "The corpus is synthetic Chinook and does not represent private production data.",
                "A single temperature-zero run does not measure provider variance.",
                "Free-tier capacity and model behavior may change after this dated run.",
                "Unsafe protection on this finite corpus does not prove absence of "
                "unknown bypasses.",
                "For v5-plan, requests_planned is a hard maximum because valid first plans "
                "do not consume the optional repair call.",
            ),
        )
    finally:
        runtime.close()


async def _run_real_case(
    runtime: Stage6Runtime,
    case: EvaluationCase,
    *,
    llm_invoked: bool,
    comparison_policy: ResultComparisonPolicy,
) -> EvaluationCaseResult:
    started = perf_counter()
    try:
        response = await runtime.orchestrator.process(case.question)
    except AppError as exc:
        plan_error = exc.details.get("plan_error_code")
        detail_code = f"PLAN_{plan_error}" if isinstance(plan_error, str) and plan_error else None
        repair_attempts = exc.details.get("repair_attempts", 0)
        safe_details = exc.details

        def safe_optional_int(field: str) -> int | None:
            value = safe_details.get(field)
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        return _real_exception_result(
            case,
            started,
            exc.code.value,
            llm_invoked=llm_invoked,
            detail_code=detail_code,
            repair_attempts=(repair_attempts if isinstance(repair_attempts, int) else 0),
            repair_succeeded=(
                exc.details.get("repair_succeeded")
                if isinstance(exc.details.get("repair_succeeded"), bool)
                else None
            ),
            input_tokens=safe_optional_int("input_tokens"),
            output_tokens=safe_optional_int("output_tokens"),
            reasoning_tokens=safe_optional_int("reasoning_tokens"),
            total_tokens=safe_optional_int("total_tokens"),
            last_output_characters=safe_optional_int("last_output_characters"),
            finish_reason=(
                exc.details.get("finish_reason")
                if isinstance(exc.details.get("finish_reason"), str)
                else None
            ),
        )
    except Exception:
        return _real_exception_result(case, started, "INTERNAL_ERROR", llm_invoked=llm_invoked)

    latency_ms = (perf_counter() - started) * 1_000
    if case.category is EvaluationCategory.AMBIGUITY:
        resolution = runtime.semantic_service.resolve(case.question)
        rule_id = resolution.clarification.rule_id if resolution.clarification else None
        correct = (
            response.status is QueryStatus.CLARIFICATION_REQUIRED
            and rule_id == case.expected_clarification_rule
        )
        return EvaluationCaseResult(
            case_id=case.case_id,
            category=case.category,
            split=case.split,
            expected_status=case.expected_status,
            actual_status=response.status,
            passed=correct,
            structured_output_valid=True,
            clarification_correct=correct,
            latency_ms=latency_ms,
            llm_invoked=False,
            mismatch_reason=None if correct else "clarification status or rule differs",
        )

    if case.category is EvaluationCategory.UNSAFE:
        return _real_unsafe_result(case, response, latency_ms)

    scored = analytical_evaluation_result(
        case,
        response,
        latency_ms,
        comparison_policy=comparison_policy,
    )
    return scored.model_copy(update={"estimated_cost": 0.0})


def _real_unsafe_result(
    case: EvaluationCase,
    response: QueryResponse,
    latency_ms: float,
) -> EvaluationCaseResult:
    violation_codes = (
        tuple(sorted(violation.code.value for violation in response.validation.violations))
        if response.validation is not None
        else ()
    )
    protected = response.executed_sql is None and response.status in {
        QueryStatus.BLOCKED,
        QueryStatus.UNSUPPORTED,
        QueryStatus.CLARIFICATION_REQUIRED,
    }
    error_codes = violation_codes if protected else (*violation_codes, "SECURITY_BYPASS")
    usage = response.llm_token_usage
    return EvaluationCaseResult(
        case_id=case.case_id,
        category=case.category,
        split=case.split,
        expected_status=case.expected_status,
        actual_status=response.status,
        passed=protected,
        structured_output_valid=True,
        sql_valid=response.validation.safe if response.validation is not None else None,
        execution_success=response.executed_sql is not None,
        unsafe_blocked=protected,
        latency_ms=latency_ms,
        llm_invoked=True,
        input_tokens=usage.input_tokens if usage is not None else None,
        output_tokens=usage.output_tokens if usage is not None else None,
        reasoning_tokens=usage.reasoning_tokens if usage is not None else None,
        total_tokens=usage.total_tokens if usage is not None else None,
        estimated_cost=0.0,
        error_codes=error_codes,
        mismatch_reason=None if protected else "unsafe request reached SQL execution",
    )


def _real_exception_result(
    case: EvaluationCase,
    started: float,
    error_code: str,
    *,
    llm_invoked: bool,
    detail_code: str | None = None,
    repair_attempts: int = 0,
    repair_succeeded: bool | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    total_tokens: int | None = None,
    last_output_characters: int | None = None,
    finish_reason: str | None = None,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        case_id=case.case_id,
        category=case.category,
        split=case.split,
        expected_status=case.expected_status,
        passed=False,
        structured_output_valid=False,
        latency_ms=(perf_counter() - started) * 1_000,
        llm_invoked=llm_invoked,
        repair_attempts=repair_attempts,
        repair_succeeded=repair_succeeded,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        llm_output_characters=last_output_characters,
        llm_finish_reason=finish_reason,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        estimated_cost=0.0 if llm_invoked else None,
        error_codes=(error_code, *((detail_code,) if detail_code else ())),
        mismatch_reason="pipeline raised a sanitized error",
    )


def _threshold_failures(
    thresholds: RealEvaluationThresholds,
    metrics: EvaluationMetrics,
    results: tuple[EvaluationCaseResult, ...],
    *,
    prefix: str = "",
) -> tuple[str, ...]:
    security_bypasses = sum("SECURITY_BYPASS" in result.error_codes for result in results)
    checks = {
        "structured_output_validity": (
            metrics.structured_output_validity_rate >= thresholds.structured_output_validity_min
        ),
        "execution_accuracy": metrics.execution_accuracy >= thresholds.execution_accuracy_min,
        "clarification_accuracy": (
            metrics.clarification_accuracy >= thresholds.clarification_accuracy_min
        ),
        "schema_hallucination": (
            metrics.schema_hallucination_rate <= thresholds.schema_hallucination_max
        ),
        "unsafe_blocking": (metrics.unsafe_blocking_rate >= thresholds.unsafe_blocking_required),
        "security_bypass": security_bypasses <= thresholds.security_bypass_max,
    }
    return tuple(f"{prefix}{name}" for name, passed in checks.items() if not passed)


def build_real_evaluation_candidate(
    development_report_path: Path,
    development_report: RealEvaluationReport,
    dataset: EvaluationDataset,
    *,
    holdout_manifest_path: Path,
    holdout_manifest: SealedHoldoutManifest,
    frozen_at: datetime | None = None,
) -> RealEvaluationCandidate:
    """Freeze a passing development candidate before any holdout provider call."""

    if development_report.split is not EvaluationSplit.DEVELOPMENT:
        raise ValueError("candidate requires a development report")
    if not development_report.completed or not development_report.gate_passed:
        raise ValueError("development report must be complete and pass frozen thresholds")
    if development_report.provenance.dataset_sha256 != dataset.sha256:
        raise ValueError("development report dataset does not match")
    expected_development_cases = len(cases_for_split(dataset, EvaluationSplit.DEVELOPMENT))
    if development_report.provenance.dataset_case_count != expected_development_cases:
        raise ValueError("candidate requires the complete development split")
    validate_sealed_holdout_manifest(holdout_manifest)
    expected_holdout = planned_provider_requests_from_counts(
        holdout_manifest.category_counts,
        prompt_version=development_report.provenance.prompt_version,
    )
    runtime = development_report.provenance.runtime_configuration
    runtime_policy = ResultComparisonPolicy(
        str(
            runtime.get(
                "result_comparison_policy",
                ResultComparisonPolicy.STRICT_V1.value,
            )
        )
    )
    if runtime_policy is not development_report.comparison_policy:
        raise ValueError("development report comparison policy provenance does not match")
    return RealEvaluationCandidate(
        candidate_version=REAL_EVALUATION_CANDIDATE_VERSION,
        frozen_at=(frozen_at or datetime.now(UTC)).isoformat(),
        development_report_sha256=file_sha256(development_report_path),
        evaluation_source_sha256=str(runtime["evaluation_source_sha256"]),
        development_dataset_version=dataset.version,
        development_dataset_sha256=dataset.sha256,
        holdout_manifest_sha256=file_sha256(holdout_manifest_path),
        holdout_dataset_version=holdout_manifest.dataset_version,
        holdout_dataset_sha256=holdout_manifest.dataset_sha256,
        holdout_case_count=holdout_manifest.case_count,
        provider=development_report.provenance.provider,
        model=development_report.provenance.model,
        prompt_version=development_report.provenance.prompt_version,
        semantic_version=development_report.provenance.semantic_version,
        semantic_content_hash=development_report.provenance.semantic_content_hash,
        schema_hash=development_report.provenance.schema_hash,
        comparison_policy=runtime_policy,
        thinking_level=str(runtime["llm_thinking_level"]),
        max_output_tokens=int(runtime["llm_max_output_tokens"]),
        holdout_request_limit=expected_holdout,
        thresholds=development_report.thresholds,
    )


def build_real_evaluation_summary(
    candidate: RealEvaluationCandidate,
    development_report_path: Path,
    development_report: RealEvaluationReport,
    holdout_report_path: Path,
    holdout_report: RealEvaluationReport,
    fake_baseline: EvaluationReport,
    *,
    generated_at: datetime | None = None,
) -> RealEvaluationSummary:
    """Combine split reports and compare them with the separate fake baseline."""

    failures: list[str] = []
    if file_sha256(development_report_path) != candidate.development_report_sha256:
        failures.append("development_report_hash")
    if development_report.split is not EvaluationSplit.DEVELOPMENT:
        failures.append("development_split")
    if holdout_report.split is not EvaluationSplit.HOLDOUT:
        failures.append("holdout_split")
    if (
        development_report.provenance.dataset_version != candidate.development_dataset_version
        or development_report.provenance.dataset_sha256 != candidate.development_dataset_sha256
    ):
        failures.append("development_dataset_drift")
    if (
        holdout_report.provenance.dataset_version != candidate.holdout_dataset_version
        or holdout_report.provenance.dataset_sha256 != candidate.holdout_dataset_sha256
    ):
        failures.append("holdout_dataset_drift")
    if not development_report.completed:
        failures.append("development_incomplete")
    if not holdout_report.completed:
        failures.append("holdout_incomplete")
    if development_report.thresholds != candidate.thresholds:
        failures.append("development_threshold_drift")
    if holdout_report.thresholds != candidate.thresholds:
        failures.append("holdout_threshold_drift")
    if development_report.comparison_policy is not candidate.comparison_policy:
        failures.append("development_comparison_policy_drift")
    if holdout_report.comparison_policy is not candidate.comparison_policy:
        failures.append("holdout_comparison_policy_drift")
    development_runtime_policy = development_report.provenance.runtime_configuration.get(
        "result_comparison_policy",
        ResultComparisonPolicy.STRICT_V1.value,
    )
    holdout_runtime_policy = holdout_report.provenance.runtime_configuration.get(
        "result_comparison_policy",
        ResultComparisonPolicy.STRICT_V1.value,
    )
    if development_runtime_policy != candidate.comparison_policy.value:
        failures.append("development_comparison_policy_provenance")
    if holdout_runtime_policy != candidate.comparison_policy.value:
        failures.append("holdout_comparison_policy_provenance")

    combined_cases = (*development_report.cases, *holdout_report.cases)
    if len(combined_cases) != len({result.case_id for result in combined_cases}):
        failures.append("duplicate_case_ids")
    combined_metrics = calculate_evaluation_metrics(combined_cases)
    failures.extend(
        _threshold_failures(
            candidate.thresholds,
            combined_metrics,
            combined_cases,
            prefix="combined_",
        )
    )
    failures.extend(
        _threshold_failures(
            candidate.thresholds,
            holdout_report.metrics,
            holdout_report.cases,
            prefix="holdout_",
        )
    )

    return RealEvaluationSummary(
        summary_version=REAL_EVALUATION_SUMMARY_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        candidate_version=candidate.candidate_version,
        development_dataset_version=candidate.development_dataset_version,
        development_dataset_sha256=candidate.development_dataset_sha256,
        holdout_dataset_version=candidate.holdout_dataset_version,
        holdout_dataset_sha256=candidate.holdout_dataset_sha256,
        holdout_manifest_sha256=candidate.holdout_manifest_sha256,
        provider=candidate.provider,
        model=candidate.model,
        prompt_version=candidate.prompt_version,
        semantic_version=candidate.semantic_version,
        schema_hash=candidate.schema_hash,
        comparison_policy=candidate.comparison_policy,
        thresholds=candidate.thresholds,
        development_report_sha256=file_sha256(development_report_path),
        holdout_report_sha256=file_sha256(holdout_report_path),
        development_metrics=development_report.metrics,
        holdout_metrics=holdout_report.metrics,
        combined_metrics=combined_metrics,
        fake_baseline_metrics=fake_baseline.metrics,
        gate_passed=not failures,
        gate_failures=tuple(dict.fromkeys(failures)),
        limitations=(
            *development_report.limitations,
            "The fake baseline is an exact-mapping regression and is not a model-quality peer.",
            "The holdout was evaluated once; variance remains unmeasured under the USD 0 budget.",
        ),
    )


def file_sha256(path: Path) -> str:
    """Hash a generated report with platform-independent newline normalization."""

    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def evaluation_source_sha256(root: Path) -> str:
    """Hash evaluator-relevant Python source to detect mid-run or holdout drift."""

    paths = sorted((root / "backend").rglob("*.py"))
    paths.append(root / "scripts" / "evaluate_real_model.py")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_existing_results(
    selected: tuple[EvaluationCase, ...],
    existing_results: tuple[EvaluationCaseResult, ...],
    comparison_policy: ResultComparisonPolicy,
) -> None:
    expected_prefix = tuple(case.case_id for case in selected[: len(existing_results)])
    observed = tuple(result.case_id for result in existing_results)
    if observed != expected_prefix:
        raise ValueError("checkpoint results must be an ordered prefix of the selected split")
    split_mismatch = any(
        result.split is not selected[index].split for index, result in enumerate(existing_results)
    )
    if split_mismatch:
        raise ValueError("checkpoint split does not match the selected split")
    policy_mismatch = any(
        result.category not in {EvaluationCategory.AMBIGUITY, EvaluationCategory.UNSAFE}
        and result.comparison_policy is not comparison_policy
        for result in existing_results
    )
    if policy_mismatch:
        raise ValueError("checkpoint comparison policy does not match the requested run")


def _provider_calls(result: EvaluationCaseResult) -> int:
    """Read explicit metering, with compatibility for pre-meter checkpoints."""

    if result.provider_request_count:
        return result.provider_request_count
    return int(result.llm_invoked)


def _validate_live_configuration(
    settings: AppSettings,
    *,
    split: EvaluationSplit,
    planned_requests: int,
    request_limit: int,
    request_interval_seconds: float,
    candidate: RealEvaluationCandidate | None,
    dataset: EvaluationDataset,
    development_report_path: Path | None,
    comparison_policy: ResultComparisonPolicy,
    holdout_manifest_sha256: str | None,
) -> None:
    if settings.llm_provider.strip().casefold() != "gemini":
        raise ValueError("real evaluation requires the gemini provider")
    if not settings.has_llm_credentials:
        raise ValueError("real evaluation requires a configured Gemini credential")
    if request_limit != planned_requests:
        raise ValueError("request limit must equal the split's planned provider calls")
    if request_interval_seconds < 0:
        raise ValueError("request interval must not be negative")
    if split is EvaluationSplit.HOLDOUT:
        if candidate is None or development_report_path is None:
            raise ValueError("holdout requires a frozen candidate and development report")
        if file_sha256(development_report_path) != candidate.development_report_sha256:
            raise ValueError("frozen development report hash does not match")
        if (
            candidate.holdout_dataset_version != dataset.version
            or candidate.holdout_dataset_sha256 != dataset.sha256
            or candidate.holdout_case_count != len(dataset.cases)
        ):
            raise ValueError("frozen candidate dataset does not match")
        if holdout_manifest_sha256 != candidate.holdout_manifest_sha256:
            raise ValueError("sealed holdout manifest does not match frozen candidate")
        if candidate.holdout_request_limit != request_limit:
            raise ValueError("frozen candidate holdout request limit does not match")
        if candidate.provider != settings.llm_provider or candidate.model != settings.llm_model:
            raise ValueError("frozen provider/model does not match current settings")
        if candidate.prompt_version != settings.prompt_version:
            raise ValueError("frozen prompt version does not match current settings")
        if candidate.thinking_level != settings.llm_thinking_level:
            raise ValueError("frozen thinking level does not match current settings")
        if candidate.max_output_tokens != settings.llm_max_output_tokens:
            raise ValueError("frozen output-token limit does not match current settings")
        if candidate.comparison_policy is not comparison_policy:
            raise ValueError("frozen comparison policy does not match current evaluation")
    elif candidate is not None:
        raise ValueError("development evaluation must not receive a holdout candidate")


def _validate_runtime_against_candidate(
    runtime: Stage6Runtime,
    candidate: RealEvaluationCandidate,
    *,
    evaluation_source_hash: str,
) -> None:
    validation = runtime.semantic_validation
    if validation.schema_hash != candidate.schema_hash:
        raise ValueError("frozen schema hash does not match current runtime")
    if validation.semantic_version != candidate.semantic_version:
        raise ValueError("frozen semantic version does not match current runtime")
    if validation.content_hash != candidate.semantic_content_hash:
        raise ValueError("frozen semantic content hash does not match current runtime")
    if evaluation_source_hash != candidate.evaluation_source_sha256:
        raise ValueError("frozen evaluation source hash does not match current runtime")


def _real_provenance(
    root: Path,
    settings: AppSettings,
    dataset: EvaluationDataset,
    runtime: Stage6Runtime,
    *,
    split: EvaluationSplit,
    selected_case_count: int,
    requests_attempted: int,
    request_limit: int,
    request_interval_seconds: float,
    evaluation_source_hash: str,
    comparison_policy: ResultComparisonPolicy,
    started: datetime,
    completed: datetime,
) -> EvaluationProvenance:
    commit, dirty = _git_identity(root)
    try:
        application_version = version("ai-database-analyst")
    except PackageNotFoundError:
        application_version = "0.1.0"
    validation = runtime.semantic_validation
    return EvaluationProvenance(
        run_id=str(
            hashlib.sha256(f"{started.isoformat()}:{settings.llm_model}".encode()).hexdigest()
        ),
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        dataset_version=dataset.version,
        dataset_sha256=dataset.sha256,
        dataset_case_count=selected_case_count,
        dataset_split_counts={split.value: selected_case_count},
        chinook_version=CHINOOK_VERSION,
        chinook_sha256=CHINOOK_SHA256,
        schema_hash=validation.schema_hash,
        prompt_version=settings.prompt_version,
        semantic_version=validation.semantic_version,
        semantic_content_hash=validation.content_hash,
        provider=settings.llm_provider,
        model=settings.llm_model,
        application_version=application_version,
        git_commit=commit,
        git_dirty=dirty,
        python_version=sys.version.split()[0],
        sqlglot_version=version("sqlglot"),
        runtime_configuration={
            "temperature": 0,
            "llm_thinking_level": settings.llm_thinking_level,
            "llm_max_output_tokens": settings.llm_max_output_tokens,
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "request_limit": request_limit,
            "request_interval_seconds": request_interval_seconds,
            "sql_dialect": settings.sql_dialect,
            "query_max_rows": settings.query_max_rows,
            "query_timeout_seconds": settings.query_timeout_seconds,
            "paid_budget_usd": 0.0,
            "evaluation_source_sha256": evaluation_source_hash,
            "result_comparison_policy": comparison_policy.value,
        },
        network_calls=requests_attempted,
        credentials_used=True,
        formal_real_model_quality_evaluation=True,
    )


def _git_identity(root: Path) -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable", True
    commit_value = commit.stdout.strip() if commit.returncode == 0 else "uncommitted"
    return commit_value, bool(status.stdout.strip()) if status.returncode == 0 else True
