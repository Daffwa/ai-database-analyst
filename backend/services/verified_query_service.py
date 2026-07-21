"""Status-aware and bounded lexical retrieval for verified query examples."""

from __future__ import annotations

from backend.schemas.llm import LanguageCode
from backend.schemas.semantic import (
    ReviewStatus,
    VerifiedQueryDefinition,
    VerifiedQueryStatus,
)
from backend.services.clarification_service import normalize_semantic_text

_STOPWORDS = frozenset(
    {
        "apa",
        "berapa",
        "dengan",
        "has",
        "is",
        "mana",
        "of",
        "the",
        "what",
        "which",
        "yang",
    }
)


class VerifiedQueryService:
    """Retrieve only valid, reviewed examples relevant to the current question."""

    def __init__(
        self,
        queries: tuple[VerifiedQueryDefinition, ...],
        *,
        max_examples: int = 3,
    ) -> None:
        if not 0 <= max_examples <= 10:
            raise ValueError("max_examples must be between zero and ten")
        self._queries = queries
        self._max_examples = max_examples

    def retrieve(
        self,
        question: str,
        language: LanguageCode,
        *,
        metric_ids: tuple[str, ...] = (),
    ) -> tuple[VerifiedQueryDefinition, ...]:
        if self._max_examples == 0:
            return ()
        normalized_question = normalize_semantic_text(question)
        question_tokens = _content_tokens(normalized_question)
        scored: list[tuple[float, str, VerifiedQueryDefinition]] = []
        for query in self._queries:
            if (
                query.status is not VerifiedQueryStatus.VALID
                or query.review_status is ReviewStatus.DRAFT
            ):
                continue
            score = max(
                (
                    _similarity(normalized_question, question_tokens, candidate)
                    for candidate in query.questions.for_language(language)
                ),
                default=0.0,
            )
            score += 0.2 * len(set(metric_ids) & set(query.metric_ids))
            if score >= 0.35:
                scored.append((score, query.query_id, query))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(item[2] for item in scored[: self._max_examples])


def _similarity(
    normalized_question: str,
    question_tokens: set[str],
    candidate: str,
) -> float:
    normalized_candidate = normalize_semantic_text(candidate)
    if normalized_question == normalized_candidate:
        return 1.0
    candidate_tokens = _content_tokens(normalized_candidate)
    union = question_tokens | candidate_tokens
    return len(question_tokens & candidate_tokens) / len(union) if union else 0.0


def _content_tokens(normalized_text: str) -> set[str]:
    return {token for token in normalized_text.split() if token not in _STOPWORDS}
