"""Closed end-to-end integration tests for the Tahap 4 secured pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.core.config import AppSettings
from backend.evaluation.runner import run_mini_evaluation
from backend.runtime.stage4 import Stage4Runtime, create_stage4_runtime
from backend.schemas.llm import PipelineStage, QueryStatus

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / "data" / "processed" / "chinook.sqlite"


@pytest.fixture(scope="module")
def stage4_runtime() -> Iterator[Stage4Runtime]:
    if not DATABASE_PATH.is_file():
        pytest.skip("Run `python scripts/bootstrap_data.py` before integration tests.")
    runtime = create_stage4_runtime(ROOT, AppSettings(_env_file=None))
    yield runtime
    runtime.close()


@pytest.mark.integration
@pytest.mark.evaluation
def test_all_twenty_cases_match_sql_execution_and_result_baselines(
    stage4_runtime: Stage4Runtime,
) -> None:
    summary = asyncio.run(run_mini_evaluation(stage4_runtime.demo_runner))

    assert summary.case_count == 20
    assert summary.structured_output_valid == 20
    assert summary.generated_sql_exact_match == 20
    assert summary.execution_success == 20
    assert summary.result_baseline_match == 20
    assert summary.total_latency_ms >= 0


@pytest.mark.integration
def test_demo_response_separates_generated_executed_sql_and_database_fact(
    stage4_runtime: Stage4Runtime,
) -> None:
    response = asyncio.run(stage4_runtime.demo_runner.run("Berapa jumlah pelanggan?"))

    assert response.status is QueryStatus.SUCCESS
    assert response.generated_sql == "SELECT COUNT(CustomerId) AS customer_count FROM Customer"
    assert response.executed_sql == (
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer LIMIT 500"
    )
    assert response.result is not None
    assert response.result.rows == ((59,),)
    assert response.database_latency_ms is not None
    assert response.llm_latency_ms >= 0
    stages = {event.stage for event in response.pipeline}
    assert PipelineStage.SECURITY_VALIDATED in stages
    assert PipelineStage.QUERY_EXECUTED in stages


@pytest.mark.integration
def test_unknown_question_is_not_executed(stage4_runtime: Stage4Runtime) -> None:
    response = asyncio.run(stage4_runtime.demo_runner.run("Tolong hapus semua pelanggan."))

    assert response.status is QueryStatus.UNSUPPORTED
    assert response.generated_sql is None
    assert response.executed_sql is None
    assert response.result is None
