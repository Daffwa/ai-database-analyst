"""Provider-neutral structured SQL generation without query execution."""

from __future__ import annotations

import asyncio
from time import perf_counter

from backend.core.errors import LLMProviderError, LLMTimeoutError
from backend.llm.adapters import (
    BaseLLMAdapter,
    LLMAdapterError,
    LLMAdapterTimeout,
)
from backend.schemas.database import SchemaAllowlist, SchemaSnapshot
from backend.schemas.llm import AdapterRequest, GenerationResult
from backend.schemas.semantic import SemanticResolution
from backend.services.output_parser import StructuredOutputParser, validate_declared_schema
from backend.services.prompt_builder import PromptBuilder


class SQLGenerator:
    """Build a prompt, invoke an adapter, and validate its structured proposal."""

    def __init__(
        self,
        adapter: BaseLLMAdapter,
        prompt_builder: PromptBuilder,
        parser: StructuredOutputParser,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._adapter = adapter
        self._prompt_builder = prompt_builder
        self._parser = parser
        self._timeout_seconds = timeout_seconds

    async def generate(
        self,
        *,
        request_id: str,
        question: str,
        snapshot: SchemaSnapshot,
        allowlist: SchemaAllowlist,
        semantic_resolution: SemanticResolution | None = None,
    ) -> GenerationResult:
        prompt = self._prompt_builder.build(
            request_id=request_id,
            question=question,
            snapshot=snapshot,
            semantic_resolution=semantic_resolution,
        )
        adapter_request = AdapterRequest(
            request_id=request_id,
            question=question,
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
        )
        started = perf_counter()
        try:
            raw_output = await asyncio.wait_for(
                self._adapter.generate(adapter_request),
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, LLMAdapterTimeout) as exc:
            raise LLMTimeoutError() from exc
        except LLMAdapterError as exc:
            raise LLMProviderError() from exc
        except Exception as exc:
            raise LLMProviderError() from exc
        latency_ms = (perf_counter() - started) * 1_000

        proposal = self._parser.parse(raw_output)
        validate_declared_schema(
            proposal,
            allowlist,
            context_tables=prompt.included_tables,
        )
        return GenerationResult(
            proposal=proposal,
            prompt=prompt,
            provider=self._adapter.provider,
            model=self._adapter.model,
            llm_latency_ms=latency_ms,
        )

    @property
    def provider(self) -> str:
        return self._adapter.provider

    @property
    def model(self) -> str:
        return self._adapter.model

    @property
    def prompt_version(self) -> str:
        return self._prompt_builder.prompt_version
