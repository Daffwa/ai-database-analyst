"""Strict JSONL loading and distribution validation for Tahap 7."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from backend.schemas.evaluation import EvaluationCase, EvaluationCategory

STAGE7_DATASET_VERSION = "stage-7-v1"
REQUIRED_DISTRIBUTION: dict[EvaluationCategory, int] = {
    EvaluationCategory.FILTERING: 20,
    EvaluationCategory.AGGREGATION: 20,
    EvaluationCategory.MULTI_TABLE_JOIN: 20,
    EvaluationCategory.TIME_ANALYSIS: 10,
    EvaluationCategory.RANKING_TOP_N: 10,
    EvaluationCategory.SUBQUERY: 5,
    EvaluationCategory.AMBIGUITY: 5,
    EvaluationCategory.UNSAFE: 10,
}


class EvaluationDatasetError(ValueError):
    """Raised when a versioned JSONL dataset fails closed validation."""


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    """Loaded cases plus the exact content identity of their JSONL source."""

    version: str
    sha256: str
    path: Path
    cases: tuple[EvaluationCase, ...]

    @property
    def category_counts(self) -> dict[str, int]:
        counts = Counter(case.category.value for case in self.cases)
        return dict(sorted(counts.items()))

    @property
    def split_counts(self) -> dict[str, int]:
        counts = Counter(case.split.value for case in self.cases)
        return dict(sorted(counts.items()))


def load_evaluation_dataset(
    path: Path,
    *,
    expected_version: str = STAGE7_DATASET_VERSION,
    enforce_distribution: bool = True,
) -> EvaluationDataset:
    """Load every nonblank JSONL row and reject drift or duplicate identities."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvaluationDatasetError("evaluation dataset is unavailable") from exc

    cases: list[EvaluationCase] = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            case = EvaluationCase.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
            raise EvaluationDatasetError(
                f"evaluation dataset line {line_number} is invalid"
            ) from exc
        cases.append(case)

    if not cases:
        raise EvaluationDatasetError("evaluation dataset must not be empty")
    if len({case.case_id for case in cases}) != len(cases):
        raise EvaluationDatasetError("evaluation case IDs must be unique")
    if len({" ".join(case.question.casefold().split()) for case in cases}) != len(cases):
        raise EvaluationDatasetError("evaluation questions must be unique")
    versions = {case.dataset_version for case in cases}
    if versions != {expected_version}:
        raise EvaluationDatasetError("evaluation dataset version does not match")

    if enforce_distribution:
        observed = Counter(case.category for case in cases)
        if observed != Counter(REQUIRED_DISTRIBUTION):
            raise EvaluationDatasetError(
                "evaluation category distribution does not match the required 100-case contract"
            )

    return EvaluationDataset(
        version=expected_version,
        sha256=hashlib.sha256(raw).hexdigest(),
        path=path,
        cases=tuple(cases),
    )
