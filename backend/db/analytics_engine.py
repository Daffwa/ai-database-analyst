"""Least-privilege SQLite engine construction for the local MVP."""

from __future__ import annotations

import sqlite3
from functools import partial
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from backend.core.errors import DatabaseUnavailableError


def _connect_read_only(database_path: Path, *, timeout_seconds: float) -> sqlite3.Connection:
    encoded_path = quote(database_path.resolve().as_posix(), safe="/:")
    uri = f"file:{encoded_path}?mode=ro"
    try:
        connection = sqlite3.connect(
            uri,
            uri=True,
            check_same_thread=False,
            timeout=timeout_seconds,
        )
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error as exc:
        if "connection" in locals():
            connection.close()
        raise DatabaseUnavailableError() from exc
    return connection


def create_sqlite_read_only_engine(
    database_path: Path,
    *,
    timeout_seconds: float = 5.0,
) -> Engine:
    """Create a SQLAlchemy engine that opens a specific SQLite file read-only."""

    resolved_path = database_path.resolve()
    if not resolved_path.is_file():
        raise DatabaseUnavailableError()
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    creator = partial(_connect_read_only, resolved_path, timeout_seconds=timeout_seconds)
    return create_engine(
        "sqlite+pysqlite://",
        creator=creator,
        poolclass=NullPool,
    )


def sqlite_query_only_enabled(engine: Engine) -> bool:
    """Return whether SQLite reports query-only mode for a new connection."""

    with engine.connect() as connection:
        value = connection.exec_driver_sql("PRAGMA query_only").scalar_one()
    return bool(value)
