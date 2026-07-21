"""Fail-closed parsing and schema metadata checks for raw LLM output."""

from __future__ import annotations

import json

from pydantic import ValidationError

from backend.core.errors import LLMOutputError
from backend.schemas.database import SchemaAllowlist
from backend.schemas.llm import LLMIntent, StructuredSQLProposal


class StructuredOutputParser:
    """Accept exactly one JSON object matching the strict proposal contract."""

    def __init__(self, *, max_characters: int = 20_000) -> None:
        if max_characters <= 0:
            raise ValueError("max_characters must be greater than zero")
        self._max_characters = max_characters

    def parse(self, raw_output: str) -> StructuredSQLProposal:
        if not raw_output.strip() or len(raw_output) > self._max_characters:
            raise LLMOutputError()
        try:
            value = json.loads(raw_output)
            if not isinstance(value, dict):
                raise LLMOutputError()
            return StructuredSQLProposal.model_validate(value)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise LLMOutputError() from exc


def validate_declared_schema(
    proposal: StructuredSQLProposal,
    allowlist: SchemaAllowlist,
    *,
    context_tables: tuple[str, ...],
) -> None:
    """Check declared metadata only; Tahap 4 must still verify the SQL AST."""

    if proposal.intent is not LLMIntent.ANALYSIS:
        return
    if not proposal.tables or not proposal.columns:
        raise LLMOutputError()
    for table_name in proposal.tables:
        if not allowlist.allows_table(table_name) or table_name not in context_tables:
            raise LLMOutputError()
    for qualified_column in proposal.columns:
        table_name, separator, column_name = qualified_column.partition(".")
        if not separator or not allowlist.allows_column(table_name, column_name):
            raise LLMOutputError()
