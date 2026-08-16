"""Tests for the provider-neutral adapter boundary and factory."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from backend.core.config import AppSettings
from backend.core.errors import ConfigurationError
from backend.llm.adapters import (
    FakeLLMAdapter,
    GeminiLLMAdapter,
    LLMAdapterAuthenticationError,
    LLMAdapterError,
    LLMAdapterRateLimitError,
    LLMAdapterTimeout,
    MeteredLLMAdapter,
    ProviderRequestBudget,
    ProviderRequestLimitExceeded,
)
from backend.llm.factory import create_llm_adapter
from backend.schemas.llm import (
    AdapterGeneration,
    AdapterRequest,
    LanguageCode,
    LLMIntent,
    StructuredSQLProposal,
)


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

    assert actual.content == expected
    assert actual.usage is None
    assert adapter.provider == "fake"
    assert adapter.model == "fake-deterministic"


def test_fake_adapter_has_safe_indonesian_and_english_defaults() -> None:
    adapter = FakeLLMAdapter()

    indonesian = StructuredSQLProposal.model_validate_json(
        asyncio.run(adapter.generate(_request("Berapa pelanggan yang aktif?"))).content
    )
    english = StructuredSQLProposal.model_validate_json(
        asyncio.run(adapter.generate(_request("Predict tomorrow's stock price"))).content
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


def test_gemini_adapter_sends_bounded_structured_request_and_parses_usage() -> None:
    observed: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["api_key"] = request.headers["x-goog-api-key"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": '{"intent":"unsupported","language":"id",'
                                    '"needs_clarification":false,"clarification_question":null,'
                                    '"assumptions":[],"sql":null,"tables":[],"columns":[],'
                                    '"confidence":1,"reasoning_summary":"Tidak didukung."}'
                                }
                            ]
                        },
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 120,
                    "candidatesTokenCount": 40,
                    "thoughtsTokenCount": 10,
                    "cachedContentTokenCount": 5,
                    "totalTokenCount": 170,
                },
            },
        )

    async def run() -> tuple[GeminiLLMAdapter, AdapterGeneration]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(
                SecretStr("test-gemini-key"),
                client=client,
                max_output_tokens=2_048,
                thinking_level="minimal",
            )
            return adapter, await adapter.generate(_request("Berapa pelanggan?"))

    adapter, generation = asyncio.run(run())
    assert adapter.provider == "gemini"
    assert adapter.model == "gemma-4-26b-a4b-it"
    assert "gemma-4-26b-a4b-it:generateContent" in str(observed["url"])
    assert observed["api_key"] == "test-gemini-key"
    payload: dict[str, Any] = observed["payload"]
    assert payload["store"] is False
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["maxOutputTokens"] == 2_048
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert generation.usage is not None
    assert generation.usage.input_tokens == 120
    assert generation.usage.output_tokens == 40
    assert generation.usage.reasoning_tokens == 10
    assert generation.usage.total_tokens == 170
    assert generation.finish_reason == "STOP"
    assert "test-gemini-key" not in repr(adapter)


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (401, LLMAdapterAuthenticationError),
        (403, LLMAdapterAuthenticationError),
        (429, LLMAdapterRateLimitError),
        (504, LLMAdapterTimeout),
        (503, LLMAdapterError),
    ],
)
def test_gemini_adapter_maps_http_failures_without_response_details(
    status_code: int,
    exception_type: type[Exception],
) -> None:
    secret_marker = "must-not-leak"

    async def run() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(status_code, text=f"provider {secret_marker}")
        )
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = GeminiLLMAdapter(SecretStr("test-key"), client=client)
            with pytest.raises(exception_type) as caught:
                await adapter.generate(_request("question"))
        assert secret_marker not in str(caught.value)

    asyncio.run(run())


def test_gemini_adapter_rejects_invalid_response_envelope() -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={}))
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = GeminiLLMAdapter(SecretStr("test-key"), client=client)
            with pytest.raises(LLMAdapterError, match="invalid response"):
                await adapter.generate(_request("question"))

    asyncio.run(run())


def test_gemini_adapter_sanitizes_network_failure() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("internal endpoint detail must-not-leak", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(SecretStr("test-key"), client=client)
            with pytest.raises(LLMAdapterError) as caught:
                await adapter.generate(_request("question"))
        assert "must-not-leak" not in str(caught.value)

    asyncio.run(run())


def test_gemini_adapter_rejects_non_json_provider_response() -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, text="not-json"))
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = GeminiLLMAdapter(SecretStr("test-key"), client=client)
            with pytest.raises(LLMAdapterError, match="invalid response"):
                await adapter.generate(_request("question"))

    asyncio.run(run())


def test_factory_builds_gemini_and_requires_key_and_supported_model() -> None:
    adapter = create_llm_adapter(
        AppSettings(
            llm_provider="gemini",
            llm_model="gemma-4-26b-a4b-it",
            llm_api_key="test-only-key",
            _env_file=None,
        )
    )
    assert isinstance(adapter, GeminiLLMAdapter)

    with pytest.raises(ConfigurationError, match="credential"):
        create_llm_adapter(
            AppSettings(
                llm_provider="gemini",
                llm_model="gemma-4-26b-a4b-it",
                _env_file=None,
            )
        )
    with pytest.raises(ConfigurationError, match="model"):
        create_llm_adapter(
            AppSettings(
                llm_provider="gemini",
                llm_model="not-a-real-model",
                llm_api_key="test-only-key",
                _env_file=None,
            )
        )


def test_provider_request_budget_caps_actual_gemini_calls() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
        )

    async def run() -> None:
        budget = ProviderRequestBudget(1)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            metered = MeteredLLMAdapter(
                GeminiLLMAdapter(SecretStr("test-key"), client=client),
                budget,
            )
            assert metered.provider == "gemini"
            assert metered.model == "gemma-4-26b-a4b-it"
            await metered.generate(_request("first"))
            with pytest.raises(ProviderRequestLimitExceeded):
                await metered.generate(_request("second"))
        assert budget.limit == budget.attempted == 1

    asyncio.run(run())
    assert calls == 1


@pytest.mark.parametrize(
    "arguments",
    (
        {"limit": -1},
        {"limit": 1, "initial_attempted": 2},
        {"limit": 1, "interval_seconds": -1},
    ),
)
def test_provider_request_budget_rejects_invalid_bounds(arguments: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ProviderRequestBudget(**arguments)
