"""Run the versioned Tahap 4 blocking and false-blocking evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from backend.core.config import get_settings
from backend.evaluation.security_runner import run_security_evaluation
from backend.schemas.database import SchemaAllowlist
from backend.services.schema_service import load_schema_snapshot
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    settings = get_settings()
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    validator = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(
            dialect=settings.sql_dialect,
            max_rows=settings.query_max_rows,
            max_query_characters=settings.sql_max_query_characters,
            blocked_functions=frozenset(settings.sql_blocked_functions),
        ),
    )
    summary = run_security_evaluation(validator)
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return int(summary.blocking_rate != 1.0 or summary.false_block_count != 0)


if __name__ == "__main__":
    raise SystemExit(main())
