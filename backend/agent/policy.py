"""Model-guided but deterministically bounded action policy."""

from __future__ import annotations

from backend.agent.contracts import AgentDecision, AgentPolicy
from backend.agent.session import AgentSession
from backend.schemas.agent import AgentAction, AgentState, AgentTerminalStatus, AgentToolName
from backend.schemas.llm import LLMIntent
from backend.services.orchestrator import SQLGenerationService


class PipelineAgentPolicy(AgentPolicy):
    """Use the configured model for SQL proposals and deterministic control elsewhere.

    The model's proposal becomes arguments to ``validate_sql``; it never directly invokes
    the database. Alternate policies may propose any action, but the registry still applies
    the same state allowlist and typed validation.
    """

    def __init__(self, generator: SQLGenerationService) -> None:
        self._generator = generator

    @property
    def provider(self) -> str:
        return self._generator.provider

    @property
    def model(self) -> str:
        return self._generator.model

    async def decide(self, session: AgentSession) -> AgentDecision:
        if session.state is AgentState.RECEIVED:
            return _decision(AgentToolName.RESOLVE_SEMANTICS)
        if session.state is AgentState.SEMANTICS_RESOLVED:
            resolution = session.semantic_resolution
            if resolution is not None and resolution.clarification is not None:
                return _decision(
                    AgentToolName.REQUEST_CLARIFICATION,
                    rule_id=resolution.clarification.rule_id,
                )
            return _decision(AgentToolName.RETRIEVE_SCHEMA_CONTEXT)
        if session.state is AgentState.SCHEMA_READY:
            generation = await self._generator.generate(
                request_id=session.request_id,
                question=session.question,
                snapshot=session.services.snapshot,
                allowlist=session.services.allowlist,
                semantic_resolution=session.semantic_resolution,
            )
            session.generation = generation
            proposal = generation.proposal
            if proposal.intent is not LLMIntent.ANALYSIS or proposal.sql is None:
                return AgentDecision(
                    action=AgentAction(
                        tool_name=AgentToolName.FINISH.value,
                        arguments={"status": AgentTerminalStatus.UNSUPPORTED.value},
                    ),
                    token_usage=generation.llm_token_usage,
                )
            return AgentDecision(
                action=AgentAction(
                    tool_name=AgentToolName.VALIDATE_SQL.value,
                    arguments={
                        "sql": proposal.sql,
                        "declared_tables": proposal.tables,
                        "declared_columns": proposal.columns,
                    },
                ),
                token_usage=generation.llm_token_usage,
            )
        if session.state is AgentState.REPAIR_ALLOWED:
            if session.current_candidate_id is None:
                raise RuntimeError("repair state requires a candidate")
            return _decision(
                AgentToolName.REPAIR_SQL,
                candidate_id=session.current_candidate_id,
            )
        if session.state is AgentState.SQL_VALIDATED:
            candidate_id = session.current_candidate_id
            handle = next(
                (
                    key
                    for key, capability in session.validation_capabilities.items()
                    if capability.candidate_id == candidate_id
                ),
                None,
            )
            if handle is None:
                raise RuntimeError("validated state requires an unused execution capability")
            return _decision(AgentToolName.EXECUTE_VALIDATED_SQL, validation_handle=handle)
        if session.state is AgentState.QUERY_EXECUTED:
            if session.current_result_handle is None:
                raise RuntimeError("executed state requires a result capability")
            return _decision(
                AgentToolName.FORMAT_RESULT,
                result_handle=session.current_result_handle,
            )
        if session.state is AgentState.RESULT_FORMATTED:
            status = (
                AgentTerminalStatus.EMPTY_RESULT
                if session.presentation is not None and session.presentation.row_count == 0
                else AgentTerminalStatus.SUCCESS
            )
            return _decision(AgentToolName.FINISH, status=status.value)
        if session.state is AgentState.BLOCKED:
            return _decision(
                AgentToolName.FINISH,
                status=AgentTerminalStatus.BLOCKED.value,
            )
        raise RuntimeError(f"no policy action for state {session.state.value}")


def _decision(tool_name: AgentToolName, **arguments: object) -> AgentDecision:
    return AgentDecision(action=AgentAction(tool_name=tool_name.value, arguments=dict(arguments)))
