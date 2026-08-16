"""Global test isolation for provider-backed settings."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from backend.core.config import clear_settings_cache


@pytest.fixture(autouse=True)
def _force_offline_llm_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep every ordinary pytest run offline even when local ``.env`` uses Gemini."""

    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_MODEL", "fake-deterministic")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    clear_settings_cache()
    yield
    clear_settings_cache()
