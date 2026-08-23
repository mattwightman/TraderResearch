from __future__ import annotations

from pathlib import Path

import pytest

from traderresearch.config import load_config


def test_mock_configuration_does_not_require_reddit_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRADERRESEARCH_DATA_DIR", str(tmp_path / "runtime"))
    config = load_config()
    assert config.reddit.mode == "mock"
    assert config.reddit.client_id is None
    assert config.database_path.parent == tmp_path / "runtime"


def test_yaml_loading_and_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "analysis:\n  minimum_source_samples: 12\nibkr:\n  client_id: 8\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IBKR_CLIENT_ID", "9")
    config = load_config(path)
    assert config.analysis.minimum_source_samples == 12
    assert config.ibkr.client_id == 9


def test_live_environment_configuration_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("ibkr:\n  environment: live\n", encoding="utf-8")
    monkeypatch.delenv("IBKR_ENVIRONMENT", raising=False)
    with pytest.raises((RuntimeError, ValueError), match=r"paper|Live"):
        load_config(path)


def test_sensitive_configuration_values_are_masked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id = "placeholder-" + "client-id"
    credential_value = "placeholder-" + "client-secret"
    monkeypatch.setenv("REDDIT_CLIENT_ID", client_id)
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", credential_value)
    monkeypatch.setenv("REDDIT_USER_AGENT", "TraderResearch/public-safe-test")

    config = load_config()

    assert config.reddit.client_id is not None
    assert config.reddit.client_id.get_secret_value() == client_id
    assert client_id not in repr(config)
    assert credential_value not in repr(config)
