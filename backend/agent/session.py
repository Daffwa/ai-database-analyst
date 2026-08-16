"""Private session state and one-use capabilities for the bounded agent."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock
from time import monotonic
from typing import Protocol

from backend.agent.contracts import AgentContinuationError
from backend.schemas.agent import (
    AgentAuditEvent,
    AgentState,
    AgentTerminalStatus,
    RequestClarificationOutput,
)
from backend.schemas.database import QueryResult, SchemaAllowlist, SchemaSnapshot
from backend.schemas.llm import GenerationResult, LanguageCode, LLMTokenUsage
from backend.schemas.result import ChartSpec, ResultPresentation, ResultSummary
from backend.schemas.semantic import SemanticResolution
from backend.schemas.sql_security import SQLValidationReport
from backend.services.chart_selector import DeterministicChartSelector
from backend.services.query_executor import QueryExecutor
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer
from backend.services.schema_retriever import SchemaContext, SchemaRetriever
from backend.services.semantic_service import SemanticService
from backend.services.sql_security import SQLSecurityService


@dataclass(frozen=True, slots=True)
class AgentLimits:
    max_steps: int = 8
    max_repairs: int = 2
    max_clarification_rounds: int = 2
    max_runtime_seconds: float = 30.0
    continuation_ttl_seconds: int = 900
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if (
            min(
                self.max_steps,
                self.max_clarification_rounds,
                self.max_runtime_seconds,
                self.continuation_ttl_seconds,
            )
            <= 0
        ):
            raise ValueError("positive agent limits are required")
        if not 0 <= self.max_repairs <= 5:
            raise ValueError("max_repairs must be between zero and five")


@dataclass(frozen=True, slots=True)
class AgentServices:
    semantic_service: SemanticService
    schema_retriever: SchemaRetriever
    snapshot: SchemaSnapshot
    allowlist: SchemaAllowlist
    validator: SQLSecurityService
    executor: QueryExecutor
    formatter: ResultFormatter
    chart_selector: DeterministicChartSelector
    summarizer: ResultSummarizer


@dataclass(frozen=True, slots=True)
class SQLCandidate:
    candidate_id: str
    sql: str
    declared_tables: tuple[str, ...]
    declared_columns: tuple[str, ...]
    validation: SQLValidationReport


@dataclass(frozen=True, slots=True)
class ValidationCapability:
    request_id: str
    candidate_id: str
    fingerprint: str
    executed_sql: str


@dataclass(frozen=True, slots=True)
class ResultCapability:
    request_id: str
    fingerprint: str
    result: QueryResult


@dataclass(slots=True)
class AgentSession:
    request_id: str
    session_id: str
    question: str
    services: AgentServices
    limits: AgentLimits
    state: AgentState = AgentState.RECEIVED
    active_started_at: float | None = field(default_factory=monotonic)
    elapsed_before_pause_ms: float = 0.0
    steps_used: int = 0
    repairs_used: int = 0
    clarification_rounds: int = 0
    total_tokens: int | None = None
    cost_usd: float | None = None
    language: LanguageCode | None = None
    semantic_resolution: SemanticResolution | None = None
    schema_context: SchemaContext | None = None
    generation: GenerationResult | None = None
    candidates: dict[str, SQLCandidate] = field(default_factory=dict)
    current_candidate_id: str | None = None
    validation_capabilities: dict[str, ValidationCapability] = field(default_factory=dict)
    result_capabilities: dict[str, ResultCapability] = field(default_factory=dict)
    current_result_handle: str | None = None
    result: QueryResult | None = None
    presentation: ResultPresentation | None = None
    chart: ChartSpec | None = None
    summary: ResultSummary | None = None
    clarification: RequestClarificationOutput | None = None
    terminal_status: AgentTerminalStatus | None = None
    stop_reason: str | None = None
    audit: list[AgentAuditEvent] = field(default_factory=list)

    @property
    def elapsed_ms(self) -> float:
        active = (
            (monotonic() - self.active_started_at) * 1_000
            if self.active_started_at is not None
            else 0.0
        )
        return max(0.0, self.elapsed_before_pause_ms + active)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.limits.max_runtime_seconds - self.elapsed_ms / 1_000)

    def pause(self) -> None:
        if self.active_started_at is not None:
            self.elapsed_before_pause_ms += (monotonic() - self.active_started_at) * 1_000
            self.active_started_at = None

    def resume(self) -> None:
        if self.active_started_at is None:
            self.active_started_at = monotonic()

    def issue_validation_capability(self, candidate: SQLCandidate) -> str:
        validation = candidate.validation
        if not validation.safe or validation.executed_sql is None or validation.fingerprint is None:
            raise ValueError("unsafe validation cannot issue an execution capability")
        handle = f"vh_{secrets.token_urlsafe(24)}"
        self.validation_capabilities[handle] = ValidationCapability(
            request_id=self.request_id,
            candidate_id=candidate.candidate_id,
            fingerprint=validation.fingerprint,
            executed_sql=validation.executed_sql,
        )
        return handle

    def consume_validation_capability(self, handle: str) -> ValidationCapability:
        capability = self.validation_capabilities.pop(handle, None)
        if capability is None or capability.request_id != self.request_id:
            raise ValueError("validation handle is invalid, expired, or already consumed")
        return capability

    def issue_result_capability(self, fingerprint: str, result: QueryResult) -> str:
        handle = f"rh_{secrets.token_urlsafe(24)}"
        self.result_capabilities[handle] = ResultCapability(
            request_id=self.request_id,
            fingerprint=fingerprint,
            result=result,
        )
        return handle

    def consume_result_capability(self, handle: str) -> ResultCapability:
        capability = self.result_capabilities.pop(handle, None)
        if capability is None or capability.request_id != self.request_id:
            raise ValueError("result handle is invalid, expired, or already consumed")
        return capability

    def add_usage(self, usage: LLMTokenUsage | None, cost_usd: float | None = None) -> None:
        if usage is not None:
            tokens = usage.total_tokens
            if tokens is None:
                known = tuple(
                    value
                    for value in (
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.reasoning_tokens,
                    )
                    if value is not None
                )
                tokens = sum(known) if known else None
            if tokens is not None:
                self.total_tokens = (self.total_tokens or 0) + tokens
        if cost_usd is not None:
            self.cost_usd = (self.cost_usd or 0.0) + cost_usd


@dataclass(frozen=True, slots=True)
class PersistedContinuation:
    """Privacy-minimized restart-safe continuation record."""

    continuation_id: str
    request_id: str
    question_digest: str
    rule_id: str
    option_ids: tuple[str, ...]
    semantic_version: str
    semantic_hash: str
    language: str
    steps_used: int
    clarification_rounds: int
    elapsed_ms: float
    expires_at: datetime


class AgentContinuationBackend(Protocol):
    def save_continuation(self, record: PersistedContinuation) -> None: ...

    def claim_continuation(self, continuation_id: str) -> PersistedContinuation | None: ...

    def release_continuation(self, continuation_id: str, *, retain: bool) -> None: ...

    def cancel_continuation(self, continuation_id: str) -> PersistedContinuation | None: ...


class AgentSessionStore:
    """Bounded TTL continuation store with an optional durable safe backend."""

    def __init__(
        self,
        *,
        max_sessions: int = 1_000,
        backend: AgentContinuationBackend | None = None,
    ) -> None:
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        self._max_sessions = max_sessions
        self._backend = backend
        self._sessions: dict[str, tuple[datetime, AgentSession]] = {}
        self._claimed: set[str] = set()
        self._lock = RLock()

    def put(self, session: AgentSession) -> None:
        expires = datetime.now(UTC) + timedelta(seconds=session.limits.continuation_ttl_seconds)
        clarification = session.clarification
        resolution = session.semantic_resolution
        if clarification is None or resolution is None or resolution.clarification is None:
            raise ValueError("only a pending clarification may be persisted")
        persisted = PersistedContinuation(
            continuation_id=session.session_id,
            request_id=session.request_id,
            question_digest=continuation_question_digest(session.question),
            rule_id=resolution.clarification.rule_id,
            option_ids=tuple(option.option_id for option in clarification.options),
            semantic_version=resolution.semantic_version,
            semantic_hash=resolution.content_hash,
            language=resolution.language.value,
            steps_used=session.steps_used,
            clarification_rounds=session.clarification_rounds,
            elapsed_ms=session.elapsed_ms,
            expires_at=expires,
        )
        with self._lock:
            self._purge_locked()
            if len(self._sessions) >= self._max_sessions:
                oldest = min(self._sessions, key=lambda key: self._sessions[key][0])
                self._sessions.pop(oldest, None)
                self._claimed.discard(oldest)
            self._sessions[session.session_id] = (expires, session)
            if self._backend is not None:
                self._backend.save_continuation(persisted)

    def claim(
        self,
        continuation_id: str,
        *,
        question: str,
        services: AgentServices,
        limits: AgentLimits,
    ) -> AgentSession:
        with self._lock:
            self._purge_locked()
            backend = self._backend
            if continuation_id in self._claimed:
                raise AgentContinuationError("continuation is invalid, expired, or busy")
            local = self._sessions.get(continuation_id)
            persisted = backend.claim_continuation(continuation_id) if backend is not None else None
            if backend is not None and persisted is None:
                raise AgentContinuationError("continuation is invalid, expired, or busy")
            if local is None and persisted is None:
                raise AgentContinuationError("continuation is invalid, expired, or busy")
            if persisted is not None and persisted.question_digest != continuation_question_digest(
                question
            ):
                if backend is None:
                    raise AgentContinuationError("continuation backend is unavailable")
                backend.release_continuation(continuation_id, retain=True)
                raise AgentContinuationError("continuation does not match the original question")
            if local is not None:
                session = local[1]
                if continuation_question_digest(session.question) != continuation_question_digest(
                    question
                ):
                    if self._backend is not None:
                        self._backend.release_continuation(continuation_id, retain=True)
                    raise AgentContinuationError(
                        "continuation does not match the original question"
                    )
            else:
                if persisted is None:
                    raise AgentContinuationError("continuation is unavailable")
                resolution = services.semantic_service.resolve(question)
                decision = resolution.clarification
                option_ids = _option_ids_for_rule(resolution, persisted.rule_id)
                if (
                    decision is None
                    or decision.rule_id != persisted.rule_id
                    or resolution.semantic_version != persisted.semantic_version
                    or resolution.content_hash != persisted.semantic_hash
                    or option_ids != persisted.option_ids
                ):
                    if self._backend is not None:
                        self._backend.release_continuation(continuation_id, retain=True)
                    raise AgentContinuationError(
                        "continuation is incompatible with the active semantic layer"
                    )
                session = AgentSession(
                    request_id=persisted.request_id,
                    session_id=persisted.continuation_id,
                    question=question,
                    services=services,
                    limits=limits,
                    state=AgentState.CLARIFICATION_REQUIRED,
                    active_started_at=None,
                    elapsed_before_pause_ms=persisted.elapsed_ms,
                    steps_used=persisted.steps_used,
                    clarification_rounds=persisted.clarification_rounds,
                    language=resolution.language,
                    semantic_resolution=resolution,
                )
                self._sessions[continuation_id] = (persisted.expires_at, session)
            self._claimed.add(continuation_id)
            return session

    def release(self, continuation_id: str, *, retain: bool) -> None:
        with self._lock:
            self._claimed.discard(continuation_id)
            if not retain:
                self._sessions.pop(continuation_id, None)
            if self._backend is not None:
                self._backend.release_continuation(continuation_id, retain=retain)

    def cancel(self, continuation_id: str) -> str:
        with self._lock:
            self._purge_locked()
            if continuation_id in self._claimed:
                raise AgentContinuationError("continuation is currently busy")
            local = self._sessions.get(continuation_id)
            backend = self._backend
            persisted = (
                backend.cancel_continuation(continuation_id) if backend is not None else None
            )
            if backend is not None and persisted is None:
                raise AgentContinuationError("continuation is invalid, expired, or busy")
            if local is None and persisted is None:
                raise AgentContinuationError("continuation is invalid or expired")
            self._sessions.pop(continuation_id, None)
            if local is not None:
                return local[1].session_id
            if persisted is None:
                raise AgentContinuationError("continuation is invalid or expired")
            return persisted.continuation_id

    def _purge_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [key for key, (expiry, _) in self._sessions.items() if expiry <= now]
        for key in expired:
            self._sessions.pop(key, None)
            self._claimed.discard(key)


def continuation_question_digest(question: str) -> str:
    normalized = " ".join(question.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _option_ids_for_rule(
    resolution: SemanticResolution,
    rule_id: str,
) -> tuple[str, ...]:
    rule = next(
        (
            term.ambiguity
            for term in resolution.matched_terms
            if term.ambiguity is not None and term.ambiguity.rule_id == rule_id
        ),
        None,
    )
    return tuple(option.option_id for option in rule.options) if rule is not None else ()
