"""Composition root for result processing and the complete Tahap 6 local UX."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from backend.core.config import AppSettings
from backend.core.logging import ensure_logging_configured
from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.evaluation.mini_cases import fake_responses as mini_fake_responses
from backend.evaluation.runner import TrustedDemoRunner
from backend.llm.factory import create_llm_adapter
from backend.schemas.database import SchemaAllowlist
from backend.schemas.result import DatabaseExplorerSnapshot, SafeSystemInfo
from backend.schemas.semantic import SemanticValidationReport
from backend.services.chart_selector import ChartPolicy, DeterministicChartSelector
from backend.services.csv_export import CSVExportService
from backend.services.experience_metadata import (
    DatabaseExplorerService,
    build_safe_system_info,
)
from backend.services.feedback_service import FeedbackService
from backend.services.orchestrator import QueryOrchestrator, QueryProcessor
from backend.services.output_parser import StructuredOutputParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.query_executor import ManualQueryExecutor
from backend.services.query_history import QueryHistoryService
from backend.services.result_experience import ResultExperienceOrchestrator
from backend.services.result_formatter import ResultFormatter
from backend.services.result_summarizer import ResultSummarizer
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot
from backend.services.secure_orchestrator import SecureQueryOrchestrator
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_service import SemanticService
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_generator import SQLGenerator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService


@dataclass(frozen=True, slots=True)
class Stage6Runtime:
    """Owned resources and user-experience services for Tahap 6."""

    engine: Engine
    orchestrator: QueryProcessor
    demo_runner: TrustedDemoRunner
    semantic_service: SemanticService
    semantic_validation: SemanticValidationReport
    history: QueryHistoryService
    feedback: FeedbackService
    csv_export: CSVExportService
    database_explorer: DatabaseExplorerSnapshot
    system_info: SafeSystemInfo

    def close(self) -> None:
        self.engine.dispose()


def create_stage6_runtime(
    root: Path,
    settings: AppSettings,
    *,
    fake_responses: Mapping[str, str] | None = None,
) -> Stage6Runtime:
    """Build the semantic, secured, result-aware fake runtime without network."""

    ensure_logging_configured(settings.app_log_level)
    schema_path = root / "data" / "schemas" / "chinook-v1.4.5.json"
    snapshot = load_schema_snapshot(schema_path)
    sql_security = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(
            dialect=settings.sql_dialect,
            max_rows=settings.query_max_rows,
            max_query_characters=settings.sql_max_query_characters,
            blocked_functions=frozenset(settings.sql_blocked_functions),
        ),
    )
    semantic_bundle = load_semantic_bundle(root / "semantic")
    semantic_validation = SemanticLayerValidator(
        snapshot,
        sql_security,
        expected_semantic_version=settings.semantic_version,
    ).validate(semantic_bundle)
    semantic_service = SemanticService(
        semantic_bundle,
        semantic_validation,
        max_verified_examples=settings.verified_query_max_examples,
        max_context_characters=settings.prompt_semantic_max_characters,
    )

    adapter = create_llm_adapter(
        settings,
        fake_responses=(mini_fake_responses() if fake_responses is None else fake_responses),
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
    engine = create_sqlite_read_only_engine(
        root / "data" / "processed" / "chinook.sqlite",
        timeout_seconds=settings.query_timeout_seconds,
    )
    executor = ManualQueryExecutor(
        engine,
        max_rows=settings.query_max_rows,
        max_columns=settings.query_max_columns,
        max_response_bytes=settings.query_max_response_bytes,
        max_query_characters=settings.sql_max_query_characters,
        timeout_seconds=settings.query_timeout_seconds,
    )
    secure = SecureQueryOrchestrator(generation, sql_security, executor)
    history = QueryHistoryService(
        max_entries=settings.query_history_max_entries,
        enabled=settings.enable_query_history,
    )
    feedback = FeedbackService(history)
    formatter = ResultFormatter(
        {metric.metric_id.casefold(): metric.format for metric in semantic_bundle.metrics.metrics}
    )
    experience = ResultExperienceOrchestrator(
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
    refreshed_at = datetime.fromtimestamp(schema_path.stat().st_mtime, UTC).isoformat()
    database_explorer = DatabaseExplorerService(
        snapshot,
        refreshed_at=refreshed_at,
    ).snapshot()
    return Stage6Runtime(
        engine=engine,
        orchestrator=experience,
        demo_runner=TrustedDemoRunner(experience, executor),
        semantic_service=semantic_service,
        semantic_validation=semantic_validation,
        history=history,
        feedback=feedback,
        csv_export=CSVExportService(max_bytes=settings.csv_max_bytes),
        database_explorer=database_explorer,
        system_info=build_safe_system_info(settings, snapshot, semantic_validation),
    )
