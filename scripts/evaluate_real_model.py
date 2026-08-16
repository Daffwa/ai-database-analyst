# ruff: noqa: E501
"""Run and report the opt-in Stage 7 Gemini/Gemma real-model evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from backend.core.config import AppSettings
from backend.evaluation.case_loader import load_evaluation_dataset
from backend.evaluation.real_model_runner import (
    build_real_evaluation_candidate,
    build_real_evaluation_summary,
    cases_for_split,
    evaluation_source_sha256,
    planned_provider_requests,
    run_real_model_evaluation,
)
from backend.schemas.evaluation import (
    EvaluationCaseResult,
    EvaluationReport,
    EvaluationSplit,
    RealEvaluationCandidate,
    RealEvaluationReport,
    RealEvaluationSummary,
    RealEvaluationThresholds,
    ResultComparisonPolicy,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "evaluation" / "stage-7-v1.jsonl"
REPORT_DIRECTORY = ROOT / "reports" / "evaluation"
DEVELOPMENT_REPORT_PATH = REPORT_DIRECTORY / "stage-7-gemini-development-v2.json"
DEVELOPMENT_MARKDOWN_PATH = REPORT_DIRECTORY / "stage-7-gemini-development-v2.md"
HOLDOUT_REPORT_PATH = REPORT_DIRECTORY / "stage-7-gemini-holdout-v2.json"
HOLDOUT_MARKDOWN_PATH = REPORT_DIRECTORY / "stage-7-gemini-holdout-v2.md"
CANDIDATE_PATH = REPORT_DIRECTORY / "stage-7-gemini-candidate-v2.json"
SUMMARY_PATH = REPORT_DIRECTORY / "stage-7-gemini-summary-v2.json"
SUMMARY_MARKDOWN_PATH = REPORT_DIRECTORY / "stage-7-gemini-summary-v2.md"
FAKE_BASELINE_PATH = REPORT_DIRECTORY / "stage-7-baseline.json"
DEVELOPMENT_CHECKPOINT_PATH = ROOT / "logs" / "point5-development-v2.checkpoint.json"
HOLDOUT_CHECKPOINT_PATH = ROOT / "logs" / "point5-holdout-v2.checkpoint.json"
MINIMUM_LIVE_INTERVAL_SECONDS = 2.0
CHECKPOINT_VERSION = "stage-7-real-provider-checkpoint-v3"


def _write_model(path: Path, payload: BaseModel, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _report_markdown(report: RealEvaluationReport) -> str:
    metrics = report.metrics
    provenance = report.provenance
    failures = (
        "No failed cases."
        if not report.error_analysis
        else "\n".join(
            f"- `{category}`: {', '.join(case_ids)}"
            for category, case_ids in report.error_analysis.items()
        )
    )
    return (
        f"""# Real-Model Evaluation: {report.split.value.title()}

- Gate: {"passed" if report.gate_passed else "failed"}
- Provider/model: `{provenance.provider}` / `{provenance.model}`
- Dataset: `{provenance.dataset_version}` / `{provenance.dataset_sha256}`
- Prompt/semantic: `{provenance.prompt_version}` / `{provenance.semantic_version}`
- Result comparison: `{report.comparison_policy.value}`
- Schema hash: `{provenance.schema_hash}`
- Requests: {report.requests_attempted}/{report.request_limit}
- Temperature/thinking: 0 / `{provenance.runtime_configuration["llm_thinking_level"]}`
- Paid budget and measured cost: USD 0 / USD {metrics.estimated_cost or 0:.2f}

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | {metrics.passed_case_count}/{metrics.case_count} ({metrics.pass_rate:.2%}) |
| Structured-output validity | {metrics.structured_output_valid_count}/{metrics.structured_output_case_count} ({metrics.structured_output_validity_rate:.2%}) |
| Valid SQL | {metrics.valid_sql_count}/{metrics.analytical_case_count} ({metrics.valid_sql_rate:.2%}) |
| Execution success | {metrics.execution_success_count}/{metrics.analytical_case_count} ({metrics.execution_success_rate:.2%}) |
| Execution accuracy | {metrics.execution_accuracy_count}/{metrics.analytical_case_count} ({metrics.execution_accuracy:.2%}) |
| Schema hallucination | {metrics.schema_hallucination_count}/{metrics.analytical_case_count} ({metrics.schema_hallucination_rate:.2%}) |
| Unsafe protection | {metrics.unsafe_blocked_count}/{metrics.unsafe_case_count} ({metrics.unsafe_blocking_rate:.2%}) |
| False blocking | {metrics.false_block_count}/{metrics.analytical_case_count} ({metrics.false_blocking_rate:.2%}) |
| Clarification accuracy | {metrics.correct_clarification_count}/{metrics.ambiguity_case_count} ({metrics.clarification_accuracy:.2%}) |
| Latency P50/P95 | {metrics.latency_p50_ms:.2f} / {metrics.latency_p95_ms:.2f} ms |
| Input/output tokens | {metrics.input_tokens or 0} / {metrics.output_tokens or 0} |
| Presentation-equivalent passes | {metrics.presentation_equivalent_count} |
| Substantive result mismatches | {metrics.substantive_mismatch_count} |

## Failure Categories

{failures}

## Gate Failures

{", ".join(report.gate_failures) if report.gate_failures else "None."}

## Boundaries

"""
        + "\n".join(f"- {limitation}" for limitation in report.limitations)
        + "\n"
    )


def _summary_markdown(summary: RealEvaluationSummary) -> str:
    development = summary.development_metrics
    holdout = summary.holdout_metrics
    combined = summary.combined_metrics
    fake = summary.fake_baseline_metrics
    return (
        f"""# Gemini/Gemma Real-Model Baseline

- Gate: {"passed" if summary.gate_passed else "failed"}
- Candidate: `{summary.candidate_version}`
- Provider/model: `{summary.provider}` / `{summary.model}`
- Dataset: `{summary.dataset_version}` / `{summary.dataset_sha256}`
- Prompt/semantic: `{summary.prompt_version}` / `{summary.semantic_version}`
- Result comparison: `{summary.comparison_policy.value}`
- Schema hash: `{summary.schema_hash}`
- Measured paid cost: USD {combined.estimated_cost or 0:.2f}

## Development, Holdout, and Combined

| Metric | Development | Holdout | Combined | Fake baseline* |
|---|---:|---:|---:|---:|
| Structured output | {development.structured_output_validity_rate:.2%} | {holdout.structured_output_validity_rate:.2%} | {combined.structured_output_validity_rate:.2%} | {fake.structured_output_validity_rate:.2%} |
| Execution accuracy | {development.execution_accuracy:.2%} | {holdout.execution_accuracy:.2%} | {combined.execution_accuracy:.2%} | {fake.execution_accuracy:.2%} |
| Schema hallucination | {development.schema_hallucination_rate:.2%} | {holdout.schema_hallucination_rate:.2%} | {combined.schema_hallucination_rate:.2%} | {fake.schema_hallucination_rate:.2%} |
| Unsafe protection | {development.unsafe_blocking_rate:.2%} | {holdout.unsafe_blocking_rate:.2%} | {combined.unsafe_blocking_rate:.2%} | {fake.unsafe_blocking_rate:.2%} |
| Clarification accuracy | {development.clarification_accuracy:.2%} | {holdout.clarification_accuracy:.2%} | {combined.clarification_accuracy:.2%} | {fake.clarification_accuracy:.2%} |
| Latency P50/P95 | {development.latency_p50_ms:.0f}/{development.latency_p95_ms:.0f} ms | {holdout.latency_p50_ms:.0f}/{holdout.latency_p95_ms:.0f} ms | {combined.latency_p50_ms:.0f}/{combined.latency_p95_ms:.0f} ms | {fake.latency_p50_ms:.0f}/{fake.latency_p95_ms:.0f} ms |
| Input/output tokens | {development.input_tokens or 0}/{development.output_tokens or 0} | {holdout.input_tokens or 0}/{holdout.output_tokens or 0} | {combined.input_tokens or 0}/{combined.output_tokens or 0} | n/a |

Note: the fake baseline uses exact mappings. It proves deterministic regression,
not equivalent language generalization.

## Gate Failures

{", ".join(summary.gate_failures) if summary.gate_failures else "None."}

## Limitations

"""
        + "\n".join(f"- {limitation}" for limitation in summary.limitations)
        + "\n"
    )


def _progress(
    index: int,
    total: int,
    result: EvaluationCaseResult,
    requests_attempted: int,
) -> None:
    print(
        json.dumps(
            {
                "case": result.case_id,
                "index": index,
                "total": total,
                "requests_attempted": requests_attempted,
                "passed": result.passed,
                "actual_status": (
                    result.actual_status.value if result.actual_status is not None else None
                ),
                "sql_valid": result.sql_valid,
                "result_match": result.result_match,
                "expected_column_count": result.expected_column_count,
                "actual_column_count": result.actual_column_count,
                "error_codes": result.error_codes,
                "repair_attempts": result.repair_attempts,
                "output_tokens": result.output_tokens,
                "llm_output_characters": result.llm_output_characters,
                "llm_finish_reason": result.llm_finish_reason,
                "mismatch_reason": result.mismatch_reason,
                "column_match_mode": (
                    result.column_match_mode.value if result.column_match_mode is not None else None
                ),
                "presentation_equivalent": result.presentation_equivalent,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )


def _load_checkpoint(
    path: Path,
    *,
    split: EvaluationSplit,
    dataset_sha256: str,
    settings: AppSettings,
    request_limit: int,
    request_interval_seconds: float,
    source_sha256: str,
    comparison_policy: ResultComparisonPolicy,
    selected_case_ids: tuple[str, ...],
) -> tuple[EvaluationCaseResult, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "split": split.value,
        "dataset_sha256": dataset_sha256,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "prompt_version": settings.prompt_version,
        "llm_max_output_tokens": settings.llm_max_output_tokens,
        "request_limit": request_limit,
        "request_interval_seconds": request_interval_seconds,
        "evaluation_source_sha256": source_sha256,
        "comparison_policy": comparison_policy.value,
        "selected_case_ids": list(selected_case_ids),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("checkpoint identity does not match the requested run")
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("checkpoint results are invalid")
    return tuple(EvaluationCaseResult.model_validate(item) for item in raw_results)


def _write_checkpoint(
    path: Path,
    *,
    split: EvaluationSplit,
    dataset_sha256: str,
    settings: AppSettings,
    request_limit: int,
    request_interval_seconds: float,
    source_sha256: str,
    comparison_policy: ResultComparisonPolicy,
    selected_case_ids: tuple[str, ...],
    results: Sequence[EvaluationCaseResult],
) -> None:
    payload = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "split": split.value,
        "dataset_sha256": dataset_sha256,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "prompt_version": settings.prompt_version,
        "llm_max_output_tokens": settings.llm_max_output_tokens,
        "request_limit": request_limit,
        "request_interval_seconds": request_interval_seconds,
        "evaluation_source_sha256": source_sha256,
        "comparison_policy": comparison_policy.value,
        "selected_case_ids": list(selected_case_ids),
        "results": [result.model_dump(mode="json") for result in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_command(args: argparse.Namespace) -> int:
    if not args.confirm_live:
        print("Live evaluation not run. Re-run with --confirm-live.")
        return 2
    if args.request_interval_seconds < MINIMUM_LIVE_INTERVAL_SECONDS:
        print(
            f"Live evaluation not run: interval must be at least "
            f"{MINIMUM_LIVE_INTERVAL_SECONDS:.0f} seconds."
        )
        return 2

    dataset = load_evaluation_dataset(args.dataset)
    split = EvaluationSplit(args.split)
    comparison_policy = ResultComparisonPolicy(args.comparison_policy)
    selected = cases_for_split(dataset, split)
    case_ids = tuple(args.case_ids or ())
    if args.case_limit is not None and case_ids:
        print("Live evaluation not run: --case-limit and --case-id are mutually exclusive.")
        return 2
    if case_ids:
        if split is EvaluationSplit.HOLDOUT:
            print("Live evaluation not run: holdout cannot use --case-id.")
            return 2
        if len(case_ids) != len(set(case_ids)):
            print("Live evaluation not run: --case-id values must be unique.")
            return 2
        by_id = {case.case_id: case for case in selected}
        if any(case_id not in by_id for case_id in case_ids):
            print("Live evaluation not run: an explicit case is outside development.")
            return 2
        selected = tuple(by_id[case_id] for case_id in case_ids)
    if args.case_limit is not None:
        if split is EvaluationSplit.HOLDOUT:
            print("Live evaluation not run: holdout cannot use --case-limit.")
            return 2
        if args.case_limit <= 0 or args.case_limit > len(selected):
            print("Live evaluation not run: invalid development case limit.")
            return 2
        selected = selected[: args.case_limit]
    planned = planned_provider_requests(selected, prompt_version=args.prompt_version)
    if args.max_requests != planned:
        print(f"Live evaluation not run: --max-requests must equal {planned} for {split.value}.")
        return 2

    configured = AppSettings()
    settings = AppSettings(
        app_log_level="WARNING",
        prompt_version=args.prompt_version,
        llm_model=args.model or configured.llm_model,
        llm_max_output_tokens=(
            args.max_output_tokens
            if args.max_output_tokens is not None
            else configured.llm_max_output_tokens
        ),
    )
    if settings.llm_provider.strip().casefold() != "gemini" or not settings.has_llm_credentials:
        print("Live evaluation not run: local Gemini configuration is incomplete.")
        return 2

    candidate: RealEvaluationCandidate | None = None
    thresholds = RealEvaluationThresholds()
    development_report_path: Path | None = None
    if split is EvaluationSplit.HOLDOUT:
        candidate = RealEvaluationCandidate.model_validate_json(
            args.candidate.read_text(encoding="utf-8")
        )
        thresholds = candidate.thresholds
        development_report_path = args.development_report

    output_path = (
        args.development_output if split is EvaluationSplit.DEVELOPMENT else args.holdout_output
    )
    markdown_path = (
        args.development_markdown if split is EvaluationSplit.DEVELOPMENT else args.holdout_markdown
    )
    if (output_path.exists() or markdown_path.exists()) and not args.force:
        print("Live evaluation not run: output exists; use --force to replace it intentionally.")
        return 2

    checkpoint_path = args.checkpoint or (
        DEVELOPMENT_CHECKPOINT_PATH
        if split is EvaluationSplit.DEVELOPMENT
        else HOLDOUT_CHECKPOINT_PATH
    )
    source_sha256 = evaluation_source_sha256(ROOT)
    checkpoint_results: list[EvaluationCaseResult] = []
    if checkpoint_path.exists() and args.resume:
        try:
            checkpoint_results.extend(
                _load_checkpoint(
                    checkpoint_path,
                    split=split,
                    dataset_sha256=dataset.sha256,
                    settings=settings,
                    request_limit=args.max_requests,
                    request_interval_seconds=args.request_interval_seconds,
                    source_sha256=source_sha256,
                    comparison_policy=comparison_policy,
                    selected_case_ids=tuple(case.case_id for case in selected),
                )
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Live evaluation not run: {exc}")
            return 2
    elif checkpoint_path.exists() and not args.force:
        print("Live evaluation not run: checkpoint exists; use --resume or --force.")
        return 2

    def checkpoint_progress(
        index: int,
        total: int,
        result: EvaluationCaseResult,
        requests_attempted: int,
    ) -> None:
        checkpoint_results.append(result)
        _write_checkpoint(
            checkpoint_path,
            split=split,
            dataset_sha256=dataset.sha256,
            settings=settings,
            request_limit=args.max_requests,
            request_interval_seconds=args.request_interval_seconds,
            source_sha256=source_sha256,
            comparison_policy=comparison_policy,
            selected_case_ids=tuple(case.case_id for case in selected),
            results=checkpoint_results,
        )
        _progress(index, total, result, requests_attempted)

    _write_checkpoint(
        checkpoint_path,
        split=split,
        dataset_sha256=dataset.sha256,
        settings=settings,
        request_limit=args.max_requests,
        request_interval_seconds=args.request_interval_seconds,
        source_sha256=source_sha256,
        comparison_policy=comparison_policy,
        selected_case_ids=tuple(case.case_id for case in selected),
        results=checkpoint_results,
    )

    try:
        report = asyncio.run(
            run_real_model_evaluation(
                ROOT,
                settings,
                dataset,
                split=split,
                request_limit=args.max_requests,
                request_interval_seconds=args.request_interval_seconds,
                case_limit=args.case_limit,
                case_ids=case_ids,
                thresholds=thresholds,
                candidate=candidate,
                development_report_path=development_report_path,
                existing_results=tuple(checkpoint_results),
                progress=checkpoint_progress,
                comparison_policy=comparison_policy,
            )
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Live evaluation stopped safely: {exc}")
        return 2

    _write_model(output_path, report, force=args.force)
    markdown_path.write_text(_report_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "split": split.value,
                "report": str(output_path.resolve().relative_to(ROOT)),
                "requests": report.requests_attempted,
                "execution_accuracy": report.metrics.execution_accuracy,
                "unsafe_blocking": report.metrics.unsafe_blocking_rate,
                "gate_passed": report.gate_passed,
                "gate_failures": report.gate_failures,
                "comparison_policy": report.comparison_policy.value,
            },
            indent=2,
        )
    )
    return 0 if report.gate_passed else 1


def _freeze_command(args: argparse.Namespace) -> int:
    dataset = load_evaluation_dataset(args.dataset)
    report = RealEvaluationReport.model_validate_json(
        args.development_report.read_text(encoding="utf-8")
    )
    try:
        candidate = build_real_evaluation_candidate(
            args.development_report,
            report,
            dataset,
            holdout_request_limit=args.holdout_max_requests,
        )
        _write_model(args.candidate, candidate, force=args.force)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Candidate not frozen: {exc}")
        return 2
    print(
        json.dumps(
            {
                "candidate": str(args.candidate.resolve().relative_to(ROOT)),
                "provider": candidate.provider,
                "model": candidate.model,
                "prompt_version": candidate.prompt_version,
                "comparison_policy": candidate.comparison_policy.value,
                "holdout_request_limit": candidate.holdout_request_limit,
            },
            indent=2,
        )
    )
    return 0


def _summarize_command(args: argparse.Namespace) -> int:
    try:
        if (args.summary.exists() or args.summary_markdown.exists()) and not args.force:
            raise FileExistsError("refusing to overwrite an existing summary report")
        candidate = RealEvaluationCandidate.model_validate_json(
            args.candidate.read_text(encoding="utf-8")
        )
        development = RealEvaluationReport.model_validate_json(
            args.development_report.read_text(encoding="utf-8")
        )
        holdout = RealEvaluationReport.model_validate_json(
            args.holdout_report.read_text(encoding="utf-8")
        )
        fake = EvaluationReport.model_validate_json(args.fake_baseline.read_text(encoding="utf-8"))
        summary = build_real_evaluation_summary(
            candidate,
            args.development_report,
            development,
            args.holdout_report,
            holdout,
            fake,
        )
        _write_model(args.summary, summary, force=args.force)
        args.summary_markdown.write_text(_summary_markdown(summary), encoding="utf-8")
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Summary not written: {exc}")
        return 2
    print(
        json.dumps(
            {
                "summary": str(args.summary.resolve().relative_to(ROOT)),
                "execution_accuracy": summary.combined_metrics.execution_accuracy,
                "holdout_execution_accuracy": summary.holdout_metrics.execution_accuracy,
                "unsafe_blocking": summary.combined_metrics.unsafe_blocking_rate,
                "estimated_cost": summary.combined_metrics.estimated_cost,
                "gate_passed": summary.gate_passed,
                "gate_failures": summary.gate_failures,
            },
            indent=2,
        )
    )
    return 0 if summary.gate_passed else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run exactly one live evaluation split.")
    run.add_argument("--split", choices=[split.value for split in EvaluationSplit], required=True)
    run.add_argument("--confirm-live", action="store_true")
    run.add_argument("--max-requests", type=int, required=True)
    run.add_argument("--request-interval-seconds", type=float, default=6.0)
    run.add_argument("--case-limit", type=int)
    run.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Development-only case ID; repeat to run a sealed explicit subset.",
    )
    run.add_argument(
        "--comparison-policy",
        choices=[policy.value for policy in ResultComparisonPolicy],
        default=ResultComparisonPolicy.STRICT_V1.value,
        help="Versioned result-equivalence policy; semantic-v2 remains fail-closed.",
    )
    run.add_argument(
        "--prompt-version",
        choices=("v1", "v2", "v3", "v4", "v5-plan"),
        default="v4",
    )
    run.add_argument(
        "--model",
        choices=("gemma-4-26b-a4b-it", "gemma-4-31b-it"),
        help="Override only the evaluation model; local application settings remain unchanged.",
    )
    run.add_argument(
        "--max-output-tokens",
        type=int,
        help="Override the frozen provider output-token ceiling for this run.",
    )
    run.add_argument("--dataset", type=Path, default=DATASET_PATH)
    run.add_argument("--development-output", type=Path, default=DEVELOPMENT_REPORT_PATH)
    run.add_argument("--development-markdown", type=Path, default=DEVELOPMENT_MARKDOWN_PATH)
    run.add_argument("--holdout-output", type=Path, default=HOLDOUT_REPORT_PATH)
    run.add_argument("--holdout-markdown", type=Path, default=HOLDOUT_MARKDOWN_PATH)
    run.add_argument("--candidate", type=Path, default=CANDIDATE_PATH)
    run.add_argument("--development-report", type=Path, default=DEVELOPMENT_REPORT_PATH)
    run.add_argument("--checkpoint", type=Path)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--force", action="store_true")
    run.set_defaults(handler=_run_command)

    freeze = subparsers.add_parser("freeze", help="Freeze a passing development candidate.")
    freeze.add_argument("--dataset", type=Path, default=DATASET_PATH)
    freeze.add_argument("--development-report", type=Path, default=DEVELOPMENT_REPORT_PATH)
    freeze.add_argument("--candidate", type=Path, default=CANDIDATE_PATH)
    freeze.add_argument("--holdout-max-requests", type=int, default=27)
    freeze.add_argument("--force", action="store_true")
    freeze.set_defaults(handler=_freeze_command)

    summarize = subparsers.add_parser("summarize", help="Combine development and holdout.")
    summarize.add_argument("--candidate", type=Path, default=CANDIDATE_PATH)
    summarize.add_argument("--development-report", type=Path, default=DEVELOPMENT_REPORT_PATH)
    summarize.add_argument("--holdout-report", type=Path, default=HOLDOUT_REPORT_PATH)
    summarize.add_argument("--fake-baseline", type=Path, default=FAKE_BASELINE_PATH)
    summarize.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    summarize.add_argument("--summary-markdown", type=Path, default=SUMMARY_MARKDOWN_PATH)
    summarize.add_argument("--force", action="store_true")
    summarize.set_defaults(handler=_summarize_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
