"""Shared fixtures for semantic-layer validation and resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.schemas.database import SchemaAllowlist, SchemaSnapshot
from backend.schemas.semantic import SemanticLayerBundle, SemanticValidationReport
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_service import SemanticService
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_security import SQLSecurityService

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def semantic_snapshot() -> SchemaSnapshot:
    return load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")


@pytest.fixture(scope="session")
def semantic_bundle() -> SemanticLayerBundle:
    return load_semantic_bundle(ROOT / "semantic")


@pytest.fixture(scope="session")
def semantic_validator(
    semantic_snapshot: SchemaSnapshot,
) -> SemanticLayerValidator:
    sql_validator = SQLSecurityService(SchemaAllowlist.from_snapshot(semantic_snapshot))
    return SemanticLayerValidator(
        semantic_snapshot,
        sql_validator,
        expected_semantic_version="v1",
    )


@pytest.fixture(scope="session")
def semantic_report(
    semantic_validator: SemanticLayerValidator,
    semantic_bundle: SemanticLayerBundle,
) -> SemanticValidationReport:
    return semantic_validator.validate(semantic_bundle)


@pytest.fixture(scope="session")
def semantic_service(
    semantic_bundle: SemanticLayerBundle,
    semantic_report: SemanticValidationReport,
) -> SemanticService:
    return SemanticService(semantic_bundle, semantic_report)
