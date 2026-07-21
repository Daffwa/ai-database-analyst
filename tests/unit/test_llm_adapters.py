"""Tests for the provider-neutral adapter boundary and factory."""

from __future__ import annotations

import asyncio

import pytest

from backend.core.config import AppSettings
from backend.core.errors import ConfigurationError
from backend.llm.adapters import FakeLLMAdapter, LLMAdapterError, LLMAdapterTimeout
from backend.llm.factory import create_llm_adapter
from backend.schemas.llm import AdapterRequest, LanguageCode, LLMIntent, StructuredSQLProposal


def _request(question: str) -> AdapterRequest:
    return AdapterRequest(
        request_id="request-1",
        question=question,
        system_prompt="system",
        user_prompt="user",
    )


def test_fake_adapter_matches_normalized_questions_and_returns_raw_response() -> None:
    expected = StructuredSQLProposal(
        intent=LLMIntent.UNSUPPORTED,
        language=LanguageCode.INDONESIAN,
        needs_clarification=False,
        confidence=1.0,
        reasoning_summary="Fixture response.",
    ).model_dump_json()
    adapter = FakeLLMAdapter({" Berapa jumlah pelanggan? ": expected})

    actual = asyncio.run(adapter.generate(_request("berapa   JUMLAH pelanggan?")))

    assert actual == expected
    assert adapter.provider == "fake"
    assert adapter.model == "fake-deterministic"


def test_fake_adapter_has_safe_indonesian_and_english_defaults() -> None:
    adapter = FakeLLMAdapter()

    indonesian = StructuredSQLProposal.model_validate_json(
        asyncio.run(adapter.generate(_request("Berapa pelanggan yang aktif?")))
    )
    english = StructuredSQLProposal.model_validate_json(
        asyncio.run(adapter.generate(_request("Predict tomorrow's stock price")))
    )

    assert indonesian.language is LanguageCode.INDONESIAN
    assert english.language is LanguageCode.ENGLISH
    assert indonesian.intent is english.intent is LLMIntent.UNSUPPORTED


@pytest.mark.parametrize(
    ("failure", "exception_type"),
    [("timeout", LLMAdapterTimeout), ("provider", LLMAdapterError)],
)
def test_fake_adapter_can_simulate_sanitized_failure_paths(
    failure: str,
    exception_type: type[Exception],
) -> None:
    adapter = FakeLLMAdapter(failure=failure)

    with pytest.raises(exception_type):
        asyncio.run(adapter.generate(_request("question")))


def test_factory_builds_fake_and_rejects_unavailable_provider() -> None:
    fake = create_llm_adapter(AppSettings(_env_file=None))
    assert isinstance(fake, FakeLLMAdapter)

    with pytest.raises(ConfigurationError, match="not available"):
        create_llm_adapter(AppSettings(llm_provider="unknown", _env_file=None))
