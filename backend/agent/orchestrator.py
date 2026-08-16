"""Bounded decide-act-observe loop with deterministic transition authority."""

from __future__ import annotations

import asyncio
import secrets
from time import perf_counter
from uuid import uuid4

from backend.agent.contracts import (
    AgentAuthorityError,
    AgentContinuationError,
    AgentPolicy,
)
from backend.agent.registry import AgentToolRegistry, RegistryResult
from backend.agent.session import AgentLimits, AgentServices, AgentSession, AgentSessionStore
from backend.core.errors import AppError, InvalidRequestError, LLMTimeoutError, QueryTimeoutError
from backend.core.observability import current_request_id
from backend.schemas.agent import (
    AgentAction,
    AgentAuditEvent,
    AgentBudgetSnapshot,
    AgentCancelResponse,
    AgentResult,
    AgentRunResponse,
    AgentState,
    AgentTerminalStatus,
    AgentToolName,
    ExecuteValidatedSQLOutput,
    FinishOutput,
    FormatResultOutput,
    RequestClarificationOutput,
    ResolveSemanticsOutput,
    RetrieveSchemaContextOutput,
    ValidationObservation,
)


class BoundedAnalyticsAgent:
    """Run an analytics agent whose authority is smaller than its model output."""

    def __init__(
        self,
        services: AgentServices,
        policy: AgentPolicy,
        registry: AgentToolRegistry,
        *,
        limits: AgentLimits | None = None,
        sessions: AgentSessionStore | None = None,
        max_question_characters: int = 2_000,
    ) -> None:
        if max_question_characters <= 0:
            raise ValueError("question limit must be positive")
        self._services = services
        self._policy = policy
        self._registry = registry
        self._limits = limits or AgentLimits()
        self._sessions = sessions or AgentSessionStore()
        self._max_question_characters = max_question_characters

    @property
    def registry(self) -> AgentToolRegistry:
        return self._registry

    async def process(self, question: str) -> AgentRunResponse:
        normalized = question.strip()
        if not normalized:
            raise InvalidRequestError("Question must not be empty.")
        if len(normalized) > self._max_question_characters:
            raise InvalidRequestError("Question exceeds the configured character limit.")
        session = AgentSession(
            request_id=current_request_id() or str(uuid4()),
            session_id=f"ags_{secrets.token_urlsafe(24)}",
            question=normalized,
            services=self._services,
            limits=self._limits,
        )
        return await self._run(session)

    async def continue_with_choice(
        self,
        continuation_id: str,
        option_id: str,
        question: str,
    ) -> AgentRunResponse:
        try:
            session = self._sessions.claim(
                continuation_id,
                question=question,
                services=self._services,
                limits=self._limits,
            )
        except AgentContinuationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        retain = True
        try:
            if (
                session.state is not AgentState.CLARIFICATION_REQUIRED
                or session.semantic_resolution is None
                or session.semantic_resolution.clarification is None
            ):
                raise InvalidRequestError("The continuation is not awaiting clarification.")
            rule_id = session.semantic_resolution.clarification.rule_id
            session.semantic_resolution = session.services.semantic_service.resolve_choice(
                session.question,
                rule_id=rule_id,
                option_id=option_id,
            )
            session.language = session.semantic_resolution.language
            session.clarification = None
            session.state = AgentState.SEMANTICS_RESOLVED
            session.resume()
            response = await self._run(session)
            retain = response.status is AgentTerminalStatus.CLARIFICATION_REQUIRED
            return response
        finally:
            self._sessions.release(continuation_id, retain=retain)

    def cancel(self, continuation_id: str) -> AgentCancelResponse:
        try:
            session_id = self._sessions.cancel(continuation_id)
        except AgentContinuationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return AgentCancelResponse(session_id=session_id)

    async def _run(self, session: AgentSession) -> AgentRunResponse:
        while session.state not in {AgentState.CLARIFICATION_REQUIRED, AgentState.COMPLETED}:
            if session.steps_used >= session.limits.max_steps:
                return self._stop(
                    session,
                    AgentTerminalStatus.MAX_STEPS_REACHED,
                    "max_steps_reached",
                )
            if session.remaining_seconds <= 0:
                return self._stop(session, AgentTerminalStatus.TIMEOUT, "agent_deadline")

            action: AgentAction | None = None
            started = perf_counter()
            try:
                decision = await asyncio.wait_for(
                    self._policy.decide(session), timeout=session.remaining_seconds
                )
                action = decision.action
                session.add_usage(decision.token_usage, decision.cost_usd)
                budget_reason = self._usage_budget_reason(session)
                if budget_reason is not None:
                    return self._stop(
                        session,
                        AgentTerminalStatus.MAX_STEPS_REACHED,
                        budget_reason,
                    )
                if (
                    session.state is AgentState.SCHEMA_READY
                    and action.tool_name == AgentToolName.VALIDATE_SQL.value
                ):
                    session.state = AgentState.SQL_PROPOSED
                result = await asyncio.wait_for(
                    self._registry.execute(session, action),
                    timeout=session.remaining_seconds,
                )
                session.steps_used += 1
                self._audit(session, action, result, started, "ok")
                self._transition(session, result)
            except AgentAuthorityError:
                session.steps_used += 1
                self._audit(session, action, None, started, "rejected")
                return self._stop(
                    session,
                    AgentTerminalStatus.BLOCKED,
                    "tool_authority_violation",
                )
            except QueryTimeoutError:
                session.steps_used += 1
                self._audit(session, action, None, started, "error")
                return self._stop(session, AgentTerminalStatus.TIMEOUT, "query_timeout")
            except LLMTimeoutError:
                session.steps_used += 1
                self._audit(session, action, None, started, "error")
                return self._stop(session, AgentTerminalStatus.TIMEOUT, "provider_timeout")
            except TimeoutError:
                session.steps_used += 1
                self._audit(session, action, None, started, "error")
                return self._stop(session, AgentTerminalStatus.TIMEOUT, "agent_deadline")
            except AppError:
                session.steps_used += 1
                self._audit(session, action, None, started, "error")
                return self._stop(session, AgentTerminalStatus.ERROR, "service_error")
            except Exception:
                session.steps_used += 1
                self._audit(session, action, None, started, "error")
                return self._stop(session, AgentTerminalStatus.ERROR, "internal_error")

        if session.state is AgentState.CLARIFICATION_REQUIRED:
            session.terminal_status = AgentTerminalStatus.CLARIFICATION_REQUIRED
            session.stop_reason = "clarification_required"
            session.pause()
            self._sessions.put(session)
        return self._response(session)

    def _transition(self, session: AgentSession, result: RegistryResult) -> None:
        name = result.observation.tool_name
        output = result.output
        if name is AgentToolName.RESOLVE_SEMANTICS:
            ResolveSemanticsOutput.model_validate(output)
            session.state = AgentState.SEMANTICS_RESOLVED
        elif name is AgentToolName.RETRIEVE_SCHEMA_CONTEXT:
            RetrieveSchemaContextOutput.model_validate(output)
            session.state = AgentState.SCHEMA_READY
        elif name in {AgentToolName.VALIDATE_SQL, AgentToolName.REPAIR_SQL}:
            validation = ValidationObservation.model_validate(output)
            if validation.safe:
                session.state = AgentState.SQL_VALIDATED
            elif validation.repairable and session.repairs_used < session.limits.max_repairs:
                session.state = AgentState.REPAIR_ALLOWED
            else:
                session.state = AgentState.BLOCKED
        elif name is AgentToolName.EXECUTE_VALIDATED_SQL:
            ExecuteValidatedSQLOutput.model_validate(output)
            session.state = AgentState.QUERY_EXECUTED
        elif name is AgentToolName.FORMAT_RESULT:
            FormatResultOutput.model_validate(output)
            session.state = AgentState.RESULT_FORMATTED
        elif name is AgentToolName.REQUEST_CLARIFICATION:
            RequestClarificationOutput.model_validate(output)
            session.state = AgentState.CLARIFICATION_REQUIRED
        elif name is AgentToolName.FINISH:
            finished = FinishOutput.model_validate(output)
            session.terminal_status = finished.status
            session.stop_reason = finished.status.value
            session.state = AgentState.COMPLETED
        else:  # registry enums make this unreachable; retain fail-closed behavior
            raise AgentAuthorityError("tool has no authorized transition")

    @staticmethod
    def _usage_budget_reason(session: AgentSession) -> str | None:
        if (
            session.limits.max_total_tokens is not None
            and session.total_tokens is not None
            and session.total_tokens > session.limits.max_total_tokens
        ):
            return "token_budget_exhausted"
        if (
            session.limits.max_cost_usd is not None
            and session.cost_usd is not None
            and session.cost_usd > session.limits.max_cost_usd
        ):
            return "cost_budget_exhausted"
        return None

    @staticmethod
    def _audit(
        session: AgentSession,
        action: AgentAction | None,
        result: RegistryResult | None,
        started: float,
        status: str,
    ) -> None:
        payload = result.observation.payload if result is not None else {}
        tool_version = result.observation.tool_version if result is not None else "unknown"
        tool_name = action.tool_name if action is not None else "policy_decision"
        session.audit.append(
            AgentAuditEvent(
                step=session.steps_used,
                tool_name=tool_name,
                tool_version=tool_version,
                status=status,
                latency_ms=max(0.0, (perf_counter() - started) * 1_000),
                candidate_id=(
                    str(payload["candidate_id"]) if payload.get("candidate_id") else None
                ),
                fingerprint=(str(payload["fingerprint"]) if payload.get("fingerprint") else None),
            )
        )

    def _stop(
        self,
        session: AgentSession,
        status: AgentTerminalStatus,
        reason: str,
    ) -> AgentRunResponse:
        session.terminal_status = status
        session.stop_reason = reason
        session.state = AgentState.COMPLETED
        session.pause()
        return self._response(session)

    def _response(self, session: AgentSession) -> AgentRunResponse:
        status = session.terminal_status or AgentTerminalStatus.ERROR
        candidate = (
            session.candidates.get(session.current_candidate_id)
            if session.current_candidate_id
            else None
        )
        result = None
        if candidate is not None or session.presentation is not None:
            validation = candidate.validation if candidate else None
            result = AgentResult(
                generated_sql=candidate.sql if candidate else None,
                executed_sql=(
                    validation.executed_sql
                    if validation is not None and session.result is not None
                    else None
                ),
                sql_fingerprint=validation.fingerprint if validation else None,
                tables=validation.tables if validation else (),
                columns=validation.columns if validation else (),
                presentation=session.presentation,
                chart=session.chart,
                explanation=session.summary.text if session.summary else None,
            )
        return AgentRunResponse(
            request_id=session.request_id,
            session_id=session.session_id,
            state=session.state,
            status=status,
            stop_reason=session.stop_reason or "internal_error",
            language=session.language,
            clarification=session.clarification,
            result=result,
            budget=AgentBudgetSnapshot(
                steps_used=session.steps_used,
                max_steps=session.limits.max_steps,
                repairs_used=session.repairs_used,
                max_repairs=session.limits.max_repairs,
                clarification_rounds=session.clarification_rounds,
                max_clarification_rounds=session.limits.max_clarification_rounds,
                elapsed_ms=session.elapsed_ms,
                max_runtime_seconds=session.limits.max_runtime_seconds,
                total_tokens=session.total_tokens,
                max_total_tokens=session.limits.max_total_tokens,
                cost_usd=session.cost_usd,
                max_cost_usd=session.limits.max_cost_usd,
            ),
            audit=tuple(session.audit),
            provider=self._policy.provider,
            model=self._policy.model,
        )
