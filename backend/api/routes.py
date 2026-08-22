"""Versioned API routes with no direct credential or engine exposure."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Annotated
from urllib.parse import unquote_to_bytes

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from starlette.concurrency import run_in_threadpool

from backend.api.dependencies import (
    APIRuntime,
    get_database_workspaces,
    get_runtime,
    require_evaluation_token,
)
from backend.core.errors import InvalidRequestError
from backend.core.logging import get_logger
from backend.core.observability import OperationalMetrics
from backend.schemas.agent import (
    AgentCancelRequest,
    AgentCancelResponse,
    AgentContinueRequest,
    AgentQueryRequest,
    AgentRunResponse,
)
from backend.schemas.api import (
    APIFeedbackRequest,
    APIQueryRequest,
    EvaluationBaselineResponse,
    HealthResponse,
    HistoryResponse,
    OperationalMetricsResponse,
)
from backend.schemas.llm import QueryResponse
from backend.schemas.result import (
    DatabaseExplorerSnapshot,
    FeedbackRecord,
)
from backend.schemas.workspace import DatabaseWorkspace, DatabaseWorkspaceDeleteResponse
from backend.services.database_workspace import DatabaseWorkspaceService

ROOT = Path(__file__).resolve().parents[2]
router = APIRouter(prefix="/api/v1")
LOGGER = get_logger(__name__)


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(
    response: Response,
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> HealthResponse:
    ready = await run_in_threadpool(runtime.health)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="healthy" if ready else "degraded", api_version="v1")


@router.post("/query", response_model=QueryResponse, tags=["analytics"])
async def query(
    payload: APIQueryRequest,
    request: Request,
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> QueryResponse:
    started = perf_counter()
    result = await runtime.orchestrator.process(payload.question)
    await run_in_threadpool(runtime.metadata.record_response, result)
    latency_ms = (perf_counter() - started) * 1_000
    metrics: OperationalMetrics = request.app.state.operational_metrics
    metrics.record_query(result)
    LOGGER.info(
        "Analytics request completed",
        extra={
            "request_id": result.request_id,
            "stage": "analytics_completed",
            "status": result.status.value,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "schema_hash": result.schema_hash,
            "sql_fingerprint": (
                result.validation.fingerprint if result.validation is not None else None
            ),
            "latency_ms": latency_ms,
            "row_count": result.result.row_count if result.result is not None else None,
            "error_code": None,
            "repair_attempts": 0,
            "input_tokens": None,
            "output_tokens": None,
        },
    )
    return result


@router.post("/agent/query", response_model=AgentRunResponse, tags=["agent"])
async def agent_query(
    payload: AgentQueryRequest,
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> AgentRunResponse:
    """Start one bounded tool-using run; the legacy query route remains compatible."""

    result = await runtime.agent.process(payload.question)
    _log_agent_result(result)
    return result


@router.post("/agent/continue", response_model=AgentRunResponse, tags=["agent"])
async def agent_continue(
    payload: AgentContinueRequest,
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> AgentRunResponse:
    """Resume only from an issued continuation and canonical option ID."""

    result = await runtime.agent.continue_with_choice(
        payload.continuation_id,
        payload.option_id,
        payload.question,
    )
    _log_agent_result(result)
    return result


@router.post("/agent/cancel", response_model=AgentCancelResponse, tags=["agent"])
async def agent_cancel(
    payload: AgentCancelRequest,
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> AgentCancelResponse:
    """Delete an unused clarification continuation."""

    return runtime.agent.cancel(payload.continuation_id)


@router.get("/schema", response_model=DatabaseExplorerSnapshot, tags=["analytics"])
async def schema(
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> DatabaseExplorerSnapshot:
    return runtime.database_explorer


@router.post(
    "/workspaces",
    response_model=DatabaseWorkspace,
    status_code=status.HTTP_201_CREATED,
    tags=["uploaded-databases"],
)
async def create_database_workspace(
    request: Request,
    encoded_filename: Annotated[
        str,
        Header(alias="X-Upload-Filename", min_length=1, max_length=765),
    ],
    workspaces: Annotated[DatabaseWorkspaceService, Depends(get_database_workspaces)],
) -> DatabaseWorkspace:
    """Upload bounded SQLite bytes into a new isolated, expiring workspace."""

    payload = await _read_bounded_upload(request, workspaces.max_upload_bytes)
    try:
        filename = unquote_to_bytes(encoded_filename).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError("The upload filename encoding is invalid.") from exc
    return await run_in_threadpool(workspaces.create, filename, payload)


@router.get(
    "/workspaces/{workspace_id}/schema",
    response_model=DatabaseExplorerSnapshot,
    tags=["uploaded-databases"],
)
async def database_workspace_schema(
    workspace_id: str,
    workspaces: Annotated[DatabaseWorkspaceService, Depends(get_database_workspaces)],
) -> DatabaseExplorerSnapshot:
    return await run_in_threadpool(workspaces.schema, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/query",
    response_model=QueryResponse,
    tags=["uploaded-databases"],
)
async def query_database_workspace(
    workspace_id: str,
    payload: APIQueryRequest,
    request: Request,
    workspaces: Annotated[DatabaseWorkspaceService, Depends(get_database_workspaces)],
) -> QueryResponse:
    """Generate, validate, and execute SQL only against one uploaded workspace."""

    started = perf_counter()
    result = await workspaces.query(workspace_id, payload.question)
    metrics: OperationalMetrics = request.app.state.operational_metrics
    metrics.record_query(result)
    LOGGER.info(
        "Uploaded database analytics request completed",
        extra={
            "request_id": result.request_id,
            "workspace_id": workspace_id,
            "stage": "uploaded_analytics_completed",
            "status": result.status.value,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "schema_hash": result.schema_hash,
            "sql_fingerprint": (
                result.validation.fingerprint if result.validation is not None else None
            ),
            "latency_ms": (perf_counter() - started) * 1_000,
            "row_count": result.result.row_count if result.result is not None else None,
            "error_code": None,
        },
    )
    return result


@router.delete(
    "/workspaces/{workspace_id}",
    response_model=DatabaseWorkspaceDeleteResponse,
    tags=["uploaded-databases"],
)
async def delete_database_workspace(
    workspace_id: str,
    workspaces: Annotated[DatabaseWorkspaceService, Depends(get_database_workspaces)],
) -> DatabaseWorkspaceDeleteResponse:
    return await run_in_threadpool(workspaces.delete, workspace_id)


@router.get("/history", response_model=HistoryResponse, tags=["metadata"])
async def history(
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HistoryResponse:
    items = await run_in_threadpool(
        runtime.metadata.list_history,
        limit=limit,
        offset=offset,
    )
    return HistoryResponse(items=items, limit=limit, offset=offset)


@router.post("/feedback", response_model=FeedbackRecord, tags=["metadata"])
async def feedback(
    payload: APIFeedbackRequest,
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> FeedbackRecord:
    return await run_in_threadpool(
        runtime.metadata.submit_feedback,
        payload.request_id,
        payload.rating,
    )


@router.get(
    "/evaluation/baseline",
    response_model=EvaluationBaselineResponse,
    tags=["evaluation"],
    dependencies=[Depends(require_evaluation_token)],
)
async def evaluation_baseline() -> EvaluationBaselineResponse:
    report = json.loads(
        (ROOT / "reports" / "evaluation" / "stage-7-baseline.json").read_text(encoding="utf-8")
    )
    metrics = report["metrics"]
    return EvaluationBaselineResponse(
        dataset_version=report["provenance"]["dataset_version"],
        dataset_sha256=report["provenance"]["dataset_sha256"],
        case_count=metrics["case_count"],
        passed_case_count=metrics["passed_case_count"],
        pass_rate=metrics["pass_rate"],
        execution_accuracy=metrics["execution_accuracy"],
        unsafe_blocking_rate=metrics["unsafe_blocking_rate"],
        gate_passed=report["gate_passed"],
    )


@router.get(
    "/operations/metrics",
    response_model=OperationalMetricsResponse,
    tags=["operations"],
    dependencies=[Depends(require_evaluation_token)],
)
async def operational_metrics(request: Request) -> OperationalMetricsResponse:
    """Return process aggregates without questions, SQL, rows, or credentials."""

    metrics: OperationalMetrics = request.app.state.operational_metrics
    return OperationalMetricsResponse.model_validate(metrics.snapshot(), from_attributes=True)


def _log_agent_result(result: AgentRunResponse) -> None:
    LOGGER.info(
        "Bounded agent request completed",
        extra={
            "request_id": result.request_id,
            "session_id": result.session_id,
            "stage": "bounded_agent_completed",
            "status": result.status.value,
            "stop_reason": result.stop_reason,
            "steps_used": result.budget.steps_used,
            "repair_attempts": result.budget.repairs_used,
            "latency_ms": result.budget.elapsed_ms,
            "provider": result.provider,
            "model": result.model,
            "sql_fingerprint": (
                result.result.sql_fingerprint if result.result is not None else None
            ),
        },
    )


async def _read_bounded_upload(request: Request, max_bytes: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise InvalidRequestError("The upload Content-Length is invalid.") from exc
        if declared_length > max_bytes:
            raise InvalidRequestError(
                "The uploaded file exceeds the configured size limit.",
                details={"max_bytes": max_bytes},
            )

    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > max_bytes:
            raise InvalidRequestError(
                "The uploaded file exceeds the configured size limit.",
                details={"max_bytes": max_bytes},
            )
        chunks.append(chunk)
    if received == 0:
        raise InvalidRequestError("The uploaded file is empty.")
    return b"".join(chunks)
