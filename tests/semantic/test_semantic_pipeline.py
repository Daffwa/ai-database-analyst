"""Tests for semantic prompt provenance and pre-LLM pipeline ordering."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from backend.llm.adapters import FakeLLMAdapter
from backend.schemas.database import SchemaSnapshot
from backend.schemas.llm import (
    LanguageCode,
    LLMIntent,
    PipelineStage,
    QueryStatus,
    StructuredSQLProposal,
)
from backend.services.orchestrator import QueryOrchestrator
from backend.services.output_parser import StructuredOutputParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.schema_retriever import SchemaRetriever
from backend.services.semantic_service import SemanticService
from backend.services.sql_generator import SQLGenerator


def test_prompt_contains_bounded_semantic_context_and_verified_example(
    semantic_snapshot: SchemaSnapshot,
    semantic_service: SemanticService,
) -> None:
    resolution = semantic_service.resolve("Berapa jumlah pelanggan?")
    package = PromptBuilder(SchemaRetriever()).build(
        request_id="request-1",
        question="Berapa jumlah pelanggan?",
        snapshot=semantic_snapshot,
        semantic_resolution=resolution,
    )
    payload = json.loads(package.user_prompt)

    assert package.semantic_version == "v1"
    assert package.semantic_context_hash == resolution.content_hash
    assert package.verified_query_ids == ("customer_count",)
    assert payload["semantic_context"]["metrics"][0]["metric_id"] == "customer_count"
    assert payload["semantic_context"]["verified_examples"][0]["query_id"] == ("customer_count")
    assert "Never invent a default" in package.system_prompt


def test_ambiguity_returns_before_the_failing_adapter_is_invoked(
    semantic_snapshot: SchemaSnapshot,
    semantic_service: SemanticService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    generator = SQLGenerator(
        FakeLLMAdapter(failure="provider"),
        PromptBuilder(SchemaRetriever()),
        StructuredOutputParser(),
    )
    orchestrator = QueryOrchestrator(
        generator,
        semantic_snapshot,
        semantic_service=semantic_service,
    )

    with caplog.at_level(logging.INFO, logger="backend.services.orchestrator"):
        response = asyncio.run(orchestrator.process("Siapa pelanggan terbaik?"))

    assert response.status is QueryStatus.CLARIFICATION_REQUIRED
    assert response.generated_sql is None
    assert response.executed_sql is None
    assert response.llm_latency_ms == 0
    assert response.semantic_version == "v1"
    assert response.matched_term_ids == ("best_customer",)
    assert PipelineStage.LLM_INVOKED not in {event.stage for event in response.pipeline}
    assert PipelineStage.AMBIGUITY_CHECKED in {event.stage for event in response.pipeline}
    audit_record = caplog.records[-1]
    assert audit_record.__dict__["clarification_rule_id"] == "best_customer_measure"
    assert audit_record.__dict__["approved_assumption_count"] == 0
    assert "pelanggan terbaik" not in audit_record.getMessage().casefold()


def test_explicit_resolution_is_visible_as_an_assumption_and_retrieval_provenance(
    semantic_snapshot: SchemaSnapshot,
    semantic_service: SemanticService,
) -> None:
    question = "Siapa pelanggan terbaik berdasarkan total belanja?"
    proposal = StructuredSQLProposal(
        intent=LLMIntent.ANALYSIS,
        language=LanguageCode.INDONESIAN,
        needs_clarification=False,
        sql=(
            "SELECT c.CustomerId, ROUND(SUM(i.Total), 2) AS total_spend "
            "FROM Customer AS c JOIN Invoice AS i ON i.CustomerId = c.CustomerId "
            "GROUP BY c.CustomerId ORDER BY total_spend DESC LIMIT 1"
        ),
        tables=("Customer", "Invoice"),
        columns=("Customer.CustomerId", "Invoice.CustomerId", "Invoice.Total"),
        confidence=1.0,
        reasoning_summary="Ranking berdasarkan metric yang dipilih.",
    )
    generator = SQLGenerator(
        FakeLLMAdapter({question: proposal.model_dump_json()}),
        PromptBuilder(SchemaRetriever()),
        StructuredOutputParser(),
    )
    orchestrator = QueryOrchestrator(
        generator,
        semantic_snapshot,
        semantic_service=semantic_service,
    )

    response = asyncio.run(orchestrator.process(question))

    assert response.status is QueryStatus.GENERATED_PENDING_SECURITY
    assert response.assumptions == ("Pelanggan diranking berdasarkan jumlah Invoice.Total.",)
    assert "customer_total_spend" in response.matched_metric_ids
    assert response.verified_query_ids == ("top_customers_by_spend",)
    stages = {event.stage for event in response.pipeline}
    assert PipelineStage.SEMANTIC_CONTEXT_LOADED in stages
    assert PipelineStage.VERIFIED_EXAMPLES_RETRIEVED in stages
    assert PipelineStage.AMBIGUITY_CHECKED in stages
