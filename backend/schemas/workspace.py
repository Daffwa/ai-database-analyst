"""Strict contracts for ephemeral uploaded SQLite workspaces."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from backend.schemas.api import StrictAPIModel
from backend.schemas.result import DatabaseExplorerSnapshot


class WorkspaceSourceType(StrEnum):
    """Supported uploaded database representations."""

    SQLITE_DATABASE = "sqlite_database"
    SQLITE_SQL_DUMP = "sqlite_sql_dump"


class DatabaseWorkspace(StrictAPIModel):
    """Public metadata for one server-owned, expiring workspace."""

    workspace_id: str = Field(pattern=r"^dbw_[0-9a-f]{32}$")
    source_name: str = Field(min_length=1, max_length=255)
    source_type: WorkspaceSourceType
    size_bytes: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str
    expires_at: str
    table_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    provider: str
    model: str
    ai_query_ready: bool
    warnings: tuple[str, ...] = ()
    schema_snapshot: DatabaseExplorerSnapshot


class DatabaseWorkspaceDeleteResponse(StrictAPIModel):
    """Confirmation that an ephemeral workspace was destroyed."""

    workspace_id: str = Field(pattern=r"^dbw_[0-9a-f]{32}$")
    deleted: bool
