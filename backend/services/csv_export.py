"""Bounded, on-demand, spreadsheet-safe CSV export."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from backend.core.errors import ResultTooLargeError
from backend.schemas.database import QueryResult
from backend.schemas.result import CSVExport


class CSVExportService:
    """Serialize only bounded returned rows and neutralize spreadsheet formulas."""

    def __init__(self, *, max_bytes: int = 1_000_000) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        self._max_bytes = max_bytes

    def export(self, request_id: str, result: QueryResult) -> CSVExport:
        """Create UTF-8 CSV without storing the payload or mutating source values."""

        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(result.columns)
        escaped = 0
        for row in result.rows:
            serialized: list[Any] = []
            for value in row:
                safe, was_escaped = _safe_cell(value)
                escaped += int(was_escaped)
                serialized.append(safe)
            writer.writerow(serialized)
        data = buffer.getvalue().encode("utf-8-sig")
        if len(data) > self._max_bytes:
            raise ResultTooLargeError(details={"max_csv_bytes": self._max_bytes})
        safe_id = "".join(character for character in request_id if character.isalnum())[:12]
        return CSVExport(
            filename=f"query-result-{safe_id or 'export'}.csv",
            data=data,
            size_bytes=len(data),
            formula_cells_escaped=escaped,
        )


def _safe_cell(value: Any) -> tuple[Any, bool]:
    if value is None:
        return "", False
    if isinstance(value, (date, datetime)):
        return value.isoformat(), False
    if not isinstance(value, str):
        return value, False
    inspection = value.lstrip("\t\r\n ")
    if inspection.startswith(("=", "+", "-", "@")):
        return f"'{value}", True
    return value, False
