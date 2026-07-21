"""Stable contracts for SQL AST validation, rewriting, and repair."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SQLViolationCode(StrEnum):
    """Safe reason codes emitted by the SQL security gate."""

    QUERY_TOO_LONG = "query_too_long"
    PARSE_FAILED = "parse_failed"
    MULTIPLE_STATEMENTS = "multiple_statements"
    DISALLOWED_STATEMENT = "disallowed_statement"
    WRITE_OPERATION = "write_operation"
    DDL_OPERATION = "ddl_operation"
    ADMINISTRATIVE_STATEMENT = "administrative_statement"
    SELECT_INTO = "select_into"
    UNBOUND_PARAMETER = "unbound_parameter"
    RECURSIVE_CTE = "recursive_cte"
    QUERY_COMPLEXITY = "query_complexity"
    CARTESIAN_JOIN = "cartesian_join"
    DISALLOWED_SCHEMA = "disallowed_schema"
    DISALLOWED_TABLE = "disallowed_table"
    DISALLOWED_COLUMN = "disallowed_column"
    AMBIGUOUS_COLUMN = "ambiguous_column"
    DISALLOWED_FUNCTION = "disallowed_function"
    DISALLOWED_CATALOG = "disallowed_catalog"
    DECLARED_SOURCE_MISMATCH = "declared_source_mismatch"


_SAFE_MESSAGES: dict[SQLViolationCode, str] = {
    SQLViolationCode.QUERY_TOO_LONG: "The SQL exceeds the configured length limit.",
    SQLViolationCode.PARSE_FAILED: "The SQL could not be parsed using the configured dialect.",
    SQLViolationCode.MULTIPLE_STATEMENTS: "Exactly one SQL statement is allowed.",
    SQLViolationCode.DISALLOWED_STATEMENT: "Only read-only analytical queries are allowed.",
    SQLViolationCode.WRITE_OPERATION: "Data modification statements are not allowed.",
    SQLViolationCode.DDL_OPERATION: "Schema modification statements are not allowed.",
    SQLViolationCode.ADMINISTRATIVE_STATEMENT: "Administrative SQL statements are not allowed.",
    SQLViolationCode.SELECT_INTO: "SELECT INTO is not allowed.",
    SQLViolationCode.UNBOUND_PARAMETER: "Unbound SQL parameters are not allowed.",
    SQLViolationCode.RECURSIVE_CTE: "Recursive CTEs are not allowed.",
    SQLViolationCode.QUERY_COMPLEXITY: (
        "The SQL exceeds the configured structural complexity limit."
    ),
    SQLViolationCode.CARTESIAN_JOIN: "Joins must have an explicit relationship condition.",
    SQLViolationCode.DISALLOWED_SCHEMA: "The SQL references a schema outside the allowlist.",
    SQLViolationCode.DISALLOWED_TABLE: "The SQL references a table outside the allowlist.",
    SQLViolationCode.DISALLOWED_COLUMN: "The SQL references an unavailable column.",
    SQLViolationCode.AMBIGUOUS_COLUMN: "The SQL contains an ambiguous or unresolved column.",
    SQLViolationCode.DISALLOWED_FUNCTION: "The SQL uses a function outside the allowlist.",
    SQLViolationCode.DISALLOWED_CATALOG: "System catalog access is not allowed.",
    SQLViolationCode.DECLARED_SOURCE_MISMATCH: (
        "Declared sources do not match the SQL syntax tree."
    ),
}


class SQLViolation(BaseModel):
    """One safe validation failure without raw SQL or parser details."""

    model_config = ConfigDict(frozen=True)

    code: SQLViolationCode
    message: str

    @classmethod
    def from_code(cls, code: SQLViolationCode) -> SQLViolation:
        return cls(code=code, message=_SAFE_MESSAGES[code])


class SQLValidationReport(BaseModel):
    """Complete result of parsing, validating, rewriting, and fingerprinting."""

    model_config = ConfigDict(frozen=True)

    safe: bool
    dialect: str
    executed_sql: str | None = None
    fingerprint: str | None = None
    tables: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    rules_passed: tuple[str, ...] = ()
    violations: tuple[SQLViolation, ...] = ()
    limit_applied: bool = False

    @model_validator(mode="after")
    def validate_report_consistency(self) -> SQLValidationReport:
        if self.safe:
            if self.violations or self.executed_sql is None or self.fingerprint is None:
                raise ValueError("safe report requires executable SQL and no violations")
        elif self.executed_sql is not None or not self.violations:
            raise ValueError("unsafe report requires violations and no executable SQL")
        return self


class SQLRepairAttempt(BaseModel):
    """One separately validated repaired SQL proposal."""

    model_config = ConfigDict(frozen=True)

    attempt: int = Field(ge=1)
    proposed_sql: str
    validation: SQLValidationReport


class SQLRepairOutcome(BaseModel):
    """Bounded repair result; successful SQL still comes from a full validation."""

    model_config = ConfigDict(frozen=True)

    repaired: bool
    final_validation: SQLValidationReport
    attempts: tuple[SQLRepairAttempt, ...]
