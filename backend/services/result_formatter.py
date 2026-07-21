"""Deterministic result normalization and display formatting."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from numbers import Number
from typing import Any

from backend.schemas.database import QueryResult
from backend.schemas.result import ColumnRole, ResultColumn, ResultPresentation, ValueFormat
from backend.schemas.semantic import MetricFormat

_CURRENCY_TOKENS = frozenset(
    {"amount", "price", "revenue", "sales", "spend", "spent", "total", "value"}
)
_PERCENTAGE_TOKENS = frozenset({"percent", "percentage", "pct"})
_TEMPORAL_TOKENS = frozenset({"date", "datetime", "month", "time", "timestamp", "year"})


class ResultFormatter:
    """Create a parallel display view without modifying database-returned values."""

    def __init__(self, metric_formats: Mapping[str, MetricFormat] | None = None) -> None:
        self._metric_formats = dict(metric_formats or {})

    def format(
        self,
        result: QueryResult,
        *,
        source_tables: tuple[str, ...] = (),
        source_columns: tuple[str, ...] = (),
    ) -> ResultPresentation:
        """Infer roles from actual values and return raw and formatted rows together."""

        if result.row_count != len(result.rows):
            raise ValueError("query result row_count does not match returned rows")
        if len(set(result.columns)) != len(result.columns):
            raise ValueError("query result columns must be unique")
        width = len(result.columns)
        if any(len(row) != width for row in result.rows):
            raise ValueError("query result rows must match the column count")

        columns = tuple(
            self._column(
                name,
                tuple(row[index] for row in result.rows),
            )
            for index, name in enumerate(result.columns)
        )
        display_rows = tuple(
            tuple(_format_value(value, columns[index].format) for index, value in enumerate(row))
            for row in result.rows
        )
        warnings: list[str] = []
        if result.truncated:
            warnings.append(
                "The result was truncated at the configured row limit; charts and summaries "
                "cover only returned rows."
            )
        if any(column.format is ValueFormat.CURRENCY for column in columns):
            warnings.append(
                "Currency values are displayed without a symbol because Chinook stores no "
                "currency code."
            )
        return ResultPresentation(
            columns=columns,
            rows=result.rows,
            display_rows=display_rows,
            row_count=result.row_count,
            truncated=result.truncated,
            execution_time_ms=result.execution_time_ms,
            source_tables=source_tables,
            source_columns=source_columns,
            warnings=tuple(warnings),
        )

    def _column(self, name: str, values: tuple[Any, ...]) -> ResultColumn:
        tokens = _name_tokens(name)
        non_null = tuple(value for value in values if value is not None)
        role = _infer_role(tokens, non_null)
        value_format = self._format_for(name, tokens, role, non_null)
        return ResultColumn(
            name=name,
            label=_humanize(name),
            role=role,
            format=value_format,
            nullable=len(non_null) != len(values),
        )

    def _format_for(
        self,
        name: str,
        tokens: tuple[str, ...],
        role: ColumnRole,
        values: tuple[Any, ...],
    ) -> ValueFormat:
        metric_format = self._metric_formats.get(name.casefold())
        if metric_format is MetricFormat.CURRENCY:
            return ValueFormat.CURRENCY
        if metric_format is MetricFormat.INTEGER:
            return ValueFormat.INTEGER
        if metric_format in {MetricFormat.DECIMAL, MetricFormat.DURATION_MS}:
            return ValueFormat.DECIMAL
        if role is ColumnRole.TEMPORAL:
            return (
                ValueFormat.DATETIME
                if any(isinstance(value, datetime) for value in values)
                else ValueFormat.DATE
            )
        if role is ColumnRole.MEASURE or role is ColumnRole.IDENTIFIER:
            if set(tokens) & _PERCENTAGE_TOKENS:
                return ValueFormat.PERCENTAGE
            if set(tokens) & _CURRENCY_TOKENS:
                return ValueFormat.CURRENCY
            if values and all(_is_integer_value(value) for value in values):
                return ValueFormat.INTEGER
            return ValueFormat.DECIMAL
        return ValueFormat.TEXT


def _infer_role(tokens: tuple[str, ...], values: tuple[Any, ...]) -> ColumnRole:
    if tokens and tokens[-1] == "id" and not set(tokens) & {"count", "number"}:
        return ColumnRole.IDENTIFIER
    if (
        set(tokens) & _TEMPORAL_TOKENS
        and values
        and all(_temporal_sort_value(value, tokens) is not None for value in values)
    ):
        return ColumnRole.TEMPORAL
    if values and all(_is_numeric(value) for value in values):
        return ColumnRole.MEASURE
    if values:
        return ColumnRole.CATEGORY
    return ColumnRole.UNKNOWN


def temporal_sort_key(value: Any, column_name: str) -> datetime | None:
    """Return a sortable time value only when the value is genuinely temporal."""

    return _temporal_sort_value(value, _name_tokens(column_name))


def _temporal_sort_value(value: Any, tokens: Sequence[str]) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, int) and "year" in tokens and 1_000 <= value <= 3_000:
        return datetime(value, 1, 1)
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}", normalized):
        normalized = f"{normalized}-01"
    if re.fullmatch(r"\d{4}", normalized) and "year" in tokens:
        normalized = f"{normalized}-01-01"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _format_value(value: Any, value_format: ValueFormat) -> str:
    if value is None:
        return "—"
    if value_format in {ValueFormat.DATE, ValueFormat.DATETIME}:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)
    if value_format is ValueFormat.INTEGER and _is_numeric(value):
        return f"{int(value):,}"
    if value_format in {ValueFormat.DECIMAL, ValueFormat.CURRENCY} and _is_numeric(value):
        return f"{float(value):,.2f}"
    if value_format is ValueFormat.PERCENTAGE and _is_numeric(value):
        return f"{float(value):,.2f}%"
    return str(value)


def _name_tokens(name: str) -> tuple[str, ...]:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).casefold()
    return tuple(token for token in re.split(r"[^a-z0-9]+", snake) if token)


def _humanize(name: str) -> str:
    return " ".join(token.capitalize() for token in _name_tokens(name)) or name


def _is_numeric(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _is_integer_value(value: Any) -> bool:
    return _is_numeric(value) and float(value).is_integer()
