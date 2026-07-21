"""Strict contracts for versioned Tahap 7 evaluation and regression reports."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas.llm import LanguageCode, QueryStatus
from backend.schemas.sql_security import SQLViolationCode


class EvaluationCategory(StrEnum):
    """Required categories in the formal Chinook evaluation dataset."""

    FILTERING = "filtering"
    AGGREGATION = "aggregation"
    MULTI_TABLE_JOIN = "multi_table_join"
    TIME_ANALYSIS = "time_analysis"
    RANKING_TOP_N = "ranking_top_n"
    SUBQUERY = "subquery"
    AMBIGUITY = "ambiguity"
    UNSAFE = "unsafe"


class EvaluationSplit(StrEnum):
    """Development and holdout labels for later real-provider evaluation."""

    DEVELOPMENT = "development"
    HOLDOUT = "holdout"


class EvaluationCase(BaseModel):
    """One strict JSONL case without credentials or runtime result rows."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    case_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]*-\d{3}$")
    dataset_version: str = Field(min_length=1, max_length=100)
    split: EvaluationSplit
    category: EvaluationCategory
    language: LanguageCode
    question: str = Field(min_length=1, max_length=2_000)
    expected_status: QueryStatus
    expected_sql: str | None = Field(default=None, min_length=1, max_length=12_000)
    expected_columns: tuple[str, ...] = Field(default=(), max_length=100)
    expected_rows: tuple[tuple[Any, ...], ...] = Field(default=(), max_length=500)
    order_sensitive: bool = True
    numeric_tolerance: float = Field(default=0.0, ge=0.0, le=1_000.0)
    allowed_tables: tuple[str, ...] = Field(default=(), max_length=100)
    allowed_columns: tuple[str, ...] = Field(default=(), max_length=500)
    forbidden_tables: tuple[str, ...] = Field(default=(), max_length=100)
    expected_clarification_rule: str | None = Field(default=None, max_length=100)
    expected_violation_code: SQLViolationCode | None = None
    tags: tuple[str, ...] = Field(default=(), max_length=20)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_case_contract(self) -> Self:
        """Require category-specific expected evidence and consistent row shapes."""

        if len(set(self.allowed_tables)) != len(self.allowed_tables):
            raise ValueError("allowed_tables must not contain duplicates")
        if len(set(self.allowed_columns)) != len(self.allowed_columns):
            raise ValueError("allowed_columns must not contain duplicates")
        if any(len(row) != len(self.expected_columns) for row in self.expected_rows):
            raise ValueError("each expected row must match expected_columns")

        if self.category is EvaluationCategory.AMBIGUITY:
            if self.expected_status is not QueryStatus.CLARIFICATION_REQUIRED:
                raise ValueError("ambiguity cases must require clarification")
            if self.expected_clarification_rule is None or self.expected_sql is not None:
                raise ValueError("ambiguity cases require a rule and no SQL")
        elif self.category is EvaluationCategory.UNSAFE:
            if self.expected_status is not QueryStatus.BLOCKED:
                raise ValueError("unsafe cases must expect blocked status")
            if self.expected_sql is None or self.expected_violation_code is None:
                raise ValueError("unsafe cases require SQL and a violation code")
        else:
            if self.expected_status not in {QueryStatus.SUCCESS, QueryStatus.EMPTY_RESULT}:
                raise ValueError("analytical cases must expect a result status")
            if self.expected_sql is None or not self.expected_columns:
                raise ValueError("analytical cases require SQL and expected columns")
            if self.expected_status is QueryStatus.EMPTY_RESULT and self.expected_rows:
                raise ValueError("empty-result cases must not define rows")
        return self


class ResultComparison(BaseModel):
    """Detailed comparison outcome for one analytical case."""

    model_config = ConfigDict(frozen=True)

    matched: bool
    columns_match: bool
    row_count_match: bool
    rows_match: bool
    mismatch_reason: str | None = None


class EvaluationCaseResult(BaseModel):
    """Privacy-minimized evidence for one executed evaluation case."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    category: EvaluationCategory
    split: EvaluationSplit
    expected_status: QueryStatus
    actual_status: QueryStatus | None = None
    passed: bool
    structured_output_valid: bool
    sql_valid: bool | None = None
    execution_success: bool | None = None
    result_match: bool | None = None
    schema_hallucination: bool | None = None
    unsafe_blocked: bool | None = None
    false_blocked: bool | None = None
    clarification_correct: bool | None = None
    repair_attempts: int = Field(default=0, ge=0)
    repair_succeeded: bool | None = None
    latency_ms: float = Field(ge=0)
    error_codes: tuple[str, ...] = ()
    mismatch_reason: str | None = None


class EvaluationMetrics(BaseModel):
    """Aggregate rates with explicit denominators and nullable unsupported metrics."""

    model_config = ConfigDict(frozen=True)

    case_count: int = Field(ge=0)
    passed_case_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    structured_output_case_count: int = Field(ge=0)
    structured_output_valid_count: int = Field(ge=0)
    structured_output_validity_rate: float = Field(ge=0, le=1)
    analytical_case_count: int = Field(ge=0)
    valid_sql_count: int = Field(ge=0)
    valid_sql_rate: float = Field(ge=0, le=1)
    execution_success_count: int = Field(ge=0)
    execution_success_rate: float = Field(ge=0, le=1)
    execution_accuracy_count: int = Field(ge=0)
    execution_accuracy: float = Field(ge=0, le=1)
    schema_hallucination_count: int = Field(ge=0)
    schema_hallucination_rate: float = Field(ge=0, le=1)
    unsafe_case_count: int = Field(ge=0)
    unsafe_blocked_count: int = Field(ge=0)
    unsafe_blocking_rate: float = Field(ge=0, le=1)
    false_block_count: int = Field(ge=0)
    false_blocking_rate: float = Field(ge=0, le=1)
    ambiguity_case_count: int = Field(ge=0)
    correct_clarification_count: int = Field(ge=0)
    clarification_accuracy: float = Field(ge=0, le=1)
    returned_clarification_count: int = Field(ge=0)
    clarification_precision: float = Field(ge=0, le=1)
    repair_attempt_count: int = Field(ge=0)
    repair_rate: float = Field(ge=0, le=1)
    repair_success_rate: float | None = Field(default=None, ge=0, le=1)
    latency_p50_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)


class EvaluationProvenance(BaseModel):
    """Version and runtime identity required for comparable evaluation runs."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    started_at: str
    completed_at: str
    dataset_version: str
    dataset_sha256: str
    dataset_case_count: int = Field(ge=0)
    dataset_split_counts: dict[str, int]
    chinook_version: str
    chinook_sha256: str
    schema_hash: str
    prompt_version: str
    semantic_version: str
    semantic_content_hash: str
    provider: str
    model: str
    application_version: str
    git_commit: str
    git_dirty: bool
    python_version: str
    sqlglot_version: str
    runtime_configuration: dict[str, str | int | float | bool]
    network_calls: int = Field(ge=0)
    credentials_used: bool
    formal_real_model_quality_evaluation: bool


class EvaluationReport(BaseModel):
    """Machine-readable full run summary and privacy-minimized case evidence."""

    model_config = ConfigDict(frozen=True)

    report_version: str
    provenance: EvaluationProvenance
    category_counts: dict[str, int]
    metrics: EvaluationMetrics
    cases: tuple[EvaluationCaseResult, ...]
    failed_case_ids: tuple[str, ...]
    error_analysis: dict[str, tuple[str, ...]]
    gate_passed: bool
    gate_failures: tuple[str, ...]
    limitations: tuple[str, ...]


class RegressionThresholds(BaseModel):
    """Allowed degradation relative to a committed baseline."""

    model_config = ConfigDict(frozen=True)

    max_execution_accuracy_drop: float = Field(default=0.0, ge=0, le=1)
    max_valid_sql_rate_drop: float = Field(default=0.0, ge=0, le=1)
    max_clarification_accuracy_drop: float = Field(default=0.0, ge=0, le=1)
    max_false_blocking_rate_increase: float = Field(default=0.0, ge=0, le=1)
    max_latency_p95_increase_ratio: float = Field(default=0.5, ge=0)
    required_unsafe_blocking_rate: float = Field(default=1.0, ge=0, le=1)


class RegressionCheck(BaseModel):
    """One named baseline comparison with its measured delta."""

    model_config = ConfigDict(frozen=True)

    metric: str
    baseline: float
    current: float
    delta: float
    threshold: float
    passed: bool
    gate: bool


class RegressionReport(BaseModel):
    """Human- and machine-readable comparison against a pinned baseline."""

    model_config = ConfigDict(frozen=True)

    report_version: str
    baseline_run_id: str
    current_run_id: str
    comparable: bool
    comparison_notes: tuple[str, ...]
    thresholds: RegressionThresholds
    checks: tuple[RegressionCheck, ...]
    gate_passed: bool
    gate_failures: tuple[str, ...]
