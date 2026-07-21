"""SQLAlchemy models for the separate application metadata database."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

METADATA_SCHEMA = "app_metadata"
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Metadata declarative base with deterministic constraint names."""

    metadata = MetaData(schema=METADATA_SCHEMA, naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DataSourceRecord(TimestampMixin, Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dialect: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)


class SchemaSnapshotRecord(TimestampMixin, Base):
    __tablename__ = "schema_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(f"{METADATA_SCHEMA}.data_sources.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    snapshot_location: Mapped[str] = mapped_column(String(500), nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False)


class VerifiedQueryRecord(TimestampMixin, Base):
    __tablename__ = "verified_queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey(f"{METADATA_SCHEMA}.data_sources.id", ondelete="CASCADE"), nullable=False
    )
    query_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    semantic_version: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sql_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QueryRequestRecord(TimestampMixin, Base):
    __tablename__ = "query_requests"
    __table_args__ = (Index("ix_query_requests_created_status", "created_at", "status"),)

    request_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ui_state: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    semantic_version: Mapped[str | None] = mapped_column(String(64))
    semantic_hash: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    sql_fingerprint: Mapped[str | None] = mapped_column(String(64))
    source_tables: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    row_count: Mapped[int | None] = mapped_column(Integer)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    database_latency_ms: Mapped[float | None] = mapped_column(Float)
    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)


class QueryAttemptRecord(TimestampMixin, Base):
    __tablename__ = "query_attempts"
    __table_args__ = (
        UniqueConstraint("request_id", "attempt_number", name="uq_query_attempt_request_number"),
        Index("ix_query_attempts_request_created", "request_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey(f"{METADATA_SCHEMA}.query_requests.request_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    sql_fingerprint: Mapped[str | None] = mapped_column(String(64))
    violation_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    execution_latency_ms: Mapped[float | None] = mapped_column(Float)


class QueryFeedbackRecord(TimestampMixin, Base):
    __tablename__ = "query_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey(f"{METADATA_SCHEMA}.query_requests.request_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    rating: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


class EvaluationCaseRecord(TimestampMixin, Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (Index("ix_evaluation_cases_dataset_category", "dataset_version", "category"),)

    case_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    split: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_action: Mapped[str] = mapped_column(String(32), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class EvaluationRunRecord(TimestampMixin, Base):
    __tablename__ = "evaluation_runs"

    run_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_version: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvaluationResultRecord(TimestampMixin, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", name="uq_evaluation_result_run_case"),
        Index("ix_evaluation_results_run_passed", "run_id", "passed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey(f"{METADATA_SCHEMA}.evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey(f"{METADATA_SCHEMA}.evaluation_cases.case_id", ondelete="RESTRICT"),
        nullable=False,
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    final_status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)


class UsageEventRecord(TimestampMixin, Base):
    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_events_type_created", "event_type", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
