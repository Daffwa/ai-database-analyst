"""Deterministic development-only audit for result comparison policy v2."""

from __future__ import annotations

from typing import Any

from backend.evaluation.case_loader import EvaluationDataset
from backend.evaluation.comparator import compare_result
from backend.schemas.database import QueryResult
from backend.schemas.evaluation import (
    ComparisonPolicyAudit,
    EvaluationCase,
    EvaluationCategory,
    EvaluationSplit,
    ResultComparisonPolicy,
)

COMPARISON_POLICY_AUDIT_VERSION = "stage-7-comparison-policy-audit-v1"


def build_comparison_policy_audit(dataset: EvaluationDataset) -> ComparisonPolicyAudit:
    """Exercise equivalence and rejection invariants without scoring holdout cases."""

    development = tuple(case for case in dataset.cases if case.split is EvaluationSplit.DEVELOPMENT)
    analytical = tuple(
        case
        for case in development
        if case.category not in {EvaluationCategory.AMBIGUITY, EvaluationCategory.UNSAFE}
    )

    exact_matches = 0
    presentation_accepted = 0
    strict_presentation_rejected = 0
    substantive_tested = 0
    substantive_rejected = 0
    required_order_tested = 0
    required_order_rejected = 0
    irrelevant_order_tested = 0
    irrelevant_order_accepted = 0

    for case in analytical:
        exact = _query_result(case.expected_columns, case.expected_rows)
        exact_matches += compare_result(
            case,
            exact,
            policy=ResultComparisonPolicy.SEMANTIC_V2,
        ).matched

        presentation = _presentation_variant(case)
        presentation_accepted += compare_result(
            case,
            presentation,
            policy=ResultComparisonPolicy.SEMANTIC_V2,
        ).matched
        strict_presentation_rejected += not compare_result(
            case,
            presentation,
            policy=ResultComparisonPolicy.STRICT_V1,
        ).matched

        for substantive in (_wrong_value_variant(case), _extra_column_variant(case)):
            substantive_tested += 1
            substantive_rejected += not compare_result(
                case,
                substantive,
                policy=ResultComparisonPolicy.SEMANTIC_V2,
            ).matched

        if (
            len(case.expected_rows) > 1
            and tuple(reversed(case.expected_rows)) != case.expected_rows
        ):
            reversed_rows = _query_result(
                case.expected_columns,
                tuple(reversed(case.expected_rows)),
            )
            if case.order_sensitive:
                required_order_tested += 1
                required_order_rejected += not compare_result(
                    case,
                    reversed_rows,
                    policy=ResultComparisonPolicy.SEMANTIC_V2,
                ).matched
            else:
                irrelevant_order_tested += 1
                irrelevant_order_accepted += compare_result(
                    case,
                    reversed_rows,
                    policy=ResultComparisonPolicy.SEMANTIC_V2,
                ).matched

    failures = {
        "exact_self_match": exact_matches == len(analytical),
        "presentation_equivalence": presentation_accepted == len(analytical),
        "strict_policy_separation": strict_presentation_rejected == len(analytical),
        "substantive_rejection": substantive_rejected == substantive_tested,
        "required_order_rejection": required_order_rejected == required_order_tested,
        "irrelevant_order_acceptance": irrelevant_order_accepted == irrelevant_order_tested,
        "holdout_isolation": True,
    }
    gate_failures = tuple(name for name, passed in failures.items() if not passed)
    return ComparisonPolicyAudit(
        report_version=COMPARISON_POLICY_AUDIT_VERSION,
        dataset_version=dataset.version,
        dataset_sha256=dataset.sha256,
        split=EvaluationSplit.DEVELOPMENT,
        comparison_policy=ResultComparisonPolicy.SEMANTIC_V2,
        development_case_count=len(development),
        analytical_case_count=len(analytical),
        holdout_cases_scored=0,
        exact_self_matches=exact_matches,
        presentation_variants_tested=len(analytical),
        presentation_variants_accepted=presentation_accepted,
        strict_policy_presentation_rejections=strict_presentation_rejected,
        substantive_variants_tested=substantive_tested,
        substantive_variants_rejected=substantive_rejected,
        required_order_variants_tested=required_order_tested,
        required_order_variants_rejected=required_order_rejected,
        irrelevant_order_variants_tested=irrelevant_order_tested,
        irrelevant_order_variants_accepted=irrelevant_order_accepted,
        gate_passed=not gate_failures,
        gate_failures=gate_failures,
        limitations=(
            "The audit uses deterministic transformations of development expectations, not "
            "new provider outputs.",
            "Value-aligned aliases pass only when a unique one-to-one mapping is provable.",
            "Extra or missing columns, ambiguous mappings, changed values, changed row counts, "
            "and required-order changes remain failures.",
            "The audit does not estimate how many prior provider failures semantic-v2 will fix "
            "because privacy-safe reports do not retain raw SQL or result rows.",
        ),
    )


def _presentation_variant(case: EvaluationCase) -> QueryResult:
    indices = tuple(reversed(range(len(case.expected_columns))))
    columns = tuple(_presentation_alias(case.expected_columns[index]) for index in indices)
    rows = tuple(tuple(row[index] for index in indices) for row in case.expected_rows)
    return _query_result(columns, rows)


def _presentation_alias(column: str) -> str:
    candidate = column.replace("_", " ").upper()
    if candidate == column:
        candidate = column.lower()
    return candidate if candidate != column else f"{column}_"


def _wrong_value_variant(case: EvaluationCase) -> QueryResult:
    if not case.expected_rows:
        added = (tuple(None for _ in case.expected_columns),)
        return _query_result(case.expected_columns, added)
    rows = [list(row) for row in case.expected_rows]
    rows[0][0] = _different_value(rows[0][0], case.numeric_tolerance)
    return _query_result(case.expected_columns, tuple(tuple(row) for row in rows))


def _different_value(value: Any, tolerance: float) -> Any:
    if value is None:
        return "__different__"
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + max(tolerance + 1.0, 1.0)
    if isinstance(value, str):
        return value + "__different__"
    return repr(value) + "__different__"


def _extra_column_variant(case: EvaluationCase) -> QueryResult:
    columns = (*case.expected_columns, "__unexpected__")
    rows = tuple((*row, None) for row in case.expected_rows)
    return _query_result(columns, rows)


def _query_result(
    columns: tuple[str, ...],
    rows: tuple[tuple[Any, ...], ...],
) -> QueryResult:
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        execution_time_ms=0,
        response_bytes=0,
    )
