"""Deterministic blocking and false-blocking evaluation for Tahap 4."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.evaluation.mini_cases import MINI_EVALUATION_CASES
from backend.evaluation.security_cases import (
    KNOWN_UNSAFE_SQL_CASES,
    SECURITY_DATASET_VERSION,
)
from backend.services.sql_security import SQLSecurityService


class SecurityEvaluationSummary(BaseModel):
    """Shareable counts and rates from one fixed security evaluation run."""

    model_config = ConfigDict(frozen=True)

    dataset_version: str
    unsafe_case_count: int = Field(ge=0)
    blocked_as_expected: int = Field(ge=0)
    blocking_rate: float = Field(ge=0, le=1)
    failed_unsafe_case_ids: tuple[str, ...]
    safe_baseline_count: int = Field(ge=0)
    allowed_safe_baselines: int = Field(ge=0)
    false_block_count: int = Field(ge=0)
    false_blocking_rate: float = Field(ge=0, le=1)
    false_blocked_case_ids: tuple[str, ...]


def run_security_evaluation(
    validator: SQLSecurityService,
) -> SecurityEvaluationSummary:
    """Evaluate known attacks and the 20 previously accepted SQL baselines."""

    failed_unsafe: list[str] = []
    for unsafe_case in KNOWN_UNSAFE_SQL_CASES:
        report = validator.validate(unsafe_case.sql)
        codes = {violation.code for violation in report.violations}
        if report.safe or unsafe_case.expected_code not in codes:
            failed_unsafe.append(unsafe_case.case_id)

    false_blocked: list[str] = []
    for safe_case in MINI_EVALUATION_CASES:
        report = validator.validate(
            safe_case.sql,
            declared_tables=safe_case.tables,
            declared_columns=safe_case.columns,
        )
        if not report.safe:
            false_blocked.append(safe_case.case_id)

    unsafe_count = len(KNOWN_UNSAFE_SQL_CASES)
    safe_count = len(MINI_EVALUATION_CASES)
    blocked = unsafe_count - len(failed_unsafe)
    allowed = safe_count - len(false_blocked)
    return SecurityEvaluationSummary(
        dataset_version=SECURITY_DATASET_VERSION,
        unsafe_case_count=unsafe_count,
        blocked_as_expected=blocked,
        blocking_rate=blocked / unsafe_count if unsafe_count else 1.0,
        failed_unsafe_case_ids=tuple(failed_unsafe),
        safe_baseline_count=safe_count,
        allowed_safe_baselines=allowed,
        false_block_count=len(false_blocked),
        false_blocking_rate=len(false_blocked) / safe_count if safe_count else 0.0,
        false_blocked_case_ids=tuple(false_blocked),
    )
