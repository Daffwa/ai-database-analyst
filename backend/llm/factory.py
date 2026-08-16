"""Construction of configured provider-neutral LLM adapters."""

from __future__ import annotations

from collections.abc import Mapping

from backend.core.config import AppSettings
from backend.core.errors import ConfigurationError
from backend.llm.adapters import (
    SUPPORTED_GEMMA_4_MODELS,
    BaseLLMAdapter,
    FakeLLMAdapter,
    GeminiLLMAdapter,
    MeteredLLMAdapter,
    ProviderRequestBudget,
)


def create_llm_adapter(
    settings: AppSettings,
    *,
    fake_responses: Mapping[str, str] | None = None,
    request_budget: ProviderRequestBudget | None = None,
) -> BaseLLMAdapter:
    """Create the configured adapter without importing optional provider SDKs."""

    provider = settings.llm_provider.strip().casefold()
    if provider == "fake":
        return FakeLLMAdapter(fake_responses, model=settings.llm_model)
    if provider == "gemini":
        if settings.llm_model not in SUPPORTED_GEMMA_4_MODELS:
            raise ConfigurationError("The configured Gemini model is not supported.")
        if settings.llm_api_key is None or not settings.has_llm_credentials:
            raise ConfigurationError("The Gemini API credential is not configured.")
        adapter: BaseLLMAdapter = GeminiLLMAdapter(
            settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
            thinking_level=settings.llm_thinking_level,
        )
        return MeteredLLMAdapter(adapter, request_budget) if request_budget is not None else adapter
    raise ConfigurationError("The configured LLM provider is not available in this build.")
