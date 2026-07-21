"""Programmatic Alembic entrypoint that avoids placing credentials in config files."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine

from alembic import command


def run_metadata_migration(root: Path, database_url: str, revision: str = "head") -> None:
    """Upgrade or downgrade using an already-open, non-logged connection."""

    config = Config(str(root / "alembic.ini"))
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            if revision.startswith("-") or revision == "base":
                command.downgrade(config, revision)
            else:
                command.upgrade(config, revision)
    finally:
        engine.dispose()
