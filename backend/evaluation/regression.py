"""Comparable Tahap 7 baseline regression checks and mandatory security gate."""

from __future__ import annotations

from backend.schemas.evaluation import (
    EvaluationReport,
    RegressionCheck,
    RegressionReport,
    RegressionThresholds,
)

REGRESSION_REPORT_VERSION = "stage-7-regression-v1"


def compare_evaluation_reports(
    baseline: EvaluationReport,
    current: EvaluationReport,
    *,
    thresholds: RegressionThresholds | None = None,
) -> RegressionReport:
    """Compare compatible reports and fail closed on any security decrease."""

    policy = thresholds or RegressionThresholds()
    comparable_fields = (
        ("dataset_sha256", baseline.provenance.dataset_sha256, current.provenance.dataset_sha256),
        ("schema_hash", baseline.provenance.schema_hash, current.provenance.schema_hash),
        ("prompt_version", baseline.provenance.prompt_version, current.provenance.prompt_version),
        (
            "semantic_content_hash",
            baseline.provenance.semantic_content_hash,
            current.provenance.semantic_content_hash,
        ),
        ("provider", baseline.provenance.provider, current.provenance.provider),
        ("model", baseline.provenance.model, current.provenance.model),
    )
    notes = tuple(
        f"{name} differs: baseline={left}, current={right}"
        for name, left, right in comparable_fields
        if left != right
    )
    comparable = not notes

    checks = (
        _minimum_check(
            "unsafe_blocking_rate",
            baseline.metrics.unsafe_blocking_rate,
            current.metrics.unsafe_blocking_rate,
            policy.required_unsafe_blocking_rate,
            gate=True,
        ),
        _drop_check(
            "execution_accuracy",
            baseline.metrics.execution_accuracy,
            current.metrics.execution_accuracy,
            policy.max_execution_accuracy_drop,
            gate=True,
        ),
        _drop_check(
            "valid_sql_rate",
            baseline.metrics.valid_sql_rate,
            current.metrics.valid_sql_rate,
            policy.max_valid_sql_rate_drop,
            gate=True,
        ),
        _drop_check(
            "clarification_accuracy",
            baseline.metrics.clarification_accuracy,
            current.metrics.clarification_accuracy,
            policy.max_clarification_accuracy_drop,
            gate=True,
        ),
        _increase_check(
            "false_blocking_rate",
            baseline.metrics.false_blocking_rate,
            current.metrics.false_blocking_rate,
            policy.max_false_blocking_rate_increase,
            gate=True,
        ),
        _ratio_check(
            "latency_p95_ms",
            baseline.metrics.latency_p95_ms,
            current.metrics.latency_p95_ms,
            policy.max_latency_p95_increase_ratio,
            gate=False,
        ),
    )
    failures = tuple(check.metric for check in checks if check.gate and not check.passed)
    if not comparable:
        failures = (*failures, "provenance_not_comparable")
    return RegressionReport(
        report_version=REGRESSION_REPORT_VERSION,
        baseline_run_id=baseline.provenance.run_id,
        current_run_id=current.provenance.run_id,
        comparable=comparable,
        comparison_notes=notes,
        thresholds=policy,
        checks=checks,
        gate_passed=not failures,
        gate_failures=failures,
    )


def _drop_check(
    metric: str,
    baseline: float,
    current: float,
    threshold: float,
    *,
    gate: bool,
) -> RegressionCheck:
    drop = baseline - current
    return RegressionCheck(
        metric=metric,
        baseline=baseline,
        current=current,
        delta=current - baseline,
        threshold=threshold,
        passed=drop <= threshold,
        gate=gate,
    )


def _increase_check(
    metric: str,
    baseline: float,
    current: float,
    threshold: float,
    *,
    gate: bool,
) -> RegressionCheck:
    increase = current - baseline
    return RegressionCheck(
        metric=metric,
        baseline=baseline,
        current=current,
        delta=increase,
        threshold=threshold,
        passed=increase <= threshold,
        gate=gate,
    )


def _minimum_check(
    metric: str,
    baseline: float,
    current: float,
    minimum: float,
    *,
    gate: bool,
) -> RegressionCheck:
    return RegressionCheck(
        metric=metric,
        baseline=baseline,
        current=current,
        delta=current - baseline,
        threshold=minimum,
        passed=current >= minimum,
        gate=gate,
    )


def _ratio_check(
    metric: str,
    baseline: float,
    current: float,
    ratio: float,
    *,
    gate: bool,
) -> RegressionCheck:
    allowed = baseline * (1 + ratio)
    return RegressionCheck(
        metric=metric,
        baseline=baseline,
        current=current,
        delta=current - baseline,
        threshold=allowed,
        passed=current <= allowed,
        gate=gate,
    )
