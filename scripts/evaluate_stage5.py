"""Run the versioned Tahap 5 clarification and retrieval evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from backend.core.config import get_settings
from backend.evaluation.semantic_runner import run_semantic_evaluation
from backend.schemas.database import SchemaAllowlist
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_service import SemanticService
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_security import SQLSecurityService

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    settings = get_settings()
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    bundle = load_semantic_bundle(ROOT / "semantic")
    sql_validator = SQLSecurityService(SchemaAllowlist.from_snapshot(snapshot))
    validation = SemanticLayerValidator(
        snapshot,
        sql_validator,
        expected_semantic_version=settings.semantic_version,
    ).validate(bundle)
    service = SemanticService(
        bundle,
        validation,
        max_verified_examples=settings.verified_query_max_examples,
        max_context_characters=settings.prompt_semantic_max_characters,
    )
    summary = run_semantic_evaluation(service, bundle)
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return int(bool(summary.failed_case_ids))


if __name__ == "__main__":
    raise SystemExit(main())
