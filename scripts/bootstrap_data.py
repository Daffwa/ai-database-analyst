"""Run the idempotent Chinook download, initialization, and snapshot workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.data.chinook import ensure_artifact
from backend.data.initialization import initialize_runtime_database
from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.schemas.database import SchemaAllowlist
from backend.services.schema_service import SchemaService, write_model_json

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace mismatched local outputs.")
    args = parser.parse_args()

    source = ensure_artifact(ROOT / "data" / "raw", force=args.force)
    initialized = initialize_runtime_database(
        source,
        ROOT / "data" / "processed" / "chinook.sqlite",
        force=args.force,
    )
    engine = create_sqlite_read_only_engine(initialized.path)
    try:
        snapshot = SchemaService(engine).create_snapshot(
            source_name="chinook",
            schema_version="v1.4.5",
        )
    finally:
        engine.dispose()

    write_model_json(
        ROOT / "data" / "schemas" / "chinook-v1.4.5.json",
        snapshot,
    )
    write_model_json(
        ROOT / "configs" / "security" / "table_allowlist.json",
        SchemaAllowlist.from_snapshot(snapshot),
    )
    print(f"source_sha256={initialized.sha256}")
    print(f"database_created={str(initialized.created).lower()}")
    print(f"schema_hash={snapshot.schema_hash}")
    print(f"tables={len(snapshot.tables)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
