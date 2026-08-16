"""Versioned execution-result comparison with fail-closed semantic alignment."""

from __future__ import annotations

import math
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.schemas.database import QueryResult
from backend.schemas.evaluation import (
    ColumnMatchMode,
    EvaluationCase,
    ResultComparison,
    ResultComparisonPolicy,
)


def compare_result(
    case: EvaluationCase,
    actual: QueryResult,
    *,
    policy: ResultComparisonPolicy = ResultComparisonPolicy.STRICT_V1,
) -> ResultComparison:
    """Compare executed rows without relying on exact SQL string identity."""

    if actual.row_count != len(actual.rows) or any(
        len(row) != len(actual.columns) for row in actual.rows
    ):
        return ResultComparison(
            matched=False,
            columns_match=False,
            row_count_match=False,
            rows_match=False,
            mismatch_reason="result shape is internally inconsistent",
            comparison_policy=policy,
            column_match_mode=ColumnMatchMode.MISMATCH,
        )
    if policy is ResultComparisonPolicy.STRICT_V1:
        return _compare_strict(case, actual)
    return _compare_semantic(case, actual)


def _compare_strict(case: EvaluationCase, actual: QueryResult) -> ResultComparison:
    columns_match = actual.columns == case.expected_columns
    row_count_match = actual.row_count == len(case.expected_rows)
    if not columns_match:
        return ResultComparison(
            matched=False,
            columns_match=False,
            row_count_match=row_count_match,
            rows_match=False,
            mismatch_reason="columns differ",
            comparison_policy=ResultComparisonPolicy.STRICT_V1,
            column_match_mode=ColumnMatchMode.MISMATCH,
        )
    if not row_count_match:
        return ResultComparison(
            matched=False,
            columns_match=True,
            row_count_match=False,
            rows_match=False,
            mismatch_reason="row count differs",
            comparison_policy=ResultComparisonPolicy.STRICT_V1,
            column_match_mode=ColumnMatchMode.EXACT,
        )

    rows_match = _rows_match(case, actual.rows)
    return ResultComparison(
        matched=rows_match,
        columns_match=True,
        row_count_match=True,
        rows_match=rows_match,
        mismatch_reason=None if rows_match else "row values or ordering differ",
        comparison_policy=ResultComparisonPolicy.STRICT_V1,
        column_match_mode=ColumnMatchMode.EXACT,
    )


def _compare_semantic(case: EvaluationCase, actual: QueryResult) -> ResultComparison:
    if len(actual.columns) != len(case.expected_columns):
        return _semantic_mismatch(
            row_count_match=actual.row_count == len(case.expected_rows),
            reason="column count differs",
        )

    row_count_match = actual.row_count == len(case.expected_rows)
    if not row_count_match:
        return ResultComparison(
            matched=False,
            columns_match=False,
            row_count_match=False,
            rows_match=False,
            mismatch_reason="row count differs",
            comparison_policy=ResultComparisonPolicy.SEMANTIC_V2,
            column_match_mode=ColumnMatchMode.MISMATCH,
        )

    alignment: tuple[int, ...] | None
    if actual.columns == case.expected_columns:
        alignment = tuple(range(len(actual.columns)))
        mode = ColumnMatchMode.EXACT
    else:
        alignment = _normalized_name_alignment(case.expected_columns, actual.columns)
        mode = ColumnMatchMode.NORMALIZED
        if alignment is None:
            alignment = _unique_value_alignment(case, actual)
            mode = ColumnMatchMode.VALUE_ALIGNED

    if alignment is None:
        return _semantic_mismatch(
            row_count_match=True,
            reason="column identity or values differ",
        )

    aligned_rows = tuple(tuple(row[index] for index in alignment) for row in actual.rows)
    rows_match = _rows_match(case, aligned_rows)
    presentation_equivalent = mode is not ColumnMatchMode.EXACT
    return ResultComparison(
        matched=rows_match,
        columns_match=True,
        row_count_match=True,
        rows_match=rows_match,
        mismatch_reason=None if rows_match else "row values or required ordering differ",
        comparison_policy=ResultComparisonPolicy.SEMANTIC_V2,
        column_match_mode=mode,
        presentation_equivalent=presentation_equivalent and rows_match,
    )


def _semantic_mismatch(*, row_count_match: bool, reason: str) -> ResultComparison:
    return ResultComparison(
        matched=False,
        columns_match=False,
        row_count_match=row_count_match,
        rows_match=False,
        mismatch_reason=reason,
        comparison_policy=ResultComparisonPolicy.SEMANTIC_V2,
        column_match_mode=ColumnMatchMode.MISMATCH,
    )


def _normalized_name_alignment(
    expected_columns: tuple[str, ...],
    actual_columns: tuple[str, ...],
) -> tuple[int, ...] | None:
    expected_keys = tuple(_canonical_column_name(name) for name in expected_columns)
    actual_keys = tuple(_canonical_column_name(name) for name in actual_columns)
    if (
        any(not key for key in (*expected_keys, *actual_keys))
        or len(set(expected_keys)) != len(expected_keys)
        or len(set(actual_keys)) != len(actual_keys)
        or set(expected_keys) != set(actual_keys)
    ):
        return None
    actual_by_key = {key: index for index, key in enumerate(actual_keys)}
    return tuple(actual_by_key[key] for key in expected_keys)


def _canonical_column_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _unique_value_alignment(
    case: EvaluationCase,
    actual: QueryResult,
) -> tuple[int, ...] | None:
    if not case.expected_rows:
        return None

    expected_keys = tuple(_canonical_column_name(name) for name in case.expected_columns)
    actual_keys = tuple(_canonical_column_name(name) for name in actual.columns)
    if (
        any(not key for key in (*expected_keys, *actual_keys))
        or len(set(expected_keys)) != len(expected_keys)
        or len(set(actual_keys)) != len(actual_keys)
    ):
        return None

    actual_by_key = {key: index for index, key in enumerate(actual_keys)}
    locked: dict[int, int] = {}
    for expected_index, key in enumerate(expected_keys):
        actual_index = actual_by_key.get(key)
        if actual_index is None:
            continue
        if not _column_values_equal(case, actual, expected_index, actual_index):
            return None
        locked[expected_index] = actual_index

    available_actual = set(range(len(actual.columns))) - set(locked.values())
    candidates: dict[int, tuple[int, ...]] = {}
    for expected_index in range(len(case.expected_columns)):
        if expected_index in locked:
            continue
        candidates[expected_index] = tuple(
            actual_index
            for actual_index in sorted(available_actual)
            if _column_values_equal(case, actual, expected_index, actual_index)
        )
        if not candidates[expected_index]:
            return None

    inferred = _unique_perfect_matching(candidates)
    if inferred is None:
        return None
    mapping = {**locked, **inferred}
    if len(mapping) != len(case.expected_columns):
        return None
    return tuple(mapping[index] for index in range(len(case.expected_columns)))


def _column_values_equal(
    case: EvaluationCase,
    actual: QueryResult,
    expected_index: int,
    actual_index: int,
) -> bool:
    expected_values = tuple(row[expected_index] for row in case.expected_rows)
    actual_values = tuple(row[actual_index] for row in actual.rows)
    if case.order_sensitive:
        return all(
            _values_equal(expected, observed, case.numeric_tolerance)
            for expected, observed in zip(expected_values, actual_values, strict=True)
        )
    return _unordered_values_equal(expected_values, actual_values, case.numeric_tolerance)


def _unique_perfect_matching(
    candidates: dict[int, tuple[int, ...]],
) -> dict[int, int] | None:
    matching = _perfect_matching(candidates)
    if matching is None:
        return None
    for expected_index, actual_index in matching.items():
        reduced = {
            index: tuple(
                candidate
                for candidate in options
                if not (index == expected_index and candidate == actual_index)
            )
            for index, options in candidates.items()
        }
        if _perfect_matching(reduced) is not None:
            return None
    return matching


def _perfect_matching(candidates: dict[int, tuple[int, ...]]) -> dict[int, int] | None:
    actual_to_expected: dict[int, int] = {}

    def assign(expected_index: int, visited: set[int]) -> bool:
        for actual_index in candidates[expected_index]:
            if actual_index in visited:
                continue
            visited.add(actual_index)
            previous = actual_to_expected.get(actual_index)
            if previous is None or assign(previous, visited):
                actual_to_expected[actual_index] = expected_index
                return True
        return False

    for expected_index in candidates:
        if not assign(expected_index, set()):
            return None
    return {expected: actual for actual, expected in actual_to_expected.items()}


def _rows_match(case: EvaluationCase, actual_rows: tuple[tuple[Any, ...], ...]) -> bool:
    if case.order_sensitive:
        return all(
            _rows_equal(expected, observed, case.numeric_tolerance)
            for expected, observed in zip(case.expected_rows, actual_rows, strict=True)
        )
    return _unordered_rows_equal(case.expected_rows, actual_rows, case.numeric_tolerance)


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


def _unordered_values_equal(
    expected_values: tuple[Any, ...],
    actual_values: tuple[Any, ...],
    tolerance: float,
) -> bool:
    remaining = list(actual_values)
    for expected in expected_values:
        match_index = next(
            (
                index
                for index, observed in enumerate(remaining)
                if _values_equal(expected, observed, tolerance)
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
