"""Deterministic ambiguity detection before LLM invocation."""

from __future__ import annotations

import re

from backend.schemas.llm import LanguageCode
from backend.schemas.semantic import (
    ClarificationDecision,
    GlossaryTerm,
)


class ClarificationEngine:
    """Resolve explicit phrases or request a choice without silent defaults."""

    def evaluate(
        self,
        question: str,
        language: LanguageCode,
        terms: tuple[GlossaryTerm, ...],
    ) -> tuple[ClarificationDecision | None, tuple[str, ...], tuple[str, ...]]:
        normalized = normalize_semantic_text(question)
        assumptions: list[str] = []
        metric_ids: list[str] = []
        for term in terms:
            rule = term.ambiguity
            if rule is None:
                continue
            matched_options = [
                option
                for option in rule.options
                if any(
                    phrase_in_text(phrase, normalized)
                    for phrase in option.resolution_phrases.for_language(language)
                )
            ]
            if len(matched_options) == 1:
                assumptions.append(matched_options[0].assumption.for_language(language))
                metric_ids.extend(matched_options[0].metric_ids)
                continue
            return (
                ClarificationDecision(
                    rule_id=rule.rule_id,
                    question=rule.question.for_language(language),
                    options=tuple(option.label.for_language(language) for option in rule.options),
                ),
                tuple(assumptions),
                tuple(dict.fromkeys(metric_ids)),
            )
        return None, tuple(assumptions), tuple(dict.fromkeys(metric_ids))


def normalize_semantic_text(value: str) -> str:
    """Normalize punctuation and whitespace while preserving Unicode words."""

    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def phrase_in_text(phrase: str, normalized_text: str) -> bool:
    normalized_phrase = normalize_semantic_text(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in f" {normalized_text} "
