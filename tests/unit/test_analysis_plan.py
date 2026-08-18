from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.schemas.analysis_plan import (
    AnalysisPlan,
    PlanAggregate,
    PlanBenchmark,
    PlanBenchmarkKind,
    PlanFilter,
    PlanFilterOperator,
    PlanFilterScope,
    PlanOrder,
    PlanOutput,
    PlanOutputKind,
    PlanRelatedFilter,
    PlanSortDirection,
    PlanTimeGrain,
)
from backend.schemas.database import SchemaAllowlist
from backend.schemas.llm import LanguageCode, LLMIntent
from backend.services.analysis_plan import (
    AnalysisPlanCompiler,
    AnalysisPlanError,
    AnalysisPlanGrounder,
    PlanSQLAlignmentValidator,
)
from backend.services.planned_sql_generator import (
    GEMINI_ANALYSIS_PLAN_SCHEMA,
    PlannedPromptBuilder,
)
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_service import SemanticService
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService

ROOT = Path(__file__).resolve().parents[2]


def _services() -> tuple[AnalysisPlanGrounder, AnalysisPlanCompiler, SQLSecurityService]:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    bundle = load_semantic_bundle(ROOT / "semantic")
    grounder = AnalysisPlanGrounder(snapshot, bundle)
    compiler = AnalysisPlanCompiler(grounder.metrics, grounder.joins)
    security = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(dialect="sqlite", max_rows=500),
    )
    return grounder, compiler, security


def _plan(**updates: object) -> AnalysisPlan:
    values: dict[str, object] = {
        "intent": LLMIntent.ANALYSIS,
        "language": LanguageCode.INDONESIAN,
        "needs_clarification": False,
        "assumptions": (),
        "base_table": "Invoice",
        "tables": ("Invoice",),
        "join_ids": (),
        "outputs": (
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.InvoiceId",
                alias="InvoiceId",
            ),
        ),
        "filters": (),
        "related_filters": (),
        "order_by": (),
        "limit": None,
        "confidence": 0.9,
        "reasoning_summary": "Rencana analisis terstruktur.",
    }
    values.update(updates)
    return AnalysisPlan.model_validate(values)


def test_provider_schema_is_inlined_and_annotation_free() -> None:
    serialized = json.dumps(GEMINI_ANALYSIS_PLAN_SCHEMA, sort_keys=True)

    assert '"$defs"' not in serialized
    assert '"$ref"' not in serialized
    assert '"default"' not in serialized
    assert '"pattern"' not in serialized
    assert '"minLength"' not in serialized
    assert '"maxLength"' not in serialized
    assert '"anyOf"' not in serialized
    assert GEMINI_ANALYSIS_PLAN_SCHEMA["additionalProperties"] is False
    output_items = GEMINI_ANALYSIS_PLAN_SCHEMA["properties"]["outputs"]["items"]
    assert output_items == {"type": "object"}


def test_plan_prompt_uses_hybrid_reviewed_example_retrieval() -> None:
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    bundle = load_semantic_bundle(ROOT / "semantic")
    security = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(dialect="sqlite", max_rows=500),
    )
    validation = SemanticLayerValidator(
        snapshot,
        security,
        expected_semantic_version=bundle.semantic_version,
    ).validate(bundle)
    semantics = SemanticService(bundle, validation, max_verified_examples=3)
    question = "Buat peringkat artis berdasarkan jumlah lagu terbanyak."
    resolution = semantics.resolve(question)

    prompt = PlannedPromptBuilder(SchemaRetriever(), bundle).build(
        request_id="hybrid-retrieval-test",
        question=question,
        snapshot=snapshot,
        semantic_resolution=resolution,
    )

    assert "artist_with_most_tracks" in prompt.verified_query_ids
    assert set(prompt.verified_query_ids) <= {
        query.query_id for query in bundle.verified_queries.queries
    }


def test_grounder_derives_join_and_compiler_emits_only_validated_sources() -> None:
    grounder, compiler, security = _services()
    plan = _plan(
        tables=("invoice", "customer"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="invoice.invoiceid",
                alias="InvoiceId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="customer.customerid",
                alias="CustomerId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="customer.firstname",
                alias="FirstName",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="customer.lastname",
                alias="LastName",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="invoice.total",
                alias="Total",
            ),
        ),
        order_by=(PlanOrder(target_alias="InvoiceId", direction=PlanSortDirection.ASCENDING),),
        limit=5,
    )

    grounded = grounder.ground(plan)
    compiled = compiler.compile(grounded)
    PlanSQLAlignmentValidator().validate(grounded, compiled, dialect="sqlite")
    validation = security.validate(
        compiled.sql,
        declared_tables=compiled.tables,
        declared_columns=compiled.columns,
    )

    assert grounded.tables == ("Invoice", "Customer")
    assert grounded.join_ids == ("invoice_to_customer",)
    assert "JOIN Customer ON Invoice.CustomerId = Customer.CustomerId" in compiled.sql
    assert validation.safe is True


def test_metric_ranking_and_time_bucket_are_compiled_deterministically() -> None:
    grounder, compiler, security = _services()
    ranking = _plan(
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.BillingCountry",
                alias="BillingCountry",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.METRIC,
                metric_id="total_revenue",
                alias="revenue",
                round_digits=2,
            ),
        ),
        order_by=(
            PlanOrder(target_alias="revenue", direction=PlanSortDirection.DESCENDING),
            PlanOrder(target_alias="BillingCountry", direction=PlanSortDirection.ASCENDING),
        ),
        limit=3,
    )
    grounded_ranking = grounder.ground(ranking)
    compiled_ranking = compiler.compile(grounded_ranking)
    assert compiled_ranking.sql == (
        "SELECT Invoice.BillingCountry AS BillingCountry, "
        "ROUND(SUM(Invoice.Total), 2) AS revenue FROM Invoice "
        "GROUP BY Invoice.BillingCountry ORDER BY revenue DESC, BillingCountry ASC LIMIT 3"
    )
    assert security.validate(
        compiled_ranking.sql,
        declared_tables=compiled_ranking.tables,
        declared_columns=compiled_ranking.columns,
    ).safe

    time_plan = _plan(
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.TIME_BUCKET,
                column="Invoice.InvoiceDate",
                time_grain=PlanTimeGrain.MONTH,
                alias="month",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Invoice.InvoiceId",
                alias="invoice_count",
            ),
        ),
        filters=(
            PlanFilter(
                target="Invoice.InvoiceDate",
                operator=PlanFilterOperator.GREATER_OR_EQUAL,
                values=("2012-01-01",),
            ),
            PlanFilter(
                target="Invoice.InvoiceDate",
                operator=PlanFilterOperator.LESS_THAN,
                values=("2013-01-01",),
            ),
        ),
        order_by=(PlanOrder(target_alias="month", direction=PlanSortDirection.ASCENDING),),
    )
    grounded_time = grounder.ground(time_plan)
    assert compiler.compile(grounded_time).sql == (
        "SELECT strftime('%Y-%m', Invoice.InvoiceDate) AS month, "
        "COUNT(Invoice.InvoiceId) AS invoice_count FROM Invoice "
        "WHERE Invoice.InvoiceDate >= '2012-01-01' AND "
        "Invoice.InvoiceDate < '2013-01-01' "
        "GROUP BY strftime('%Y-%m', Invoice.InvoiceDate) ORDER BY month ASC"
    )


def test_global_and_group_average_benchmarks_compile_without_free_sql() -> None:
    grounder, compiler, _ = _services()
    global_average = _plan(
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.InvoiceId",
                alias="InvoiceId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.Total",
                alias="Total",
            ),
        ),
        filters=(
            PlanFilter(
                target="Invoice.Total",
                operator=PlanFilterOperator.GREATER_THAN,
                benchmark=PlanBenchmark(
                    kind=PlanBenchmarkKind.GLOBAL_AVERAGE,
                    table="Invoice",
                    column="Invoice.Total",
                ),
            ),
        ),
        order_by=(PlanOrder(target_alias="Total", direction=PlanSortDirection.DESCENDING),),
        limit=5,
    )
    sql = compiler.compile(grounder.ground(global_average)).sql
    assert "Invoice.Total > (SELECT AVG(Invoice.Total) FROM Invoice)" in sql

    grouped_average = _plan(
        base_table="Album",
        tables=("Album", "Track"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Album.AlbumId",
                alias="AlbumId",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Track.TrackId",
                alias="track_count",
            ),
        ),
        filters=(
            PlanFilter(
                scope=PlanFilterScope.HAVING,
                target="track_count",
                operator=PlanFilterOperator.GREATER_THAN,
                benchmark=PlanBenchmark(
                    kind=PlanBenchmarkKind.GROUP_AVERAGE,
                    table="Track",
                    column="Track.TrackId",
                    aggregate=PlanAggregate.COUNT,
                    group_by="Track.AlbumId",
                ),
            ),
        ),
        order_by=(PlanOrder(target_alias="track_count", direction=PlanSortDirection.DESCENDING),),
        limit=5,
    )
    sql = compiler.compile(grounder.ground(grouped_average)).sql
    assert "HAVING COUNT(Track.TrackId) > (SELECT AVG(group_value)" in sql


def test_related_filter_uses_only_approved_join_path() -> None:
    grounder, compiler, security = _services()
    plan = _plan(
        base_table="Artist",
        tables=("Artist",),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Artist.ArtistId",
                alias="ArtistId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Artist.Name",
                alias="Name",
            ),
        ),
        related_filters=(
            PlanRelatedFilter(
                outer_column="Artist.ArtistId",
                subquery_select_column="Album.ArtistId",
                base_table="Album",
                tables=("Album", "Track"),
                filters=(
                    PlanFilter(
                        target="Track.UnitPrice",
                        operator=PlanFilterOperator.GREATER_THAN,
                        values=(1.5,),
                    ),
                ),
            ),
        ),
        order_by=(PlanOrder(target_alias="ArtistId", direction=PlanSortDirection.ASCENDING),),
        limit=5,
    )
    grounded = grounder.ground(plan)
    compiled = compiler.compile(grounded)

    assert "Album.ArtistId IN" not in compiled.sql
    assert "Artist.ArtistId IN (SELECT Album.ArtistId FROM Album JOIN Track" in compiled.sql
    assert security.validate(
        compiled.sql,
        declared_tables=compiled.tables,
        declared_columns=compiled.columns,
    ).safe


def test_unknown_column_fails_closed_before_compilation() -> None:
    grounder, _, _ = _services()
    plan = _plan(
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.SecretValue",
                alias="SecretValue",
            ),
        )
    )

    with pytest.raises(AnalysisPlanError, match="unknown_column"):
        grounder.ground(plan)


def test_filtered_foreign_id_detail_requires_identifier_display_and_filter_column() -> None:
    grounder, compiler, _ = _services()
    incomplete = _plan(
        base_table="Track",
        tables=("Track",),
        outputs=(
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.TrackId", alias="TrackId"),
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.Name", alias="Name"),
        ),
        filters=(
            PlanFilter(
                target="Track.GenreId",
                operator=PlanFilterOperator.EQUALS,
                values=(1,),
            ),
        ),
        limit=5,
    )

    with pytest.raises(AnalysisPlanError, match="missing_filter_identifier_projection"):
        grounder.ground(incomplete)

    missing_primary = incomplete.model_copy(
        update={
            "outputs": (
                incomplete.outputs[1],
                PlanOutput(
                    kind=PlanOutputKind.COLUMN,
                    column="Track.GenreId",
                    alias="GenreId",
                ),
            )
        }
    )
    with pytest.raises(AnalysisPlanError, match="missing_primary_identifier_projection"):
        grounder.ground(missing_primary)

    missing_display = incomplete.model_copy(
        update={
            "outputs": (
                incomplete.outputs[0],
                PlanOutput(
                    kind=PlanOutputKind.COLUMN,
                    column="Track.GenreId",
                    alias="GenreId",
                ),
            )
        }
    )
    with pytest.raises(AnalysisPlanError, match="missing_display_projection"):
        grounder.ground(missing_display)

    complete = incomplete.model_copy(
        update={
            "outputs": (
                *incomplete.outputs,
                PlanOutput(
                    kind=PlanOutputKind.COLUMN,
                    column="Track.GenreId",
                    alias="GenreId",
                ),
            )
        }
    )
    grounded = grounder.ground(complete)
    assert compiler.compile(grounded).output_aliases == ("TrackId", "Name", "GenreId")
    id_filtered = grounder.ground(
        complete,
        question="Tampilkan lima track bergenre ID 1.",
    )
    assert compiler.compile(id_filtered).output_aliases == ("TrackId", "Name", "GenreId")


def test_bounded_detail_policy_uses_schema_roles_and_explicit_question_attributes() -> None:
    grounder, _, _ = _services()
    invoice = _plan(
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.InvoiceId",
                alias="InvoiceId",
            ),
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Invoice.Total", alias="Total"),
        ),
        limit=5,
    )
    completed_invoice = grounder.ground(invoice, question="Tampilkan lima invoice bernilai tinggi.")
    assert tuple(output.alias for output in completed_invoice.outputs) == (
        "InvoiceId",
        "CustomerId",
        "Total",
    )

    explicit_invoice = invoice.model_copy(
        update={
            "outputs": (
                invoice.outputs[0],
                PlanOutput(
                    kind=PlanOutputKind.COLUMN,
                    column="Invoice.CustomerId",
                    alias="CustomerId",
                ),
                invoice.outputs[1],
            )
        }
    )
    assert (
        grounder.ground(
            explicit_invoice, question="Tampilkan lima invoice bernilai tinggi."
        ).outputs
        == explicit_invoice.outputs
    )

    filtered_invoice = explicit_invoice.model_copy(
        update={
            "outputs": (
                *explicit_invoice.outputs,
                PlanOutput(
                    kind=PlanOutputKind.COLUMN,
                    column="Invoice.BillingCountry",
                    alias="BillingCountry",
                ),
            ),
            "filters": (
                PlanFilter(
                    target="Invoice.BillingCountry",
                    operator=PlanFilterOperator.EQUALS,
                    values=("Germany",),
                ),
            ),
        }
    )
    pruned = grounder.ground(
        filtered_invoice,
        question="Tampilkan lima invoice yang ditagihkan ke Jerman.",
    )
    assert tuple(output.alias for output in pruned.outputs) == (
        "InvoiceId",
        "CustomerId",
        "Total",
    )

    track = _plan(
        base_table="Track",
        tables=("Track",),
        outputs=(
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.TrackId", alias="TrackId"),
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.Name", alias="Name"),
        ),
        limit=5,
    )
    related = grounder.ground(track, question="Tampilkan lima track beserta nama genre.")
    assert tuple(output.alias for output in related.outputs) == (
        "TrackId",
        "Name",
        "genre_name",
    )
    with pytest.raises(AnalysisPlanError, match="missing_named_attribute_projection"):
        grounder.ground(track, question="List five longest tracks in milliseconds.")


def test_bounded_aggregate_entity_ranking_completes_grouped_identity_and_display() -> None:
    grounder, compiler, _ = _services()
    ranking = _plan(
        base_table="Genre",
        tables=("Genre", "Track"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Genre.Name",
                alias="Name",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Track.TrackId",
                alias="track_count",
            ),
        ),
        order_by=(PlanOrder(target_alias="track_count", direction=PlanSortDirection.DESCENDING),),
        limit=5,
    )

    grounded = grounder.ground(
        ranking,
        question="Tampilkan lima genre dengan jumlah track terbanyak.",
    )
    assert compiler.compile(grounded).output_aliases == ("GenreId", "Name", "track_count")
    assert all(output.group_by for output in grounded.outputs[:2])


def test_unbounded_entity_aggregation_completes_identity_and_orders_by_dimensions() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Genre",
        tables=("Genre", "Track", "InvoiceLine"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Genre.Name",
                alias="Name",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.SUM,
                column="InvoiceLine.Quantity",
                alias="units_sold",
            ),
        ),
    )

    grounded = grounder.ground(plan, question="Sum units sold by genre.")

    assert compiler.compile(grounded).output_aliases == ("GenreId", "Name", "units_sold")
    assert tuple(order.target_alias for order in grounded.order_by) == ("GenreId", "Name")


def test_count_grouping_defaults_to_dimension_order_instead_of_measure_order() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Track",
        tables=("Track",),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Track.GenreId",
                alias="GenreId",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Track.TrackId",
                alias="track_count",
            ),
        ),
    )

    sql = compiler.compile(
        grounder.ground(
            plan,
            question="Count tracks for each genre ID.",
            selected_metric_ids=("track_count",),
        )
    ).sql

    assert sql.endswith("ORDER BY GenreId ASC")


def test_universal_identifier_grouping_removes_invented_limit_and_display_projection() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Album",
        tables=("Album", "Artist"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Album.ArtistId",
                alias="ArtistId",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Artist.Name",
                alias="Name",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Album.AlbumId",
                alias="album_count",
            ),
        ),
        limit=20,
    )

    grounded = grounder.ground(plan, question="Hitung album untuk setiap artist ID.")
    compiled = compiler.compile(grounded)

    assert grounded.limit is None
    assert compiled.output_aliases == ("ArtistId", "album_count")
    assert "Artist.Name" not in compiled.sql
    assert "LIMIT" not in compiled.sql


def test_grouping_keeps_display_when_user_explicitly_requests_it() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Artist",
        tables=("Album", "Artist"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Artist.ArtistId",
                alias="ArtistId",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Album.AlbumId",
                alias="album_count",
            ),
        ),
    )

    grounded = grounder.ground(
        plan,
        question="Hitung album untuk setiap artist ID dan nama artist.",
    )

    assert compiler.compile(grounded).output_aliases == ("ArtistId", "Name", "album_count")


@pytest.mark.parametrize(
    "question",
    (
        "Hitung album untuk tiap artist ID.",
        "Hitung album untuk masing-masing artist ID.",
        "Hitung album untuk semua artist ID, urutkan berdasarkan ID.",
    ),
)
def test_universal_grouping_synonyms_do_not_accept_an_invented_limit(question: str) -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Album",
        tables=("Album", "Artist"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Album.ArtistId",
                alias="ArtistId",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Artist.Name",
                alias="Name",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Album.AlbumId",
                alias="album_count",
            ),
        ),
        limit=20,
    )

    grounded = grounder.ground(plan, question=question)

    assert grounded.limit is None
    assert compiler.compile(grounded).output_aliases == ("ArtistId", "album_count")


def test_universal_grouping_keeps_an_explicit_requested_quantity() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Album",
        tables=("Album", "Artist"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Album.ArtistId",
                alias="ArtistId",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Artist.Name",
                alias="Name",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Album.AlbumId",
                alias="album_count",
            ),
        ),
        limit=20,
    )

    grounded = grounder.ground(plan, question="Tampilkan 20 artist dan jumlah albumnya.")

    assert grounded.limit == 20
    assert compiler.compile(grounded).output_aliases == ("ArtistId", "Name", "album_count")


def test_detail_projection_uses_requested_relationship_and_numeric_fact_roles() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="InvoiceLine",
        tables=("InvoiceLine", "Invoice"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="InvoiceLine.InvoiceLineId",
                alias="InvoiceLineId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.Total",
                alias="Total",
            ),
        ),
        limit=5,
    )

    grounded = grounder.ground(
        plan,
        question="Show five invoice lines with their invoice totals.",
    )

    assert compiler.compile(grounded).output_aliases == (
        "InvoiceLineId",
        "InvoiceId",
        "UnitPrice",
        "Quantity",
        "Total",
    )


def test_filter_focus_controls_projection_limit_and_stable_multi_value_order() -> None:
    grounder, compiler, _ = _services()
    missing_bytes = _plan(
        base_table="Track",
        tables=("Track",),
        outputs=(
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.TrackId", alias="TrackId"),
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.Name", alias="Name"),
        ),
        filters=(
            PlanFilter(
                target="Track.Bytes",
                operator=PlanFilterOperator.IS_NULL,
            ),
        ),
    )
    grounded_missing = grounder.ground(
        missing_bytes,
        question="Show tracks with a missing byte size.",
    )
    assert compiler.compile(grounded_missing).output_aliases == ("TrackId", "Name", "Bytes")
    assert grounded_missing.limit == 5

    countries = _plan(
        base_table="Customer",
        tables=("Customer",),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Customer.CustomerId",
                alias="CustomerId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Customer.Country",
                alias="Country",
            ),
        ),
        filters=(
            PlanFilter(
                target="Customer.Country",
                operator=PlanFilterOperator.IN,
                values=("Canada", "France"),
            ),
        ),
    )
    grounded_countries = grounder.ground(
        countries,
        question="Tampilkan pelanggan dari Kanada atau Prancis.",
    )
    assert compiler.compile(grounded_countries).output_aliases == (
        "CustomerId",
        "FirstName",
        "LastName",
        "Country",
    )
    assert grounded_countries.limit == 10
    assert tuple(order.target_alias for order in grounded_countries.order_by) == (
        "Country",
        "CustomerId",
    )


def test_ordered_detail_without_an_explicit_count_uses_a_five_row_sample() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.Total",
                alias="Total",
            ),
        ),
        filters=(
            PlanFilter(
                target="Invoice.Total",
                operator=PlanFilterOperator.GREATER_OR_EQUAL,
                values=(10,),
            ),
        ),
        order_by=(PlanOrder(target_alias="Total", direction=PlanSortDirection.DESCENDING),),
    )

    grounded = grounder.ground(
        plan,
        question="List invoices with totals of at least 10, highest total first.",
    )

    assert grounded.limit == 5
    assert compiler.compile(grounded).output_aliases == ("InvoiceId", "CustomerId", "Total")


def test_named_relationship_role_completes_related_display_pair() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Customer",
        tables=("Customer", "Employee"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Customer.CustomerId",
                alias="CustomerId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Employee.FirstName",
                alias="rep_first_name",
            ),
        ),
        limit=5,
    )

    grounded = grounder.ground(
        plan,
        question="Tampilkan lima pelanggan beserta nama support rep.",
    )

    assert compiler.compile(grounded).output_aliases == (
        "CustomerId",
        "FirstName",
        "LastName",
        "rep_first_name",
        "rep_last_name",
    )


def test_bounded_grouped_foreign_key_is_lifted_to_requested_entity_grain() -> None:
    grounder, compiler, _ = _services()
    plan = _plan(
        base_table="Invoice",
        tables=("Invoice",),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.CustomerId",
                alias="CustomerId",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Invoice.InvoiceId",
                alias="invoice_count",
            ),
        ),
        limit=5,
    )

    grounded = grounder.ground(
        plan,
        question="Count invoices for five customers by customer ID.",
        selected_metric_ids=("invoice_count",),
    )

    assert grounded.base_table == "Customer"
    assert compiler.compile(grounded).output_aliases == (
        "CustomerId",
        "FirstName",
        "LastName",
        "invoice_count",
    )


def test_display_ranking_without_requested_quantity_does_not_invent_top_one() -> None:
    grounder, _, _ = _services()
    plan = _plan(
        base_table="MediaType",
        tables=("MediaType", "Track"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="MediaType.Name",
                alias="Name",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Track.TrackId",
                alias="track_count",
            ),
        ),
        order_by=(PlanOrder(target_alias="track_count", direction=PlanSortDirection.DESCENDING),),
        limit=1,
    )

    grounded = grounder.ground(
        plan,
        question="Tampilkan tipe media dengan jumlah track terbanyak.",
        selected_metric_ids=("track_count",),
    )

    assert grounded.limit is None
    assert tuple(output.alias for output in grounded.outputs) == (
        "MediaTypeId",
        "Name",
        "track_count",
    )


def test_question_grain_and_default_detail_order_are_grounded_deterministically() -> None:
    grounder, compiler, _ = _services()
    model_plan = _plan(
        base_table="Genre",
        tables=("Genre", "Track"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Track.Name",
                alias="track_name",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Genre.Name",
                alias="genre_name",
            ),
        ),
        order_by=(
            PlanOrder(
                target_alias="genre_name",
                direction=PlanSortDirection.DESCENDING,
            ),
        ),
        limit=5,
    )

    grounded = grounder.ground(
        model_plan,
        question="Tampilkan lima track beserta nama genrenya.",
    )
    compiled = compiler.compile(grounded)

    assert grounded.base_table == "Track"
    assert compiled.output_aliases == ("TrackId", "track_name", "genre_name")
    assert tuple(order.target_alias for order in grounded.order_by) == ("TrackId",)
    assert "FROM Track JOIN Genre" in compiled.sql
    assert compiled.sql.endswith("ORDER BY TrackId ASC LIMIT 5")


def test_longest_detail_ranking_keeps_value_order_with_primary_key_tiebreaker() -> None:
    grounder, compiler, _ = _services()
    model_plan = _plan(
        language=LanguageCode.ENGLISH,
        base_table="Track",
        tables=("Track",),
        outputs=(
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.TrackId", alias="TrackId"),
            PlanOutput(kind=PlanOutputKind.COLUMN, column="Track.Name", alias="Name"),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Track.Milliseconds",
                alias="Milliseconds",
            ),
        ),
        order_by=(
            PlanOrder(
                target_alias="Milliseconds",
                direction=PlanSortDirection.DESCENDING,
            ),
        ),
        limit=5,
    )

    grounded = grounder.ground(
        model_plan,
        question="List the five longest tracks in milliseconds.",
    )
    compiled = compiler.compile(grounded)

    assert tuple((order.target_alias, order.direction) for order in grounded.order_by) == (
        ("Milliseconds", PlanSortDirection.DESCENDING),
        ("TrackId", PlanSortDirection.ASCENDING),
    )
    assert compiled.sql.endswith("ORDER BY Milliseconds DESC, TrackId ASC LIMIT 5")


def test_bounded_global_benchmark_orders_by_compared_value_then_primary_key() -> None:
    grounder, compiler, _ = _services()
    model_plan = _plan(
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.InvoiceId",
                alias="InvoiceId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.CustomerId",
                alias="CustomerId",
            ),
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.Total",
                alias="Total",
            ),
        ),
        filters=(
            PlanFilter(
                target="Invoice.Total",
                operator=PlanFilterOperator.GREATER_THAN,
                benchmark=PlanBenchmark(
                    kind=PlanBenchmarkKind.GLOBAL_AVERAGE,
                    table="Invoice",
                    column="Invoice.Total",
                ),
            ),
        ),
        order_by=(
            PlanOrder(
                target_alias="InvoiceId",
                direction=PlanSortDirection.ASCENDING,
            ),
        ),
        limit=5,
    )

    grounded = grounder.ground(
        model_plan,
        question="Tampilkan lima invoice yang nilainya di atas rata-rata seluruh invoice.",
    )
    compiled = compiler.compile(grounded)

    assert tuple((order.target_alias, order.direction) for order in grounded.order_by) == (
        ("Total", PlanSortDirection.DESCENDING),
        ("InvoiceId", PlanSortDirection.ASCENDING),
    )
    assert compiled.sql.endswith("ORDER BY Total DESC, InvoiceId ASC LIMIT 5")


def test_one_reviewed_metric_overrides_a_competing_model_aggregation() -> None:
    grounder, compiler, _ = _services()
    model_plan = _plan(
        base_table="Invoice",
        tables=("Invoice", "InvoiceLine"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Invoice.BillingCountry",
                alias="BillingCountry",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.SUM,
                column="Invoice.Total",
                alias="line_sales",
            ),
        ),
    )

    grounded = grounder.ground(
        model_plan,
        question="Hitung nilai penjualan baris invoice per negara penagihan.",
        selected_metric_ids=("product_sales_value",),
    )
    compiled = compiler.compile(grounded)

    assert grounded.outputs[1].kind is PlanOutputKind.METRIC
    assert grounded.outputs[1].metric_id == "product_sales_value"
    assert tuple(order.target_alias for order in grounded.order_by) == (
        "line_sales",
        "BillingCountry",
    )
    assert "ROUND(SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity), 2)" in compiled.sql
    assert compiled.sql.endswith("ORDER BY line_sales DESC, BillingCountry ASC")


def test_group_benchmark_uses_requested_entity_grain_and_stable_ranking() -> None:
    grounder, compiler, _ = _services()
    model_plan = _plan(
        base_table="Track",
        tables=("Track", "Album"),
        outputs=(
            PlanOutput(
                kind=PlanOutputKind.COLUMN,
                column="Album.Title",
                alias="Title",
                group_by=True,
            ),
            PlanOutput(
                kind=PlanOutputKind.AGGREGATE,
                aggregate=PlanAggregate.COUNT,
                column="Track.TrackId",
                alias="track_count",
            ),
        ),
        filters=(
            PlanFilter(
                scope=PlanFilterScope.HAVING,
                target="track_count",
                operator=PlanFilterOperator.GREATER_THAN,
                benchmark=PlanBenchmark(
                    kind=PlanBenchmarkKind.GROUP_AVERAGE,
                    table="Track",
                    column="Track.TrackId",
                    aggregate=PlanAggregate.COUNT,
                    group_by="Track.AlbumId",
                ),
            ),
        ),
        limit=5,
    )

    grounded = grounder.ground(
        model_plan,
        question="Show five albums whose track count is above the average album track count.",
        selected_metric_ids=("track_count",),
    )
    compiled = compiler.compile(grounded)

    assert grounded.base_table == "Album"
    assert compiled.output_aliases == ("AlbumId", "Title", "track_count")
    assert tuple(order.target_alias for order in grounded.order_by) == (
        "track_count",
        "AlbumId",
        "Title",
    )
    assert "HAVING COUNT(Track.TrackId) > (SELECT AVG(group_value)" in compiled.sql
    assert compiled.sql.endswith("ORDER BY track_count DESC, AlbumId ASC, Title ASC LIMIT 5")
