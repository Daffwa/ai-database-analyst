"""Normalized database metadata and read-only query result contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class ColumnMetadata(BaseModel):
    """One normalized column in ordinal database order."""

    model_config = ConfigDict(frozen=True)

    name: str
    position: int = Field(ge=0)
    data_type: str
    nullable: bool
    default: str | None = None
    primary_key_position: int | None = Field(default=None, ge=1)


class ForeignKeyMetadata(BaseModel):
    """A normalized table-level foreign-key relationship."""

    model_config = ConfigDict(frozen=True)

    name: str | None = None
    constrained_columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]
    on_update: str | None = None
    on_delete: str | None = None


class TableMetadata(BaseModel):
    """Normalized metadata for one analytics table."""

    model_config = ConfigDict(frozen=True)

    name: str
    columns: tuple[ColumnMetadata, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKeyMetadata, ...]


class SchemaSnapshot(BaseModel):
    """Versioned and content-addressed analytics schema."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    dialect: str
    schema_version: str
    tables: tuple[TableMetadata, ...]
    views: tuple[str, ...]
    schema_hash: str

    @classmethod
    def create(
        cls,
        *,
        source_name: str,
        dialect: str,
        schema_version: str,
        tables: tuple[TableMetadata, ...],
        views: tuple[str, ...],
    ) -> Self:
        body = {
            "source_name": source_name,
            "dialect": dialect,
            "schema_version": schema_version,
            "tables": [table.model_dump(mode="json") for table in tables],
            "views": list(views),
        }
        canonical = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(**body, schema_hash=hashlib.sha256(canonical).hexdigest())


class SchemaAllowlist(BaseModel):
    """Exact table/column allowlist derived from a verified snapshot."""

    model_config = ConfigDict(frozen=True)

    schema_hash: str
    tables: dict[str, tuple[str, ...]]
    views: tuple[str, ...]

    @classmethod
    def from_snapshot(cls, snapshot: SchemaSnapshot) -> Self:
        return cls(
            schema_hash=snapshot.schema_hash,
            tables={
                table.name: tuple(column.name for column in table.columns)
                for table in snapshot.tables
            },
            views=snapshot.views,
        )

    def allows_table(self, table_name: str) -> bool:
        return table_name in self.tables or table_name in self.views

    def allows_column(self, table_name: str, column_name: str) -> bool:
        return column_name in self.tables.get(table_name, ())


class QueryResult(BaseModel):
    """Bounded and JSON-compatible result from a manual read-only query."""

    model_config = ConfigDict(frozen=True)

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_count: int = Field(ge=0)
    truncated: bool
    execution_time_ms: float = Field(ge=0)
    response_bytes: int = Field(ge=0)
