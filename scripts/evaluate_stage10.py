"""Evaluate local release readiness and separate external release decisions."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from scripts.dev import COMMANDS

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "evaluation" / "stage-10-readiness.json"
EXTERNAL_EVIDENCE_PATH = ROOT / "reports" / "evaluation" / "stage-10-external-evidence.json"
REQUIRED_HOSTED_WORKFLOWS = ("CI", "Docker", "Security", "Evaluation")
REQUIRED_DEPLOYMENT_CONTROLS = (
    "authentication",
    "authorization",
    "https",
    "managed_postgresql",
    "managed_secrets",
    "monitoring",
    "rate_limiting",
    "rollback_tested",
    "smoke_tests",
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
DEV_COMMAND = re.compile(r"(?:uv run )?python scripts/dev\.py ([a-z0-9-]+)")


def _json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _markdown_paths() -> tuple[Path, ...]:
    return (ROOT / "README.md", ROOT / "SECURITY.md", *(ROOT / "docs").glob("*.md"))


def _broken_local_links() -> tuple[str, ...]:
    broken: list[str] = []
    for document in _markdown_paths():
        source = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(source):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{document.relative_to(ROOT)} -> {raw_target}")
    return tuple(sorted(broken))


def _jpeg_dimensions(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    offset = 2
    start_of_frame = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 8 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            return None
        if marker in start_of_frame and segment_length >= 7:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += segment_length
    return None


def _github_remote() -> str | None:
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _repository_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith("https://github.com/"):
        return None
    return value.removesuffix(".git").rstrip("/")


def _hosted_actions_verified(evidence: dict[str, object]) -> bool:
    repository = _mapping(evidence.get("repository"))
    repository_url = _repository_url(repository.get("url"))
    hosted = _mapping(evidence.get("hosted_actions"))
    verified_commit = hosted.get("verified_commit")
    workflows = _mapping(hosted.get("required_workflows"))
    if (
        repository_url is None
        or str(repository.get("visibility", "")).lower() != "public"
        or not isinstance(verified_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", verified_commit) is None
    ):
        return False
    for workflow_name in REQUIRED_HOSTED_WORKFLOWS:
        run = _mapping(workflows.get(workflow_name))
        run_id = run.get("run_id")
        if (
            not isinstance(run_id, int)
            or run_id <= 0
            or run.get("head_sha") != verified_commit
            or run.get("conclusion") != "success"
            or run.get("url") != f"{repository_url}/actions/runs/{run_id}"
        ):
            return False
    return True


def _public_deployment_verified(evidence: dict[str, object]) -> bool:
    deployment = _mapping(evidence.get("public_deployment"))
    controls = _mapping(deployment.get("controls"))
    public_url = deployment.get("public_url")
    return (
        deployment.get("performed") is True
        and isinstance(public_url, str)
        and public_url.startswith("https://")
        and all(controls.get(control) is True for control in REQUIRED_DEPLOYMENT_CONTROLS)
    )


def main() -> int:
    required_documents = (
        ROOT / "README.md",
        ROOT / "LICENSE",
        ROOT / "SECURITY.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "api.md",
        ROOT / "docs" / "data-source.md",
        ROOT / "docs" / "deployment.md",
        ROOT / "docs" / "demo-script.md",
        ROOT / "docs" / "evaluation.md",
        ROOT / "docs" / "operations.md",
        ROOT / "docs" / "security.md",
        ROOT / "docs" / "threat-model.md",
        ROOT / "reports" / "test-results" / "stage-10-summary.md",
    )
    screenshots = (
        ROOT / "reports" / "screenshots" / "stage-9-ui-result.jpg",
        ROOT / "reports" / "screenshots" / "stage-9-ui-details.jpg",
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documented_commands = set(DEV_COMMAND.findall(readme))
    supported_commands = {*COMMANDS, "verify"}
    unknown_commands = tuple(sorted(documented_commands - supported_commands))
    broken_links = _broken_local_links()
    screenshot_dimensions = {path.name: _jpeg_dimensions(path) for path in screenshots}
    stage7 = _json(ROOT / "reports" / "evaluation" / "stage-7-baseline.json")
    stage8 = _json(ROOT / "reports" / "evaluation" / "stage-8-readiness.json")
    stage9 = _json(ROOT / "reports" / "evaluation" / "stage-9-readiness.json")
    compose = _json(ROOT / "reports" / "test-results" / "stage-9-compose.json")
    security = _json(ROOT / "reports" / "security" / "stage-9-security.json")
    clean_checkout = _json(ROOT / "reports" / "test-results" / "stage-9-clean-checkout.json")
    local_checks = {
        "required_release_documents_present": all(
            path.exists() and path.stat().st_size > 200 for path in required_documents
        ),
        "readme_commands_are_supported": not unknown_commands,
        "local_markdown_links_resolve": not broken_links,
        "reviewed_screenshots_present": all(
            dimensions is not None and dimensions[0] >= 1200 and dimensions[1] >= 700
            for dimensions in screenshot_dimensions.values()
        ),
        "fake_provider_limitation_disclosed": "fake-deterministic" in readme
        and "not open-ended language generalization" in readme,
        "dataset_source_and_license_documented": "v1.4.5"
        in (ROOT / "docs" / "data-source.md").read_text(encoding="utf-8")
        and "MIT" in (ROOT / "docs" / "data-source.md").read_text(encoding="utf-8"),
        "stage7_evaluation_preserved": stage7.get("gate_passed") is True,
        "stage8_gate_preserved": stage8.get("stage_gate_passed") is True,
        "stage9_gate_preserved": stage9.get("stage_gate_passed") is True,
        "compose_gate_verified": compose.get("stage_gate_passed") is True,
        "security_gate_verified": security.get("stage_gate_passed") is True,
        "clean_checkout_gate_verified": clean_checkout.get("stage_gate_passed") is True,
    }
    local_release_gate_passed = all(local_checks.values())
    remote = _github_remote()
    external_evidence = _json(EXTERNAL_EVIDENCE_PATH)
    hosted_actions_verified = _hosted_actions_verified(external_evidence)
    public_deployment_performed = _public_deployment_verified(external_evidence)
    external_checks = {
        "project_license_selected": (ROOT / "LICENSE").exists(),
        "github_remote_verified": remote is not None and "github.com" in remote.lower(),
        "hosted_actions_verified": hosted_actions_verified,
        "public_deployment_performed": public_deployment_performed,
    }
    stage_gate_passed = (
        local_release_gate_passed
        and external_checks["project_license_selected"]
        and external_checks["github_remote_verified"]
        and external_checks["hosted_actions_verified"]
    )
    report = {
        "report_version": "stage-10-readiness-v2",
        "checked_at": datetime.now(UTC).isoformat(),
        "local_checks": local_checks,
        "local_release_gate_passed": local_release_gate_passed,
        "external_checks": external_checks,
        "github_remote": remote,
        "external_evidence_path": EXTERNAL_EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "hosted_actions_evidence": _mapping(external_evidence.get("hosted_actions")),
        "public_deployment_evidence": _mapping(external_evidence.get("public_deployment")),
        "deployment_required_for_local_gate": False,
        "deployment_required_for_stage_gate": False,
        "unknown_readme_commands": unknown_commands,
        "broken_local_links": broken_links,
        "screenshot_dimensions": screenshot_dimensions,
        "stage_gate_passed": stage_gate_passed,
        "blockers": [
            message
            for blocked, message in (
                (
                    not external_checks["project_license_selected"],
                    "Select the project license.",
                ),
                (
                    not external_checks["github_remote_verified"],
                    "Authorize and verify the GitHub owner, visibility, and remote.",
                ),
                (
                    not external_checks["hosted_actions_verified"],
                    "Verify the required hosted GitHub Actions runs.",
                ),
            )
            if blocked
        ],
        "remaining_external_actions": [
            "Select and verify a public deployment platform, authentication, HTTPS, "
            "rate limiting, managed secrets/PostgreSQL, monitoring, smoke tests, and rollback."
        ]
        if not public_deployment_performed
        else [],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if local_release_gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
