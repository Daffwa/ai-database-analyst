"""PostgreSQL engines with explicit least-privilege identity checks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from backend.core.errors import ConfigurationError, DatabaseUnavailableError


@dataclass(frozen=True, slots=True)
class PostgreSQLIdentity:
    """Non-secret evidence about the connected database role."""

    current_user: str
    current_database: str
    superuser: bool
    create_database: bool
    create_role: bool
    bypass_rls: bool


def create_postgresql_engine(
    database_url: str,
    *,
    expected_username: str,
    connect_timeout_seconds: int = 5,
) -> Engine:
    """Create a psycopg engine only for the expected configured identity."""

    try:
        parsed = make_url(database_url)
    except Exception as exc:
        raise ConfigurationError("The PostgreSQL database URL is invalid.") from exc
    if parsed.drivername != "postgresql+psycopg":
        raise ConfigurationError("PostgreSQL URLs must use the postgresql+psycopg driver.")
    if parsed.username != expected_username:
        raise ConfigurationError(f"The database URL must use the {expected_username} role.")
    if not parsed.database:
        raise ConfigurationError("The PostgreSQL database name is required.")
    return create_engine(
        parsed,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": connect_timeout_seconds},
    )


def inspect_postgresql_identity(engine: Engine) -> PostgreSQLIdentity:
    """Read role flags without exposing a DSN, host, or credential."""

    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT current_user, current_database(), "
                    "r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolbypassrls "
                    "FROM pg_catalog.pg_roles AS r WHERE r.rolname = current_user"
                )
            ).one()
    except Exception as exc:
        raise DatabaseUnavailableError() from exc
    return PostgreSQLIdentity(
        current_user=str(row[0]),
        current_database=str(row[1]),
        superuser=bool(row[2]),
        create_database=bool(row[3]),
        create_role=bool(row[4]),
        bypass_rls=bool(row[5]),
    )


def assert_application_identity(
    engine: Engine,
    *,
    expected_username: str,
) -> PostgreSQLIdentity:
    """Fail if an application engine is privileged or uses the wrong role."""

    identity = inspect_postgresql_identity(engine)
    if identity.current_user != expected_username:
        raise ConfigurationError("The connected PostgreSQL role is not the expected identity.")
    if any(
        (
            identity.superuser,
            identity.create_database,
            identity.create_role,
            identity.bypass_rls,
        )
    ):
        raise ConfigurationError("Application PostgreSQL roles must not be privileged.")
    return identity
