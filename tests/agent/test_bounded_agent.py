"""Authority, repair, continuation, and budget tests for Points 6 and 7."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from backend.agent.contracts import AgentDecision, AgentPolicy, RepairCandidate
from backend.agent.orchestrator import BoundedAnalyticsAgent
from backend.agent.policy import PipelineAgentPolicy
from backend.agent.registry import AgentToolRegistry
from backend.agent.repair_provider import LLMRepairProvider
from backend.agent.session import (
    AgentContinuationBackend,
    AgentLimits,
    AgentServices,
    AgentSession,
    AgentSessionStore,
    PersistedContinuation,
    SQLCandidate,
)
from backend.agent.tools import (
    ExecuteValidatedSQLTool,
    FormatResultTool,
    RepairSQLTool,
    RequestClarificationTool,
    ResolveSemanticsTool,
    ValidateSQLTool,
    default_tools,
)
from backend.core.errors import (
    InvalidRequestError,
    LLMOutputError,
    LLMProviderError,
    LLMTimeoutError,
    QueryTimeoutError,
)
from backend.llm.adapters import FakeLLMAdapter
from backend.schemas.agent import (
    AgentAction,
    AgentState,
    AgentTerminalStatus,
    ExecuteValidatedSQLInput,
    FormatResultInput,
    RepairSQLInput,
    RequestClarificationInput,
    ValidateSQLInput,
    ValidationObservation,
)
from backend.schemas.database import QueryResult, SchemaAllowlist
from backend.schemas.llm import (
    LanguageCode,
    LLMIntent,
    LLMTokenUsage,
    StructuredSQLProposal,
)
from backend.services.chart_selector import DeterministicChartSelector
from backend.services.orchestrator import SQLGenerationService
from backend.services.output_parser import StructuredOutputParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.query_executor import QueryExecutor
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_service import SemanticService
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_generator import SQLGenerator
from backend.services.sql_security import SQLSecurityService

ROOT = Path(__file__).resolve().parents[2]


class RecordingExecutor(QueryExecutor):
    def __init__(self, *, rows: tuple[tuple[Any, ...], ...] = ((59,),)) -> None:
        self.calls: list[str] = []
        self._rows = rows

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        self.calls.append(sql)
        return QueryResult(
            columns=("customer_count",),
            rows=self._rows,
            row_count=len(self._rows),
            truncated=False,
            execution_time_ms=0.1,
            response_bytes=40,
        )


class StubRepairProvider:
    def __init__(self, proposals: tuple[str, ...]) -> None:
        self.proposals = proposals
        self.calls = 0

    async def propose(self, session: AgentSession, candidate_id: str) -> RepairCandidate:
        _ = session, candidate_id
        index = min(self.calls, len(self.proposals) - 1)
        self.calls += 1
        return RepairCandidate(
            sql=self.proposals[index],
            declared_tables=("Customer",),
            declared_columns=("Customer.CustomerId",),
        )


@dataclass(frozen=True)
class BuiltAgent:
    agent: BoundedAnalyticsAgent
    executor: RecordingExecutor
    repair: StubRepairProvider
    services: AgentServices
    policy: AgentPolicy


def _proposal(sql: str) -> StructuredSQLProposal:
    return StructuredSQLProposal(
        intent=LLMIntent.ANALYSIS,
        language=LanguageCode.ENGLISH,
        needs_clarification=False,
        sql=sql,
        tables=("Customer",),
        columns=("Customer.CustomerId",),
        confidence=1.0,
        reasoning_summary="A bounded test proposal.",
    )


def _build_agent(
    question: str,
    sql: str,
    *,
    repair_sql: tuple[str, ...] = ("SELECT COUNT(CustomerId) AS customer_count FROM Customer",),
    limits: AgentLimits | None = None,
    rows: tuple[tuple[Any, ...], ...] = ((59,),),
    policy: AgentPolicy | None = None,
    sessions: AgentSessionStore | None = None,
) -> BuiltAgent:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    allowlist = SchemaAllowlist.from_snapshot(snapshot)
    validator = SQLSecurityService(allowlist)
    bundle = load_semantic_bundle(ROOT / "semantic")
    semantic_report = SemanticLayerValidator(
        snapshot,
        validator,
        expected_semantic_version="v1",
    ).validate(bundle)
    semantic = SemanticService(bundle, semantic_report)
    retriever = SchemaRetriever()
    generator: SQLGenerationService = SQLGenerator(
        FakeLLMAdapter({question: _proposal(sql).model_dump_json()}),
        PromptBuilder(retriever),
        StructuredOutputParser(),
    )
    executor = RecordingExecutor(rows=rows)
    services = AgentServices(
        semantic_service=semantic,
        schema_retriever=retriever,
        snapshot=snapshot,
        allowlist=allowlist,
        validator=validator,
        executor=executor,
        formatter=ResultFormatter(),
        chart_selector=DeterministicChartSelector(),
        summarizer=ResultSummarizer(),
    )
    repair = StubRepairProvider(repair_sql)
    active_policy = policy or PipelineAgentPolicy(generator)
    return BuiltAgent(
        agent=BoundedAnalyticsAgent(
            services,
            active_policy,
            AgentToolRegistry(default_tools(repair)),
            limits=limits,
            sessions=sessions,
        ),
        executor=executor,
        repair=repair,
        services=services,
        policy=active_policy,
    )


def test_safe_run_uses_typed_tools_and_one_database_execution() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )

    response = asyncio.run(built.agent.process(question))

    assert response.status is AgentTerminalStatus.SUCCESS
    assert response.state is AgentState.COMPLETED
    assert response.budget.steps_used == 6
    assert len(built.executor.calls) == 1
    assert response.result is not None
    assert response.result.presentation is not None
    assert response.result.presentation.rows == ((59,),)
    assert tuple(event.tool_name for event in response.audit) == (
        "resolve_semantics",
        "retrieve_schema_context",
        "validate_sql",
        "execute_validated_sql",
        "format_result",
        "finish",
    )


def test_audit_excludes_question_sql_prompt_and_rows() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    response = asyncio.run(built.agent.process(question))

    serialized = "".join(event.model_dump_json() for event in response.audit).casefold()
    assert question.casefold() not in serialized
    assert "select " not in serialized
    assert "prompt" not in serialized
    assert all(
        set(event.model_dump())
        == {
            "step",
            "tool_name",
            "tool_version",
            "status",
            "latency_ms",
            "candidate_id",
            "fingerprint",
        }
        for event in response.audit
    )


def test_destructive_sql_is_blocked_without_repair_or_execution() -> None:
    question = "Delete customers"
    built = _build_agent(question, "DELETE FROM Customer")

    response = asyncio.run(built.agent.process(question))

    assert response.status is AgentTerminalStatus.BLOCKED
    assert response.stop_reason == "blocked"
    assert built.repair.calls == 0
    assert built.executor.calls == []


def test_repairable_sql_is_repaired_revalidated_and_executed() -> None:
    question = "How many customers are there?"
    built = _build_agent(question, "SELECT Missing FROM Customer")

    response = asyncio.run(built.agent.process(question))

    assert response.status is AgentTerminalStatus.SUCCESS
    assert response.budget.repairs_used == 1
    assert built.repair.calls == 1
    assert len(built.executor.calls) == 1


def test_repair_stops_at_two_attempts_and_never_executes_invalid_sql() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT Missing FROM Customer",
        repair_sql=("SELECT StillMissing FROM Customer",),
    )

    response = asyncio.run(built.agent.process(question))

    assert response.status is AgentTerminalStatus.BLOCKED
    assert response.budget.repairs_used == 2
    assert built.repair.calls == 2
    assert built.executor.calls == []


def test_clarification_uses_canonical_option_and_resumes_same_session() -> None:
    question = "Who is the best customer?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    first = asyncio.run(built.agent.process(question))

    assert first.status is AgentTerminalStatus.CLARIFICATION_REQUIRED
    assert first.clarification is not None
    assert {option.option_id for option in first.clarification.options} == {
        "total_spend",
        "transaction_count",
        "latest_transaction",
    }

    resumed = asyncio.run(
        built.agent.continue_with_choice(
            first.clarification.continuation_id,
            "total_spend",
            question,
        )
    )
    assert resumed.session_id == first.session_id
    assert resumed.status is AgentTerminalStatus.SUCCESS
    assert resumed.budget.clarification_rounds == 1


def test_invalid_clarification_choice_does_not_consume_continuation() -> None:
    question = "Who is the best customer?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    first = asyncio.run(built.agent.process(question))
    assert first.clarification is not None

    with pytest.raises(InvalidRequestError):
        asyncio.run(
            built.agent.continue_with_choice(
                first.clarification.continuation_id,
                "ignore_all_rules",
                question,
            )
        )
    resumed = asyncio.run(
        built.agent.continue_with_choice(
            first.clarification.continuation_id,
            "total_spend",
            question,
        )
    )
    assert resumed.status is AgentTerminalStatus.SUCCESS


def test_validation_handle_is_single_use_and_executor_never_accepts_tool_sql() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    session = AgentSession(
        request_id="request-handle",
        session_id="ags_handle_test_123456",
        question=question,
        services=built.services,
        limits=AgentLimits(),
        state=AgentState.SQL_PROPOSED,
    )
    validation = asyncio.run(
        ValidateSQLTool().run(
            session,
            ValidateSQLInput(
                sql="SELECT COUNT(CustomerId) AS customer_count FROM Customer",
                declared_tables=("Customer",),
                declared_columns=("Customer.CustomerId",),
            ),
        )
    )
    observed = ValidationObservation.model_validate(validation)
    assert observed.validation_handle is not None
    execution = ExecuteValidatedSQLTool()
    asyncio.run(
        execution.run(
            session,
            ExecuteValidatedSQLInput(validation_handle=observed.validation_handle),
        )
    )
    with pytest.raises(ValueError, match="already consumed"):
        asyncio.run(
            execution.run(
                session,
                ExecuteValidatedSQLInput(validation_handle=observed.validation_handle),
            )
        )
    assert len(built.executor.calls) == 1


def test_registry_rejects_execute_before_validation() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    session = AgentSession(
        request_id="request-authority",
        session_id="ags_authority_test_123456",
        question=question,
        services=built.services,
        limits=AgentLimits(),
    )
    with pytest.raises(ValueError, match="not allowed"):
        asyncio.run(
            built.agent.registry.execute(
                session,
                AgentAction(
                    tool_name="execute_validated_sql",
                    arguments={"validation_handle": "vh_forged_123456789"},
                ),
            )
        )
    assert built.executor.calls == []


class UnknownToolPolicy(AgentPolicy):
    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "malicious-script"

    async def decide(self, session: AgentSession) -> AgentDecision:
        _ = session
        return AgentDecision(AgentAction(tool_name="shell", arguments={"command": "whoami"}))


def test_unknown_model_tool_is_fail_closed() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        policy=UnknownToolPolicy(),
    )

    response = asyncio.run(built.agent.process(question))

    assert response.status is AgentTerminalStatus.BLOCKED
    assert response.stop_reason == "tool_authority_violation"
    assert response.audit[0].status == "rejected"
    assert built.executor.calls == []


def test_max_step_budget_stops_before_generation_or_execution() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        limits=AgentLimits(max_steps=1),
    )

    response = asyncio.run(built.agent.process(question))

    assert response.status is AgentTerminalStatus.MAX_STEPS_REACHED
    assert response.stop_reason == "max_steps_reached"
    assert built.executor.calls == []


def test_empty_result_has_distinct_terminal_status() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        rows=(),
    )

    response = asyncio.run(built.agent.process(question))

    assert response.status is AgentTerminalStatus.EMPTY_RESULT


class MemoryContinuationBackend(AgentContinuationBackend):
    def __init__(self) -> None:
        self.records: dict[str, PersistedContinuation] = {}
        self.claimed: set[str] = set()

    def save_continuation(self, record: PersistedContinuation) -> None:
        self.records[record.continuation_id] = record
        self.claimed.discard(record.continuation_id)

    def claim_continuation(self, continuation_id: str) -> PersistedContinuation | None:
        record = self.records.get(continuation_id)
        if (
            record is None
            or continuation_id in self.claimed
            or record.expires_at <= datetime.now(UTC)
        ):
            return None
        self.claimed.add(continuation_id)
        return record

    def release_continuation(self, continuation_id: str, *, retain: bool) -> None:
        self.claimed.discard(continuation_id)
        if not retain:
            self.records.pop(continuation_id, None)

    def cancel_continuation(self, continuation_id: str) -> PersistedContinuation | None:
        if continuation_id in self.claimed:
            return None
        return self.records.pop(continuation_id, None)


def test_continuation_survives_process_local_session_loss_without_raw_question_storage() -> None:
    question = "Who is the best customer?"
    backend = MemoryContinuationBackend()
    first_runtime = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        sessions=AgentSessionStore(backend=backend),
    )
    first = asyncio.run(first_runtime.agent.process(question))
    assert first.clarification is not None
    stored = backend.records[first.session_id]
    assert stored.question_digest != question
    assert question not in repr(stored)

    restarted_agent = BoundedAnalyticsAgent(
        first_runtime.services,
        first_runtime.policy,
        AgentToolRegistry(default_tools(first_runtime.repair)),
        sessions=AgentSessionStore(backend=backend),
    )
    resumed = asyncio.run(
        restarted_agent.continue_with_choice(
            first.session_id,
            "total_spend",
            question,
        )
    )
    assert resumed.status is AgentTerminalStatus.SUCCESS
    assert first.session_id not in backend.records


def _repair_session(question: str = "Repair this query") -> AgentSession:
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    session = AgentSession(
        request_id="repair-provider-request",
        session_id="ags_repair_provider_123456",
        question=question,
        services=built.services,
        limits=AgentLimits(),
    )
    validation = built.services.validator.validate("SELECT Missing FROM Customer")
    candidate = SQLCandidate(
        candidate_id="sqlc_repair_provider_123456",
        sql="SELECT Missing FROM Customer",
        declared_tables=("Customer",),
        declared_columns=("Customer.CustomerId",),
        validation=validation,
    )
    session.candidates[candidate.candidate_id] = candidate
    return session


def test_llm_repair_provider_returns_only_a_structured_candidate() -> None:
    question = "Repair this query"
    session = _repair_session(question)
    response = _proposal(
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer"
    ).model_dump_json()
    provider = LLMRepairProvider(
        FakeLLMAdapter({question: response}),
        StructuredOutputParser(),
        timeout_seconds=1,
    )

    candidate = asyncio.run(provider.propose(session, "sqlc_repair_provider_123456"))

    assert candidate.sql.startswith("SELECT COUNT")
    assert candidate.declared_tables == ("Customer",)


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [("timeout", LLMTimeoutError), ("provider", LLMProviderError)],
)
def test_llm_repair_provider_sanitizes_adapter_failures(
    failure: str,
    error_type: type[Exception],
) -> None:
    session = _repair_session()
    provider = LLMRepairProvider(
        FakeLLMAdapter(failure=failure),
        StructuredOutputParser(),
        timeout_seconds=1,
    )
    with pytest.raises(error_type):
        asyncio.run(provider.propose(session, "sqlc_repair_provider_123456"))


def test_llm_repair_provider_rejects_missing_and_non_analysis_outputs() -> None:
    session = _repair_session()
    provider = LLMRepairProvider(
        FakeLLMAdapter(),
        StructuredOutputParser(),
        timeout_seconds=1,
    )
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(provider.propose(session, "sqlc_missing_123456789"))
    with pytest.raises(LLMOutputError):
        asyncio.run(provider.propose(session, "sqlc_repair_provider_123456"))
    with pytest.raises(ValueError, match="positive"):
        LLMRepairProvider(FakeLLMAdapter(), StructuredOutputParser(), timeout_seconds=0)


class RaisingPolicy(AgentPolicy):
    def __init__(self, error: Exception) -> None:
        self._error = error

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "raising-policy"

    async def decide(self, session: AgentSession) -> AgentDecision:
        _ = session
        raise self._error


@pytest.mark.parametrize(
    ("error", "status", "reason"),
    [
        (QueryTimeoutError(), AgentTerminalStatus.TIMEOUT, "query_timeout"),
        (LLMTimeoutError(), AgentTerminalStatus.TIMEOUT, "provider_timeout"),
        (InvalidRequestError(), AgentTerminalStatus.ERROR, "service_error"),
        (RuntimeError("private detail"), AgentTerminalStatus.ERROR, "internal_error"),
    ],
)
def test_agent_sanitizes_distinct_policy_and_service_failures(
    error: Exception,
    status: AgentTerminalStatus,
    reason: str,
) -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        policy=RaisingPolicy(error),
    )

    response = asyncio.run(built.agent.process(question))

    assert response.status is status
    assert response.stop_reason == reason
    assert response.audit[0].status == "error"
    assert "private detail" not in response.model_dump_json()


class SlowPolicy(UnknownToolPolicy):
    async def decide(self, session: AgentSession) -> AgentDecision:
        _ = session
        await asyncio.sleep(0.05)
        return AgentDecision(AgentAction(tool_name="resolve_semantics"))


def test_agent_deadline_stops_a_slow_decision() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        policy=SlowPolicy(),
        limits=AgentLimits(max_runtime_seconds=0.001),
    )
    response = asyncio.run(built.agent.process(question))
    assert response.status is AgentTerminalStatus.TIMEOUT
    assert response.stop_reason == "agent_deadline"


class UsagePolicy(UnknownToolPolicy):
    def __init__(self, *, tokens: int | None = None, cost: float | None = None) -> None:
        self.tokens = tokens
        self.cost = cost

    async def decide(self, session: AgentSession) -> AgentDecision:
        _ = session
        usage = LLMTokenUsage(input_tokens=self.tokens) if self.tokens is not None else None
        return AgentDecision(
            AgentAction(tool_name="resolve_semantics"),
            token_usage=usage,
            cost_usd=self.cost,
        )


@pytest.mark.parametrize(
    ("policy", "limits", "reason"),
    [
        (
            UsagePolicy(tokens=6),
            AgentLimits(max_total_tokens=5),
            "token_budget_exhausted",
        ),
        (
            UsagePolicy(cost=0.02),
            AgentLimits(max_cost_usd=0.01),
            "cost_budget_exhausted",
        ),
    ],
)
def test_usage_budgets_stop_before_a_tool_call(
    policy: AgentPolicy,
    limits: AgentLimits,
    reason: str,
) -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        policy=policy,
        limits=limits,
    )
    response = asyncio.run(built.agent.process(question))
    assert response.status is AgentTerminalStatus.MAX_STEPS_REACHED
    assert response.stop_reason == reason
    assert response.audit == ()


def test_agent_rejects_blank_long_and_unknown_continuation_inputs() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    with pytest.raises(InvalidRequestError):
        asyncio.run(built.agent.process("   "))
    with pytest.raises(InvalidRequestError):
        asyncio.run(built.agent.process("x" * 2_001))
    with pytest.raises(InvalidRequestError):
        asyncio.run(
            built.agent.continue_with_choice(
                "ags_missing_continuation_123456",
                "total_spend",
                question,
            )
        )
    with pytest.raises(InvalidRequestError):
        built.agent.cancel("ags_missing_continuation_123456")


def test_agent_cancel_consumes_a_pending_continuation() -> None:
    question = "Who is the best customer?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    response = asyncio.run(built.agent.process(question))
    cancelled = built.agent.cancel(response.session_id)
    assert cancelled.status is AgentTerminalStatus.CANCELLED
    with pytest.raises(InvalidRequestError):
        built.agent.cancel(response.session_id)


class EmptyToolOutput(BaseModel):
    pass


class InvalidOutputTool:
    name = ResolveSemanticsTool.name
    version = "test"
    description = "Return an invalid output for fail-closed testing."
    input_model: type[BaseModel] = ResolveSemanticsTool.input_model
    output_model: type[BaseModel] = ResolveSemanticsTool.output_model

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        _ = session, payload
        return EmptyToolOutput()


def test_registry_rejects_duplicates_missing_tools_bad_arguments_and_bad_outputs() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    session = AgentSession(
        request_id="registry-request",
        session_id="ags_registry_session_123456",
        question=question,
        services=built.services,
        limits=AgentLimits(),
    )
    with pytest.raises(ValueError, match="duplicate"):
        AgentToolRegistry((ResolveSemanticsTool(), ResolveSemanticsTool()))
    empty = AgentToolRegistry(())
    assert empty.names == ()
    with pytest.raises(ValueError, match="not registered"):
        asyncio.run(
            empty.execute(session, AgentAction(tool_name="resolve_semantics", arguments={}))
        )
    with pytest.raises(ValueError, match="arguments"):
        asyncio.run(
            built.agent.registry.execute(
                session,
                AgentAction(tool_name="resolve_semantics", arguments={"unexpected": True}),
            )
        )
    invalid = AgentToolRegistry((InvalidOutputTool(),))
    with pytest.raises(RuntimeError, match="invalid typed observation"):
        asyncio.run(
            invalid.execute(session, AgentAction(tool_name="resolve_semantics", arguments={}))
        )


def test_policy_rejects_impossible_internal_states_and_missing_capabilities() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    policy = built.policy
    session = AgentSession(
        request_id="policy-guard-request",
        session_id="ags_policy_guard_123456",
        question=question,
        services=built.services,
        limits=AgentLimits(),
    )
    for state, message in (
        (AgentState.REPAIR_ALLOWED, "repair state"),
        (AgentState.SQL_VALIDATED, "validated state"),
        (AgentState.QUERY_EXECUTED, "executed state"),
        (AgentState.COMPLETED, "no policy action"),
    ):
        session.state = state
        with pytest.raises(RuntimeError, match=message):
            asyncio.run(policy.decide(session))


def test_capability_and_usage_guards_fail_closed() -> None:
    question = "How many customers are there?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    session = AgentSession(
        request_id="capability-guard-request",
        session_id="ags_capability_guard_123456",
        question=question,
        services=built.services,
        limits=AgentLimits(),
    )
    unsafe = SQLCandidate(
        candidate_id="sqlc_unsafe_guard_123456",
        sql="DELETE FROM Customer",
        declared_tables=("Customer",),
        declared_columns=("Customer.CustomerId",),
        validation=built.services.validator.validate("DELETE FROM Customer"),
    )
    with pytest.raises(ValueError, match="unsafe validation"):
        session.issue_validation_capability(unsafe)
    with pytest.raises(ValueError, match="invalid"):
        session.consume_validation_capability("vh_missing_123456789")
    with pytest.raises(ValueError, match="invalid"):
        session.consume_result_capability("rh_missing_123456789")
    session.add_usage(LLMTokenUsage(total_tokens=4), 0.01)
    session.add_usage(LLMTokenUsage(input_tokens=2, output_tokens=3), 0.02)
    session.add_usage(LLMTokenUsage(), None)
    assert session.total_tokens == 9
    assert session.cost_usd == pytest.approx(0.03)
    session.pause()
    paused = session.elapsed_ms
    session.pause()
    session.resume()
    session.resume()
    assert session.elapsed_ms >= paused


def test_tool_guards_reject_invalid_repair_clarification_and_format_states() -> None:
    question = "Who is the best customer?"
    built = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    session = AgentSession(
        request_id="tool-guard-request",
        session_id="ags_tool_guard_123456",
        question=question,
        services=built.services,
        limits=AgentLimits(max_repairs=0),
    )
    repair = RepairSQLTool(built.repair)
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(repair.run(session, RepairSQLInput(candidate_id="sqlc_missing_123456789")))

    safe_validation = built.services.validator.validate(
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        declared_tables=("Customer",),
        declared_columns=("Customer.CustomerId",),
    )
    safe = SQLCandidate(
        candidate_id="sqlc_safe_guard_123456",
        sql="SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        declared_tables=("Customer",),
        declared_columns=("Customer.CustomerId",),
        validation=safe_validation,
    )
    session.candidates[safe.candidate_id] = safe
    with pytest.raises(ValueError, match="safe SQL"):
        asyncio.run(repair.run(session, RepairSQLInput(candidate_id=safe.candidate_id)))

    destructive = SQLCandidate(
        candidate_id="sqlc_destructive_guard_123456",
        sql="DELETE FROM Customer",
        declared_tables=("Customer",),
        declared_columns=("Customer.CustomerId",),
        validation=built.services.validator.validate("DELETE FROM Customer"),
    )
    session.candidates[destructive.candidate_id] = destructive
    with pytest.raises(ValueError, match="security-policy"):
        asyncio.run(repair.run(session, RepairSQLInput(candidate_id=destructive.candidate_id)))

    repairable = SQLCandidate(
        candidate_id="sqlc_budget_guard_123456",
        sql="SELECT Missing FROM Customer",
        declared_tables=("Customer",),
        declared_columns=("Customer.CustomerId",),
        validation=built.services.validator.validate("SELECT Missing FROM Customer"),
    )
    session.candidates[repairable.candidate_id] = repairable
    with pytest.raises(ValueError, match="budget"):
        asyncio.run(repair.run(session, RepairSQLInput(candidate_id=repairable.candidate_id)))

    clarification = RequestClarificationTool()
    with pytest.raises(ValueError, match="no deterministic"):
        asyncio.run(
            clarification.run(
                session,
                RequestClarificationInput(rule_id="best_customer_measure"),
            )
        )
    resolution = built.services.semantic_service.resolve(question)
    session.semantic_resolution = resolution
    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(
            clarification.run(
                session,
                RequestClarificationInput(rule_id="active_customer_basis"),
            )
        )
    session.semantic_resolution = resolution.model_copy(update={"matched_terms": ()})
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(
            clarification.run(
                session,
                RequestClarificationInput(rule_id="best_customer_measure"),
            )
        )
    session.semantic_resolution = resolution
    session.clarification_rounds = session.limits.max_clarification_rounds
    with pytest.raises(ValueError, match="budget"):
        asyncio.run(
            clarification.run(
                session,
                RequestClarificationInput(rule_id="best_customer_measure"),
            )
        )

    result_handle = session.issue_result_capability(
        "a" * 64,
        QueryResult(
            columns=("customer_count",),
            rows=((59,),),
            row_count=1,
            truncated=False,
            execution_time_ms=0,
            response_bytes=1,
        ),
    )
    session.language = None
    with pytest.raises(RuntimeError, match="resolved language"):
        asyncio.run(
            FormatResultTool().run(
                session,
                FormatResultInput(result_handle=result_handle),
            )
        )


def test_session_store_guards_capacity_expiry_and_persisted_only_cancel() -> None:
    question = "Who is the best customer?"
    store = AgentSessionStore(max_sessions=1)
    first_runtime = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        sessions=store,
    )
    first = asyncio.run(first_runtime.agent.process(question))
    second = asyncio.run(first_runtime.agent.process(question))
    with pytest.raises(InvalidRequestError):
        first_runtime.agent.cancel(first.session_id)
    assert first_runtime.agent.cancel(second.session_id).status is AgentTerminalStatus.CANCELLED
    with pytest.raises(ValueError, match="positive"):
        AgentSessionStore(max_sessions=0)

    backend = MemoryContinuationBackend()
    persisted_runtime = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        sessions=AgentSessionStore(backend=backend),
    )
    persisted = asyncio.run(persisted_runtime.agent.process(question))
    restarted_store = AgentSessionStore(backend=backend)
    restarted_agent = BoundedAnalyticsAgent(
        persisted_runtime.services,
        persisted_runtime.policy,
        AgentToolRegistry(default_tools(persisted_runtime.repair)),
        sessions=restarted_store,
    )
    assert restarted_agent.cancel(persisted.session_id).session_id == persisted.session_id

    expiring_runtime = _build_agent(
        question,
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        limits=AgentLimits(continuation_ttl_seconds=1),
    )
    expiring = asyncio.run(expiring_runtime.agent.process(question))
    asyncio.run(asyncio.sleep(1.01))
    with pytest.raises(InvalidRequestError):
        expiring_runtime.agent.cancel(expiring.session_id)


def test_limit_construction_and_session_store_reject_invalid_state() -> None:
    with pytest.raises(ValueError, match="positive"):
        AgentLimits(max_steps=0)
    with pytest.raises(ValueError, match="between zero and five"):
        AgentLimits(max_repairs=6)
    built = _build_agent(
        "How many customers are there?",
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
    )
    session = AgentSession(
        request_id="invalid-store-request",
        session_id="ags_invalid_store_123456",
        question="How many customers are there?",
        services=built.services,
        limits=AgentLimits(),
    )
    with pytest.raises(ValueError, match="pending clarification"):
        AgentSessionStore().put(session)
