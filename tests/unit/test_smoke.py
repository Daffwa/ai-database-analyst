"""Import and package metadata smoke tests."""

from backend import __version__
from backend.core import AppError, AppSettings, ErrorCode


def test_package_imports_and_version() -> None:
    assert __version__ == "0.1.0"
    assert AppSettings().llm_provider == "fake"
    assert issubclass(AppError, Exception)
    assert ErrorCode.INVALID_REQUEST == "INVALID_REQUEST"
