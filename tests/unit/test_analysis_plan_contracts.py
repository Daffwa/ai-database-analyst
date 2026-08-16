from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.analysis_plan import (
    AnalysisPlan,
    PlanAggregate,
    PlanBenchmark,
    PlanBenchmarkKind,
    PlanFilter,
    PlanFilterOperator,
    PlanOutput,
    PlanOutputKind,
    PlanTimeGrain,
)
from backend.schemas.llm import LanguageCode, LLMIntent
from backend.services.analysis_plan import (
    AnalysisPlanCompiler,
    AnalysisPlanError,
    AnalysisPlanGrounder,
    AnalysisPlanNormalizer,
    CompiledAnalysisPlan,
    PlanSQLAlignmentValidator,
)
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle

ROOT = Path(__file__).resolve().parents[2]


def _output_values() -> dict[str, object]:
    return {
        "kind": "column",
        "alias": "InvoiceId",
        "column": "Invoice.InvoiceId",
        "second_column": None,
        "aggregate": None,
        "metric_id": None,
        "time_grain": None,
        "round_digits": None,
        "group_by": False,
    }


def _plan_values() -> dict[str, object]:
    return {
        "intent": "analysis",
        "language": "id",
        "needs_clarification": False,
        "clarification_question": None,
        "assumptions": [],
        "base_table": "Invoice",
        "tables": ["Invoice"],
        "join_ids": [],
        "outputs": [_output_values()],
        "filters": [],
        "related_filters": [],
        "order_by": [],
        "limit": None,
        "confidence": 0.9,
        "reasoning_summary": "Rencana terikat kontrak.",
    }


def test_output_contract_rejects_incompatible_kind_fields() -> None:
    invalid_updates = (
        {"column": None},
        {"round_digits": 2},
        {"kind": "aggregate", "aggregate": None},
        {"kind": "aggregate", "aggregate": "sum", "metric_id": "total_revenue"},
        {"kind": "aggregate", "aggregate": "sum_product"},
        {"kind": "aggregate", "aggregate": "count", "second_column": "Invoice.Total"},
        {"kind": "metric", "column": None, "metric_id": None},
        {"kind": "metric", "column": None, "metric_id": "total_revenue", "group_by": True},
        {"kind": "time_bucket", "time_grain": None},
        {"kind": "time_bucket", "time_grain": "year", "round_digits": 2},
        {"kind": "time_bucket", "time_grain": "year", "group_by": False},
    )
    for updates in invalid_updates:
        values = {**_output_values(), **updates}
        with pytest.raises(ValidationError):
            PlanOutput.model_validate(values)


def test_benchmark_filter_and_related_contracts_fail_closed() -> None:
    invalid_benchmarks = (
        {
            "kind": "global_average",
            "table": "Invoice",
            "column": "Invoice.Total",
            "aggregate": "sum",
        },
        {"kind": "group_average", "table": "Invoice", "column": "Invoice.Total"},
        {
            "kind": "group_average",
            "table": "Invoice",
            "column": "Invoice.Total",
            "aggregate": "maximum",
            "group_by": "Invoice.CustomerId",
        },
    )
    for benchmark_values in invalid_benchmarks:
        with pytest.raises(ValidationError):
            PlanBenchmark.model_validate(benchmark_values)

    explicit_global_average = PlanBenchmark(
        kind=PlanBenchmarkKind.GLOBAL_AVERAGE,
        table="Invoice",
        column="Invoice.Total",
        aggregate=PlanAggregate.AVERAGE,
    )
    assert explicit_global_average.aggregate is PlanAggregate.AVERAGE

    benchmark = PlanBenchmark(
        kind=PlanBenchmarkKind.GLOBAL_AVERAGE,
        table="Invoice",
        column="Invoice.Total",
    )
    invalid_filters = (
        {"operator": "equals", "values": [True]},
        {"operator": "is_null", "values": [1]},
        {"operator": "greater_than", "values": [1], "benchmark": benchmark},
        {"operator": "between", "values": [1]},
        {"operator": "in", "values": []},
        {"operator": "equals", "values": []},
        {"scope": "having", "operator": "equals", "values": [1]},
    )
    for updates in invalid_filters:
        with pytest.raises(ValidationError):
            PlanFilter.model_validate({"target": "Invoice.Total", **updates})


def test_plan_normalizer_canonicalizes_only_bounded_aliases_and_benchmarks() -> None:
    normalized = AnalysisPlanNormalizer.normalize(
        {
            "outputs": [{"alias": "track name"}, {"alias": "2 unsafe"}],
            "order_by": [{"target_alias": "track name"}],
            "filters": [
                {
                    "scope": "having",
                    "target": "track name",
                    "values": None,
                    "benchmark": {
                        "kind": "global_average",
                        "table": "Track",
                        "column": "TrackId",
                        "aggregate": "count",
                        "group_by": ["AlbumId"],
                    },
                }
            ],
        }
    )

    assert normalized["outputs"][0]["alias"] == "track_name"
    assert normalized["outputs"][1]["alias"] == "2 unsafe"
    assert normalized["order_by"][0]["target_alias"] == "track_name"
    assert normalized["filters"][0]["target"] == "track_name"
    benchmark = normalized["filters"][0]["benchmark"]
    assert benchmark["kind"] == "group_average"
    assert benchmark["column"] == "Track.TrackId"
    assert benchmark["group_by"] == "Track.AlbumId"
    assert normalized["filters"][0]["values"] == []

    valid_filter = {
        "target": "Track.UnitPrice",
        "operator": "greater_than",
        "values": [1],
    }
    invalid_related = (
        {
            "outer_column": "Artist.ArtistId",
            "subquery_select_column": "Album.ArtistId",
            "base_table": "Album",
            "tables": ["Track"],
            "filters": [valid_filter],
        },
        {
            "outer_column": "Artist.ArtistId",
            "subquery_select_column": "Album.ArtistId",
            "base_table": "Album",
            "tables": ["Album", "Album"],
            "filters": [valid_filter],
        },
    )
    for related_values in invalid_related:
        payload = _plan_values()
        payload["related_filters"] = [related_values]
        with pytest.raises(ValidationError):
            AnalysisPlan.model_validate(payload)


def test_plan_normalizer_safely_salvages_typed_output_residue() -> None:
    payload = _plan_values()
    payload["outputs"] = [
        {
            **_output_values(),
            "round_digits": 2,
            "aggregate": "count",
            "metric_id": "invoice_count",
        }
    ]

    plan = AnalysisPlan.model_validate(AnalysisPlanNormalizer.normalize(payload))

    assert plan.outputs == (
        PlanOutput(kind=PlanOutputKind.COLUMN, alias="InvoiceId", column="Invoice.InvoiceId"),
    )


def test_plan_normalizer_canonicalizes_unsupported_to_a_non_executable_plan() -> None:
    payload = {
        **_plan_values(),
        "intent": "unsupported",
        "unsupported": "database credentials are outside the safe scope",
    }

    plan = AnalysisPlan.model_validate(AnalysisPlanNormalizer.normalize(payload))

    assert plan.intent is LLMIntent.UNSUPPORTED
    assert plan.base_table is None
    assert plan.outputs == ()
    assert plan.filters == ()
    assert plan.limit is None

    analysis_with_unsupported_marker = {
        **_plan_values(),
        "unsupported": "system catalogs and credentials are forbidden",
    }
    marked = AnalysisPlan.model_validate(
        AnalysisPlanNormalizer.normalize(analysis_with_unsupported_marker)
    )
    assert marked.intent is LLMIntent.UNSUPPORTED
    assert marked.outputs == ()


def test_analysis_plan_intent_contract_rejects_inconsistent_state() -> None:
    invalid_updates = (
        {"assumptions": [""]},
        {"tables": ["Invoice", "Invoice"]},
        {"outputs": [_output_values(), _output_values()]},
        {"order_by": [{"target_alias": "missing", "direction": "ascending"}]},
        {"needs_clarification": True, "clarification_question": "Pilih metrik?"},
        {"base_table": None},
        {
            "intent": "clarification",
            "needs_clarification": False,
            "clarification_question": None,
            "base_table": None,
            "tables": [],
            "outputs": [],
        },
        {
            "intent": "clarification",
            "needs_clarification": True,
            "clarification_question": "Pilih metrik?",
        },
        {
            "intent": "unsupported",
            "needs_clarification": True,
            "clarification_question": "Mengapa?",
            "base_table": None,
            "tables": [],
            "outputs": [],
        },
        {"intent": "unsupported"},
    )
    for updates in invalid_updates:
        with pytest.raises(ValidationError):
            AnalysisPlan.model_validate({**_plan_values(), **updates})


def _compiler() -> tuple[AnalysisPlanGrounder, AnalysisPlanCompiler]:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    bundle = load_semantic_bundle(ROOT / "semantic")
    grounder = AnalysisPlanGrounder(snapshot, bundle)
    return grounder, AnalysisPlanCompiler(grounder.metrics, grounder.joins)


def test_compiler_covers_bounded_aggregate_and_filter_primitives() -> None:
    grounder, compiler = _compiler()
    plan = AnalysisPlan(
        intent=LLMIntent.ANALYSIS,
        language=LanguageCode.INDONESIAN,
        needs_clarification=False,
        base_table="Invoice",
        tables=("Invoice",),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                alias="distinct_customers",
                aggregate=PlanAggregate.COUNT_DISTINCT,
                column="Invoice.CustomerId",
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                alias="sum_total",
                aggregate=PlanAggregate.SUM,
                column="Invoice.Total",
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                alias="avg_total",
                aggregate=PlanAggregate.AVERAGE,
                column="Invoice.Total",
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                alias="min_total",
                aggregate=PlanAggregate.MINIMUM,
                column="Invoice.Total",
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                alias="max_total",
                aggregate=PlanAggregate.MAXIMUM,
                column="Invoice.Total",
            ),
        ),
        filters=(
            PlanFilter(
                target="Invoice.BillingCountry",
                operator=PlanFilterOperator.NOT_EQUALS,
                values=("X",),
            ),
            PlanFilter(
                target="Invoice.Total", operator=PlanFilterOperator.GREATER_THAN, values=(0,)
            ),
            PlanFilter(
                target="Invoice.Total", operator=PlanFilterOperator.LESS_OR_EQUAL, values=(100,)
            ),
            PlanFilter(
                target="Invoice.Total", operator=PlanFilterOperator.BETWEEN, values=(1, 100)
            ),
            PlanFilter(
                target="Invoice.BillingCountry",
                operator=PlanFilterOperator.IN,
                values=("Brazil", "USA"),
            ),
            PlanFilter(
                target="Invoice.BillingAddress",
                operator=PlanFilterOperator.CONTAINS,
                values=("Street",),
            ),
            PlanFilter(
                target="Invoice.BillingCity", operator=PlanFilterOperator.STARTS_WITH, values=("B",)
            ),
            PlanFilter(
                target="Invoice.BillingPostalCode",
                operator=PlanFilterOperator.ENDS_WITH,
                values=("0",),
            ),
            PlanFilter(target="Invoice.BillingState", operator=PlanFilterOperator.IS_NULL),
            PlanFilter(target="Invoice.BillingCountry", operator=PlanFilterOperator.IS_NOT_NULL),
        ),
        confidence=0.9,
        reasoning_summary="Semua primitif tetap dibatasi.",
    )
    sql = compiler.compile(grounder.ground(plan)).sql

    assert "COUNT(DISTINCT Invoice.CustomerId)" in sql
    assert "AVG(Invoice.Total)" in sql
    assert "Invoice.BillingCountry IN ('Brazil', 'USA')" in sql
    assert "Invoice.BillingAddress LIKE '%Street%'" in sql
    assert "Invoice.BillingState IS NULL" in sql

    product_plan = plan.model_copy(
        update={
            "base_table": "InvoiceLine",
            "tables": ("InvoiceLine",),
            "outputs": (
                PlanOutput(
                    kind=PlanOutputKind.AGGREGATE,
                    alias="sales",
                    aggregate=PlanAggregate.SUM_PRODUCT,
                    column="InvoiceLine.UnitPrice",
                    second_column="InvoiceLine.Quantity",
                ),
            ),
            "filters": (),
        }
    )
    assert (
        "SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity)"
        in compiler.compile(grounder.ground(product_plan)).sql
    )


@pytest.mark.parametrize(
    ("grain", "format_code"),
    (
        (PlanTimeGrain.YEAR, "%Y"),
        (PlanTimeGrain.MONTH_NUMBER, "%m"),
        (PlanTimeGrain.WEEKDAY_NUMBER, "%w"),
    ),
)
def test_time_bucket_variants(grain: PlanTimeGrain, format_code: str) -> None:
    grounder, compiler = _compiler()
    plan = AnalysisPlan(
        intent=LLMIntent.ANALYSIS,
        language=LanguageCode.INDONESIAN,
        needs_clarification=False,
        base_table="Invoice",
        tables=("Invoice",),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.TIME_BUCKET,
                alias="bucket",
                column="Invoice.InvoiceDate",
                time_grain=grain,
                group_by=True,
            ),
        ),
        confidence=0.9,
        reasoning_summary="Bucket waktu tervalidasi.",
    )
    assert (
        f"strftime('{format_code}', Invoice.InvoiceDate)"
        in compiler.compile(grounder.ground(plan)).sql
    )


def test_alignment_validator_rejects_independent_drift() -> None:
    grounder, compiler = _compiler()
    plan = AnalysisPlan.model_validate(_plan_values())
    grounded = grounder.ground(plan)
    compiled = compiler.compile(grounded)
    validator = PlanSQLAlignmentValidator()
    invalid = (
        CompiledAnalysisPlan(
            sql="DELETE FROM Invoice",
            tables=compiled.tables,
            columns=compiled.columns,
            output_aliases=compiled.output_aliases,
        ),
        replace(compiled, output_aliases=("wrong",)),
        replace(compiled, tables=("Customer",)),
        replace(compiled, sql=compiled.sql + " LIMIT 2"),
    )
    expected_codes = (
        "compiled_sql_not_select",
        "compiled_output_mismatch",
        "compiled_table_mismatch",
        "compiled_limit_mismatch",
    )
    for candidate, code in zip(invalid, expected_codes, strict=True):
        with pytest.raises(AnalysisPlanError, match=code):
            validator.validate(grounded, candidate, dialect="sqlite")
