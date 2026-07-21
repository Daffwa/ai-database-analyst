"""Tests for deterministic and idempotent SQLite initialization."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from backend.core.errors import DatasetVerificationError
from backend.data.chinook import DatasetArtifact
from backend.data.initialization import initialize_runtime_database, verify_database_contents


def _create_source(path: Path) -> tuple[DatasetArtifact, dict[str, int]]:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE Parent (
                ParentId INTEGER PRIMARY KEY,
                Name TEXT NOT NULL
            );
            CREATE TABLE Child (
                ChildId INTEGER PRIMARY KEY,
                ParentId INTEGER NOT NULL REFERENCES Parent(ParentId),
                Amount NUMERIC NOT NULL
            );
            INSERT INTO Parent VALUES (1, 'A'), (2, 'B');
            INSERT INTO Child VALUES (1, 1, 10.5), (2, 1, 4.5), (3, 2, 8.0);
            """
        )
    content = path.read_bytes()
    artifact = DatasetArtifact(
        release="test-v1",
        filename=path.name,
        url=path.as_uri(),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )
    return artifact, {"Child": 3, "Parent": 2}


def test_initialize_creates_byte_identical_database_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    artifact, counts = _create_source(source)
    destination = tmp_path / "processed" / "runtime.sqlite"

    first = initialize_runtime_database(
        source,
        destination,
        artifact=artifact,
        expected_counts=counts,
    )
    second = initialize_runtime_database(
        source,
        destination,
        artifact=artifact,
        expected_counts=counts,
    )

    assert first.created is True
    assert second.created is False
    assert first.sha256 == artifact.sha256 == second.sha256
    assert first.table_counts == counts == second.table_counts
    assert destination.read_bytes() == source.read_bytes()


def test_initialize_rejects_corrupt_output_unless_force_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    artifact, counts = _create_source(source)
    destination = tmp_path / "processed" / "runtime.sqlite"
    destination.parent.mkdir()
    destination.write_bytes(b"corrupt")

    with pytest.raises(DatasetVerificationError):
        initialize_runtime_database(
            source,
            destination,
            artifact=artifact,
            expected_counts=counts,
        )

    repaired = initialize_runtime_database(
        source,
        destination,
        artifact=artifact,
        expected_counts=counts,
        force=True,
    )

    assert repaired.created is True
    assert destination.read_bytes() == source.read_bytes()


def test_database_content_verification_rejects_schema_and_count_drift(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    _create_source(source)

    with pytest.raises(DatasetVerificationError, match="schema"):
        verify_database_contents(source, expected_counts={"Other": 1})

    with pytest.raises(DatasetVerificationError, match="row counts"):
        verify_database_contents(source, expected_counts={"Child": 99, "Parent": 2})


def test_database_content_verification_rejects_missing_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(DatasetVerificationError, match="missing"):
        verify_database_contents(tmp_path / "missing.sqlite", expected_counts={})

    invalid = tmp_path / "invalid.sqlite"
    invalid.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(DatasetVerificationError, match="could not be verified"):
        verify_database_contents(invalid, expected_counts={})
