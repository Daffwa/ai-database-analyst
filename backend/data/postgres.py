"""Reproducible Chinook PostgreSQL seeding and least-privilege role setup."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url

from backend.data.initialization import CHINOOK_EXPECTED_TABLE_COUNTS
from backend.schemas.database import SchemaSnapshot

ANALYTICS_DATABASE = "chinook"
METADATA_DATABASE = "analyst_metadata"
ANALYTICS_OWNER = "analytics_owner"
ANALYTICS_READONLY = "analytics_readonly"
METADATA_USER = "app_metadata_user"
MIGRATION_USER = "migration_user"
DATA_SCHEMA = "chinook_data"
ANALYTICS_SCHEMA = "analytics"


@dataclass(frozen=True, slots=True)
class PostgreSQLBootstrapResult:
    """Non-secret evidence from a successful bootstrap."""

    analytics_database: str
    metadata_database: str
    analytics_role: str
    metadata_role: str
    table_counts: dict[str, int]


def psycopg_conninfo(database_url: str, *, database: str | None = None) -> str:
    """Translate a SQLAlchemy psycopg URL into a libpq URI for direct setup."""

    parsed = make_url(database_url)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("admin URL must use postgresql+psycopg")
    return parsed.set(
        drivername="postgresql",
        database=database or parsed.database or "postgres",
        query={**parsed.query, "connect_timeout": "10"},
    ).render_as_string(hide_password=False)


def application_database_urls(
    admin_url: str,
    *,
    analytics_password: str,
    metadata_password: str,
    migration_password: str,
) -> tuple[str, str, str]:
    """Build role-specific URLs while keeping credentials out of logs."""

    parsed = make_url(admin_url)
    analytics = URL.create(
        "postgresql+psycopg",
        username=ANALYTICS_READONLY,
        password=analytics_password,
        database=ANALYTICS_DATABASE,
        host=parsed.host,
        port=parsed.port,
        query=parsed.query,
    )
    metadata = URL.create(
        "postgresql+psycopg",
        username=METADATA_USER,
        password=metadata_password,
        database=METADATA_DATABASE,
        host=parsed.host,
        port=parsed.port,
        query=parsed.query,
    )
    migration = URL.create(
        "postgresql+psycopg",
        username=MIGRATION_USER,
        password=migration_password,
        database=METADATA_DATABASE,
        host=parsed.host,
        port=parsed.port,
        query=parsed.query,
    )
    return (
        analytics.render_as_string(hide_password=False),
        metadata.render_as_string(hide_password=False),
        migration.render_as_string(hide_password=False),
    )


def bootstrap_postgresql(
    admin_url: str,
    *,
    seed_sql_path: Path,
    logical_snapshot: SchemaSnapshot,
    passwords: Mapping[str, str],
) -> PostgreSQLBootstrapResult:
    """Create roles/databases, seed Chinook, and expose only compatibility views."""

    required_passwords = {ANALYTICS_READONLY, METADATA_USER, MIGRATION_USER}
    if set(passwords) != required_passwords or any(not passwords[name] for name in passwords):
        raise ValueError("all three application role passwords are required")
    source = seed_sql_path.read_text(encoding="utf-8-sig")
    seed_sql = _database_commands_removed(source)

    with psycopg.connect(psycopg_conninfo(admin_url), autocommit=True) as admin:
        _ensure_role(admin, ANALYTICS_OWNER, login=False)
        _ensure_role(
            admin,
            ANALYTICS_READONLY,
            login=True,
            password=passwords[ANALYTICS_READONLY],
        )
        _ensure_role(admin, METADATA_USER, login=True, password=passwords[METADATA_USER])
        _ensure_role(admin, MIGRATION_USER, login=True, password=passwords[MIGRATION_USER])
        _ensure_database(admin, ANALYTICS_DATABASE, ANALYTICS_OWNER)
        _ensure_database(admin, METADATA_DATABASE, MIGRATION_USER)
        _configure_database_connect(admin)

    with psycopg.connect(
        psycopg_conninfo(admin_url, database=ANALYTICS_DATABASE), autocommit=True
    ) as connection:
        connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(ANALYTICS_SCHEMA))
        )
        connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(DATA_SCHEMA))
        )
        connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(ANALYTICS_OWNER)))
        connection.execute(
            sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                sql.Identifier(DATA_SCHEMA), sql.Identifier(ANALYTICS_OWNER)
            )
        )
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(DATA_SCHEMA)))
        connection.execute(seed_sql, prepare=False)
        connection.execute(
            sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                sql.Identifier(ANALYTICS_SCHEMA), sql.Identifier(ANALYTICS_OWNER)
            )
        )
        for statement in _compatibility_view_statements(logical_snapshot):
            connection.execute(statement)
        connection.execute("RESET ROLE")
        _apply_analytics_privileges(connection)
        counts = _verify_counts(connection)

    return PostgreSQLBootstrapResult(
        analytics_database=ANALYTICS_DATABASE,
        metadata_database=METADATA_DATABASE,
        analytics_role=ANALYTICS_READONLY,
        metadata_role=METADATA_USER,
        table_counts=counts,
    )


def _database_commands_removed(source: str) -> str:
    blocked = re.compile(r"^\s*(?:DROP\s+DATABASE|CREATE\s+DATABASE|\\c\s+chinook)", re.I)
    return "\n".join(line for line in source.splitlines() if not blocked.match(line))


def _ensure_role(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    *,
    login: bool,
    password: str | None = None,
) -> None:
    exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    login_clause = sql.SQL("LOGIN") if login else sql.SQL("NOLOGIN")
    if exists is None:
        statement = sql.SQL(
            "CREATE ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        ).format(sql.Identifier(role), login_clause)
        if password is not None:
            statement += sql.SQL(" PASSWORD {}").format(sql.Literal(password))
        connection.execute(statement)
    else:
        statement = sql.SQL(
            "ALTER ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        ).format(sql.Identifier(role), login_clause)
        if password is not None:
            statement += sql.SQL(" PASSWORD {}").format(sql.Literal(password))
        connection.execute(statement)


def _ensure_database(
    connection: psycopg.Connection[tuple[object, ...]], database: str, owner: str
) -> None:
    exists = connection.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
    ).fetchone()
    if exists is None:
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database), sql.Identifier(owner)
            )
        )
    else:
        connection.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(database), sql.Identifier(owner)
            )
        )


def _configure_database_connect(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    for database in (ANALYTICS_DATABASE, METADATA_DATABASE):
        connection.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database))
        )
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(ANALYTICS_DATABASE),
            sql.Identifier(ANALYTICS_OWNER),
            sql.Identifier(ANALYTICS_READONLY),
        )
    )
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(METADATA_DATABASE),
            sql.Identifier(MIGRATION_USER),
            sql.Identifier(METADATA_USER),
        )
    )
    connection.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO {}, pg_temp").format(
            sql.Identifier(ANALYTICS_READONLY),
            sql.Identifier(ANALYTICS_DATABASE),
            sql.Identifier(ANALYTICS_SCHEMA),
        )
    )
    connection.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET default_transaction_read_only TO on").format(
            sql.Identifier(ANALYTICS_READONLY), sql.Identifier(ANALYTICS_DATABASE)
        )
    )
    connection.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET statement_timeout TO '5s'").format(
            sql.Identifier(ANALYTICS_READONLY), sql.Identifier(ANALYTICS_DATABASE)
        )
    )
    connection.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO app_metadata, pg_temp").format(
            sql.Identifier(METADATA_USER), sql.Identifier(METADATA_DATABASE)
        )
    )


def _compatibility_view_statements(snapshot: SchemaSnapshot) -> tuple[sql.Composed, ...]:
    statements: list[sql.Composed] = []
    for table in snapshot.tables:
        physical_table = _snake_case(table.name)
        projections = [
            sql.SQL("{} AS {}").format(
                sql.Identifier(_snake_case(column.name)),
                sql.Identifier(column.name.casefold()),
            )
            for column in table.columns
        ]
        statements.append(
            sql.SQL("CREATE VIEW {}.{} AS SELECT {} FROM {}.{}").format(
                sql.Identifier(ANALYTICS_SCHEMA),
                sql.Identifier(table.name.casefold()),
                sql.SQL(", ").join(projections),
                sql.Identifier(DATA_SCHEMA),
                sql.Identifier(physical_table),
            )
        )
    return tuple(statements)


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _apply_analytics_privileges(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    connection.execute(
        sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC, {}").format(
            sql.Identifier(DATA_SCHEMA), sql.Identifier(ANALYTICS_READONLY)
        )
    )
    connection.execute(
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(
            sql.Identifier(DATA_SCHEMA), sql.Identifier(ANALYTICS_READONLY)
        )
    )
    connection.execute(
        sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(ANALYTICS_SCHEMA))
    )
    connection.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(ANALYTICS_SCHEMA), sql.Identifier(ANALYTICS_READONLY)
        )
    )
    connection.execute(
        sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
            sql.Identifier(ANALYTICS_SCHEMA), sql.Identifier(ANALYTICS_READONLY)
        )
    )
    connection.execute(
        sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(
            sql.Identifier(ANALYTICS_SCHEMA), sql.Identifier(ANALYTICS_READONLY)
        )
    )


def _verify_counts(connection: psycopg.Connection[tuple[object, ...]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in sorted(CHINOOK_EXPECTED_TABLE_COUNTS):
        row = connection.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(ANALYTICS_SCHEMA), sql.Identifier(table.casefold())
            )
        ).fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL count verification returned no row")
        counts[table] = int(str(row[0]))
    if counts != dict(sorted(CHINOOK_EXPECTED_TABLE_COUNTS.items())):
        raise RuntimeError("PostgreSQL Chinook row counts do not match the pinned release")
    return counts
