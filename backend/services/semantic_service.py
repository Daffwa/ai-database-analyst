"""Semantic context selection, clarification, and bounded prompt material."""

from __future__ import annotations

import json

from backend.core.errors import SemanticLayerError
from backend.schemas.llm import LanguageCode
from backend.schemas.semantic import (
    ApprovalStatus,
    GlossaryTerm,
    JoinDefinition,
    MetricDefinition,
    ReviewStatus,
    SemanticLayerBundle,
    SemanticResolution,
    SemanticValidationReport,
    VerifiedQueryDefinition,
)
from backend.services.clarification_service import (
    ClarificationEngine,
    normalize_semantic_text,
    phrase_in_text,
)
from backend.services.verified_query_service import VerifiedQueryService


class SemanticService:
    """Resolve one question using a validated immutable semantic bundle."""

    def __init__(
        self,
        bundle: SemanticLayerBundle,
        validation: SemanticValidationReport,
        *,
        max_verified_examples: int = 3,
        max_context_characters: int = 8_000,
    ) -> None:
        if not validation.valid:
            raise SemanticLayerError(
                details={"codes": [issue.code.value for issue in validation.issues]}
            )
        if max_context_characters <= 0:
            raise ValueError("max_context_characters must be greater than zero")
        self._bundle = bundle
        self._validation = validation
        self._clarification = ClarificationEngine()
        self._verified_queries = VerifiedQueryService(
            bundle.verified_queries.queries,
            max_examples=max_verified_examples,
        )
        self._max_context_characters = max_context_characters

    @property
    def validation(self) -> SemanticValidationReport:
        return self._validation

    def resolve(self, question: str) -> SemanticResolution:
        language = detect_semantic_language(question)
        terms = self._match_terms(question, language)
        metrics = self._match_metrics(question, language, terms)
        clarification, assumptions, resolved_metric_ids = self._clarification.evaluate(
            question,
            language,
            terms,
        )
        metrics = self._metrics_for_ids(metrics, resolved_metric_ids)
        if clarification is not None:
            return SemanticResolution(
                semantic_version=self._bundle.semantic_version,
                content_hash=self._bundle.content_hash,
                language=language,
                matched_terms=terms,
                matched_metrics=metrics,
                assumptions=assumptions,
                clarification=clarification,
            )

        queries = self._verified_queries.retrieve(
            question,
            language,
            metric_ids=tuple(metric.metric_id for metric in metrics),
        )
        metrics = self._metrics_for_queries(metrics, queries)
        joins = self._approved_joins_for(queries)
        resolution = SemanticResolution(
            semantic_version=self._bundle.semantic_version,
            content_hash=self._bundle.content_hash,
            language=language,
            matched_terms=terms,
            matched_metrics=metrics,
            approved_joins=joins,
            verified_queries=queries,
            assumptions=assumptions,
        )
        return self._bound_resolution(resolution)

    def _match_terms(
        self,
        question: str,
        language: LanguageCode,
    ) -> tuple[GlossaryTerm, ...]:
        normalized = normalize_semantic_text(question)
        return tuple(
            term
            for term in self._bundle.glossary.terms
            if any(
                _term_phrase_matches(phrase, normalized)
                for phrase in (
                    term.label.for_language(language),
                    *term.synonyms.for_language(language),
                )
            )
        )

    def _match_metrics(
        self,
        question: str,
        language: LanguageCode,
        terms: tuple[GlossaryTerm, ...],
    ) -> tuple[MetricDefinition, ...]:
        normalized = normalize_semantic_text(question)
        matched_term_ids = {term.term_id for term in terms}
        return tuple(
            metric
            for metric in self._bundle.metrics.metrics
            if metric.review_status is not ReviewStatus.DRAFT
            and (
                bool(set(metric.term_ids) & matched_term_ids)
                or any(
                    phrase_in_text(phrase, normalized)
                    for phrase in (
                        metric.label.for_language(language),
                        *metric.aliases.for_language(language),
                    )
                )
            )
        )

    def _metrics_for_queries(
        self,
        matched: tuple[MetricDefinition, ...],
        queries: tuple[VerifiedQueryDefinition, ...],
    ) -> tuple[MetricDefinition, ...]:
        selected_ids = {metric.metric_id for metric in matched} | {
            metric_id for query in queries for metric_id in query.metric_ids
        }
        return tuple(
            metric
            for metric in self._bundle.metrics.metrics
            if metric.metric_id in selected_ids and metric.review_status is not ReviewStatus.DRAFT
        )

    def _metrics_for_ids(
        self,
        matched: tuple[MetricDefinition, ...],
        metric_ids: tuple[str, ...],
    ) -> tuple[MetricDefinition, ...]:
        selected_ids = {metric.metric_id for metric in matched} | set(metric_ids)
        return tuple(
            metric
            for metric in self._bundle.metrics.metrics
            if metric.metric_id in selected_ids and metric.review_status is not ReviewStatus.DRAFT
        )

    def _approved_joins_for(
        self,
        queries: tuple[VerifiedQueryDefinition, ...],
    ) -> tuple[JoinDefinition, ...]:
        join_ids = {join_id for query in queries for join_id in query.join_ids}
        return tuple(
            join
            for join in self._bundle.joins.joins
            if join.join_id in join_ids and join.approval_status is ApprovalStatus.APPROVED
        )

    def _bound_resolution(self, resolution: SemanticResolution) -> SemanticResolution:
        if len(render_semantic_prompt_context(resolution)) <= self._max_context_characters:
            return resolution
        update = resolution
        fields = ("verified_queries", "approved_joins", "matched_metrics", "matched_terms")
        for field_name in fields:
            while getattr(update, field_name):
                shortened = getattr(update, field_name)[:-1]
                update = update.model_copy(
                    update={field_name: shortened, "context_truncated": True}
                )
                if len(render_semantic_prompt_context(update)) <= self._max_context_characters:
                    return update
        return update.model_copy(update={"context_truncated": True})


def render_semantic_prompt_context(resolution: SemanticResolution) -> str:
    """Serialize only generation-relevant, non-sensitive semantic fields."""

    payload = {
        "semantic_version": resolution.semantic_version,
        "matched_terms": [
            {
                "term_id": term.term_id,
                "definition": term.definition.for_language(resolution.language),
            }
            for term in resolution.matched_terms
        ],
        "metrics": [
            {
                "metric_id": metric.metric_id,
                "definition": metric.definition.for_language(resolution.language),
                "expression": metric.expression,
                "source_table": metric.source_table,
                "term_ids": metric.term_ids,
                "dimensions": metric.dimensions,
                "requires_period": metric.requires_period,
                "double_counting_note": metric.double_counting_note,
            }
            for metric in resolution.matched_metrics
        ],
        "approved_joins": [
            {
                "join_id": join.join_id,
                "left": [join.left_table, join.left_columns],
                "right": [join.right_table, join.right_columns],
                "cardinality": join.cardinality.value,
                "guidance": join.guidance,
            }
            for join in resolution.approved_joins
        ],
        "verified_examples": [
            {
                "query_id": query.query_id,
                "questions": query.questions.for_language(resolution.language),
                "sql": query.sql,
                "tables": query.tables,
                "columns": query.columns,
            }
            for query in resolution.verified_queries
        ],
        "approved_assumptions": resolution.assumptions,
        "context_truncated": resolution.context_truncated,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def detect_semantic_language(question: str) -> LanguageCode:
    """Detect the two supported languages for pre-LLM clarification text."""

    indonesian_markers = {
        "apa",
        "bagaimana",
        "bandingkan",
        "berapa",
        "jumlah",
        "nilai",
        "negara",
        "pelanggan",
        "pendapatan",
        "penjualan",
        "produk",
        "rata",
        "siapa",
        "terbaik",
        "terbaru",
        "tahun",
        "tampilkan",
        "transaksi",
        "yang",
    }
    tokens = set(normalize_semantic_text(question).split())
    return LanguageCode.INDONESIAN if tokens & indonesian_markers else LanguageCode.ENGLISH


def _term_phrase_matches(phrase: str, normalized_question: str) -> bool:
    if phrase_in_text(phrase, normalized_question):
        return True
    phrase_tokens = set(normalize_semantic_text(phrase).split())
    question_tokens = set(normalized_question.split())
    return len(phrase_tokens) > 1 and phrase_tokens <= question_tokens
