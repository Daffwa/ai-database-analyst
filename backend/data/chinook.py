"""Acquisition and verification for pinned Chinook database artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.core.errors import DatasetVerificationError


@dataclass(frozen=True, slots=True)
class DatasetArtifact:
    """Immutable metadata required to verify one downloaded artifact."""

    release: str
    filename: str
    url: str
    sha256: str
    size_bytes: int


CHINOOK_SQLITE_ARTIFACT = DatasetArtifact(
    release="v1.4.5",
    filename="Chinook_Sqlite.sqlite",
    url=(
        "https://github.com/lerocha/chinook-database/releases/download/v1.4.5/Chinook_Sqlite.sqlite"
    ),
    sha256="bdf635be69850bd3be09c9a2dbeef7ddfb80036bd3ef3381383cd03b61e4a61a",
    size_bytes=1_067_008,
)

CHINOOK_POSTGRESQL_ARTIFACT = DatasetArtifact(
    release="v1.4.5",
    filename="Chinook_PostgreSql.sql",
    url=(
        "https://github.com/lerocha/chinook-database/releases/download/"
        "v1.4.5/Chinook_PostgreSql.sql"
    ),
    sha256="e3fde5c1a5b51a2a91429a702c9ca6e69ba56e6c7f5e112724d70c3d03db695e",
    size_bytes=600_200,
)


def file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a lowercase SHA-256 digest without loading the file into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(path: Path, artifact: DatasetArtifact = CHINOOK_SQLITE_ARTIFACT) -> None:
    """Fail closed unless size and SHA-256 match the pinned metadata."""

    if not path.is_file():
        raise DatasetVerificationError(
            "The pinned dataset artifact is missing.",
            details={"filename": artifact.filename},
        )

    actual_size = path.stat().st_size
    if actual_size != artifact.size_bytes:
        raise DatasetVerificationError(
            "The dataset artifact size does not match the pinned release.",
            details={"filename": artifact.filename},
        )

    actual_sha256 = file_sha256(path)
    if actual_sha256.lower() != artifact.sha256.lower():
        raise DatasetVerificationError(
            "The dataset artifact checksum does not match the pinned release.",
            details={"filename": artifact.filename},
        )


def ensure_artifact(
    destination_directory: Path,
    *,
    artifact: DatasetArtifact = CHINOOK_SQLITE_ARTIFACT,
    force: bool = False,
    timeout_seconds: int = 30,
) -> Path:
    """Download a pinned artifact atomically, or reuse an already valid file."""

    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = destination_directory / artifact.filename

    if destination.exists():
        try:
            verify_artifact(destination, artifact)
        except DatasetVerificationError:
            if not force:
                raise
        else:
            return destination

    temporary = destination.with_name(f"{destination.name}.part")
    temporary.unlink(missing_ok=True)

    try:
        request = Request(artifact.url, headers={"User-Agent": "AI-Database-Analyst-Setup"})
        # The URL is part of immutable artifact metadata and the bytes must pass the
        # pinned size and SHA-256 checks below before they can replace any dataset.
        with (
            urlopen(  # nosec B310
                request, timeout=timeout_seconds
            ) as response,
            temporary.open("wb") as target,
        ):
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
        verify_artifact(temporary, artifact)
        temporary.replace(destination)
    except (OSError, URLError) as exc:
        raise DatasetVerificationError() from exc
    finally:
        temporary.unlink(missing_ok=True)

    return destination
