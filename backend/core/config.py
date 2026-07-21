"""Centralized, lazy, and testable application settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppSettings(BaseSettings):
    """Validated runtime settings with safe local defaults.

    No provider credential is required when the fake LLM adapter is selected.
    Loading is intentionally lazy through :func:`get_settings`, so importing a
    module cannot fail merely because an optional secret is absent.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    app_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    frontend_port: int = Field(default=8501, ge=1, le=65535)
    api_base_url: str = "http://localhost:8000"
    api_timeout_seconds: int = Field(default=15, ge=1, le=120)
    evaluation_api_token: SecretStr | None = None

    llm_provider: str = "fake"
    llm_model: str = "fake-deterministic"
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: int = Field(default=30, ge=1, le=300)
    llm_max_output_characters: int = Field(default=20_000, ge=1_000, le=100_000)

    question_max_characters: int = Field(default=2_000, ge=100, le=20_000)
    prompt_schema_max_tables: int = Field(default=8, ge=1, le=100)
    prompt_schema_max_characters: int = Field(default=12_000, ge=1_000, le=100_000)
    prompt_semantic_max_characters: int = Field(default=8_000, ge=1_000, le=50_000)
    verified_query_max_examples: int = Field(default=3, ge=0, le=10)

    analytics_database_url: str | None = None
    metadata_database_url: str | None = None
    analytics_schema: str = Field(default="analytics", pattern=r"^[a-z][a-z0-9_]{0,62}$")
    metadata_schema: str = Field(default="app_metadata", pattern=r"^[a-z][a-z0-9_]{0,62}$")

    query_timeout_seconds: int = Field(default=5, ge=1, le=60)
    query_max_rows: int = Field(default=500, ge=1, le=5_000)
    query_max_columns: int = Field(default=100, ge=1, le=500)
    query_max_response_bytes: int = Field(default=5_000_000, ge=1_024, le=50_000_000)
    query_max_repair_attempts: int = Field(default=2, ge=0, le=5)
    csv_max_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)

    chart_max_categories: int = Field(default=50, ge=2, le=500)
    chart_max_grouped_measures: int = Field(default=3, ge=1, le=5)
    chart_recommended_line_points: int = Field(default=8, ge=2, le=100)
    chart_recommended_scatter_points: int = Field(default=8, ge=2, le=100)
    query_history_max_entries: int = Field(default=100, ge=1, le=1_000)

    sql_dialect: str = "sqlite"
    sql_max_query_characters: int = Field(default=12_000, ge=100, le=100_000)
    sql_allow_explain: bool = False
    sql_blocked_functions: tuple[str, ...] = (
        "pg_sleep",
        "dblink",
        "load_extension",
        "readfile",
        "writefile",
    )

    prompt_version: str = "v1"
    semantic_version: str = "v1"

    enable_query_history: bool = True
    enable_result_summary: bool = True
    store_raw_question: bool = False
    store_raw_sql: bool = False
    store_result_rows: bool = False

    cors_allowed_origins: list[str] = ["http://localhost:8501"]

    @model_validator(mode="after")
    def validate_network_boundaries(self) -> "AppSettings":
        """Reject unsafe browser access and accidentally shared DB credentials."""

        if self.app_env == "production" and "*" in self.cors_allowed_origins:
            raise ValueError("production CORS origins must not contain a wildcard")
        if (
            self.analytics_database_url
            and self.metadata_database_url
            and self.analytics_database_url == self.metadata_database_url
        ):
            raise ValueError("analytics and metadata database URLs must be distinct")
        return self

    @property
    def has_llm_credentials(self) -> bool:
        """Return whether a non-empty provider credential was configured."""

        return bool(self.llm_api_key and self.llm_api_key.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Load and cache settings on first use rather than at import time."""

    return AppSettings()


def clear_settings_cache() -> None:
    """Clear the settings cache for tests or an explicit configuration reload."""

    get_settings.cache_clear()
