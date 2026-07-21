"""Deterministic, bounded schema-context selection for prompt construction."""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass

from backend.schemas.database import SchemaSnapshot, TableMetadata

_ALIASES: dict[str, tuple[str, ...]] = {
    "Album": ("album",),
    "Artist": ("artist", "artis"),
    "Customer": ("customer", "customers", "pelanggan", "brazil", "brasil"),
    "Employee": (
        "employee",
        "employees",
        "karyawan",
        "support agent",
        "support rep",
        "support representative",
    ),
    "Genre": ("genre",),
    "Invoice": (
        "invoice",
        "invoices",
        "transaksi",
        "billing",
        "penagihan",
        "revenue",
        "pendapatan",
        "belanja",
        "terbaru",
        "latest",
        "year",
        "tahun",
        "month",
        "bulan",
    ),
    "InvoiceLine": (
        "sales",
        "penjualan",
        "invoice line",
        "invoice-line",
        "baris invoice",
        "unit sold",
        "units sold",
        "unit terjual",
        "quantity",
        "quantities",
    ),
    "MediaType": ("media type", "jenis media", "tipe media"),
    "Playlist": ("playlist",),
    "PlaylistTrack": ("playlist track",),
    "Track": ("track", "tracks", "lagu"),
}


@dataclass(frozen=True, slots=True)
class SchemaContext:
    """Bounded serialized schema selected for one natural-language question."""

    schema_hash: str
    table_names: tuple[str, ...]
    serialized: str
    truncated: bool


class SchemaRetriever:
    """Select tables by deterministic lexical scoring and relationship paths."""

    def __init__(self, *, max_tables: int = 8, max_characters: int = 12_000) -> None:
        if max_tables <= 0 or max_characters <= 0:
            raise ValueError("Schema context budgets must be greater than zero")
        self._max_tables = max_tables
        self._max_characters = max_characters

    def retrieve(self, question: str, snapshot: SchemaSnapshot) -> SchemaContext:
        normalized = " ".join(question.casefold().split())
        scores = {table.name: self._score_table(normalized, table) for table in snapshot.tables}
        selected = [name for name, score in scores.items() if score > 0]
        selected.sort(key=lambda name: (-scores[name], name.casefold()))
        selected = selected[: self._max_tables]
        selected = self._add_relationship_paths(selected, snapshot, scores)

        table_by_name = {table.name: table for table in snapshot.tables}
        serialized_tables: list[dict[str, object]] = []
        included: list[str] = []
        truncated = len(selected) < len([name for name, score in scores.items() if score > 0])
        for table_name in selected:
            candidate = [*serialized_tables, _serialize_table(table_by_name[table_name])]
            rendered = json.dumps(
                {"dialect": snapshot.dialect, "tables": candidate},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if len(rendered) > self._max_characters:
                truncated = True
                break
            serialized_tables = candidate
            included.append(table_name)

        serialized = json.dumps(
            {"dialect": snapshot.dialect, "tables": serialized_tables},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return SchemaContext(
            schema_hash=snapshot.schema_hash,
            table_names=tuple(included),
            serialized=serialized,
            truncated=truncated,
        )

    @staticmethod
    def _score_table(question: str, table: TableMetadata) -> int:
        score = sum(5 for alias in _ALIASES.get(table.name, ()) if alias in question)
        for column in table.columns:
            words = " ".join(
                part.casefold()
                for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", column.name)
            )
            if words and words in question:
                score += 1
        return score

    def _add_relationship_paths(
        self,
        selected: list[str],
        snapshot: SchemaSnapshot,
        scores: dict[str, int],
    ) -> list[str]:
        graph: dict[str, set[str]] = {table.name: set() for table in snapshot.tables}
        for table in snapshot.tables:
            for foreign_key in table.foreign_keys:
                graph[table.name].add(foreign_key.referred_table)
                graph[foreign_key.referred_table].add(table.name)

        expanded = list(selected)
        for index, start in enumerate(selected):
            for end in selected[index + 1 :]:
                path = _shortest_path(graph, start, end)
                for table_name in path:
                    if table_name not in expanded and len(expanded) < self._max_tables:
                        expanded.append(table_name)
        return sorted(expanded, key=lambda name: (-scores.get(name, 0), name.casefold()))


def _shortest_path(graph: dict[str, set[str]], start: str, end: str) -> tuple[str, ...]:
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(start, (start,))])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        if node == end:
            return path
        for neighbor in sorted(graph[node], key=str.casefold):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, (*path, neighbor)))
    return ()


def _serialize_table(table: TableMetadata) -> dict[str, object]:
    return {
        "name": table.name,
        "columns": [
            {
                "name": column.name,
                "type": column.data_type,
                "nullable": column.nullable,
            }
            for column in table.columns
        ],
        "primary_key": list(table.primary_key),
        "foreign_keys": [
            {
                "columns": list(foreign_key.constrained_columns),
                "referred_table": foreign_key.referred_table,
                "referred_columns": list(foreign_key.referred_columns),
            }
            for foreign_key in table.foreign_keys
        ],
    }
