"""FastAPI application factory with owned lifespan and safe error contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.api.dependencies import APIRuntime
from backend.api.routes import router
from backend.core.config import AppSettings, get_settings
from backend.core.errors import AppError, ErrorCode
from backend.core.logging import get_logger
from backend.core.observability import (
    OperationalMetrics,
    bind_request_id,
    new_request_id,
    reset_request_id,
)
from backend.runtime.stage8 import create_stage8_runtime

ROOT = Path(__file__).resolve().parents[2]
LOGGER = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign one server-controlled identifier to every HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = new_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = bind_request_id(request_id)
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = (perf_counter() - started) * 1_000
            metrics: OperationalMetrics = request.app.state.operational_metrics
            metrics.record_http(latency_ms=latency_ms)
            LOGGER.info(
                "HTTP request completed",
                extra={
                    "request_id": request_id,
                    "stage": "http_completed",
                    "status": status_code,
                    "model": None,
                    "prompt_version": None,
                    "schema_hash": None,
                    "sql_fingerprint": None,
                    "latency_ms": latency_ms,
                    "row_count": None,
                    "error_code": "HTTP_ERROR" if status_code >= 400 else None,
                },
            )
            reset_request_id(token)


def create_app(
    settings: AppSettings | None = None,
    *,
    runtime: APIRuntime | None = None,
) -> FastAPI:
    """Create an app without opening a database connection at import time."""

    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = runtime is None
        active_runtime = runtime or create_stage8_runtime(ROOT, active_settings)
        app.state.runtime = active_runtime
        try:
            yield
        finally:
            if owned:
                active_runtime.close()

    app = FastAPI(
        title="AI Database Analyst API",
        version="0.9.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs" if active_settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.operational_metrics = OperationalMetrics()
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Evaluation-Token", "X-Request-ID"],
    )
    app.include_router(router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        status_code = {
            ErrorCode.INVALID_REQUEST: 400,
            ErrorCode.SECURITY_POLICY_VIOLATION: 403,
            ErrorCode.DATABASE_UNAVAILABLE: 503,
            ErrorCode.EXTERNAL_SERVICE_ERROR: 503,
            ErrorCode.QUERY_TIMEOUT: 504,
            ErrorCode.LLM_TIMEOUT: 504,
        }.get(exc.code, 500)
        _record_query_error(request, timeout=status_code == 504)
        return JSONResponse(
            status_code=status_code,
            content=exc.to_public_dict(request_id=request.state.request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        _record_query_error(request, timeout=False)
        return JSONResponse(
            status_code=422,
            content={
                "error_code": ErrorCode.INVALID_REQUEST.value,
                "message": "The request payload is invalid.",
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": (
                    ErrorCode.SECURITY_POLICY_VIOLATION.value
                    if exc.status_code == 403
                    else ErrorCode.INVALID_REQUEST.value
                ),
                "message": "The request is not allowed."
                if exc.status_code == 403
                else "Not found.",
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        _record_query_error(request, timeout=False)
        LOGGER.exception(
            "Unhandled API error",
            extra={"request_id": request.state.request_id, "error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error_code": ErrorCode.INTERNAL_ERROR.value,
                "message": "The request could not be completed.",
                "request_id": request.state.request_id,
            },
        )

    return app


def _record_query_error(request: Request, *, timeout: bool) -> None:
    if request.url.path == "/api/v1/query":
        metrics: OperationalMetrics = request.app.state.operational_metrics
        metrics.record_query_error(timeout=timeout)


def app() -> FastAPI:
    """Uvicorn factory target: ``backend.api.app:app --factory``."""

    return create_app()
