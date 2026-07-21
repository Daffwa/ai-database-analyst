"""Focused tests for Tahap 8 configuration and PostgreSQL contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.core.config import AppSettings
from backend.core.errors import ConfigurationError
from backend.data.chinook import CHINOOK_POSTGRESQL_ARTIFACT
from backend.data.postgres import _database_commands_removed
from backend.db.postgres import create_postgresql_engine
from backend.runtime.stage8 import postgres_fake_responses
from backend.schemas.api import APIQueryRequest
from backend.services.prompt_builder import PromptBuilder
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot

ROOT = Path(__file__).resolve().parents[2]


def test_stage8_artifact_and_snapshot_are_content_addressed() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json")
    assert CHINOOK_POSTGRESQL_ARTIFACT.release == "v1.4.5"
    assert CHINOOK_POSTGRESQL_ARTIFACT.size_bytes == 600_200
    assert CHINOOK_POSTGRESQL_ARTIFACT.sha256 == (
        "e3fde5c1a5b51a2a91429a702c9ca6e69ba56e6c7f5e112724d70c3d03db695e"
    )
    assert snapshot.dialect == "postgres"
    assert snapshot.schema_hash == (
        "f3569fc49358ddbd50328badf58ac4748cd0ccc60995c741648cb79b2db02e4e"
    )


def test_postgres_seed_removes_only_database_level_commands() -> None:
    source = (
        "DROP DATABASE IF EXISTS chinook;\nCREATE DATABASE chinook;\n"
        "\\c chinook;\nCREATE TABLE album(id int);"
    )
    sanitized = _database_commands_removed(source)
    assert "DATABASE" not in sanitized
    assert "\\c" not in sanitized
    assert sanitized == "CREATE TABLE album(id int);"


def test_application_database_engine_requires_exact_role_and_driver() -> None:
    with pytest.raises(ConfigurationError):
        create_postgresql_engine(
            "sqlite:///tmp.db",
            expected_username="analytics_readonly",
        )
    with pytest.raises(ConfigurationError):
        create_postgresql_engine(
            "postgresql+psycopg://postgres:secret@localhost/chinook",
            expected_username="analytics_readonly",
        )


def test_settings_reject_shared_credentials_and_wildcard_production_cors() -> None:
    with pytest.raises(ValidationError):
        AppSettings(
            analytics_database_url="postgresql+psycopg://same:x@localhost/db",
            metadata_database_url="postgresql+psycopg://same:x@localhost/db",
        )
    with pytest.raises(ValidationError):
        AppSettings(app_env="production", cors_allowed_origins=["*"])


def test_prompt_v2_names_postgres_target_and_fake_sql_is_translated() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json")
    prompt = PromptBuilder(SchemaRetriever(), prompt_version="v2").build(
        request_id="stage8-test",
        question="Bagaimana tren pendapatan setiap bulan?",
        snapshot=snapshot,
    )
    payload = json.loads(prompt.user_prompt)
    assert payload["target_dialect"] == "postgres"
    assert "target_dialect" in prompt.system_prompt
    assert all(
        "strftime" not in response.casefold() for response in postgres_fake_responses().values()
    )
    destructive = json.loads(postgres_fake_responses()["Hapus semua pelanggan."])
    assert destructive["sql"] == "DELETE FROM Customer"
    assert destructive["intent"] == "analysis"


def test_api_query_contract_rejects_whitespace_only_input() -> None:
    with pytest.raises(ValidationError):
        APIQueryRequest(question="   ")


def test_postgres_runner_keeps_admin_password_out_of_process_arguments() -> None:
    source = (ROOT / "scripts" / "run_stage8_integration.py").read_text(encoding="utf-8")
    assert '"--env",\n        "POSTGRES_PASSWORD",' in source
    assert 'f"POSTGRES_PASSWORD=' not in source
    assert "IMAGE_PULL_TIMEOUT_SECONDS = 180" in source
