"""Deterministic semantic definitions validation against schema and SQL policy."""

from __future__ import annotations

from collections.abc import Iterable

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from backend.schemas.database import SchemaAllowlist, SchemaSnapshot
from backend.schemas.semantic import (
    JoinDefinition,
    MetricDefinition,
    SemanticLayerBundle,
    SemanticValidationIssue,
    SemanticValidationReport,
    SemanticViolationCode,
    VerifiedQueryDefinition,
    VerifiedQueryStatus,
)
from backend.services.sql_security import SQLSecurityService

_MESSAGES: dict[SemanticViolationCode, str] = {
    SemanticViolationCode.VERSION_MISMATCH: (
        "Semantic document versions must match the active version."
    ),
    SemanticViolationCode.SCHEMA_HASH_MISMATCH: (
        "Semantic documents must target the active schema hash."
    ),
    SemanticViolationCode.DUPLICATE_IDENTIFIER: "Semantic identifiers must be unique.",
    SemanticViolationCode.SYNONYM_CONFLICT: "A synonym cannot resolve to multiple definitions.",
    SemanticViolationCode.UNKNOWN_TABLE: "A semantic definition references an unavailable table.",
    SemanticViolationCode.UNKNOWN_COLUMN: "A semantic definition references an unavailable column.",
    SemanticViolationCode.METRIC_EXPRESSION_INVALID: (
        "The metric expression is not a valid safe expression."
    ),
    SemanticViolationCode.JOIN_KEY_INVALID: "Join key columns must exist and have matching arity.",
    SemanticViolationCode.JOIN_NOT_FOREIGN_KEY: (
        "The approved join does not match a schema foreign key."
    ),
    SemanticViolationCode.UNKNOWN_METRIC: "A verified query references an unknown metric.",
    SemanticViolationCode.UNKNOWN_TERM: "A metric references an unknown glossary term.",
    SemanticViolationCode.UNKNOWN_JOIN: "A verified query references an unknown join.",
    SemanticViolationCode.VERIFIED_QUERY_INVALID: (
        "A verified query did not pass the SQL security policy."
    ),
}


class SemanticLayerValidator:
    """Validate versions, vocabulary, expressions, joins, and verified SQL."""

    def __init__(
        self,
        snapshot: SchemaSnapshot,
        sql_validator: SQLSecurityService,
        *,
        expected_semantic_version: str,
    ) -> None:
        self._snapshot = snapshot
        self._allowlist = SchemaAllowlist.from_snapshot(snapshot)
        self._sql_validator = sql_validator
        self._expected_version = expected_semantic_version

    def validate(self, bundle: SemanticLayerBundle) -> SemanticValidationReport:
        issues: list[SemanticValidationIssue] = []
        documents = (
            ("glossary", bundle.glossary.semantic_version, bundle.glossary.schema_hash),
            ("metrics", bundle.metrics.semantic_version, bundle.metrics.schema_hash),
            ("joins", bundle.joins.semantic_version, bundle.joins.schema_hash),
            (
                "verified_queries",
                bundle.verified_queries.semantic_version,
                bundle.verified_queries.schema_hash,
            ),
        )
        for location, version, schema_hash in documents:
            if version != self._expected_version:
                _add_issue(issues, SemanticViolationCode.VERSION_MISMATCH, location)
            if schema_hash != self._snapshot.schema_hash:
                _add_issue(issues, SemanticViolationCode.SCHEMA_HASH_MISMATCH, location)

        self._validate_unique_ids(bundle, issues)
        self._validate_synonyms(bundle, issues)
        term_ids = {term.term_id for term in bundle.glossary.terms}
        metric_ids = {metric.metric_id for metric in bundle.metrics.metrics}
        for term in bundle.glossary.terms:
            if term.ambiguity is not None and any(
                not set(option.metric_ids) <= metric_ids for option in term.ambiguity.options
            ):
                _add_issue(
                    issues,
                    SemanticViolationCode.UNKNOWN_METRIC,
                    f"glossary.{term.term_id}",
                )
        for metric in bundle.metrics.metrics:
            self._validate_metric(metric, term_ids, issues)
        for join in bundle.joins.joins:
            self._validate_join(join, issues)
        self._validate_verified_queries(bundle, issues)

        return SemanticValidationReport(
            valid=not issues,
            semantic_version=bundle.semantic_version,
            schema_hash=bundle.schema_hash,
            content_hash=bundle.content_hash,
            term_count=len(bundle.glossary.terms),
            metric_count=len(bundle.metrics.metrics),
            join_count=len(bundle.joins.joins),
            valid_verified_query_count=sum(
                query.status is VerifiedQueryStatus.VALID
                for query in bundle.verified_queries.queries
            ),
            issues=tuple(issues),
        )

    def _validate_unique_ids(
        self,
        bundle: SemanticLayerBundle,
        issues: list[SemanticValidationIssue],
    ) -> None:
        collections: tuple[tuple[str, Iterable[str]], ...] = (
            ("glossary", (term.term_id for term in bundle.glossary.terms)),
            ("metrics", (metric.metric_id for metric in bundle.metrics.metrics)),
            ("joins", (join.join_id for join in bundle.joins.joins)),
            (
                "verified_queries",
                (query.query_id for query in bundle.verified_queries.queries),
            ),
        )
        for location, identifiers in collections:
            values = tuple(identifiers)
            if len(values) != len(set(values)):
                _add_issue(issues, SemanticViolationCode.DUPLICATE_IDENTIFIER, location)

    def _validate_synonyms(
        self,
        bundle: SemanticLayerBundle,
        issues: list[SemanticValidationIssue],
    ) -> None:
        seen: dict[tuple[str, str], str] = {}
        for term in bundle.glossary.terms:
            phrases = (
                (("id", phrase) for phrase in (term.label.id, *term.synonyms.id)),
                (("en", phrase) for phrase in (term.label.en, *term.synonyms.en)),
            )
            for language_phrases in phrases:
                for language, phrase in language_phrases:
                    key = (language, _normalize_phrase(phrase))
                    owner = seen.setdefault(key, term.term_id)
                    if owner != term.term_id:
                        _add_issue(
                            issues,
                            SemanticViolationCode.SYNONYM_CONFLICT,
                            f"glossary.{term.term_id}",
                        )

    def _validate_metric(
        self,
        metric: MetricDefinition,
        term_ids: set[str],
        issues: list[SemanticValidationIssue],
    ) -> None:
        location = f"metrics.{metric.metric_id}"
        if not set(metric.term_ids) <= term_ids:
            _add_issue(issues, SemanticViolationCode.UNKNOWN_TERM, location)
        if not self._allowlist.allows_table(metric.source_table):
            _add_issue(issues, SemanticViolationCode.UNKNOWN_TABLE, location)
            return
        for reference in (
            *metric.dimensions,
            *((metric.time_dimension,) if metric.time_dimension else ()),
        ):
            self._validate_qualified_column(reference, location, issues)

        sql = f"SELECT {metric.expression} AS semantic_metric FROM {metric.source_table}"
        try:
            parsed = sqlglot.parse_one(sql, read=self._snapshot.dialect)
        except (SqlglotError, ValueError):
            _add_issue(issues, SemanticViolationCode.METRIC_EXPRESSION_INVALID, location)
            return
        if not isinstance(parsed, exp.Select) or len(parsed.expressions) != 1:
            _add_issue(issues, SemanticViolationCode.METRIC_EXPRESSION_INVALID, location)
            return
        expression_columns = tuple(parsed.expressions[0].find_all(exp.Column))
        if not expression_columns or any(
            column.table.casefold() != metric.source_table.casefold()
            for column in expression_columns
        ):
            _add_issue(issues, SemanticViolationCode.METRIC_EXPRESSION_INVALID, location)
            return
        report = self._sql_validator.validate(sql)
        if not report.safe or {table.casefold() for table in report.tables} != {
            metric.source_table.casefold()
        }:
            _add_issue(issues, SemanticViolationCode.METRIC_EXPRESSION_INVALID, location)

    def _validate_join(
        self,
        join: JoinDefinition,
        issues: list[SemanticValidationIssue],
    ) -> None:
        location = f"joins.{join.join_id}"
        if not self._allowlist.allows_table(join.left_table) or not self._allowlist.allows_table(
            join.right_table
        ):
            _add_issue(issues, SemanticViolationCode.UNKNOWN_TABLE, location)
            return
        if (
            len(join.left_columns) != len(join.right_columns)
            or any(
                not self._allowlist.allows_column(join.left_table, column)
                for column in join.left_columns
            )
            or any(
                not self._allowlist.allows_column(join.right_table, column)
                for column in join.right_columns
            )
        ):
            _add_issue(issues, SemanticViolationCode.JOIN_KEY_INVALID, location)
            return
        if not self._matches_foreign_key(join):
            _add_issue(issues, SemanticViolationCode.JOIN_NOT_FOREIGN_KEY, location)

    def _matches_foreign_key(self, join: JoinDefinition) -> bool:
        for table in self._snapshot.tables:
            for foreign_key in table.foreign_keys:
                direct = (
                    table.name == join.left_table
                    and foreign_key.referred_table == join.right_table
                    and foreign_key.constrained_columns == join.left_columns
                    and foreign_key.referred_columns == join.right_columns
                )
                reverse = (
                    table.name == join.right_table
                    and foreign_key.referred_table == join.left_table
                    and foreign_key.constrained_columns == join.right_columns
                    and foreign_key.referred_columns == join.left_columns
                )
                if direct or reverse:
                    return True
        return False

    def _validate_verified_queries(
        self,
        bundle: SemanticLayerBundle,
        issues: list[SemanticValidationIssue],
    ) -> None:
        metric_ids = {metric.metric_id for metric in bundle.metrics.metrics}
        join_ids = {join.join_id for join in bundle.joins.joins}
        for query in bundle.verified_queries.queries:
            location = f"verified_queries.{query.query_id}"
            if not set(query.metric_ids) <= metric_ids:
                _add_issue(issues, SemanticViolationCode.UNKNOWN_METRIC, location)
            if not set(query.join_ids) <= join_ids:
                _add_issue(issues, SemanticViolationCode.UNKNOWN_JOIN, location)
            self._validate_verified_query_sql(query, location, issues)

    def _validate_verified_query_sql(
        self,
        query: VerifiedQueryDefinition,
        location: str,
        issues: list[SemanticValidationIssue],
    ) -> None:
        report = self._sql_validator.validate(
            query.sql,
            declared_tables=query.tables,
            declared_columns=query.columns,
        )
        if not report.safe:
            _add_issue(issues, SemanticViolationCode.VERIFIED_QUERY_INVALID, location)

    def _validate_qualified_column(
        self,
        reference: str,
        location: str,
        issues: list[SemanticValidationIssue],
    ) -> None:
        parts = reference.split(".")
        if len(parts) != 2:
            _add_issue(issues, SemanticViolationCode.UNKNOWN_COLUMN, location)
            return
        table, column = parts
        if not self._allowlist.allows_table(table):
            _add_issue(issues, SemanticViolationCode.UNKNOWN_TABLE, location)
        elif not self._allowlist.allows_column(table, column):
            _add_issue(issues, SemanticViolationCode.UNKNOWN_COLUMN, location)


def _add_issue(
    issues: list[SemanticValidationIssue],
    code: SemanticViolationCode,
    location: str,
) -> None:
    issue = SemanticValidationIssue(code=code, location=location, message=_MESSAGES[code])
    if issue not in issues:
        issues.append(issue)


def _normalize_phrase(value: str) -> str:
    return " ".join(value.casefold().split())
