"""Tests proving repaired SQL cannot bypass the complete validator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.schemas.database import SchemaAllowlist
from backend.schemas.sql_security import SQLViolationCode
from backend.services.schema_service import load_schema_snapshot
from backend.services.sql_repair import SQLRepairCoordinator
from backend.services.sql_security import SQLSecurityService

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def validator() -> SQLSecurityService:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    return SQLSecurityService(SchemaAllowlist.from_snapshot(snapshot))


def test_repairable_parse_failure_can_be_repaired_only_after_full_validation(
    validator: SQLSecurityService,
) -> None:
    initial = validator.validate("SELEC CustomerId FROM Customer")
    observed_codes: list[tuple[SQLViolationCode, ...]] = []

    async def repair(attempt: int, codes: tuple[SQLViolationCode, ...]) -> str:
        observed_codes.append(codes)
        return "SELECT CustomerId FROM Customer"

    outcome = asyncio.run(
        SQLRepairCoordinator(validator).repair(
            initial,
            repair,
            declared_tables=("Customer",),
            declared_columns=("Customer.CustomerId",),
        )
    )

    assert outcome.repaired is True
    assert outcome.final_validation.safe is True
    assert outcome.final_validation.executed_sql == ("SELECT CustomerId FROM Customer LIMIT 500")
    assert len(outcome.attempts) == 1
    assert observed_codes == [(SQLViolationCode.PARSE_FAILED,)]


def test_security_violation_is_never_sent_to_repair_callback(
    validator: SQLSecurityService,
) -> None:
    initial = validator.validate("DELETE FROM Customer")
    called = False

    async def forbidden_callback(
        attempt: int,
        codes: tuple[SQLViolationCode, ...],
    ) -> str:
        nonlocal called
        called = True
        return "SELECT CustomerId FROM Customer"

    outcome = asyncio.run(SQLRepairCoordinator(validator).repair(initial, forbidden_callback))

    assert outcome.repaired is False
    assert outcome.attempts == ()
    assert called is False


def test_repaired_write_is_revalidated_blocked_and_not_retried(
    validator: SQLSecurityService,
) -> None:
    initial = validator.validate("SELEC CustomerId FROM Customer")

    async def malicious_repair(
        attempt: int,
        codes: tuple[SQLViolationCode, ...],
    ) -> str:
        return "UPDATE Customer SET FirstName = 'changed'"

    outcome = asyncio.run(SQLRepairCoordinator(validator).repair(initial, malicious_repair))

    assert outcome.repaired is False
    assert len(outcome.attempts) == 1
    assert SQLViolationCode.WRITE_OPERATION in {
        violation.code for violation in outcome.final_validation.violations
    }


def test_repair_attempts_are_bounded_and_safe_input_needs_no_repair(
    validator: SQLSecurityService,
) -> None:
    invalid = validator.validate("SELEC CustomerId FROM Customer")
    attempts = 0

    async def still_invalid(
        attempt: int,
        codes: tuple[SQLViolationCode, ...],
    ) -> str:
        nonlocal attempts
        attempts += 1
        return "SELECT ("

    exhausted = asyncio.run(
        SQLRepairCoordinator(validator, max_attempts=2).repair(invalid, still_invalid)
    )
    safe = validator.validate("SELECT CustomerId FROM Customer")
    unchanged = asyncio.run(SQLRepairCoordinator(validator).repair(safe, still_invalid))

    assert exhausted.repaired is False
    assert len(exhausted.attempts) == 2
    assert attempts == 2
    assert unchanged.final_validation == safe
    with pytest.raises(ValueError, match="between zero and five"):
        SQLRepairCoordinator(validator, max_attempts=6)
