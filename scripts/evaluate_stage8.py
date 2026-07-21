"""Evaluate deterministic Tahap 8 implementation readiness and external gate status."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.data.chinook import CHINOOK_POSTGRESQL_ARTIFACT
from backend.metadata.models import Base
from backend.schemas.database import SchemaAllowlist
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "evaluation" / "stage-8-readiness.json"
POSTGRES_REPORT_PATH = ROOT / "reports" / "test-results" / "stage-8-postgres.json"
EXPECTED_METADATA_TABLES = {
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


def main() -> int:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json")
    bundle = load_semantic_bundle(
        ROOT / "semantic", dialect_overlay=ROOT / "semantic" / "postgresql.yaml"
    )
    semantic = SemanticLayerValidator(
        snapshot,
        SQLSecurityService(
            SchemaAllowlist.from_snapshot(snapshot),
            policy=SQLSecurityPolicy(dialect="postgres", allowed_schemas=frozenset({"analytics"})),
        ),
        expected_semantic_version="v1-postgresql",
    ).validate(bundle)
    columns = {
        column.name.casefold() for table in Base.metadata.sorted_tables for column in table.columns
    }
    frontend_source = (ROOT / "frontend" / "streamlit_api_app.py").read_text(encoding="utf-8")
    checks = {
        "postgres_artifact_pinned": (
            CHINOOK_POSTGRESQL_ARTIFACT.sha256
            == "e3fde5c1a5b51a2a91429a702c9ca6e69ba56e6c7f5e112724d70c3d03db695e"
        ),
        "postgres_snapshot_content_addressed": (
            snapshot.schema_hash
            == "f3569fc49358ddbd50328badf58ac4748cd0ccc60995c741648cb79b2db02e4e"
        ),
        "postgres_semantic_overlay_valid": semantic.valid,
        "metadata_models_complete": (
            {table.name for table in Base.metadata.sorted_tables} == EXPECTED_METADATA_TABLES
        ),
        "metadata_omits_raw_sensitive_payloads": not {
            "raw_question",
            "raw_sql",
            "result_rows",
        }
        & columns,
        "alembic_revision_present": (
            ROOT / "alembic" / "versions" / "20260720_0001_stage8_metadata.py"
        ).is_file(),
        "fastapi_factory_present": (ROOT / "backend" / "api" / "app.py").is_file(),
        "frontend_uses_api_client": (
            "AnalystAPIClient" in frontend_source
            and "create_stage6_runtime" not in frontend_source
            and "analytics_engine" not in frontend_source
        ),
        "postgres_integration_tests_present": (
            ROOT / "tests" / "postgres" / "test_stage8_postgres.py"
        ).is_file(),
    }
    postgres_report = (
        json.loads(POSTGRES_REPORT_PATH.read_text(encoding="utf-8"))
        if POSTGRES_REPORT_PATH.is_file()
        else {
            "postgresql_integration_verified": False,
            "blocker": "PostgreSQL integration report is not available.",
        }
    )
    implementation_gate_passed = all(checks.values())
    postgres_verified = bool(postgres_report["postgresql_integration_verified"])
    report = {
        "report_version": "stage-8-readiness-v1",
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "implementation_gate_passed": implementation_gate_passed,
        "postgresql_integration_verified": postgres_verified,
        "stage_gate_passed": implementation_gate_passed and postgres_verified,
        "blocker": postgres_report.get("blocker"),
        "provenance": {
            "chinook_version": CHINOOK_POSTGRESQL_ARTIFACT.release,
            "chinook_postgresql_sha256": CHINOOK_POSTGRESQL_ARTIFACT.sha256,
            "schema_hash": snapshot.schema_hash,
            "semantic_version": bundle.semantic_version,
            "semantic_content_hash": bundle.content_hash,
            "prompt_version": "v2",
            "api_version": "v1",
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if implementation_gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
