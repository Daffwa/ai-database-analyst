"""Adversarial and false-blocking tests for the SQLGlot security gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.evaluation.mini_cases import MINI_EVALUATION_CASES
from backend.evaluation.security_cases import KNOWN_UNSAFE_SQL_CASES, SecurityEvaluationCase
from backend.evaluation.security_runner import run_security_evaluation
from backend.schemas.database import SchemaAllowlist
from backend.schemas.sql_security import SQLViolationCode
from backend.services.schema_service import load_schema_snapshot
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def validator() -> SQLSecurityService:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    return SQLSecurityService(SchemaAllowlist.from_snapshot(snapshot))


@pytest.mark.parametrize(
    "case",
    KNOWN_UNSAFE_SQL_CASES,
    ids=[case.case_id for case in KNOWN_UNSAFE_SQL_CASES],
)
def test_known_unsafe_sql_is_blocked(
    validator: SQLSecurityService,
    case: SecurityEvaluationCase,
) -> None:
    report = validator.validate(case.sql)

    assert report.safe is False
    assert report.executed_sql is None
    assert case.expected_code in {violation.code for violation in report.violations}
    assert all("/" not in violation.message for violation in report.violations)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT CustomerId FROM Customer",
        "select /* comment */ customerid from customer",
        "SELECT\n\tCustomerId\nFROM\tCustomer",
        'SELECT "CustomerId" FROM "Customer"',
        (
            "SELECT c.CustomerId, i.Total FROM Customer AS c JOIN Invoice AS i "
            "ON i.CustomerId = c.CustomerId"
        ),
        (
            "WITH totals AS (SELECT CustomerId, SUM(Total) AS amount FROM Invoice "
            "GROUP BY CustomerId) SELECT CustomerId, amount FROM totals"
        ),
        (
            "SELECT CustomerId FROM Customer WHERE CustomerId IN "
            "(SELECT CustomerId FROM Invoice WHERE Total > 10)"
        ),
        ("SELECT CustomerId FROM Customer UNION SELECT CustomerId FROM Invoice"),
        ("SELECT CustomerId, ROW_NUMBER() OVER (ORDER BY CustomerId) AS position FROM Customer"),
        "SELECT 'semicolon; inside literal' AS value",
    ],
)
def test_safe_read_only_ast_shapes_are_allowed(
    validator: SQLSecurityService,
    sql: str,
) -> None:
    report = validator.validate(sql)

    assert report.safe is True
    assert report.executed_sql is not None
    assert report.fingerprint is not None
    assert not report.violations


def test_all_twenty_baselines_have_zero_false_blocks(
    validator: SQLSecurityService,
) -> None:
    reports = [
        validator.validate(
            case.sql,
            declared_tables=case.tables,
            declared_columns=case.columns,
        )
        for case in MINI_EVALUATION_CASES
    ]

    assert len(reports) == 20
    assert all(report.safe for report in reports)


def test_security_evaluation_reports_blocking_and_false_blocking_rates(
    validator: SQLSecurityService,
) -> None:
    summary = run_security_evaluation(validator)

    assert summary.unsafe_case_count == 30
    assert summary.blocked_as_expected == 30
    assert summary.blocking_rate == 1.0
    assert summary.failed_unsafe_case_ids == ()
    assert summary.safe_baseline_count == 20
    assert summary.allowed_safe_baselines == 20
    assert summary.false_block_count == 0
    assert summary.false_blocking_rate == 0.0


def test_limit_is_added_lowered_or_preserved(validator: SQLSecurityService) -> None:
    added = validator.validate("SELECT CustomerId FROM Customer")
    lowered = validator.validate("SELECT CustomerId FROM Customer LIMIT 9999")
    preserved = validator.validate("SELECT CustomerId FROM Customer LIMIT 5")
    negative = validator.validate("SELECT CustomerId FROM Customer LIMIT -1")

    assert added.executed_sql == "SELECT CustomerId FROM Customer LIMIT 500"
    assert lowered.executed_sql == "SELECT CustomerId FROM Customer LIMIT 500"
    assert preserved.executed_sql == "SELECT CustomerId FROM Customer LIMIT 5"
    assert negative.executed_sql == "SELECT CustomerId FROM Customer LIMIT 500"
    assert added.limit_applied is lowered.limit_applied is negative.limit_applied is True
    assert preserved.limit_applied is False


def test_table_column_and_declared_source_checks_are_ast_derived(
    validator: SQLSecurityService,
) -> None:
    unknown_table = validator.validate("SELECT id FROM Secret")
    unknown_column = validator.validate("SELECT SecretValue FROM Customer")
    ambiguous = validator.validate(
        "SELECT CustomerId FROM Customer JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId"
    )
    mismatch = validator.validate(
        "SELECT Total FROM Invoice",
        declared_tables=("Customer",),
        declared_columns=("Customer.CustomerId",),
    )

    assert SQLViolationCode.DISALLOWED_TABLE in {
        violation.code for violation in unknown_table.violations
    }
    assert SQLViolationCode.DISALLOWED_COLUMN in {
        violation.code for violation in unknown_column.violations
    }
    assert SQLViolationCode.AMBIGUOUS_COLUMN in {
        violation.code for violation in ambiguous.violations
    }
    assert SQLViolationCode.DECLARED_SOURCE_MISMATCH in {
        violation.code for violation in mismatch.violations
    }


def test_fingerprint_redacts_literals_and_is_stable_across_formatting(
    validator: SQLSecurityService,
) -> None:
    first = validator.validate("SELECT CustomerId FROM Customer WHERE Country = 'Brazil'")
    second = validator.validate(
        " select customerid FROM customer WHERE country='Germany' -- hidden\n"
    )
    different = validator.validate("SELECT FirstName FROM Customer")

    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != different.fingerprint


def test_query_length_and_complexity_budgets_fail_closed(
    validator: SQLSecurityService,
) -> None:
    long_query = validator.validate("SELECT " + "1," * 7_000 + "1")
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    strict = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(max_joins=1),
    )
    complex_query = strict.validate(
        "SELECT ar.ArtistId FROM Artist AS ar "
        "JOIN Album AS al ON al.ArtistId = ar.ArtistId "
        "JOIN Track AS t ON t.AlbumId = al.AlbumId"
    )

    assert long_query.violations[0].code is SQLViolationCode.QUERY_TOO_LONG
    assert SQLViolationCode.QUERY_COMPLEXITY in {
        violation.code for violation in complex_query.violations
    }


def test_nested_recursive_cte_and_constant_true_join_are_blocked(
    validator: SQLSecurityService,
) -> None:
    nested_recursive = validator.validate(
        "SELECT n FROM (WITH RECURSIVE x(n) AS "
        "(SELECT 1 UNION ALL SELECT n + 1 FROM x) SELECT n FROM x)"
    )
    constant_join = validator.validate(
        "SELECT c.CustomerId FROM Customer AS c JOIN Invoice AS i ON 1 = 1"
    )

    assert SQLViolationCode.RECURSIVE_CTE in {
        violation.code for violation in nested_recursive.violations
    }
    assert SQLViolationCode.CARTESIAN_JOIN in {
        violation.code for violation in constant_join.violations
    }


def test_invalid_policy_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        SQLSecurityPolicy(max_rows=0)
    with pytest.raises(ValueError, match="must not be empty"):
        SQLSecurityPolicy(dialect=" ")
