"""Bounded in-memory query history with privacy-minimized metadata."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock

from backend.schemas.llm import QueryResponse, QueryStatus
from backend.schemas.result import FeedbackRating, HistoryEntry, UXState


class QueryHistoryService:
    """Keep recent safe metadata without questions, SQL text, or result rows."""

    def __init__(
        self,
        *,
        max_entries: int = 100,
        enabled: bool = True,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")
        self._entries: deque[HistoryEntry] = deque(maxlen=max_entries)
        self._enabled = enabled
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = RLock()

    def record(self, response: QueryResponse) -> HistoryEntry | None:
        """Record a completed response using an explicit safe-field allowlist."""

        if not self._enabled:
            return None
        entry = HistoryEntry(
            request_id=response.request_id,
            created_at=self._now().isoformat(),
            status=response.status.value,
            ui_state=response.ui_state or _ui_state(response.status),
            sql_fingerprint=(response.validation.fingerprint if response.validation else None),
            row_count=(response.result.row_count if response.result else None),
            truncated=(response.result.truncated if response.result else False),
            total_latency_ms=response.llm_latency_ms + (response.database_latency_ms or 0.0),
        )
        with self._lock:
            self._entries.appendleft(entry)
        return entry

    def list(self) -> tuple[HistoryEntry, ...]:
        """Return newest-first immutable history."""

        with self._lock:
            return tuple(self._entries)

    def attach_feedback(
        self,
        request_id: str,
        rating: FeedbackRating,
    ) -> HistoryEntry | None:
        """Attach a fixed rating to an existing request without adding raw text."""

        with self._lock:
            for index, entry in enumerate(self._entries):
                if entry.request_id == request_id:
                    updated = entry.model_copy(update={"feedback": rating})
                    self._entries[index] = updated
                    return updated
        return None


def _ui_state(status: QueryStatus) -> UXState:
    return {
        QueryStatus.SUCCESS: UXState.SUCCESS,
        QueryStatus.TRUSTED_DEMO_SUCCESS: UXState.SUCCESS,
        QueryStatus.EMPTY_RESULT: UXState.EMPTY,
        QueryStatus.CLARIFICATION_REQUIRED: UXState.CLARIFICATION,
        QueryStatus.BLOCKED: UXState.BLOCKED,
        QueryStatus.UNSUPPORTED: UXState.UNSUPPORTED,
        QueryStatus.GENERATED_PENDING_SECURITY: UXState.PENDING,
    }[status]
