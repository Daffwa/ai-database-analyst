"""Frontend client accepts every major response state and sanitizes failures."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

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
