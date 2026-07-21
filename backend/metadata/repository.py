"""Privacy-minimized metadata persistence with explicit field allowlists."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.core.errors import DatabaseUnavailableError, InvalidRequestError
from backend.metadata.models import (
    DataSourceRecord,
    QueryAttemptRecord,
    QueryFeedbackRecord,
    QueryRequestRecord,
    SchemaSnapshotRecord,
    UsageEventRecord,
    VerifiedQueryRecord,
)
from backend.schemas.database import SchemaSnapshot
from backend.schemas.llm import QueryResponse
from backend.schemas.result import FeedbackRating, FeedbackRecord, HistoryEntry, UXState
from backend.schemas.semantic import SemanticLayerBundle


class MetadataRepository:
    """Store durable audit metadata without raw questions, SQL, or result rows."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def synchronize_catalog(
        self,
        snapshot: SchemaSnapshot,
        semantic_bundle: SemanticLayerBundle,
        *,
        snapshot_location: str,
    ) -> None:
        """Idempotently register the active schema and verified-query identities."""

        try:
            with Session(self._engine) as session, session.begin():
                source = session.scalar(
                    select(DataSourceRecord).where(
                        DataSourceRecord.source_key == "chinook-postgresql-v1.4.5"
                    )
                )
                if source is None:
                    source = DataSourceRecord(
                        source_key="chinook-postgresql-v1.4.5",
                        display_name="Chinook PostgreSQL",
                        dialect=snapshot.dialect,
                        schema_version=snapshot.schema_version,
                        schema_hash=snapshot.schema_hash,
                        review_status="project_verified",
                    )
                    session.add(source)
                    session.flush()
                existing_snapshot = session.scalar(
                    select(SchemaSnapshotRecord).where(
                        SchemaSnapshotRecord.schema_hash == snapshot.schema_hash
                    )
                )
                if existing_snapshot is None:
                    session.add(
                        SchemaSnapshotRecord(
                            data_source_id=source.id,
                            schema_version=snapshot.schema_version,
                            schema_hash=snapshot.schema_hash,
                            snapshot_location=snapshot_location,
                            table_count=len(snapshot.tables),
                        )
                    )
                for query in semantic_bundle.verified_queries.queries:
                    existing_query = session.scalar(
                        select(VerifiedQueryRecord).where(
                            VerifiedQueryRecord.query_id == query.query_id
                        )
                    )
                    if existing_query is None:
                        session.add(
                            VerifiedQueryRecord(
                                data_source_id=source.id,
                                query_id=query.query_id,
                                semantic_version=semantic_bundle.semantic_version,
                                semantic_hash=semantic_bundle.content_hash,
                                sql_fingerprint=hashlib.sha256(
                                    query.sql.encode("utf-8")
                                ).hexdigest(),
                                review_status=query.review_status.value,
                                enabled=query.status.value == "valid",
                            )
                        )
        except Exception as exc:
            raise DatabaseUnavailableError("The metadata database is unavailable.") from exc

    def record_response(self, response: QueryResponse) -> None:
        """Persist one response and its safe attempt metadata atomically."""

        validation = response.validation
        violation_codes = (
            [violation.code.value for violation in validation.violations] if validation else []
        )
        record = QueryRequestRecord(
            request_id=response.request_id,
            status=response.status.value,
            ui_state=(response.ui_state or UXState.PENDING).value,
            language=response.language.value,
            prompt_version=response.prompt_version,
            schema_hash=response.schema_hash,
            semantic_version=response.semantic_version,
            semantic_hash=response.semantic_context_hash,
            provider=response.provider,
            model=response.model,
            sql_fingerprint=validation.fingerprint if validation else None,
            source_tables=list(validation.tables if validation else response.tables),
            row_count=response.result.row_count if response.result else None,
            truncated=response.result.truncated if response.result else False,
            llm_latency_ms=response.llm_latency_ms,
            database_latency_ms=response.database_latency_ms,
            total_latency_ms=response.llm_latency_ms + (response.database_latency_ms or 0.0),
        )
        try:
            with Session(self._engine) as session, session.begin():
                existing = session.get(QueryRequestRecord, response.request_id)
                if existing is None:
                    session.add(record)
                    session.flush()
                    if response.generated_sql is not None or validation is not None:
                        session.add(
                            QueryAttemptRecord(
                                request_id=response.request_id,
                                attempt_number=1,
                                status=response.status.value,
                                sql_fingerprint=validation.fingerprint if validation else None,
                                violation_codes=violation_codes,
                                execution_latency_ms=response.database_latency_ms,
                            )
                        )
                    session.add(
                        UsageEventRecord(
                            request_id=response.request_id,
                            event_type=response.status.value,
                            latency_ms=record.total_latency_ms,
                            provider=response.provider,
                            model=response.model,
                            attributes={"ui_state": record.ui_state},
                        )
                    )
        except Exception as exc:
            raise DatabaseUnavailableError("The metadata database is unavailable.") from exc

    def list_history(self, *, limit: int = 50, offset: int = 0) -> tuple[HistoryEntry, ...]:
        """Return newest-first safe history with bounded pagination."""

        if not 1 <= limit <= 100 or offset < 0:
            raise InvalidRequestError("History pagination is outside the allowed range.")
        statement = (
            select(QueryRequestRecord, QueryFeedbackRecord)
            .outerjoin(
                QueryFeedbackRecord,
                QueryFeedbackRecord.request_id == QueryRequestRecord.request_id,
            )
            .order_by(QueryRequestRecord.created_at.desc(), QueryRequestRecord.request_id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            with Session(self._engine) as session:
                rows = session.execute(statement).all()
        except Exception as exc:
            raise DatabaseUnavailableError("The metadata database is unavailable.") from exc
        return tuple(
            HistoryEntry(
                request_id=request.request_id,
                created_at=request.created_at.isoformat(),
                status=request.status,
                ui_state=UXState(request.ui_state),
                sql_fingerprint=request.sql_fingerprint,
                row_count=request.row_count,
                truncated=request.truncated,
                total_latency_ms=request.total_latency_ms,
                feedback=(FeedbackRating(feedback.rating) if feedback is not None else None),
            )
            for request, feedback in rows
        )

    def submit_feedback(
        self,
        request_id: str,
        rating: FeedbackRating,
    ) -> FeedbackRecord:
        """Create or replace a fixed-choice rating for a persisted request."""

        normalized = request_id.strip()
        if not normalized:
            raise InvalidRequestError("Request ID must not be empty.")
        created_at = datetime.now(UTC)
        try:
            with Session(self._engine) as session, session.begin():
                if session.get(QueryRequestRecord, normalized) is None:
                    raise InvalidRequestError("Feedback requires a known request.")
                existing = session.scalar(
                    select(QueryFeedbackRecord).where(QueryFeedbackRecord.request_id == normalized)
                )
                if existing is None:
                    session.add(
                        QueryFeedbackRecord(
                            request_id=normalized,
                            rating=rating.value,
                            created_at=created_at,
                        )
                    )
                else:
                    existing.rating = rating.value
                    existing.created_at = created_at
        except InvalidRequestError:
            raise
        except Exception as exc:
            raise DatabaseUnavailableError("The metadata database is unavailable.") from exc
        return FeedbackRecord(
            request_id=normalized,
            rating=rating,
            created_at=created_at.isoformat(),
        )

    def ping(self) -> bool:
        """Return dependency readiness without exposing connection details."""

        try:
            with self._engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        except Exception:
            return False
        return True
