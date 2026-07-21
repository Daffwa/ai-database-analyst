"""Bootstrap Tahap 8 PostgreSQL roles, databases, Chinook data, and migrations."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from backend.data.chinook import CHINOOK_POSTGRESQL_ARTIFACT, ensure_artifact
from backend.data.postgres import (
    ANALYTICS_READONLY,
    METADATA_USER,
    MIGRATION_USER,
    application_database_urls,
    bootstrap_postgresql,
)
from backend.metadata.migrations import run_metadata_migration
from backend.services.schema_service import load_schema_snapshot

ROOT = Path(__file__).resolve().parents[1]


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> int:
    admin_url = _required_environment("STAGE8_POSTGRES_ADMIN_URL")
    passwords = {
        ANALYTICS_READONLY: _required_environment("STAGE8_ANALYTICS_PASSWORD"),
        METADATA_USER: _required_environment("STAGE8_METADATA_PASSWORD"),
        MIGRATION_USER: _required_environment("STAGE8_MIGRATION_PASSWORD"),
    }
    seed_path = ensure_artifact(
        ROOT / "data" / "raw",
        artifact=CHINOOK_POSTGRESQL_ARTIFACT,
    )
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json")
    result = bootstrap_postgresql(
        admin_url,
        seed_sql_path=seed_path,
        logical_snapshot=snapshot,
        passwords=passwords,
    )
    _, _, migration_url = application_database_urls(
        admin_url,
        analytics_password=passwords[ANALYTICS_READONLY],
        metadata_password=passwords[METADATA_USER],
        migration_password=passwords[MIGRATION_USER],
    )
    run_metadata_migration(ROOT, migration_url)
    print(json.dumps({**asdict(result), "migration": "head"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
