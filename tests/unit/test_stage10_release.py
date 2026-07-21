"""Static Stage 10 documentation and release-evidence contracts."""

import json
from pathlib import Path

from scripts.evaluate_stage10 import main as evaluate_stage10

ROOT = Path(__file__).resolve().parents[2]


def test_release_documents_disclose_public_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    assert "fake-deterministic" in readme
    assert "not open-ended language generalization" in readme
    assert "Do not open a public issue" in security
    assert "no public platform or resource selected" in deployment
    assert "## Rollback" in deployment


def test_stage10_evaluator_records_local_and_external_state_separately() -> None:
    assert evaluate_stage10() == 0
    report = json.loads(
        (ROOT / "reports" / "evaluation" / "stage-10-readiness.json").read_text(encoding="utf-8")
    )
    assert report["local_release_gate_passed"] is True
    assert report["stage_gate_passed"] is False
    assert report["external_checks"]["project_license_selected"] is True
    remote = report["github_remote"]
    assert report["external_checks"]["github_remote_verified"] is (
        isinstance(remote, str) and "github.com" in remote.lower()
    )
    assert report["broken_local_links"] == []
