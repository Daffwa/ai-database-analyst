"""Strict public and internal-safe contracts for the bounded analytics agent."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas.llm import LanguageCode
from backend.schemas.result import ChartSpec, ResultPresentation


class StrictAgentModel(BaseModel):
    """Immutable, extra-forbidding base for every agent boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class AgentState(StrEnum):
    RECEIVED = "received"
    SEMANTICS_RESOLVED = "semantics_resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    SCHEMA_READY = "schema_ready"
    SQL_PROPOSED = "sql_proposed"
    SQL_VALIDATED = "sql_validated"
    REPAIR_ALLOWED = "repair_allowed"
    BLOCKED = "blocked"
    QUERY_EXECUTED = "query_executed"
    RESULT_FORMATTED = "result_formatted"
    COMPLETED = "completed"


class AgentTerminalStatus(StrEnum):
    SUCCESS = "success"
    EMPTY_RESULT = "empty_result"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    MAX_STEPS_REACHED = "max_steps_reached"
    ERROR = "error"
    CANCELLED = "cancelled"


class AgentToolName(StrEnum):
    RESOLVE_SEMANTICS = "resolve_semantics"
    RETRIEVE_SCHEMA_CONTEXT = "retrieve_schema_context"
    VALIDATE_SQL = "validate_sql"
    REPAIR_SQL = "repair_sql"
    EXECUTE_VALIDATED_SQL = "execute_validated_sql"
    FORMAT_RESULT = "format_result"
    REQUEST_CLARIFICATION = "request_clarification"
    FINISH = "finish"


class AgentAction(StrictAgentModel):
    """One proposed action. Its arguments are revalidated by the registry."""

    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ResolveSemanticsInput(StrictAgentModel):
    pass


class ResolveSemanticsOutput(StrictAgentModel):
    language: LanguageCode
    semantic_version: str
    term_ids: tuple[str, ...] = ()
    metric_ids: tuple[str, ...] = ()
    clarification_rule_id: str | None = None


class RetrieveSchemaContextInput(StrictAgentModel):
    pass


class RetrieveSchemaContextOutput(StrictAgentModel):
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    table_ids: tuple[str, ...]
    truncated: bool


class ValidateSQLInput(StrictAgentModel):
    sql: str = Field(min_length=1, max_length=12_000)
    declared_tables: tuple[str, ...] = Field(default=(), max_length=100)
    declared_columns: tuple[str, ...] = Field(default=(), max_length=500)


class ValidationObservation(StrictAgentModel):
    candidate_id: str = Field(min_length=16, max_length=100)
    safe: bool
    validation_handle: str | None = Field(default=None, min_length=16, max_length=200)
    fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    violation_codes: tuple[str, ...] = ()
    repairable: bool
    table_ids: tuple[str, ...] = ()
    column_ids: tuple[str, ...] = ()
    limit_applied: bool = False

    @model_validator(mode="after")
    def validate_handle(self) -> ValidationObservation:
        if self.safe != (self.validation_handle is not None):
            raise ValueError("only safe validation may issue a handle")
        if self.safe and self.fingerprint is None:
            raise ValueError("safe validation requires a fingerprint")
        return self


class RepairSQLInput(StrictAgentModel):
    candidate_id: str = Field(min_length=16, max_length=100)


class ExecuteValidatedSQLInput(StrictAgentModel):
    validation_handle: str = Field(min_length=16, max_length=200)


class ExecuteValidatedSQLOutput(StrictAgentModel):
    result_handle: str = Field(min_length=16, max_length=200)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=0)
    truncated: bool
    execution_time_ms: float = Field(ge=0)


class FormatResultInput(StrictAgentModel):
    result_handle: str = Field(min_length=16, max_length=200)


class FormatResultOutput(StrictAgentModel):
    row_count: int = Field(ge=0)
    chart_type: str | None = None
    explanation: str


class RequestClarificationInput(StrictAgentModel):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


class ClarificationOptionView(StrictAgentModel):
    option_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=500)


class RequestClarificationOutput(StrictAgentModel):
    continuation_id: str = Field(min_length=16, max_length=200)
    question: str = Field(min_length=1, max_length=500)
    options: tuple[ClarificationOptionView, ...] = Field(min_length=2, max_length=5)
    expires_at: str


class FinishInput(StrictAgentModel):
    status: AgentTerminalStatus


class FinishOutput(StrictAgentModel):
    status: AgentTerminalStatus


class AgentObservation(StrictAgentModel):
    """Sanitized tool result exposed to a deciding model or audit consumer."""

    tool_name: AgentToolName
    tool_version: str
    status: str = Field(pattern=r"^(ok|rejected|error)$")
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentAuditEvent(StrictAgentModel):
    """Privacy-safe event: never contains question, SQL, prompt, or rows."""

    step: int = Field(ge=1)
    tool_name: str = Field(min_length=1, max_length=100)
    tool_version: str
    status: str = Field(pattern=r"^(ok|rejected|error)$")
    latency_ms: float = Field(ge=0)
    candidate_id: str | None = None
    fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class AgentBudgetSnapshot(StrictAgentModel):
    steps_used: int = Field(ge=0)
    max_steps: int = Field(ge=1)
    repairs_used: int = Field(ge=0)
    max_repairs: int = Field(ge=0)
    clarification_rounds: int = Field(ge=0)
    max_clarification_rounds: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0)
    max_runtime_seconds: float = Field(gt=0)
    total_tokens: int | None = Field(default=None, ge=0)
    max_total_tokens: int | None = Field(default=None, ge=1)
    cost_usd: float | None = Field(default=None, ge=0)
    max_cost_usd: float | None = Field(default=None, gt=0)


class AgentResult(StrictAgentModel):
    """Final bounded result. Raw values are returned only to the requesting client."""

    generated_sql: str | None = None
    executed_sql: str | None = None
    sql_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tables: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    presentation: ResultPresentation | None = None
    chart: ChartSpec | None = None
    explanation: str | None = None


class AgentRunResponse(StrictAgentModel):
    request_id: str = Field(min_length=1, max_length=100)
    session_id: str = Field(min_length=16, max_length=200)
    state: AgentState
    status: AgentTerminalStatus
    stop_reason: str = Field(min_length=1, max_length=100)
    language: LanguageCode | None = None
    clarification: RequestClarificationOutput | None = None
    result: AgentResult | None = None
    budget: AgentBudgetSnapshot
    audit: tuple[AgentAuditEvent, ...]
    provider: str
    model: str
    architecture_version: str = "bounded-agent-v1"


class AgentQueryRequest(StrictAgentModel):
    question: str = Field(min_length=1, max_length=2_000)


class AgentContinueRequest(StrictAgentModel):
    continuation_id: str = Field(min_length=16, max_length=200)
    option_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    question: str = Field(min_length=1, max_length=2_000)


class AgentCancelRequest(StrictAgentModel):
    continuation_id: str = Field(min_length=16, max_length=200)


class AgentCancelResponse(StrictAgentModel):
    session_id: str
    status: AgentTerminalStatus = AgentTerminalStatus.CANCELLED
