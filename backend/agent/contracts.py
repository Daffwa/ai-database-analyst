"""Internal protocols and safe errors for the bounded agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from backend.schemas.agent import AgentAction, AgentState, AgentToolName
from backend.schemas.llm import LLMTokenUsage

if TYPE_CHECKING:
    from backend.agent.session import AgentSession


class AgentAuthorityError(ValueError):
    """A model proposed an unknown or state-inappropriate tool call."""


class AgentContinuationError(ValueError):
    """A continuation identifier or canonical choice is invalid."""


class AgentTool(Protocol):
    name: AgentToolName
    version: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel: ...


@dataclass(frozen=True, slots=True)
class AgentDecision:
    action: AgentAction
    token_usage: LLMTokenUsage | None = None
    cost_usd: float | None = None


class AgentPolicy(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def decide(self, session: AgentSession) -> AgentDecision: ...


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    sql: str
    declared_tables: tuple[str, ...]
    declared_columns: tuple[str, ...]
    token_usage: LLMTokenUsage | None = None
    cost_usd: float | None = None


class SQLRepairProvider(Protocol):
    async def propose(self, session: AgentSession, candidate_id: str) -> RepairCandidate: ...


TOOL_ALLOWLIST: dict[AgentState, frozenset[AgentToolName]] = {
    AgentState.RECEIVED: frozenset({AgentToolName.RESOLVE_SEMANTICS}),
    AgentState.SEMANTICS_RESOLVED: frozenset(
        {
            AgentToolName.RETRIEVE_SCHEMA_CONTEXT,
            AgentToolName.REQUEST_CLARIFICATION,
            AgentToolName.FINISH,
        }
    ),
    AgentState.SQL_PROPOSED: frozenset({AgentToolName.VALIDATE_SQL}),
    AgentState.REPAIR_ALLOWED: frozenset({AgentToolName.REPAIR_SQL, AgentToolName.FINISH}),
    AgentState.SQL_VALIDATED: frozenset({AgentToolName.EXECUTE_VALIDATED_SQL}),
    AgentState.BLOCKED: frozenset({AgentToolName.FINISH}),
    AgentState.QUERY_EXECUTED: frozenset({AgentToolName.FORMAT_RESULT}),
    AgentState.RESULT_FORMATTED: frozenset({AgentToolName.FINISH}),
    AgentState.SCHEMA_READY: frozenset({AgentToolName.REQUEST_CLARIFICATION, AgentToolName.FINISH}),
    AgentState.CLARIFICATION_REQUIRED: frozenset(),
    AgentState.COMPLETED: frozenset(),
}
