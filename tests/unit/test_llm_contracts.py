"""Tests for strict structured output parsing and declared-schema checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.core.errors import LLMOutputError
from backend.schemas.database import SchemaAllowlist
from backend.schemas.llm import LanguageCode, LLMIntent, StructuredSQLProposal
from backend.services.output_parser import StructuredOutputParser, validate_declared_schema
from backend.services.schema_service import load_schema_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _analysis_payload(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "intent": "analysis",
        "language": "id",
        "needs_clarification": False,
        "clarification_question": None,
        "assumptions": [],
        "sql": "SELECT COUNT(CustomerId) FROM Customer",
        "tables": ["Customer"],
        "columns": ["Customer.CustomerId"],
        "confidence": 0.9,
        "reasoning_summary": "Menghitung baris pelanggan.",
    }
    payload.update(updates)
    return payload


def test_analysis_contract_accepts_complete_structured_proposal() -> None:
    proposal = StructuredSQLProposal.model_validate(_analysis_payload())

    assert proposal.intent is LLMIntent.ANALYSIS
    assert proposal.language is LanguageCode.INDONESIAN
    assert proposal.sql == "SELECT COUNT(CustomerId) FROM Customer"


@pytest.mark.parametrize(
    "updates",
    [
        {"sql": None},
        {"sql": "   "},
        {"needs_clarification": True, "clarification_question": "Metric apa?"},
        {"tables": ["Customer", "Customer"]},
        {"columns": ["Customer.CustomerId", "Customer.CustomerId"]},
        {"assumptions": [""]},
        {"confidence": 1.1},
        {"unexpected": "forbidden"},
    ],
)
def test_analysis_contract_rejects_inconsistent_or_extra_fields(
    updates: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        StructuredSQLProposal.model_validate(_analysis_payload(**updates))


def test_clarification_and_unsupported_contracts_are_sql_free() -> None:
    clarification = StructuredSQLProposal(
        intent=LLMIntent.CLARIFICATION,
        language=LanguageCode.INDONESIAN,
        needs_clarification=True,
        clarification_question="Gunakan nilai atau jumlah transaksi?",
        confidence=0.8,
        reasoning_summary="Metrik belum ditentukan.",
    )
    unsupported = StructuredSQLProposal(
        intent=LLMIntent.UNSUPPORTED,
        language=LanguageCode.ENGLISH,
        needs_clarification=False,
        confidence=1.0,
        reasoning_summary="The requested evidence is not in this database.",
    )

    assert clarification.sql is None
    assert unsupported.tables == ()

    with pytest.raises(ValidationError):
        StructuredSQLProposal.model_validate(clarification.model_dump() | {"sql": "SELECT 1"})
    with pytest.raises(ValidationError):
        StructuredSQLProposal.model_validate(
            unsupported.model_dump() | {"needs_clarification": True}
        )


def test_parser_accepts_json_object_and_rejects_free_text_and_oversize() -> None:
    parser = StructuredOutputParser(max_characters=1_000)
    proposal = parser.parse(json.dumps(_analysis_payload()))

    assert proposal.intent is LLMIntent.ANALYSIS
    for invalid in ("", "not-json", "[]", "```json\n{}\n```"):
        with pytest.raises(LLMOutputError):
            parser.parse(invalid)
    with pytest.raises(LLMOutputError):
        parser.parse("x" * 1_001)
    with pytest.raises(ValueError):
        StructuredOutputParser(max_characters=0)


def test_declared_schema_requires_allowed_qualified_sources_in_prompt_context() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    allowlist = SchemaAllowlist.from_snapshot(snapshot)
    proposal = StructuredSQLProposal.model_validate(_analysis_payload())

    validate_declared_schema(proposal, allowlist, context_tables=("Customer",))

    invalid_cases: list[tuple[dict[str, Any], tuple[str, ...]]] = [
        ({"tables": ["Secret"]}, ("Secret",)),
        ({"columns": ["Customer.Secret"]}, ("Customer",)),
        ({"columns": ["CustomerId"]}, ("Customer",)),
        ({"tables": ["Customer"]}, ("Invoice",)),
        ({"tables": [], "columns": []}, ()),
    ]
    for updates, context in invalid_cases:
        invalid = StructuredSQLProposal.model_validate(_analysis_payload(**updates))
        with pytest.raises(LLMOutputError):
            validate_declared_schema(invalid, allowlist, context_tables=context)

    clarification = StructuredSQLProposal(
        intent=LLMIntent.CLARIFICATION,
        language=LanguageCode.ENGLISH,
        needs_clarification=True,
        clarification_question="Which metric?",
        confidence=0.5,
        reasoning_summary="A metric is required.",
    )
    validate_declared_schema(clarification, allowlist, context_tables=())
