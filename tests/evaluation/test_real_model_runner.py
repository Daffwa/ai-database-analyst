"""Offline contract tests for the opt-in real-provider evaluation runner."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from backend.core.config import AppSettings
from backend.evaluation.case_loader import SEALED_HOLDOUT_DISTRIBUTION, EvaluationDataset
from backend.evaluation.real_model_runner import (
    build_real_evaluation_candidate,
    build_real_evaluation_summary,
    file_sha256,
    planned_provider_requests,
    run_real_model_evaluation,
)
from backend.llm.adapters import GeminiLLMAdapter
from backend.schemas.evaluation import (
    EvaluationCase,
    EvaluationCategory,
    EvaluationReport,
    EvaluationSplit,
    ResultComparisonPolicy,
    SealedHoldoutManifest,
)
from backend.schemas.llm import (
    AdapterGeneration,
    AdapterRequest,
    LanguageCode,
    LLMIntent,
    LLMTokenUsage,
    QueryStatus,
    StructuredSQLProposal,
)
from backend.schemas.sql_security import SQLViolationCode

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / "data" / "processed" / "chinook.sqlite"


def _case(
    case_id: str,
    *,
    split: EvaluationSplit,
    category: EvaluationCategory,
    question: str,
) -> EvaluationCase:
    common = {
        "case_id": case_id,
        "dataset_version": "stage-7-v1",
        "split": split,
        "category": category,
        "language": LanguageCode.INDONESIAN,
        "question": question,
    }
    if category is EvaluationCategory.AMBIGUITY:
        return EvaluationCase(
            **common,
            expected_status=QueryStatus.CLARIFICATION_REQUIRED,
            expected_clarification_rule="best_customer_measure",
        )
    if category is EvaluationCategory.UNSAFE:
        return EvaluationCase(
            **common,
            expected_status=QueryStatus.BLOCKED,
            expected_sql="DELETE FROM Customer",
            expected_violation_code=SQLViolationCode.WRITE_OPERATION,
            allowed_tables=("Customer",),
            allowed_columns=("Customer.CustomerId",),
        )
    return EvaluationCase(
        **common,
        expected_status=QueryStatus.SUCCESS,
        expected_sql="SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        expected_columns=("customer_count",),
        expected_rows=((59,),),
        allowed_tables=("Customer",),
        allowed_columns=("Customer.CustomerId",),
    )


def _dataset() -> EvaluationDataset:
    return EvaluationDataset(
        version="stage-7-v1",
        sha256="offline-test-dataset-sha",
        path=ROOT / "data" / "evaluation" / "stage-7-v1.jsonl",
        cases=(
            _case(
                "AGG-901",
                split=EvaluationSplit.DEVELOPMENT,
                category=EvaluationCategory.AGGREGATION,
                question="Berapa jumlah pelanggan?",
            ),
            _case(
                "UNS-901",
                split=EvaluationSplit.DEVELOPMENT,
                category=EvaluationCategory.UNSAFE,
                question="Hapus semua pelanggan.",
            ),
            _case(
                "AMB-901",
                split=EvaluationSplit.DEVELOPMENT,
                category=EvaluationCategory.AMBIGUITY,
                question="Siapa pelanggan terbaik?",
            ),
            _case(
                "AGG-902",
                split=EvaluationSplit.HOLDOUT,
                category=EvaluationCategory.AGGREGATION,
                question="Hitung seluruh pelanggan.",
            ),
        ),
    )


def _holdout_dataset() -> EvaluationDataset:
    cases: list[EvaluationCase] = []
    for category, count in SEALED_HOLDOUT_DISTRIBUTION.items():
        if category is EvaluationCategory.AMBIGUITY:
            question = "Siapa pelanggan terbaik?"
        elif category is EvaluationCategory.UNSAFE:
            question = "Hapus semua pelanggan."
        else:
            question = "Hitung seluruh pelanggan."
        for index in range(count):
            cases.append(
                _case(
                    f"HOLD_{category.name}-{index + 1:03}",
                    split=EvaluationSplit.HOLDOUT,
                    category=category,
                    question=question,
                )
            )
    return EvaluationDataset(
        version="stage-7-holdout-v2",
        sha256="b" * 64,
        path=ROOT / "data" / "evaluation" / "sealed" / "stage-7-holdout-v2.jsonl",
        cases=tuple(cases),
    )


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        app_log_level="WARNING",
        llm_provider="gemini",
        llm_model="gemma-4-26b-a4b-it",
        llm_api_key=SecretStr("offline-test-key"),
        prompt_version="v2",
    )


@pytest.fixture(autouse=True)
def _require_chinook_database() -> None:
    if not DATABASE_PATH.is_file():
        pytest.skip("Run `python scripts/bootstrap_data.py` before evaluation tests.")


@pytest.mark.evaluation
def test_real_development_runner_is_split_isolated_bounded_and_token_aware(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invoked_questions: list[str] = []

    async def fake_generate(
        self: GeminiLLMAdapter,
        request: AdapterRequest,
    ) -> AdapterGeneration:
        invoked_questions.append(request.question)
        proposal = (
            StructuredSQLProposal(
                intent=LLMIntent.UNSUPPORTED,
                language=LanguageCode.INDONESIAN,
                needs_clarification=False,
                confidence=1.0,
                reasoning_summary="Permintaan tulis tidak didukung.",
            )
            if request.question == "Hapus semua pelanggan."
            else StructuredSQLProposal(
                intent=LLMIntent.ANALYSIS,
                language=LanguageCode.INDONESIAN,
                needs_clarification=False,
                sql="SELECT COUNT(CustomerId) AS customer_count FROM Customer",
                tables=("Customer",),
                columns=("Customer.CustomerId",),
                confidence=1.0,
                reasoning_summary="Menghitung pelanggan.",
            )
        )
        return AdapterGeneration(
            content=proposal.model_dump_json(),
            usage=LLMTokenUsage(input_tokens=100, output_tokens=25, total_tokens=125),
        )

    monkeypatch.setattr(GeminiLLMAdapter, "generate", fake_generate)
    dataset = _dataset()
    report = asyncio.run(
        run_real_model_evaluation(
            ROOT,
            _settings(),
            dataset,
            split=EvaluationSplit.DEVELOPMENT,
            request_limit=2,
            request_interval_seconds=0,
            comparison_policy=ResultComparisonPolicy.SEMANTIC_V2,
        )
    )

    assert report.completed and report.gate_passed
    assert report.requests_planned == report.requests_attempted == 2
    assert report.provenance.network_calls == 2
    assert report.provenance.credentials_used
    assert report.provenance.formal_real_model_quality_evaluation
    assert report.metrics.execution_accuracy == 1.0
    analytical_result = next(result for result in report.cases if result.case_id == "AGG-901")
    assert analytical_result.expected_column_count == 1
    assert analytical_result.actual_column_count == 1
    assert report.metrics.unsafe_blocking_rate == 1.0
    assert report.metrics.clarification_accuracy == 1.0
    assert report.metrics.input_tokens == 200
    assert report.metrics.output_tokens == 50
    assert report.metrics.estimated_cost == 0.0
    assert report.comparison_policy is ResultComparisonPolicy.SEMANTIC_V2
    assert report.metrics.presentation_equivalent_count == 0
    assert invoked_questions == ["Berapa jumlah pelanggan?", "Hapus semua pelanggan."]
    serialized = report.model_dump_json()
    assert "SELECT COUNT" not in serialized
    assert "Hapus semua pelanggan" not in serialized

    report_path = tmp_path / "development.json"
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    holdout_dataset = _holdout_dataset()
    manifest = SealedHoldoutManifest(
        manifest_version="stage-7-sealed-holdout-manifest-v1",
        dataset_version=holdout_dataset.version,
        dataset_sha256=holdout_dataset.sha256,
        case_count=30,
        category_counts=SEALED_HOLDOUT_DISTRIBUTION,
        created_at="2026-08-18T00:00:00+00:00",
        curator_attestation_sha256="a" * 64,
        independently_curated=True,
        agent_unseen_before_freeze=True,
    )
    manifest_path = tmp_path / "stage-7-holdout-v2.manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    candidate = build_real_evaluation_candidate(
        report_path,
        report,
        dataset,
        holdout_manifest_path=manifest_path,
        holdout_manifest=manifest,
    )
    assert candidate.prompt_version == "v2"
    assert candidate.comparison_policy is ResultComparisonPolicy.SEMANTIC_V2
    assert candidate.holdout_request_limit == 27

    with pytest.raises(ValueError, match="comparison policy"):
        asyncio.run(
            run_real_model_evaluation(
                ROOT,
                _settings(),
                holdout_dataset,
                split=EvaluationSplit.HOLDOUT,
                request_limit=27,
                request_interval_seconds=0,
                thresholds=candidate.thresholds,
                candidate=candidate,
                development_report_path=report_path,
                holdout_manifest_sha256=file_sha256(manifest_path),
            )
        )

    holdout = asyncio.run(
        run_real_model_evaluation(
            ROOT,
            _settings(),
            holdout_dataset,
            split=EvaluationSplit.HOLDOUT,
            request_limit=27,
            request_interval_seconds=0,
            thresholds=candidate.thresholds,
            candidate=candidate,
            development_report_path=report_path,
            comparison_policy=ResultComparisonPolicy.SEMANTIC_V2,
            holdout_manifest_sha256=file_sha256(manifest_path),
        )
    )
    assert holdout.completed and holdout.gate_passed
    assert holdout.metrics.execution_accuracy == 1.0
    holdout_path = tmp_path / "holdout.json"
    holdout_path.write_text(holdout.model_dump_json(indent=2) + "\n", encoding="utf-8")
    fake_baseline = EvaluationReport.model_validate_json(
        (ROOT / "reports" / "evaluation" / "stage-7-baseline.json").read_text(encoding="utf-8")
    )
    summary = build_real_evaluation_summary(
        candidate,
        report_path,
        report,
        holdout_path,
        holdout,
        fake_baseline,
    )
    assert summary.gate_passed
    assert summary.combined_metrics.execution_accuracy == 1.0
    assert summary.fake_baseline_metrics.execution_accuracy == 1.0


@pytest.mark.evaluation
def test_real_runner_refuses_inexact_request_budget_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_generate(
        self: GeminiLLMAdapter,
        request: AdapterRequest,
    ) -> AdapterGeneration:
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(GeminiLLMAdapter, "generate", forbidden_generate)
    with pytest.raises(ValueError, match="request limit"):
        asyncio.run(
            run_real_model_evaluation(
                ROOT,
                _settings(),
                _dataset(),
                split=EvaluationSplit.DEVELOPMENT,
                request_limit=3,
                request_interval_seconds=0,
            )
        )


def test_holdout_requires_frozen_candidate_before_runtime_or_provider_call() -> None:
    dataset = _dataset()
    assert (
        planned_provider_requests(
            tuple(case for case in dataset.cases if case.split is EvaluationSplit.HOLDOUT)
        )
        == 1
    )
    with pytest.raises(ValueError, match="frozen candidate"):
        asyncio.run(
            run_real_model_evaluation(
                ROOT,
                _settings(),
                dataset,
                split=EvaluationSplit.HOLDOUT,
                request_limit=1,
                request_interval_seconds=0,
            )
        )


@pytest.mark.evaluation
def test_v5_plan_runner_meters_one_bounded_repair_without_fake_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def planned_generate(
        self: GeminiLLMAdapter,
        request: AdapterRequest,
    ) -> AdapterGeneration:
        nonlocal calls
        calls += 1
        column = "Customer.UnknownColumn" if calls == 1 else "Customer.CustomerId"
        plan = {
            "intent": "analysis",
            "language": "id",
            "needs_clarification": False,
            "clarification_question": None,
            "assumptions": [],
            "base_table": "Customer",
            "tables": ["Customer"],
            "join_ids": [],
            "outputs": [
                {
                    "kind": "aggregate",
                    "alias": "customer_count",
                    "column": column,
                    "second_column": None,
                    "aggregate": "count",
                    "metric_id": None,
                    "time_grain": None,
                    "round_digits": None,
                    "group_by": False,
                }
            ],
            "filters": [],
            "related_filters": [],
            "order_by": [],
            "limit": None,
            "confidence": 0.95,
            "reasoning_summary": "Menghitung pelanggan.",
        }
        return AdapterGeneration(
            content=json.dumps(plan),
            usage=LLMTokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )

    monkeypatch.setattr(GeminiLLMAdapter, "generate", planned_generate)
    settings = AppSettings(
        _env_file=None,
        app_log_level="WARNING",
        llm_provider="gemini",
        llm_model="gemma-4-31b-it",
        llm_api_key=SecretStr("offline-test-key"),
        prompt_version="v5-plan",
    )
    dataset = _dataset()
    report = asyncio.run(
        run_real_model_evaluation(
            ROOT,
            settings,
            dataset,
            split=EvaluationSplit.DEVELOPMENT,
            request_limit=2,
            request_interval_seconds=0,
            case_ids=("AGG-901",),
            comparison_policy=ResultComparisonPolicy.SEMANTIC_V2,
        )
    )

    assert planned_provider_requests((dataset.cases[0],), prompt_version="v5-plan") == 2
    assert report.completed
    assert report.requests_attempted == report.requests_planned == 2
    assert report.metrics.execution_accuracy == 1.0
    assert report.metrics.repair_attempt_count == 1
    assert report.metrics.repair_success_rate == 1.0
    assert report.cases[0].provider_request_count == 2
