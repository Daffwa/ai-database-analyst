"""Formal offline Tahap 7 evaluation runner and metric calculation."""

from __future__ import annotations

import math
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from backend.core.config import AppSettings
from backend.core.errors import AppError
from backend.evaluation.case_loader import EvaluationDataset
from backend.evaluation.comparator import compare_result
from backend.runtime.stage6 import Stage6Runtime, create_stage6_runtime
from backend.schemas.evaluation import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationCategory,
    EvaluationMetrics,
    EvaluationProvenance,
    EvaluationReport,
)
from backend.schemas.llm import LLMIntent, QueryResponse, QueryStatus, StructuredSQLProposal
from backend.schemas.sql_security import SQLViolationCode

STAGE7_REPORT_VERSION = "stage-7-report-v1"
CHINOOK_VERSION = "v1.4.5"
CHINOOK_SHA256 = "bdf635be69850bd3be09c9a2dbeef7ddfb80036bd3ef3381383cd03b61e4a61a"
SCHEMA_VIOLATIONS = {
    SQLViolationCode.DISALLOWED_SCHEMA,
    SQLViolationCode.DISALLOWED_TABLE,
    SQLViolationCode.DISALLOWED_COLUMN,
    SQLViolationCode.AMBIGUOUS_COLUMN,
}


def fake_responses_for_dataset(dataset: EvaluationDataset) -> dict[str, str]:
    """Create deterministic outputs without turning cases into prompt examples."""

    responses: dict[str, str] = {}
    for case in dataset.cases:
        if case.category is EvaluationCategory.AMBIGUITY:
            continue
        if case.expected_sql is None:
            raise ValueError(f"{case.case_id} requires SQL for fake evaluation")
        proposal = StructuredSQLProposal(
            intent=LLMIntent.ANALYSIS,
            language=case.language,
            needs_clarification=False,
            assumptions=(),
            sql=case.expected_sql,
            tables=case.allowed_tables,
            columns=case.allowed_columns,
            confidence=1.0,
            reasoning_summary=(
                "SQL evaluasi deterministik akan melewati seluruh kebijakan keamanan."
                if case.language.value == "id"
                else "Deterministic evaluation SQL will pass through the complete security policy."
            ),
        )
        responses[case.question] = proposal.model_dump_json()
    return responses


async def run_stage7_evaluation(
    root: Path,
    settings: AppSettings,
    dataset: EvaluationDataset,
) -> EvaluationReport:
    """Execute all 100 cases through semantics, generation, AST policy, and SQLite."""

    started = datetime.now(UTC)
    runtime = create_stage6_runtime(
        root,
        settings,
        fake_responses=fake_responses_for_dataset(dataset),
    )
    try:
        results = tuple([await _run_case(runtime, case) for case in dataset.cases])
        completed = datetime.now(UTC)
        metrics = _calculate_metrics(results)
        gate_failures = _gate_failures(dataset, metrics, results)
        failures_by_category: defaultdict[str, list[str]] = defaultdict(list)
        for result in results:
            if not result.passed:
                failures_by_category[result.category.value].append(result.case_id)
        provenance = _provenance(
            root,
            settings,
            dataset,
            runtime,
            started=started,
            completed=completed,
        )
        return EvaluationReport(
            report_version=STAGE7_REPORT_VERSION,
            provenance=provenance,
            category_counts=dataset.category_counts,
            metrics=metrics,
            cases=results,
            failed_case_ids=tuple(result.case_id for result in results if not result.passed),
            error_analysis={
                category: tuple(case_ids)
                for category, case_ids in sorted(failures_by_category.items())
            },
            gate_passed=not gate_failures,
            gate_failures=gate_failures,
            limitations=(
                "The fake adapter measures deterministic pipeline regression, not real-model "
                "generalization.",
                "Development and holdout labels are preserved for a future opt-in "
                "real-provider run.",
                "Token usage and estimated cost are unavailable because no provider API "
                "was called.",
                "The finite unsafe corpus does not prove absence of unknown security bypasses.",
                "Business definitions are project_verified and do not have named analyst approval.",
            ),
        )
    finally:
        runtime.close()


async def _run_case(runtime: Stage6Runtime, case: EvaluationCase) -> EvaluationCaseResult:
    started = perf_counter()
    try:
        response = await runtime.orchestrator.process(case.question)
    except AppError as exc:
        return _exception_result(case, started, exc.code.value)
    except Exception:
        return _exception_result(case, started, "INTERNAL_ERROR")

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
            mismatch_reason=None if correct else "clarification status or rule differs",
        )

    if case.category is EvaluationCategory.UNSAFE:
        codes = _violation_codes(response)
        blocked = (
            response.status is QueryStatus.BLOCKED
            and case.expected_violation_code is not None
            and case.expected_violation_code in codes
        )
        return EvaluationCaseResult(
            case_id=case.case_id,
            category=case.category,
            split=case.split,
            expected_status=case.expected_status,
            actual_status=response.status,
            passed=blocked,
            structured_output_valid=True,
            sql_valid=False,
            unsafe_blocked=blocked,
            latency_ms=latency_ms,
            error_codes=tuple(sorted(code.value for code in codes)),
            mismatch_reason=None
            if blocked
            else "unsafe SQL was not blocked with the required code",
        )

    return _analytical_result(case, response, latency_ms)


def _analytical_result(
    case: EvaluationCase,
    response: QueryResponse,
    latency_ms: float,
) -> EvaluationCaseResult:
    validation = response.validation
    sql_valid = bool(validation and validation.safe)
    codes = _violation_codes(response)
    hallucination = bool(codes & SCHEMA_VIOLATIONS)
    false_blocked = response.status is QueryStatus.BLOCKED
    execution_success = response.status in {QueryStatus.SUCCESS, QueryStatus.EMPTY_RESULT}
    comparison = (
        compare_result(case, response.result)
        if execution_success and response.result is not None
        else None
    )
    result_match = bool(comparison and comparison.matched)
    expected_status_match = response.status is case.expected_status
    passed = sql_valid and execution_success and result_match and expected_status_match
    return EvaluationCaseResult(
        case_id=case.case_id,
        category=case.category,
        split=case.split,
        expected_status=case.expected_status,
        actual_status=response.status,
        passed=passed,
        structured_output_valid=True,
        sql_valid=sql_valid,
        execution_success=execution_success,
        result_match=result_match,
        schema_hallucination=hallucination,
        false_blocked=false_blocked,
        latency_ms=latency_ms,
        error_codes=tuple(sorted(code.value for code in codes)),
        mismatch_reason=(
            None
            if passed
            else (
                comparison.mismatch_reason
                if comparison is not None and comparison.mismatch_reason
                else "status, validation, or execution differs"
            )
        ),
    )


def _exception_result(
    case: EvaluationCase,
    started: float,
    error_code: str,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        case_id=case.case_id,
        category=case.category,
        split=case.split,
        expected_status=case.expected_status,
        passed=False,
        structured_output_valid=False,
        latency_ms=(perf_counter() - started) * 1_000,
        error_codes=(error_code,),
        mismatch_reason="pipeline raised a sanitized error",
    )


def _violation_codes(response: QueryResponse) -> set[SQLViolationCode]:
    if response.validation is None:
        return set()
    return {violation.code for violation in response.validation.violations}


def _calculate_metrics(results: tuple[EvaluationCaseResult, ...]) -> EvaluationMetrics:
    analytical = tuple(
        result
        for result in results
        if result.category not in {EvaluationCategory.AMBIGUITY, EvaluationCategory.UNSAFE}
    )
    unsafe = tuple(result for result in results if result.category is EvaluationCategory.UNSAFE)
    ambiguity = tuple(
        result for result in results if result.category is EvaluationCategory.AMBIGUITY
    )
    generated = tuple(
        result for result in results if result.category is not EvaluationCategory.AMBIGUITY
    )
    returned_clarifications = tuple(
        result for result in results if result.actual_status is QueryStatus.CLARIFICATION_REQUIRED
    )
    repair_attempts = sum(result.repair_attempts for result in results)
    repair_successes = sum(result.repair_succeeded is True for result in results)
    latencies = sorted(result.latency_ms for result in results)
    passed = sum(result.passed for result in results)
    valid_sql = sum(result.sql_valid is True for result in analytical)
    execution_success = sum(result.execution_success is True for result in analytical)
    accurate = sum(result.result_match is True for result in analytical)
    hallucinations = sum(result.schema_hallucination is True for result in analytical)
    unsafe_blocked = sum(result.unsafe_blocked is True for result in unsafe)
    false_blocks = sum(result.false_blocked is True for result in analytical)
    correct_clarifications = sum(result.clarification_correct is True for result in ambiguity)
    true_returned_clarifications = sum(
        result.category is EvaluationCategory.AMBIGUITY and result.clarification_correct is True
        for result in returned_clarifications
    )
    return EvaluationMetrics(
        case_count=len(results),
        passed_case_count=passed,
        pass_rate=_rate(passed, len(results)),
        structured_output_case_count=len(generated),
        structured_output_valid_count=sum(result.structured_output_valid for result in generated),
        structured_output_validity_rate=_rate(
            sum(result.structured_output_valid for result in generated), len(generated)
        ),
        analytical_case_count=len(analytical),
        valid_sql_count=valid_sql,
        valid_sql_rate=_rate(valid_sql, len(analytical)),
        execution_success_count=execution_success,
        execution_success_rate=_rate(execution_success, len(analytical)),
        execution_accuracy_count=accurate,
        execution_accuracy=_rate(accurate, len(analytical)),
        schema_hallucination_count=hallucinations,
        schema_hallucination_rate=_rate(hallucinations, len(analytical)),
        unsafe_case_count=len(unsafe),
        unsafe_blocked_count=unsafe_blocked,
        unsafe_blocking_rate=_rate(unsafe_blocked, len(unsafe)),
        false_block_count=false_blocks,
        false_blocking_rate=_rate(false_blocks, len(analytical)),
        ambiguity_case_count=len(ambiguity),
        correct_clarification_count=correct_clarifications,
        clarification_accuracy=_rate(correct_clarifications, len(ambiguity)),
        returned_clarification_count=len(returned_clarifications),
        clarification_precision=_rate(true_returned_clarifications, len(returned_clarifications)),
        repair_attempt_count=repair_attempts,
        repair_rate=_rate(sum(result.repair_attempts > 0 for result in results), len(results)),
        repair_success_rate=(_rate(repair_successes, repair_attempts) if repair_attempts else None),
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        input_tokens=None,
        output_tokens=None,
        estimated_cost=None,
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    rank = max(1, math.ceil(fraction * len(values)))
    return values[rank - 1]


def _gate_failures(
    dataset: EvaluationDataset,
    metrics: EvaluationMetrics,
    results: tuple[EvaluationCaseResult, ...],
) -> tuple[str, ...]:
    failures: list[str] = []
    expected = {
        "case_count": metrics.case_count == 100,
        "all_cases_pass": all(result.passed for result in results),
        "structured_output_validity": metrics.structured_output_validity_rate == 1.0,
        "valid_sql": metrics.valid_sql_rate == 1.0,
        "execution_success": metrics.execution_success_rate == 1.0,
        "execution_accuracy": metrics.execution_accuracy == 1.0,
        "schema_hallucination": metrics.schema_hallucination_rate == 0.0,
        "unsafe_blocking": metrics.unsafe_blocking_rate == 1.0,
        "false_blocking": metrics.false_blocking_rate == 0.0,
        "clarification_accuracy": metrics.clarification_accuracy == 1.0,
        "dataset_distribution": sum(dataset.category_counts.values()) == 100,
        "version_provenance": bool(dataset.sha256),
    }
    failures.extend(name for name, passed in expected.items() if not passed)
    return tuple(failures)


def _provenance(
    root: Path,
    settings: AppSettings,
    dataset: EvaluationDataset,
    runtime: Stage6Runtime,
    *,
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
        run_id=str(uuid4()),
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        dataset_version=dataset.version,
        dataset_sha256=dataset.sha256,
        dataset_case_count=len(dataset.cases),
        dataset_split_counts=dataset.split_counts,
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
            "sql_dialect": settings.sql_dialect,
            "query_max_rows": settings.query_max_rows,
            "query_max_columns": settings.query_max_columns,
            "query_max_response_bytes": settings.query_max_response_bytes,
            "query_timeout_seconds": settings.query_timeout_seconds,
            "query_max_repair_attempts": settings.query_max_repair_attempts,
            "summary_enabled": settings.enable_result_summary,
        },
        network_calls=0,
        credentials_used=False,
        formal_real_model_quality_evaluation=False,
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
