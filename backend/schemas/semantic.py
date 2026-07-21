"""Strict contracts for the versioned Chinook semantic layer."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.llm import LanguageCode


class StrictSemanticModel(BaseModel):
    """Shared immutable and extra-forbidding semantic model configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class LocalizedText(StrictSemanticModel):
    """Required Indonesian and English text."""

    id: str = Field(min_length=1, max_length=500)
    en: str = Field(min_length=1, max_length=500)

    def for_language(self, language: LanguageCode) -> str:
        return self.id if language is LanguageCode.INDONESIAN else self.en


class LocalizedPhrases(StrictSemanticModel):
    """Normalized-match candidates in both supported languages."""

    id: tuple[str, ...] = Field(min_length=1, max_length=30)
    en: tuple[str, ...] = Field(min_length=1, max_length=30)

    def for_language(self, language: LanguageCode) -> tuple[str, ...]:
        return self.id if language is LanguageCode.INDONESIAN else self.en


class ClarificationOption(StrictSemanticModel):
    """One explicit way to resolve an ambiguous business phrase."""

    option_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: LocalizedText
    resolution_phrases: LocalizedPhrases
    assumption: LocalizedText
    metric_ids: tuple[str, ...] = Field(default=(), max_length=10)


class ClarificationRule(StrictSemanticModel):
    """Question and supported resolutions for one ambiguous glossary term."""

    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    question: LocalizedText
    options: tuple[ClarificationOption, ...] = Field(min_length=2, max_length=5)


class GlossaryTerm(StrictSemanticModel):
    """One canonical concept and all safe lexical aliases."""

    term_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: LocalizedText
    definition: LocalizedText
    synonyms: LocalizedPhrases
    ambiguity: ClarificationRule | None = None
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=10)


class ReviewStatus(StrEnum):
    """Human-review provenance; technical validation is tracked separately."""

    DRAFT = "draft"
    PROJECT_VERIFIED = "project_verified"
    ANALYST_VERIFIED = "analyst_verified"


class MetricFormat(StrEnum):
    """Display intent without changing the stored numeric value."""

    CURRENCY = "currency"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DURATION_MS = "duration_ms"


class MetricDefinition(StrictSemanticModel):
    """Canonical metric expression at an explicit source grain."""

    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: LocalizedText
    definition: LocalizedText
    aliases: LocalizedPhrases
    expression: str = Field(min_length=1, max_length=2_000)
    source_table: str = Field(min_length=1, max_length=128)
    term_ids: tuple[str, ...] = Field(default=(), max_length=20)
    grain: str = Field(min_length=1, max_length=300)
    aggregation: str = Field(min_length=1, max_length=50)
    format: MetricFormat
    dimensions: tuple[str, ...] = Field(default=(), max_length=50)
    time_dimension: str | None = Field(default=None, max_length=257)
    requires_period: bool = False
    double_counting_note: str = Field(min_length=1, max_length=500)
    review_status: ReviewStatus
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=10)


class JoinCardinality(StrEnum):
    """Cardinality from left table to right table."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class ApprovalStatus(StrEnum):
    """Whether a relationship may be retrieved for generation."""

    APPROVED = "approved"
    DRAFT = "draft"
    REJECTED = "rejected"


class RiskLevel(StrEnum):
    """Known aggregation duplication risk when traversing a join."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class JoinDefinition(StrictSemanticModel):
    """One explicitly reviewed relationship between physical tables."""

    join_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    left_table: str = Field(min_length=1, max_length=128)
    left_columns: tuple[str, ...] = Field(min_length=1, max_length=10)
    right_table: str = Field(min_length=1, max_length=128)
    right_columns: tuple[str, ...] = Field(min_length=1, max_length=10)
    cardinality: JoinCardinality
    approval_status: ApprovalStatus
    double_counting_risk: RiskLevel
    guidance: str = Field(min_length=1, max_length=500)
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=10)


class VerifiedQueryStatus(StrEnum):
    """Only valid queries may enter retrieval or prompt context."""

    VALID = "valid"
    DRAFT = "draft"
    DEPRECATED = "deprecated"


class VerifiedQueryDefinition(StrictSemanticModel):
    """Human-inspectable question and SQL pair with provenance."""

    query_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    questions: LocalizedPhrases
    sql: str = Field(min_length=1, max_length=12_000)
    tables: tuple[str, ...] = Field(min_length=1, max_length=100)
    columns: tuple[str, ...] = Field(min_length=1, max_length=500)
    metric_ids: tuple[str, ...] = Field(default=(), max_length=20)
    join_ids: tuple[str, ...] = Field(default=(), max_length=20)
    assumptions: LocalizedPhrases | None = None
    tags: tuple[str, ...] = Field(default=(), max_length=20)
    expected_result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: VerifiedQueryStatus
    review_status: ReviewStatus
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=10)


class GlossaryDocument(StrictSemanticModel):
    semantic_version: str = Field(min_length=1, max_length=50)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    terms: tuple[GlossaryTerm, ...] = Field(min_length=1)


class MetricsDocument(StrictSemanticModel):
    semantic_version: str = Field(min_length=1, max_length=50)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics: tuple[MetricDefinition, ...] = Field(min_length=1)


class JoinsDocument(StrictSemanticModel):
    semantic_version: str = Field(min_length=1, max_length=50)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    joins: tuple[JoinDefinition, ...] = Field(min_length=1)


class VerifiedQueriesDocument(StrictSemanticModel):
    semantic_version: str = Field(min_length=1, max_length=50)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    queries: tuple[VerifiedQueryDefinition, ...] = Field(min_length=1)


class DialectQueryOverride(StrictSemanticModel):
    """Dialect-specific SQL for an existing verified query identifier."""

    sql: str = Field(min_length=1, max_length=12_000)
    expected_result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SemanticDialectOverlay(StrictSemanticModel):
    """Small canonical overlay that keeps business definitions single-sourced."""

    base_semantic_version: str = Field(min_length=1, max_length=50)
    semantic_version: str = Field(min_length=1, max_length=50)
    base_schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    dialect: str = Field(min_length=1, max_length=32)
    clear_expected_result_hashes: bool = True
    query_overrides: dict[str, DialectQueryOverride] = Field(default_factory=dict)


class SemanticLayerBundle(StrictSemanticModel):
    """All semantic documents loaded as one content-addressed unit."""

    glossary: GlossaryDocument
    metrics: MetricsDocument
    joins: JoinsDocument
    verified_queries: VerifiedQueriesDocument
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def semantic_version(self) -> str:
        return self.glossary.semantic_version

    @property
    def schema_hash(self) -> str:
        return self.glossary.schema_hash


class SemanticViolationCode(StrEnum):
    """Stable validation codes safe for reports and startup errors."""

    VERSION_MISMATCH = "version_mismatch"
    SCHEMA_HASH_MISMATCH = "schema_hash_mismatch"
    DUPLICATE_IDENTIFIER = "duplicate_identifier"
    SYNONYM_CONFLICT = "synonym_conflict"
    UNKNOWN_TABLE = "unknown_table"
    UNKNOWN_COLUMN = "unknown_column"
    METRIC_EXPRESSION_INVALID = "metric_expression_invalid"
    JOIN_KEY_INVALID = "join_key_invalid"
    JOIN_NOT_FOREIGN_KEY = "join_not_foreign_key"
    UNKNOWN_METRIC = "unknown_metric"
    UNKNOWN_TERM = "unknown_term"
    UNKNOWN_JOIN = "unknown_join"
    VERIFIED_QUERY_INVALID = "verified_query_invalid"


class SemanticValidationIssue(StrictSemanticModel):
    """One sanitized semantic validation problem."""

    code: SemanticViolationCode
    location: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=500)


class SemanticValidationReport(StrictSemanticModel):
    """Complete deterministic validation result for one bundle."""

    valid: bool
    semantic_version: str
    schema_hash: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    term_count: int = Field(ge=0)
    metric_count: int = Field(ge=0)
    join_count: int = Field(ge=0)
    valid_verified_query_count: int = Field(ge=0)
    issues: tuple[SemanticValidationIssue, ...] = ()


class ClarificationDecision(StrictSemanticModel):
    """Pre-generation clarification selected from a versioned rule."""

    rule_id: str
    question: str
    options: tuple[str, ...] = Field(min_length=2, max_length=5)


class SemanticResolution(StrictSemanticModel):
    """Bounded semantic context selected for one user question."""

    semantic_version: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    language: LanguageCode
    matched_terms: tuple[GlossaryTerm, ...] = ()
    matched_metrics: tuple[MetricDefinition, ...] = ()
    approved_joins: tuple[JoinDefinition, ...] = ()
    verified_queries: tuple[VerifiedQueryDefinition, ...] = ()
    assumptions: tuple[str, ...] = ()
    clarification: ClarificationDecision | None = None
    context_truncated: bool = False
