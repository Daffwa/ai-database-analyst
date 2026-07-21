"""Tests for the closed Stage 3 catalog and result identity."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from backend.core.errors import EvaluationBaselineError
from backend.evaluation.mini_cases import (
    MINI_EVALUATION_CASES,
    fake_responses,
    find_case,
)
from backend.evaluation.runner import TrustedDemoRunner, result_sha256
from backend.schemas.database import QueryResult
from backend.schemas.llm import (
    LLMIntent,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
    StructuredSQLProposal,
)
from backend.services.orchestrator import QueryOrchestrator
from backend.services.query_executor import ManualQueryExecutor


class _StubOrchestrator(QueryOrchestrator):
    def __init__(self, response: QueryResponse) -> None:
        self._response = response

    async def process(self, question: str) -> QueryResponse:
        return self._response


class _StubExecutor(ManualQueryExecutor):
    def __init__(self, result: QueryResult) -> None:
        self._result = result

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        return self._result


def test_catalog_contains_twenty_unique_non_placeholder_baselines() -> None:
    assert len(MINI_EVALUATION_CASES) == 20
    assert len({case.case_id for case in MINI_EVALUATION_CASES}) == 20
    assert len({case.question for case in MINI_EVALUATION_CASES}) == 20
    assert all(case.expected_result_sha256 != "0" * 64 for case in MINI_EVALUATION_CASES)
    assert all(case.proposal().intent is LLMIntent.ANALYSIS for case in MINI_EVALUATION_CASES)


def test_fake_responses_and_normalized_case_lookup_are_deterministic() -> None:
    responses = fake_responses()
    first = MINI_EVALUATION_CASES[0]

    proposal = StructuredSQLProposal.model_validate_json(responses[first.question])
    found = find_case(f"  {first.question.upper()}  ")

    assert proposal.sql == first.sql
    assert found == first
    assert find_case("not in catalog") is None


def test_result_hash_excludes_latency_and_includes_data() -> None:
    first = QueryResult(
        columns=("count",),
        rows=((59,),),
        row_count=1,
        truncated=False,
        execution_time_ms=1,
        response_bytes=10,
    )
    same_data = first.model_copy(update={"execution_time_ms": 99, "response_bytes": 999})
    changed = first.model_copy(update={"rows": ((60,),)})

    assert result_sha256(first) == result_sha256(same_data)
    assert result_sha256(first) != result_sha256(changed)


def _first_case_response() -> QueryResponse:
    case = MINI_EVALUATION_CASES[0]
    proposal = case.proposal()
    return QueryResponse(
        request_id="request-1",
        status=QueryStatus.GENERATED_PENDING_SECURITY,
        language=proposal.language,
        generated_sql=proposal.sql,
        assumptions=proposal.assumptions,
        tables=proposal.tables,
        columns=proposal.columns,
        confidence=proposal.confidence,
        reasoning_summary=proposal.reasoning_summary,
        clarification_question=None,
        prompt_version="v1",
        schema_hash="schema-hash",
        provider="fake",
        model="fake-deterministic",
        llm_latency_ms=1,
        pipeline=(PipelineEvent(stage=PipelineStage.COMPLETED),),
        warnings=("warning",),
    )


@pytest.mark.parametrize(
    ("response_updates", "result"),
    [
        (
            {"generated_sql": "SELECT 60 AS customer_count"},
            QueryResult(
                columns=("customer_count",),
                rows=((59,),),
                row_count=1,
                truncated=False,
                execution_time_ms=1,
                response_bytes=10,
            ),
        ),
        (
            {},
            QueryResult(
                columns=("wrong",),
                rows=((59,),),
                row_count=1,
                truncated=False,
                execution_time_ms=1,
                response_bytes=10,
            ),
        ),
        (
            {},
            QueryResult(
                columns=("customer_count",),
                rows=((60,),),
                row_count=1,
                truncated=False,
                execution_time_ms=1,
                response_bytes=10,
            ),
        ),
    ],
)
def test_trusted_runner_fails_closed_on_proposal_column_or_result_drift(
    response_updates: dict[str, Any],
    result: QueryResult,
) -> None:
    response = _first_case_response().model_copy(update=response_updates)
    runner = TrustedDemoRunner(_StubOrchestrator(response), _StubExecutor(result))

    with pytest.raises(EvaluationBaselineError):
        asyncio.run(runner.run(MINI_EVALUATION_CASES[0].question))
