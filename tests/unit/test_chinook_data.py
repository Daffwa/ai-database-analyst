"""Tests for pinned dataset acquisition and checksum verification."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.core.errors import DatasetVerificationError
from backend.data.chinook import DatasetArtifact, ensure_artifact, file_sha256, verify_artifact


def _artifact_for(path: Path, *, url: str | None = None) -> DatasetArtifact:
    content = path.read_bytes()
    return DatasetArtifact(
        release="test-v1",
        filename="fixture.sqlite",
        url=url or path.as_uri(),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def test_file_sha256_and_verification_accept_exact_artifact(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    source.write_bytes(b"verified fixture")
    artifact = _artifact_for(source)

    assert file_sha256(source, chunk_size=3) == artifact.sha256
    verify_artifact(source, artifact)


def test_verification_rejects_missing_size_and_checksum_mismatches(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    source = tmp_path / "source.sqlite"
    source.write_bytes(b"correct bytes")
    artifact = _artifact_for(source)

    with pytest.raises(DatasetVerificationError, match="missing"):
        verify_artifact(missing, artifact)

    source.write_bytes(b"short")
    with pytest.raises(DatasetVerificationError, match="size"):
        verify_artifact(source, artifact)

    source.write_bytes(b"x" * artifact.size_bytes)
    assert source.stat().st_size == artifact.size_bytes
    with pytest.raises(DatasetVerificationError, match="checksum"):
        verify_artifact(source, artifact)


def test_ensure_artifact_downloads_atomically_and_reuses_valid_file(tmp_path: Path) -> None:
    source_directory = tmp_path / "source"
    source_directory.mkdir()
    source = source_directory / "upstream.sqlite"
    source.write_bytes(b"downloaded fixture")
    artifact = _artifact_for(source)
    destination_directory = tmp_path / "raw"

    first = ensure_artifact(destination_directory, artifact=artifact)
    source.unlink()
    second = ensure_artifact(destination_directory, artifact=artifact)

    assert first == destination_directory / artifact.filename
    assert second == first
    assert first.read_bytes() == b"downloaded fixture"
    assert not first.with_name(f"{first.name}.part").exists()


def test_ensure_artifact_requires_force_to_replace_mismatched_output(tmp_path: Path) -> None:
    source = tmp_path / "upstream.sqlite"
    source.write_bytes(b"canonical fixture")
    artifact = _artifact_for(source)
    destination_directory = tmp_path / "raw"
    destination_directory.mkdir()
    destination = destination_directory / artifact.filename
    destination.write_bytes(b"corrupted fixture")

    with pytest.raises(DatasetVerificationError):
        ensure_artifact(destination_directory, artifact=artifact)

    restored = ensure_artifact(destination_directory, artifact=artifact, force=True)

    assert restored.read_bytes() == source.read_bytes()


def test_ensure_artifact_removes_partial_file_after_failed_verification(tmp_path: Path) -> None:
    source = tmp_path / "upstream.sqlite"
    source.write_bytes(b"upstream")
    artifact = DatasetArtifact(
        release="test-v1",
        filename="fixture.sqlite",
        url=source.as_uri(),
        sha256="0" * 64,
        size_bytes=source.stat().st_size,
    )
    destination_directory = tmp_path / "raw"

    with pytest.raises(DatasetVerificationError):
        ensure_artifact(destination_directory, artifact=artifact)

    assert not (destination_directory / "fixture.sqlite.part").exists()
    assert not (destination_directory / "fixture.sqlite").exists()
