"""Run metadata Alembic migrations using a dedicated migration credential."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from backend.metadata.migrations import run_metadata_migration

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", nargs="?", default="head")
    args = parser.parse_args()
    database_url = os.getenv("METADATA_MIGRATION_DATABASE_URL")
    if not database_url:
        parser.error("METADATA_MIGRATION_DATABASE_URL is required")
    run_metadata_migration(ROOT, database_url, args.revision)
    print(f"Metadata migration completed: {args.revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
