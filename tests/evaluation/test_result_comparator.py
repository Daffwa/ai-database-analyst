"""Regression tests for order, NULL, empty, type, and numeric result comparison."""

from __future__ import annotations

from typing import Any

from backend.evaluation.comparator import compare_result
from backend.schemas.database import QueryResult
from backend.schemas.evaluation import EvaluationCase, EvaluationCategory, EvaluationSplit
from backend.schemas.llm import LanguageCode, QueryStatus


def _case(
    rows: tuple[tuple[Any, ...], ...],
    *,
    columns: tuple[str, ...] = ("label", "value"),
    order_sensitive: bool = True,
    tolerance: float = 0.0,
) -> EvaluationCase:
    return EvaluationCase(
        case_id="TST-001",
        dataset_version="test-v1",
        split=EvaluationSplit.DEVELOPMENT,
        category=EvaluationCategory.FILTERING,
        language=LanguageCode.ENGLISH,
        question="Test comparison.",
        expected_status=QueryStatus.SUCCESS,
        expected_sql="SELECT Name AS label, TrackId AS value FROM Track",
        expected_columns=columns,
        expected_rows=rows,
        order_sensitive=order_sensitive,
        numeric_tolerance=tolerance,
        allowed_tables=("Track",),
        allowed_columns=("Track.Name", "Track.TrackId"),
    )


def _result(
    rows: tuple[tuple[Any, ...], ...],
    *,
    columns: tuple[str, ...] = ("label", "value"),
) -> QueryResult:
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        execution_time_ms=1,
        response_bytes=10,
    )


def test_order_sensitive_and_order_insensitive_comparison() -> None:
    expected = (("a", 1), ("b", 2))
    reversed_result = _result(tuple(reversed(expected)))

    assert not compare_result(_case(expected), reversed_result).matched
    assert compare_result(_case(expected, order_sensitive=False), reversed_result).matched


def test_numeric_tolerance_and_numeric_type_normalization() -> None:
    within = compare_result(_case((("value", 1.0),), tolerance=0.01), _result((("value", 1.009),)))
    outside = compare_result(_case((("value", 1),), tolerance=0.01), _result((("value", 1.02),)))

    assert within.matched
    assert not outside.matched


def test_null_empty_and_non_numeric_type_rules() -> None:
    assert compare_result(_case(((None, 1),)), _result(((None, 1.0),))).matched
    assert not compare_result(_case(((None, 1),)), _result((("", 1),))).matched
    assert not compare_result(_case((("1", 1),)), _result(((1, 1),))).matched

    empty_case = _case((), columns=("value",))
    empty_result = _result((), columns=("value",))
    assert compare_result(empty_case, empty_result).matched


def test_column_and_row_count_mismatches_are_explicit() -> None:
    case = _case((("a", 1),))

    column_mismatch = compare_result(case, _result((("a", 1),), columns=("x", "value")))
    count_mismatch = compare_result(case, _result(()))

    assert column_mismatch.mismatch_reason == "columns differ"
    assert count_mismatch.mismatch_reason == "row count differs"
