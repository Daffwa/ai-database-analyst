"""Provider-neutral LLM interfaces and concrete provider implementations."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping
from time import monotonic
from typing import Any, Final, Literal

import httpx
from pydantic import SecretStr

from backend.schemas.llm import (
    AdapterGeneration,
    AdapterRequest,
    LanguageCode,
    LLMIntent,
    LLMTokenUsage,
    StructuredSQLProposal,
)

GEMINI_API_BASE_URL: Final = "https://generativelanguage.googleapis.com/v1beta"
SUPPORTED_GEMMA_4_MODELS: Final = frozenset(
    {
        "gemma-4-26b-a4b-it",
        "gemma-4-31b-it",
    }
)

GEMINI_SQL_PROPOSAL_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": ["analysis", "clarification", "unsupported"]},
        "language": {"type": "string", "enum": ["id", "en"]},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "sql": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "tables": {"type": "array", "items": {"type": "string"}},
        "columns": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "intent",
        "language",
        "needs_clarification",
        "clarification_question",
        "assumptions",
        "sql",
        "tables",
        "columns",
        "confidence",
        "reasoning_summary",
    ],
}


class LLMAdapterError(Exception):
    """Internal provider failure that must be sanitized at the service boundary."""


class LLMAdapterTimeout(LLMAdapterError):
    """Internal signal for a provider-side timeout."""


class LLMAdapterAuthenticationError(LLMAdapterError):
    """Internal signal for a rejected provider credential."""


class LLMAdapterRateLimitError(LLMAdapterError):
    """Internal signal for a provider-side quota or rate limit."""


class ProviderRequestLimitExceeded(LLMAdapterError):
    """Internal signal that a local hard provider-call cap was reached."""


class ProviderRequestBudget:
    """Concurrency-safe hard cap and minimum interval for actual provider calls."""

    def __init__(
        self,
        limit: int,
        *,
        initial_attempted: int = 0,
        interval_seconds: float = 0.0,
    ) -> None:
        if limit < 0:
            raise ValueError("provider request limit must not be negative")
        if not 0 <= initial_attempted <= limit:
            raise ValueError("initial provider request count is outside the request limit")
        if interval_seconds < 0:
            raise ValueError("provider request interval must not be negative")
        self._limit = limit
        self._attempted = initial_attempted
        self._interval_seconds = interval_seconds
        self._last_started: float | None = None
        self._lock = asyncio.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def attempted(self) -> int:
        return self._attempted

    async def reserve(self) -> None:
        """Reserve exactly one call before network I/O, failing closed at the cap."""

        async with self._lock:
            if self._attempted >= self._limit:
                raise ProviderRequestLimitExceeded("local provider request budget exhausted")
            if self._last_started is not None:
                elapsed = monotonic() - self._last_started
                if elapsed < self._interval_seconds:
                    await asyncio.sleep(self._interval_seconds - elapsed)
            self._last_started = monotonic()
            self._attempted += 1


class BaseLLMAdapter(ABC):
    """Small async boundary that keeps provider SDKs out of domain services."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return a stable provider identifier."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the configured model identifier."""

    @abstractmethod
    async def generate(self, request: AdapterRequest) -> AdapterGeneration:
        """Return raw structured output and safe metadata without executing SQL."""


class MeteredLLMAdapter(BaseLLMAdapter):
    """Decorator that meters every real adapter request, including repair calls."""

    def __init__(self, adapter: BaseLLMAdapter, budget: ProviderRequestBudget) -> None:
        self._adapter = adapter
        self._budget = budget

    @property
    def provider(self) -> str:
        return self._adapter.provider

    @property
    def model(self) -> str:
        return self._adapter.model

    async def generate(self, request: AdapterRequest) -> AdapterGeneration:
        await self._budget.reserve()
        return await self._adapter.generate(request)


class FakeLLMAdapter(BaseLLMAdapter):
    """Deterministic offline adapter keyed by normalized exact questions."""

    def __init__(
        self,
        responses: Mapping[str, str] | None = None,
        *,
        model: str = "fake-deterministic",
        failure: str | None = None,
    ) -> None:
        self._responses = {
            _normalize_question(question): response
            for question, response in (responses or {}).items()
        }
        self._model = model
        self._failure = failure

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: AdapterRequest) -> AdapterGeneration:
        if self._failure == "timeout":
            raise LLMAdapterTimeout("fake internal timeout detail")
        if self._failure == "provider":
            raise LLMAdapterError("fake internal provider detail")

        response = self._responses.get(_normalize_question(request.question))
        if response is not None:
            return AdapterGeneration(content=response)
        return AdapterGeneration(
            content=StructuredSQLProposal(
                intent=LLMIntent.UNSUPPORTED,
                language=_detect_language(request.question),
                needs_clarification=False,
                confidence=1.0,
                reasoning_summary=(
                    "Pertanyaan belum tersedia dalam katalog demo deterministik."
                    if _detect_language(request.question) is LanguageCode.INDONESIAN
                    else "The question is not available in the deterministic demo catalog."
                ),
            ).model_dump_json()
        )


class GeminiLLMAdapter(BaseLLMAdapter):
    """Gemini Developer API adapter restricted to hosted Gemma 4 models."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        model: str = "gemma-4-26b-a4b-it",
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 4_096,
        thinking_level: Literal["minimal", "high"] = "minimal",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if model not in SUPPORTED_GEMMA_4_MODELS:
            raise ValueError("Unsupported hosted Gemma 4 model")
        if not api_key.get_secret_value():
            raise ValueError("Gemini API key must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._thinking_level = thinking_level
        self._client = client

    @property
    def provider(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: AdapterRequest) -> AdapterGeneration:
        generation_config: dict[str, Any] = {
            "responseMimeType": "application/json",
            "maxOutputTokens": self._max_output_tokens,
            "temperature": 0,
            "thinkingConfig": {"thinkingLevel": self._thinking_level},
        }
        if request.enforce_response_schema:
            generation_config["responseJsonSchema"] = (
                request.response_schema or GEMINI_SQL_PROPOSAL_SCHEMA
            )
        payload = {
            "systemInstruction": {"parts": [{"text": request.system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request.user_prompt}],
                }
            ],
            "generationConfig": generation_config,
            "store": False,
        }
        response = await self._post(payload)
        return _parse_gemini_generation(response)

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        url = f"{GEMINI_API_BASE_URL}/models/{self._model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key.get_secret_value(),
        }
        try:
            if self._client is not None:
                response = await self._client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMAdapterTimeout("Gemini request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMAdapterError("Gemini network request failed") from exc

        if response.status_code in {401, 403}:
            raise LLMAdapterAuthenticationError("Gemini rejected the configured credential")
        if response.status_code == 429:
            raise LLMAdapterRateLimitError("Gemini quota or rate limit reached")
        if response.status_code in {408, 504}:
            raise LLMAdapterTimeout("Gemini request timed out")
        if response.is_error:
            raise LLMAdapterError("Gemini provider request failed")
        return response


def _parse_gemini_generation(response: httpx.Response) -> AdapterGeneration:
    try:
        payload = response.json()
        candidates = payload["candidates"]
        candidate = candidates[0]
        parts = candidate["content"]["parts"]
        content = "".join(
            part["text"]
            for part in parts
            if isinstance(part, dict)
            and isinstance(part.get("text"), str)
            and not part.get("thought", False)
        )
        if not content.strip():
            raise ValueError("Gemini response did not contain candidate text")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMAdapterError("Gemini returned an invalid response envelope") from exc

    usage_payload = payload.get("usageMetadata")
    usage = _parse_gemini_usage(usage_payload) if isinstance(usage_payload, dict) else None
    finish_reason = candidate.get("finishReason")
    return AdapterGeneration(
        content=content,
        usage=usage,
        finish_reason=(finish_reason[:100] if isinstance(finish_reason, str) else None),
    )


def _parse_gemini_usage(payload: dict[str, Any]) -> LLMTokenUsage:
    return LLMTokenUsage(
        input_tokens=_optional_non_negative_int(payload.get("promptTokenCount")),
        output_tokens=_optional_non_negative_int(payload.get("candidatesTokenCount")),
        reasoning_tokens=_optional_non_negative_int(payload.get("thoughtsTokenCount")),
        cached_input_tokens=_optional_non_negative_int(payload.get("cachedContentTokenCount")),
        total_tokens=_optional_non_negative_int(payload.get("totalTokenCount")),
    )


def _optional_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _normalize_question(question: str) -> str:
    return " ".join(question.casefold().split())


def _detect_language(question: str) -> LanguageCode:
    indonesian_markers = {
        "apa",
        "berapa",
        "dari",
        "dengan",
        "karyawan",
        "pelanggan",
        "pendapatan",
        "tampilkan",
        "yang",
    }
    tokens = set(_normalize_question(question).replace("?", "").split())
    return LanguageCode.INDONESIAN if tokens & indonesian_markers else LanguageCode.ENGLISH
