"""Build the corrected development-only Point-5 corpus without holdout content."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from backend.core.config import AppSettings
from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.evaluation.case_loader import (
    DEVELOPMENT_DISTRIBUTION,
    STAGE7_DEVELOPMENT_DATASET_VERSION,
)
from backend.schemas.database import SchemaAllowlist
from backend.services.query_executor import ManualQueryExecutor
from backend.services.schema_service import load_schema_snapshot
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService
from scripts.build_stage7_dataset import CaseSpec, _build_row, all_specs

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "evaluation" / "stage-7-development-v2.jsonl"
AGGREGATION_UNIVERSAL_SQL = (
    "SELECT ArtistId, COUNT(AlbumId) AS album_count FROM Album GROUP BY ArtistId ORDER BY ArtistId"
)


def _development_specs() -> tuple[tuple[CaseSpec, int], ...]:
    selected: list[tuple[CaseSpec, int]] = []
    for ordinal, spec in enumerate(all_specs(), start=1):
        if ordinal % 10 in {0, 8, 9}:
            continue
        if spec.case_id == "AGG-007":
            spec = replace(spec, sql=AGGREGATION_UNIVERSAL_SQL)
        selected.append((spec, ordinal))
    return tuple(selected)


def build_development_dataset(output: Path, *, force: bool = False) -> None:
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing dataset: {output}")
    settings = AppSettings()
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
    engine = create_sqlite_read_only_engine(
        ROOT / "data" / "processed" / "chinook.sqlite",
        timeout_seconds=settings.query_timeout_seconds,
    )
    executor = ManualQueryExecutor(
        engine,
        max_rows=settings.query_max_rows,
        max_columns=settings.query_max_columns,
        max_response_bytes=settings.query_max_response_bytes,
        max_query_characters=settings.sql_max_query_characters,
        timeout_seconds=settings.query_timeout_seconds,
    )
    try:
        rows = []
        for spec, ordinal in _development_specs():
            row = _build_row(spec, ordinal, validator=validator, executor=executor)
            row["dataset_version"] = STAGE7_DEVELOPMENT_DATASET_VERSION
            rows.append(row)
    finally:
        engine.dispose()

    observed = Counter(row["category"] for row in rows)
    expected = Counter(
        {category.value: count for category, count in DEVELOPMENT_DISTRIBUTION.items()}
    )
    if len(rows) != 70 or observed != expected:
        raise ValueError("development specifications do not match the required distribution")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build_development_dataset(args.output, force=args.force)
    print(f"Wrote 70 development cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
