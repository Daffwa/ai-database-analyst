"""Alembic environment for the separate metadata database."""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from alembic import context
from backend.metadata.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    database_url = os.getenv("METADATA_MIGRATION_DATABASE_URL")
    if not database_url:
        raise RuntimeError("METADATA_MIGRATION_DATABASE_URL is required for offline migration")
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if isinstance(supplied, Connection):
        connection = supplied
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    database_url = os.getenv("METADATA_MIGRATION_DATABASE_URL")
    if not database_url:
        raise RuntimeError("METADATA_MIGRATION_DATABASE_URL is required")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
