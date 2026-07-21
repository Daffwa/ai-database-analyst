"""End-to-end regression tests for the semantic and secured Tahap 5 runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.core.config import AppSettings
from backend.evaluation.runner import run_mini_evaluation
from backend.runtime.stage5 import Stage5Runtime, create_stage5_runtime
from backend.schemas.llm import PipelineStage, QueryStatus

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / "data" / "processed" / "chinook.sqlite"


@pytest.fixture(scope="module")
def stage5_runtime() -> Iterator[Stage5Runtime]:
    if not DATABASE_PATH.is_file():
        pytest.skip("Run `python scripts/bootstrap_data.py` before integration tests.")
    runtime = create_stage5_runtime(ROOT, AppSettings(_env_file=None))
    yield runtime
    runtime.close()


@pytest.mark.integration
@pytest.mark.evaluation
def test_semantic_change_keeps_all_twenty_database_baselines_green(
    stage5_runtime: Stage5Runtime,
) -> None:
    summary = asyncio.run(run_mini_evaluation(stage5_runtime.demo_runner))

    assert summary.case_count == 20
    assert summary.execution_success == 20
    assert summary.result_baseline_match == 20


@pytest.mark.integration
def test_clear_question_carries_semantic_provenance_through_safe_execution(
    stage5_runtime: Stage5Runtime,
) -> None:
    response = asyncio.run(stage5_runtime.demo_runner.run("Berapa jumlah pelanggan?"))

    assert response.status is QueryStatus.SUCCESS
    assert response.result is not None
    assert response.result.rows == ((59,),)
    assert response.semantic_version == "v1"
    assert response.semantic_context_hash == stage5_runtime.semantic_validation.content_hash
    assert response.matched_metric_ids == ("customer_count",)
    assert response.verified_query_ids == ("customer_count",)
    assert PipelineStage.SECURITY_VALIDATED in {event.stage for event in response.pipeline}


@pytest.mark.integration
def test_ambiguous_question_never_generates_or_executes_sql(
    stage5_runtime: Stage5Runtime,
) -> None:
    response = asyncio.run(stage5_runtime.demo_runner.run("Siapa pelanggan terbaik?"))

    assert response.status is QueryStatus.CLARIFICATION_REQUIRED
    assert response.generated_sql is None
    assert response.executed_sql is None
    assert response.result is None
    assert response.llm_latency_ms == 0
    assert "Total belanja" in (response.clarification_question or "")
