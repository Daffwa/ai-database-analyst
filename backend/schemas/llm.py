"""Provider-neutral contracts for structured text-to-SQL generation."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas.database import QueryResult
from backend.schemas.result import ChartSpec, NumericEvidence, ResultPresentation, UXState
from backend.schemas.sql_security import SQLValidationReport


class LLMIntent(StrEnum):
    """Supported structured intents for the Tahap 3 generation boundary."""

    ANALYSIS = "analysis"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


class LanguageCode(StrEnum):
    """Languages accepted by the MVP question contract."""

    INDONESIAN = "id"
    ENGLISH = "en"


class StructuredSQLProposal(BaseModel):
    """Strict model output contract; SQL remains untrusted after validation."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    intent: LLMIntent
    language: LanguageCode
    needs_clarification: bool
    clarification_question: str | None = Field(default=None, min_length=1, max_length=500)
    assumptions: tuple[str, ...] = Field(default=(), max_length=10)
    sql: str | None = Field(default=None, min_length=1, max_length=12_000)
    tables: tuple[str, ...] = Field(default=(), max_length=100)
    columns: tuple[str, ...] = Field(default=(), max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_intent_contract(self) -> Self:
        """Make intent-dependent fields internally consistent."""

        if len(set(self.tables)) != len(self.tables):
            raise ValueError("tables must not contain duplicates")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must not contain duplicates")
        if any(not assumption for assumption in self.assumptions):
            raise ValueError("assumptions must not contain empty values")

        if self.intent is LLMIntent.ANALYSIS:
            if self.needs_clarification or self.clarification_question is not None:
                raise ValueError("analysis must not request clarification")
            if self.sql is None:
                raise ValueError("analysis requires non-empty SQL")
        elif self.intent is LLMIntent.CLARIFICATION:
            if not self.needs_clarification or self.clarification_question is None:
                raise ValueError("clarification requires a question")
            if self.sql is not None or self.tables or self.columns:
                raise ValueError("clarification must not propose SQL or sources")
        else:
            if self.needs_clarification or self.clarification_question is not None:
                raise ValueError("unsupported intent must not request clarification")
            if self.sql is not None or self.tables or self.columns:
                raise ValueError("unsupported intent must not propose SQL or sources")
        return self


class PromptPackage(BaseModel):
    """Versioned prompt material sent through an adapter."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    prompt_version: str
    schema_hash: str
    included_tables: tuple[str, ...]
    schema_context_truncated: bool
    semantic_version: str | None = None
    semantic_context_hash: str | None = None
    semantic_context_truncated: bool = False
    verified_query_ids: tuple[str, ...] = ()
    system_prompt: str
    user_prompt: str


class AdapterRequest(BaseModel):
    """Minimum provider-neutral request passed to an LLM adapter."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    question: str
    system_prompt: str
    user_prompt: str


class PipelineStage(StrEnum):
    """Observable generation, security, and execution stages."""

    REQUEST_VALIDATED = "request_validated"
    REQUEST_ID_ASSIGNED = "request_id_assigned"
    SCHEMA_CONTEXT_LOADED = "schema_context_loaded"
    SEMANTIC_CONTEXT_LOADED = "semantic_context_loaded"
    VERIFIED_EXAMPLES_RETRIEVED = "verified_examples_retrieved"
    AMBIGUITY_CHECKED = "ambiguity_checked"
    PROMPT_BUILT = "prompt_built"
    LLM_INVOKED = "llm_invoked"
    OUTPUT_VALIDATED = "output_validated"
    AWAITING_SECURITY_VALIDATION = "awaiting_security_validation"
    SECURITY_VALIDATED = "security_validated"
    SECURITY_BLOCKED = "security_blocked"
    QUERY_EXECUTED = "query_executed"
    TRUSTED_DEMO_EXECUTED = "trusted_demo_executed"
    RESULT_NORMALIZED = "result_normalized"
    CHART_SELECTED = "chart_selected"
    RESULT_SUMMARIZED = "result_summarized"
    HISTORY_RECORDED = "history_recorded"
    COMPLETED = "completed"


class PipelineEvent(BaseModel):
    """One completed orchestration stage with optional measured latency."""

    model_config = ConfigDict(frozen=True)

    stage: PipelineStage
    latency_ms: float | None = Field(default=None, ge=0)


class QueryStatus(StrEnum):
    """Public states across generation, security validation, and execution."""

    GENERATED_PENDING_SECURITY = "generated_pending_security"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    TRUSTED_DEMO_SUCCESS = "trusted_demo_success"
    SUCCESS = "success"
    EMPTY_RESULT = "empty_result"
    BLOCKED = "blocked"


class GenerationResult(BaseModel):
    """Validated proposal plus provider and prompt provenance."""

    model_config = ConfigDict(frozen=True)

    proposal: StructuredSQLProposal
    prompt: PromptPackage
    provider: str
    model: str
    llm_latency_ms: float = Field(ge=0)


class QueryResponse(BaseModel):
    """Auditable response with generated and executed SQL separated."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    status: QueryStatus
    language: LanguageCode
    generated_sql: str | None
    executed_sql: str | None = None
    result: QueryResult | None = None
    validation: SQLValidationReport | None = None
    assumptions: tuple[str, ...]
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
    clarification_question: str | None
    prompt_version: str
    schema_hash: str
    semantic_version: str | None = None
    semantic_context_hash: str | None = None
    matched_term_ids: tuple[str, ...] = ()
    matched_metric_ids: tuple[str, ...] = ()
    verified_query_ids: tuple[str, ...] = ()
    provider: str
    model: str
    llm_latency_ms: float = Field(ge=0)
    database_latency_ms: float | None = Field(default=None, ge=0)
    pipeline: tuple[PipelineEvent, ...]
    warnings: tuple[str, ...]
    presentation: ResultPresentation | None = None
    chart: ChartSpec | None = None
    explanation: str | None = None
    summary_evidence: tuple[NumericEvidence, ...] = ()
    ui_state: UXState | None = None
