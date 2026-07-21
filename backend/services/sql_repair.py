"""Bounded SQL repair coordination that re-runs the complete security gate."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.schemas.sql_security import (
    SQLRepairAttempt,
    SQLRepairOutcome,
    SQLValidationReport,
    SQLViolationCode,
)
from backend.services.sql_security import SQLSecurityService

RepairCallback = Callable[[int, tuple[SQLViolationCode, ...]], Awaitable[str]]

REPAIRABLE_CODES = frozenset(
    {
        SQLViolationCode.PARSE_FAILED,
        SQLViolationCode.DISALLOWED_COLUMN,
        SQLViolationCode.AMBIGUOUS_COLUMN,
        SQLViolationCode.DECLARED_SOURCE_MISMATCH,
    }
)


class SQLRepairCoordinator:
    """Retry only non-policy syntax/schema failures and validate every attempt."""

    def __init__(
        self,
        validator: SQLSecurityService,
        *,
        max_attempts: int = 2,
    ) -> None:
        if not 0 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between zero and five")
        self._validator = validator
        self._max_attempts = max_attempts

    async def repair(
        self,
        initial_validation: SQLValidationReport,
        callback: RepairCallback,
        *,
        declared_tables: tuple[str, ...] = (),
        declared_columns: tuple[str, ...] = (),
    ) -> SQLRepairOutcome:
        if initial_validation.safe:
            return SQLRepairOutcome(
                repaired=False,
                final_validation=initial_validation,
                attempts=(),
            )
        if not self._is_repairable(initial_validation) or self._max_attempts == 0:
            return SQLRepairOutcome(
                repaired=False,
                final_validation=initial_validation,
                attempts=(),
            )

        attempts: list[SQLRepairAttempt] = []
        validation = initial_validation
        for attempt_number in range(1, self._max_attempts + 1):
            codes = tuple(violation.code for violation in validation.violations)
            candidate = await callback(attempt_number, codes)
            validation = self._validator.validate(
                candidate,
                declared_tables=declared_tables,
                declared_columns=declared_columns,
            )
            attempts.append(
                SQLRepairAttempt(
                    attempt=attempt_number,
                    proposed_sql=candidate,
                    validation=validation,
                )
            )
            if validation.safe:
                return SQLRepairOutcome(
                    repaired=True,
                    final_validation=validation,
                    attempts=tuple(attempts),
                )
            if not self._is_repairable(validation):
                break

        return SQLRepairOutcome(
            repaired=False,
            final_validation=validation,
            attempts=tuple(attempts),
        )

    @staticmethod
    def _is_repairable(validation: SQLValidationReport) -> bool:
        return bool(validation.violations) and all(
            violation.code in REPAIRABLE_CODES for violation in validation.violations
        )
