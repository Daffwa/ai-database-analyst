"""Uploaded SQLite workspace ingestion, isolation, and query tests."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from backend.core.config import AppSettings
from backend.core.errors import InvalidRequestError, SecurityPolicyError, WorkspaceNotFoundError
from backend.schemas.llm import LanguageCode, LLMIntent, QueryStatus, StructuredSQLProposal
from backend.schemas.workspace import WorkspaceSourceType
from backend.services.database_workspace import UploadedDatabaseWorkspaceService

QUESTION = "Berapa jumlah pengguna?"


def _proposal(sql: str) -> str:
    return StructuredSQLProposal(
        intent=LLMIntent.ANALYSIS,
        language=LanguageCode.INDONESIAN,
        needs_clarification=False,
        assumptions=(),
        sql=sql,
        tables=("users",),
        columns=("users.id",),
        confidence=1,
        reasoning_summary="Menghitung pengguna dari database upload.",
    ).model_dump_json()


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        app_env="test",
        llm_provider="fake",
        llm_model="fake-deterministic",
        database_workspace_storage_root=tmp_path / "workspaces",
        database_workspace_upload_max_bytes=100_000,
        database_workspace_max_database_bytes=200_000,
    )


def test_sql_dump_workspace_inspects_queries_and_deletes_in_isolation(tmp_path: Path) -> None:
    service = UploadedDatabaseWorkspaceService(
        _settings(tmp_path),
        fake_responses={QUESTION: _proposal("SELECT COUNT(users.id) AS user_count FROM users")},
    )
    upload = b"""-- ordinary SQLite dump
BEGIN TRANSACTION;
CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
INSERT INTO users(id, name) VALUES (1, 'A'), (2, 'B');
CREATE INDEX idx_users_name ON users(name);
COMMIT;
"""

    workspace = service.create("../../demo.sql", upload)
    response = asyncio.run(service.query(workspace.workspace_id, QUESTION))

    assert workspace.source_name == "demo.sql"
    assert workspace.table_count == 1
    assert workspace.column_count == 2
    assert workspace.ai_query_ready is False
    assert workspace.schema_snapshot.tables[0].review_status == "uploaded_unreviewed"
    assert response.status is QueryStatus.SUCCESS
    assert response.result is not None and response.result.rows == ((2,),)
    assert response.validation is not None and response.validation.safe is True
    assert "uploaded SQLite workspace" in response.warnings[0]

    database_path = tmp_path / "workspaces" / workspace.workspace_id / "database.sqlite"
    assert database_path.is_file()
    assert service.delete(workspace.workspace_id).deleted is True
    assert not database_path.parent.exists()
    with pytest.raises(WorkspaceNotFoundError):
        service.schema(workspace.workspace_id)
    service.close()


@pytest.mark.parametrize(
    "statement",
    [
        "ATTACH DATABASE 'outside.db' AS stolen;",
        "CREATE VIEW exposed AS SELECT * FROM users;",
        "CREATE VIRTUAL TABLE docs USING fts5(body);",
        "CREATE INDEX dangerous ON users(load_extension('payload'));",
        "INSERT INTO users SELECT * FROM other_users;",
        "DELETE FROM users;",
    ],
)
def test_sql_dump_rejects_non_allowlisted_statements(
    tmp_path: Path,
    statement: str,
) -> None:
    service = UploadedDatabaseWorkspaceService(_settings(tmp_path))
    upload = (f"CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT);\n{statement}\n").encode()

    with pytest.raises(SecurityPolicyError):
        service.create("unsafe.sql", upload)

    assert not tuple((tmp_path / "workspaces").glob("dbw_*"))
    service.close()


def test_sqlite_database_file_is_copied_and_active_objects_are_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO users(name) VALUES ('A')")
        connection.commit()
    service = UploadedDatabaseWorkspaceService(_settings(tmp_path))
    workspace = service.create("source.sqlite", source.read_bytes())
    source.unlink()

    assert service.schema(workspace.workspace_id).tables[0].name == "users"
    assert (tmp_path / "workspaces" / workspace.workspace_id / "database.sqlite").is_file()
    service.close()

    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
        connection.execute("CREATE VIEW user_view AS SELECT id FROM users")
        connection.commit()
    rejecting_service = UploadedDatabaseWorkspaceService(_settings(tmp_path))
    with pytest.raises(InvalidRequestError, match="views, triggers"):
        rejecting_service.create("source.db", source.read_bytes())
    rejecting_service.close()


def test_sqlite_backup_with_bak_suffix_is_accepted_but_sql_server_backup_is_not(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO users(name) VALUES ('A')")
        connection.commit()

    service = UploadedDatabaseWorkspaceService(_settings(tmp_path))
    workspace = service.create("nightly.bak", source.read_bytes())

    assert workspace.source_type is WorkspaceSourceType.SQLITE_BACKUP
    assert service.schema(workspace.workspace_id).tables[0].name == "users"
    with pytest.raises(InvalidRequestError, match=r"SQL Server \.bak"):
        service.create("sql-server.bak", b"not a SQLite backup")
    service.close()


def test_csv_workspace_preserves_text_and_normalizes_identifiers(tmp_path: Path) -> None:
    service = UploadedDatabaseWorkspaceService(
        _settings(tmp_path),
        fake_responses={QUESTION: _proposal("SELECT COUNT(users.id) AS user_count FROM users")},
    )
    upload = b"id,Full Name,id\n001,Alice,external-1\n002,Bob\n"

    workspace = service.create("users.csv", upload)
    response = asyncio.run(service.query(workspace.workspace_id, QUESTION))
    columns = workspace.schema_snapshot.tables[0].columns

    assert workspace.source_type is WorkspaceSourceType.CSV_TABLE
    assert [column.name for column in columns] == ["id", "Full_Name", "id_2"]
    assert all(column.data_type == "TEXT" for column in columns)
    assert response.result is not None and response.result.rows == ((2,),)
    database_path = tmp_path / "workspaces" / workspace.workspace_id / "database.sqlite"
    database_url = f"file:{database_path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(database_url, uri=True)) as connection:
        rows = connection.execute('SELECT id, "Full_Name", id_2 FROM users ORDER BY id').fetchall()
    assert rows == [("001", "Alice", "external-1"), ("002", "Bob", None)]
    service.close()


def test_json_workspace_supports_multiple_tables_and_nested_values(tmp_path: Path) -> None:
    service = UploadedDatabaseWorkspaceService(
        _settings(tmp_path),
        fake_responses={QUESTION: _proposal("SELECT COUNT(users.id) AS user_count FROM users")},
    )
    upload = json.dumps(
        {
            "users": [
                {"id": 1, "profile": {"city": "Jakarta"}, "active": True},
                {"id": 2, "profile": None, "active": False},
            ],
            "orders": [{"order_id": 10, "user_id": 1, "total": 12.5}],
        }
    ).encode()

    workspace = service.create("export.json", upload)
    response = asyncio.run(service.query(workspace.workspace_id, QUESTION))

    assert workspace.source_type is WorkspaceSourceType.JSON_DOCUMENT
    assert {table.name for table in workspace.schema_snapshot.tables} == {"orders", "users"}
    assert response.result is not None and response.result.rows == ((2,),)
    database_path = tmp_path / "workspaces" / workspace.workspace_id / "database.sqlite"
    database_url = f"file:{database_path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(database_url, uri=True)) as connection:
        stored = connection.execute(
            "SELECT id, profile, active, typeof(id), typeof(active) FROM users ORDER BY id"
        ).fetchall()
    assert stored == [
        (1, '{"city":"Jakarta"}', 1, "integer", "integer"),
        (2, None, 0, "integer", "integer"),
    ]
    service.close()


@pytest.mark.parametrize(
    ("filename", "payload", "message"),
    [
        ("users.csv", b"\n", "header row"),
        ("users.csv", b"id,name\n1,A,extra\n", "more fields"),
        ("users.json", b'{"id": 1, "id": 2}', "valid bounded JSON"),
        ("users.json", b"[NaN]", "valid bounded JSON"),
    ],
)
def test_malformed_csv_and_json_fail_closed(
    tmp_path: Path,
    filename: str,
    payload: bytes,
    message: str,
) -> None:
    service = UploadedDatabaseWorkspaceService(_settings(tmp_path))
    with pytest.raises(InvalidRequestError, match=message):
        service.create(filename, payload)
    assert not tuple((tmp_path / "workspaces").glob("dbw_*"))
    service.close()


def test_structured_data_record_budget_fails_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"database_workspace_max_records": 1})
    service = UploadedDatabaseWorkspaceService(settings)

    with pytest.raises(InvalidRequestError, match="too many records"):
        service.create("users.csv", b"id\n1\n2\n")
    with pytest.raises(InvalidRequestError, match="too many records"):
        service.create("users.json", b'[{"id": 1}, {"id": 2}]')
    assert not tuple((tmp_path / "workspaces").glob("dbw_*"))
    service.close()


def test_generated_write_is_blocked_before_uploaded_database_execution(tmp_path: Path) -> None:
    service = UploadedDatabaseWorkspaceService(
        _settings(tmp_path),
        fake_responses={QUESTION: _proposal("DELETE FROM users")},
    )
    workspace = service.create(
        "demo.sql",
        b"CREATE TABLE users(id INTEGER PRIMARY KEY); INSERT INTO users VALUES (1);",
    )

    response = asyncio.run(service.query(workspace.workspace_id, QUESTION))

    assert response.status is QueryStatus.BLOCKED
    assert response.executed_sql is None
    assert response.validation is not None and response.validation.safe is False
    service.close()


@pytest.mark.parametrize(
    ("filename", "payload", "message"),
    [
        ("demo.txt", b"not supported", "Only .db"),
        ("demo.db", b"not sqlite", "not a valid SQLite"),
        ("demo.sql", b"\xff\xfe", "UTF-8"),
        ("demo.sql", b"CREATE TABLE users(name TEXT);\x00", "null bytes"),
        ("demo.sql", b"CREATE TABLE users(name TEXT", "invalid SQLite syntax"),
        ("bad\nname.sql", b"CREATE TABLE users(id INTEGER);", "filename is invalid"),
    ],
)
def test_malformed_uploads_fail_closed_and_leave_no_workspace(
    tmp_path: Path,
    filename: str,
    payload: bytes,
    message: str,
) -> None:
    service = UploadedDatabaseWorkspaceService(_settings(tmp_path))
    with pytest.raises(InvalidRequestError, match=message):
        service.create(filename, payload)
    assert not tuple((tmp_path / "workspaces").glob("dbw_*"))
    service.close()


def test_workspace_limits_active_count_tables_columns_and_identifiers(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={
            "database_workspace_max_active": 1,
            "database_workspace_max_tables": 1,
            "database_workspace_max_columns": 2,
        }
    )
    service = UploadedDatabaseWorkspaceService(settings)
    first = service.create("one.sql", b"CREATE TABLE users(id INTEGER, name TEXT);")
    with pytest.raises(InvalidRequestError, match="active uploaded-workspace limit"):
        service.create("two.sql", b"CREATE TABLE second(id INTEGER);")
    service.delete(first.workspace_id)

    with pytest.raises(InvalidRequestError, match="too many tables"):
        service.create(
            "tables.sql",
            b"CREATE TABLE first(id INTEGER); CREATE TABLE second(id INTEGER);",
        )
    with pytest.raises(InvalidRequestError, match="too many columns"):
        service.create(
            "columns.sql",
            b"CREATE TABLE users(id INTEGER, name TEXT, email TEXT);",
        )
    with pytest.raises(InvalidRequestError, match="too many columns"):
        service.create("columns.csv", b"id,name,email\n1,A,a@example.test\n")
    with pytest.raises(InvalidRequestError, match="too many tables"):
        service.create("tables.json", b'{"users": [], "orders": []}')
    with pytest.raises(InvalidRequestError, match="unsupported table or column identifier"):
        service.create("identifier.sql", b'CREATE TABLE "bad.name"(id INTEGER);')
    service.close()
