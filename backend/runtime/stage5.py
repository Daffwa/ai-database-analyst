"""Composition root for the semantic and secured Tahap 5 demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from backend.core.config import AppSettings
from backend.core.logging import ensure_logging_configured
from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.evaluation.mini_cases import fake_responses
from backend.evaluation.runner import TrustedDemoRunner
from backend.llm.factory import create_llm_adapter
from backend.schemas.database import SchemaAllowlist
from backend.schemas.semantic import SemanticValidationReport
from backend.services.orchestrator import QueryOrchestrator, QueryProcessor
from backend.services.output_parser import StructuredOutputParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.query_executor import ManualQueryExecutor
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot
from backend.services.secure_orchestrator import SecureQueryOrchestrator
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_service import SemanticService
from backend.services.semantic_validator import SemanticLayerValidator
from backend.services.sql_generator import SQLGenerator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService


@dataclass(frozen=True, slots=True)
class Stage5Runtime:
    """Owned resources, semantic evidence, and entry points for Tahap 5."""

    engine: Engine
    orchestrator: QueryProcessor
    demo_runner: TrustedDemoRunner
    semantic_service: SemanticService
    semantic_validation: SemanticValidationReport

    def close(self) -> None:
        self.engine.dispose()


def create_stage5_runtime(root: Path, settings: AppSettings) -> Stage5Runtime:
    """Build the semantic, secured fake-provider runtime without network access."""

    ensure_logging_configured(settings.app_log_level)
    snapshot = load_schema_snapshot(root / "data" / "schemas" / "chinook-v1.4.5.json")
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

    adapter = create_llm_adapter(settings, fake_responses=fake_responses())
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
    generator_orchestrator = QueryOrchestrator(
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
    orchestrator = SecureQueryOrchestrator(generator_orchestrator, sql_security, executor)
    return Stage5Runtime(
        engine=engine,
        orchestrator=orchestrator,
        demo_runner=TrustedDemoRunner(orchestrator, executor),
        semantic_service=semantic_service,
        semantic_validation=semantic_validation,
    )
