from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from backend.core.errors import LLMOutputError, LLMProviderError, LLMTimeoutError
from backend.llm.adapters import GeminiLLMAdapter
from backend.schemas.database import SchemaAllowlist
from backend.schemas.llm import GenerationResult
from backend.services.planned_sql_generator import PlannedPromptBuilder, PlannedSQLGenerator
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService

ROOT = Path(__file__).resolve().parents[2]


def _provider_response(
    plan: dict[str, object], *, input_tokens: int, output_tokens: int
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(plan)}]}}],
            "usageMetadata": {
                "promptTokenCount": input_tokens,
                "candidatesTokenCount": output_tokens,
                "totalTokenCount": input_tokens + output_tokens,
            },
        },
    )


def _detail_plan(column: str) -> dict[str, object]:
    return {
        "intent": "analysis",
        "language": "id",
        "needs_clarification": False,
        "clarification_question": None,
        "assumptions": [],
        "base_table": "Customer",
        "tables": ["Customer"],
        "join_ids": [],
        "outputs": [
            {
                "kind": "column",
                "alias": "CustomerId",
                "column": column,
                "second_column": None,
                "aggregate": None,
                "metric_id": None,
                "time_grain": None,
                "round_digits": None,
                "group_by": False,
            },
            {
                "kind": "column",
                "alias": "FirstName",
                "column": "Customer.FirstName",
                "second_column": None,
                "aggregate": None,
                "metric_id": None,
                "time_grain": None,
                "round_digits": None,
                "group_by": False,
            },
            {
                "kind": "column",
                "alias": "LastName",
                "column": "Customer.LastName",
                "second_column": None,
                "aggregate": None,
                "metric_id": None,
                "time_grain": None,
                "round_digits": None,
                "group_by": False,
            },
        ],
        "filters": [
            {
                "scope": "where",
                "target": "Customer.Country",
                "operator": "equals",
                "values": ["Brazil"],
                "benchmark": None,
            }
        ],
        "related_filters": [],
        "order_by": [{"target_alias": "CustomerId", "direction": "ascending"}],
        "limit": 5,
        "confidence": 0.95,
        "reasoning_summary": "Pelanggan Brasil diurutkan berdasarkan ID.",
    }


def _unsupported_plan() -> dict[str, object]:
    return {
        "intent": "unsupported",
        "language": "id",
        "needs_clarification": False,
        "clarification_question": None,
        "assumptions": [],
        "base_table": None,
        "tables": [],
        "join_ids": [],
        "outputs": [],
        "filters": [],
        "related_filters": [],
        "order_by": [],
        "limit": None,
        "confidence": 1.0,
        "reasoning_summary": "Permintaan tidak didukung.",
    }


def _album_count_plan(group_by: object) -> dict[str, object]:
    return {
        "intent": "analysis",
        "language": "en",
        "needs_clarification": False,
        "clarification_question": None,
        "assumptions": [],
        "base_table": "Album",
        "tables": ["Album", "Track"],
        "join_ids": [],
        "outputs": [
            {
                "kind": "column",
                "alias": "AlbumId",
                "column": "Album.AlbumId",
                "second_column": None,
                "aggregate": None,
                "metric_id": None,
                "time_grain": None,
                "round_digits": None,
                "group_by": True,
            },
            {
                "kind": "column",
                "alias": "Title",
                "column": "Album.Title",
                "second_column": None,
                "aggregate": None,
                "metric_id": None,
                "time_grain": None,
                "round_digits": None,
                "group_by": True,
            },
            {
                "kind": "aggregate",
                "alias": "track_count",
                "column": "Track.TrackId",
                "second_column": None,
                "aggregate": "count",
                "metric_id": None,
                "time_grain": None,
                "round_digits": None,
                "group_by": False,
            },
        ],
        "filters": [
            {
                "scope": "having",
                "target": "track_count",
                "operator": "greater_than",
                "values": [],
                "benchmark": {
                    "kind": "group_average",
                    "table": "Track",
                    "column": "Track.TrackId",
                    "aggregate": "count",
                    "group_by": group_by,
                },
            }
        ],
        "related_filters": [],
        "order_by": [
            {"target_alias": "track_count", "direction": "descending"},
            {"target_alias": "AlbumId", "direction": "ascending"},
        ],
        "limit": 5,
        "confidence": 0.9,
        "reasoning_summary": "Count tracks per album and compare with the grouped average.",
    }


def test_real_gemini_adapter_plan_path_repairs_once_without_fake_llm() -> None:
    requests: list[httpx.Request] = []
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    responses = [
        _provider_response(
            _detail_plan("Customer.UnknownColumn"), input_tokens=100, output_tokens=50
        ),
        _provider_response(_detail_plan("Customer.CustomerId"), input_tokens=110, output_tokens=45),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["store"] is False
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseJsonSchema" not in payload["generationConfig"]
        if len(requests) == 2:
            repair_payload = json.loads(payload["contents"][0]["parts"][0]["text"])
            assert repair_payload["repair_feedback"]["error_code"] == "unknown_column"
        return responses[len(requests) - 1]

    async def generate_plan() -> GenerationResult:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(
                SecretStr("local-test-key"),
                model="gemma-4-31b-it",
                client=client,
            )
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=1,
            )
            return await generator.generate(
                request_id="planned-gemini-test",
                question="Tampilkan lima pelanggan dari Brasil berdasarkan ID.",
                snapshot=snapshot,
                allowlist=SchemaAllowlist.from_snapshot(snapshot),
            )

    result = asyncio.run(generate_plan())

    assert len(requests) == 2
    assert result.llm_request_count == 2
    assert result.repair_attempts == 1
    assert result.repair_succeeded is True
    assert result.llm_token_usage is not None
    assert result.llm_token_usage.input_tokens == 210
    assert result.llm_token_usage.output_tokens == 95
    assert result.proposal.sql == (
        "SELECT Customer.CustomerId AS CustomerId, Customer.FirstName AS FirstName, "
        "Customer.LastName AS LastName FROM Customer WHERE Customer.Country = 'Brazil' "
        "ORDER BY CustomerId ASC LIMIT 5"
    )
    security = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(dialect="sqlite", max_rows=500),
    )
    assert security.validate(
        result.proposal.sql,
        declared_tables=result.proposal.tables,
        declared_columns=result.proposal.columns,
    ).safe


def test_real_gemini_plan_path_retries_one_transient_provider_failure() -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(503, text="private transient detail")
        return _provider_response(
            _detail_plan("Customer.CustomerId"),
            input_tokens=120,
            output_tokens=40,
        )

    async def generate_plan() -> GenerationResult:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(SecretStr("local-test-key"), client=client)
            snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=1,
                provider_retry_base_delay_seconds=0,
            )
            return await generator.generate(
                request_id="planned-provider-retry-test",
                question="Tampilkan lima pelanggan dari Brasil berdasarkan ID.",
                snapshot=snapshot,
                allowlist=SchemaAllowlist.from_snapshot(snapshot),
            )

    result = asyncio.run(generate_plan())

    assert requests == 2
    assert result.llm_request_count == 2
    assert result.repair_attempts == 0
    assert result.repair_succeeded is None
    assert result.llm_token_usage is not None
    assert result.llm_token_usage.total_tokens == 160


def test_real_gemini_plan_path_does_not_retry_authentication_failure() -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(403, text="private authentication detail")

    async def generate_plan() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(SecretStr("local-test-key"), client=client)
            snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=1,
                provider_retry_base_delay_seconds=0,
            )
            with pytest.raises(LLMProviderError):
                await generator.generate(
                    request_id="planned-auth-no-retry-test",
                    question="Berapa pelanggan?",
                    snapshot=snapshot,
                    allowlist=SchemaAllowlist.from_snapshot(snapshot),
                )

    asyncio.run(generate_plan())

    assert requests == 1


def test_real_gemini_plan_path_repairs_invalid_benchmark_group_by_type() -> None:
    requests: list[httpx.Request] = []
    responses = (
        _provider_response(
            _album_count_plan({"column": "Track.AlbumId"}),
            input_tokens=150,
            output_tokens=80,
        ),
        _provider_response(
            _album_count_plan("Track.AlbumId"),
            input_tokens=160,
            output_tokens=75,
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 2:
            payload = json.loads(request.content)
            repair_payload = json.loads(payload["contents"][0]["parts"][0]["text"])
            assert repair_payload["repair_feedback"]["error_code"] == (
                "invalid_benchmark_group_by_type"
            )
        return responses[len(requests) - 1]

    async def generate_plan() -> GenerationResult:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(SecretStr("local-test-key"), client=client)
            snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=1,
            )
            return await generator.generate(
                request_id="planned-benchmark-repair-test",
                question=(
                    "Show five albums whose track count is above the average album track count."
                ),
                snapshot=snapshot,
                allowlist=SchemaAllowlist.from_snapshot(snapshot),
            )

    result = asyncio.run(generate_plan())

    assert len(requests) == 2
    assert result.repair_attempts == 1
    assert result.repair_succeeded is True
    assert result.proposal.sql is not None
    assert "HAVING COUNT(Track.TrackId) > (SELECT AVG(group_value)" in result.proposal.sql


def test_real_gemini_adapter_plan_path_returns_bounded_unsupported() -> None:
    async def generate() -> GenerationResult:
        transport = httpx.MockTransport(
            lambda _request: _provider_response(
                _unsupported_plan(),
                input_tokens=0,
                output_tokens=0,
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = GeminiLLMAdapter(SecretStr("local-test-key"), client=client)
            snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=0,
            )
            return await generator.generate(
                request_id="planned-unsupported-test",
                question="Prediksi harga saham besok.",
                snapshot=snapshot,
                allowlist=SchemaAllowlist.from_snapshot(snapshot),
            )

    result = asyncio.run(generate())

    assert result.proposal.intent.value == "unsupported"
    assert result.proposal.sql is None
    assert result.llm_request_count == 1
    assert result.prompt.prompt_version == "v5-plan"


def test_real_gemini_adapter_plan_path_stops_after_one_invalid_repair() -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return _provider_response({}, input_tokens=1, output_tokens=1)

    async def generate() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(SecretStr("local-test-key"), client=client)
            snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=1,
            )
            with pytest.raises(LLMOutputError) as caught:
                await generator.generate(
                    request_id="planned-invalid-test",
                    question="Berapa pelanggan?",
                    snapshot=snapshot,
                    allowlist=SchemaAllowlist.from_snapshot(snapshot),
                )
            assert str(caught.value.details["plan_error_code"]).startswith("invalid_plan_contract_")
            assert caught.value.details["repair_attempts"] == 1
            assert caught.value.details["input_tokens"] == 2
            assert caught.value.details["output_tokens"] == 2
            assert caught.value.details["last_output_characters"] == 2
            assert caught.value.details["finish_reason"] is None

    asyncio.run(generate())
    assert requests == 2


@pytest.mark.parametrize(
    ("raw_content", "shape"),
    (
        ("```json\n{}\n```", "fenced"),
        ('{"intent":"analysis"', "truncated_object"),
        ('{"intent":}', "malformed_object"),
        ("[not-json", "array_text"),
        ("plain text", "non_json_text"),
    ),
)
def test_plan_json_shape_diagnostics_remain_sanitized(
    raw_content: str,
    shape: str,
) -> None:
    async def generate() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": raw_content}]}}]},
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = GeminiLLMAdapter(SecretStr("local-test-key"), client=client)
            snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=0,
            )
            with pytest.raises(LLMOutputError) as caught:
                await generator.generate(
                    request_id=f"planned-{shape}-test",
                    question="Berapa pelanggan?",
                    snapshot=snapshot,
                    allowlist=SchemaAllowlist.from_snapshot(snapshot),
                )
            assert caught.value.details["plan_error_code"] == f"invalid_plan_json_{shape}"
            assert raw_content not in str(caught.value.details)

    asyncio.run(generate())


@pytest.mark.parametrize(
    ("provider_failure", "expected_error"),
    (("http", LLMProviderError), ("timeout", LLMTimeoutError)),
)
def test_real_gemini_adapter_plan_path_sanitizes_provider_failures(
    provider_failure: str,
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if provider_failure == "timeout":
            raise httpx.ReadTimeout("private provider detail", request=request)
        return httpx.Response(500, text="private provider detail")

    async def generate() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiLLMAdapter(SecretStr("local-test-key"), client=client)
            snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
            bundle = load_semantic_bundle(ROOT / "semantic")
            generator = PlannedSQLGenerator(
                adapter,
                PlannedPromptBuilder(SchemaRetriever(), bundle),
                bundle,
                max_plan_repairs=0,
            )
            with pytest.raises(expected_error) as caught:
                await generator.generate(
                    request_id="planned-provider-error-test",
                    question="Berapa pelanggan?",
                    snapshot=snapshot,
                    allowlist=SchemaAllowlist.from_snapshot(snapshot),
                )
            assert "private provider detail" not in str(caught.value)

    asyncio.run(generate())
