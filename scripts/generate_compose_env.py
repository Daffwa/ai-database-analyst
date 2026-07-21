"""Generate ignored local Docker Compose credentials without printing them."""

from __future__ import annotations

import argparse
import os
import secrets
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".env.compose"


def compose_environment() -> dict[str, str]:
    """Return URL-safe random values suitable for Compose interpolation."""

    return {
        "POSTGRES_ADMIN_PASSWORD": secrets.token_urlsafe(32),
        "STAGE8_ANALYTICS_PASSWORD": secrets.token_urlsafe(32),
        "STAGE8_METADATA_PASSWORD": secrets.token_urlsafe(32),
        "STAGE8_MIGRATION_PASSWORD": secrets.token_urlsafe(32),
        "EVALUATION_API_TOKEN": secrets.token_urlsafe(32),
        "API_PUBLISHED_PORT": "8000",
        "FRONTEND_PUBLISHED_PORT": "8501",
    }


def write_environment(path: Path, values: dict[str, str], *, overwrite: bool = False) -> None:
    """Write with exclusive creation by default and best-effort owner-only mode."""

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    with suppress(OSError):
        path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Replace the exact output file")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT not in output.parents:
        parser.error("output must stay inside the repository")
    try:
        write_environment(output, compose_environment(), overwrite=args.force)
    except FileExistsError:
        parser.error(f"{output.name} already exists; use --force to replace that exact file")
    print(f"Created ignored Compose environment: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
