"""Bounded manual query execution over an already read-only engine."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from time import perf_counter
from typing import Any, Protocol

from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

from backend.core.errors import (
    InvalidRequestError,
    QueryExecutionError,
    QueryTimeoutError,
    ResultTooLargeError,
)
from backend.schemas.database import QueryResult


class QueryExecutor(Protocol):
    """Execution boundary accepted by secure orchestration."""

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryResult: ...


class ManualQueryExecutor:
    """Execute developer-supplied analytical SQL with response budgets.

    Direct use is intended for trusted developer SQL. Generated SQL may reach
    this service only through the Tahap 4 AST security orchestrator.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        max_rows: int = 500,
        max_columns: int = 100,
        max_response_bytes: int = 5_000_000,
        max_query_characters: int = 12_000,
        timeout_seconds: float = 5.0,
    ) -> None:
        if (
            min(
                max_rows,
                max_columns,
                max_response_bytes,
                max_query_characters,
                timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("Query budgets must be greater than zero")
        self._engine = engine
        self._max_rows = max_rows
        self._max_columns = max_columns
        self._max_response_bytes = max_response_bytes
        self._max_query_characters = max_query_characters
        self._timeout_seconds = timeout_seconds

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        normalized_sql = sql.strip()
        if not normalized_sql:
            raise InvalidRequestError("SQL must not be empty.")
        if len(normalized_sql) > self._max_query_characters:
            raise InvalidRequestError("SQL exceeds the configured character limit.")

        started = perf_counter()
        try:
            with self._engine.connect() as connection:
                raw_connection = connection.connection.driver_connection
                sqlite_connection = (
                    raw_connection if isinstance(raw_connection, sqlite3.Connection) else None
                )
                deadline = perf_counter() + self._timeout_seconds
                if sqlite_connection is not None:
                    sqlite_connection.set_progress_handler(
                        lambda: int(perf_counter() >= deadline),
                        1_000,
                    )
                try:
                    result = connection.exec_driver_sql(
                        normalized_sql,
                        dict(parameters or {}),
                    )
                    if not result.returns_rows:
                        raise QueryExecutionError("Only queries that return rows are supported.")

                    column_names = result.keys()
                    columns = tuple(map(str, column_names))
                    if len(columns) > self._max_columns:
                        raise ResultTooLargeError(
                            details={"max_columns": self._max_columns},
                        )

                    fetched = result.fetchmany(self._max_rows + 1)
                finally:
                    if sqlite_connection is not None:
                        sqlite_connection.set_progress_handler(None, 0)
        except OperationalError as exc:
            if "interrupted" in str(exc).casefold():
                raise QueryTimeoutError() from exc
            raise QueryExecutionError() from exc
        except SQLAlchemyError as exc:
            raise QueryExecutionError() from exc

        truncated = len(fetched) > self._max_rows
        rows = tuple(tuple(row) for row in fetched[: self._max_rows])
        response_bytes = len(
            json.dumps(
                {"columns": columns, "rows": rows},
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )
        if response_bytes > self._max_response_bytes:
            raise ResultTooLargeError(
                details={"max_response_bytes": self._max_response_bytes},
            )

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            execution_time_ms=(perf_counter() - started) * 1_000,
            response_bytes=response_bytes,
        )


class PostgreSQLReadOnlyQueryExecutor:
    """Execute validated SQL inside a bounded PostgreSQL read-only transaction."""

    def __init__(
        self,
        engine: Engine,
        *,
        schema: str = "analytics",
        max_rows: int = 500,
        max_columns: int = 100,
        max_response_bytes: int = 5_000_000,
        max_query_characters: int = 12_000,
        timeout_seconds: float = 5.0,
    ) -> None:
        if (
            min(
                max_rows,
                max_columns,
                max_response_bytes,
                max_query_characters,
                timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("Query budgets must be greater than zero")
        if not schema or not schema.replace("_", "").isalnum():
            raise ValueError("PostgreSQL analytics schema is invalid")
        self._engine = engine
        self._schema = schema
        self._max_rows = max_rows
        self._max_columns = max_columns
        self._max_response_bytes = max_response_bytes
        self._max_query_characters = max_query_characters
        self._timeout_seconds = timeout_seconds

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        normalized_sql = sql.strip()
        if not normalized_sql:
            raise InvalidRequestError("SQL must not be empty.")
        if len(normalized_sql) > self._max_query_characters:
            raise InvalidRequestError("SQL exceeds the configured character limit.")

        started = perf_counter()
        fetched: list[Any]
        columns: tuple[str, ...]
        timeout_ms = max(1, int(self._timeout_seconds * 1_000))
        try:
            with self._engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    connection.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout_ms}")
                    connection.exec_driver_sql(
                        f'SET LOCAL search_path TO "{self._schema}", pg_temp'
                    )
                    result = connection.exec_driver_sql(
                        normalized_sql,
                        dict(parameters or {}),
                    )
                    if not result.returns_rows:
                        raise QueryExecutionError("Only queries that return rows are supported.")
                    columns = tuple(map(str, result.keys()))
                    if len(columns) > self._max_columns:
                        raise ResultTooLargeError(details={"max_columns": self._max_columns})
                    fetched = list(result.fetchmany(self._max_rows + 1))
                finally:
                    transaction.rollback()
        except DBAPIError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None)
            if sqlstate == "57014":
                raise QueryTimeoutError() from exc
            raise QueryExecutionError() from exc
        except SQLAlchemyError as exc:
            raise QueryExecutionError() from exc

        truncated = len(fetched) > self._max_rows
        rows = tuple(tuple(row) for row in fetched[: self._max_rows])
        response_bytes = len(
            json.dumps(
                {"columns": columns, "rows": rows},
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )
        if response_bytes > self._max_response_bytes:
            raise ResultTooLargeError(details={"max_response_bytes": self._max_response_bytes})
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            execution_time_ms=(perf_counter() - started) * 1_000,
            response_bytes=response_bytes,
        )
