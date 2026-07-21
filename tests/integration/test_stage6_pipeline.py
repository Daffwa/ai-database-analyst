"""End-to-end result and UX regressions for the Tahap 6 runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.core.config import AppSettings
from backend.evaluation.result_runner import run_result_evaluation
from backend.evaluation.runner import run_mini_evaluation
from backend.runtime.stage6 import Stage6Runtime, create_stage6_runtime
from backend.schemas.llm import PipelineStage, QueryStatus
from backend.schemas.result import ChartType, FeedbackRating, UXState

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / "data" / "processed" / "chinook.sqlite"


@pytest.fixture(scope="module")
def stage6_runtime() -> Iterator[Stage6Runtime]:
    if not DATABASE_PATH.is_file():
        pytest.skip("Run `python scripts/bootstrap_data.py` before integration tests.")
    runtime = create_stage6_runtime(ROOT, AppSettings(_env_file=None))
    yield runtime
    runtime.close()


@pytest.mark.integration
@pytest.mark.evaluation
def test_result_layer_keeps_all_twenty_database_baselines_green(
    stage6_runtime: Stage6Runtime,
) -> None:
    summary = asyncio.run(run_mini_evaluation(stage6_runtime.demo_runner))

    assert summary.case_count == 20
    assert summary.execution_success == 20
    assert summary.result_baseline_match == 20


@pytest.mark.integration
@pytest.mark.parametrize(
    ("question", "chart_type"),
    [
        ("Berapa jumlah pelanggan?", ChartType.KPI),
        ("Berapa jumlah pelanggan per negara?", ChartType.BAR),
        ("Bagaimana tren pendapatan setiap bulan?", ChartType.LINE),
    ],
)
def test_real_results_select_expected_chart_and_grounded_summary(
    stage6_runtime: Stage6Runtime,
    question: str,
    chart_type: ChartType,
) -> None:
    response = asyncio.run(stage6_runtime.demo_runner.run(question))

    assert response.status is QueryStatus.SUCCESS
    assert response.ui_state is UXState.SUCCESS
    assert response.result is not None
    assert response.presentation is not None
    assert response.presentation.rows == response.result.rows
    assert response.chart is not None and response.chart.type is chart_type
    allowed = set(response.result.columns)
    assert ({response.chart.x} if response.chart.x else set()) | set(response.chart.y) <= allowed
    for evidence in response.summary_evidence:
        column_index = response.result.columns.index(evidence.column)
        assert response.result.rows[evidence.row_index][column_index] == evidence.raw_value
    assert PipelineStage.RESULT_SUMMARIZED in {event.stage for event in response.pipeline}


@pytest.mark.integration
def test_clarification_is_a_visible_state_and_is_recorded_without_sql(
    stage6_runtime: Stage6Runtime,
) -> None:
    response = asyncio.run(stage6_runtime.demo_runner.run("Siapa pelanggan terbaik?"))

    assert response.status is QueryStatus.CLARIFICATION_REQUIRED
    assert response.ui_state is UXState.CLARIFICATION
    assert response.generated_sql is None
    assert response.chart is None
    entry = stage6_runtime.history.list()[0]
    assert entry.request_id == response.request_id
    assert entry.sql_fingerprint is None


@pytest.mark.integration
def test_feedback_csv_explorer_and_safe_system_info_share_the_stage6_runtime(
    stage6_runtime: Stage6Runtime,
) -> None:
    response = asyncio.run(stage6_runtime.demo_runner.run("Berapa jumlah pelanggan?"))
    assert response.result is not None

    feedback = stage6_runtime.feedback.submit(response.request_id, FeedbackRating.CORRECT)
    export = stage6_runtime.csv_export.export(response.request_id, response.result)
    system_json = stage6_runtime.system_info.model_dump_json()

    assert feedback.rating is FeedbackRating.CORRECT
    assert stage6_runtime.history.list()[0].feedback is FeedbackRating.CORRECT
    assert export.data.startswith(b"\xef\xbb\xbf")
    assert len(stage6_runtime.database_explorer.tables) == 11
    assert "api_key" not in system_json.casefold()
    assert "database_url" not in system_json.casefold()


@pytest.mark.integration
@pytest.mark.evaluation
def test_stage6_measured_evaluation_has_no_failed_cases(
    stage6_runtime: Stage6Runtime,
) -> None:
    summary = asyncio.run(run_result_evaluation(stage6_runtime))

    assert summary.case_count == 20
    assert summary.database_result_matches == 20
    assert summary.presentation_matches == 20
    assert summary.chart_contracts_valid == 20
    assert summary.expected_chart_case_count == 4
    assert summary.expected_chart_matches == 4
    assert summary.grounded_summaries == 20
    assert summary.csv_exports_valid == 20
    assert summary.empty_result_state_valid is True
    assert summary.feedback_saved is True
    assert summary.history_metadata_safe is True
    assert summary.system_info_safe is True
    assert not summary.failed_case_ids
