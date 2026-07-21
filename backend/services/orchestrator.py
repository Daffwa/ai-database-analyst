"""Explicit generation orchestration with optional Tahap 5 semantics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID, uuid4

from backend.core.errors import InvalidRequestError
from backend.core.logging import get_logger
from backend.core.observability import current_request_id
from backend.schemas.database import SchemaAllowlist, SchemaSnapshot
from backend.schemas.llm import (
    LanguageCode,
    LLMIntent,
    PipelineEvent,
    PipelineStage,
    QueryResponse,
    QueryStatus,
)
from backend.schemas.semantic import SemanticResolution
from backend.services.semantic_service import SemanticService
from backend.services.sql_generator import SQLGenerator

STAGE_3_WARNING = "Tahap 3 demo only: generated SQL has not passed the Tahap 4 AST security gate."
STAGE_5_WARNING = (
    "Tahap 5 semantic context applied; generated SQL remains untrusted until the "
    "Tahap 4 AST security gate passes."
)
LOGGER = get_logger(__name__)


class QueryProcessor(Protocol):
    """Common async boundary for generation-only and secure pipelines."""

    async def process(self, question: str) -> QueryResponse:
        """Process one natural-language question."""


class QueryOrchestrator:
    """Validate, resolve semantics, generate, and return an auditable proposal."""

    def __init__(
        self,
        generator: SQLGenerator,
        snapshot: SchemaSnapshot,
        *,
        max_question_characters: int = 2_000,
        request_id_factory: Callable[[], UUID] = uuid4,
        semantic_service: SemanticService | None = None,
    ) -> None:
        if max_question_characters <= 0:
            raise ValueError("max_question_characters must be greater than zero")
        self._generator = generator
        self._snapshot = snapshot
        self._allowlist = SchemaAllowlist.from_snapshot(snapshot)
        self._max_question_characters = max_question_characters
        self._request_id_factory = request_id_factory
        self._semantic_service = semantic_service

    async def process(self, question: str) -> QueryResponse:
        normalized_question = question.strip()
        if not normalized_question:
            raise InvalidRequestError("Question must not be empty.")
        if len(normalized_question) > self._max_question_characters:
            raise InvalidRequestError("Question exceeds the configured character limit.")

        request_id = current_request_id() or str(self._request_id_factory())
        semantic_resolution = (
            self._semantic_service.resolve(normalized_question)
            if self._semantic_service is not None
            else None
        )
        if semantic_resolution is not None:
            _log_semantic_resolution(request_id, semantic_resolution)
        if semantic_resolution is not None and semantic_resolution.clarification is not None:
            return self._clarification_response(request_id, semantic_resolution)

        generation = await self._generator.generate(
            request_id=request_id,
            question=normalized_question,
            snapshot=self._snapshot,
            allowlist=self._allowlist,
            semantic_resolution=semantic_resolution,
        )
        proposal = generation.proposal
        status = {
            LLMIntent.ANALYSIS: QueryStatus.GENERATED_PENDING_SECURITY,
            LLMIntent.CLARIFICATION: QueryStatus.CLARIFICATION_REQUIRED,
            LLMIntent.UNSUPPORTED: QueryStatus.UNSUPPORTED,
        }[proposal.intent]
        pipeline = [
            PipelineEvent(stage=PipelineStage.REQUEST_VALIDATED),
            PipelineEvent(stage=PipelineStage.REQUEST_ID_ASSIGNED),
            PipelineEvent(stage=PipelineStage.SCHEMA_CONTEXT_LOADED),
        ]
        if semantic_resolution is not None:
            pipeline.extend(
                (
                    PipelineEvent(stage=PipelineStage.SEMANTIC_CONTEXT_LOADED),
                    PipelineEvent(stage=PipelineStage.VERIFIED_EXAMPLES_RETRIEVED),
                    PipelineEvent(stage=PipelineStage.AMBIGUITY_CHECKED),
                )
            )
        pipeline.extend(
            (
                PipelineEvent(stage=PipelineStage.PROMPT_BUILT),
                PipelineEvent(
                    stage=PipelineStage.LLM_INVOKED,
                    latency_ms=generation.llm_latency_ms,
                ),
                PipelineEvent(stage=PipelineStage.OUTPUT_VALIDATED),
            )
        )
        if proposal.intent is LLMIntent.ANALYSIS:
            pipeline.append(PipelineEvent(stage=PipelineStage.AWAITING_SECURITY_VALIDATION))
        pipeline.append(PipelineEvent(stage=PipelineStage.COMPLETED))

        return QueryResponse(
            request_id=request_id,
            status=status,
            language=proposal.language,
            generated_sql=proposal.sql,
            assumptions=_merge_assumptions(
                proposal.assumptions,
                semantic_resolution.assumptions if semantic_resolution is not None else (),
            ),
            tables=proposal.tables,
            columns=proposal.columns,
            confidence=proposal.confidence,
            reasoning_summary=proposal.reasoning_summary,
            clarification_question=proposal.clarification_question,
            prompt_version=generation.prompt.prompt_version,
            schema_hash=generation.prompt.schema_hash,
            semantic_version=generation.prompt.semantic_version,
            semantic_context_hash=generation.prompt.semantic_context_hash,
            matched_term_ids=(
                tuple(term.term_id for term in semantic_resolution.matched_terms)
                if semantic_resolution is not None
                else ()
            ),
            matched_metric_ids=(
                tuple(metric.metric_id for metric in semantic_resolution.matched_metrics)
                if semantic_resolution is not None
                else ()
            ),
            verified_query_ids=generation.prompt.verified_query_ids,
            provider=generation.provider,
            model=generation.model,
            llm_latency_ms=generation.llm_latency_ms,
            pipeline=tuple(pipeline),
            warnings=(STAGE_5_WARNING if semantic_resolution is not None else STAGE_3_WARNING,),
        )

    def _clarification_response(
        self,
        request_id: str,
        semantic_resolution: SemanticResolution,
    ) -> QueryResponse:
        clarification = semantic_resolution.clarification
        if clarification is None:
            raise RuntimeError("clarification response requires a decision")
        return QueryResponse(
            request_id=request_id,
            status=QueryStatus.CLARIFICATION_REQUIRED,
            language=semantic_resolution.language,
            generated_sql=None,
            assumptions=semantic_resolution.assumptions,
            tables=(),
            columns=(),
            confidence=1.0,
            reasoning_summary=(
                "Istilah bisnis perlu diperjelas sebelum SQL dibuat."
                if semantic_resolution.language is LanguageCode.INDONESIAN
                else "A business term must be clarified before SQL is generated."
            ),
            clarification_question=(
                f"{clarification.question} Pilihan: " + "; ".join(clarification.options)
            ),
            prompt_version=self._generator.prompt_version,
            schema_hash=self._snapshot.schema_hash,
            semantic_version=semantic_resolution.semantic_version,
            semantic_context_hash=semantic_resolution.content_hash,
            matched_term_ids=tuple(term.term_id for term in semantic_resolution.matched_terms),
            matched_metric_ids=tuple(
                metric.metric_id for metric in semantic_resolution.matched_metrics
            ),
            provider=self._generator.provider,
            model=self._generator.model,
            llm_latency_ms=0.0,
            pipeline=(
                PipelineEvent(stage=PipelineStage.REQUEST_VALIDATED),
                PipelineEvent(stage=PipelineStage.REQUEST_ID_ASSIGNED),
                PipelineEvent(stage=PipelineStage.SCHEMA_CONTEXT_LOADED),
                PipelineEvent(stage=PipelineStage.SEMANTIC_CONTEXT_LOADED),
                PipelineEvent(stage=PipelineStage.VERIFIED_EXAMPLES_RETRIEVED),
                PipelineEvent(stage=PipelineStage.AMBIGUITY_CHECKED),
                PipelineEvent(stage=PipelineStage.COMPLETED),
            ),
            warnings=(
                "No SQL was generated because the semantic ambiguity policy "
                "requires clarification.",
            ),
        )


def _merge_assumptions(
    proposal_assumptions: tuple[str, ...],
    semantic_assumptions: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*proposal_assumptions, *semantic_assumptions)))


def _log_semantic_resolution(
    request_id: str,
    resolution: SemanticResolution,
) -> None:
    """Audit semantic decisions without raw questions or assumption text."""

    LOGGER.info(
        "Semantic resolution decision",
        extra={
            "request_id": request_id,
            "semantic_version": resolution.semantic_version,
            "semantic_context_hash": resolution.content_hash,
            "matched_term_ids": tuple(term.term_id for term in resolution.matched_terms),
            "matched_metric_ids": tuple(metric.metric_id for metric in resolution.matched_metrics),
            "verified_query_ids": tuple(query.query_id for query in resolution.verified_queries),
            "clarification_rule_id": (
                resolution.clarification.rule_id if resolution.clarification else None
            ),
            "approved_assumption_count": len(resolution.assumptions),
            "semantic_context_truncated": resolution.context_truncated,
        },
    )
