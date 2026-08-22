"""Ephemeral, isolated query workspaces for user-uploaded SQLite data."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Protocol
from uuid import uuid4

from sqlalchemy.engine import Engine

from backend.core.config import AppSettings
from backend.core.errors import InvalidRequestError, WorkspaceNotFoundError
from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.llm.factory import create_llm_adapter
from backend.schemas.database import SchemaAllowlist, SchemaSnapshot
from backend.schemas.llm import QueryResponse
from backend.schemas.result import DatabaseExplorerSnapshot
from backend.schemas.workspace import (
    DatabaseWorkspace,
    DatabaseWorkspaceDeleteResponse,
    WorkspaceSourceType,
)
from backend.services.chart_selector import ChartPolicy, DeterministicChartSelector
from backend.services.experience_metadata import DatabaseExplorerService
from backend.services.orchestrator import QueryOrchestrator, QueryProcessor
from backend.services.output_parser import StructuredOutputParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.query_executor import ManualQueryExecutor
from backend.services.query_history import QueryHistoryService
from backend.services.result_experience import ResultExperienceOrchestrator
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import SchemaService
from backend.services.secure_orchestrator import SecureQueryOrchestrator
from backend.services.sql_generator import SQLGenerator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService
from backend.services.sqlite_workspace_importer import (
    SQLiteImportPolicy,
    import_sqlite_upload,
)

UPLOADED_SQLITE_WARNING = (
    "SQL passed the deterministic AST policy and executed only against the "
    "ephemeral uploaded SQLite workspace in read-only mode."
)


class DatabaseWorkspaceService(Protocol):
    """API-facing boundary for uploaded database lifecycle and queries."""

    @property
    def max_upload_bytes(self) -> int: ...

    def create(self, filename: str, payload: bytes) -> DatabaseWorkspace: ...

    def schema(self, workspace_id: str) -> DatabaseExplorerSnapshot: ...

    async def query(self, workspace_id: str, question: str) -> QueryResponse: ...

    def delete(self, workspace_id: str) -> DatabaseWorkspaceDeleteResponse: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class _WorkspaceRuntime:
    engine: Engine
    processor: QueryProcessor
    explorer: DatabaseExplorerSnapshot

    def close(self) -> None:
        self.engine.dispose()


@dataclass(slots=True)
class _WorkspaceEntry:
    public: DatabaseWorkspace
    runtime: _WorkspaceRuntime
    directory: Path
    active_queries: int = 0


class UploadedDatabaseWorkspaceService:
    """Own bounded temporary files and an independent read-only query runtime."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        storage_root: Path | None = None,
        fake_responses: Mapping[str, str] | None = None,
    ) -> None:
        configured_root = storage_root or settings.database_workspace_storage_root
        self._storage_root = (
            Path(configured_root).resolve()
            if configured_root is not None
            else Path(tempfile.gettempdir()).resolve() / "ai-database-analyst-workspaces"
        )
        self._storage_root.mkdir(parents=True, exist_ok=True)
        self._settings = settings
        self._fake_responses = fake_responses
        self._entries: dict[str, _WorkspaceEntry] = {}
        self._lock = RLock()

    @property
    def max_upload_bytes(self) -> int:
        return self._settings.database_workspace_upload_max_bytes

    def create(self, filename: str, payload: bytes) -> DatabaseWorkspace:
        source_name = _safe_source_name(filename)
        with self._lock:
            self._remove_expired_locked()
            if len(self._entries) >= self._settings.database_workspace_max_active:
                raise InvalidRequestError(
                    "The server has reached its active uploaded-workspace limit."
                )

        workspace_id = f"dbw_{uuid4().hex}"
        directory = (self._storage_root / workspace_id).resolve()
        _assert_owned_directory(self._storage_root, directory)
        database_path = directory / "database.sqlite"
        try:
            imported = import_sqlite_upload(
                filename=source_name,
                payload=payload,
                destination=database_path,
                policy=SQLiteImportPolicy(
                    max_upload_bytes=self._settings.database_workspace_upload_max_bytes,
                    max_database_bytes=self._settings.database_workspace_max_database_bytes,
                    max_statements=self._settings.database_workspace_max_sql_statements,
                    max_records=self._settings.database_workspace_max_records,
                    max_tables=self._settings.database_workspace_max_tables,
                    max_columns=self._settings.database_workspace_max_columns,
                    timeout_seconds=self._settings.database_workspace_import_timeout_seconds,
                ),
            )
            _validate_sqlite_database(
                database_path,
                timeout_seconds=self._settings.database_workspace_import_timeout_seconds,
                max_tables=self._settings.database_workspace_max_tables,
                max_columns=self._settings.database_workspace_max_columns,
            )
            runtime, snapshot = _create_workspace_runtime(
                database_path,
                source_name=source_name,
                content_sha256=imported.content_sha256,
                settings=self._settings,
                fake_responses=self._fake_responses,
            )
            column_count = sum(len(table.columns) for table in snapshot.tables)
            if len(snapshot.tables) > self._settings.database_workspace_max_tables:
                raise InvalidRequestError("The uploaded database contains too many tables.")
            if column_count > self._settings.database_workspace_max_columns:
                raise InvalidRequestError("The uploaded database contains too many columns.")
            if not snapshot.tables or column_count == 0:
                raise InvalidRequestError("The uploaded database has no queryable tables.")

            created_at = datetime.now(UTC)
            expires_at = created_at + timedelta(
                seconds=self._settings.database_workspace_ttl_seconds
            )
            provider_warning = (
                "The fake provider cannot generate arbitrary uploaded-schema queries; "
                "configure the approved Gemini provider to use prompt-to-query."
                if self._settings.llm_provider.casefold() == "fake"
                else "Uploaded schema and relevant table metadata are sent to the configured "
                "LLM provider when a workspace question is submitted.",
            )
            warnings = (*provider_warning, *_source_warnings(imported.source_type))
            public = DatabaseWorkspace(
                workspace_id=workspace_id,
                source_name=source_name,
                source_type=imported.source_type,
                size_bytes=imported.size_bytes,
                content_sha256=imported.content_sha256,
                created_at=created_at.isoformat(),
                expires_at=expires_at.isoformat(),
                table_count=len(snapshot.tables),
                column_count=column_count,
                provider=self._settings.llm_provider,
                model=self._settings.llm_model,
                ai_query_ready=(
                    self._settings.llm_provider.casefold() != "fake"
                    and self._settings.has_llm_credentials
                ),
                warnings=warnings,
                schema_snapshot=runtime.explorer,
            )
            entry = _WorkspaceEntry(public=public, runtime=runtime, directory=directory)
            with self._lock:
                self._remove_expired_locked()
                if len(self._entries) >= self._settings.database_workspace_max_active:
                    raise InvalidRequestError(
                        "The server has reached its active uploaded-workspace limit."
                    )
                self._entries[workspace_id] = entry
            return public
        except Exception:
            if "runtime" in locals():
                runtime.close()
            _remove_owned_directory(self._storage_root, directory)
            raise

    def schema(self, workspace_id: str) -> DatabaseExplorerSnapshot:
        with self._lock:
            return self._entry_locked(workspace_id).runtime.explorer

    async def query(self, workspace_id: str, question: str) -> QueryResponse:
        with self._lock:
            entry = self._entry_locked(workspace_id)
            entry.active_queries += 1
        try:
            return await entry.runtime.processor.process(question)
        finally:
            with self._lock:
                entry.active_queries -= 1

    def delete(self, workspace_id: str) -> DatabaseWorkspaceDeleteResponse:
        with self._lock:
            entry = self._entry_locked(workspace_id)
            if entry.active_queries:
                raise InvalidRequestError("The uploaded workspace is currently processing a query.")
            self._entries.pop(workspace_id)
        _close_and_remove(self._storage_root, entry)
        return DatabaseWorkspaceDeleteResponse(workspace_id=workspace_id, deleted=True)

    def close(self) -> None:
        with self._lock:
            entries = tuple(self._entries.values())
            self._entries.clear()
        for entry in entries:
            _close_and_remove(self._storage_root, entry)

    def _entry_locked(self, workspace_id: str) -> _WorkspaceEntry:
        self._remove_expired_locked()
        entry = self._entries.get(workspace_id)
        if entry is None:
            raise WorkspaceNotFoundError()
        return entry

    def _remove_expired_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [
            workspace_id
            for workspace_id, entry in self._entries.items()
            if datetime.fromisoformat(entry.public.expires_at) <= now and entry.active_queries == 0
        ]
        for workspace_id in expired:
            entry = self._entries.pop(workspace_id)
            _close_and_remove(self._storage_root, entry)


def _create_workspace_runtime(
    database_path: Path,
    *,
    source_name: str,
    content_sha256: str,
    settings: AppSettings,
    fake_responses: Mapping[str, str] | None,
) -> tuple[_WorkspaceRuntime, SchemaSnapshot]:
    engine = create_sqlite_read_only_engine(
        database_path,
        timeout_seconds=settings.query_timeout_seconds,
    )
    try:
        snapshot = SchemaService(engine).create_snapshot(
            source_name=source_name,
            schema_version=f"upload-{content_sha256[:12]}",
        )
        allowlist = SchemaAllowlist.from_snapshot(snapshot)
        validator = SQLSecurityService(
            allowlist,
            policy=SQLSecurityPolicy(
                dialect="sqlite",
                max_rows=settings.query_max_rows,
                max_query_characters=settings.sql_max_query_characters,
                allowed_schemas=frozenset({"main"}),
                blocked_functions=frozenset(settings.sql_blocked_functions),
            ),
        )
        adapter = create_llm_adapter(settings, fake_responses=fake_responses or {})
        generator = SQLGenerator(
            adapter,
            PromptBuilder(
                SchemaRetriever(
                    max_tables=settings.database_workspace_max_tables,
                    max_characters=settings.prompt_schema_max_characters,
                    fallback_to_all=True,
                ),
                prompt_version="v4",
            ),
            StructuredOutputParser(max_characters=settings.llm_max_output_characters),
            timeout_seconds=settings.llm_timeout_seconds,
        )
        generation = QueryOrchestrator(
            generator,
            snapshot,
            max_question_characters=settings.question_max_characters,
        )
        executor = ManualQueryExecutor(
            engine,
            max_rows=settings.query_max_rows,
            max_columns=settings.query_max_columns,
            max_response_bytes=settings.query_max_response_bytes,
            max_query_characters=settings.sql_max_query_characters,
            timeout_seconds=settings.query_timeout_seconds,
        )
        secure = SecureQueryOrchestrator(
            generation,
            validator,
            executor,
            success_warning=UPLOADED_SQLITE_WARNING,
        )
        processor = ResultExperienceOrchestrator(
            secure,
            ResultFormatter({}),
            DeterministicChartSelector(
                ChartPolicy(
                    max_bar_categories=settings.chart_max_categories,
                    max_grouped_measures=settings.chart_max_grouped_measures,
                    recommended_line_points=settings.chart_recommended_line_points,
                    recommended_scatter_points=settings.chart_recommended_scatter_points,
                )
            ),
            ResultSummarizer(),
            QueryHistoryService(max_entries=1, enabled=False),
            enable_summary=settings.enable_result_summary,
        )
        explorer = DatabaseExplorerService(
            snapshot,
            refreshed_at=datetime.now(UTC).isoformat(),
            review_status="uploaded_unreviewed",
        ).snapshot()
        return _WorkspaceRuntime(engine=engine, processor=processor, explorer=explorer), snapshot
    except Exception:
        engine.dispose()
        raise


def _validate_sqlite_database(
    database_path: Path,
    *,
    timeout_seconds: float,
    max_tables: int,
    max_columns: int,
) -> None:
    deadline = monotonic() + timeout_seconds
    try:
        connection = sqlite3.connect(
            f"file:{database_path.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=timeout_seconds,
        )
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.set_progress_handler(
            lambda: int(monotonic() >= deadline),
            1_000,
        )
        try:
            quick_check = connection.execute("PRAGMA quick_check(1)").fetchone()
            if quick_check is None or str(quick_check[0]).casefold() != "ok":
                raise InvalidRequestError("The uploaded SQLite database failed integrity checks.")
            objects = connection.execute(
                "SELECT type, name, sql FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
            table_names = tuple(
                str(name) for object_type, name, _sql in objects if object_type == "table"
            )
            if len(table_names) > max_tables:
                raise InvalidRequestError("The uploaded database contains too many tables.")
            column_count = 0
            for table_name in table_names:
                _validate_uploaded_identifier(table_name)
                columns = connection.execute(
                    "SELECT name FROM pragma_table_xinfo(?)",
                    (table_name,),
                ).fetchall()
                for (column_name,) in columns:
                    _validate_uploaded_identifier(str(column_name))
                column_count += len(columns)
                if column_count > max_columns:
                    raise InvalidRequestError("The uploaded database contains too many columns.")
        finally:
            connection.set_progress_handler(None, 0)
            connection.close()
    except InvalidRequestError:
        raise
    except sqlite3.Error as exc:
        raise InvalidRequestError("The uploaded file is not a readable SQLite database.") from exc

    for object_type, _name, sql in objects:
        normalized_sql = str(sql or "").lstrip().casefold()
        if object_type in {"view", "trigger"} or normalized_sql.startswith("create virtual table"):
            raise InvalidRequestError(
                "Uploaded SQLite views, triggers, and virtual tables are not supported."
            )


def _safe_source_name(filename: str) -> str:
    if not filename or any(ord(character) < 32 for character in filename):
        raise InvalidRequestError("The upload filename is invalid.")
    source_name = Path(filename.replace("\\", "/")).name.strip()
    if not source_name or source_name in {".", ".."} or len(source_name) > 255:
        raise InvalidRequestError("The upload filename is invalid.")
    return source_name


def _source_warnings(source_type: WorkspaceSourceType) -> tuple[str, ...]:
    if source_type is WorkspaceSourceType.CSV_TABLE:
        return (
            "CSV values are preserved as text and unsafe or duplicate headers are normalized "
            "into unique SQLite column names.",
        )
    if source_type is WorkspaceSourceType.JSON_DOCUMENT:
        return (
            "JSON scalar types are preserved where SQLite supports them; nested arrays and "
            "objects are stored as compact JSON text.",
        )
    if source_type is WorkspaceSourceType.SQLITE_BACKUP:
        return ("The .bak upload was accepted because it is a valid SQLite backup.",)
    return ()


def _validate_uploaded_identifier(identifier: str) -> None:
    if (
        not identifier
        or "." in identifier
        or len(identifier) > 128
        or any(ord(character) < 32 for character in identifier)
    ):
        raise InvalidRequestError(
            "The uploaded database contains an unsupported table or column identifier."
        )


def _assert_owned_directory(storage_root: Path, directory: Path) -> None:
    if directory.parent != storage_root or not directory.name.startswith("dbw_"):
        raise RuntimeError("Workspace storage ownership check failed")


def _remove_owned_directory(storage_root: Path, directory: Path) -> None:
    _assert_owned_directory(storage_root, directory)
    if directory.exists():
        shutil.rmtree(directory)


def _close_and_remove(storage_root: Path, entry: _WorkspaceEntry) -> None:
    entry.runtime.close()
    _remove_owned_directory(storage_root, entry.directory)
