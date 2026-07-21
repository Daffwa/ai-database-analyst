"""FastAPI dependency injection and protected evaluation authorization."""

from __future__ import annotations

import secrets
from typing import Protocol, cast

from fastapi import Header, HTTPException, Request, status

from backend.core.config import AppSettings
from backend.schemas.llm import QueryResponse
from backend.schemas.result import (
    DatabaseExplorerSnapshot,
    FeedbackRating,
    FeedbackRecord,
    HistoryEntry,
    SafeSystemInfo,
)
from backend.services.orchestrator import QueryProcessor


class MetadataStore(Protocol):
    def record_response(self, response: QueryResponse) -> None: ...

    def list_history(self, *, limit: int, offset: int) -> tuple[HistoryEntry, ...]: ...

    def submit_feedback(self, request_id: str, rating: FeedbackRating) -> FeedbackRecord: ...


class APIRuntime(Protocol):
    @property
    def orchestrator(self) -> QueryProcessor: ...

    @property
    def metadata(self) -> MetadataStore: ...

    @property
    def database_explorer(self) -> DatabaseExplorerSnapshot: ...

    @property
    def system_info(self) -> SafeSystemInfo: ...

    def health(self) -> bool: ...

    def close(self) -> None: ...


def get_runtime(request: Request) -> APIRuntime:
    return cast(APIRuntime, request.app.state.runtime)


def get_settings(request: Request) -> AppSettings:
    return cast(AppSettings, request.app.state.settings)


def require_evaluation_token(
    request: Request,
    x_evaluation_token: str | None = Header(default=None),
) -> None:
    settings = get_settings(request)
    configured = settings.evaluation_api_token
    if configured is None or not configured.get_secret_value():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if x_evaluation_token is None or not secrets.compare_digest(
        x_evaluation_token,
        configured.get_secret_value(),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
