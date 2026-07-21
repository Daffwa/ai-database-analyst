"""Strict versioned HTTP contracts for the Tahap 8 FastAPI boundary."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.schemas.result import FeedbackRating, HistoryEntry


class StrictAPIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class APIQueryRequest(StrictAPIModel):
    question: str = Field(min_length=1, max_length=2_000)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class APIFeedbackRequest(StrictAPIModel):
    request_id: str = Field(min_length=1, max_length=100)
    rating: FeedbackRating


class HealthResponse(StrictAPIModel):
    status: str = Field(pattern=r"^(healthy|degraded)$")
    api_version: str


class HistoryResponse(StrictAPIModel):
    items: tuple[HistoryEntry, ...]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class APIErrorResponse(StrictAPIModel):
    error_code: str
    message: str
    request_id: str


class EvaluationBaselineResponse(StrictAPIModel):
    dataset_version: str
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int = Field(ge=0)
    passed_case_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    execution_accuracy: float = Field(ge=0.0, le=1.0)
    unsafe_blocking_rate: float = Field(ge=0.0, le=1.0)
    gate_passed: bool

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.passed_case_count > self.case_count:
            raise ValueError("passed count cannot exceed case count")
        return self


class OperationalMetricsResponse(StrictAPIModel):
    """Privacy-safe process counters for protected operational diagnosis."""

    http_requests_total: int = Field(ge=0)
    analytics_requests_total: int = Field(ge=0)
    uptime_seconds: float = Field(ge=0)
    http_requests_per_second: float = Field(ge=0)
    success_total: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    blocked_total: int = Field(ge=0)
    blocked_rate: float = Field(ge=0, le=1)
    clarification_total: int = Field(ge=0)
    clarification_rate: float = Field(ge=0, le=1)
    timeout_total: int = Field(ge=0)
    timeout_rate: float = Field(ge=0, le=1)
    repair_attempts_total: int = Field(ge=0)
    repair_rate: float = Field(ge=0)
    error_total: int = Field(ge=0)
    average_latency_ms: float | None = Field(default=None, ge=0)
    max_latency_ms: float | None = Field(default=None, ge=0)
    status_counts: dict[str, int]
    input_tokens_total: int | None = Field(default=None, ge=0)
    output_tokens_total: int | None = Field(default=None, ge=0)
