"""FastAPI contract, DI, CORS, protection, and safe-error tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.core.config import AppSettings
from backend.schemas.llm import (
    LanguageCode,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)
from backend.schemas.result import (
    FeedbackRating,
    FeedbackRecord,
    HistoryEntry,
    SafeSystemInfo,
    UXState,
)
from backend.services.experience_metadata import DatabaseExplorerService
from backend.services.schema_service import load_schema_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _response(question: str) -> QueryResponse:
    if question == "explode":
        raise RuntimeError("internal host=secret-db password=never-expose")
    status = QueryStatus.CLARIFICATION_REQUIRED if question == "ambiguous" else QueryStatus.SUCCESS
    return QueryResponse(
        request_id=f"request-{question}",
        status=status,
        language=LanguageCode.INDONESIAN,
        generated_sql=None if status is QueryStatus.CLARIFICATION_REQUIRED else "SELECT 1",
        executed_sql=None if status is QueryStatus.CLARIFICATION_REQUIRED else "SELECT 1",
        assumptions=(),
        tables=(),
        columns=(),
        confidence=1.0,
        reasoning_summary="Ringkasan aman.",
        clarification_question=(
            "Pilih definisi." if status is QueryStatus.CLARIFICATION_REQUIRED else None
        ),
        prompt_version="v2",
        schema_hash="f" * 64,
        semantic_version="v1-postgresql",
        semantic_context_hash="e" * 64,
        provider="fake",
        model="fake-deterministic",
        llm_latency_ms=0.0,
        pipeline=(PipelineEvent(stage=PipelineStage.COMPLETED),),
        warnings=(),
        ui_state=(
            UXState.CLARIFICATION
            if status is QueryStatus.CLARIFICATION_REQUIRED
            else UXState.SUCCESS
        ),
    )


class FakeOrchestrator:
    async def process(self, question: str) -> QueryResponse:
        return _response(question)


class FakeMetadata:
    def __init__(self) -> None:
        self.responses: dict[str, QueryResponse] = {}
        self.feedback: dict[str, FeedbackRating] = {}

    def record_response(self, response: QueryResponse) -> None:
        self.responses[response.request_id] = response

    def list_history(self, *, limit: int, offset: int) -> tuple[HistoryEntry, ...]:
        values = tuple(self.responses.values())[offset : offset + limit]
        return tuple(
            HistoryEntry(
                request_id=response.request_id,
                created_at=datetime.now(UTC).isoformat(),
                status=response.status.value,
                ui_state=response.ui_state or UXState.PENDING,
                row_count=None,
                total_latency_ms=0,
                feedback=self.feedback.get(response.request_id),
            )
            for response in values
        )

    def submit_feedback(self, request_id: str, rating: FeedbackRating) -> FeedbackRecord:
        self.feedback[request_id] = rating
        return FeedbackRecord(
            request_id=request_id,
            rating=rating,
            created_at=datetime.now(UTC).isoformat(),
        )


class FakeRuntime:
    def __init__(self) -> None:
        snapshot = load_schema_snapshot(
            ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json"
        )
        self.orchestrator = FakeOrchestrator()
        self.metadata = FakeMetadata()
        self.database_explorer = DatabaseExplorerService(
            snapshot, refreshed_at="2026-07-20T00:00:00+00:00"
        ).snapshot()
        self.system_info = SafeSystemInfo(
            app_environment="test",
            dataset="Chinook",
            schema_version=snapshot.schema_version,
            schema_hash=snapshot.schema_hash,
            semantic_version="v1-postgresql",
            semantic_content_hash="e" * 64,
            prompt_version="v2",
            provider="fake",
            model="fake-deterministic",
            sql_dialect="postgres",
            max_result_rows=500,
            max_csv_bytes=1_000_000,
            query_history_storage="postgresql_metadata",
            raw_question_stored=False,
            raw_sql_stored=False,
            result_rows_stored=False,
        )

    def health(self) -> bool:
        return True

    def close(self) -> None:
        return None


def _settings() -> AppSettings:
    return AppSettings(
        app_env="test",
        cors_allowed_origins=["http://localhost:8501"],
        evaluation_api_token="test-evaluation-token",
    )


def test_api_contract_query_schema_history_feedback_health_and_openapi() -> None:
    runtime = FakeRuntime()
    with TestClient(create_app(_settings(), runtime=runtime)) as client:
        health = client.get("/api/v1/health")
        query = client.post("/api/v1/query", json={"question": "normal"})
        schema = client.get("/api/v1/schema")
        history = client.get("/api/v1/history?limit=10&offset=0")
        feedback = client.post(
            "/api/v1/feedback",
            json={"request_id": "request-normal", "rating": "correct"},
        )
        openapi = client.get("/api/v1/openapi.json")
        metrics = client.get(
            "/api/v1/operations/metrics",
            headers={"X-Evaluation-Token": "test-evaluation-token"},
        )

    assert health.status_code == 200
    assert health.json() == {"status": "healthy", "api_version": "v1"}
    assert query.status_code == 200
    assert query.json()["status"] == "success"
    assert schema.status_code == 200 and len(schema.json()["tables"]) == 11
    assert history.status_code == 200 and len(history.json()["items"]) == 1
    assert feedback.status_code == 200 and feedback.json()["rating"] == "correct"
    assert openapi.status_code == 200
    assert "/api/v1/query" in openapi.json()["paths"]
    assert metrics.status_code == 200
    assert metrics.json()["analytics_requests_total"] == 1
    assert metrics.json()["success_total"] == 1
    serialized_metrics = metrics.text.casefold()
    assert "question" not in serialized_metrics
    assert "sql" not in serialized_metrics


def test_api_validation_errors_and_unhandled_errors_are_sanitized() -> None:
    app = create_app(_settings(), runtime=FakeRuntime())
    with TestClient(app, raise_server_exceptions=False) as client:
        validation = client.post("/api/v1/query", json={"question": "   "})
        failure = client.post("/api/v1/query", json={"question": "explode"})
    assert validation.status_code == 422
    assert validation.json()["error_code"] == "INVALID_REQUEST"
    assert validation.json()["request_id"]
    serialized = failure.text.casefold()
    assert failure.status_code == 500
    assert "secret-db" not in serialized
    assert "password" not in serialized
    assert failure.json()["error_code"] == "INTERNAL_ERROR"


def test_evaluation_endpoint_is_protected_and_returns_summary_only() -> None:
    with TestClient(create_app(_settings(), runtime=FakeRuntime())) as client:
        denied = client.get("/api/v1/evaluation/baseline")
        allowed = client.get(
            "/api/v1/evaluation/baseline",
            headers={"X-Evaluation-Token": "test-evaluation-token"},
        )
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "SECURITY_POLICY_VIOLATION"
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["case_count"] == 100
    assert payload["gate_passed"] is True
    assert "cases" not in payload
    assert "database_url" not in allowed.text.casefold()


def test_cors_is_limited_to_the_configured_frontend_origin() -> None:
    with TestClient(create_app(_settings(), runtime=FakeRuntime())) as client:
        allowed = client.options(
            "/api/v1/query",
            headers={
                "Origin": "http://localhost:8501",
                "Access-Control-Request-Method": "POST",
            },
        )
        denied = client.options(
            "/api/v1/query",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8501"
    assert "access-control-allow-origin" not in denied.headers


def test_request_id_middleware_accepts_uuid_and_rejects_arbitrary_text() -> None:
    accepted_id = str(UUID(int=2))
    with TestClient(create_app(_settings(), runtime=FakeRuntime())) as client:
        accepted = client.get("/api/v1/health", headers={"X-Request-ID": accepted_id})
        rejected = client.get("/api/v1/health", headers={"X-Request-ID": "untrusted-log-injection"})
    assert accepted.headers["X-Request-ID"] == accepted_id
    assert rejected.headers["X-Request-ID"] != "untrusted-log-injection"
    assert UUID(rejected.headers["X-Request-ID"])
