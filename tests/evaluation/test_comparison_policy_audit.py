"""Development-only audit contract for semantic comparison policy v2."""

from __future__ import annotations

from pathlib import Path

from backend.evaluation.case_loader import load_evaluation_dataset
from backend.evaluation.comparison_audit import build_comparison_policy_audit
from backend.schemas.evaluation import EvaluationSplit, ResultComparisonPolicy

ROOT = Path(__file__).resolve().parents[2]


def test_semantic_comparison_audit_passes_without_scoring_holdout() -> None:
    dataset = load_evaluation_dataset(ROOT / "data" / "evaluation" / "stage-7-v1.jsonl")
    audit = build_comparison_policy_audit(dataset)

    assert audit.gate_passed
    assert audit.split is EvaluationSplit.DEVELOPMENT
    assert audit.comparison_policy is ResultComparisonPolicy.SEMANTIC_V2
    assert audit.development_case_count == 70
    assert audit.analytical_case_count == 61
    assert audit.holdout_cases_scored == 0
    assert audit.exact_self_matches == audit.analytical_case_count
    assert audit.presentation_variants_accepted == audit.presentation_variants_tested
    assert audit.strict_policy_presentation_rejections == audit.presentation_variants_tested
    assert audit.substantive_variants_rejected == audit.substantive_variants_tested
    assert audit.required_order_variants_rejected == audit.required_order_variants_tested
    assert audit.irrelevant_order_variants_accepted == audit.irrelevant_order_variants_tested

    serialized = audit.model_dump_json()
    for forbidden in ("question", "expected_sql", "expected_rows", "generated_sql"):
        assert forbidden not in serialized
