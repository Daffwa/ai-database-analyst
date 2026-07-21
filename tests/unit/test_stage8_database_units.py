"""Unit coverage for PostgreSQL setup, identity, migration, and metadata adapters."""

from __future__ import annotations

from collections import deque
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.engine import Engine

from alembic import command as alembic_command
from backend.core.errors import ConfigurationError
from backend.data.initialization import CHINOOK_EXPECTED_TABLE_COUNTS
from backend.data.postgres import (
    ANALYTICS_READONLY,
    _apply_analytics_privileges,
    _compatibility_view_statements,
    _configure_database_connect,
    _ensure_database,
    _ensure_role,
    _snake_case,
    _verify_counts,
    application_database_urls,
    psycopg_conninfo,
)
from backend.db.postgres import (
    PostgreSQLIdentity,
    assert_application_identity,
    create_postgresql_engine,
    inspect_postgresql_identity,
)
from backend.metadata import migrations
from backend.metadata.models import DataSourceRecord, QueryFeedbackRecord, QueryRequestRecord
from backend.metadata.repository import MetadataRepository
from backend.schemas.llm import (
    LanguageCode,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)
from backend.schemas.result import FeedbackRating, UXState
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle

ROOT = Path(__file__).resolve().parents[2]


class FakePsycopgResult:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class FakePsycopgConnection:
    def __init__(self, rows: list[tuple[object, ...] | None] | None = None) -> None:
        self.rows = deque(rows or [])
        self.statements: list[object] = []

    def execute(self, statement: object, *_args: object, **_kwargs: object) -> FakePsycopgResult:
        self.statements.append(statement)
        return FakePsycopgResult(self.rows.popleft() if self.rows else None)


def test_postgres_url_helpers_and_role_setup_helpers_cover_both_paths() -> None:
    admin = "postgresql+psycopg://postgres:secret@localhost:5432/postgres"
    assert psycopg_conninfo(admin, database="chinook").startswith("postgresql://postgres")
    analytics, metadata, migration = application_database_urls(
        admin,
        analytics_password="analytics-secret",
        metadata_password="metadata-secret",
        migration_password="migration-secret",
    )
    assert "analytics_readonly" in analytics and analytics.endswith("/chinook")
    assert "app_metadata_user" in metadata
    assert "migration_user" in migration

    missing = FakePsycopgConnection([None, None])
    _ensure_role(cast(Any, missing), "new_role", login=True, password="secret")
    _ensure_database(cast(Any, missing), "new_database", "owner")
    existing = FakePsycopgConnection([(1,), (1,)])
    _ensure_role(cast(Any, existing), "existing_role", login=False)
    _ensure_database(cast(Any, existing), "existing_database", "owner")
    configured = FakePsycopgConnection()
    _configure_database_connect(cast(Any, configured))
    _apply_analytics_privileges(cast(Any, configured))
    assert len(missing.statements) == 4
    assert len(existing.statements) == 4
    assert len(configured.statements) >= 10


def test_compatibility_views_and_count_verification_are_deterministic() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json")
    statements = _compatibility_view_statements(snapshot)
    assert len(statements) == 11
    assert _snake_case("PlaylistTrack") == "playlist_track"
    rows: list[tuple[object, ...] | None] = [
        (value,) for _, value in sorted(CHINOOK_EXPECTED_TABLE_COUNTS.items())
    ]
    connection = FakePsycopgConnection(rows)
    assert _verify_counts(cast(Any, connection)) == dict(
        sorted(CHINOOK_EXPECTED_TABLE_COUNTS.items())
    )
    with pytest.raises(RuntimeError):
        _verify_counts(cast(Any, FakePsycopgConnection([None])))


class FakeSQLAlchemyResult:
    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row

    def one(self) -> tuple[object, ...]:
        return self._row


class FakeSQLAlchemyConnection:
    def __init__(self, row: tuple[object, ...]) -> None:
        self.row = row

    def __enter__(self) -> FakeSQLAlchemyConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _statement: object) -> FakeSQLAlchemyResult:
        return FakeSQLAlchemyResult(self.row)


class FakeIdentityEngine:
    def __init__(self, row: tuple[object, ...]) -> None:
        self.row = row

    def connect(self) -> FakeSQLAlchemyConnection:
        return FakeSQLAlchemyConnection(self.row)


def test_postgres_engine_and_identity_checks_fail_closed() -> None:
    engine = create_postgresql_engine(
        "postgresql+psycopg://analytics_readonly:secret@localhost/chinook",
        expected_username=ANALYTICS_READONLY,
    )
    assert engine.url.password == "secret"
    engine.dispose()

    safe_engine = cast(
        Engine,
        FakeIdentityEngine(("analytics_readonly", "chinook", False, False, False, False)),
    )
    identity = inspect_postgresql_identity(safe_engine)
    assert identity == PostgreSQLIdentity(
        current_user="analytics_readonly",
        current_database="chinook",
        superuser=False,
        create_database=False,
        create_role=False,
        bypass_rls=False,
    )
    assert (
        assert_application_identity(safe_engine, expected_username="analytics_readonly") == identity
    )
    wrong_engine = cast(
        Engine,
        FakeIdentityEngine(("wrong", "chinook", False, False, False, False)),
    )
    with pytest.raises(ConfigurationError):
        assert_application_identity(wrong_engine, expected_username="analytics_readonly")
    privileged = cast(
        Engine,
        FakeIdentityEngine(("analytics_readonly", "chinook", True, False, False, False)),
    )
    with pytest.raises(ConfigurationError):
        assert_application_identity(privileged, expected_username="analytics_readonly")


class FakeAlembicConfig:
    def __init__(self, _path: str) -> None:
        self.attributes: dict[str, object] = {}


class FakeMigrationEngine:
    def begin(self) -> nullcontext[object]:
        return nullcontext(object())

    def dispose(self) -> None:
        return None


def test_programmatic_migration_routes_upgrade_and_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(migrations, "Config", FakeAlembicConfig)
    monkeypatch.setattr(
        migrations, "create_engine", lambda *_args, **_kwargs: FakeMigrationEngine()
    )
    monkeypatch.setattr(
        alembic_command,
        "upgrade",
        lambda _config, revision: calls.append(("upgrade", revision)),
    )
    monkeypatch.setattr(
        alembic_command,
        "downgrade",
        lambda _config, revision: calls.append(("downgrade", revision)),
    )
    migrations.run_metadata_migration(ROOT, "postgresql+psycopg://fake", "head")
    migrations.run_metadata_migration(ROOT, "postgresql+psycopg://fake", "base")
    assert calls == [("upgrade", "head"), ("downgrade", "base")]


def _response() -> QueryResponse:
    return QueryResponse(
        request_id="request-1",
        status=QueryStatus.SUCCESS,
        language=LanguageCode.INDONESIAN,
        generated_sql="SELECT 1",
        executed_sql="SELECT 1",
        assumptions=(),
        tables=("Customer",),
        columns=("Customer.CustomerId",),
        confidence=1,
        reasoning_summary="Aman.",
        clarification_question=None,
        prompt_version="v2",
        schema_hash="f" * 64,
        semantic_version="v1-postgresql",
        semantic_context_hash="e" * 64,
        provider="fake",
        model="fake",
        llm_latency_ms=1,
        pipeline=(PipelineEvent(stage=PipelineStage.COMPLETED),),
        warnings=(),
        ui_state=UXState.SUCCESS,
    )


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.scalar_values: deque[object | None] = deque()
        self.get_value: object | None = None
        self.executed_rows: list[tuple[QueryRequestRecord, QueryFeedbackRecord | None]] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def begin(self) -> FakeSession:
        return self

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if isinstance(value, DataSourceRecord):
                value.id = 1

    def get(self, _model: object, _identity: object) -> object | None:
        return self.get_value

    def scalar(self, _statement: object) -> object | None:
        return self.scalar_values.popleft() if self.scalar_values else None

    def execute(self, _statement: object) -> Any:
        class Rows:
            def __init__(
                self, rows: list[tuple[QueryRequestRecord, QueryFeedbackRecord | None]]
            ) -> None:
                self._rows = rows

            def all(self) -> list[tuple[QueryRequestRecord, QueryFeedbackRecord | None]]:
                return self._rows

        return Rows(self.executed_rows)


def test_metadata_repository_safe_paths_with_mocked_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions: deque[FakeSession] = deque()

    def session_factory(_engine: object) -> FakeSession:
        return sessions.popleft()

    monkeypatch.setattr("backend.metadata.repository.Session", session_factory)
    repository = MetadataRepository(cast(Engine, object()))

    catalog_session = FakeSession()
    sessions.append(catalog_session)
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json")
    bundle = load_semantic_bundle(
        ROOT / "semantic", dialect_overlay=ROOT / "semantic" / "postgresql.yaml"
    )
    repository.synchronize_catalog(snapshot, bundle, snapshot_location="snapshot.json")
    assert len(catalog_session.added) == 12

    record_session = FakeSession()
    sessions.append(record_session)
    repository.record_response(_response())
    assert len(record_session.added) == 3

    request = QueryRequestRecord(
        request_id="request-1",
        status="success",
        ui_state="success",
        language="id",
        prompt_version="v2",
        schema_hash="f" * 64,
        provider="fake",
        model="fake",
        source_tables=[],
        truncated=False,
        llm_latency_ms=1,
        total_latency_ms=1,
        created_at=datetime.now(UTC),
    )
    history_session = FakeSession()
    history_session.executed_rows = [(request, None)]
    sessions.append(history_session)
    assert repository.list_history(limit=10)[0].request_id == "request-1"

    feedback_session = FakeSession()
    feedback_session.get_value = request
    sessions.append(feedback_session)
    feedback = repository.submit_feedback("request-1", FeedbackRating.CORRECT)
    assert feedback.rating is FeedbackRating.CORRECT
