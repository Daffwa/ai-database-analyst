"""Verify the CI quality matrix from a temporary committed clean checkout."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "test-results" / "stage-9-clean-checkout.json"
PYTHON_VERSIONS = ("3.11", "3.12")


def _run(
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def _source_paths() -> tuple[Path, ...]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    relative_paths = tuple(Path(value.decode("utf-8")) for value in listed.split(b"\0") if value)
    if not relative_paths:
        raise RuntimeError("No Git-trackable source files were found")
    return relative_paths


def _copy_source(destination: Path, paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(paths, key=lambda item: item.as_posix()):
        source = (ROOT / relative_path).resolve()
        source.relative_to(ROOT.resolve())
        if not source.is_file():
            raise RuntimeError("A Git-trackable source path is not a regular file")
        data = source.read_bytes()
        digest.update(relative_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return digest.hexdigest()


def _require_success(result: subprocess.CompletedProcess[str], stage: str) -> None:
    if result.returncode != 0:
        diagnostic = "\n".join((result.stdout, result.stderr)).strip()[-4_000:]
        if diagnostic:
            print(f"[{stage}] safe diagnostic tail:\n{diagnostic}")
        raise RuntimeError(f"{stage} failed with exit code {result.returncode}")


def _write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    checked_at = datetime.now(UTC).isoformat()
    report: dict[str, Any] = {
        "report_version": "stage-9-clean-checkout-v1",
        "checked_at": checked_at,
        "python_matrix": list(PYTHON_VERSIONS),
        "checkout_clean_before_verification": False,
        "stage_gate_passed": False,
        "blocker": None,
    }
    stage = "inventory_source"
    try:
        paths = _source_paths()
        report["source_file_count"] = len(paths)
        with tempfile.TemporaryDirectory(prefix="stage9-clean-checkout-") as temporary:
            temporary_root = Path(temporary)
            source_repository = temporary_root / "source"
            clean_checkout = temporary_root / "checkout"
            source_repository.mkdir()
            report["source_sha256"] = _copy_source(source_repository, paths)

            stage = "create_ephemeral_commit"
            _require_success(
                _run(
                    ["git", "init", "--initial-branch", "main"],
                    cwd=source_repository,
                ),
                stage,
            )
            _require_success(_run(["git", "add", "--all"], cwd=source_repository), stage)
            committed = _run(
                [
                    "git",
                    "-c",
                    "user.name=Stage 9 Gate",
                    "-c",
                    "user.email=stage9-gate@invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "--message",
                    "stage-9-clean-checkout-gate",
                ],
                cwd=source_repository,
            )
            _require_success(committed, stage)

            stage = "clone_ephemeral_commit"
            cloned = _run(
                ["git", "clone", "--local", str(source_repository), str(clean_checkout)],
                cwd=temporary_root,
            )
            _require_success(cloned, stage)
            status = _run(["git", "status", "--porcelain"], cwd=clean_checkout)
            _require_success(status, stage)
            if status.stdout.strip():
                raise RuntimeError("The temporary checkout is not clean")
            report["checkout_clean_before_verification"] = True
            revision = _run(["git", "rev-parse", "HEAD"], cwd=clean_checkout)
            _require_success(revision, stage)
            report["ephemeral_commit"] = revision.stdout.strip()

            results: dict[str, bool] = {}
            for version in PYTHON_VERSIONS:
                stage = f"python_{version}_sync"
                environment = os.environ.copy()
                environment["UV_PROJECT_ENVIRONMENT"] = str(
                    temporary_root / f"venv-{version.replace('.', '')}"
                )
                synchronized = _run(
                    ["uv", "sync", "--frozen", "--extra", "dev", "--python", version],
                    cwd=clean_checkout,
                    environment=environment,
                    timeout=900,
                )
                _require_success(synchronized, stage)
                stage = f"python_{version}_data_setup"
                bootstrapped = _run(
                    [
                        "uv",
                        "run",
                        "--frozen",
                        "--python",
                        version,
                        "python",
                        "scripts/dev.py",
                        "data-setup",
                    ],
                    cwd=clean_checkout,
                    environment=environment,
                    timeout=300,
                )
                _require_success(bootstrapped, stage)
                stage = f"python_{version}_verify"
                verified = _run(
                    [
                        "uv",
                        "run",
                        "--frozen",
                        "--python",
                        version,
                        "python",
                        "scripts/dev.py",
                        "verify",
                    ],
                    cwd=clean_checkout,
                    environment=environment,
                    timeout=900,
                )
                _require_success(verified, stage)
                results[version] = True
            report["python_results"] = results
            report["stage_gate_passed"] = all(results.values())
    except (OSError, RuntimeError, subprocess.SubprocessError, UnicodeError) as exc:
        report["blocker"] = f"Clean-checkout gate failed during {stage}: {type(exc).__name__}"
    _write_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["stage_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
