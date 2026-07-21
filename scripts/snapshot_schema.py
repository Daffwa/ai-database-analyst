"""Generate the versioned Chinook schema snapshot and initial allowlist."""

from __future__ import annotations

from pathlib import Path

from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.schemas.database import SchemaAllowlist
from backend.services.schema_service import SchemaService, write_model_json

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    engine = create_sqlite_read_only_engine(ROOT / "data" / "processed" / "chinook.sqlite")
    try:
        snapshot = SchemaService(engine).create_snapshot(
            source_name="chinook",
            schema_version="v1.4.5",
        )
    finally:
        engine.dispose()

    allowlist = SchemaAllowlist.from_snapshot(snapshot)
    snapshot_path = ROOT / "data" / "schemas" / "chinook-v1.4.5.json"
    allowlist_path = ROOT / "configs" / "security" / "table_allowlist.json"
    write_model_json(snapshot_path, snapshot)
    write_model_json(allowlist_path, allowlist)
    print(f"snapshot={snapshot_path}")
    print(f"allowlist={allowlist_path}")
    print(f"schema_hash={snapshot.schema_hash}")
    print(f"tables={len(snapshot.tables)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
