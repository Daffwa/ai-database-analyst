# ruff: noqa: E501
"""Run the formal 100-case Tahap 7 evaluation and regression quality gate."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.core.config import AppSettings
from backend.evaluation.case_loader import load_evaluation_dataset
from backend.evaluation.regression import compare_evaluation_reports
from backend.evaluation.stage7_runner import run_stage7_evaluation
from backend.schemas.evaluation import EvaluationReport, RegressionReport

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "evaluation" / "stage-7-v1.jsonl"
BASELINE_PATH = ROOT / "reports" / "evaluation" / "stage-7-baseline.json"
REGRESSION_PATH = ROOT / "reports" / "evaluation" / "stage-7-regression.json"
BASELINE_MARKDOWN_PATH = ROOT / "reports" / "evaluation" / "stage-7-baseline.md"
ERROR_ANALYSIS_PATH = ROOT / "reports" / "evaluation" / "stage-7-error-analysis.md"


def _write_json(path: Path, payload: EvaluationReport | RegressionReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _load_report(path: Path) -> EvaluationReport:
    return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))


def _baseline_markdown(report: EvaluationReport) -> str:
    metrics = report.metrics
    provenance = report.provenance
    return (
        f"""# Tahap 7 Baseline Report

- Result: {"passed" if report.gate_passed else "failed"}
- Dataset: `{provenance.dataset_version}` ({provenance.dataset_case_count} cases)
- Dataset SHA-256: `{provenance.dataset_sha256}`
- Development / holdout: {provenance.dataset_split_counts.get("development", 0)} / {provenance.dataset_split_counts.get("holdout", 0)}
- Chinook: `{provenance.chinook_version}`
- Schema hash: `{provenance.schema_hash}`
- Prompt / semantic: `{provenance.prompt_version}` / `{provenance.semantic_version}`
- Semantic content hash: `{provenance.semantic_content_hash}`
- Provider / model: `{provenance.provider}` / `{provenance.model}`
- Git commit: `{provenance.git_commit}`; dirty at run: `{str(provenance.git_dirty).lower()}`

## Metrics

| Metric | Result |
|---|---:|
| All cases | {metrics.passed_case_count}/{metrics.case_count} ({metrics.pass_rate:.2%}) |
| Structured-output validity | {metrics.structured_output_valid_count}/{metrics.structured_output_case_count} ({metrics.structured_output_validity_rate:.2%}) |
| Valid SQL | {metrics.valid_sql_count}/{metrics.analytical_case_count} ({metrics.valid_sql_rate:.2%}) |
| Execution success | {metrics.execution_success_count}/{metrics.analytical_case_count} ({metrics.execution_success_rate:.2%}) |
| Execution accuracy | {metrics.execution_accuracy_count}/{metrics.analytical_case_count} ({metrics.execution_accuracy:.2%}) |
| Schema hallucination | {metrics.schema_hallucination_count}/{metrics.analytical_case_count} ({metrics.schema_hallucination_rate:.2%}) |
| Unsafe blocking | {metrics.unsafe_blocked_count}/{metrics.unsafe_case_count} ({metrics.unsafe_blocking_rate:.2%}) |
| False blocking | {metrics.false_block_count}/{metrics.analytical_case_count} ({metrics.false_blocking_rate:.2%}) |
| Clarification accuracy | {metrics.correct_clarification_count}/{metrics.ambiguity_case_count} ({metrics.clarification_accuracy:.2%}) |
| Clarification precision | {metrics.clarification_precision:.2%} |
| Repair rate | {metrics.repair_rate:.2%} |
| Latency P50 / P95 | {metrics.latency_p50_ms:.2f} ms / {metrics.latency_p95_ms:.2f} ms |
| Token usage / cost | not available (offline fake provider) |

## Category Distribution

"""
        + "\n".join(
            f"- `{category}`: {count}" for category, count in report.category_counts.items()
        )
        + """

## Interpretation Boundary

This is a reproducible offline regression baseline. The fake adapter validates
the complete deterministic pipeline but does not measure real-model language
generalization. The holdout labels are reserved for a future opt-in provider
evaluation and the evaluation cases are never inserted as verified prompt
examples.
"""
    )


def _error_analysis_markdown(report: EvaluationReport) -> str:
    if not report.failed_case_ids:
        analysis = "No failed cases in this run."
    else:
        analysis = "\n".join(
            f"- `{category}`: {', '.join(case_ids)}"
            for category, case_ids in report.error_analysis.items()
        )
    return (
        f"""# Tahap 7 Error Analysis

- Run ID: `{report.provenance.run_id}`
- Gate: {"passed" if report.gate_passed else "failed"}
- Failed cases: {len(report.failed_case_ids)}

## Failures by Category

{analysis}

## Residual Limitations

"""
        + "\n".join(f"- {item}" for item in report.limitations)
        + "\n"
    )


async def _run(args: argparse.Namespace) -> int:
    dataset = load_evaluation_dataset(args.dataset)
    settings = AppSettings(app_log_level="WARNING")
    report = await run_stage7_evaluation(ROOT, settings, dataset)

    if args.write_baseline:
        if args.baseline.exists() and not args.force:
            raise FileExistsError(f"refusing to overwrite baseline: {args.baseline}")
        _write_json(args.baseline, report)

    baseline = report if args.write_baseline else _load_report(args.baseline)
    regression = compare_evaluation_reports(baseline, report)
    if args.write_reports:
        _write_json(REGRESSION_PATH, regression)
        BASELINE_MARKDOWN_PATH.write_text(_baseline_markdown(report), encoding="utf-8")
        ERROR_ANALYSIS_PATH.write_text(_error_analysis_markdown(report), encoding="utf-8")

    summary = {
        "report_version": report.report_version,
        "run_id": report.provenance.run_id,
        "dataset_version": report.provenance.dataset_version,
        "dataset_sha256": report.provenance.dataset_sha256,
        "category_counts": report.category_counts,
        "metrics": report.metrics.model_dump(mode="json"),
        "failed_case_ids": report.failed_case_ids,
        "gate_passed": report.gate_passed,
        "gate_failures": report.gate_failures,
        "regression_gate_passed": regression.gate_passed,
        "regression_gate_failures": regression.gate_failures,
    }
    print(json.dumps(summary, indent=2))
    return 0 if report.gate_passed and regression.gate_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--write-reports", action="store_true")
    parser.add_argument("--force", action="store_true")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
