"""Versioned API routes with no direct credential or engine exposure."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from starlette.concurrency import run_in_threadpool

from backend.api.dependencies import APIRuntime, get_runtime, require_evaluation_token
from backend.core.logging import get_logger
from backend.core.observability import OperationalMetrics
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


@router.get("/schema", response_model=DatabaseExplorerSnapshot, tags=["analytics"])
async def schema(
    runtime: Annotated[APIRuntime, Depends(get_runtime)],
) -> DatabaseExplorerSnapshot:
    return runtime.database_explorer


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
