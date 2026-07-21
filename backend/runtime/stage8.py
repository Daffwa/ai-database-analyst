"""PostgreSQL, metadata, and API composition root for Tahap 8."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from backend.core.config import AppSettings
from backend.core.errors import ConfigurationError
from backend.core.logging import ensure_logging_configured
from backend.db.postgres import assert_application_identity, create_postgresql_engine
from backend.evaluation.case_loader import load_evaluation_dataset
from backend.evaluation.mini_cases import fake_responses as mini_fake_responses
from backend.llm.factory import create_llm_adapter
from backend.metadata.repository import MetadataRepository
from backend.schemas.database import SchemaAllowlist
from backend.schemas.evaluation import EvaluationCategory
from backend.schemas.llm import LLMIntent, StructuredSQLProposal
from backend.schemas.result import DatabaseExplorerSnapshot, SafeSystemInfo
from backend.schemas.semantic import SemanticValidationReport
from backend.services.chart_selector import ChartPolicy, DeterministicChartSelector
from backend.services.experience_metadata import DatabaseExplorerService, build_safe_system_info
from backend.services.orchestrator import QueryOrchestrator, QueryProcessor
from backend.services.output_parser import StructuredOutputParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.query_executor import PostgreSQLReadOnlyQueryExecutor
from backend.services.query_history import QueryHistoryService
from backend.services.result_experience import ResultExperienceOrchestrator
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot
from backend.services.secure_orchestrator import (
    POSTGRESQL_SECURITY_WARNING,
    SecureQueryOrchestrator,
)
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_service import SemanticService
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_generator import SQLGenerator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService


@dataclass(frozen=True, slots=True)
class Stage8Runtime:
    """Owned PostgreSQL resources and application services for the API."""

    analytics_engine: Engine
    metadata_engine: Engine
    orchestrator: QueryProcessor
    metadata: MetadataRepository
    database_explorer: DatabaseExplorerSnapshot
    system_info: SafeSystemInfo
    semantic_validation: SemanticValidationReport

    def health(self) -> bool:
        """Check both dependencies without returning their addresses or credentials."""

        try:
            with self.analytics_engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        except Exception:
            return False
        return self.metadata.ping()

    def close(self) -> None:
        self.analytics_engine.dispose()
        self.metadata_engine.dispose()


def create_stage8_runtime(
    root: Path,
    settings: AppSettings,
    *,
    fake_responses: Mapping[str, str] | None = None,
) -> Stage8Runtime:
    """Build the final separated application runtime and verify DB identities."""

    ensure_logging_configured(settings.app_log_level)
    if not settings.analytics_database_url or not settings.metadata_database_url:
        raise ConfigurationError("Tahap 8 requires analytics and metadata database URLs.")
    if settings.prompt_version != "v2" or settings.sql_dialect != "postgres":
        raise ConfigurationError("Tahap 8 requires prompt v2 and the postgres SQL dialect.")

    analytics_engine = create_postgresql_engine(
        settings.analytics_database_url,
        expected_username="analytics_readonly",
        connect_timeout_seconds=settings.query_timeout_seconds,
    )
    metadata_engine = create_postgresql_engine(
        settings.metadata_database_url,
        expected_username="app_metadata_user",
        connect_timeout_seconds=settings.query_timeout_seconds,
    )
    try:
        analytics_identity = assert_application_identity(
            analytics_engine, expected_username="analytics_readonly"
        )
        metadata_identity = assert_application_identity(
            metadata_engine, expected_username="app_metadata_user"
        )
        if analytics_identity.current_database == metadata_identity.current_database:
            raise ConfigurationError("Analytics and metadata must use separate databases.")

        snapshot_path = root / "data" / "schemas" / "chinook-postgresql-v1.4.5.json"
        snapshot = load_schema_snapshot(snapshot_path)
        allowlist = SchemaAllowlist.from_snapshot(snapshot)
        sql_security = SQLSecurityService(
            allowlist,
            policy=SQLSecurityPolicy(
                dialect="postgres",
                max_rows=settings.query_max_rows,
                max_query_characters=settings.sql_max_query_characters,
                allowed_schemas=frozenset({settings.analytics_schema}),
                blocked_functions=frozenset(settings.sql_blocked_functions),
            ),
        )
        semantic_bundle = load_semantic_bundle(
            root / "semantic",
            dialect_overlay=root / "semantic" / "postgresql.yaml",
        )
        semantic_validation = SemanticLayerValidator(
            snapshot,
            sql_security,
            expected_semantic_version=semantic_bundle.semantic_version,
        ).validate(semantic_bundle)
        semantic_service = SemanticService(
            semantic_bundle,
            semantic_validation,
            max_verified_examples=settings.verified_query_max_examples,
            max_context_characters=settings.prompt_semantic_max_characters,
        )

        adapter = create_llm_adapter(
            settings,
            fake_responses=(
                postgres_fake_responses(root) if fake_responses is None else fake_responses
            ),
        )
        generator = SQLGenerator(
            adapter,
            PromptBuilder(
                SchemaRetriever(
                    max_tables=settings.prompt_schema_max_tables,
                    max_characters=settings.prompt_schema_max_characters,
                ),
                prompt_version=settings.prompt_version,
            ),
            StructuredOutputParser(max_characters=settings.llm_max_output_characters),
            timeout_seconds=settings.llm_timeout_seconds,
        )
        generation = QueryOrchestrator(
            generator,
            snapshot,
            max_question_characters=settings.question_max_characters,
            semantic_service=semantic_service,
        )
        executor = PostgreSQLReadOnlyQueryExecutor(
            analytics_engine,
            schema=settings.analytics_schema,
            max_rows=settings.query_max_rows,
            max_columns=settings.query_max_columns,
            max_response_bytes=settings.query_max_response_bytes,
            max_query_characters=settings.sql_max_query_characters,
            timeout_seconds=settings.query_timeout_seconds,
        )
        secure = SecureQueryOrchestrator(
            generation,
            sql_security,
            executor,
            success_warning=POSTGRESQL_SECURITY_WARNING,
        )
        history = QueryHistoryService(
            max_entries=settings.query_history_max_entries,
            enabled=False,
        )
        formatter = ResultFormatter(
            {
                metric.metric_id.casefold(): metric.format
                for metric in semantic_bundle.metrics.metrics
            }
        )
        orchestrator = ResultExperienceOrchestrator(
            secure,
            formatter,
            DeterministicChartSelector(
                ChartPolicy(
                    max_bar_categories=settings.chart_max_categories,
                    max_grouped_measures=settings.chart_max_grouped_measures,
                    recommended_line_points=settings.chart_recommended_line_points,
                    recommended_scatter_points=settings.chart_recommended_scatter_points,
                )
            ),
            ResultSummarizer(),
            history,
            enable_summary=settings.enable_result_summary,
        )
        metadata = MetadataRepository(metadata_engine)
        metadata.synchronize_catalog(
            snapshot,
            semantic_bundle,
            snapshot_location="data/schemas/chinook-postgresql-v1.4.5.json",
        )
        refreshed_at = datetime.fromtimestamp(snapshot_path.stat().st_mtime, UTC).isoformat()
        return Stage8Runtime(
            analytics_engine=analytics_engine,
            metadata_engine=metadata_engine,
            orchestrator=orchestrator,
            metadata=metadata,
            database_explorer=DatabaseExplorerService(
                snapshot, refreshed_at=refreshed_at
            ).snapshot(),
            system_info=build_safe_system_info(settings, snapshot, semantic_validation),
            semantic_validation=semantic_validation,
        )
    except Exception:
        analytics_engine.dispose()
        metadata_engine.dispose()
        raise


def postgres_fake_responses(root: Path | None = None) -> dict[str, str]:
    """Return safe demos plus adversarial cases for the final fake runtime."""

    project_root = root or Path(__file__).resolve().parents[2]
    responses: dict[str, str] = {}
    replacements = {
        "strftime('%Y-%m', InvoiceDate)": "SUBSTR(CAST(InvoiceDate AS TEXT), 1, 7)",
        "strftime('%Y', InvoiceDate)": "SUBSTR(CAST(InvoiceDate AS TEXT), 1, 4)",
    }
    for question, serialized in mini_fake_responses().items():
        payload = json.loads(serialized)
        proposed_sql = payload.get("sql")
        if isinstance(proposed_sql, str):
            for source, target in replacements.items():
                proposed_sql = proposed_sql.replace(source, target)
            payload["sql"] = proposed_sql
        responses[question] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    dataset = load_evaluation_dataset(project_root / "data" / "evaluation" / "stage-7-v1.jsonl")
    for case in dataset.cases:
        if case.category is not EvaluationCategory.UNSAFE or case.expected_sql is None:
            continue
        proposal = StructuredSQLProposal(
            intent=LLMIntent.ANALYSIS,
            language=case.language,
            needs_clarification=False,
            assumptions=(),
            sql=case.expected_sql,
            tables=case.allowed_tables,
            columns=case.allowed_columns,
            confidence=1.0,
            reasoning_summary=(
                "SQL adversarial deterministik harus diblokir oleh kebijakan keamanan."
                if case.language.value == "id"
                else "Deterministic adversarial SQL must be blocked by the security policy."
            ),
        )
        responses[case.question] = proposal.model_dump_json()
    return responses
