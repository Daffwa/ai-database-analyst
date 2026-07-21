"""Validate the complete semantic layer against the active Chinook schema."""

from __future__ import annotations

import json
from pathlib import Path

from backend.core.config import get_settings
from backend.schemas.database import SchemaAllowlist
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_security import SQLSecurityService

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    settings = get_settings()
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    bundle = load_semantic_bundle(ROOT / "semantic")
    report = SemanticLayerValidator(
        snapshot,
        SQLSecurityService(SchemaAllowlist.from_snapshot(snapshot)),
        expected_semantic_version=settings.semantic_version,
    ).validate(bundle)
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return int(not report.valid)


if __name__ == "__main__":
    raise SystemExit(main())
