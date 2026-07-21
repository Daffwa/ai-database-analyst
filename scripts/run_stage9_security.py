"""Run dependency, SAST, secret, SQL, and container security gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "security" / "stage-9-security.json"
GITLEAKS_IMAGE = (
    "ghcr.io/gitleaks/gitleaks:v8.30.1@"
    "sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
)
TRIVY_IMAGE = (
    "aquasec/trivy:0.70.0@sha256:be1190afcb28352bfddc4ddeb71470835d16462af68d310f9f4bca710961a41e"
)
APPLICATION_IMAGES = (
    "ai-database-analyst-api:local",
    "ai-database-analyst-frontend:local",
)


def _run(arguments: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def _write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _dependency_audit(temp_directory: Path) -> bool:
    requirements = temp_directory / "runtime-requirements.txt"
    exported = _run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-hashes",
            "--no-emit-project",
            "--output-file",
            str(requirements),
        ]
    )
    if exported.returncode != 0:
        return False
    audited = _run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--requirement",
            str(requirements),
            "--progress-spinner",
            "off",
        ],
        timeout=600,
    )
    return audited.returncode == 0


def _sast(temp_directory: Path) -> bool:
    output = temp_directory / "bandit.json"
    scanned = _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            "backend",
            "frontend",
            "scripts",
            "-ll",
            "-ii",
            "-f",
            "json",
            "-o",
            str(output),
            "-q",
        ]
    )
    return scanned.returncode == 0


def _secret_scan() -> bool:
    scanned = _run(
        [
            "docker",
            "run",
            "--rm",
            "--mount",
            f"type=bind,source={ROOT},target=/repo,readonly",
            GITLEAKS_IMAGE,
            "dir",
            "/repo",
            "--config",
            "/repo/.gitleaks.toml",
            "--no-banner",
            "--redact",
        ],
        timeout=600,
    )
    return scanned.returncode == 0


def _sql_security_tests() -> bool:
    tested = _run(
        [sys.executable, "-m", "pytest", "--no-cov", "tests/security"],
        timeout=300,
    )
    return tested.returncode == 0


def _container_scan() -> bool:
    # A bind-mounted cache becomes root-owned when Trivy runs in its container,
    # which prevents GitHub's non-root runner from cleaning its temp directory.
    # A uniquely named Docker volume keeps the shared cache inside Docker and is
    # removed explicitly regardless of the scan result.
    cache_volume = f"ai-database-analyst-trivy-{uuid.uuid4().hex}"
    created = _run(["docker", "volume", "create", cache_volume], timeout=30)
    if created.returncode != 0:
        return False
    cache_mount = f"type=volume,source={cache_volume},target=/root/.cache/trivy"
    try:
        for application_image in APPLICATION_IMAGES:
            exists = _run(["docker", "image", "inspect", application_image], timeout=30)
            if exists.returncode != 0:
                return False
            scanned = _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--mount",
                    "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
                    "--mount",
                    cache_mount,
                    TRIVY_IMAGE,
                    "image",
                    "--scanners",
                    "vuln,secret",
                    "--ignore-unfixed",
                    "--severity",
                    "HIGH,CRITICAL",
                    "--exit-code",
                    "1",
                    "--no-progress",
                    "--skip-version-check",
                    application_image,
                ],
                timeout=900,
            )
            if scanned.returncode != 0:
                return False
        config_scan = _run(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,source={ROOT},target=/repo,readonly",
                "--mount",
                cache_mount,
                TRIVY_IMAGE,
                "config",
                "--severity",
                "HIGH,CRITICAL",
                "--exit-code",
                "1",
                "--skip-version-check",
                "/repo",
            ],
            timeout=600,
        )
        return config_scan.returncode == 0
    finally:
        _run(["docker", "volume", "rm", "--force", cache_volume], timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-containers",
        action="store_true",
        help="Run source gates only; the complete Stage 9 gate requires images",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="stage9-security-") as temp:
        temp_directory = Path(temp)
        checks = {
            "dependency_audit_passed": _dependency_audit(temp_directory),
            "sast_passed": _sast(temp_directory),
            "secret_scan_passed": _secret_scan(),
            "sql_security_tests_passed": _sql_security_tests(),
            "container_scan_passed": (None if args.skip_containers else _container_scan()),
        }
    executed_checks_passed = all(value is True for value in checks.values() if value is not None)
    complete_gate_passed = executed_checks_passed and checks["container_scan_passed"] is True
    report = {
        "report_version": "stage-9-security-v1",
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "gitleaks_image": GITLEAKS_IMAGE,
        "trivy_image": TRIVY_IMAGE,
        "stage_gate_passed": complete_gate_passed,
        "executed_checks_passed": executed_checks_passed,
        "sensitive_findings_in_report": False,
    }
    _write_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if executed_checks_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
