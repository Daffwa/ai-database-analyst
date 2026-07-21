"""End-to-end offline verification of the formal Tahap 7 runner."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.core.config import AppSettings
from backend.evaluation.case_loader import load_evaluation_dataset
from backend.evaluation.stage7_runner import (
    fake_responses_for_dataset,
    run_stage7_evaluation,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.evaluation
def test_formal_offline_evaluation_passes_complete_gate() -> None:
    dataset = load_evaluation_dataset(ROOT / "data" / "evaluation" / "stage-7-v1.jsonl")
    report = asyncio.run(run_stage7_evaluation(ROOT, AppSettings(app_log_level="WARNING"), dataset))

    assert report.gate_passed
    assert report.metrics.case_count == 100
    assert report.metrics.execution_accuracy == 1.0
    assert report.metrics.schema_hallucination_rate == 0.0
    assert report.metrics.unsafe_blocking_rate == 1.0
    assert report.metrics.false_blocking_rate == 0.0
    assert report.metrics.clarification_accuracy == 1.0
    assert report.provenance.network_calls == 0
    assert not report.provenance.credentials_used
    assert not report.provenance.formal_real_model_quality_evaluation
    assert not report.failed_case_ids


def test_fake_dataset_responses_exclude_ambiguity_and_numeric_answers() -> None:
    dataset = load_evaluation_dataset(ROOT / "data" / "evaluation" / "stage-7-v1.jsonl")
    responses = fake_responses_for_dataset(dataset)

    assert len(responses) == 95
    assert all(
        case.question not in responses
        for case in dataset.cases
        if case.category.value == "ambiguity"
    )
    assert all("reasoning_summary" in payload for payload in responses.values())
