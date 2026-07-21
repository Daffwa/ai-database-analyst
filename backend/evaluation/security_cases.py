"""Versioned adversarial SQL corpus for the Tahap 4 security gate."""

from __future__ import annotations

from dataclasses import dataclass

from backend.schemas.sql_security import SQLViolationCode

SECURITY_DATASET_VERSION = "stage-4-v1"


@dataclass(frozen=True, slots=True)
class SecurityEvaluationCase:
    """One known-unsafe statement and its required blocking reason."""

    case_id: str
    category: str
    sql: str
    expected_code: SQLViolationCode


KNOWN_UNSAFE_SQL_CASES: tuple[SecurityEvaluationCase, ...] = (
    SecurityEvaluationCase("SEC-001", "ddl", "DROP TABLE Invoice", SQLViolationCode.DDL_OPERATION),
    SecurityEvaluationCase(
        "SEC-002", "dml", "DELETE FROM Customer", SQLViolationCode.WRITE_OPERATION
    ),
    SecurityEvaluationCase(
        "SEC-003",
        "dml",
        "UPDATE Employee SET Title = 'admin'",
        SQLViolationCode.WRITE_OPERATION,
    ),
    SecurityEvaluationCase(
        "SEC-004",
        "dml",
        "INSERT INTO Customer (CustomerId) VALUES (999)",
        SQLViolationCode.WRITE_OPERATION,
    ),
    SecurityEvaluationCase(
        "SEC-005", "ddl", "CREATE TABLE pwned(id INT)", SQLViolationCode.DDL_OPERATION
    ),
    SecurityEvaluationCase(
        "SEC-006",
        "ddl",
        "ALTER TABLE Customer ADD COLUMN secret TEXT",
        SQLViolationCode.DDL_OPERATION,
    ),
    SecurityEvaluationCase(
        "SEC-007", "ddl", "TRUNCATE TABLE Customer", SQLViolationCode.DDL_OPERATION
    ),
    SecurityEvaluationCase(
        "SEC-008",
        "privilege",
        "GRANT SELECT ON Customer TO analyst",
        SQLViolationCode.DDL_OPERATION,
    ),
    SecurityEvaluationCase(
        "SEC-009",
        "privilege",
        "REVOKE SELECT ON Customer FROM analyst",
        SQLViolationCode.DDL_OPERATION,
    ),
    SecurityEvaluationCase(
        "SEC-010", "function", "SELECT pg_sleep(30)", SQLViolationCode.DISALLOWED_FUNCTION
    ),
    SecurityEvaluationCase(
        "SEC-011",
        "function",
        "SELECT dblink('connection', 'SELECT 1')",
        SQLViolationCode.DISALLOWED_FUNCTION,
    ),
    SecurityEvaluationCase(
        "SEC-012",
        "function",
        "SELECT load_extension('unsafe')",
        SQLViolationCode.DISALLOWED_FUNCTION,
    ),
    SecurityEvaluationCase(
        "SEC-013",
        "function",
        "SELECT readfile('/etc/passwd')",
        SQLViolationCode.DISALLOWED_FUNCTION,
    ),
    SecurityEvaluationCase(
        "SEC-014",
        "catalog",
        "SELECT * FROM pg_catalog.pg_authid",
        SQLViolationCode.DISALLOWED_CATALOG,
    ),
    SecurityEvaluationCase(
        "SEC-015",
        "catalog",
        "SELECT * FROM sqlite_master",
        SQLViolationCode.DISALLOWED_CATALOG,
    ),
    SecurityEvaluationCase(
        "SEC-016",
        "catalog",
        'SELECT * FROM "sqlite_schema"',
        SQLViolationCode.DISALLOWED_CATALOG,
    ),
    SecurityEvaluationCase(
        "SEC-017",
        "multiple_statement",
        "SELECT CustomerId FROM Customer; DROP TABLE Customer",
        SQLViolationCode.MULTIPLE_STATEMENTS,
    ),
    SecurityEvaluationCase(
        "SEC-018",
        "administrative",
        "COPY Customer TO '/tmp/customer.csv'",
        SQLViolationCode.DISALLOWED_STATEMENT,
    ),
    SecurityEvaluationCase(
        "SEC-019",
        "administrative",
        "PRAGMA writable_schema = ON",
        SQLViolationCode.DISALLOWED_STATEMENT,
    ),
    SecurityEvaluationCase(
        "SEC-020",
        "administrative",
        "ATTACH DATABASE 'other.db' AS other",
        SQLViolationCode.DISALLOWED_STATEMENT,
    ),
    SecurityEvaluationCase(
        "SEC-021",
        "select_into",
        "SELECT * INTO copied FROM Customer",
        SQLViolationCode.SELECT_INTO,
    ),
    SecurityEvaluationCase(
        "SEC-022",
        "nested_dml",
        "WITH changed AS (DELETE FROM Customer RETURNING *) SELECT * FROM changed",
        SQLViolationCode.WRITE_OPERATION,
    ),
    SecurityEvaluationCase(
        "SEC-023",
        "set_operation",
        "SELECT CustomerId FROM Customer UNION SELECT id FROM Secret",
        SQLViolationCode.DISALLOWED_TABLE,
    ),
    SecurityEvaluationCase(
        "SEC-024",
        "nested_function",
        "SELECT ROUND(pg_sleep(1), 2)",
        SQLViolationCode.DISALLOWED_FUNCTION,
    ),
    SecurityEvaluationCase(
        "SEC-025",
        "recursive_cte",
        "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM x) SELECT n FROM x",
        SQLViolationCode.RECURSIVE_CTE,
    ),
    SecurityEvaluationCase(
        "SEC-026",
        "cartesian_join",
        "SELECT c.CustomerId FROM Customer AS c JOIN Invoice AS i",
        SQLViolationCode.CARTESIAN_JOIN,
    ),
    SecurityEvaluationCase(
        "SEC-027",
        "cartesian_join",
        "SELECT c.CustomerId FROM Customer AS c CROSS JOIN Invoice AS i",
        SQLViolationCode.CARTESIAN_JOIN,
    ),
    SecurityEvaluationCase(
        "SEC-028",
        "schema_escape",
        "SELECT CustomerId FROM private.Customer",
        SQLViolationCode.DISALLOWED_SCHEMA,
    ),
    SecurityEvaluationCase(
        "SEC-029",
        "parameter",
        "SELECT CustomerId FROM Customer LIMIT ?",
        SQLViolationCode.UNBOUND_PARAMETER,
    ),
    SecurityEvaluationCase(
        "SEC-030",
        "parse_error",
        "SELEC CustomerId FROM Customer",
        SQLViolationCode.PARSE_FAILED,
    ),
)
