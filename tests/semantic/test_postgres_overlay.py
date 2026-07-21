"""PostgreSQL semantic overlay remains schema-bound and project-verified."""

from __future__ import annotations

from pathlib import Path

from backend.schemas.database import SchemaAllowlist
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService

ROOT = Path(__file__).resolve().parents[2]


def test_postgres_semantic_overlay_validates_without_changing_base_yaml() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json")
    bundle = load_semantic_bundle(
        ROOT / "semantic",
        dialect_overlay=ROOT / "semantic" / "postgresql.yaml",
    )
    validator = SemanticLayerValidator(
        snapshot,
        SQLSecurityService(
            SchemaAllowlist.from_snapshot(snapshot),
            policy=SQLSecurityPolicy(
                dialect="postgres",
                allowed_schemas=frozenset({"analytics"}),
            ),
        ),
        expected_semantic_version="v1-postgresql",
    )
    report = validator.validate(bundle)
    assert report.valid
    assert report.schema_hash == snapshot.schema_hash
    assert report.semantic_version == "v1-postgresql"
    assert all(
        query.review_status.value == "project_verified" for query in bundle.verified_queries.queries
    )
    assert all("strftime" not in query.sql.casefold() for query in bundle.verified_queries.queries)
