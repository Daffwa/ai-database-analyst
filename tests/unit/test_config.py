"""Tests for centralized and lazy settings."""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from backend.core.config import AppSettings, clear_settings_cache, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_safe_defaults_require_no_provider_secret() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.llm_provider == "fake"
    assert settings.llm_model == "fake-deterministic"
    assert settings.llm_api_key is None
    assert settings.llm_max_output_characters == 20_000
    assert settings.has_llm_credentials is False
    assert settings.question_max_characters == 2_000
    assert settings.prompt_schema_max_tables == 8
    assert settings.prompt_schema_max_characters == 12_000
    assert settings.prompt_semantic_max_characters == 8_000
    assert settings.verified_query_max_examples == 3
    assert settings.sql_dialect == "sqlite"
    assert settings.sql_max_query_characters == 12_000
    assert settings.sql_allow_explain is False
    assert "load_extension" in settings.sql_blocked_functions
    assert settings.store_raw_question is False
    assert settings.store_raw_sql is False
    assert settings.store_result_rows is False
    assert settings.csv_max_bytes == 1_000_000
    assert settings.chart_max_categories == 50
    assert settings.chart_max_grouped_measures == 3
    assert settings.chart_recommended_line_points == 8
    assert settings.chart_recommended_scatter_points == 8
    assert settings.query_history_max_entries == 100


def test_settings_are_loaded_lazily_and_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("QUERY_MAX_ROWS", "125")

    first = get_settings()
    second = get_settings()

    assert first is second
    assert first.app_env == "test"
    assert first.query_max_rows == 125


def test_clear_settings_cache_reloads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERY_MAX_ROWS", "100")
    assert get_settings().query_max_rows == 100

    monkeypatch.setenv("QUERY_MAX_ROWS", "200")
    assert get_settings().query_max_rows == 100

    clear_settings_cache()
    assert get_settings().query_max_rows == 200


def test_secret_is_masked_and_detected() -> None:
    raw_secret = "test-only-provider-secret"
    settings = AppSettings(llm_api_key=raw_secret, _env_file=None)

    assert settings.has_llm_credentials is True
    assert raw_secret not in repr(settings)
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == raw_secret


def test_query_budget_validation_fails_closed() -> None:
    with pytest.raises(ValidationError):
        AppSettings(query_max_rows=0, _env_file=None)

    with pytest.raises(ValidationError):
        AppSettings(prompt_schema_max_tables=0, _env_file=None)

    with pytest.raises(ValidationError):
        AppSettings(sql_max_query_characters=99, _env_file=None)

    with pytest.raises(ValidationError):
        AppSettings(query_max_repair_attempts=6, _env_file=None)

    with pytest.raises(ValidationError):
        AppSettings(verified_query_max_examples=11, _env_file=None)

    with pytest.raises(ValidationError):
        AppSettings(csv_max_bytes=1_000, _env_file=None)

    with pytest.raises(ValidationError):
        AppSettings(chart_max_categories=1, _env_file=None)

    with pytest.raises(ValidationError):
        AppSettings(query_history_max_entries=0, _env_file=None)


def test_settings_are_immutable() -> None:
    settings = AppSettings(_env_file=None)

    with pytest.raises(ValidationError):
        settings.query_max_rows = 1_000  # type: ignore[misc]
