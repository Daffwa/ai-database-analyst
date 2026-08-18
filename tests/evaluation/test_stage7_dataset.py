"""Contract tests for the formal 100-case JSONL evaluation dataset."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from backend.evaluation.case_loader import (
    DEVELOPMENT_DISTRIBUTION,
    REQUIRED_DISTRIBUTION,
    SEALED_HOLDOUT_DISTRIBUTION,
    EvaluationDatasetError,
    load_development_evaluation_dataset,
    load_evaluation_dataset,
    load_sealed_holdout_dataset,
)
from backend.schemas.evaluation import EvaluationCategory, SealedHoldoutManifest

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evaluation" / "stage-7-v1.jsonl"
DEVELOPMENT_DATASET_PATH = ROOT / "data" / "evaluation" / "stage-7-development-v2.jsonl"


def _write_synthetic_sealed_holdout(path: Path) -> None:
    source_rows = [
        json.loads(line)
        for line in DEVELOPMENT_DATASET_PATH.read_text(encoding="utf-8").splitlines()
    ]
    by_category: dict[str, list[dict[str, object]]] = {}
    for row in source_rows:
        by_category.setdefault(str(row["category"]), []).append(row)
    payloads = []
    for category, count in SEALED_HOLDOUT_DISTRIBUTION.items():
        available = by_category[category.value]
        for index in range(count):
            payload = dict(available[index % len(available)])
            payload.update(
                case_id=f"HOLD_{category.name}-{index + 1:03}",
                dataset_version="stage-7-holdout-v2",
                split="holdout",
                question=f"{payload['question']} [sealed synthetic {category.value} {index + 1}]",
            )
            payloads.append(payload)
    path.write_text(
        "".join(json.dumps(payload) + "\n" for payload in payloads),
        encoding="utf-8",
    )


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


def test_corrected_development_dataset_excludes_holdout_and_repairs_universal_aggregation() -> None:
    dataset = load_development_evaluation_dataset(DEVELOPMENT_DATASET_PATH)

    assert len(dataset.cases) == 70
    assert dataset.split_counts == {"development": 70}
    assert Counter(case.category for case in dataset.cases) == Counter(DEVELOPMENT_DISTRIBUTION)
    corrected = next(case for case in dataset.cases if case.case_id == "AGG-007")
    assert corrected.expected_sql is not None and "LIMIT" not in corrected.expected_sql
    assert corrected.expected_columns == ("ArtistId", "album_count")
    assert len(corrected.expected_rows) == 204


def test_sealed_holdout_loader_requires_exact_manifest_commitment(tmp_path: Path) -> None:
    payload_path = tmp_path / "holdout.jsonl"
    _write_synthetic_sealed_holdout(payload_path)
    committed = load_evaluation_dataset(
        payload_path,
        expected_version="stage-7-holdout-v2",
        enforce_distribution=False,
    )
    manifest = SealedHoldoutManifest(
        manifest_version="stage-7-sealed-holdout-manifest-v1",
        dataset_version=committed.version,
        dataset_sha256=committed.sha256,
        case_count=30,
        category_counts=SEALED_HOLDOUT_DISTRIBUTION,
        created_at="2026-08-18T00:00:00Z",
        curator_attestation_sha256="a" * 64,
        independently_curated=True,
        agent_unseen_before_freeze=True,
    )

    loaded = load_sealed_holdout_dataset(payload_path, manifest)
    assert loaded.sha256 == manifest.dataset_sha256
    lines = payload_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["question"] = "tampered"
    lines[0] = json.dumps(tampered)
    payload_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(EvaluationDatasetError, match="hash"):
        load_sealed_holdout_dataset(payload_path, manifest)


def test_sealed_holdout_manifest_rejects_incomplete_distribution(tmp_path: Path) -> None:
    payload = json.loads(DEVELOPMENT_DATASET_PATH.read_text(encoding="utf-8").splitlines()[0])
    payload.update(dataset_version="stage-7-holdout-v2", split="holdout")
    payload_path = tmp_path / "incomplete.jsonl"
    payload_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    committed = load_evaluation_dataset(
        payload_path,
        expected_version="stage-7-holdout-v2",
        enforce_distribution=False,
    )
    manifest = SealedHoldoutManifest(
        manifest_version="stage-7-sealed-holdout-manifest-v1",
        dataset_version=committed.version,
        dataset_sha256=committed.sha256,
        case_count=1,
        category_counts={committed.cases[0].category: 1},
        created_at="2026-08-18T00:00:00Z",
        curator_attestation_sha256="a" * 64,
        independently_curated=True,
        agent_unseen_before_freeze=True,
    )

    with pytest.raises(EvaluationDatasetError, match="manifest distribution"):
        load_sealed_holdout_dataset(payload_path, manifest)


def test_runtime_has_no_case_specific_agg007_policy() -> None:
    runtime_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((ROOT / "backend").rglob("*.py"))
    )

    assert "AGG-007" not in runtime_source


def test_dataset_identity_is_stable_across_platform_line_endings(tmp_path: Path) -> None:
    source = DATASET_PATH.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lf_path = tmp_path / "lf.jsonl"
    crlf_path = tmp_path / "crlf.jsonl"
    lf_path.write_bytes(source)
    crlf_path.write_bytes(source.replace(b"\n", b"\r\n"))

    lf_dataset = load_evaluation_dataset(lf_path)
    crlf_dataset = load_evaluation_dataset(crlf_path)

    assert lf_dataset.sha256 == crlf_dataset.sha256


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
