"""Fail-closed tests for semantic result-comparison policy v2."""

from __future__ import annotations

from typing import Any

from backend.evaluation.comparator import compare_result
from backend.schemas.database import QueryResult
from backend.schemas.evaluation import (
    ColumnMatchMode,
    EvaluationCase,
    EvaluationCategory,
    EvaluationSplit,
    ResultComparisonPolicy,
)
from backend.schemas.llm import LanguageCode, QueryStatus


def _case(
    columns: tuple[str, ...],
    rows: tuple[tuple[Any, ...], ...],
    *,
    order_sensitive: bool = True,
) -> EvaluationCase:
    return EvaluationCase(
        case_id="TST-101",
        dataset_version="test-v2",
        split=EvaluationSplit.DEVELOPMENT,
        category=EvaluationCategory.AGGREGATION,
        language=LanguageCode.ENGLISH,
        question="Test semantic comparison.",
        expected_status=QueryStatus.SUCCESS,
        expected_sql="SELECT 1",
        expected_columns=columns,
        expected_rows=rows,
        order_sensitive=order_sensitive,
        allowed_tables=("Invoice",),
        allowed_columns=("Invoice.Total",),
    )


def _result(columns: tuple[str, ...], rows: tuple[tuple[Any, ...], ...]) -> QueryResult:
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        execution_time_ms=1,
        response_bytes=10,
    )


def test_semantic_v2_accepts_normalized_aliases_and_column_reordering() -> None:
    case = _case(("artist_name", "units_sold"), (("A", 5), ("B", 4)))
    actual = _result(("UNITS SOLD", "ARTIST NAME"), ((5, "A"), (4, "B")))

    assert not compare_result(case, actual).matched
    comparison = compare_result(case, actual, policy=ResultComparisonPolicy.SEMANTIC_V2)

    assert comparison.matched
    assert comparison.column_match_mode is ColumnMatchMode.NORMALIZED
    assert comparison.presentation_equivalent


def test_semantic_v2_accepts_only_unique_value_aligned_aliases() -> None:
    case = _case(("artist_name", "units_sold"), (("A", 5), ("B", 4)))
    actual = _result(("sales", "artist"), ((5, "A"), (4, "B")))

    comparison = compare_result(case, actual, policy=ResultComparisonPolicy.SEMANTIC_V2)

    assert comparison.matched
    assert comparison.column_match_mode is ColumnMatchMode.VALUE_ALIGNED
    assert comparison.presentation_equivalent


def test_semantic_v2_rejects_ambiguous_value_alignment() -> None:
    case = _case(("left_value", "right_value"), ((1, 1), (2, 2)))
    actual = _result(("x", "y"), ((1, 1), (2, 2)))

    comparison = compare_result(case, actual, policy=ResultComparisonPolicy.SEMANTIC_V2)

    assert not comparison.matched
    assert comparison.column_match_mode is ColumnMatchMode.MISMATCH
    assert comparison.mismatch_reason == "column identity or values differ"


def test_semantic_v2_rejects_partial_name_conflicts_and_extra_columns() -> None:
    case = _case(("revenue", "invoice_count"), ((10, 2), (20, 3)))
    misleading = _result(("revenue", "count"), ((2, 10), (3, 20)))
    extra = _result(("revenue", "invoice_count", "extra"), ((10, 2, None), (20, 3, None)))

    misleading_comparison = compare_result(
        case,
        misleading,
        policy=ResultComparisonPolicy.SEMANTIC_V2,
    )
    extra_comparison = compare_result(case, extra, policy=ResultComparisonPolicy.SEMANTIC_V2)

    assert not misleading_comparison.matched
    assert not extra_comparison.matched
    assert extra_comparison.mismatch_reason == "column count differs"


def test_semantic_v2_preserves_required_row_order() -> None:
    rows = (("A", 5), ("B", 4))
    case = _case(("artist_name", "units_sold"), rows)
    reversed_result = _result(("ARTIST NAME", "UNITS SOLD"), tuple(reversed(rows)))

    comparison = compare_result(
        case,
        reversed_result,
        policy=ResultComparisonPolicy.SEMANTIC_V2,
    )

    assert not comparison.matched
    assert comparison.mismatch_reason == "row values or required ordering differ"


def test_semantic_v2_allows_row_order_only_when_case_declares_it_irrelevant() -> None:
    rows = (("A", 5), ("B", 4))
    case = _case(("artist_name", "units_sold"), rows, order_sensitive=False)
    reversed_result = _result(("UNITS SOLD", "ARTIST NAME"), ((4, "B"), (5, "A")))

    comparison = compare_result(
        case,
        reversed_result,
        policy=ResultComparisonPolicy.SEMANTIC_V2,
    )

    assert comparison.matched
    assert comparison.presentation_equivalent


def test_semantic_v2_empty_results_require_name_proof() -> None:
    case = _case(("customer_count",), ())
    normalized = _result(("CUSTOMER COUNT",), ())
    unproven_alias = _result(("count",), ())

    assert compare_result(
        case,
        normalized,
        policy=ResultComparisonPolicy.SEMANTIC_V2,
    ).matched
    assert not compare_result(
        case,
        unproven_alias,
        policy=ResultComparisonPolicy.SEMANTIC_V2,
    ).matched


def test_semantic_v2_rejects_internally_inconsistent_query_results() -> None:
    case = _case(("customer_count",), ((59,),))
    wrong_count = QueryResult(
        columns=("customer_count",),
        rows=((59,),),
        row_count=2,
        truncated=False,
        execution_time_ms=1,
        response_bytes=10,
    )
    wrong_width = QueryResult(
        columns=("customer_count",),
        rows=((59, 60),),
        row_count=1,
        truncated=False,
        execution_time_ms=1,
        response_bytes=10,
    )

    for actual in (wrong_count, wrong_width):
        comparison = compare_result(
            case,
            actual,
            policy=ResultComparisonPolicy.SEMANTIC_V2,
        )
        assert not comparison.matched
        assert comparison.mismatch_reason == "result shape is internally inconsistent"
