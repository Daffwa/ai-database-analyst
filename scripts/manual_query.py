"""Execute a developer-supplied read-only query against local Chinook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.services.query_executor import ManualQueryExecutor

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql", default="SELECT COUNT(*) AS customer_count FROM Customer")
    parser.add_argument("--max-rows", type=int, default=20)
    args = parser.parse_args()

    engine = create_sqlite_read_only_engine(ROOT / "data" / "processed" / "chinook.sqlite")
    try:
        result = ManualQueryExecutor(engine, max_rows=args.max_rows).execute(args.sql)
    finally:
        engine.dispose()
    print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
