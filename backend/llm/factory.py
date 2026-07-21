"""Construction of configured provider-neutral LLM adapters."""

from __future__ import annotations

from collections.abc import Mapping

from backend.core.config import AppSettings
from backend.core.errors import ConfigurationError
from backend.llm.adapters import BaseLLMAdapter, FakeLLMAdapter


def create_llm_adapter(
    settings: AppSettings,
    *,
    fake_responses: Mapping[str, str] | None = None,
) -> BaseLLMAdapter:
    """Create the configured adapter without importing optional provider SDKs."""

    provider = settings.llm_provider.strip().casefold()
    if provider == "fake":
        return FakeLLMAdapter(fake_responses, model=settings.llm_model)
    raise ConfigurationError("The configured LLM provider is not available in this build.")
