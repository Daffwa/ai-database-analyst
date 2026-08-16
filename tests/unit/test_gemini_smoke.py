"""Safety gate for the explicitly opt-in live Gemini smoke command."""

import pytest

from scripts.gemini_smoke import main


def test_live_gemini_smoke_requires_explicit_confirmation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 2
    assert "not run" in capsys.readouterr().out
