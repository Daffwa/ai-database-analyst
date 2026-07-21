"""Tahap 6 result normalization, charting, summarization, and history boundary."""

from __future__ import annotations

from backend.core.errors import AppError, ErrorCode
from backend.core.logging import get_logger
from backend.schemas.llm import (
    LanguageCode,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)
from backend.schemas.result import UXState
from backend.services.chart_selector import DeterministicChartSelector
from backend.services.orchestrator import QueryProcessor
from backend.services.query_history import QueryHistoryService
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer

LOGGER = get_logger(__name__)


def ux_state_for_error(error: AppError) -> UXState:
    """Map sanitized runtime errors to the two explicit failure UI states."""

    return UXState.TIMEOUT if error.code is ErrorCode.QUERY_TIMEOUT else UXState.ERROR


class ResultExperienceOrchestrator:
    """Enrich safe database responses without changing raw rows or SQL decisions."""

    def __init__(
        self,
        downstream: QueryProcessor,
        formatter: ResultFormatter,
        chart_selector: DeterministicChartSelector,
        summarizer: ResultSummarizer,
        history: QueryHistoryService,
        *,
        enable_summary: bool = True,
    ) -> None:
        self._downstream = downstream
        self._formatter = formatter
        self._chart_selector = chart_selector
        self._summarizer = summarizer
        self._history = history
        self._enable_summary = enable_summary

    async def process(self, question: str) -> QueryResponse:
        """Process, present, and record one request through explicit result stages."""

        response = await self._downstream.process(question)
        events: list[PipelineEvent] = []
        updates: dict[str, object] = {
            "ui_state": _state_for(response.status),
            "explanation": _state_explanation(response),
        }
        if response.status in {QueryStatus.SUCCESS, QueryStatus.TRUSTED_DEMO_SUCCESS}:
            if response.result is None:
                raise RuntimeError("successful response must contain a database result")
            physical_tables = (
                response.validation.tables if response.validation is not None else response.tables
            )
            presentation = self._formatter.format(
                response.result,
                source_tables=physical_tables,
                source_columns=response.columns,
            )
            chart = self._chart_selector.select(presentation)
            updates.update(
                {
                    "status": (
                        QueryStatus.EMPTY_RESULT if presentation.row_count == 0 else response.status
                    ),
                    "presentation": presentation,
                    "chart": chart,
                    "ui_state": (UXState.EMPTY if presentation.row_count == 0 else UXState.SUCCESS),
                    "warnings": tuple(
                        dict.fromkeys(
                            (
                                *response.warnings,
                                *presentation.warnings,
                                *(chart.warnings if chart is not None else ()),
                            )
                        )
                    ),
                }
            )
            events.extend(
                (
                    PipelineEvent(stage=PipelineStage.RESULT_NORMALIZED),
                    PipelineEvent(stage=PipelineStage.CHART_SELECTED),
                )
            )
            if self._enable_summary:
                summary = self._summarizer.summarize(
                    presentation,
                    chart,
                    language=response.language,
                )
                updates.update(
                    {
                        "explanation": summary.text,
                        "summary_evidence": summary.evidence,
                    }
                )
                events.append(PipelineEvent(stage=PipelineStage.RESULT_SUMMARIZED))

        enriched = response.model_copy(update=updates)
        enriched = enriched.model_copy(update={"pipeline": _append_events(enriched, *events)})
        history_entry = self._history.record(enriched)
        if history_entry is not None:
            enriched = enriched.model_copy(
                update={
                    "pipeline": _append_events(
                        enriched,
                        PipelineEvent(stage=PipelineStage.HISTORY_RECORDED),
                    )
                }
            )
        LOGGER.info(
            "Result experience assembled",
            extra={
                "request_id": enriched.request_id,
                "query_status": enriched.status.value,
                "ui_state": enriched.ui_state.value if enriched.ui_state else None,
                "result_row_count": enriched.result.row_count if enriched.result else None,
                "chart_type": enriched.chart.type.value if enriched.chart else None,
                "summary_evidence_count": len(enriched.summary_evidence),
            },
        )
        return enriched


def _append_events(
    response: QueryResponse,
    *events: PipelineEvent,
) -> tuple[PipelineEvent, ...]:
    retained = tuple(
        event for event in response.pipeline if event.stage is not PipelineStage.COMPLETED
    )
    return (*retained, *events, PipelineEvent(stage=PipelineStage.COMPLETED))


def _state_for(status: QueryStatus) -> UXState:
    return {
        QueryStatus.SUCCESS: UXState.SUCCESS,
        QueryStatus.TRUSTED_DEMO_SUCCESS: UXState.SUCCESS,
        QueryStatus.EMPTY_RESULT: UXState.EMPTY,
        QueryStatus.CLARIFICATION_REQUIRED: UXState.CLARIFICATION,
        QueryStatus.BLOCKED: UXState.BLOCKED,
        QueryStatus.UNSUPPORTED: UXState.UNSUPPORTED,
        QueryStatus.GENERATED_PENDING_SECURITY: UXState.PENDING,
    }[status]


def _state_explanation(response: QueryResponse) -> str | None:
    language = response.language
    if response.status is QueryStatus.CLARIFICATION_REQUIRED:
        return (
            "Pilih satu interpretasi sebelum analisis dilanjutkan."
            if language is LanguageCode.INDONESIAN
            else "Choose one interpretation before analysis continues."
        )
    if response.status is QueryStatus.BLOCKED:
        return (
            "Kueri tidak dijalankan karena kebijakan keamanan memblokirnya."
            if language is LanguageCode.INDONESIAN
            else "The query was not executed because the security policy blocked it."
        )
    if response.status is QueryStatus.UNSUPPORTED:
        return (
            "Pertanyaan belum didukung oleh runtime lokal."
            if language is LanguageCode.INDONESIAN
            else "The local runtime does not support this question yet."
        )
    if response.status in {
        QueryStatus.SUCCESS,
        QueryStatus.TRUSTED_DEMO_SUCCESS,
        QueryStatus.EMPTY_RESULT,
    }:
        return None
    return response.reasoning_summary
