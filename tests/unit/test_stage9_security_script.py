"""Unit contracts for the Stage 9 security runner."""

from __future__ import annotations

import subprocess

import pytest

from scripts import run_stage9_security


def test_container_scan_uses_and_removes_a_docker_cache_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], int]] = []

    def fake_run(arguments: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
        calls.append((arguments, timeout))
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(run_stage9_security, "_run", fake_run)

    assert run_stage9_security._container_scan() is True

    volume_name = calls[0][0][-1]
    assert volume_name.startswith("ai-database-analyst-trivy-")
    assert calls[0] == (["docker", "volume", "create", volume_name], 30)
    assert calls[-1] == (["docker", "volume", "rm", "--force", volume_name], 30)
    trivy_runs = [
        arguments for arguments, _ in calls if run_stage9_security.TRIVY_IMAGE in arguments
    ]
    assert len(trivy_runs) == 3
    assert all(
        f"type=volume,source={volume_name},target=/root/.cache/trivy" in arguments
        for arguments in trivy_runs
    )
