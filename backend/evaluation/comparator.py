"""Execution-result comparison with explicit order, NULL, type, and tolerance rules."""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.schemas.database import QueryResult
from backend.schemas.evaluation import EvaluationCase, ResultComparison


def compare_result(case: EvaluationCase, actual: QueryResult) -> ResultComparison:
    """Compare a query result to one case without relying on exact SQL strings."""

    columns_match = actual.columns == case.expected_columns
    row_count_match = actual.row_count == len(case.expected_rows)
    if not columns_match:
        return ResultComparison(
            matched=False,
            columns_match=False,
            row_count_match=row_count_match,
            rows_match=False,
            mismatch_reason="columns differ",
        )
    if not row_count_match:
        return ResultComparison(
            matched=False,
            columns_match=True,
            row_count_match=False,
            rows_match=False,
            mismatch_reason="row count differs",
        )

    if case.order_sensitive:
        rows_match = all(
            _rows_equal(expected, observed, case.numeric_tolerance)
            for expected, observed in zip(case.expected_rows, actual.rows, strict=True)
        )
    else:
        rows_match = _unordered_rows_equal(
            case.expected_rows,
            actual.rows,
            case.numeric_tolerance,
        )
    return ResultComparison(
        matched=rows_match,
        columns_match=True,
        row_count_match=True,
        rows_match=rows_match,
        mismatch_reason=None if rows_match else "row values or ordering differ",
    )


def _unordered_rows_equal(
    expected_rows: tuple[tuple[Any, ...], ...],
    actual_rows: tuple[tuple[Any, ...], ...],
    tolerance: float,
) -> bool:
    remaining = list(actual_rows)
    for expected in expected_rows:
        match_index = next(
            (
                index
                for index, observed in enumerate(remaining)
                if _rows_equal(expected, observed, tolerance)
            ),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return not remaining


def _rows_equal(expected: tuple[Any, ...], actual: tuple[Any, ...], tolerance: float) -> bool:
    return len(expected) == len(actual) and all(
        _values_equal(expected_value, actual_value, tolerance)
        for expected_value, actual_value in zip(expected, actual, strict=True)
    )


def _values_equal(expected: Any, actual: Any, tolerance: float) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual

    expected_number = _decimal_or_none(expected)
    actual_number = _decimal_or_none(actual)
    if expected_number is not None or actual_number is not None:
        if expected_number is None or actual_number is None:
            return False
        return abs(expected_number - actual_number) <= Decimal(str(tolerance))

    if isinstance(expected, (date, datetime)):
        expected = expected.isoformat()
    if isinstance(actual, (date, datetime)):
        actual = actual.isoformat()
    return type(expected) is type(actual) and expected == actual


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
