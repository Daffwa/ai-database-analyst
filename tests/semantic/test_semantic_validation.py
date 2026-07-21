"""Fail-closed validation tests for every semantic definition class."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.errors import SemanticLayerError
from backend.schemas.semantic import (
    LocalizedPhrases,
    SemanticLayerBundle,
    SemanticValidationReport,
    SemanticViolationCode,
)
from backend.services.semantic_loader import load_semantic_bundle
from backend.services.semantic_validator import SemanticLayerValidator


def _codes(report: SemanticValidationReport) -> set[SemanticViolationCode]:
    return {issue.code for issue in report.issues}


def test_real_semantic_bundle_is_content_addressed_and_fully_valid(
    semantic_bundle: SemanticLayerBundle,
    semantic_report: SemanticValidationReport,
) -> None:
    assert semantic_report.valid is True
    assert semantic_report.semantic_version == "v1"
    assert semantic_report.schema_hash == semantic_bundle.schema_hash
    assert semantic_report.content_hash == semantic_bundle.content_hash
    assert semantic_report.term_count == 9
    assert semantic_report.metric_count == 10
    assert semantic_report.join_count == 11
    assert semantic_report.valid_verified_query_count == 10
    assert semantic_report.issues == ()


def test_loader_is_deterministic_and_sanitizes_missing_or_invalid_yaml(
    semantic_bundle: SemanticLayerBundle,
    tmp_path: Path,
) -> None:
    assert load_semantic_bundle(Path(__file__).resolve().parents[2] / "semantic") == (
        semantic_bundle
    )
    with pytest.raises(SemanticLayerError) as missing:
        load_semantic_bundle(tmp_path)
    assert str(tmp_path) not in missing.value.public_message

    (tmp_path / "glossary.yaml").write_text("terms: [", encoding="utf-8")
    with pytest.raises(SemanticLayerError):
        load_semantic_bundle(tmp_path)


def test_document_version_and_schema_hash_must_match(
    semantic_bundle: SemanticLayerBundle,
    semantic_validator: SemanticLayerValidator,
) -> None:
    changed = semantic_bundle.model_copy(
        update={
            "metrics": semantic_bundle.metrics.model_copy(
                update={"semantic_version": "v2", "schema_hash": "0" * 64}
            )
        }
    )
    report = semantic_validator.validate(changed)

    assert report.valid is False
    assert {
        SemanticViolationCode.VERSION_MISMATCH,
        SemanticViolationCode.SCHEMA_HASH_MISMATCH,
    } <= _codes(report)


def test_duplicate_identifiers_and_synonym_conflicts_are_rejected(
    semantic_bundle: SemanticLayerBundle,
    semantic_validator: SemanticLayerValidator,
) -> None:
    first, second, *remaining = semantic_bundle.glossary.terms
    conflict = second.model_copy(
        update={
            "synonyms": LocalizedPhrases(
                id=(first.synonyms.id[0],),
                en=(first.synonyms.en[0],),
            )
        }
    )
    changed = semantic_bundle.model_copy(
        update={
            "glossary": semantic_bundle.glossary.model_copy(
                update={"terms": (first, conflict, *remaining, first)}
            )
        }
    )
    report = semantic_validator.validate(changed)

    assert SemanticViolationCode.DUPLICATE_IDENTIFIER in _codes(report)
    assert SemanticViolationCode.SYNONYM_CONFLICT in _codes(report)


@pytest.mark.parametrize(
    ("update", "expected_code"),
    [
        ({"source_table": "Missing"}, SemanticViolationCode.UNKNOWN_TABLE),
        (
            {"dimensions": ("Invoice.DoesNotExist",)},
            SemanticViolationCode.UNKNOWN_COLUMN,
        ),
        (
            {"expression": "SUM(Customer.CustomerId)"},
            SemanticViolationCode.METRIC_EXPRESSION_INVALID,
        ),
        ({"term_ids": ("missing_term",)}, SemanticViolationCode.UNKNOWN_TERM),
    ],
)
def test_metric_references_and_expressions_fail_closed(
    semantic_bundle: SemanticLayerBundle,
    semantic_validator: SemanticLayerValidator,
    update: dict[str, object],
    expected_code: SemanticViolationCode,
) -> None:
    metric = semantic_bundle.metrics.metrics[0].model_copy(update=update)
    changed = semantic_bundle.model_copy(
        update={
            "metrics": semantic_bundle.metrics.model_copy(
                update={"metrics": (metric, *semantic_bundle.metrics.metrics[1:])}
            )
        }
    )

    assert expected_code in _codes(semantic_validator.validate(changed))


@pytest.mark.parametrize(
    ("update", "expected_code"),
    [
        ({"left_columns": ("DoesNotExist",)}, SemanticViolationCode.JOIN_KEY_INVALID),
        (
            {"left_columns": ("AlbumId",)},
            SemanticViolationCode.JOIN_NOT_FOREIGN_KEY,
        ),
    ],
)
def test_join_keys_must_exist_and_match_a_real_foreign_key(
    semantic_bundle: SemanticLayerBundle,
    semantic_validator: SemanticLayerValidator,
    update: dict[str, object],
    expected_code: SemanticViolationCode,
) -> None:
    join = semantic_bundle.joins.joins[0].model_copy(update=update)
    changed = semantic_bundle.model_copy(
        update={
            "joins": semantic_bundle.joins.model_copy(
                update={"joins": (join, *semantic_bundle.joins.joins[1:])}
            )
        }
    )

    assert expected_code in _codes(semantic_validator.validate(changed))


@pytest.mark.parametrize(
    ("update", "expected_code"),
    [
        ({"metric_ids": ("missing_metric",)}, SemanticViolationCode.UNKNOWN_METRIC),
        ({"join_ids": ("missing_join",)}, SemanticViolationCode.UNKNOWN_JOIN),
        ({"sql": "DELETE FROM Customer"}, SemanticViolationCode.VERIFIED_QUERY_INVALID),
    ],
)
def test_verified_query_references_and_sql_are_fully_validated(
    semantic_bundle: SemanticLayerBundle,
    semantic_validator: SemanticLayerValidator,
    update: dict[str, object],
    expected_code: SemanticViolationCode,
) -> None:
    query = semantic_bundle.verified_queries.queries[0].model_copy(update=update)
    changed = semantic_bundle.model_copy(
        update={
            "verified_queries": semantic_bundle.verified_queries.model_copy(
                update={"queries": (query, *semantic_bundle.verified_queries.queries[1:])}
            )
        }
    )

    assert expected_code in _codes(semantic_validator.validate(changed))


def test_unknown_metric_in_clarification_option_is_rejected(
    semantic_bundle: SemanticLayerBundle,
    semantic_validator: SemanticLayerValidator,
) -> None:
    term = next(term for term in semantic_bundle.glossary.terms if term.ambiguity)
    assert term.ambiguity is not None
    option = term.ambiguity.options[0].model_copy(update={"metric_ids": ("missing_metric",)})
    changed_term = term.model_copy(
        update={
            "ambiguity": term.ambiguity.model_copy(
                update={"options": (option, *term.ambiguity.options[1:])}
            )
        }
    )
    terms = tuple(
        changed_term if candidate.term_id == term.term_id else candidate
        for candidate in semantic_bundle.glossary.terms
    )
    changed = semantic_bundle.model_copy(
        update={"glossary": semantic_bundle.glossary.model_copy(update={"terms": terms})}
    )

    assert SemanticViolationCode.UNKNOWN_METRIC in _codes(semantic_validator.validate(changed))
