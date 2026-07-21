"""Fail-closed SQLGlot AST security policy for the SQLite MVP."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, SqlglotError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope
from sqlglot.optimizer.simplify import simplify

from backend.schemas.database import SchemaAllowlist
from backend.schemas.sql_security import (
    SQLValidationReport,
    SQLViolation,
    SQLViolationCode,
)

DEFAULT_ALLOWED_FUNCTIONS = frozenset(
    {
        "abs",
        "and",
        "avg",
        "cast",
        "coalesce",
        "count",
        "cume_dist",
        "date",
        "datetime",
        "dense_rank",
        "first_value",
        "ifnull",
        "julianday",
        "lag",
        "last_value",
        "lead",
        "length",
        "lower",
        "ltrim",
        "max",
        "min",
        "nth_value",
        "ntile",
        "nullif",
        "percent_rank",
        "printf",
        "rank",
        "replace",
        "round",
        "row_number",
        "rtrim",
        "strftime",
        "substr",
        "substring",
        "sum",
        "time",
        "time_to_str",
        "total",
        "trim",
        "ts_or_ds_to_timestamp",
        "typeof",
        "unixepoch",
        "upper",
    }
)

DEFAULT_BLOCKED_FUNCTIONS = frozenset(
    {
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "load_extension",
        "lo_export",
        "lo_import",
        "pg_ls_dir",
        "pg_read_binary_file",
        "pg_read_file",
        "pg_sleep",
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "readfile",
        "writefile",
    }
)

BLOCKED_CATALOGS = frozenset(
    {
        "information_schema",
        "mysql",
        "performance_schema",
        "pg_catalog",
        "sqlite_master",
        "sqlite_schema",
        "sys",
    }
)


@dataclass(frozen=True, slots=True)
class SQLSecurityPolicy:
    """Validated budgets and allowlists used for every SQL attempt."""

    dialect: str = "sqlite"
    max_rows: int = 500
    max_query_characters: int = 12_000
    max_joins: int = 12
    max_subqueries: int = 12
    max_ctes: int = 8
    max_set_operations: int = 8
    allowed_schemas: frozenset[str] = frozenset({"main"})
    allowed_functions: frozenset[str] = DEFAULT_ALLOWED_FUNCTIONS
    blocked_functions: frozenset[str] = field(default_factory=lambda: DEFAULT_BLOCKED_FUNCTIONS)

    def __post_init__(self) -> None:
        budgets = (
            self.max_rows,
            self.max_query_characters,
            self.max_joins,
            self.max_subqueries,
            self.max_ctes,
            self.max_set_operations,
        )
        if min(budgets) <= 0:
            raise ValueError("SQL security budgets must be greater than zero")
        if not self.dialect.strip():
            raise ValueError("SQL dialect must not be empty")


class SQLSecurityService:
    """Parse, recursively validate, qualify, rewrite, and fingerprint one query."""

    def __init__(
        self,
        allowlist: SchemaAllowlist,
        *,
        policy: SQLSecurityPolicy | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._policy = policy or SQLSecurityPolicy()
        self._table_names = {table_name.casefold(): table_name for table_name in allowlist.tables}
        self._column_names = {
            table_name.casefold(): {column.casefold(): column for column in columns}
            for table_name, columns in allowlist.tables.items()
        }
        self._schema: dict[str, object] = {
            table_name: {column: "UNKNOWN" for column in columns}
            for table_name, columns in allowlist.tables.items()
        }

    def validate(
        self,
        sql: str,
        *,
        declared_tables: tuple[str, ...] = (),
        declared_columns: tuple[str, ...] = (),
    ) -> SQLValidationReport:
        normalized_sql = sql.strip()
        if not normalized_sql or len(normalized_sql) > self._policy.max_query_characters:
            code = (
                SQLViolationCode.PARSE_FAILED
                if not normalized_sql
                else SQLViolationCode.QUERY_TOO_LONG
            )
            return self._blocked(code)

        try:
            statements = sqlglot.parse(
                normalized_sql,
                read=self._policy.dialect,
                error_level=sqlglot.ErrorLevel.RAISE,
            )
        except (ParseError, SqlglotError, ValueError) as exc:
            return self._blocked(SQLViolationCode.PARSE_FAILED, cause=exc)

        if len(statements) != 1:
            return self._blocked(SQLViolationCode.MULTIPLE_STATEMENTS)
        expression = statements[0]
        if expression is None or not isinstance(expression, exp.Expression):
            return self._blocked(SQLViolationCode.PARSE_FAILED)

        violations: list[SQLViolationCode] = []
        if not isinstance(expression, exp.Query):
            _add_violation(violations, SQLViolationCode.DISALLOWED_STATEMENT)
        self._validate_forbidden_nodes(expression, violations)
        self._validate_structure(expression, violations)
        self._validate_functions(expression, violations)
        tables = self._validate_tables(expression, violations)
        columns = self._validate_columns(expression, violations)

        if declared_tables and {table.casefold() for table in declared_tables} != {
            table.casefold() for table in tables
        }:
            _add_violation(violations, SQLViolationCode.DECLARED_SOURCE_MISMATCH)
        if declared_columns and {column.casefold() for column in declared_columns} != {
            column.casefold() for column in columns
        }:
            _add_violation(violations, SQLViolationCode.DECLARED_SOURCE_MISMATCH)

        fingerprint = _fingerprint(expression, self._policy.dialect)
        if violations:
            return SQLValidationReport(
                safe=False,
                dialect=self._policy.dialect,
                fingerprint=fingerprint,
                tables=tables,
                columns=columns,
                violations=tuple(SQLViolation.from_code(code) for code in violations),
            )

        rewritten, limit_applied = _rewrite_limit(
            expression,
            max_rows=self._policy.max_rows,
        )
        executed_sql = rewritten.sql(
            dialect=self._policy.dialect,
            pretty=False,
            comments=False,
        )
        return SQLValidationReport(
            safe=True,
            dialect=self._policy.dialect,
            executed_sql=executed_sql,
            fingerprint=fingerprint,
            tables=tables,
            columns=columns,
            rules_passed=(
                "single_statement",
                "read_only_root",
                "recursive_ast",
                "schema_allowlist",
                "column_allowlist",
                "function_allowlist",
                "catalog_blocklist",
                "complexity_budget",
                "result_limit",
            ),
            limit_applied=limit_applied,
        )

    def _validate_forbidden_nodes(
        self,
        expression: exp.Expression,
        violations: list[SQLViolationCode],
    ) -> None:
        write_nodes = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.LoadData)
        ddl_nodes = (
            exp.Create,
            exp.Alter,
            exp.Drop,
            exp.TruncateTable,
            exp.Grant,
            exp.Revoke,
        )
        administrative_nodes = (
            exp.Command,
            exp.Transaction,
            exp.Commit,
            exp.Rollback,
            exp.Execute,
            exp.Copy,
            exp.Pragma,
            exp.Use,
            exp.Set,
            exp.Attach,
            exp.Detach,
            exp.Cache,
            exp.Uncache,
            exp.Show,
            exp.Describe,
            exp.Kill,
            exp.Declare,
            exp.Analyze,
            exp.Lock,
        )
        if any(expression.find(node_type) is not None for node_type in write_nodes):
            _add_violation(violations, SQLViolationCode.WRITE_OPERATION)
        if any(expression.find(node_type) is not None for node_type in ddl_nodes):
            _add_violation(violations, SQLViolationCode.DDL_OPERATION)
        if any(expression.find(node_type) is not None for node_type in administrative_nodes):
            _add_violation(violations, SQLViolationCode.ADMINISTRATIVE_STATEMENT)
        if expression.find(exp.Into) is not None:
            _add_violation(violations, SQLViolationCode.SELECT_INTO)
        if expression.find(exp.Placeholder) is not None:
            _add_violation(violations, SQLViolationCode.UNBOUND_PARAMETER)

    def _validate_structure(
        self,
        expression: exp.Expression,
        violations: list[SQLViolationCode],
    ) -> None:
        if any(with_clause.args.get("recursive") for with_clause in expression.find_all(exp.With)):
            _add_violation(violations, SQLViolationCode.RECURSIVE_CTE)

        counts = (
            (sum(1 for _ in expression.find_all(exp.Join)), self._policy.max_joins),
            (
                sum(1 for _ in expression.find_all(exp.Subquery)),
                self._policy.max_subqueries,
            ),
            (sum(1 for _ in expression.find_all(exp.CTE)), self._policy.max_ctes),
            (
                sum(1 for _ in expression.find_all(exp.SetOperation)),
                self._policy.max_set_operations,
            ),
        )
        if any(actual > maximum for actual, maximum in counts):
            _add_violation(violations, SQLViolationCode.QUERY_COMPLEXITY)

        for join in expression.find_all(exp.Join):
            kind = str(join.args.get("kind") or "").casefold()
            condition = join.args.get("on")
            has_condition = condition is not None or join.args.get("using") is not None
            simplified_condition = (
                simplify(condition.copy(), dialect=self._policy.dialect) if condition else None
            )
            condition_is_true = (
                isinstance(simplified_condition, exp.Boolean) and simplified_condition.this is True
            )
            if kind == "cross" or not has_condition or condition_is_true:
                _add_violation(violations, SQLViolationCode.CARTESIAN_JOIN)

    def _validate_functions(
        self,
        expression: exp.Expression,
        violations: list[SQLViolationCode],
    ) -> None:
        blocked = {
            name.casefold()
            for name in (*self._policy.blocked_functions, *DEFAULT_BLOCKED_FUNCTIONS)
        }
        allowed = {name.casefold() for name in self._policy.allowed_functions}
        for function in expression.find_all(exp.Func):
            names = {function.sql_name().casefold()}
            if isinstance(function, exp.Anonymous):
                names.add(function.name.casefold())
            names.discard("")
            if names & blocked or not names & allowed:
                _add_violation(violations, SQLViolationCode.DISALLOWED_FUNCTION)

    def _validate_tables(
        self,
        expression: exp.Expression,
        violations: list[SQLViolationCode],
    ) -> tuple[str, ...]:
        tables: set[str] = set()
        for scope in traverse_scope(expression):
            for _, source in scope.selected_sources.values():
                if not isinstance(source, exp.Table):
                    continue
                table_name = source.name
                schema_name = source.db
                catalog_name = source.catalog
                folded_parts = {
                    part.casefold() for part in (table_name, schema_name, catalog_name) if part
                }
                if folded_parts & BLOCKED_CATALOGS:
                    _add_violation(violations, SQLViolationCode.DISALLOWED_CATALOG)
                    continue
                if schema_name and schema_name.casefold() not in self._policy.allowed_schemas:
                    _add_violation(violations, SQLViolationCode.DISALLOWED_SCHEMA)
                    continue
                if catalog_name:
                    _add_violation(violations, SQLViolationCode.DISALLOWED_SCHEMA)
                    continue
                canonical = self._table_names.get(table_name.casefold())
                if canonical is None:
                    _add_violation(violations, SQLViolationCode.DISALLOWED_TABLE)
                else:
                    tables.add(canonical)
        return tuple(sorted(tables, key=str.casefold))

    def _validate_columns(
        self,
        expression: exp.Expression,
        violations: list[SQLViolationCode],
    ) -> tuple[str, ...]:
        has_ambiguous_column = self._has_ambiguous_unqualified_column(expression)
        if has_ambiguous_column:
            _add_violation(violations, SQLViolationCode.AMBIGUOUS_COLUMN)
        try:
            qualified = qualify(
                expression.copy(),
                dialect=self._policy.dialect,
                schema=self._schema,
                quote_identifiers=False,
                identify=False,
                validate_qualify_columns=True,
            )
        except OptimizeError as exc:
            code = (
                SQLViolationCode.AMBIGUOUS_COLUMN
                if has_ambiguous_column or "ambiguous" in str(exc).casefold()
                else SQLViolationCode.DISALLOWED_COLUMN
            )
            _add_violation(violations, code)
            return ()
        except (SqlglotError, ValueError, TypeError):
            _add_violation(violations, SQLViolationCode.DISALLOWED_COLUMN)
            return ()

        columns: set[str] = set()
        for scope in traverse_scope(qualified):
            columns.update(self._physical_columns(scope, violations))
        return tuple(sorted(columns, key=str.casefold))

    def _has_ambiguous_unqualified_column(self, expression: exp.Expression) -> bool:
        for scope in traverse_scope(expression):
            physical_tables = [
                source
                for source in scope.sources.values()
                if isinstance(source, exp.Table) and source.name.casefold() in self._column_names
            ]
            for column in scope.columns:
                if column.table:
                    continue
                matches = {
                    table.name.casefold()
                    for table in physical_tables
                    if column.name.casefold() in self._column_names[table.name.casefold()]
                }
                if len(matches) > 1:
                    return True
        return False

    def _physical_columns(
        self,
        scope: Scope,
        violations: list[SQLViolationCode],
    ) -> set[str]:
        columns: set[str] = set()
        for column in scope.columns:
            if not column.table:
                continue
            source = scope.sources.get(column.table)
            if isinstance(source, Scope):
                continue
            if not isinstance(source, exp.Table):
                _add_violation(violations, SQLViolationCode.AMBIGUOUS_COLUMN)
                continue
            canonical_table = self._table_names.get(source.name.casefold())
            if canonical_table is None:
                continue
            canonical_column = self._column_names[canonical_table.casefold()].get(
                column.name.casefold()
            )
            if canonical_column is None:
                _add_violation(violations, SQLViolationCode.DISALLOWED_COLUMN)
                continue
            columns.add(f"{canonical_table}.{canonical_column}")
        return columns

    def _blocked(
        self,
        code: SQLViolationCode,
        *,
        cause: Exception | None = None,
    ) -> SQLValidationReport:
        _ = cause
        return SQLValidationReport(
            safe=False,
            dialect=self._policy.dialect,
            violations=(SQLViolation.from_code(code),),
        )


def _add_violation(
    violations: list[SQLViolationCode],
    code: SQLViolationCode,
) -> None:
    if code not in violations:
        violations.append(code)


def _rewrite_limit(expression: exp.Expression, *, max_rows: int) -> tuple[exp.Expression, bool]:
    rewritten = expression.copy()
    limit = rewritten.args.get("limit")
    if isinstance(limit, exp.Limit):
        value = limit.expression
        if isinstance(value, exp.Literal) and value.is_int:
            integer = int(value.this)
            if 0 <= integer <= max_rows:
                return rewritten, False
    if not isinstance(rewritten, exp.Query):
        return rewritten, False
    return rewritten.limit(max_rows, copy=False), True


def _fingerprint(expression: exp.Expression, dialect: str) -> str:
    def redact_literals(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Literal):
            return exp.Placeholder()
        return node

    redacted = expression.copy().transform(redact_literals)
    canonical = redacted.sql(
        dialect=dialect,
        pretty=False,
        comments=False,
        normalize=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
