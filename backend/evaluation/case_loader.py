"""Strict JSONL loading and distribution validation for Tahap 7."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from backend.schemas.evaluation import (
    EvaluationCase,
    EvaluationCategory,
    EvaluationSplit,
    SealedHoldoutManifest,
)

STAGE7_DATASET_VERSION = "stage-7-v1"
STAGE7_DEVELOPMENT_DATASET_VERSION = "stage-7-development-v2"
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
DEVELOPMENT_DISTRIBUTION: dict[EvaluationCategory, int] = {
    EvaluationCategory.FILTERING: 14,
    EvaluationCategory.AGGREGATION: 14,
    EvaluationCategory.MULTI_TABLE_JOIN: 14,
    EvaluationCategory.TIME_ANALYSIS: 7,
    EvaluationCategory.RANKING_TOP_N: 7,
    EvaluationCategory.SUBQUERY: 5,
    EvaluationCategory.AMBIGUITY: 2,
    EvaluationCategory.UNSAFE: 7,
}
SEALED_HOLDOUT_DISTRIBUTION: dict[EvaluationCategory, int] = {
    EvaluationCategory.FILTERING: 5,
    EvaluationCategory.AGGREGATION: 5,
    EvaluationCategory.MULTI_TABLE_JOIN: 5,
    EvaluationCategory.TIME_ANALYSIS: 3,
    EvaluationCategory.RANKING_TOP_N: 3,
    EvaluationCategory.SUBQUERY: 3,
    EvaluationCategory.AMBIGUITY: 3,
    EvaluationCategory.UNSAFE: 3,
}


class EvaluationDatasetError(ValueError):
    """Raised when a versioned JSONL dataset fails closed validation."""


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    """Loaded cases plus the platform-independent identity of their JSONL source."""

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

    # Git may materialize text files with different platform line endings. Hash a
    # canonical LF representation so the same committed corpus has one identity
    # on Windows and Linux while all other byte-level drift remains detectable.
    canonical_raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

    return EvaluationDataset(
        version=expected_version,
        sha256=hashlib.sha256(canonical_raw).hexdigest(),
        path=path,
        cases=tuple(cases),
    )


def load_development_evaluation_dataset(path: Path) -> EvaluationDataset:
    """Load the versioned development-only corpus used before candidate freeze."""

    dataset = load_evaluation_dataset(
        path,
        expected_version=STAGE7_DEVELOPMENT_DATASET_VERSION,
        enforce_distribution=False,
    )
    if any(case.split is not EvaluationSplit.DEVELOPMENT for case in dataset.cases):
        raise EvaluationDatasetError("development dataset contains a non-development case")
    if Counter(case.category for case in dataset.cases) != Counter(DEVELOPMENT_DISTRIBUTION):
        raise EvaluationDatasetError("development dataset distribution does not match")
    return dataset


def load_sealed_holdout_dataset(
    path: Path,
    manifest: SealedHoldoutManifest,
) -> EvaluationDataset:
    """Load a private holdout payload only when it matches its public commitment."""

    validate_sealed_holdout_manifest(manifest)
    dataset = load_evaluation_dataset(
        path,
        expected_version=manifest.dataset_version,
        enforce_distribution=False,
    )
    if dataset.sha256 != manifest.dataset_sha256:
        raise EvaluationDatasetError("sealed holdout payload hash does not match manifest")
    if len(dataset.cases) != manifest.case_count:
        raise EvaluationDatasetError("sealed holdout case count does not match manifest")
    if any(case.split is not EvaluationSplit.HOLDOUT for case in dataset.cases):
        raise EvaluationDatasetError("sealed holdout contains a non-holdout case")
    observed = Counter(case.category for case in dataset.cases)
    if observed != Counter(manifest.category_counts):
        raise EvaluationDatasetError("sealed holdout category distribution does not match manifest")
    return dataset


def validate_sealed_holdout_manifest(manifest: SealedHoldoutManifest) -> None:
    """Require the preregistered 30-case distribution across every category."""

    if Counter(manifest.category_counts) != Counter(SEALED_HOLDOUT_DISTRIBUTION):
        raise EvaluationDatasetError("sealed holdout manifest distribution does not match")
