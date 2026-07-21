"""Cross-platform development command wrapper.

Run with the Python interpreter from the project virtual environment, for
example: ``python scripts/dev.py verify``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMANDS: dict[str, list[str]] = {
    "format": [sys.executable, "-m", "ruff", "format", "."],
    "format-check": [sys.executable, "-m", "ruff", "format", "--check", "."],
    "lint": [sys.executable, "-m", "ruff", "check", "."],
    "type-check": [sys.executable, "-m", "mypy", "backend", "scripts", "tests"],
    "test-unit": [
        sys.executable,
        "-m",
        "pytest",
        "--no-cov",
        "tests/unit",
    ],
    "test-integration": [
        sys.executable,
        "-m",
        "pytest",
        "--no-cov",
        "tests/integration",
    ],
    "test-security": [
        sys.executable,
        "-m",
        "pytest",
        "--no-cov",
        "tests/security",
    ],
    "test-semantic": [
        sys.executable,
        "-m",
        "pytest",
        "--no-cov",
        "tests/semantic",
    ],
    "test-result": [
        sys.executable,
        "-m",
        "pytest",
        "--no-cov",
        "tests/result",
    ],
    "test-ui": [sys.executable, "-m", "pytest", "--no-cov", "tests/ui"],
    "test": [sys.executable, "-m", "pytest"],
    "data-setup": [sys.executable, "scripts/bootstrap_data.py"],
    "data-smoke": [sys.executable, "scripts/manual_query.py"],
    "stage3-smoke": [sys.executable, "scripts/stage3_smoke.py"],
    "evaluate-stage3": [sys.executable, "scripts/evaluate_stage3.py"],
    "stage4-smoke": [sys.executable, "scripts/stage4_smoke.py"],
    "evaluate-stage4": [sys.executable, "scripts/evaluate_stage4.py"],
    "semantic-validate": [sys.executable, "scripts/validate_semantic.py"],
    "stage5-smoke": [sys.executable, "scripts/stage5_smoke.py"],
    "evaluate-stage5": [sys.executable, "scripts/evaluate_stage5.py"],
    "stage6-smoke": [sys.executable, "scripts/stage6_smoke.py"],
    "evaluate-stage6": [sys.executable, "scripts/evaluate_stage6.py"],
    "evaluate-stage7": [sys.executable, "scripts/evaluate_stage7.py"],
    "evaluate-stage8": [sys.executable, "scripts/evaluate_stage8.py"],
    "test-postgres": [sys.executable, "scripts/run_stage8_integration.py"],
    "generate-compose-env": [sys.executable, "scripts/generate_compose_env.py"],
    "docker-smoke": [sys.executable, "-m", "scripts.run_stage9_compose"],
    "security-stage9": [sys.executable, "scripts/run_stage9_security.py"],
    "test-clean-checkout": [sys.executable, "scripts/run_stage9_clean_checkout.py"],
    "evaluate-stage9": [sys.executable, "scripts/evaluate_stage9.py"],
    "evaluate-stage10": [sys.executable, "scripts/evaluate_stage10.py"],
    "api": [sys.executable, "-m", "uvicorn", "backend.api.app:app", "--factory"],
    "ui-stage6": [sys.executable, "-m", "streamlit", "run", "frontend/streamlit_app.py"],
    "ui": [sys.executable, "-m", "streamlit", "run", "frontend/streamlit_api_app.py"],
}

VERIFY_SEQUENCE = (
    "format-check",
    "lint",
    "type-check",
    "semantic-validate",
    "evaluate-stage5",
    "evaluate-stage6",
    "evaluate-stage7",
    "evaluate-stage8",
    "evaluate-stage9",
    "evaluate-stage10",
    "test",
)


def run_command(name: str, extra_arguments: tuple[str, ...] = ()) -> int:
    """Run one named command from the repository root."""

    command = [*COMMANDS[name], *extra_arguments]
    print(f"[{name}] {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main() -> int:
    """Parse CLI input and run a command or the complete verification sequence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(*COMMANDS, "verify"))
    parser.add_argument("command_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    selected = VERIFY_SEQUENCE if args.command == "verify" else (args.command,)
    for name in selected:
        extra_arguments = tuple(args.command_args) if len(selected) == 1 else ()
        return_code = run_command(name, extra_arguments)
        if return_code != 0:
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
