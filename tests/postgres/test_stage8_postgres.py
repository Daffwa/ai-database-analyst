"""Actual PostgreSQL privilege, migration, API, and audit integration gate."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from backend.api.app import create_app
from backend.core.config import AppSettings
from backend.data.initialization import CHINOOK_EXPECTED_TABLE_COUNTS
from backend.db.postgres import assert_application_identity, create_postgresql_engine
from backend.metadata.migrations import run_metadata_migration
from backend.runtime.stage8 import create_stage8_runtime

ROOT = Path(__file__).resolve().parents[2]


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is required for PostgreSQL integration tests")
    return value


@pytest.mark.postgres
def test_migration_upgrades_from_empty_and_creates_all_metadata_models() -> None:
    migration_url = _required("METADATA_MIGRATION_DATABASE_URL")
    run_metadata_migration(ROOT, migration_url, "base")
    run_metadata_migration(ROOT, migration_url, "head")
    engine = create_postgresql_engine(
        _required("METADATA_DATABASE_URL"),
        expected_username="app_metadata_user",
    )
    try:
        tables = set(inspect(engine).get_table_names(schema="app_metadata"))
    finally:
        engine.dispose()
    assert tables == {
        "data_sources",
        "schema_snapshots",
        "verified_queries",
        "query_requests",
        "query_attempts",
        "query_feedback",
        "evaluation_cases",
        "evaluation_runs",
        "evaluation_results",
        "usage_events",
    }


@pytest.mark.postgres
def test_analytics_role_is_actual_readonly_and_allowlisted() -> None:
    engine = create_postgresql_engine(
        _required("ANALYTICS_DATABASE_URL"),
        expected_username="analytics_readonly",
    )
    try:
        identity = assert_application_identity(engine, expected_username="analytics_readonly")
        assert not any(
            (
                identity.superuser,
                identity.create_database,
                identity.create_role,
                identity.bypass_rls,
            )
        )
        with engine.connect() as connection:
            count = connection.exec_driver_sql("SELECT COUNT(*) FROM Customer").scalar_one()
            assert count == CHINOOK_EXPECTED_TABLE_COUNTS["Customer"]
            assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
            assert connection.exec_driver_sql("SHOW statement_timeout").scalar_one() == "5s"

        blocked_writes = (
            "INSERT INTO Customer (CustomerId, FirstName, LastName, Email) "
            "VALUES (9999, 'A', 'B', 'x@example.test')",
            "UPDATE Customer SET FirstName = 'X' WHERE CustomerId = 1",
            "DELETE FROM Customer WHERE CustomerId = 1",
            "CREATE TABLE analytics.not_allowed (id integer)",
            "DROP VIEW analytics.customer",
        )
        for statement in blocked_writes:
            with engine.connect() as connection, pytest.raises(DBAPIError):
                connection.exec_driver_sql(statement)
        with engine.connect() as connection, pytest.raises(DBAPIError):
            connection.exec_driver_sql("SELECT COUNT(*) FROM chinook_data.customer")
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_metadata_role_is_distinct_and_cannot_create_or_reach_analytics() -> None:
    metadata_engine = create_postgresql_engine(
        _required("METADATA_DATABASE_URL"),
        expected_username="app_metadata_user",
    )
    try:
        metadata_identity = assert_application_identity(
            metadata_engine, expected_username="app_metadata_user"
        )
        assert metadata_identity.current_database == "analyst_metadata"
        with metadata_engine.connect() as connection, pytest.raises(DBAPIError):
            connection.exec_driver_sql("CREATE TABLE app_metadata.not_allowed (id integer)")
    finally:
        metadata_engine.dispose()

    admin_url = _required("STAGE8_POSTGRES_ADMIN_URL")
    analytics_url = _required("ANALYTICS_DATABASE_URL")
    cross_database_url = (
        make_url(analytics_url)
        .set(drivername="postgresql", database="analyst_metadata")
        .render_as_string(hide_password=False)
    )
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(cross_database_url)
    assert "analytics_readonly" not in _required("METADATA_DATABASE_URL")
    assert "app_metadata_user" not in analytics_url
    assert "postgres" in admin_url


@pytest.mark.postgres
def test_fastapi_runtime_persists_safe_metadata_and_all_primary_states() -> None:
    settings = AppSettings(
        app_env="test",
        analytics_database_url=_required("ANALYTICS_DATABASE_URL"),
        metadata_database_url=_required("METADATA_DATABASE_URL"),
        sql_dialect="postgres",
        prompt_version="v2",
        semantic_version="v1-postgresql",
        evaluation_api_token="integration-evaluation-token",
    )
    runtime = create_stage8_runtime(ROOT, settings)
    try:
        with TestClient(create_app(settings, runtime=runtime)) as client:
            health = client.get("/api/v1/health")
            success = client.post("/api/v1/query", json={"question": "Berapa jumlah pelanggan?"})
            clarification = client.post(
                "/api/v1/query", json={"question": "Siapa pelanggan terbaik?"}
            )
            blocked = client.post("/api/v1/query", json={"question": "Hapus semua pelanggan."})
            history = client.get("/api/v1/history")
            feedback = client.post(
                "/api/v1/feedback",
                json={
                    "request_id": success.json()["request_id"],
                    "rating": "correct",
                },
            )
            schema = client.get("/api/v1/schema")
        assert health.status_code == 200
        assert success.status_code == 200
        assert success.json()["status"] == "success"
        assert success.json()["result"]["rows"] == [[59]]
        assert clarification.status_code == 200
        assert clarification.json()["status"] == "clarification_required"
        assert blocked.status_code == 200
        assert blocked.json()["status"] == "blocked"
        assert blocked.json()["executed_sql"] is None
        assert blocked.json()["validation"]["safe"] is False
        assert history.status_code == 200 and len(history.json()["items"]) >= 3
        assert feedback.status_code == 200 and feedback.json()["rating"] == "correct"
        assert schema.status_code == 200 and len(schema.json()["tables"]) == 11

        correlation_id = str(UUID(int=8))
        with TestClient(create_app(settings, runtime=runtime)) as client:
            correlated = client.post(
                "/api/v1/query",
                json={"question": "Berapa jumlah pelanggan?"},
                headers={"X-Request-ID": correlation_id},
            )
        assert correlated.status_code == 200
        assert correlated.headers["X-Request-ID"] == correlation_id
        assert correlated.json()["request_id"] == correlation_id

        metadata_columns = {
            column["name"]
            for column in inspect(runtime.metadata_engine).get_columns(
                "query_requests", schema="app_metadata"
            )
        }
        assert not {"raw_question", "raw_sql", "result_rows"} & metadata_columns
        assert "sql_fingerprint" in metadata_columns
    finally:
        runtime.close()
