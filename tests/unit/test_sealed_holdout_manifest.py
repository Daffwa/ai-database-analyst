"""Offline guards for independently curated holdout commitments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.evaluation.case_loader import SEALED_HOLDOUT_DISTRIBUTION
from scripts.create_sealed_holdout_manifest import create_manifest, main

ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_DATASET_PATH = ROOT / "data" / "evaluation" / "stage-7-development-v2.jsonl"


def _write_synthetic_holdout(path: Path) -> None:
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
                question=f"{payload['question']} [manifest synthetic {category.value} {index + 1}]",
            )
            payloads.append(payload)
    path.write_text(
        "".join(json.dumps(payload) + "\n" for payload in payloads),
        encoding="utf-8",
    )


def test_manifest_creation_exposes_only_commitment_metadata(tmp_path: Path) -> None:
    payload_path = tmp_path / "holdout.jsonl"
    attestation_path = tmp_path / "attestation.txt"
    _write_synthetic_holdout(payload_path)
    attestation_path.write_text("curated independently", encoding="utf-8")

    manifest = create_manifest(
        payload_path,
        dataset_version="stage-7-holdout-v2",
        created_at="2026-08-18T00:00:00Z",
        curator_attestation_path=attestation_path,
    )

    serialized = manifest.model_dump_json()
    assert manifest.case_count == 30
    assert manifest.independently_curated
    assert manifest.agent_unseen_before_freeze
    assert "question" not in serialized
    assert "expected_sql" not in serialized


def test_manifest_cli_requires_both_curator_confirmations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "manifest.json"

    assert (
        main(
            [
                "--dataset",
                str(tmp_path / "missing.jsonl"),
                "--dataset-version",
                "stage-7-holdout-v2",
                "--created-at",
                "2026-08-18T00:00:00Z",
                "--curator-attestation",
                str(tmp_path / "missing.txt"),
                "--output",
                str(output_path),
            ]
        )
        == 2
    )
    assert "both independent-curation attestations are required" in capsys.readouterr().out
    assert not output_path.exists()
