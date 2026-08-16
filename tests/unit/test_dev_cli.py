"""Tests for the cross-platform development command wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import dev


def test_run_command_forces_fake_provider_for_offline_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verification path must never inherit a live provider from ``.env``."""

    observed_environment: dict[str, str] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
        env: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[str]:
        del command, cwd, check
        assert env is not None
        observed_environment.update(env)
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr("scripts.dev.subprocess.run", fake_run)

    assert dev.run_command("lint", force_offline=True) == 0
    assert observed_environment["LLM_PROVIDER"] == "fake"
    assert observed_environment["LLM_MODEL"] == "fake-deterministic"
    assert observed_environment["LLM_API_KEY"] == ""


def test_run_command_preserves_environment_for_explicit_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit live-capable commands continue to use their configured provider."""

    observed_environment: list[object] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
        env: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[str]:
        del command, cwd, check
        observed_environment.append(env)
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr("scripts.dev.subprocess.run", fake_run)

    assert dev.run_command("gemini-smoke") == 0
    assert observed_environment == [None]
