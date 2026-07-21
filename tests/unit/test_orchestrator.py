"""Tests for the explicit non-executing Tahap 3 orchestration state machine."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

from backend.core.errors import InvalidRequestError
from backend.llm.adapters import FakeLLMAdapter
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
from backend.services.schema_service import load_schema_snapshot
from backend.services.sql_generator import SQLGenerator

ROOT = Path(__file__).resolve().parents[2]
FIXED_UUID = UUID("00000000-0000-4000-8000-000000000003")


def _orchestrator(
    question: str,
    proposal: StructuredSQLProposal,
    *,
    max_question_characters: int = 2_000,
) -> QueryOrchestrator:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    generator = SQLGenerator(
        FakeLLMAdapter({question: proposal.model_dump_json()}),
        PromptBuilder(SchemaRetriever()),
        StructuredOutputParser(),
    )
    return QueryOrchestrator(
        generator,
        snapshot,
        max_question_characters=max_question_characters,
        request_id_factory=lambda: FIXED_UUID,
    )


def test_analysis_stops_before_security_validation_and_execution() -> None:
    question = "Berapa jumlah pelanggan?"
    proposal = StructuredSQLProposal(
        intent=LLMIntent.ANALYSIS,
        language=LanguageCode.INDONESIAN,
        needs_clarification=False,
        sql="SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        tables=("Customer",),
        columns=("Customer.CustomerId",),
        confidence=1.0,
        reasoning_summary="Menghitung pelanggan.",
    )

    response = asyncio.run(_orchestrator(question, proposal).process(question))

    assert response.request_id == str(FIXED_UUID)
    assert response.status is QueryStatus.GENERATED_PENDING_SECURITY
    assert response.generated_sql == proposal.sql
    assert response.executed_sql is None
    assert response.result is None
    assert response.database_latency_ms is None
    assert PipelineStage.AWAITING_SECURITY_VALIDATION in {
        event.stage for event in response.pipeline
    }
    assert "not passed" in response.warnings[0]


@pytest.mark.parametrize(
    ("question", "proposal", "expected_status"),
    [
        (
            "Siapa pelanggan terbaik?",
            StructuredSQLProposal(
                intent=LLMIntent.CLARIFICATION,
                language=LanguageCode.INDONESIAN,
                needs_clarification=True,
                clarification_question="Gunakan total belanja atau jumlah transaksi?",
                confidence=0.9,
                reasoning_summary="Metrik terbaik ambigu.",
            ),
            QueryStatus.CLARIFICATION_REQUIRED,
        ),
        (
            "Predict tomorrow's stock price",
            StructuredSQLProposal(
                intent=LLMIntent.UNSUPPORTED,
                language=LanguageCode.ENGLISH,
                needs_clarification=False,
                confidence=1.0,
                reasoning_summary="The database has no market data.",
            ),
            QueryStatus.UNSUPPORTED,
        ),
    ],
)
def test_non_analysis_intents_complete_without_sql(
    question: str,
    proposal: StructuredSQLProposal,
    expected_status: QueryStatus,
) -> None:
    response = asyncio.run(_orchestrator(question, proposal).process(question))

    assert response.status is expected_status
    assert response.generated_sql is None
    assert response.executed_sql is None
    assert PipelineStage.AWAITING_SECURITY_VALIDATION not in {
        event.stage for event in response.pipeline
    }


def test_orchestrator_rejects_empty_and_oversized_questions() -> None:
    proposal = StructuredSQLProposal(
        intent=LLMIntent.UNSUPPORTED,
        language=LanguageCode.ENGLISH,
        needs_clarification=False,
        confidence=1.0,
        reasoning_summary="Unsupported.",
    )
    orchestrator = _orchestrator("q", proposal, max_question_characters=3)

    with pytest.raises(InvalidRequestError, match="empty"):
        asyncio.run(orchestrator.process("   "))
    with pytest.raises(InvalidRequestError, match="character limit"):
        asyncio.run(orchestrator.process("four"))


def test_orchestrator_rejects_invalid_question_budget() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    generator = SQLGenerator(
        FakeLLMAdapter(),
        PromptBuilder(SchemaRetriever()),
        StructuredOutputParser(),
    )
    with pytest.raises(ValueError, match="greater than zero"):
        QueryOrchestrator(generator, snapshot, max_question_characters=0)
