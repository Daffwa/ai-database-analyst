"""Durable continuation repository tests with an attached SQLite schema."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Table, create_engine, event
from sqlalchemy.engine import Engine

from backend.agent.session import PersistedContinuation
from backend.metadata.models import AgentContinuationRecord
from backend.metadata.repository import MetadataRepository


def _engine() -> Engine:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def attach_schema(connection: Any, _record: object) -> None:
        connection.execute("ATTACH DATABASE ':memory:' AS app_metadata")

    cast(Table, AgentContinuationRecord.__table__).create(engine)
    return engine


def _record(identifier: str = "ags_repository_123456") -> PersistedContinuation:
    return PersistedContinuation(
        continuation_id=identifier,
        request_id="request-repository",
        question_digest="a" * 64,
        rule_id="best_customer_measure",
        option_ids=("total_spend", "transaction_count", "latest_transaction"),
        semantic_version="v1",
        semantic_hash="b" * 64,
        language="en",
        steps_used=2,
        clarification_rounds=1,
        elapsed_ms=10,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def test_repository_save_claim_release_consume_and_cancel() -> None:
    engine = _engine()
    repository = MetadataRepository(engine)
    record = _record()
    try:
        repository.save_continuation(record)
        claimed = repository.claim_continuation(record.continuation_id)
        assert claimed == record
        assert repository.claim_continuation(record.continuation_id) is None

        repository.release_continuation(record.continuation_id, retain=True)
        assert repository.claim_continuation(record.continuation_id) == record
        repository.release_continuation(record.continuation_id, retain=False)
        assert repository.claim_continuation(record.continuation_id) is None

        second = _record("ags_repository_cancel_123456")
        repository.save_continuation(second)
        assert repository.cancel_continuation(second.continuation_id) == second
        assert repository.cancel_continuation(second.continuation_id) is None
        repository.release_continuation("missing-continuation", retain=False)
    finally:
        engine.dispose()


def test_repository_upsert_and_expired_records_fail_closed() -> None:
    engine = _engine()
    repository = MetadataRepository(engine)
    record = _record()
    try:
        repository.save_continuation(record)
        updated = replace(
            record,
            steps_used=3,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        repository.save_continuation(updated)
        assert repository.claim_continuation(record.continuation_id) is None
        assert repository.cancel_continuation(record.continuation_id) is None
    finally:
        engine.dispose()
