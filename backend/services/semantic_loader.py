"""Safe loading and content addressing for versioned YAML semantic files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import ValidationError

from backend.core.errors import SemanticLayerError
from backend.schemas.semantic import (
    GlossaryDocument,
    JoinsDocument,
    MetricsDocument,
    SemanticDialectOverlay,
    SemanticLayerBundle,
    StrictSemanticModel,
    VerifiedQueriesDocument,
)

SemanticDocument = TypeVar("SemanticDocument", bound=StrictSemanticModel)


def load_semantic_bundle(
    root: Path,
    *,
    dialect_overlay: Path | None = None,
) -> SemanticLayerBundle:
    """Load the four required YAML files without constructing Python objects."""

    glossary = _load_document(root / "glossary.yaml", GlossaryDocument)
    metrics = _load_document(root / "metrics.yaml", MetricsDocument)
    joins = _load_document(root / "joins.yaml", JoinsDocument)
    verified_queries = _load_document(
        root / "verified_queries.yaml",
        VerifiedQueriesDocument,
    )
    if dialect_overlay is not None:
        overlay = _load_document(dialect_overlay, SemanticDialectOverlay)
        glossary, metrics, joins, verified_queries = _apply_overlay(
            glossary,
            metrics,
            joins,
            verified_queries,
            overlay,
        )
    canonical = json.dumps(
        {
            "glossary": glossary.model_dump(mode="json"),
            "metrics": metrics.model_dump(mode="json"),
            "joins": joins.model_dump(mode="json"),
            "verified_queries": verified_queries.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SemanticLayerBundle(
        glossary=glossary,
        metrics=metrics,
        joins=joins,
        verified_queries=verified_queries,
        content_hash=hashlib.sha256(canonical).hexdigest(),
    )


def _apply_overlay(
    glossary: GlossaryDocument,
    metrics: MetricsDocument,
    joins: JoinsDocument,
    verified_queries: VerifiedQueriesDocument,
    overlay: SemanticDialectOverlay,
) -> tuple[GlossaryDocument, MetricsDocument, JoinsDocument, VerifiedQueriesDocument]:
    if glossary.semantic_version != overlay.base_semantic_version:
        raise SemanticLayerError("The semantic dialect overlay version does not match its base.")
    if glossary.schema_hash != overlay.base_schema_hash:
        raise SemanticLayerError("The semantic dialect overlay schema does not match its base.")
    known_query_ids = {query.query_id for query in verified_queries.queries}
    if not set(overlay.query_overrides).issubset(known_query_ids):
        raise SemanticLayerError("The semantic dialect overlay references an unknown query.")

    common = {
        "semantic_version": overlay.semantic_version,
        "schema_hash": overlay.schema_hash,
    }
    queries = tuple(
        query.model_copy(
            update={
                **(
                    {"expected_result_sha256": None} if overlay.clear_expected_result_hashes else {}
                ),
                **(
                    {
                        "sql": override.sql,
                        "expected_result_sha256": override.expected_result_sha256,
                    }
                    if (override := overlay.query_overrides.get(query.query_id)) is not None
                    else {}
                ),
            }
        )
        for query in verified_queries.queries
    )
    return (
        glossary.model_copy(update=common),
        metrics.model_copy(update=common),
        joins.model_copy(update=common),
        verified_queries.model_copy(update={**common, "queries": queries}),
    )


def _load_document(
    path: Path,
    model_type: type[SemanticDocument],
) -> SemanticDocument:
    try:
        with path.open("r", encoding="utf-8") as source:
            raw: Any = yaml.safe_load(source)
        return model_type.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError, TypeError, ValueError) as exc:
        raise SemanticLayerError() from exc
