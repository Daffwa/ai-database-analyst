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
        metrics = self._metrics_for_queries(
            metrics,
            queries,
            question=question,
            language=language,
        )
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
        eligible = tuple(
            metric
            for metric in self._bundle.metrics.metrics
            if metric.review_status is not ReviewStatus.DRAFT
        )
        direct = tuple(
            metric
            for metric in eligible
            if any(
                phrase_in_text(phrase, normalized)
                for phrase in (
                    metric.label.for_language(language),
                    *metric.aliases.for_language(language),
                )
            )
        )
        if direct:
            return direct

        term_candidates = tuple(
            metric
            for metric in eligible
            if set(metric.term_ids) & matched_term_ids
            and _metric_intent_matches(metric, normalized)
        )
        if len(term_candidates) == 1:
            return term_candidates
        if not term_candidates:
            scored_counts = tuple(
                (score, metric)
                for metric in eligible
                if metric.aggregation.casefold() in {"count", "count_distinct"}
                for score in (_count_metric_entity_score(metric, normalized),)
                if score is not None
            )
            if not scored_counts:
                return ()
            best_score = max(score for score, _metric in scored_counts)
            return tuple(metric for score, metric in scored_counts if score == best_score)

        scored = tuple(
            (
                _metric_phrase_score(metric, normalized, language),
                metric,
            )
            for metric in term_candidates
        )
        best_score = max(score for score, _metric in scored)
        if best_score == 0:
            return term_candidates
        return tuple(metric for score, metric in scored if score == best_score)

    def _metrics_for_queries(
        self,
        matched: tuple[MetricDefinition, ...],
        queries: tuple[VerifiedQueryDefinition, ...],
        *,
        question: str,
        language: LanguageCode,
    ) -> tuple[MetricDefinition, ...]:
        """Import metric bindings only from exact reviewed-question matches.

        Lexically similar verified queries remain useful few-shot examples, but
        they must not silently replace the measure requested by the user.
        """

        normalized_question = normalize_semantic_text(question)
        selected_ids = {metric.metric_id for metric in matched} | {
            metric_id
            for query in queries
            if any(
                normalize_semantic_text(candidate) == normalized_question
                for candidate in query.questions.for_language(language)
            )
            for metric_id in query.metric_ids
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
        selected_ids = set(metric_ids) if metric_ids else {metric.metric_id for metric in matched}
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
    phrase_tokens = normalize_semantic_text(phrase).split()
    if not phrase_tokens or not set(phrase_tokens) & {"latest", "terbaru"}:
        return False
    return set(phrase_tokens) <= set(normalized_question.split())


def _metric_phrase_score(
    metric: MetricDefinition,
    normalized_question: str,
    language: LanguageCode,
) -> int:
    """Prefer the uniquely most specific reviewed metric for a broad term."""

    question_tokens = set(normalized_question.split())
    phrases = (
        metric.label.for_language(language),
        *metric.aliases.for_language(language),
    )
    return max(
        (len(set(normalize_semantic_text(phrase).split()) & question_tokens) for phrase in phrases),
        default=0,
    )


_COUNT_CUES = frozenset(
    {
        "banyak",
        "count",
        "counts",
        "frequency",
        "frequent",
        "hitung",
        "jumlah",
        "most",
        "number",
        "sering",
        "terbanyak",
    }
)


def _metric_intent_matches(metric: MetricDefinition, normalized_question: str) -> bool:
    """Require an aggregation cue before a broad glossary term binds a metric."""

    tokens = set(normalized_question.split())
    aggregation = metric.aggregation.casefold()
    if aggregation in {"count", "count_distinct"}:
        return bool(tokens & _COUNT_CUES)
    if aggregation in {"sum", "sum_product"}:
        return bool(
            tokens
            & {
                "belanja",
                "omzet",
                "pendapatan",
                "penjualan",
                "revenue",
                "sales",
                "spend",
                "sum",
                "total",
                "value",
            }
        )
    if aggregation in {"average", "avg"}:
        return bool(tokens & {"average", "avg", "mean", "rata"})
    return True


def _count_metric_entity_score(
    metric: MetricDefinition,
    normalized_question: str,
) -> int | None:
    """Match compositional requests such as ``count all invoices`` safely."""

    tokens = [_singular_token(token) for token in normalized_question.split()]
    cue_positions = tuple(index for index, token in enumerate(tokens) if token in _COUNT_CUES)
    if not cue_positions:
        return None
    question_tokens = set(tokens)
    phrases = (
        metric.label.id,
        metric.label.en,
        *metric.aliases.id,
        *metric.aliases.en,
    )
    scores: list[int] = []
    for phrase in phrases:
        entity_tokens = tuple(
            _singular_token(token)
            for token in normalize_semantic_text(phrase).split()
            if token not in _COUNT_CUES and token not in {"all", "number"}
        )
        if not entity_tokens or not set(entity_tokens) <= question_tokens:
            continue
        entity_positions = tuple(
            index for index, token in enumerate(tokens) if token in set(entity_tokens)
        )
        distance = min(abs(cue - entity) for cue in cue_positions for entity in entity_positions)
        scores.append(len(set(entity_tokens)) * 100 - distance)
    return max(scores) if scores else None


def _singular_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token
