"""Tahap 4 security gate and read-only execution orchestration."""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.schemas.llm import PipelineEvent, PipelineStage, QueryResponse, QueryStatus
from backend.services.orchestrator import QueryProcessor
from backend.services.query_executor import QueryExecutor
from backend.services.sql_security import SQLSecurityService

STAGE_4_WARNING = (
    "Tahap 4 AST security gate passed; the SQLite MVP is still not a production "
    "authorization boundary."
)
POSTGRESQL_SECURITY_WARNING = (
    "SQL passed the deterministic AST policy and executed through the PostgreSQL "
    "analytics_readonly role in a read-only transaction."
)
LOGGER = get_logger(__name__)


class SecureQueryOrchestrator:
    """Validate every generated SQL AST before passing rewritten SQL to execution."""

    def __init__(
        self,
        generator_orchestrator: QueryProcessor,
        validator: SQLSecurityService,
        executor: QueryExecutor,
        *,
        success_warning: str = STAGE_4_WARNING,
    ) -> None:
        self._generator_orchestrator = generator_orchestrator
        self._validator = validator
        self._executor = executor
        self._success_warning = success_warning

    async def process(self, question: str) -> QueryResponse:
        response = await self._generator_orchestrator.process(question)
        if response.status is not QueryStatus.GENERATED_PENDING_SECURITY:
            return response
        if response.generated_sql is None:
            _log_security_decision(
                response.request_id, safe=False, violation_codes=("missing_sql",)
            )
            return response.model_copy(
                update={
                    "status": QueryStatus.BLOCKED,
                    "pipeline": _finish_pipeline(
                        response,
                        PipelineEvent(stage=PipelineStage.SECURITY_BLOCKED),
                    ),
                }
            )

        validation = self._validator.validate(
            response.generated_sql,
            declared_tables=response.tables,
            declared_columns=response.columns,
        )
        if not validation.safe or validation.executed_sql is None:
            _log_security_decision(
                response.request_id,
                safe=False,
                fingerprint=validation.fingerprint,
                tables=validation.tables,
                violation_codes=tuple(violation.code.value for violation in validation.violations),
            )
            return response.model_copy(
                update={
                    "status": QueryStatus.BLOCKED,
                    "validation": validation,
                    "pipeline": _finish_pipeline(
                        response,
                        PipelineEvent(stage=PipelineStage.SECURITY_BLOCKED),
                    ),
                    "warnings": ("Generated SQL was blocked by the deterministic AST policy.",),
                }
            )

        result = self._executor.execute(validation.executed_sql)
        _log_security_decision(
            response.request_id,
            safe=True,
            fingerprint=validation.fingerprint,
            tables=validation.tables,
            limit_applied=validation.limit_applied,
        )
        return response.model_copy(
            update={
                "status": QueryStatus.SUCCESS,
                "executed_sql": validation.executed_sql,
                "result": result,
                "validation": validation,
                "database_latency_ms": result.execution_time_ms,
                "pipeline": _finish_pipeline(
                    response,
                    PipelineEvent(stage=PipelineStage.SECURITY_VALIDATED),
                    PipelineEvent(
                        stage=PipelineStage.QUERY_EXECUTED,
                        latency_ms=result.execution_time_ms,
                    ),
                ),
                "warnings": (self._success_warning,),
            }
        )


def _finish_pipeline(
    response: QueryResponse,
    *events: PipelineEvent,
) -> tuple[PipelineEvent, ...]:
    retained = tuple(
        event
        for event in response.pipeline
        if event.stage not in {PipelineStage.AWAITING_SECURITY_VALIDATION, PipelineStage.COMPLETED}
    )
    return (*retained, *events, PipelineEvent(stage=PipelineStage.COMPLETED))


def _log_security_decision(
    request_id: str,
    *,
    safe: bool,
    fingerprint: str | None = None,
    tables: tuple[str, ...] = (),
    violation_codes: tuple[str, ...] = (),
    limit_applied: bool = False,
) -> None:
    """Record a decision without logging raw question, SQL, or result rows."""

    LOGGER.info(
        "SQL security decision",
        extra={
            "request_id": request_id,
            "security_safe": safe,
            "sql_fingerprint": fingerprint,
            "tables": tables,
            "violation_codes": violation_codes,
            "limit_applied": limit_applied,
        },
    )
