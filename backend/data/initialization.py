"""Idempotent initialization and sanity checks for the Chinook runtime database."""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from backend.core.errors import DatasetVerificationError
from backend.data.chinook import (
    CHINOOK_SQLITE_ARTIFACT,
    DatasetArtifact,
    file_sha256,
    verify_artifact,
)

CHINOOK_EXPECTED_TABLE_COUNTS: dict[str, int] = {
    "Album": 347,
    "Artist": 275,
    "Customer": 59,
    "Employee": 8,
    "Genre": 25,
    "Invoice": 412,
    "InvoiceLine": 2_240,
    "MediaType": 5,
    "Playlist": 18,
    "PlaylistTrack": 8_715,
    "Track": 3_503,
}


@dataclass(frozen=True, slots=True)
class DatabaseInitializationResult:
    """Evidence returned by a successful database initialization."""

    path: Path
    created: bool
    sha256: str
    table_counts: dict[str, int]


def _read_only_uri(path: Path) -> str:
    encoded_path = quote(path.resolve().as_posix(), safe="/:")
    return f"file:{encoded_path}?mode=ro"


def _quoted_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def verify_database_contents(
    path: Path,
    *,
    expected_counts: Mapping[str, int] = CHINOOK_EXPECTED_TABLE_COUNTS,
) -> dict[str, int]:
    """Verify SQLite integrity, expected tables, and deterministic row counts."""

    if not path.is_file():
        raise DatasetVerificationError("The initialized database file is missing.")

    try:
        with closing(sqlite3.connect(_read_only_uri(path), uri=True)) as connection:
            connection.execute("PRAGMA query_only = ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise DatasetVerificationError("SQLite integrity verification failed.")

            rows = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            actual_tables = {str(row[0]) for row in rows}
            if actual_tables != set(expected_counts):
                raise DatasetVerificationError(
                    "The initialized database schema does not match the expected dataset."
                )

            actual_counts = {
                table: int(
                    connection.execute(
                        # `table` comes only from the expected-count allowlist and
                        # is escaped as an SQLite identifier, never as SQL data.
                        f"SELECT COUNT(*) FROM {_quoted_identifier(table)}"  # nosec B608
                    ).fetchone()[0]
                )
                for table in sorted(expected_counts)
            }
    except sqlite3.Error as exc:
        raise DatasetVerificationError("The SQLite database could not be verified.") from exc

    if actual_counts != dict(sorted(expected_counts.items())):
        raise DatasetVerificationError(
            "The initialized database row counts do not match the pinned dataset."
        )
    return actual_counts


def initialize_runtime_database(
    source: Path,
    destination: Path,
    *,
    artifact: DatasetArtifact = CHINOOK_SQLITE_ARTIFACT,
    expected_counts: Mapping[str, int] = CHINOOK_EXPECTED_TABLE_COUNTS,
    force: bool = False,
) -> DatabaseInitializationResult:
    """Create a byte-identical runtime copy and safely reuse valid output."""

    verify_artifact(source, artifact)
    source_counts = verify_database_contents(source, expected_counts=expected_counts)

    if destination.exists():
        try:
            verify_artifact(destination, artifact)
            destination_counts = verify_database_contents(
                destination, expected_counts=expected_counts
            )
        except DatasetVerificationError:
            if not force:
                raise
        else:
            return DatabaseInitializationResult(
                path=destination,
                created=False,
                sha256=file_sha256(destination),
                table_counts=destination_counts,
            )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.part")
    temporary.unlink(missing_ok=True)

    try:
        shutil.copyfile(source, temporary)
        verify_artifact(temporary, artifact)
        verify_database_contents(temporary, expected_counts=expected_counts)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    return DatabaseInitializationResult(
        path=destination,
        created=True,
        sha256=file_sha256(destination),
        table_counts=source_counts,
    )
