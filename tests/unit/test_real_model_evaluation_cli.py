"""CLI guards for the live real-model evaluator."""

from __future__ import annotations

import pytest

from scripts.evaluate_real_model import main


def test_real_evaluation_requires_explicit_live_confirmation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["run", "--split", "development", "--max-requests", "68"]) == 2
    assert "not run" in capsys.readouterr().out


def test_real_evaluation_rejects_burst_interval_before_loading_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "run",
                "--split",
                "development",
                "--max-requests",
                "68",
                "--request-interval-seconds",
                "0",
                "--confirm-live",
            ]
        )
        == 2
    )
    assert "at least 2 seconds" in capsys.readouterr().out


def test_holdout_requires_private_payload_before_loading_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "run",
                "--split",
                "holdout",
                "--max-requests",
                "1",
                "--confirm-live",
            ]
        )
        == 2
    )
    assert "--holdout-dataset is required" in capsys.readouterr().out


def test_real_evaluation_cli_rejects_unknown_comparison_policy() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--split",
                "development",
                "--max-requests",
                "68",
                "--comparison-policy",
                "loose",
            ]
        )


def test_real_evaluation_cli_validates_output_token_override() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--split",
                "development",
                "--max-requests",
                "68",
                "--max-output-tokens",
                "not-an-integer",
            ]
        )
