"""Structured, credential-safe logging configuration."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
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
_SENSITIVE_KEYS = frozenset(
    {
        "author_identifier",
        "data_dir",
        "email",
        "host",
        "hostname",
        "reddit_user_agent",
        "user_name",
        "username",
    }
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|client_secret|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|auth(?:entication|orization)?[_-]?token)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_AUTHORIZATION = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_VENDOR_TOKEN = re.compile(
    r"\b(?:AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|"
    r"gh[pousr]_[0-9A-Za-z]{16,}|github_pat_[0-9A-Za-z_]{20,}|"
    r"sk-(?:proj-)?[0-9A-Za-z_-]{16,}|xox[baprs]-[0-9A-Za-z-]{10,})\b"
)
_EMBEDDED_URL_CREDENTIALS = re.compile(r"(?i)\b(https?|postgres(?:ql)?|mysql)://[^/@\s]+:[^/@\s]+@")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PRIVATE_UNIX_PATH = re.compile(r"/(?:" "home|Users" r")/[^\s\"'<>]+")
_PRIVATE_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\s\"'<>]+")
_PRIVATE_IP = re.compile(
    r"\b(?:10(?:\.[0-9]{1,3}){3}|192\.168(?:\.[0-9]{1,3}){2}|"
    r"172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2})\b"
)
_BROKERAGE_ACCOUNT = re.compile(r"\b(?:DU|U)[0-9]{5,}\b")


def redact_sensitive_text(value: str) -> str:
    """Remove common credentials and personal identifiers from output text."""

    home = str(Path.home())
    if len(home) > 1:
        value = value.replace(home, "[PRIVATE_PATH]")
    value = _PRIVATE_UNIX_PATH.sub("[PRIVATE_PATH]", value)
    value = _PRIVATE_WINDOWS_PATH.sub("[PRIVATE_PATH]", value)
    value = _EMBEDDED_URL_CREDENTIALS.sub(r"\1://[REDACTED]@", value)
    value = _AUTHORIZATION.sub(r"\1 [REDACTED]", value)
    value = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", value)
    value = _VENDOR_TOKEN.sub("[REDACTED]", value)
    value = _EMAIL.sub("[REDACTED_EMAIL]", value)
    value = _PRIVATE_IP.sub("[REDACTED_IP]", value)
    return _BROKERAGE_ACCOUNT.sub("[REDACTED_ACCOUNT]", value)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return lowered in _SENSITIVE_KEYS or any(
        fragment in lowered for fragment in _SENSITIVE_FRAGMENTS
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Path):
        return redact_sensitive_text(str(value))
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return redact_sensitive_text(str(value))


def _safe_extra(record: logging.LogRecord) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED:
            continue
        if _is_sensitive_key(key):
            values[key] = "[REDACTED]"
        else:
            values[key] = _sanitize(value)
    return values


class JsonFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
            **_safe_extra(record),
        }
        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(_sanitize(payload), separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger for structured console output."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
