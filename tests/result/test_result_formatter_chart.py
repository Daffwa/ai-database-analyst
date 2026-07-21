"""Focused tests for non-mutating formatting and deterministic chart selection."""

from __future__ import annotations

from datetime import date

import pytest

from backend.schemas.database import QueryResult
from backend.schemas.result import ChartOrientation, ChartType, ColumnRole, ValueFormat
from backend.schemas.semantic import MetricFormat
from backend.services.chart_selector import (
    ChartPolicy,
    DeterministicChartSelector,
    sorted_chart_records,
)
from backend.services.result_formatter import ResultFormatter


def _result(
    columns: tuple[str, ...],
    rows: tuple[tuple[object, ...], ...],
    *,
    truncated: bool = False,
) -> QueryResult:
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        execution_time_ms=1.5,
        response_bytes=100,
    )


def test_formatter_preserves_raw_values_and_builds_parallel_display_rows() -> None:
    raw_rows = ((1, date(2026, 7, 19), 12.5, None),)
    presentation = ResultFormatter({"revenue": MetricFormat.CURRENCY}).format(
        _result(("CustomerId", "invoice_date", "revenue", "note"), raw_rows),
        source_tables=("Customer", "Invoice"),
        source_columns=("Customer.CustomerId", "Invoice.Total"),
    )

    assert presentation.rows == raw_rows
    assert presentation.display_rows == (("1", "2026-07-19", "12.50", "—"),)
    assert [column.role for column in presentation.columns] == [
        ColumnRole.IDENTIFIER,
        ColumnRole.TEMPORAL,
        ColumnRole.MEASURE,
        ColumnRole.UNKNOWN,
    ]
    assert presentation.columns[2].format is ValueFormat.CURRENCY
    assert presentation.source_tables == ("Customer", "Invoice")
    assert "currency code" in presentation.warnings[0]


def test_formatter_marks_truncation_and_integer_measure() -> None:
    presentation = ResultFormatter().format(_result(("customer_count",), ((59,),), truncated=True))

    assert presentation.columns[0].role is ColumnRole.MEASURE
    assert presentation.columns[0].format is ValueFormat.INTEGER
    assert presentation.display_rows == (("59",),)
    assert "truncated" in presentation.warnings[0]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            QueryResult(
                columns=("value",),
                rows=((1,),),
                row_count=0,
                truncated=False,
                execution_time_ms=0,
                response_bytes=1,
            ),
            "row_count",
        ),
        (_result(("value", "value"), ((1, 2),)), "unique"),
        (_result(("a", "b"), ((1,),)), "column count"),
    ],
)
def test_formatter_rejects_inconsistent_result_shapes(
    result: QueryResult,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ResultFormatter().format(result)


def test_single_numeric_value_selects_kpi() -> None:
    presentation = ResultFormatter().format(_result(("customer_count",), ((59,),)))

    chart = DeterministicChartSelector().select(presentation)

    assert chart is not None
    assert chart.type is ChartType.KPI
    assert chart.x is None
    assert chart.y == ("customer_count",)


def test_category_and_numeric_measure_select_bar_without_redundant_series() -> None:
    presentation = ResultFormatter().format(
        _result(
            ("Country", "customer_count"),
            (("USA", 13), ("Canada", 8), ("Brazil", 5), ("France", 5)),
        )
    )

    chart = DeterministicChartSelector().select(presentation)

    assert chart is not None
    assert chart.type is ChartType.BAR
    assert chart.x == "Country"
    assert chart.y == ("customer_count",)
    assert chart.palette == ("#2563EB",)
    assert "no redundant" in chart.non_color_distinction


def test_long_category_labels_select_horizontal_bar() -> None:
    presentation = ResultFormatter().format(
        _result(
            ("track", "sales"),
            (("A very long track label that needs horizontal space", 10.0), ("Short", 9.0)),
        )
    )

    chart = DeterministicChartSelector().select(presentation)

    assert chart is not None
    assert chart.type is ChartType.BAR
    assert chart.orientation is ChartOrientation.HORIZONTAL
    assert chart.warnings


def test_valid_time_axis_selects_line_and_renderer_records_are_sorted() -> None:
    presentation = ResultFormatter().format(
        _result(
            ("month", "revenue"),
            tuple(
                (month, float(index))
                for index, month in enumerate(
                    (
                        "2024-03",
                        "2024-01",
                        "2024-02",
                        "2024-04",
                        "2024-05",
                        "2024-06",
                        "2024-07",
                        "2024-08",
                    )
                )
            ),
        )
    )

    chart = DeterministicChartSelector().select(presentation)
    assert chart is not None
    records = sorted_chart_records(presentation, chart)

    assert chart.type is ChartType.LINE
    assert chart.x == "month"
    assert [record["month"].strftime("%Y-%m") for record in records[:3]] == [
        "2024-01",
        "2024-02",
        "2024-03",
    ]


def test_non_temporal_strings_never_select_line_chart() -> None:
    presentation = ResultFormatter().format(
        _result(("month", "revenue"), (("winter", 1.0), ("spring", 2.0)))
    )

    chart = DeterministicChartSelector().select(presentation)

    assert chart is not None
    assert presentation.columns[0].role is ColumnRole.CATEGORY
    assert chart.type is ChartType.BAR


def test_two_continuous_measures_select_scatter_with_density_warning() -> None:
    presentation = ResultFormatter().format(
        _result(("average_value", "total_value"), ((1.0, 2.0), (2.0, 5.0)))
    )

    chart = DeterministicChartSelector().select(presentation)

    assert chart is not None
    assert chart.type is ChartType.SCATTER
    assert chart.x == "average_value"
    assert chart.y == ("total_value",)
    assert "fewer than eight" in chart.warnings[0]


def test_identifiers_are_dimensions_and_never_continuous_scatter_measures() -> None:
    presentation = ResultFormatter().format(
        _result(("CustomerId", "InvoiceId"), ((1, 10), (2, 11), (3, 12)))
    )

    chart = DeterministicChartSelector().select(presentation)

    assert chart is not None
    assert all(column.role is ColumnRole.IDENTIFIER for column in presentation.columns)
    assert chart.type is ChartType.TABLE


def test_chart_never_references_a_column_absent_from_result() -> None:
    presentation = ResultFormatter().format(
        _result(("genre", "sales"), (("Rock", 10.0), ("Jazz", 5.0)))
    )
    chart = DeterministicChartSelector().select(presentation)
    assert chart is not None
    allowed = {column.name for column in presentation.columns}

    assert ({chart.x} if chart.x else set()) | set(chart.y) <= allowed


def test_empty_result_has_no_chart() -> None:
    presentation = ResultFormatter().format(_result(("Country", "revenue"), ()))

    assert DeterministicChartSelector().select(presentation) is None


def test_chart_policy_rejects_non_positive_thresholds() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        ChartPolicy(max_bar_categories=0)


def test_high_cardinality_category_falls_back_to_table() -> None:
    presentation = ResultFormatter().format(
        _result(
            ("category", "sales"),
            tuple((f"Category {index}", float(index)) for index in range(4)),
        )
    )
    selector = DeterministicChartSelector(ChartPolicy(max_bar_categories=3))

    chart = selector.select(presentation)

    assert chart is not None
    assert chart.type is ChartType.TABLE
    assert "category limit" in chart.warnings[0]
