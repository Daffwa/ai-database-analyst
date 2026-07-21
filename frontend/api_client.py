"""Credential-free HTTP client used by the final Streamlit frontend."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from backend.schemas.api import APIFeedbackRequest, APIQueryRequest, HealthResponse, HistoryResponse
from backend.schemas.llm import QueryResponse
from backend.schemas.result import DatabaseExplorerSnapshot, FeedbackRating, FeedbackRecord


class APIClientError(RuntimeError):
    """Sanitized API failure safe for a frontend message."""

    def __init__(self, error_code: str, message: str, request_id: str | None = None) -> None:
        self.error_code = error_code
        self.public_message = message
        self.request_id = request_id
        super().__init__(message)


class AnalystAPIClient:
    """Small typed client; it never receives database credentials."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def health(self) -> HealthResponse:
        return HealthResponse.model_validate(self._request("GET", "/api/v1/health"))

    def query(self, question: str) -> QueryResponse:
        payload = APIQueryRequest(question=question)
        return QueryResponse.model_validate(
            self._request("POST", "/api/v1/query", json=payload.model_dump(mode="json"))
        )

    def schema(self) -> DatabaseExplorerSnapshot:
        return DatabaseExplorerSnapshot.model_validate(self._request("GET", "/api/v1/schema"))

    def history(self, *, limit: int = 50, offset: int = 0) -> HistoryResponse:
        return HistoryResponse.model_validate(
            self._request(
                "GET",
                "/api/v1/history",
                params={"limit": limit, "offset": offset},
            )
        )

    def feedback(self, request_id: str, rating: FeedbackRating) -> FeedbackRecord:
        payload = APIFeedbackRequest(request_id=request_id, rating=rating)
        return FeedbackRecord.model_validate(
            self._request("POST", "/api/v1/feedback", json=payload.model_dump(mode="json"))
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("X-Request-ID", str(uuid4()))
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise APIClientError("API_UNAVAILABLE", "Backend API tidak dapat dijangkau.") from exc
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            raise APIClientError(
                str(payload.get("error_code", "API_ERROR")),
                str(payload.get("message", "Permintaan API gagal.")),
                (
                    str(payload["request_id"])
                    if payload.get("request_id")
                    else response.headers.get("X-Request-ID")
                ),
            )
        try:
            return response.json()
        except ValueError as exc:
            raise APIClientError("API_RESPONSE_INVALID", "Respons API tidak valid.") from exc
