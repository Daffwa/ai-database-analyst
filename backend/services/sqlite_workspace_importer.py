"""Fail-closed ingestion for uploaded SQLite databases and SQL dumps."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

from backend.core.errors import InvalidRequestError, SecurityPolicyError
from backend.schemas.workspace import WorkspaceSourceType

SQLITE_HEADER = b"SQLite format 3\x00"
SUPPORTED_DATABASE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
SUPPORTED_UPLOAD_SUFFIXES = frozenset({*SUPPORTED_DATABASE_SUFFIXES, ".sql"})


@dataclass(frozen=True, slots=True)
class SQLiteImportPolicy:
    """Resource budgets for one untrusted upload."""

    max_upload_bytes: int
    max_database_bytes: int
    max_statements: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        if (
            min(
                self.max_upload_bytes,
                self.max_database_bytes,
                self.max_statements,
                self.timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("SQLite import budgets must be greater than zero")


@dataclass(frozen=True, slots=True)
class SQLiteImportResult:
    """Safe provenance returned after creating the isolated SQLite file."""

    source_type: WorkspaceSourceType
    content_sha256: str
    size_bytes: int


def import_sqlite_upload(
    *,
    filename: str,
    payload: bytes,
    destination: Path,
    policy: SQLiteImportPolicy,
) -> SQLiteImportResult:
    """Create one isolated SQLite database without executing unrestricted SQL."""

    suffix = Path(filename).suffix.casefold()
    if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
        raise InvalidRequestError(
            "Only .db, .sqlite, .sqlite3, and SQLite .sql files are supported."
        )
    if not payload:
        raise InvalidRequestError("The uploaded file is empty.")
    if len(payload) > policy.max_upload_bytes:
        raise InvalidRequestError(
            "The uploaded file exceeds the configured size limit.",
            details={"max_bytes": policy.max_upload_bytes},
        )

    destination.parent.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(payload).hexdigest()
    if suffix in SUPPORTED_DATABASE_SUFFIXES:
        if not payload.startswith(SQLITE_HEADER):
            raise InvalidRequestError("The uploaded file is not a valid SQLite database.")
        destination.write_bytes(payload)
        source_type = WorkspaceSourceType.SQLITE_DATABASE
    else:
        _import_sql_dump(payload, destination, policy)
        source_type = WorkspaceSourceType.SQLITE_SQL_DUMP

    if destination.stat().st_size > policy.max_database_bytes:
        raise InvalidRequestError(
            "The imported database exceeds the configured storage limit.",
            details={"max_database_bytes": policy.max_database_bytes},
        )
    return SQLiteImportResult(
        source_type=source_type,
        content_sha256=digest,
        size_bytes=len(payload),
    )


def _import_sql_dump(payload: bytes, destination: Path, policy: SQLiteImportPolicy) -> None:
    try:
        sql_text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError("SQLite SQL uploads must use UTF-8 encoding.") from exc
    if "\x00" in sql_text:
        raise InvalidRequestError("The SQL upload contains invalid null bytes.")

    statements = _split_sql_statements(sql_text)
    if not statements:
        raise InvalidRequestError("The SQL upload contains no statements.")
    if len(statements) > policy.max_statements:
        raise InvalidRequestError(
            "The SQL upload contains too many statements.",
            details={"max_statements": policy.max_statements},
        )

    deadline = monotonic() + policy.timeout_seconds
    try:
        connection = sqlite3.connect(destination, timeout=policy.timeout_seconds)
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        max_pages = max(1, policy.max_database_bytes // page_size)
        connection.execute(f"PRAGMA max_page_count = {max_pages}")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.set_progress_handler(lambda: int(monotonic() >= deadline), 1_000)
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in statements:
                if monotonic() >= deadline:
                    raise InvalidRequestError("The SQL import exceeded its time limit.")
                expression = _validated_import_expression(statement)
                if expression is None:
                    continue
                connection.execute(statement)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.set_progress_handler(None, 0)
            connection.close()
    except (InvalidRequestError, SecurityPolicyError):
        raise
    except (sqlite3.Error, OSError) as exc:
        raise InvalidRequestError("The SQLite SQL upload could not be imported safely.") from exc


def _validated_import_expression(statement: str) -> exp.Expression | None:
    try:
        expressions = sqlglot.parse(
            statement,
            read="sqlite",
            error_level=sqlglot.ErrorLevel.RAISE,
        )
    except (ParseError, SqlglotError, ValueError) as exc:
        raise InvalidRequestError("The SQL upload contains invalid SQLite syntax.") from exc
    if len(expressions) != 1 or expressions[0] is None:
        raise SecurityPolicyError("Every imported SQL statement must parse independently.")
    expression = expressions[0]

    if isinstance(expression, (exp.Transaction, exp.Commit)):
        return None
    if isinstance(expression, exp.Create):
        return _validate_create(expression)
    if isinstance(expression, exp.Insert):
        return _validate_insert(expression)
    raise SecurityPolicyError(
        "SQL uploads may contain only CREATE TABLE, CREATE INDEX, and INSERT VALUES."
    )


def _validate_create(expression: exp.Create) -> exp.Expression:
    kind = str(expression.args.get("kind") or "").upper()
    if kind not in {"TABLE", "INDEX"}:
        raise SecurityPolicyError("Views, triggers, and other SQL objects are not allowed.")
    if expression.args.get("replace") or expression.args.get("expression") is not None:
        raise SecurityPolicyError("CREATE OR REPLACE and CREATE AS are not allowed.")
    if expression.find(exp.VirtualProperty) is not None:
        raise SecurityPolicyError("SQLite virtual tables are not allowed.")
    if any(expression.find(node) is not None for node in (exp.Select, exp.Subquery, exp.Func)):
        raise SecurityPolicyError("Computed CREATE expressions are not allowed in SQL uploads.")
    table = _created_table(expression)
    _validate_table_identifier(table)
    if expression.find(exp.Command) is not None:
        raise SecurityPolicyError("Unrecognized CREATE syntax is not allowed.")
    return expression


def _validate_insert(expression: exp.Insert) -> exp.Expression:
    table: exp.Expression = expression.this
    if isinstance(table, exp.Schema):
        table = table.this
    if not isinstance(table, exp.Table):
        raise SecurityPolicyError("INSERT must target one explicit table.")
    _validate_table_identifier(table)
    if not isinstance(expression.args.get("expression"), exp.Values):
        raise SecurityPolicyError("INSERT SELECT and computed data imports are not allowed.")
    if (
        expression.args.get("returning") is not None
        or expression.args.get("overwrite")
        or expression.args.get("conflict") is not None
        or expression.args.get("alternative") is not None
        or expression.args.get("ignore")
    ):
        raise SecurityPolicyError("INSERT modifiers are not allowed in SQL uploads.")
    if any(expression.find(node) is not None for node in (exp.Select, exp.Subquery, exp.Func)):
        raise SecurityPolicyError("Imported values must be literals, not queries or functions.")
    return expression


def _created_table(expression: exp.Create) -> exp.Table:
    target = expression.this
    if isinstance(target, exp.Schema):
        target = target.this
    if isinstance(target, exp.Index):
        target = target.args.get("table")
    if not isinstance(target, exp.Table):
        raise SecurityPolicyError("CREATE must target one explicit table.")
    return target


def _validate_table_identifier(table: exp.Table) -> None:
    if table.catalog or (table.db and table.db.casefold() != "main"):
        raise SecurityPolicyError("Attached databases and cross-schema objects are not allowed.")
    name = table.name
    if not name or name.casefold().startswith("sqlite_"):
        raise SecurityPolicyError("SQLite system objects are not allowed.")
    if len(name) > 128 or any(ord(character) < 32 for character in name):
        raise SecurityPolicyError("The SQL upload contains an invalid table identifier.")


def _split_sql_statements(sql_text: str) -> tuple[str, ...]:
    """Split on top-level semicolons while preserving quoted values and comments."""

    statements: list[str] = []
    start = 0
    index = 0
    quote: str | None = None
    bracketed = False
    line_comment = False
    block_comment = False
    length = len(sql_text)
    while index < length:
        character = sql_text[index]
        next_character = sql_text[index + 1] if index + 1 < length else ""
        if line_comment:
            if character in "\r\n":
                line_comment = False
        elif block_comment:
            if character == "*" and next_character == "/":
                block_comment = False
                index += 1
        elif quote is not None:
            if character == quote:
                if next_character == quote:
                    index += 1
                else:
                    quote = None
        elif bracketed:
            if character == "]":
                bracketed = False
        elif character == "-" and next_character == "-":
            line_comment = True
            index += 1
        elif character == "/" and next_character == "*":
            block_comment = True
            index += 1
        elif character in {"'", '"', "`"}:
            quote = character
        elif character == "[":
            bracketed = True
        elif character == ";":
            candidate = sql_text[start : index + 1].strip()
            if candidate:
                statements.append(candidate)
            start = index + 1
        index += 1

    if quote is not None or bracketed or block_comment:
        raise InvalidRequestError("The SQL upload ends inside an unterminated token.")
    remainder = sql_text[start:].strip()
    if remainder:
        statements.append(remainder)
    return tuple(statements)
