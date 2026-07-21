"""Tests for structured logging and secret redaction."""

import json
import logging
from typing import Any

import pytest

from backend.core.logging import (
    REDACTED,
    JsonFormatter,
    configure_logging,
    ensure_logging_configured,
    get_logger,
    redact_text,
    sanitize_log_value,
)


def _record(message: str, **extra: Any) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.mark.parametrize(
    "value",
    [
        "Authorization: Bearer abc.def.ghi",
        "provider key sk-example123456789",
        "postgresql://user:password@database:5432/app",
    ],
)
def test_redact_text_removes_common_secret_shapes(value: str) -> None:
    redacted = redact_text(value)

    assert value != redacted
    assert REDACTED in redacted


def test_recursive_sanitization_redacts_sensitive_keys() -> None:
    value = {
        "request_id": "request-1",
        "nested": {
            "api_key": "do-not-log",
            "values": ["safe", "Bearer hidden-token"],
        },
    }

    sanitized = sanitize_log_value(value)

    assert sanitized == {
        "request_id": "request-1",
        "nested": {
            "api_key": REDACTED,
            "values": ["safe", REDACTED],
        },
    }


def test_sanitization_handles_primitives_and_unknown_objects() -> None:
    class DisplayValue:
        def __str__(self) -> str:
            return "Bearer object-secret"

    assert sanitize_log_value(None) is None
    assert sanitize_log_value(True) is True
    assert sanitize_log_value(5) == 5
    assert sanitize_log_value(("safe",)) == ["safe"]
    assert sanitize_log_value(DisplayValue()) == REDACTED


def test_json_formatter_emits_structured_sanitized_payload() -> None:
    record = _record(
        "Request accepted with Bearer secret-token",
        request_id="request-123",
        api_key="never-print-me",
        stage="validation",
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["message"] == f"Request accepted with {REDACTED}"
    assert payload["request_id"] == "request-123"
    assert payload["api_key"] == REDACTED
    assert payload["stage"] == "validation"
    assert payload["timestamp"].endswith("+00:00")


def test_json_formatter_records_exception_type_without_traceback() -> None:
    try:
        raise RuntimeError("internal sensitive detail")
    except RuntimeError:
        record = _record("Operation failed")
        record.exc_info = tuple(__import__("sys").exc_info())

    payload = json.loads(JsonFormatter().format(record))

    assert payload["exception_type"] == "RuntimeError"
    assert "internal sensitive detail" not in payload


def test_configure_logging_replaces_handlers_and_validates_level() -> None:
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    try:
        configured = configure_logging("warning")

        assert configured is root_logger
        assert configured.level == logging.WARNING
        assert len(configured.handlers) == 1
        assert isinstance(configured.handlers[0].formatter, JsonFormatter)

        with pytest.raises(ValueError, match="Unsupported log level"):
            configure_logging("not-a-level")
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)


def test_get_logger_has_no_implicit_global_configuration() -> None:
    assert get_logger("backend.test").name == "backend.test"


def test_ensure_logging_is_idempotent_and_preserves_host_handlers() -> None:
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    host_handler = logging.NullHandler()
    try:
        root_logger.handlers.clear()
        root_logger.addHandler(host_handler)
        root_logger.setLevel(logging.WARNING)

        first = ensure_logging_configured("INFO")
        second = ensure_logging_configured("INFO")

        assert first is second is root_logger
        assert host_handler in root_logger.handlers
        assert (
            sum(isinstance(handler.formatter, JsonFormatter) for handler in root_logger.handlers)
            == 1
        )
        assert root_logger.level == logging.INFO
        with pytest.raises(ValueError, match="Unsupported log level"):
            ensure_logging_configured("not-a-level")
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)
