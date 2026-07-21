"""Safe schema explorer and allowlisted runtime information."""

from __future__ import annotations

from backend.core.config import AppSettings
from backend.schemas.database import SchemaSnapshot
from backend.schemas.result import (
    DatabaseExplorerSnapshot,
    ExplorerColumn,
    ExplorerRelationship,
    ExplorerTable,
    SafeSystemInfo,
)
from backend.schemas.semantic import SemanticValidationReport

_TABLE_DESCRIPTIONS = {
    "Album": "Album musik yang dimiliki satu artis.",
    "Artist": "Artis musik pada katalog Chinook.",
    "Customer": "Satu akun pelanggan dan lokasi penagihannya.",
    "Employee": "Pegawai dan struktur pelaporan dukungan pelanggan.",
    "Genre": "Klasifikasi genre untuk track.",
    "Invoice": "Satu transaksi pelanggan pada grain invoice.",
    "InvoiceLine": "Satu item track di dalam invoice.",
    "MediaType": "Format media untuk track.",
    "Playlist": "Daftar putar bernama.",
    "PlaylistTrack": "Keanggotaan many-to-many antara playlist dan track.",
    "Track": "Produk musik pada grain satu track.",
}


class DatabaseExplorerService:
    """Expose only schema metadata and reviewed descriptions, never sample rows."""

    def __init__(self, snapshot: SchemaSnapshot, *, refreshed_at: str) -> None:
        self._snapshot = snapshot
        self._refreshed_at = refreshed_at

    def snapshot(self) -> DatabaseExplorerSnapshot:
        """Build the complete schema-only explorer contract."""

        tables = tuple(
            ExplorerTable(
                name=table.name,
                business_description=_TABLE_DESCRIPTIONS.get(
                    table.name,
                    "Belum memiliki deskripsi bisnis yang ditinjau.",
                ),
                review_status="project_verified",
                columns=tuple(
                    ExplorerColumn(
                        name=column.name,
                        data_type=column.data_type,
                        nullable=column.nullable,
                        primary_key=column.primary_key_position is not None,
                    )
                    for column in table.columns
                ),
                primary_key=table.primary_key,
                relationships=tuple(
                    ExplorerRelationship(
                        columns=foreign_key.constrained_columns,
                        referred_table=foreign_key.referred_table,
                        referred_columns=foreign_key.referred_columns,
                    )
                    for foreign_key in table.foreign_keys
                ),
            )
            for table in self._snapshot.tables
        )
        return DatabaseExplorerSnapshot(
            source_name=self._snapshot.source_name,
            dialect=self._snapshot.dialect,
            schema_version=self._snapshot.schema_version,
            schema_hash=self._snapshot.schema_hash,
            refreshed_at=self._refreshed_at,
            tables=tables,
        )


def build_safe_system_info(
    settings: AppSettings,
    snapshot: SchemaSnapshot,
    semantic_validation: SemanticValidationReport,
) -> SafeSystemInfo:
    """Return a hard-coded allowlist that cannot accidentally serialize secrets."""

    return SafeSystemInfo(
        app_environment=settings.app_env,
        dataset=f"{snapshot.source_name} / {snapshot.schema_version}",
        schema_version=snapshot.schema_version,
        schema_hash=snapshot.schema_hash,
        semantic_version=semantic_validation.semantic_version,
        semantic_content_hash=semantic_validation.content_hash,
        prompt_version=settings.prompt_version,
        provider=settings.llm_provider,
        model=settings.llm_model,
        sql_dialect=settings.sql_dialect,
        max_result_rows=settings.query_max_rows,
        max_csv_bytes=settings.csv_max_bytes,
        query_history_storage=(
            "bounded in-memory metadata" if settings.enable_query_history else "disabled"
        ),
        raw_question_stored=settings.store_raw_question,
        raw_sql_stored=settings.store_raw_sql,
        result_rows_stored=settings.store_result_rows,
    )
