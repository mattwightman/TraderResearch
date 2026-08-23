from __future__ import annotations

import io
import json
import logging

from traderresearch.logging_config import JsonFormatter


def test_structured_logging_redacts_nested_and_message_values() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("traderresearch.test.privacy")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    sensitive_value = "not-a-real-" + "secret"
    author = "research_user_" + "private"
    private_path = "/" + "home" + "/YOUR_USERNAME/project/config.yaml"
    private_ip = ".".join(("192", "168", "1", "10"))
    logger.info(
        "password=%s path=%s address=%s",
        sensitive_value,
        private_path,
        private_ip,
        extra={
            "author_identifier": author,
            "nested": {"auth_token": sensitive_value, "safe_value": "synthetic"},
        },
    )

    payload = json.loads(stream.getvalue())
    serialized = json.dumps(payload)
    assert sensitive_value not in serialized
    assert author not in serialized
    assert private_path not in serialized
    assert private_ip not in serialized
    assert payload["author_identifier"] == "[REDACTED]"
    assert payload["nested"]["auth_token"] == "[REDACTED]"
    assert payload["nested"]["safe_value"] == "synthetic"
    assert "[PRIVATE_PATH]" in payload["message"]
    assert "[REDACTED_IP]" in payload["message"]


def test_structured_logging_redacts_exception_paths() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("traderresearch.test.exception_privacy")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    private_path = "/" + "Users" + "/YOUR_USERNAME/private.txt"

    try:
        raise ValueError(f"Unable to read {private_path}")
    except ValueError:
        logger.exception("Synthetic read failure")

    payload = json.loads(stream.getvalue())
    assert private_path not in payload["exception"]
    assert "[PRIVATE_PATH]" in payload["exception"]
