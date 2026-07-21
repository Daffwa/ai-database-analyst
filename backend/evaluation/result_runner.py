"""Measured Tahap 6 result, visualization, export, and UX evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.evaluation.mini_cases import MINI_EVALUATION_CASES
from backend.evaluation.runner import result_sha256
from backend.runtime.stage6 import Stage6Runtime
from backend.schemas.database import QueryResult
from backend.schemas.llm import LanguageCode, QueryStatus
from backend.schemas.result import ChartType, FeedbackRating
from backend.services.chart_selector import DeterministicChartSelector
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer

RESULT_EVALUATION_VERSION = "stage-6-v1"
EXPECTED_CHARTS = {
    "S3-001": ChartType.KPI,
    "S3-005": ChartType.TABLE,
    "S3-009": ChartType.BAR,
    "S3-016": ChartType.LINE,
}


class ResultEvaluationSummary(BaseModel):
    """Aggregate deterministic UX evidence for the closed 20-case catalog."""

    model_config = ConfigDict(frozen=True)

    evaluation_version: str
    case_count: int = Field(ge=0)
    database_result_matches: int = Field(ge=0)
    presentation_matches: int = Field(ge=0)
    chart_contracts_valid: int = Field(ge=0)
    expected_chart_case_count: int = Field(ge=0)
    expected_chart_matches: int = Field(ge=0)
    grounded_summaries: int = Field(ge=0)
    csv_exports_valid: int = Field(ge=0)
    chart_type_counts: dict[str, int]
    empty_result_state_valid: bool
    feedback_saved: bool
    history_metadata_safe: bool
    database_explorer_table_count: int = Field(ge=0)
    system_info_safe: bool
    failed_case_ids: tuple[str, ...]


async def run_result_evaluation(runtime: Stage6Runtime) -> ResultEvaluationSummary:
    """Run real closed cases and validate every presentation reference."""

    failed: list[str] = []
    database_matches = 0
    presentation_matches = 0
    chart_contracts = 0
    expected_chart_matches = 0
    grounded_summaries = 0
    csv_exports = 0
    chart_counts: dict[str, int] = {}
    responses = []

    for case in MINI_EVALUATION_CASES:
        response = await runtime.demo_runner.run(case.question)
        responses.append(response)
        if (
            response.status is QueryStatus.SUCCESS
            and response.result is not None
            and result_sha256(response.result) == case.expected_result_sha256
        ):
            database_matches += 1
        else:
            failed.append(f"{case.case_id}:database")
            continue

        if (
            response.presentation is not None
            and response.presentation.rows == response.result.rows
            and response.presentation.row_count == response.result.row_count
        ):
            presentation_matches += 1
        else:
            failed.append(f"{case.case_id}:presentation")

        chart = response.chart
        allowed_columns = set(response.result.columns)
        chart_columns = ({chart.x} if chart is not None and chart.x else set()) | (
            set(chart.y) if chart is not None else set()
        )
        if chart is not None and chart_columns <= allowed_columns:
            chart_contracts += 1
            chart_counts[chart.type.value] = chart_counts.get(chart.type.value, 0) + 1
        else:
            failed.append(f"{case.case_id}:chart")

        expected_chart = EXPECTED_CHARTS.get(case.case_id)
        if expected_chart is not None:
            if chart is not None and chart.type is expected_chart:
                expected_chart_matches += 1
            else:
                failed.append(f"{case.case_id}:expected_chart")

        evidence_valid = all(
            response.result.rows[evidence.row_index][response.result.columns.index(evidence.column)]
            == evidence.raw_value
            for evidence in response.summary_evidence
        )
        if response.explanation and evidence_valid:
            grounded_summaries += 1
        else:
            failed.append(f"{case.case_id}:summary")

        try:
            export = runtime.csv_export.export(response.request_id, response.result)
        except Exception:  # pragma: no cover - sanitized into the evaluation failure list
            failed.append(f"{case.case_id}:csv")
        else:
            if export.size_bytes == len(export.data):
                csv_exports += 1
            else:
                failed.append(f"{case.case_id}:csv")

    empty_result = QueryResult(
        columns=("value",),
        rows=(),
        row_count=0,
        truncated=False,
        execution_time_ms=0,
        response_bytes=0,
    )
    empty_presentation = ResultFormatter().format(empty_result)
    empty_chart = DeterministicChartSelector().select(empty_presentation)
    empty_summary = ResultSummarizer().summarize(
        empty_presentation,
        empty_chart,
        language=LanguageCode.INDONESIAN,
    )
    empty_valid = empty_chart is None and "tidak ada baris" in empty_summary.text

    feedback_saved = False
    if responses:
        feedback = runtime.feedback.submit(responses[0].request_id, FeedbackRating.CORRECT)
        feedback_saved = feedback.rating is FeedbackRating.CORRECT

    allowed_history_fields = {
        "request_id",
        "created_at",
        "status",
        "ui_state",
        "sql_fingerprint",
        "row_count",
        "truncated",
        "total_latency_ms",
        "feedback",
    }
    history_entries = runtime.history.list()
    history_safe = bool(history_entries) and all(
        set(entry.model_dump()) == allowed_history_fields for entry in history_entries
    )
    system_payload = runtime.system_info.model_dump_json().casefold()
    system_safe = all(
        forbidden not in system_payload
        for forbidden in ("api_key", "database_url", "password", "credential")
    )
    expected_count = len(MINI_EVALUATION_CASES)
    return ResultEvaluationSummary(
        evaluation_version=RESULT_EVALUATION_VERSION,
        case_count=expected_count,
        database_result_matches=database_matches,
        presentation_matches=presentation_matches,
        chart_contracts_valid=chart_contracts,
        expected_chart_case_count=len(EXPECTED_CHARTS),
        expected_chart_matches=expected_chart_matches,
        grounded_summaries=grounded_summaries,
        csv_exports_valid=csv_exports,
        chart_type_counts=chart_counts,
        empty_result_state_valid=empty_valid,
        feedback_saved=feedback_saved,
        history_metadata_safe=history_safe,
        database_explorer_table_count=len(runtime.database_explorer.tables),
        system_info_safe=system_safe,
        failed_case_ids=tuple(failed),
    )
