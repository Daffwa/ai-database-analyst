"""Contract tests for the formal 100-case JSONL evaluation dataset."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from backend.evaluation.case_loader import (
    REQUIRED_DISTRIBUTION,
    EvaluationDatasetError,
    load_evaluation_dataset,
)
from backend.schemas.evaluation import EvaluationCategory

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evaluation" / "stage-7-v1.jsonl"


def test_formal_dataset_has_exact_distribution_and_split() -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)

    assert len(dataset.cases) == 100
    assert Counter(case.category for case in dataset.cases) == Counter(REQUIRED_DISTRIBUTION)
    assert dataset.split_counts == {"development": 70, "holdout": 30}
    assert len(dataset.sha256) == 64
    assert sum(case.category is EvaluationCategory.AMBIGUITY for case in dataset.cases) == 5
    assert sum(case.category is EvaluationCategory.UNSAFE for case in dataset.cases) == 10


def test_dataset_questions_are_not_verified_prompt_examples() -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)
    verified_text = (
        (ROOT / "semantic" / "verified_queries.yaml").read_text(encoding="utf-8").casefold()
    )

    assert all(case.question.casefold() not in verified_text for case in dataset.cases)


@pytest.mark.parametrize("mutation", ["duplicate", "version", "distribution", "invalid_json"])
def test_loader_fails_closed_on_dataset_drift(tmp_path: Path, mutation: str) -> None:
    lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()
    if mutation == "duplicate":
        lines.append(lines[0])
    elif mutation == "version":
        payload = json.loads(lines[0])
        payload["dataset_version"] = "unexpected"
        lines[0] = json.dumps(payload)
    elif mutation == "distribution":
        lines.pop()
    else:
        lines[0] = "{broken"
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationDatasetError):
        load_evaluation_dataset(path)


def test_loader_rejects_missing_or_empty_files(tmp_path: Path) -> None:
    with pytest.raises(EvaluationDatasetError):
        load_evaluation_dataset(tmp_path / "missing.jsonl")

    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(EvaluationDatasetError):
        load_evaluation_dataset(empty, enforce_distribution=False)
