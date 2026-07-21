"""Deterministic database-result summarization with cell-level evidence."""

from __future__ import annotations

from numbers import Number
from typing import Any

from backend.schemas.llm import LanguageCode
from backend.schemas.result import (
    ChartSpec,
    ChartType,
    NumericEvidence,
    ResultPresentation,
    ResultSummary,
)
from backend.services.result_formatter import temporal_sort_key


class ResultSummarizer:
    """Explain only returned rows and cite every numeric value used in prose."""

    def summarize(
        self,
        result: ResultPresentation,
        chart: ChartSpec | None,
        *,
        language: LanguageCode,
    ) -> ResultSummary:
        """Create a short grounded summary without invoking a language model."""

        if result.row_count == 0:
            return ResultSummary(
                text=(
                    "Kueri berhasil, tetapi tidak ada baris yang cocok."
                    if language is LanguageCode.INDONESIAN
                    else "The query succeeded, but no rows matched."
                )
            )
        if chart is None:
            return self._row_count_summary(result, language)
        if chart.type is ChartType.KPI:
            return self._kpi_summary(result, chart, language)
        if chart.type is ChartType.BAR:
            return self._bar_summary(result, chart, language)
        if chart.type is ChartType.LINE:
            return self._line_summary(result, chart, language)
        return self._row_count_summary(result, language)

    @staticmethod
    def _kpi_summary(
        result: ResultPresentation,
        chart: ChartSpec,
        language: LanguageCode,
    ) -> ResultSummary:
        column = chart.y[0]
        column_index = _column_index(result, column)
        raw = result.rows[0][column_index]
        evidence = _evidence(result, column_index, 0)
        label = result.columns[column_index].label
        text = f"{label}: {result.display_rows[0][column_index]}."
        return ResultSummary(text=text, evidence=(() if raw is None else (evidence,)))

    @staticmethod
    def _bar_summary(
        result: ResultPresentation,
        chart: ChartSpec,
        language: LanguageCode,
    ) -> ResultSummary:
        if chart.x is None or not chart.y:
            return ResultSummarizer._row_count_summary(result, language)
        x_name = chart.x
        x_index = _column_index(result, x_name)
        y_index = _column_index(result, chart.y[0])
        candidates = [
            (row_index, _as_number(row[y_index])) for row_index, row in enumerate(result.rows)
        ]
        numeric = tuple(item for item in candidates if item[1] is not None)
        if not numeric:
            return ResultSummarizer._row_count_summary(result, language)
        row_index, _ = max(numeric, key=lambda item: item[1] or 0)
        category = str(result.rows[row_index][x_index])
        value = result.display_rows[row_index][y_index]
        measure = result.columns[y_index].label
        text = (
            f"Nilai {measure} tertinggi pada baris yang dikembalikan adalah {value} "
            f"untuk {category}."
            if language is LanguageCode.INDONESIAN
            else f"The highest returned {measure} is {value} for {category}."
        )
        return ResultSummary(text=text, evidence=(_evidence(result, y_index, row_index),))

    @staticmethod
    def _line_summary(
        result: ResultPresentation,
        chart: ChartSpec,
        language: LanguageCode,
    ) -> ResultSummary:
        if chart.x is None or not chart.y:
            return ResultSummarizer._row_count_summary(result, language)
        x_name = chart.x
        x_index = _column_index(result, x_name)
        y_index = _column_index(result, chart.y[0])
        ordered = sorted(
            range(result.row_count),
            key=lambda index: (
                temporal_sort_key(result.rows[index][x_index], x_name) or _minimum_datetime()
            ),
        )
        first, last = ordered[0], ordered[-1]
        first_period = result.display_rows[first][x_index]
        last_period = result.display_rows[last][x_index]
        first_value = result.display_rows[first][y_index]
        last_value = result.display_rows[last][y_index]
        measure = result.columns[y_index].label
        text = (
            f"{measure} berubah dari {first_value} pada {first_period} menjadi "
            f"{last_value} pada {last_period}."
            if language is LanguageCode.INDONESIAN
            else f"{measure} moved from {first_value} in {first_period} to "
            f"{last_value} in {last_period}."
        )
        return ResultSummary(
            text=text,
            evidence=(
                _evidence(result, y_index, first),
                _evidence(result, y_index, last),
            ),
        )

    @staticmethod
    def _row_count_summary(
        result: ResultPresentation,
        language: LanguageCode,
    ) -> ResultSummary:
        text = (
            f"Kueri mengembalikan {result.row_count} baris."
            if language is LanguageCode.INDONESIAN
            else f"The query returned {result.row_count} rows."
        )
        if result.truncated:
            text += (
                " Hasil dibatasi; ringkasan hanya mencakup baris yang ditampilkan."
                if language is LanguageCode.INDONESIAN
                else " The result is truncated; this summary covers only displayed rows."
            )
        return ResultSummary(text=text)


def _column_index(result: ResultPresentation, name: str) -> int:
    return tuple(column.name for column in result.columns).index(name)


def _evidence(
    result: ResultPresentation,
    column_index: int,
    row_index: int,
) -> NumericEvidence:
    raw = _as_number(result.rows[row_index][column_index])
    if raw is None:
        raise ValueError("numeric summary evidence must reference a numeric result cell")
    return NumericEvidence(
        column=result.columns[column_index].name,
        row_index=row_index,
        raw_value=raw,
        display_value=result.display_rows[row_index][column_index],
    )


def _as_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, Number):
        return None
    return value if isinstance(value, (int, float)) else float(str(value))


def _minimum_datetime() -> Any:
    from datetime import datetime

    return datetime.min
