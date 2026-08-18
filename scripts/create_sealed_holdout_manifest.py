"""Create a public hash commitment for a privately supplied holdout payload."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from backend.evaluation.case_loader import (
    EvaluationDatasetError,
    load_evaluation_dataset,
    validate_sealed_holdout_manifest,
)
from backend.schemas.evaluation import EvaluationSplit, SealedHoldoutManifest


def create_manifest(
    dataset_path: Path,
    *,
    dataset_version: str,
    created_at: str,
    curator_attestation_path: Path,
) -> SealedHoldoutManifest:
    """Validate the sealed payload and return metadata that reveals no case content."""

    dataset = load_evaluation_dataset(
        dataset_path,
        expected_version=dataset_version,
        enforce_distribution=False,
    )
    if any(case.split is not EvaluationSplit.HOLDOUT for case in dataset.cases):
        raise EvaluationDatasetError("sealed payload contains a non-holdout case")
    attestation_sha256 = hashlib.sha256(curator_attestation_path.read_bytes()).hexdigest()
    counts = Counter(case.category for case in dataset.cases)
    manifest = SealedHoldoutManifest(
        manifest_version="stage-7-sealed-holdout-manifest-v1",
        dataset_version=dataset.version,
        dataset_sha256=dataset.sha256,
        case_count=len(dataset.cases),
        category_counts=dict(counts),
        created_at=created_at,
        curator_attestation_sha256=attestation_sha256,
        independently_curated=True,
        agent_unseen_before_freeze=True,
    )
    validate_sealed_holdout_manifest(manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--curator-attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-independent-curation", action="store_true")
    parser.add_argument("--confirm-agent-unseen", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if not args.confirm_independent_curation or not args.confirm_agent_unseen:
        print("Manifest not created: both independent-curation attestations are required.")
        return 2
    if args.output.exists() and not args.force:
        print("Manifest not created: output exists; use --force to replace intentionally.")
        return 2
    try:
        manifest = create_manifest(
            args.dataset,
            dataset_version=args.dataset_version,
            created_at=args.created_at,
            curator_attestation_path=args.curator_attestation,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (EvaluationDatasetError, OSError, ValueError) as exc:
        print(f"Manifest not created: {exc}")
        return 2
    print(
        f"Created sealed holdout manifest: version={manifest.dataset_version} "
        f"cases={manifest.case_count} sha256={manifest.dataset_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
