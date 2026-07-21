"""Database schema inspection, normalization, hashing, and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import SchemaInspectionError
from backend.schemas.database import (
    ColumnMetadata,
    ForeignKeyMetadata,
    SchemaAllowlist,
    SchemaSnapshot,
    TableMetadata,
)


class SchemaService:
    """Create deterministic snapshots from SQLAlchemy database inspection."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_snapshot(
        self,
        *,
        source_name: str,
        schema_version: str,
    ) -> SchemaSnapshot:
        try:
            inspector = inspect(self._engine)
            table_names = sorted(inspector.get_table_names(), key=str.casefold)
            tables = tuple(self._inspect_table(inspector, name) for name in table_names)
            views = tuple(sorted(inspector.get_view_names(), key=str.casefold))
        except SQLAlchemyError as exc:
            raise SchemaInspectionError() from exc

        return SchemaSnapshot.create(
            source_name=source_name,
            dialect=self._engine.dialect.name,
            schema_version=schema_version,
            tables=tables,
            views=views,
        )

    @staticmethod
    def _inspect_table(inspector: Any, table_name: str) -> TableMetadata:
        columns_raw = inspector.get_columns(table_name)
        pk_constraint = inspector.get_pk_constraint(table_name)
        primary_key = tuple(str(name) for name in pk_constraint.get("constrained_columns", ()))
        pk_positions = {name: index + 1 for index, name in enumerate(primary_key)}

        columns = tuple(
            ColumnMetadata(
                name=str(column["name"]),
                position=position,
                data_type=str(column["type"]),
                nullable=bool(column.get("nullable", True)),
                default=(None if column.get("default") is None else str(column.get("default"))),
                primary_key_position=pk_positions.get(str(column["name"])),
            )
            for position, column in enumerate(columns_raw)
        )

        foreign_keys = tuple(
            sorted(
                (
                    ForeignKeyMetadata(
                        name=(
                            None if foreign_key.get("name") is None else str(foreign_key["name"])
                        ),
                        constrained_columns=tuple(
                            str(name) for name in foreign_key.get("constrained_columns", ())
                        ),
                        referred_table=str(foreign_key["referred_table"]),
                        referred_columns=tuple(
                            str(name) for name in foreign_key.get("referred_columns", ())
                        ),
                        on_update=_option(foreign_key, "onupdate"),
                        on_delete=_option(foreign_key, "ondelete"),
                    )
                    for foreign_key in inspector.get_foreign_keys(table_name)
                ),
                key=lambda item: (
                    item.referred_table.casefold(),
                    item.constrained_columns,
                ),
            )
        )
        return TableMetadata(
            name=table_name,
            columns=columns,
            primary_key=primary_key,
            foreign_keys=foreign_keys,
        )


def _option(foreign_key: dict[str, Any], name: str) -> str | None:
    options = foreign_key.get("options") or {}
    value = options.get(name)
    return None if value is None else str(value)


def write_model_json(path: Path, model: BaseModel) -> None:
    """Persist a Pydantic model atomically as stable, human-readable JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.part")
    temporary.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_schema_snapshot(path: Path) -> SchemaSnapshot:
    return SchemaSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def load_schema_allowlist(path: Path) -> SchemaAllowlist:
    return SchemaAllowlist.model_validate_json(path.read_text(encoding="utf-8"))
