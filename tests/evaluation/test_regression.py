"""Regression threshold and provenance comparison tests."""

from __future__ import annotations

from pathlib import Path

from backend.evaluation.regression import compare_evaluation_reports
from backend.schemas.evaluation import EvaluationReport

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "reports" / "evaluation" / "stage-7-baseline.json"


def _baseline() -> EvaluationReport:
    return EvaluationReport.model_validate_json(BASELINE_PATH.read_text(encoding="utf-8"))


def test_identical_baseline_passes_all_regression_gates() -> None:
    baseline = _baseline()
    regression = compare_evaluation_reports(baseline, baseline)

    assert regression.comparable
    assert regression.gate_passed
    assert not regression.gate_failures


def test_any_known_unsafe_security_drop_fails_the_gate() -> None:
    baseline = _baseline()
    degraded_metrics = baseline.metrics.model_copy(update={"unsafe_blocking_rate": 0.9})
    degraded = baseline.model_copy(update={"metrics": degraded_metrics})

    regression = compare_evaluation_reports(baseline, degraded)

    assert not regression.gate_passed
    assert "unsafe_blocking_rate" in regression.gate_failures


def test_accuracy_false_block_and_provenance_regressions_fail() -> None:
    baseline = _baseline()
    degraded_metrics = baseline.metrics.model_copy(
        update={"execution_accuracy": 0.99, "false_blocking_rate": 0.01}
    )
    changed_provenance = baseline.provenance.model_copy(update={"prompt_version": "v2"})
    degraded = baseline.model_copy(
        update={"metrics": degraded_metrics, "provenance": changed_provenance}
    )

    regression = compare_evaluation_reports(baseline, degraded)

    assert not regression.comparable
    assert set(regression.gate_failures) == {
        "execution_accuracy",
        "false_blocking_rate",
        "provenance_not_comparable",
    }


def test_latency_regression_is_reported_as_non_gate_warning() -> None:
    baseline = _baseline()
    slower_metrics = baseline.metrics.model_copy(
        update={"latency_p95_ms": baseline.metrics.latency_p95_ms * 2}
    )
    slower = baseline.model_copy(update={"metrics": slower_metrics})

    regression = compare_evaluation_reports(baseline, slower)
    latency = next(check for check in regression.checks if check.metric == "latency_p95_ms")

    assert not latency.passed
    assert not latency.gate
    assert regression.gate_passed
