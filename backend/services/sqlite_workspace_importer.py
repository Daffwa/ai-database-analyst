"""Fail-closed ingestion for uploaded SQLite and bounded tabular data."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import sqlite3
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

from backend.core.errors import InvalidRequestError, SecurityPolicyError
from backend.schemas.workspace import WorkspaceSourceType

SQLITE_HEADER = b"SQLite format 3\x00"
SUPPORTED_DATABASE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
SUPPORTED_BACKUP_SUFFIXES = frozenset({".bak"})
SUPPORTED_TABULAR_SUFFIXES = frozenset({".csv", ".json"})
SUPPORTED_UPLOAD_SUFFIXES = frozenset(
    {
        *SUPPORTED_DATABASE_SUFFIXES,
        *SUPPORTED_BACKUP_SUFFIXES,
        *SUPPORTED_TABULAR_SUFFIXES,
        ".sql",
    }
)
MAX_JSON_NESTING_DEPTH = 32
MAX_IDENTIFIER_CHARACTERS = 120
_UNSAFE_IDENTIFIER_CHARACTERS = re.compile(r"[^A-Za-z0-9_]+")


@dataclass(frozen=True, slots=True)
class SQLiteImportPolicy:
    """Resource budgets for one untrusted upload."""

    max_upload_bytes: int
    max_database_bytes: int
    max_statements: int
    max_records: int
    max_tables: int
    max_columns: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        if (
            min(
                self.max_upload_bytes,
                self.max_database_bytes,
                self.max_statements,
                self.max_records,
                self.max_tables,
                self.max_columns,
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
            "Only .db, .sqlite, .sqlite3, SQLite .bak, .sql, .csv, and .json files are supported."
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
    if suffix in SUPPORTED_DATABASE_SUFFIXES or suffix in SUPPORTED_BACKUP_SUFFIXES:
        if not payload.startswith(SQLITE_HEADER):
            if suffix in SUPPORTED_BACKUP_SUFFIXES:
                raise InvalidRequestError(
                    "Only SQLite backups saved as .bak are supported; SQL Server .bak "
                    "files must be restored outside this application."
                )
            raise InvalidRequestError("The uploaded file is not a valid SQLite database.")
        destination.write_bytes(payload)
        source_type = (
            WorkspaceSourceType.SQLITE_BACKUP
            if suffix in SUPPORTED_BACKUP_SUFFIXES
            else WorkspaceSourceType.SQLITE_DATABASE
        )
    elif suffix == ".sql":
        _import_sql_dump(payload, destination, policy)
        source_type = WorkspaceSourceType.SQLITE_SQL_DUMP
    elif suffix == ".csv":
        _import_csv(payload, destination, filename=filename, policy=policy)
        source_type = WorkspaceSourceType.CSV_TABLE
    else:
        _import_json(payload, destination, filename=filename, policy=policy)
        source_type = WorkspaceSourceType.JSON_DOCUMENT

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


def _import_csv(
    payload: bytes,
    destination: Path,
    *,
    filename: str,
    policy: SQLiteImportPolicy,
) -> None:
    text = _decode_utf8(payload, label="CSV")
    if "\x00" in text:
        raise InvalidRequestError("The CSV upload contains invalid null bytes.")

    try:
        dialect = _detect_csv_dialect(text)
        reader = csv.reader(io.StringIO(text, newline=""), dialect=dialect, strict=True)
        header = next(reader, None)
    except csv.Error as exc:
        raise InvalidRequestError("The CSV upload could not be parsed safely.") from exc
    if header is None or not header or not any(value.strip() for value in header):
        raise InvalidRequestError("The CSV upload must contain a non-empty header row.")
    if len(header) > policy.max_columns:
        raise InvalidRequestError("The uploaded database contains too many columns.")

    table_name = _safe_identifier(Path(filename).stem, fallback="data")
    column_names = _unique_identifiers(header, fallback="column")
    quoted_table = _quote_identifier(table_name)
    create_sql = "CREATE TABLE {} ({})".format(
        quoted_table,
        ", ".join(f"{_quote_identifier(column)} TEXT" for column in column_names),
    )
    placeholders = ", ".join("?" for _ in column_names)
    insert_sql = f"INSERT INTO {quoted_table} VALUES ({placeholders})"

    connection, deadline = _open_bounded_import_database(destination, policy)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(create_sql)
        record_count = 0
        try:
            for row in reader:
                if not row:
                    continue
                record_count += 1
                _check_record_budget(record_count, deadline=deadline, policy=policy)
                if len(row) > len(column_names):
                    raise InvalidRequestError("A CSV row contains more fields than the header row.")
                padded: list[str | None] = [*row]
                padded.extend(None for _ in range(len(column_names) - len(row)))
                connection.execute(insert_sql, padded)
        except csv.Error as exc:
            raise InvalidRequestError("The CSV upload could not be parsed safely.") from exc
        _check_database_size(connection, policy)
        connection.commit()
    except InvalidRequestError:
        connection.rollback()
        raise
    except (sqlite3.Error, OSError, OverflowError) as exc:
        connection.rollback()
        raise InvalidRequestError("The CSV upload could not be imported safely.") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        _close_import_connection(connection)


def _import_json(
    payload: bytes,
    destination: Path,
    *,
    filename: str,
    policy: SQLiteImportPolicy,
) -> None:
    text = _decode_utf8(payload, label="JSON")
    if "\x00" in text:
        raise InvalidRequestError("The JSON upload contains invalid null bytes.")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_json_object_without_duplicate_keys,
            parse_constant=_reject_nonstandard_json_number,
        )
        _validate_json_nesting(document)
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise InvalidRequestError("The JSON upload must contain valid bounded JSON.") from exc

    base_table_name = _safe_identifier(Path(filename).stem, fallback="data")
    raw_tables: list[tuple[str, Any]]
    if (
        isinstance(document, dict)
        and document
        and all(isinstance(value, list) for value in document.values())
    ):
        raw_tables = list(document.items())
    elif isinstance(document, dict) and not document:
        raise InvalidRequestError("The JSON upload contains no fields or records.")
    else:
        raw_tables = [(base_table_name, document)]

    if len(raw_tables) > policy.max_tables:
        raise InvalidRequestError("The uploaded database contains too many tables.")
    prepared_tables = [(name, _json_rows(value)) for name, value in raw_tables]
    total_records = sum(len(rows) for _, rows in prepared_tables)
    _check_record_budget(
        total_records,
        deadline=monotonic() + policy.timeout_seconds,
        policy=policy,
    )
    total_columns = sum(_json_column_count(rows) for _, rows in prepared_tables)
    if total_columns > policy.max_columns:
        raise InvalidRequestError("The uploaded database contains too many columns.")

    table_names = _unique_identifiers(
        [name for name, _ in prepared_tables],
        fallback="table",
    )
    connection, deadline = _open_bounded_import_database(destination, policy)
    try:
        connection.execute("BEGIN IMMEDIATE")
        scanned_records = 0
        for table_name, (_, rows) in zip(table_names, prepared_tables, strict=True):
            scanned_records += len(rows)
            _check_record_budget(scanned_records, deadline=deadline, policy=policy)
            _write_json_table(
                connection,
                table_name,
                rows,
                deadline=deadline,
                policy=policy,
            )
        connection.commit()
    except InvalidRequestError:
        connection.rollback()
        raise
    except (sqlite3.Error, OSError, OverflowError) as exc:
        connection.rollback()
        raise InvalidRequestError("The JSON upload could not be imported safely.") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        _close_import_connection(connection)


def _write_json_table(
    connection: sqlite3.Connection,
    table_name: str,
    rows: list[dict[str, Any]],
    *,
    deadline: float,
    policy: SQLiteImportPolicy,
) -> None:
    raw_column_names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for name in row:
            if name not in seen:
                seen.add(name)
                raw_column_names.append(name)
    if not raw_column_names:
        raw_column_names = ["value"]
        rows = [{"value": None} for _ in rows]

    column_names = _unique_identifiers(raw_column_names, fallback="column")
    column_mapping = dict(zip(raw_column_names, column_names, strict=True))
    declarations = {
        column_mapping[name]: _json_declared_type(row.get(name) for row in rows)
        for name in raw_column_names
    }
    quoted_table = _quote_identifier(table_name)
    connection.execute(
        "CREATE TABLE {} ({})".format(
            quoted_table,
            ", ".join(
                " ".join(part for part in (_quote_identifier(column), declarations[column]) if part)
                for column in column_names
            ),
        )
    )
    if not rows:
        return
    placeholders = ", ".join("?" for _ in column_names)
    insert_sql = f"INSERT INTO {quoted_table} VALUES ({placeholders})"
    for row in rows:
        if monotonic() >= deadline:
            raise InvalidRequestError("The structured-data import exceeded its time limit.")
        normalized = {
            column_mapping[name]: _sqlite_json_value(value) for name, value in row.items()
        }
        connection.execute(insert_sql, [normalized.get(column) for column in column_names])
    _check_database_size(connection, policy)


def _json_rows(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else [value]
    rows: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"value": item})
    return rows


def _json_column_count(rows: list[dict[str, Any]]) -> int:
    columns = {name for row in rows for name in row}
    return max(1, len(columns))


def _sqlite_json_value(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        if -(2**63) <= value <= 2**63 - 1:
            return value
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidRequestError("The JSON upload contains a non-finite number.")
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    raise InvalidRequestError("The JSON upload contains an unsupported value type.")


def _json_declared_type(values: Iterable[Any]) -> str:
    storage_classes: set[str] = set()
    for value in values:
        normalized = _sqlite_json_value(value)
        if normalized is None:
            continue
        if isinstance(normalized, int):
            storage_classes.add("integer")
        elif isinstance(normalized, float):
            storage_classes.add("real")
        else:
            storage_classes.add("text")
    if not storage_classes or (len(storage_classes) > 1 and "text" in storage_classes):
        return ""
    if storage_classes == {"integer"}:
        return "INTEGER"
    if storage_classes <= {"integer", "real"}:
        return "NUMERIC"
    return "TEXT"


def _json_object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonstandard_json_number(value: str) -> None:
    raise ValueError(f"non-standard JSON number: {value}")


def _validate_json_nesting(document: Any) -> None:
    stack: list[tuple[Any, int]] = [(document, 1)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_NESTING_DEPTH:
            raise ValueError("JSON nesting is too deep")
        if isinstance(value, dict):
            stack.extend((nested, depth + 1) for nested in value.values())
        elif isinstance(value, list):
            stack.extend((nested, depth + 1) for nested in value)


def _decode_utf8(payload: bytes, *, label: str) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError(f"{label} uploads must use UTF-8 encoding.") from exc


def _detect_csv_dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    sample = text[:65_536]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _safe_identifier(value: str, *, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    identifier = _UNSAFE_IDENTIFIER_CHARACTERS.sub("_", normalized).strip("_")
    if not identifier:
        identifier = fallback
    if identifier[0].isdigit():
        identifier = f"{fallback}_{identifier}"
    if identifier.casefold().startswith("sqlite_"):
        identifier = f"data_{identifier}"
    return identifier[:MAX_IDENTIFIER_CHARACTERS]


def _unique_identifiers(values: list[str], *, fallback: str) -> list[str]:
    identifiers: list[str] = []
    used: set[str] = set()
    for position, value in enumerate(values, start=1):
        base = _safe_identifier(str(value).strip(), fallback=f"{fallback}_{position}")
        candidate = base
        suffix = 2
        while candidate.casefold() in used:
            marker = f"_{suffix}"
            candidate = f"{base[: MAX_IDENTIFIER_CHARACTERS - len(marker)]}{marker}"
            suffix += 1
        used.add(candidate.casefold())
        identifiers.append(candidate)
    return identifiers


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _open_bounded_import_database(
    destination: Path,
    policy: SQLiteImportPolicy,
) -> tuple[sqlite3.Connection, float]:
    deadline = monotonic() + policy.timeout_seconds
    try:
        connection = sqlite3.connect(destination, timeout=policy.timeout_seconds)
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        max_pages = max(1, policy.max_database_bytes // page_size)
        connection.execute(f"PRAGMA max_page_count = {max_pages}")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.set_progress_handler(lambda: int(monotonic() >= deadline), 1_000)
        return connection, deadline
    except (sqlite3.Error, OSError) as exc:
        if "connection" in locals():
            connection.close()
        raise InvalidRequestError("The structured-data upload could not be imported.") from exc


def _close_import_connection(connection: sqlite3.Connection) -> None:
    connection.set_progress_handler(None, 0)
    connection.close()


def _check_record_budget(
    record_count: int,
    *,
    deadline: float,
    policy: SQLiteImportPolicy,
) -> None:
    if record_count > policy.max_records:
        raise InvalidRequestError(
            "The structured-data upload contains too many records.",
            details={"max_records": policy.max_records},
        )
    if monotonic() >= deadline:
        raise InvalidRequestError("The structured-data import exceeded its time limit.")


def _check_database_size(connection: sqlite3.Connection, policy: SQLiteImportPolicy) -> None:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    if page_count * page_size > policy.max_database_bytes:
        raise InvalidRequestError(
            "The imported database exceeds the configured storage limit.",
            details={"max_database_bytes": policy.max_database_bytes},
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
