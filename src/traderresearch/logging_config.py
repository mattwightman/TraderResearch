"""Structured, credential-safe logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_SENSITIVE_FRAGMENTS = (
    "account",
    "authorization",
    "balance",
    "client_secret",
    "credential",
    "password",
    "secret",
    "token",
)


def _safe_extra(record: logging.LogRecord) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED:
            continue
        if any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS):
            values[key] = "[REDACTED]"
        else:
            values[key] = value
    return values


class JsonFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **_safe_extra(record),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger for structured console output."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
