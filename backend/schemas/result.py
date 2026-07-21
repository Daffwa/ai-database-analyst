"""Strict contracts for result presentation, charts, history, and feedback."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictResultModel(BaseModel):
    """Shared immutable and extra-forbidding result model configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class ColumnRole(StrEnum):
    """Analytical role inferred from returned values, never from model claims."""

    IDENTIFIER = "identifier"
    TEMPORAL = "temporal"
    MEASURE = "measure"
    CATEGORY = "category"
    UNKNOWN = "unknown"


class ValueFormat(StrEnum):
    """Presentation format that leaves the underlying result value unchanged."""

    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    DATE = "date"
    DATETIME = "datetime"


class ChartType(StrEnum):
    """Small deterministic visualization vocabulary supported by Streamlit."""

    KPI = "kpi"
    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    TABLE = "table"


class ChartOrientation(StrEnum):
    """Bar direction selected from label density."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class UXState(StrEnum):
    """Reader-facing states independent of framework widgets."""

    SUCCESS = "success"
    EMPTY = "empty"
    CLARIFICATION = "clarification"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNSUPPORTED = "unsupported"
    PENDING = "pending"


class ResultColumn(StrictResultModel):
    """One returned column with inferred role and non-mutating display intent."""

    name: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=256)
    role: ColumnRole
    format: ValueFormat
    nullable: bool


class ResultPresentation(StrictResultModel):
    """Normalized raw values plus a parallel display-only representation."""

    columns: tuple[ResultColumn, ...]
    rows: tuple[tuple[Any, ...], ...]
    display_rows: tuple[tuple[str, ...], ...]
    row_count: int = Field(ge=0)
    truncated: bool
    execution_time_ms: float = Field(ge=0)
    source_tables: tuple[str, ...] = ()
    source_columns: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        """Ensure the display view cannot drift from the database result shape."""

        if self.row_count != len(self.rows) or len(self.rows) != len(self.display_rows):
            raise ValueError("row_count, rows, and display_rows must have equal lengths")
        width = len(self.columns)
        if any(len(row) != width for row in (*self.rows, *self.display_rows)):
            raise ValueError("every row must match the result column count")
        return self


class ChartSpec(StrictResultModel):
    """Renderer-neutral chart choice containing only returned column names."""

    type: ChartType
    x: str | None = Field(default=None, max_length=256)
    y: tuple[str, ...] = Field(default=(), max_length=5)
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = Field(min_length=1, max_length=300)
    x_label: str | None = Field(default=None, max_length=200)
    y_label: str | None = Field(default=None, max_length=200)
    format: ValueFormat
    orientation: ChartOrientation = ChartOrientation.VERTICAL
    palette: tuple[str, ...] = Field(default=("#2563EB",), min_length=1, max_length=5)
    non_color_distinction: str = Field(min_length=1, max_length=300)
    data_row_count: int = Field(ge=0)
    warnings: tuple[str, ...] = ()


class NumericEvidence(StrictResultModel):
    """Exact result location cited by a deterministic summary."""

    column: str = Field(min_length=1, max_length=256)
    row_index: int = Field(ge=0)
    raw_value: int | float
    display_value: str = Field(min_length=1, max_length=200)


class ResultSummary(StrictResultModel):
    """Grounded explanation and the exact numeric cells it references."""

    text: str = Field(min_length=1, max_length=1_000)
    evidence: tuple[NumericEvidence, ...] = Field(default=(), max_length=10)


class FeedbackRating(StrEnum):
    """Fixed feedback choices; no free-form sensitive text is required."""

    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"


class FeedbackRecord(StrictResultModel):
    """One in-memory feedback decision tied to a known request ID."""

    request_id: str = Field(min_length=1, max_length=100)
    rating: FeedbackRating
    created_at: str = Field(min_length=1, max_length=50)


class HistoryEntry(StrictResultModel):
    """Privacy-minimized query history without question, SQL, or result rows."""

    request_id: str = Field(min_length=1, max_length=100)
    created_at: str = Field(min_length=1, max_length=50)
    status: str = Field(min_length=1, max_length=50)
    ui_state: UXState
    sql_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    row_count: int | None = Field(default=None, ge=0)
    truncated: bool = False
    total_latency_ms: float = Field(ge=0)
    feedback: FeedbackRating | None = None


class CSVExport(StrictResultModel):
    """Bounded spreadsheet-safe CSV payload generated on demand."""

    filename: str = Field(min_length=1, max_length=200)
    media_type: str = "text/csv"
    data: bytes
    size_bytes: int = Field(ge=0)
    formula_cells_escaped: int = Field(ge=0)


class ExplorerColumn(StrictResultModel):
    """Safe database-explorer column metadata without sample values."""

    name: str
    data_type: str
    nullable: bool
    primary_key: bool


class ExplorerRelationship(StrictResultModel):
    """One physical foreign-key relationship shown in the explorer."""

    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]


class ExplorerTable(StrictResultModel):
    """One schema table and project-reviewed business description."""

    name: str
    business_description: str
    review_status: str
    columns: tuple[ExplorerColumn, ...]
    primary_key: tuple[str, ...]
    relationships: tuple[ExplorerRelationship, ...]


class DatabaseExplorerSnapshot(StrictResultModel):
    """Safe schema-only explorer payload."""

    source_name: str
    dialect: str
    schema_version: str
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    refreshed_at: str
    tables: tuple[ExplorerTable, ...]


class SafeSystemInfo(StrictResultModel):
    """Explicit allowlist of non-secret runtime information."""

    app_environment: str
    dataset: str
    schema_version: str
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_version: str
    semantic_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str
    provider: str
    model: str
    sql_dialect: str
    max_result_rows: int = Field(ge=1)
    max_csv_bytes: int = Field(ge=1)
    query_history_storage: str
    raw_question_stored: bool
    raw_sql_stored: bool
    result_rows_stored: bool
