"""Download and verify the pinned Chinook SQLite release artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.data.chinook import CHINOOK_SQLITE_ARTIFACT, ensure_artifact, file_sha256

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace a mismatched local file.")
    args = parser.parse_args()

    path = ensure_artifact(
        ROOT / "data" / "raw",
        artifact=CHINOOK_SQLITE_ARTIFACT,
        force=args.force,
    )
    print(f"artifact={path}")
    print(f"sha256={file_sha256(path)}")
    print(f"size_bytes={path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
