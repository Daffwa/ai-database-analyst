"""Safe closed-catalog execution and metrics for the Tahap 3 mini evaluation."""

from __future__ import annotations

import hashlib
import json
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from backend.core.errors import EvaluationBaselineError
from backend.evaluation.mini_cases import MINI_EVALUATION_CASES, find_case
from backend.schemas.database import QueryResult
from backend.schemas.llm import PipelineEvent, PipelineStage, QueryResponse, QueryStatus
from backend.services.orchestrator import QueryProcessor
from backend.services.query_executor import QueryExecutor


class MiniEvaluationSummary(BaseModel):
    """Aggregate deterministic results for the complete 20-case catalog."""

    model_config = ConfigDict(frozen=True)

    case_count: int = Field(ge=0)
    structured_output_valid: int = Field(ge=0)
    generated_sql_exact_match: int = Field(ge=0)
    execution_success: int = Field(ge=0)
    result_baseline_match: int = Field(ge=0)
    total_latency_ms: float = Field(ge=0)


class TrustedDemoRunner:
    """Execute only a catalog constant after exact proposal identity checks."""

    def __init__(
        self,
        orchestrator: QueryProcessor,
        executor: QueryExecutor,
    ) -> None:
        self._orchestrator = orchestrator
        self._executor = executor

    async def run(self, question: str) -> QueryResponse:
        response = await self._orchestrator.process(question)
        case = find_case(question)
        if case is None:
            return response
        if (
            response.generated_sql != case.sql
            or response.tables != case.tables
            or response.columns != case.columns
        ):
            raise EvaluationBaselineError()

        if response.status is QueryStatus.SUCCESS:
            if response.result is None or response.validation is None:
                raise EvaluationBaselineError()
            if result_sha256(response.result) != case.expected_result_sha256:
                raise EvaluationBaselineError()
            return response
        if response.status is not QueryStatus.GENERATED_PENDING_SECURITY:
            return response

        result = self._executor.execute(case.sql)
        if result.columns != case.expected_columns:
            raise EvaluationBaselineError()
        if result_sha256(result) != case.expected_result_sha256:
            raise EvaluationBaselineError()

        pipeline = (
            *(event for event in response.pipeline if event.stage is not PipelineStage.COMPLETED),
            PipelineEvent(
                stage=PipelineStage.TRUSTED_DEMO_EXECUTED,
                latency_ms=result.execution_time_ms,
            ),
            PipelineEvent(stage=PipelineStage.COMPLETED),
        )
        return response.model_copy(
            update={
                "status": QueryStatus.TRUSTED_DEMO_SUCCESS,
                "executed_sql": case.sql,
                "result": result,
                "database_latency_ms": result.execution_time_ms,
                "pipeline": pipeline,
                "warnings": (
                    *response.warnings,
                    "Executed SQL came from an exact-match trusted demo baseline.",
                ),
            }
        )


async def run_mini_evaluation(runner: TrustedDemoRunner) -> MiniEvaluationSummary:
    """Run all cases and fail immediately on any baseline mismatch."""

    started = perf_counter()
    responses = [await runner.run(case.question) for case in MINI_EVALUATION_CASES]
    successful = [
        response
        for response in responses
        if response.status in {QueryStatus.SUCCESS, QueryStatus.TRUSTED_DEMO_SUCCESS}
    ]
    count = len(successful)
    return MiniEvaluationSummary(
        case_count=len(MINI_EVALUATION_CASES),
        structured_output_valid=len(responses),
        generated_sql_exact_match=count,
        execution_success=count,
        result_baseline_match=count,
        total_latency_ms=(perf_counter() - started) * 1_000,
    )


def result_sha256(result: QueryResult) -> str:
    """Hash only normalized columns and rows, excluding timing metadata."""

    canonical = json.dumps(
        {
            "columns": result.model_dump(mode="json")["columns"],
            "rows": result.model_dump(mode="json")["rows"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
