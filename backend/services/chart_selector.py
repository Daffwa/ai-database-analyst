"""Deterministic, result-only chart selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.schemas.result import (
    ChartOrientation,
    ChartSpec,
    ChartType,
    ColumnRole,
    ResultColumn,
    ResultPresentation,
    ValueFormat,
)
from backend.services.result_formatter import temporal_sort_key


@dataclass(frozen=True, slots=True)
class ChartPolicy:
    """Auditable selection and data-density thresholds."""

    max_bar_categories: int = 50
    max_grouped_measures: int = 3
    recommended_line_points: int = 8
    recommended_scatter_points: int = 8
    long_label_characters: int = 24

    def __post_init__(self) -> None:
        if (
            min(
                self.max_bar_categories,
                self.max_grouped_measures,
                self.recommended_line_points,
                self.recommended_scatter_points,
                self.long_label_characters,
            )
            <= 0
        ):
            raise ValueError("chart policy values must be greater than zero")


class DeterministicChartSelector:
    """Choose the simplest honest chart from returned values and inferred roles."""

    def __init__(self, policy: ChartPolicy | None = None) -> None:
        self._policy = policy or ChartPolicy()

    def select(self, result: ResultPresentation) -> ChartSpec | None:
        """Return a chart specification using only result column names."""

        if result.row_count == 0 or not result.columns:
            return None

        measures = _with_role(result.columns, ColumnRole.MEASURE)
        temporal = _with_role(result.columns, ColumnRole.TEMPORAL)
        dimensions = (
            *_with_role(result.columns, ColumnRole.CATEGORY),
            *_with_role(result.columns, ColumnRole.IDENTIFIER),
        )

        if result.row_count == 1 and len(result.columns) == 1 and len(measures) == 1:
            measure = measures[0]
            return ChartSpec(
                type=ChartType.KPI,
                y=(measure.name,),
                title=measure.label,
                subtitle="One database-returned value",
                y_label=measure.label,
                format=measure.format,
                non_color_distinction="Exact value label; color is not used as evidence.",
                data_row_count=1,
            )

        if temporal and measures and _valid_temporal_axis(result, temporal[0]):
            x = temporal[0]
            y = measures[: self._policy.max_grouped_measures]
            warnings = (
                ("The time series has fewer than eight points; interpret shape cautiously.",)
                if result.row_count < self._policy.recommended_line_points
                else ()
            )
            return ChartSpec(
                type=ChartType.LINE,
                x=x.name,
                y=tuple(column.name for column in y),
                title=_comparison_title(y, x),
                subtitle=f"{result.row_count} ordered time points from returned rows",
                x_label=x.label,
                y_label=_measure_label(y),
                format=y[0].format,
                palette=("#2563EB", "#B7791F", "#C05621")[: len(y)],
                non_color_distinction="Series use direct axis labels and distinct line positions.",
                data_row_count=result.row_count,
                warnings=warnings,
            )

        if dimensions and measures:
            x = dimensions[0]
            y = measures[: self._policy.max_grouped_measures]
            if result.row_count <= self._policy.max_bar_categories:
                orientation = (
                    ChartOrientation.HORIZONTAL
                    if _has_long_labels(result, x, self._policy.long_label_characters)
                    else ChartOrientation.VERTICAL
                )
                warnings = (
                    (
                        "The comparison has fewer than four categories; exact labels carry "
                        "more evidence than bar shape.",
                    )
                    if result.row_count < 4
                    else ()
                )
                return ChartSpec(
                    type=ChartType.BAR,
                    x=x.name,
                    y=tuple(column.name for column in y),
                    title=_comparison_title(y, x),
                    subtitle=f"{result.row_count} categories; bars use a zero baseline",
                    x_label=x.label,
                    y_label=_measure_label(y),
                    format=y[0].format,
                    orientation=orientation,
                    palette=("#2563EB", "#B7791F", "#C05621")[: len(y)],
                    non_color_distinction=(
                        "Axis labels identify categories; no redundant category legend is used."
                    ),
                    data_row_count=result.row_count,
                    warnings=warnings,
                )

        if len(measures) >= 2:
            x_measure, y_measure = measures[:2]
            warnings = (
                (
                    "The relationship view has fewer than eight observations; clustering and "
                    "correlation should not be inferred.",
                )
                if result.row_count < self._policy.recommended_scatter_points
                else ()
            )
            return ChartSpec(
                type=ChartType.SCATTER,
                x=x_measure.name,
                y=(y_measure.name,),
                title=f"{y_measure.label} versus {x_measure.label}",
                subtitle=f"{result.row_count} observations at the returned query grain",
                x_label=x_measure.label,
                y_label=y_measure.label,
                format=y_measure.format,
                non_color_distinction="Point position carries both quantitative comparisons.",
                data_row_count=result.row_count,
                warnings=warnings,
            )

        warnings = (
            (
                (
                    "A categorical chart was not selected because the returned row count exceeds "
                    "the configured category limit."
                ),
            )
            if dimensions and measures
            else ()
        )
        return ChartSpec(
            type=ChartType.TABLE,
            title="Database result",
            subtitle=f"{result.row_count} returned rows for exact lookup",
            format=ValueFormat.TEXT,
            non_color_distinction="Exact values are presented in a table; color is not required.",
            data_row_count=result.row_count,
            warnings=warnings,
        )


def sorted_chart_records(
    result: ResultPresentation,
    chart: ChartSpec,
) -> list[dict[str, Any]]:
    """Build renderer input and sort time axes without altering the base result."""

    records = [
        dict(zip((column.name for column in result.columns), row, strict=True))
        for row in result.rows
    ]
    if chart.type is ChartType.LINE and chart.x is not None:
        x_name = chart.x
        for record in records:
            temporal_value = temporal_sort_key(record[x_name], x_name)
            if temporal_value is not None:
                record[x_name] = temporal_value
        records.sort(key=lambda record: record[x_name])
    return records


def _with_role(
    columns: tuple[ResultColumn, ...],
    role: ColumnRole,
) -> tuple[ResultColumn, ...]:
    return tuple(column for column in columns if column.role is role)


def _valid_temporal_axis(result: ResultPresentation, column: ResultColumn) -> bool:
    index = tuple(item.name for item in result.columns).index(column.name)
    keys = tuple(temporal_sort_key(row[index], column.name) for row in result.rows)
    return all(key is not None for key in keys) and len(set(keys)) == len(keys)


def _has_long_labels(
    result: ResultPresentation,
    column: ResultColumn,
    threshold: int,
) -> bool:
    index = tuple(item.name for item in result.columns).index(column.name)
    return any(len(str(row[index])) > threshold for row in result.rows)


def _comparison_title(measures: tuple[ResultColumn, ...], dimension: ResultColumn) -> str:
    return f"{_measure_label(measures)} by {dimension.label}"


def _measure_label(measures: tuple[ResultColumn, ...]) -> str:
    return " and ".join(measure.label for measure in measures)
