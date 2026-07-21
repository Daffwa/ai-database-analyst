"""Tests for grounded summaries, UX states, and result orchestration."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from backend.core.errors import QueryExecutionError, QueryTimeoutError
from backend.schemas.database import QueryResult
from backend.schemas.llm import (
    LanguageCode,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)
from backend.schemas.result import ChartType, UXState
from backend.services.chart_selector import DeterministicChartSelector
from backend.services.query_history import QueryHistoryService
from backend.services.result_experience import ResultExperienceOrchestrator, ux_state_for_error
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer


def _result(
    columns: tuple[str, ...],
    rows: tuple[tuple[object, ...], ...],
) -> QueryResult:
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        execution_time_ms=2.0,
        response_bytes=100,
    )


def _response(
    result: QueryResult | None,
    *,
    status: QueryStatus = QueryStatus.SUCCESS,
) -> QueryResponse:
    return QueryResponse(
        request_id="00000000-0000-0000-0000-000000000006",
        status=status,
        language=LanguageCode.INDONESIAN,
        generated_sql="SELECT 1" if result is not None else None,
        executed_sql="SELECT 1" if result is not None else None,
        result=result,
        assumptions=(),
        tables=("Customer",) if result is not None else (),
        columns=("Customer.CustomerId",) if result is not None else (),
        confidence=1.0,
        reasoning_summary="Ringkasan usulan.",
        clarification_question=(
            "Pilih definisi." if status is QueryStatus.CLARIFICATION_REQUIRED else None
        ),
        prompt_version="v1",
        schema_hash="a" * 64,
        provider="fake",
        model="fake-deterministic",
        llm_latency_ms=1.0,
        database_latency_ms=(2.0 if result is not None else None),
        pipeline=(
            PipelineEvent(stage=PipelineStage.QUERY_EXECUTED),
            PipelineEvent(stage=PipelineStage.COMPLETED),
        ),
        warnings=(),
    )


class _StubProcessor:
    def __init__(self, response: QueryResponse) -> None:
        self.response = response

    async def process(self, question: str) -> QueryResponse:
        del question
        return self.response


def _experience(
    response: QueryResponse,
) -> tuple[ResultExperienceOrchestrator, QueryHistoryService]:
    history = QueryHistoryService(
        now=lambda: datetime(2026, 7, 19, tzinfo=UTC),
    )
    return (
        ResultExperienceOrchestrator(
            _StubProcessor(response),
            ResultFormatter(),
            DeterministicChartSelector(),
            ResultSummarizer(),
            history,
        ),
        history,
    )


def test_kpi_summary_references_exact_database_cell() -> None:
    presentation = ResultFormatter().format(_result(("customer_count",), ((59,),)))
    chart = DeterministicChartSelector().select(presentation)

    summary = ResultSummarizer().summarize(
        presentation,
        chart,
        language=LanguageCode.INDONESIAN,
    )

    assert summary.text == "Customer Count: 59."
    assert summary.evidence[0].column == "customer_count"
    assert summary.evidence[0].row_index == 0
    assert summary.evidence[0].raw_value == presentation.rows[0][0]


def test_bar_summary_uses_highest_returned_value_and_its_category() -> None:
    presentation = ResultFormatter().format(
        _result(("Country", "revenue"), (("A", -5.0), ("B", -2.0), ("C", -10.0)))
    )
    chart = DeterministicChartSelector().select(presentation)

    summary = ResultSummarizer().summarize(
        presentation,
        chart,
        language=LanguageCode.ENGLISH,
    )

    assert "B" in summary.text
    assert "-2.00" in summary.text
    assert summary.evidence[0].raw_value == -2.0
    assert summary.evidence[0].row_index == 1


def test_line_summary_uses_chronological_first_and_last_rows() -> None:
    presentation = ResultFormatter().format(
        _result(
            ("month", "revenue"),
            (("2024-03", 3.0), ("2024-01", 1.0), ("2024-02", 2.0)),
        )
    )
    chart = DeterministicChartSelector().select(presentation)
    assert chart is not None and chart.type is ChartType.LINE

    summary = ResultSummarizer().summarize(
        presentation,
        chart,
        language=LanguageCode.INDONESIAN,
    )

    assert "1.00 pada 2024-01" in summary.text
    assert "3.00 pada 2024-03" in summary.text
    assert tuple(evidence.row_index for evidence in summary.evidence) == (1, 0)


def test_empty_summary_is_a_valid_non_error_state() -> None:
    presentation = ResultFormatter().format(_result(("Country",), ()))

    summary = ResultSummarizer().summarize(
        presentation,
        None,
        language=LanguageCode.INDONESIAN,
    )

    assert summary.text == "Kueri berhasil, tetapi tidak ada baris yang cocok."
    assert not summary.evidence


def test_experience_enriches_success_without_changing_result_values() -> None:
    original = _result(("customer_count",), ((59,),))
    service, history = _experience(_response(original))

    response = asyncio.run(service.process("Berapa pelanggan?"))

    assert response.status is QueryStatus.SUCCESS
    assert response.ui_state is UXState.SUCCESS
    assert response.result is original
    assert response.presentation is not None
    assert response.presentation.rows == original.rows
    assert response.chart is not None and response.chart.type is ChartType.KPI
    assert response.summary_evidence[0].raw_value == 59
    assert {event.stage for event in response.pipeline} >= {
        PipelineStage.RESULT_NORMALIZED,
        PipelineStage.CHART_SELECTED,
        PipelineStage.RESULT_SUMMARIZED,
        PipelineStage.HISTORY_RECORDED,
    }
    assert history.list()[0].row_count == 1


def test_experience_maps_zero_rows_to_empty_result_and_keeps_successful_execution() -> None:
    service, history = _experience(_response(_result(("Country",), ())))

    response = asyncio.run(service.process("Tidak ada hasil"))

    assert response.status is QueryStatus.EMPTY_RESULT
    assert response.ui_state is UXState.EMPTY
    assert response.result is not None
    assert response.result.row_count == 0
    assert response.chart is None
    assert "tidak ada baris" in (response.explanation or "")
    assert history.list()[0].status == "empty_result"


def test_experience_maps_and_records_clarification_without_result_processing() -> None:
    service, history = _experience(_response(None, status=QueryStatus.CLARIFICATION_REQUIRED))

    response = asyncio.run(service.process("Pelanggan terbaik?"))

    assert response.ui_state is UXState.CLARIFICATION
    assert response.presentation is None
    assert response.chart is None
    assert PipelineStage.RESULT_NORMALIZED not in {event.stage for event in response.pipeline}
    assert history.list()[0].ui_state is UXState.CLARIFICATION


@pytest.mark.parametrize(
    ("status", "expected_state", "message_fragment"),
    [
        (QueryStatus.BLOCKED, UXState.BLOCKED, "kebijakan keamanan"),
        (QueryStatus.UNSUPPORTED, UXState.UNSUPPORTED, "belum didukung"),
    ],
)
def test_experience_maps_non_result_states(
    status: QueryStatus,
    expected_state: UXState,
    message_fragment: str,
) -> None:
    service, history = _experience(_response(None, status=status))

    response = asyncio.run(service.process("Pertanyaan non-result"))

    assert response.ui_state is expected_state
    assert message_fragment in (response.explanation or "")
    assert response.presentation is None
    assert history.list()[0].ui_state is expected_state


@pytest.mark.parametrize(
    ("error", "expected_state"),
    [
        (QueryTimeoutError(), UXState.TIMEOUT),
        (QueryExecutionError(), UXState.ERROR),
    ],
)
def test_runtime_errors_have_explicit_failure_states(
    error: QueryTimeoutError | QueryExecutionError,
    expected_state: UXState,
) -> None:
    assert ux_state_for_error(error) is expected_state


def test_summary_can_be_disabled_without_disabling_result_and_chart() -> None:
    history = QueryHistoryService()
    service = ResultExperienceOrchestrator(
        _StubProcessor(_response(_result(("customer_count",), ((59,),)))),
        ResultFormatter(),
        DeterministicChartSelector(),
        ResultSummarizer(),
        history,
        enable_summary=False,
    )

    response = asyncio.run(service.process("Berapa pelanggan?"))

    assert response.presentation is not None
    assert response.chart is not None
    assert response.explanation is None
    assert not response.summary_evidence
