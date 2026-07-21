"""Integration checks against the bootstrapped Chinook v1.4.5 database."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from backend.core.errors import QueryExecutionError
from backend.data.chinook import CHINOOK_SQLITE_ARTIFACT, file_sha256
from backend.data.initialization import CHINOOK_EXPECTED_TABLE_COUNTS, verify_database_contents
from backend.db.analytics_engine import create_sqlite_read_only_engine, sqlite_query_only_enabled
from backend.schemas.database import SchemaAllowlist
from backend.services.query_executor import ManualQueryExecutor
from backend.services.schema_service import (
    SchemaService,
    load_schema_allowlist,
    load_schema_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / "data" / "processed" / "chinook.sqlite"
SNAPSHOT_PATH = ROOT / "data" / "schemas" / "chinook-v1.4.5.json"
ALLOWLIST_PATH = ROOT / "configs" / "security" / "table_allowlist.json"


@pytest.fixture(scope="module")
def chinook_engine() -> Iterator[Engine]:
    if not DATABASE_PATH.is_file():
        pytest.skip("Run `python scripts/bootstrap_data.py` before integration tests.")
    engine = create_sqlite_read_only_engine(DATABASE_PATH)
    yield engine
    engine.dispose()


@pytest.mark.integration
def test_pinned_database_checksum_integrity_and_counts() -> None:
    if not DATABASE_PATH.is_file():
        pytest.skip("Run `python scripts/bootstrap_data.py` before integration tests.")

    assert file_sha256(DATABASE_PATH) == CHINOOK_SQLITE_ARTIFACT.sha256
    assert verify_database_contents(DATABASE_PATH) == CHINOOK_EXPECTED_TABLE_COUNTS


@pytest.mark.integration
def test_tracked_snapshot_and_allowlist_match_runtime(chinook_engine: Engine) -> None:
    runtime = SchemaService(chinook_engine).create_snapshot(
        source_name="chinook",
        schema_version="v1.4.5",
    )
    tracked = load_schema_snapshot(SNAPSHOT_PATH)
    allowlist = load_schema_allowlist(ALLOWLIST_PATH)

    assert runtime == tracked
    assert len(runtime.tables) == 11
    assert SchemaAllowlist.from_snapshot(runtime) == allowlist
    assert allowlist.allows_column("InvoiceLine", "UnitPrice") is True


@pytest.mark.integration
def test_join_aggregation_limits_and_write_rejection(chinook_engine: Engine) -> None:
    executor = ManualQueryExecutor(chinook_engine, max_rows=3)

    assert sqlite_query_only_enabled(chinook_engine) is True
    result = executor.execute(
        """
        SELECT c.Country, ROUND(SUM(i.Total), 2) AS Revenue
        FROM Customer AS c
        JOIN Invoice AS i ON i.CustomerId = c.CustomerId
        GROUP BY c.Country
        ORDER BY Revenue DESC, c.Country
        """
    )
    assert result.columns == ("Country", "Revenue")
    assert result.rows[0] == ("USA", 523.06)
    assert result.row_count == 3
    assert result.truncated is True

    before = executor.execute("SELECT FirstName FROM Customer WHERE CustomerId = 1").rows
    with pytest.raises(QueryExecutionError):
        executor.execute("UPDATE Customer SET FirstName = 'Changed' WHERE CustomerId = 1")
    after = executor.execute("SELECT FirstName FROM Customer WHERE CustomerId = 1").rows
    assert before == after
