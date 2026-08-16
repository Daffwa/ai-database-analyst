"""Run one explicit, payload-safe live Gemini/Gemma connectivity smoke test."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from backend.core.config import AppSettings
from backend.core.errors import ConfigurationError, LLMOutputError
from backend.llm.adapters import (
    LLMAdapterAuthenticationError,
    LLMAdapterError,
    LLMAdapterRateLimitError,
    LLMAdapterTimeout,
)
from backend.llm.factory import create_llm_adapter
from backend.schemas.llm import AdapterRequest
from backend.services.output_parser import StructuredOutputParser


async def _run(settings: AppSettings) -> dict[str, object]:
    adapter = create_llm_adapter(settings)
    generation = await adapter.generate(
        AdapterRequest(
            request_id="live-gemini-smoke",
            question="Synthetic connectivity smoke test",
            system_prompt=(
                "Return one JSON object matching the supplied response schema. "
                "Use intent unsupported, language en, needs_clarification false, "
                "null clarification_question and sql, empty assumptions/tables/columns, "
                "confidence 1, and a brief reasoning_summary."
            ),
            user_prompt=json.dumps(
                {"question": "Synthetic connectivity smoke test", "schema_context": {}},
                separators=(",", ":"),
            ),
        )
    )
    proposal = StructuredOutputParser(max_characters=settings.llm_max_output_characters).parse(
        generation.content
    )
    usage = generation.usage
    return {
        "status": "passed",
        "provider": adapter.provider,
        "model": adapter.model,
        "intent": proposal.intent.value,
        "input_tokens": usage.input_tokens if usage is not None else None,
        "output_tokens": usage.output_tokens if usage is not None else None,
        "total_tokens": usage.total_tokens if usage is not None else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Confirm that a rotated local credential may make one live API request.",
    )
    args = parser.parse_args(argv)
    if not args.confirm_live:
        print("Live request not run. Re-run with --confirm-live after rotating the exposed key.")
        return 2

    settings = AppSettings()
    if settings.llm_provider.strip().casefold() != "gemini":
        print("Live request not run: configure LLM_PROVIDER=gemini in the local environment.")
        return 2

    try:
        result = asyncio.run(_run(settings))
    except ConfigurationError:
        print("Live request not run: Gemini configuration is incomplete.")
        return 2
    except LLMAdapterAuthenticationError:
        print("Live Gemini smoke failed: credential rejected.")
        return 1
    except LLMAdapterRateLimitError:
        print("Live Gemini smoke failed: quota or rate limit reached.")
        return 1
    except LLMAdapterTimeout:
        print("Live Gemini smoke failed: request timed out.")
        return 1
    except (LLMAdapterError, LLMOutputError):
        print("Live Gemini smoke failed: provider output was unavailable or invalid.")
        return 1

    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
