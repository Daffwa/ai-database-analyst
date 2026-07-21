"""Metadata schema stores audit identities but no raw sensitive payload columns."""

from backend.metadata.models import Base


def test_metadata_schema_contains_all_required_models_and_privacy_defaults() -> None:
    expected = {
        "data_sources",
        "schema_snapshots",
        "verified_queries",
        "query_requests",
        "query_attempts",
        "query_feedback",
        "evaluation_cases",
        "evaluation_runs",
        "evaluation_results",
        "usage_events",
    }
    assert {table.name for table in Base.metadata.sorted_tables} == expected
    all_columns = {
        column.name.casefold() for table in Base.metadata.sorted_tables for column in table.columns
    }
    assert "raw_question" not in all_columns
    assert "raw_sql" not in all_columns
    assert "result_rows" not in all_columns
    assert "sql_fingerprint" in all_columns
