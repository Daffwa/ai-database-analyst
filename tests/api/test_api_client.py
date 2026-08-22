"""Frontend client accepts every major response state and sanitizes failures."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from backend.schemas.agent import (
    AgentBudgetSnapshot,
    AgentRunResponse,
    AgentState,
    AgentTerminalStatus,
)
from backend.schemas.llm import (
    LanguageCode,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)
from backend.schemas.result import UXState
from frontend.api_client import AnalystAPIClient, APIClientError


def _query_response(status: QueryStatus, state: UXState) -> dict[str, object]:
    response = QueryResponse(
        request_id=f"request-{status.value}",
        status=status,
        language=LanguageCode.INDONESIAN,
        generated_sql=("SELECT 1" if status is QueryStatus.SUCCESS else None),
        executed_sql=("SELECT 1" if status is QueryStatus.SUCCESS else None),
        assumptions=(),
        tables=(),
        columns=(),
        confidence=1,
        reasoning_summary="Aman.",
        clarification_question=("Pilih definisi." if state is UXState.CLARIFICATION else None),
        prompt_version="v2",
        schema_hash="f" * 64,
        semantic_version="v1-postgresql",
        semantic_context_hash="e" * 64,
        provider="fake",
        model="fake",
        llm_latency_ms=0,
        pipeline=(PipelineEvent(stage=PipelineStage.COMPLETED),),
        warnings=(),
        ui_state=state,
    )
    return response.model_dump(mode="json")


@pytest.mark.parametrize(
    ("status", "state"),
    [
        (QueryStatus.SUCCESS, UXState.SUCCESS),
        (QueryStatus.CLARIFICATION_REQUIRED, UXState.CLARIFICATION),
        (QueryStatus.BLOCKED, UXState.BLOCKED),
        (QueryStatus.UNSUPPORTED, UXState.UNSUPPORTED),
    ],
)
def test_frontend_client_accepts_major_query_states(
    status: QueryStatus,
    state: UXState,
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json=_query_response(status, state))
    )
    client = AnalystAPIClient("http://test", transport=transport)
    try:
        response = client.query("pertanyaan")
    finally:
        client.close()
    assert response.status is status
    assert response.ui_state is state


def test_frontend_client_exposes_only_safe_api_error_fields() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            500,
            json={
                "error_code": "INTERNAL_ERROR",
                "message": "The request could not be completed.",
                "request_id": "safe-id",
            },
        )
    )
    client = AnalystAPIClient("http://test", transport=transport)
    try:
        with pytest.raises(APIClientError) as caught:
            client.query("pertanyaan")
    finally:
        client.close()
    assert caught.value.error_code == "INTERNAL_ERROR"
    assert caught.value.request_id == "safe-id"
    assert "traceback" not in str(caught.value).casefold()


def test_frontend_client_sends_a_canonical_correlation_id() -> None:
    observed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.headers["X-Request-ID"])
        return httpx.Response(200, json={"status": "healthy", "api_version": "v1"})

    client = AnalystAPIClient("http://test", transport=httpx.MockTransport(handler))
    try:
        client.health()
    finally:
        client.close()
    assert len(observed) == 1
    assert UUID(observed[0])


def test_frontend_agent_client_sends_original_question_for_safe_durable_resume() -> None:
    observed: dict[str, object] = {}
    response = AgentRunResponse(
        request_id="agent-client-request",
        session_id="ags_client_session_123456",
        state=AgentState.COMPLETED,
        status=AgentTerminalStatus.SUCCESS,
        stop_reason="success",
        budget=AgentBudgetSnapshot(
            steps_used=1,
            max_steps=8,
            repairs_used=0,
            max_repairs=2,
            clarification_rounds=1,
            max_clarification_rounds=2,
            elapsed_ms=1,
            max_runtime_seconds=30,
        ),
        audit=(),
        provider="fake",
        model="fake",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["body"] = request.read().decode("utf-8")
        return httpx.Response(200, json=response.model_dump(mode="json"))

    client = AnalystAPIClient("http://test", transport=httpx.MockTransport(handler))
    try:
        parsed = client.agent_continue(
            "ags_client_session_123456",
            "total_spend",
            "Who is the best customer?",
        )
    finally:
        client.close()
    assert parsed.status is AgentTerminalStatus.SUCCESS
    assert observed["path"] == "/api/v1/agent/continue"
    assert "Who is the best customer?" in str(observed["body"])


def test_frontend_client_supports_uploaded_database_lifecycle() -> None:
    workspace_id = "dbw_" + "a" * 32
    explorer = {
        "source_name": "users.sql",
        "dialect": "sqlite",
        "schema_version": "upload-123456789abc",
        "schema_hash": "f" * 64,
        "refreshed_at": "2026-08-18T00:00:00+00:00",
        "tables": [
            {
                "name": "users",
                "business_description": "Belum ditinjau.",
                "review_status": "uploaded_unreviewed",
                "columns": [
                    {
                        "name": "id",
                        "data_type": "INTEGER",
                        "nullable": False,
                        "primary_key": True,
                    }
                ],
                "primary_key": ["id"],
                "relationships": [],
            }
        ],
    }
    workspace = {
        "workspace_id": workspace_id,
        "source_name": "users.sql",
        "source_type": "sqlite_sql_dump",
        "size_bytes": 24,
        "content_sha256": "e" * 64,
        "created_at": "2026-08-18T00:00:00+00:00",
        "expires_at": "2026-08-18T00:30:00+00:00",
        "table_count": 1,
        "column_count": 1,
        "provider": "fake",
        "model": "fake-deterministic",
        "ai_query_ready": False,
        "warnings": ["Fake provider."],
        "schema_snapshot": explorer,
    }
    observed: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append((request.method, request.url.path, request.read()))
        if request.method == "POST" and request.url.path == "/api/v1/workspaces":
            assert request.headers["X-Upload-Filename"] == "pengguna%20%C3%BC.sql"
            assert not request.url.query
            return httpx.Response(201, json=workspace)
        if request.method == "GET":
            return httpx.Response(200, json=explorer)
        if request.method == "DELETE":
            return httpx.Response(200, json={"workspace_id": workspace_id, "deleted": True})
        return httpx.Response(
            200,
            json=_query_response(QueryStatus.SUCCESS, UXState.SUCCESS),
        )

    client = AnalystAPIClient("http://test", transport=httpx.MockTransport(handler))
    try:
        created = client.create_database_workspace("pengguna ü.sql", b"CREATE TABLE users(id);")
        schema = client.workspace_schema(workspace_id)
        queried = client.workspace_query(workspace_id, "Count users")
        deleted = client.delete_database_workspace(workspace_id)
    finally:
        client.close()

    assert created.workspace_id == workspace_id
    assert schema.tables[0].name == "users"
    assert queried.status is QueryStatus.SUCCESS
    assert deleted.deleted is True
    assert observed[0][2] == b"CREATE TABLE users(id);"
