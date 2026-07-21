"""Tests for bounded history, feedback, CSV, explorer, and safe system info."""

from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.core.config import AppSettings
from backend.core.errors import InvalidRequestError, ResultTooLargeError
from backend.schemas.database import QueryResult
from backend.schemas.llm import (
    LanguageCode,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)
from backend.schemas.result import FeedbackRating, UXState
from backend.schemas.semantic import SemanticValidationReport
from backend.services.csv_export import CSVExportService
from backend.services.experience_metadata import DatabaseExplorerService, build_safe_system_info
from backend.services.feedback_service import FeedbackService
from backend.services.query_history import QueryHistoryService
from backend.services.schema_service import load_schema_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _result(rows: tuple[tuple[object, ...], ...]) -> QueryResult:
    return QueryResult(
        columns=("label", "value"),
        rows=rows,
        row_count=len(rows),
        truncated=False,
        execution_time_ms=2.0,
        response_bytes=100,
    )


def _response(request_id: str) -> QueryResponse:
    result = _result((("A", 1),))
    return QueryResponse(
        request_id=request_id,
        status=QueryStatus.SUCCESS,
        language=LanguageCode.INDONESIAN,
        generated_sql="SELECT value",
        executed_sql="SELECT value LIMIT 500",
        result=result,
        assumptions=(),
        tables=("Customer",),
        columns=("Customer.CustomerId",),
        confidence=1.0,
        reasoning_summary="Aman.",
        clarification_question=None,
        prompt_version="v1",
        schema_hash="a" * 64,
        provider="fake",
        model="fake",
        llm_latency_ms=1.0,
        database_latency_ms=2.0,
        pipeline=(PipelineEvent(stage=PipelineStage.COMPLETED),),
        warnings=(),
        ui_state=UXState.SUCCESS,
    )


def test_history_is_bounded_and_contains_no_raw_question_sql_or_rows() -> None:
    history = QueryHistoryService(
        max_entries=2,
        now=lambda: datetime(2026, 7, 19, tzinfo=UTC),
    )
    for request_id in ("one", "two", "three"):
        history.record(_response(request_id))

    payload = [entry.model_dump(mode="json") for entry in history.list()]
    serialized = str(payload)

    assert [entry["request_id"] for entry in payload] == ["three", "two"]
    assert "SELECT value" not in serialized
    assert "question" not in serialized.casefold()
    assert "rows" not in serialized.casefold()


def test_disabled_history_is_a_no_op() -> None:
    history = QueryHistoryService(enabled=False)

    assert history.record(_response("disabled")) is None
    assert history.list() == ()


def test_feedback_updates_known_history_and_audits_only_fixed_rating(
    caplog: pytest.LogCaptureFixture,
) -> None:
    history = QueryHistoryService(now=lambda: datetime(2026, 7, 19, tzinfo=UTC))
    history.record(_response("known-request"))
    service = FeedbackService(
        history,
        now=lambda: datetime(2026, 7, 19, 1, tzinfo=UTC),
    )

    with caplog.at_level(logging.INFO, logger="backend.services.feedback_service"):
        record = service.submit("known-request", FeedbackRating.PARTIALLY_CORRECT)

    assert record.rating is FeedbackRating.PARTIALLY_CORRECT
    assert history.list()[0].feedback is FeedbackRating.PARTIALLY_CORRECT
    assert service.list() == (record,)
    assert caplog.records[-1].__dict__["feedback_rating"] == "partially_correct"
    assert "SELECT" not in caplog.records[-1].getMessage()


def test_feedback_rejects_unknown_or_empty_request() -> None:
    service = FeedbackService(QueryHistoryService())

    with pytest.raises(InvalidRequestError):
        service.submit("missing", FeedbackRating.INCORRECT)
    with pytest.raises(InvalidRequestError):
        service.submit(" ", FeedbackRating.INCORRECT)


def test_csv_export_is_bounded_utf8_and_neutralizes_formulas() -> None:
    result = _result((("=2+2", 4), (" safe", 5), ("\t@cmd", 6)))

    exported = CSVExportService(max_bytes=1_000).export("request-123", result)
    rows = list(csv.reader(io.StringIO(exported.data.decode("utf-8-sig"))))

    assert rows[0] == ["label", "value"]
    assert rows[1][0] == "'=2+2"
    assert rows[2][0] == " safe"
    assert rows[3][0] == "'\t@cmd"
    assert exported.formula_cells_escaped == 2
    assert exported.size_bytes == len(exported.data)
    assert result.rows[0][0] == "=2+2"


def test_csv_export_fails_before_returning_oversized_payload() -> None:
    with pytest.raises(ResultTooLargeError) as error:
        CSVExportService(max_bytes=10).export("request", _result((("long-value", 1),)))

    assert error.value.details == {"max_csv_bytes": 10}


def test_database_explorer_contains_schema_metadata_but_no_samples() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    explorer = DatabaseExplorerService(
        snapshot,
        refreshed_at="2026-07-19T00:00:00+00:00",
    ).snapshot()
    invoice = next(table for table in explorer.tables if table.name == "Invoice")
    serialized = explorer.model_dump_json()

    assert len(explorer.tables) == 11
    assert invoice.primary_key == ("InvoiceId",)
    assert any(item.referred_table == "Customer" for item in invoice.relationships)
    assert invoice.review_status == "project_verified"
    assert "sample" not in serialized.casefold()
    assert "password" not in serialized.casefold()


def test_system_info_uses_an_allowlist_and_never_serializes_secret_or_database_url() -> None:
    secret = "never-show-this-provider-secret"
    settings = AppSettings(
        llm_api_key=secret,
        analytics_database_url="sqlite:///sensitive-location.sqlite",
        metadata_database_url="postgresql://user:password@example/db",
        _env_file=None,
    )
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    validation = SemanticValidationReport(
        valid=True,
        semantic_version="v1",
        schema_hash=snapshot.schema_hash,
        content_hash="b" * 64,
        term_count=9,
        metric_count=10,
        join_count=11,
        valid_verified_query_count=10,
    )

    info = build_safe_system_info(settings, snapshot, validation)
    serialized = info.model_dump_json()

    assert info.max_csv_bytes == 1_000_000
    assert secret not in serialized
    assert "sensitive-location" not in serialized
    assert "password" not in serialized.casefold()
    assert "api_key" not in serialized.casefold()
