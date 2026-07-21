"""Composition root for the secured and deterministic Tahap 4 demo."""

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
from backend.services.orchestrator import QueryOrchestrator, QueryProcessor
from backend.services.output_parser import StructuredOutputParser
from backend.services.prompt_builder import PromptBuilder
from backend.services.query_executor import ManualQueryExecutor
from backend.services.schema_retriever import SchemaRetriever
from backend.services.schema_service import load_schema_snapshot
from backend.services.secure_orchestrator import SecureQueryOrchestrator
from backend.services.sql_generator import SQLGenerator
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService


@dataclass(frozen=True, slots=True)
class Stage4Runtime:
    """Owned resources and entry points for one local Tahap 4 runtime."""

    engine: Engine
    orchestrator: QueryProcessor
    demo_runner: TrustedDemoRunner

    def close(self) -> None:
        self.engine.dispose()


def create_stage4_runtime(root: Path, settings: AppSettings) -> Stage4Runtime:
    """Build the secured fake-provider runtime without network access."""

    ensure_logging_configured(settings.app_log_level)
    snapshot = load_schema_snapshot(root / "data" / "schemas" / "chinook-v1.4.5.json")
    adapter = create_llm_adapter(settings, fake_responses=fake_responses())
    retriever = SchemaRetriever(
        max_tables=settings.prompt_schema_max_tables,
        max_characters=settings.prompt_schema_max_characters,
    )
    generator = SQLGenerator(
        adapter,
        PromptBuilder(retriever, prompt_version=settings.prompt_version),
        StructuredOutputParser(max_characters=settings.llm_max_output_characters),
        timeout_seconds=settings.llm_timeout_seconds,
    )
    generator_orchestrator = QueryOrchestrator(
        generator,
        snapshot,
        max_question_characters=settings.question_max_characters,
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
    security = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(
            dialect=settings.sql_dialect,
            max_rows=settings.query_max_rows,
            max_query_characters=settings.sql_max_query_characters,
            blocked_functions=frozenset(settings.sql_blocked_functions),
        ),
    )
    orchestrator = SecureQueryOrchestrator(generator_orchestrator, security, executor)
    return Stage4Runtime(
        engine=engine,
        orchestrator=orchestrator,
        demo_runner=TrustedDemoRunner(orchestrator, executor),
    )
