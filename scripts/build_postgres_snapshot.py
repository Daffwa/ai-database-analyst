"""Build the tracked PostgreSQL logical contract from the verified Chinook schema."""

from __future__ import annotations

from pathlib import Path

from backend.schemas.database import SchemaSnapshot
from backend.services.schema_service import load_schema_snapshot, write_model_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "schemas" / "chinook-v1.4.5.json"
DESTINATION = ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json"


def main() -> int:
    source = load_schema_snapshot(SOURCE)
    snapshot = SchemaSnapshot.create(
        source_name="Chinook PostgreSQL analytics compatibility contract",
        dialect="postgres",
        schema_version="v1.4.5-postgresql",
        tables=source.tables,
        views=(),
    )
    write_model_json(DESTINATION, snapshot)
    print(snapshot.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
