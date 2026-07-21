"""Request-correlation and privacy-safe aggregate metric tests."""

from uuid import UUID

import pytest

from backend.core.observability import (
    OperationalMetrics,
    bind_request_id,
    current_request_id,
    new_request_id,
    reset_request_id,
    valid_request_id,
)
from backend.schemas.llm import (
    LanguageCode,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)


def _response(status: QueryStatus) -> QueryResponse:
    return QueryResponse(
        request_id=str(UUID(int=3)),
        status=status,
        language=LanguageCode.ENGLISH,
        generated_sql=None,
        clarification_question=None,
        assumptions=(),
        tables=(),
        columns=(),
        confidence=1,
        reasoning_summary="Safe.",
        prompt_version="v2",
        schema_hash="f" * 64,
        semantic_version="v1-postgresql",
        semantic_context_hash="e" * 64,
        provider="fake",
        model="fake-deterministic",
        llm_latency_ms=0,
        pipeline=(PipelineEvent(stage=PipelineStage.COMPLETED),),
        warnings=(),
    )


def test_request_ids_accept_only_canonical_uuid_and_context_resets() -> None:
    request_id = str(UUID(int=1))
    assert valid_request_id(request_id) == request_id
    assert valid_request_id("attacker-controlled\ntext") is None
    assert valid_request_id(None) is None
    assert new_request_id(request_id) == request_id
    assert UUID(new_request_id("invalid"))

    token = bind_request_id(request_id)
    assert current_request_id() == request_id
    reset_request_id(token)
    assert current_request_id() is None
    with pytest.raises(ValueError, match="canonical UUID"):
        bind_request_id("invalid")


def test_operational_metrics_count_states_without_payloads() -> None:
    metrics = OperationalMetrics()
    metrics.record_http(latency_ms=10)
    metrics.record_http(latency_ms=20)
    metrics.record_query(_response(QueryStatus.SUCCESS))
    metrics.record_query(_response(QueryStatus.BLOCKED), repair_attempts=1)
    metrics.record_query(_response(QueryStatus.CLARIFICATION_REQUIRED))
    metrics.record_query_error(timeout=True)

    snapshot = metrics.snapshot()
    assert snapshot.http_requests_total == 2
    assert snapshot.analytics_requests_total == 4
    assert snapshot.uptime_seconds >= 0
    assert snapshot.http_requests_per_second >= 0
    assert snapshot.success_total == 1
    assert snapshot.success_rate == 0.25
    assert snapshot.blocked_total == 1
    assert snapshot.blocked_rate == 0.25
    assert snapshot.clarification_total == 1
    assert snapshot.clarification_rate == 0.25
    assert snapshot.timeout_total == 1
    assert snapshot.timeout_rate == 0.25
    assert snapshot.error_total == 1
    assert snapshot.repair_attempts_total == 1
    assert snapshot.repair_rate == 0.25
    assert snapshot.average_latency_ms == 15
    assert snapshot.max_latency_ms == 20
    assert snapshot.input_tokens_total is None
    assert "question" not in snapshot.__dataclass_fields__
    assert "sql" not in snapshot.__dataclass_fields__
