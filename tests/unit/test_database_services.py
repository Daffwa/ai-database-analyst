"""Tests for the read-only engine, schema service, allowlist, and manual executor."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import (
    DatabaseUnavailableError,
    InvalidRequestError,
    QueryExecutionError,
    QueryTimeoutError,
    ResultTooLargeError,
    SchemaInspectionError,
)
from backend.db.analytics_engine import create_sqlite_read_only_engine, sqlite_query_only_enabled
from backend.schemas.database import SchemaAllowlist
from backend.services.query_executor import ManualQueryExecutor
from backend.services.schema_service import (
    SchemaService,
    load_schema_allowlist,
    load_schema_snapshot,
    write_model_json,
)


@pytest.fixture
def sample_database(tmp_path: Path) -> Path:
    path = tmp_path / "analytics.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE Artist (
                ArtistId INTEGER PRIMARY KEY,
                Name TEXT NOT NULL
            );
            CREATE TABLE Album (
                AlbumId INTEGER PRIMARY KEY,
                Title TEXT NOT NULL,
                ArtistId INTEGER NOT NULL,
FOREIGN KEY (ArtistId) REFERENCES Artist(ArtistId) ON UPDATE CASCADE ON DELETE RESTRICT
            );
            CREATE VIEW AlbumSummary AS
                SELECT AlbumId, Title FROM Album;
            INSERT INTO Artist VALUES (1, 'Alpha'), (2, 'Beta');
            INSERT INTO Album VALUES (1, 'First', 1), (2, 'Second', 1), (3, 'Third', 2);
            """
        )
    return path


def test_read_only_engine_enables_query_only_and_rejects_writes(sample_database: Path) -> None:
    engine = create_sqlite_read_only_engine(sample_database)
    try:
        assert sqlite_query_only_enabled(engine) is True
        result = ManualQueryExecutor(engine).execute("SELECT COUNT(*) AS total FROM Album")
        assert result.rows == ((3,),)

        with pytest.raises(QueryExecutionError) as caught:
            ManualQueryExecutor(engine).execute("DELETE FROM Album")
        assert caught.value.to_public_dict() == {
            "error_code": "QUERY_EXECUTION_FAILED",
            "message": "The query could not be executed.",
        }
    finally:
        engine.dispose()

    with sqlite3.connect(sample_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM Album").fetchone() == (3,)


def test_engine_rejects_missing_path_and_invalid_timeout(tmp_path: Path) -> None:
    with pytest.raises(DatabaseUnavailableError):
        create_sqlite_read_only_engine(tmp_path / "missing.sqlite")

    existing = tmp_path / "existing.sqlite"
    existing.touch()
    with pytest.raises(ValueError, match="greater than zero"):
        create_sqlite_read_only_engine(existing, timeout_seconds=0)


def test_schema_snapshot_is_stable_complete_and_round_trippable(
    sample_database: Path,
    tmp_path: Path,
) -> None:
    engine = create_sqlite_read_only_engine(sample_database)
    try:
        service = SchemaService(engine)
        first = service.create_snapshot(source_name="fixture", schema_version="test-v1")
        second = service.create_snapshot(source_name="fixture", schema_version="test-v1")
    finally:
        engine.dispose()

    assert first == second
    assert first.schema_hash == second.schema_hash
    assert [table.name for table in first.tables] == ["Album", "Artist"]
    assert first.views == ("AlbumSummary",)
    album = first.tables[0]
    assert album.primary_key == ("AlbumId",)
    assert album.columns[0].primary_key_position == 1
    assert album.foreign_keys[0].constrained_columns == ("ArtistId",)
    assert album.foreign_keys[0].referred_table == "Artist"
    assert album.foreign_keys[0].on_update == "CASCADE"
    assert album.foreign_keys[0].on_delete == "RESTRICT"

    allowlist = SchemaAllowlist.from_snapshot(first)
    assert allowlist.allows_table("Album") is True
    assert allowlist.allows_table("AlbumSummary") is True
    assert allowlist.allows_table("Unknown") is False
    assert allowlist.allows_column("Album", "Title") is True
    assert allowlist.allows_column("Album", "Unknown") is False

    snapshot_path = tmp_path / "metadata" / "snapshot.json"
    allowlist_path = tmp_path / "metadata" / "allowlist.json"
    write_model_json(snapshot_path, first)
    write_model_json(allowlist_path, allowlist)
    assert load_schema_snapshot(snapshot_path) == first
    assert load_schema_allowlist(allowlist_path) == allowlist
    assert not snapshot_path.with_name("snapshot.json.part").exists()


def test_schema_service_sanitizes_inspection_failure(
    monkeypatch: pytest.MonkeyPatch,
    sample_database: Path,
) -> None:
    def fail_inspection(_engine: object) -> None:
        raise SQLAlchemyError("sensitive database detail")

    monkeypatch.setattr("backend.services.schema_service.inspect", fail_inspection)
    engine = create_sqlite_read_only_engine(sample_database)
    try:
        with pytest.raises(SchemaInspectionError) as caught:
            SchemaService(engine).create_snapshot(source_name="fixture", schema_version="test-v1")
    finally:
        engine.dispose()

    assert "sensitive database detail" not in caught.value.public_message


def test_manual_executor_supports_parameters_and_bounded_results(sample_database: Path) -> None:
    engine = create_sqlite_read_only_engine(sample_database)
    try:
        result = ManualQueryExecutor(engine, max_rows=2).execute(
            "SELECT AlbumId, Title FROM Album WHERE ArtistId = :artist_id ORDER BY AlbumId",
            {"artist_id": 1},
        )
        truncated = ManualQueryExecutor(engine, max_rows=2).execute(
            "SELECT AlbumId FROM Album ORDER BY AlbumId"
        )
    finally:
        engine.dispose()

    assert result.columns == ("AlbumId", "Title")
    assert result.rows == ((1, "First"), (2, "Second"))
    assert result.row_count == 2
    assert result.truncated is False
    assert result.response_bytes > 0
    assert result.execution_time_ms >= 0
    assert truncated.rows == ((1,), (2,))
    assert truncated.truncated is True


def test_manual_executor_rejects_invalid_queries_and_budget_overruns(
    sample_database: Path,
) -> None:
    engine = create_sqlite_read_only_engine(sample_database)
    try:
        executor = ManualQueryExecutor(engine, max_query_characters=10)
        with pytest.raises(InvalidRequestError, match="empty"):
            executor.execute("  ")
        with pytest.raises(InvalidRequestError, match="character limit"):
            executor.execute("SELECT 12345")
        with pytest.raises(QueryExecutionError):
            ManualQueryExecutor(engine).execute("SELECT missing FROM nowhere")
        with pytest.raises(ResultTooLargeError) as columns_error:
            ManualQueryExecutor(engine, max_columns=1).execute("SELECT 1 AS a, 2 AS b")
        assert columns_error.value.details == {"max_columns": 1}
        with pytest.raises(ResultTooLargeError) as bytes_error:
            ManualQueryExecutor(engine, max_response_bytes=1).execute("SELECT 'large' AS value")
        assert bytes_error.value.details == {"max_response_bytes": 1}
    finally:
        engine.dispose()

    with pytest.raises(ValueError, match="greater than zero"):
        ManualQueryExecutor(engine, max_rows=0)


def test_manual_executor_rejects_non_row_statements() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with pytest.raises(QueryExecutionError, match="return rows"):
            ManualQueryExecutor(engine).execute("CREATE TABLE Example (id INTEGER)")
    finally:
        engine.dispose()


def test_manual_executor_interrupts_sqlite_after_timeout(sample_database: Path) -> None:
    engine = create_sqlite_read_only_engine(sample_database)
    expensive_sql = """
        WITH RECURSIVE counter(value) AS (
            VALUES (0)
            UNION ALL
            SELECT value + 1 FROM counter WHERE value < 100000000
        )
        SELECT SUM(value) FROM counter
    """
    try:
        with pytest.raises(QueryTimeoutError):
            ManualQueryExecutor(engine, timeout_seconds=0.000001).execute(expensive_sql)
        recovered = ManualQueryExecutor(engine).execute("SELECT COUNT(*) FROM Album")
        assert recovered.rows == ((3,),)
    finally:
        engine.dispose()
