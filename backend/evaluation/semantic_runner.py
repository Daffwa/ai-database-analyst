"""Deterministic Tahap 5 semantic and clarification evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.evaluation.mini_cases import MINI_EVALUATION_CASES
from backend.evaluation.semantic_cases import (
    AMBIGUOUS_SEMANTIC_CASES,
    RESOLVED_SEMANTIC_CASES,
    SEMANTIC_EVALUATION_VERSION,
)
from backend.schemas.semantic import SemanticLayerBundle, VerifiedQueryStatus
from backend.services.semantic_service import SemanticService


class SemanticEvaluationSummary(BaseModel):
    """Measured clarification and retrieval results for one semantic version."""

    model_config = ConfigDict(frozen=True)

    evaluation_version: str
    semantic_version: str
    semantic_content_hash: str
    ambiguous_case_count: int = Field(ge=0)
    correct_clarifications: int = Field(ge=0)
    clarification_recall: float = Field(ge=0, le=1)
    resolved_case_count: int = Field(ge=0)
    resolved_without_clarification: int = Field(ge=0)
    baseline_case_count: int = Field(ge=0)
    baseline_false_clarifications: int = Field(ge=0)
    baseline_false_clarification_rate: float = Field(ge=0, le=1)
    valid_verified_query_count: int = Field(ge=0)
    exact_verified_query_retrievals: int = Field(ge=0)
    failed_case_ids: tuple[str, ...]


def run_semantic_evaluation(
    service: SemanticService,
    bundle: SemanticLayerBundle,
) -> SemanticEvaluationSummary:
    """Measure required clarification, overclarification, and exact retrieval."""

    failed: list[str] = []
    correct_clarifications = 0
    for case in AMBIGUOUS_SEMANTIC_CASES:
        decision = service.resolve(case.question).clarification
        if decision is not None and decision.rule_id == case.expected_rule_id:
            correct_clarifications += 1
        else:
            failed.append(case.case_id)

    resolved_without_clarification = 0
    for case in RESOLVED_SEMANTIC_CASES:
        if service.resolve(case.question).clarification is None:
            resolved_without_clarification += 1
        else:
            failed.append(case.case_id)

    baseline_false_clarifications = 0
    for baseline_case in MINI_EVALUATION_CASES:
        if service.resolve(baseline_case.question).clarification is not None:
            baseline_false_clarifications += 1
            failed.append(baseline_case.case_id)

    valid_queries = tuple(
        query
        for query in bundle.verified_queries.queries
        if query.status is VerifiedQueryStatus.VALID
    )
    exact_retrievals = 0
    for query in valid_queries:
        resolution = service.resolve(query.questions.id[0])
        if query.query_id in {example.query_id for example in resolution.verified_queries}:
            exact_retrievals += 1
        else:
            failed.append(query.query_id)

    ambiguous_count = len(AMBIGUOUS_SEMANTIC_CASES)
    baseline_count = len(MINI_EVALUATION_CASES)
    return SemanticEvaluationSummary(
        evaluation_version=SEMANTIC_EVALUATION_VERSION,
        semantic_version=bundle.semantic_version,
        semantic_content_hash=bundle.content_hash,
        ambiguous_case_count=ambiguous_count,
        correct_clarifications=correct_clarifications,
        clarification_recall=(correct_clarifications / ambiguous_count if ambiguous_count else 1.0),
        resolved_case_count=len(RESOLVED_SEMANTIC_CASES),
        resolved_without_clarification=resolved_without_clarification,
        baseline_case_count=baseline_count,
        baseline_false_clarifications=baseline_false_clarifications,
        baseline_false_clarification_rate=(
            baseline_false_clarifications / baseline_count if baseline_count else 0.0
        ),
        valid_verified_query_count=len(valid_queries),
        exact_verified_query_retrievals=exact_retrievals,
        failed_case_ids=tuple(dict.fromkeys(failed)),
    )
