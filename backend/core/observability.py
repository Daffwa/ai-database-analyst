"""Request correlation and privacy-safe in-process operational metrics."""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar, Token
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from uuid import UUID, uuid4

from backend.schemas.llm import QueryResponse, QueryStatus

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)


def valid_request_id(value: str | None) -> str | None:
    """Accept canonical UUIDs only so arbitrary client text never reaches logs."""

    if not value or len(value) > 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return str(parsed) if str(parsed) == value.casefold() else None


def new_request_id(candidate: str | None = None) -> str:
    """Return a validated caller correlation ID or a server-generated UUID."""

    return valid_request_id(candidate) or str(uuid4())


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind one validated request ID for the current async execution context."""

    normalized = valid_request_id(request_id)
    if normalized is None:
        raise ValueError("request_id must be a canonical UUID")
    return _REQUEST_ID.set(normalized)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the preceding request context."""

    _REQUEST_ID.reset(token)


def current_request_id() -> str | None:
    """Return the current correlation identifier when running inside the API."""

    return _REQUEST_ID.get()


@dataclass(frozen=True, slots=True)
class OperationalMetricsSnapshot:
    """Safe aggregate counters; no question, SQL, row, URL, or credential fields."""

    http_requests_total: int
    analytics_requests_total: int
    uptime_seconds: float
    http_requests_per_second: float
    success_total: int
    success_rate: float
    blocked_total: int
    blocked_rate: float
    clarification_total: int
    clarification_rate: float
    timeout_total: int
    timeout_rate: float
    repair_attempts_total: int
    repair_rate: float
    error_total: int
    average_latency_ms: float | None
    max_latency_ms: float | None
    status_counts: dict[str, int]
    input_tokens_total: int | None
    output_tokens_total: int | None


class OperationalMetrics:
    """Small thread-safe process metrics for the single-process portfolio API."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._started_at = perf_counter()
        self._http_requests = 0
        self._analytics_requests = 0
        self._status_counts: Counter[str] = Counter()
        self._timeout_count = 0
        self._error_count = 0
        self._repair_attempts = 0
        self._latency_count = 0
        self._latency_total_ms = 0.0
        self._latency_max_ms = 0.0

    def record_http(self, *, latency_ms: float) -> None:
        """Count one HTTP request and its bounded aggregate latency."""

        with self._lock:
            self._http_requests += 1
            self._latency_count += 1
            self._latency_total_ms += max(0.0, latency_ms)
            self._latency_max_ms = max(self._latency_max_ms, latency_ms)

    def record_query(self, response: QueryResponse, *, repair_attempts: int = 0) -> None:
        """Count one completed analytics state without retaining its payload."""

        with self._lock:
            self._analytics_requests += 1
            self._status_counts[response.status.value] += 1
            self._repair_attempts += max(0, repair_attempts)

    def record_query_error(self, *, timeout: bool) -> None:
        """Count a failed analytics request using only a stable category."""

        with self._lock:
            self._analytics_requests += 1
            self._error_count += 1
            if timeout:
                self._timeout_count += 1

    def snapshot(self) -> OperationalMetricsSnapshot:
        """Copy the current aggregate state under one lock."""

        with self._lock:
            status_counts = dict(sorted(self._status_counts.items()))
            uptime_seconds = max(0.0, perf_counter() - self._started_at)
            analytics_denominator = max(1, self._analytics_requests)
            success_total = sum(
                status_counts.get(status.value, 0)
                for status in (
                    QueryStatus.SUCCESS,
                    QueryStatus.TRUSTED_DEMO_SUCCESS,
                    QueryStatus.EMPTY_RESULT,
                )
            )
            blocked_total = status_counts.get(QueryStatus.BLOCKED.value, 0)
            clarification_total = status_counts.get(QueryStatus.CLARIFICATION_REQUIRED.value, 0)
            latency_average = (
                self._latency_total_ms / self._latency_count if self._latency_count else None
            )
            latency_max = self._latency_max_ms if self._latency_count else None
            return OperationalMetricsSnapshot(
                http_requests_total=self._http_requests,
                analytics_requests_total=self._analytics_requests,
                uptime_seconds=round(uptime_seconds, 3),
                http_requests_per_second=round(self._http_requests / max(uptime_seconds, 0.001), 6),
                success_total=success_total,
                success_rate=round(success_total / analytics_denominator, 6),
                blocked_total=blocked_total,
                blocked_rate=round(blocked_total / analytics_denominator, 6),
                clarification_total=clarification_total,
                clarification_rate=round(clarification_total / analytics_denominator, 6),
                timeout_total=self._timeout_count,
                timeout_rate=round(self._timeout_count / analytics_denominator, 6),
                repair_attempts_total=self._repair_attempts,
                repair_rate=round(self._repair_attempts / analytics_denominator, 6),
                error_total=self._error_count,
                average_latency_ms=(
                    round(latency_average, 3) if latency_average is not None else None
                ),
                max_latency_ms=round(latency_max, 3) if latency_max is not None else None,
                status_counts=status_counts,
                input_tokens_total=None,
                output_tokens_total=None,
            )
