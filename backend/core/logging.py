"""Structured JSON logging with conservative secret redaction."""

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|credential|database[_-]?url|password|secret|token)",
    re.IGNORECASE,
)
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b(?:postgres(?:ql)?|mysql)://[^\s:@/]+:[^\s@/]+@", re.IGNORECASE),
)
_RESERVED_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


def redact_text(value: str) -> str:
    """Redact common credential shapes from unstructured text."""

    redacted = value
    for pattern in _SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def sanitize_log_value(value: Any, *, key: str | None = None) -> Any:
    """Recursively sanitize values before JSON serialization."""

    if key and _SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_log_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_log_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))


class JsonFormatter(logging.Formatter):
    """Format a log record as one sanitized JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = sanitize_log_value(value, key=key)

        if record.exc_info:
            exception_type = record.exc_info[0]
            payload["exception_type"] = (
                exception_type.__name__ if exception_type is not None else "Exception"
            )

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure the process root logger with exactly one JSON stream handler."""

    normalized_level = level.upper()
    if normalized_level not in logging.getLevelNamesMapping():
        msg = f"Unsupported log level: {level}"
        raise ValueError(msg)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(normalized_level)
    logging.captureWarnings(True)
    return root_logger


def ensure_logging_configured(level: str = "INFO") -> logging.Logger:
    """Add structured logging once without removing host-owned handlers."""

    normalized_level = level.upper()
    level_mapping = logging.getLevelNamesMapping()
    if normalized_level not in level_mapping:
        msg = f"Unsupported log level: {level}"
        raise ValueError(msg)

    root_logger = logging.getLogger()
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in root_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)

    requested_level = level_mapping[normalized_level]
    if root_logger.level == logging.NOTSET or root_logger.level > requested_level:
        root_logger.setLevel(requested_level)
    logging.captureWarnings(True)
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Return a named logger without configuring global logging implicitly."""

    return logging.getLogger(name)
