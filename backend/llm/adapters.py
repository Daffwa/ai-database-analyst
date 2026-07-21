"""Provider-neutral LLM interface and deterministic fake implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from backend.schemas.llm import AdapterRequest, LanguageCode, LLMIntent, StructuredSQLProposal


class LLMAdapterError(Exception):
    """Internal provider failure that must be sanitized at the service boundary."""


class LLMAdapterTimeout(LLMAdapterError):
    """Internal signal for a provider-side timeout."""


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
    async def generate(self, request: AdapterRequest) -> str:
        """Return raw structured output without parsing or executing SQL."""


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

    async def generate(self, request: AdapterRequest) -> str:
        if self._failure == "timeout":
            raise LLMAdapterTimeout("fake internal timeout detail")
        if self._failure == "provider":
            raise LLMAdapterError("fake internal provider detail")

        response = self._responses.get(_normalize_question(request.question))
        if response is not None:
            return response
        return StructuredSQLProposal(
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
