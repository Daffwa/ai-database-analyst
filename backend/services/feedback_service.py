"""Fixed-choice feedback collection over safe in-memory history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock

from backend.core.errors import InvalidRequestError
from backend.core.logging import get_logger
from backend.schemas.result import FeedbackRating, FeedbackRecord
from backend.services.query_history import QueryHistoryService

LOGGER = get_logger(__name__)


class FeedbackService:
    """Save one current rating per known request without free-form content."""

    def __init__(
        self,
        history: QueryHistoryService,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._history = history
        self._records: dict[str, FeedbackRecord] = {}
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = RLock()

    def submit(self, request_id: str, rating: FeedbackRating) -> FeedbackRecord:
        """Create or replace a rating only for a request present in history."""

        normalized_request_id = request_id.strip()
        if not normalized_request_id:
            raise InvalidRequestError("Request ID must not be empty.")
        if self._history.attach_feedback(normalized_request_id, rating) is None:
            raise InvalidRequestError("Feedback requires a request from the current history.")
        record = FeedbackRecord(
            request_id=normalized_request_id,
            rating=rating,
            created_at=self._now().isoformat(),
        )
        with self._lock:
            self._records[normalized_request_id] = record
        LOGGER.info(
            "Query feedback recorded",
            extra={"request_id": normalized_request_id, "feedback_rating": rating.value},
        )
        return record

    def list(self) -> tuple[FeedbackRecord, ...]:
        """Return feedback records in insertion order."""

        with self._lock:
            return tuple(self._records.values())
