"""Clarification, bounded context, and verified-query retrieval tests."""

from __future__ import annotations

import pytest

from backend.core.errors import SemanticLayerError
from backend.evaluation.mini_cases import MINI_EVALUATION_CASES
from backend.evaluation.semantic_cases import (
    AMBIGUOUS_SEMANTIC_CASES,
    RESOLVED_SEMANTIC_CASES,
    SemanticEvaluationCase,
)
from backend.evaluation.semantic_runner import run_semantic_evaluation
from backend.schemas.llm import LanguageCode
from backend.schemas.semantic import (
    SemanticLayerBundle,
    SemanticValidationReport,
    VerifiedQueryStatus,
)
from backend.services.semantic_service import (
    SemanticService,
    detect_semantic_language,
    render_semantic_prompt_context,
)
from backend.services.verified_query_service import VerifiedQueryService


@pytest.mark.parametrize(
    "case",
    AMBIGUOUS_SEMANTIC_CASES,
    ids=[case.case_id for case in AMBIGUOUS_SEMANTIC_CASES],
)
def test_ambiguous_business_terms_require_the_expected_clarification(
    semantic_service: SemanticService,
    case: SemanticEvaluationCase,
) -> None:
    resolution = semantic_service.resolve(case.question)

    assert resolution.clarification is not None
    assert resolution.clarification.rule_id == case.expected_rule_id
    assert len(resolution.clarification.options) >= 2
    assert resolution.verified_queries == ()


@pytest.mark.parametrize(
    "case",
    RESOLVED_SEMANTIC_CASES,
    ids=[case.case_id for case in RESOLVED_SEMANTIC_CASES],
)
def test_explicitly_resolved_terms_do_not_overclarify(
    semantic_service: SemanticService,
    case: SemanticEvaluationCase,
) -> None:
    resolution = semantic_service.resolve(case.question)

    assert resolution.clarification is None
    assert resolution.assumptions


def test_all_twenty_existing_baselines_have_zero_false_clarifications(
    semantic_service: SemanticService,
) -> None:
    assert all(
        semantic_service.resolve(case.question).clarification is None
        for case in MINI_EVALUATION_CASES
    )


def test_each_valid_verified_query_is_retrieved_for_its_exact_question(
    semantic_service: SemanticService,
    semantic_bundle: SemanticLayerBundle,
) -> None:
    queries = tuple(
        query
        for query in semantic_bundle.verified_queries.queries
        if query.status is VerifiedQueryStatus.VALID
    )
    for query in queries:
        resolution = semantic_service.resolve(query.questions.id[0])
        assert query.query_id in {candidate.query_id for candidate in resolution.verified_queries}


def test_verified_query_service_excludes_non_valid_status_and_respects_bound(
    semantic_bundle: SemanticLayerBundle,
) -> None:
    valid = semantic_bundle.verified_queries.queries[0]
    deprecated = valid.model_copy(
        update={"query_id": "deprecated_query", "status": VerifiedQueryStatus.DEPRECATED}
    )
    service = VerifiedQueryService((deprecated, valid), max_examples=1)

    result = service.retrieve(valid.questions.id[0], LanguageCode.INDONESIAN)

    assert result == (valid,)
    assert (
        VerifiedQueryService((valid,), max_examples=0).retrieve(
            valid.questions.id[0], LanguageCode.INDONESIAN
        )
        == ()
    )
    with pytest.raises(ValueError, match="between zero and ten"):
        VerifiedQueryService((valid,), max_examples=11)


def test_semantic_context_is_bounded_and_marks_truncation(
    semantic_bundle: SemanticLayerBundle,
    semantic_report: SemanticValidationReport,
) -> None:
    service = SemanticService(
        semantic_bundle,
        semantic_report,
        max_verified_examples=3,
        max_context_characters=300,
    )
    resolution = service.resolve("Tampilkan lima pelanggan dengan total belanja terbesar.")

    assert resolution.context_truncated is True
    assert len(render_semantic_prompt_context(resolution)) <= 300


def test_invalid_report_and_context_budget_fail_before_use(
    semantic_bundle: SemanticLayerBundle,
    semantic_report: SemanticValidationReport,
) -> None:
    invalid = semantic_report.model_copy(update={"valid": False})
    with pytest.raises(SemanticLayerError):
        SemanticService(semantic_bundle, invalid)
    with pytest.raises(ValueError, match="greater than zero"):
        SemanticService(semantic_bundle, semantic_report, max_context_characters=0)


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Bandingkan jumlah invoice per tahun.", LanguageCode.INDONESIAN),
        ("Which artist has the most tracks?", LanguageCode.ENGLISH),
    ],
)
def test_pre_llm_language_detection(question: str, language: LanguageCode) -> None:
    assert detect_semantic_language(question) is language


def test_versioned_semantic_evaluation_has_no_failed_cases(
    semantic_service: SemanticService,
    semantic_bundle: SemanticLayerBundle,
) -> None:
    summary = run_semantic_evaluation(semantic_service, semantic_bundle)

    assert summary.correct_clarifications == 10
    assert summary.clarification_recall == 1.0
    assert summary.resolved_without_clarification == 10
    assert summary.baseline_false_clarifications == 0
    assert summary.exact_verified_query_retrievals == 10
    assert summary.failed_case_ids == ()
