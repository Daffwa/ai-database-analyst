"""Create or verify the immutable Chinook runtime database copy."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.data.initialization import initialize_runtime_database

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace invalid runtime output.")
    args = parser.parse_args()

    result = initialize_runtime_database(
        ROOT / "data" / "raw" / "Chinook_Sqlite.sqlite",
        ROOT / "data" / "processed" / "chinook.sqlite",
        force=args.force,
    )
    print(f"database={result.path}")
    print(f"created={str(result.created).lower()}")
    print(f"sha256={result.sha256}")
    print(f"tables={len(result.table_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
