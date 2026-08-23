"""Typed configuration with environment overrides and safe defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RedditConfig(BaseModel):
    """Read-only Reddit collector settings."""

    mode: Literal["mock", "api"] = "mock"
    communities: list[str] = Field(default_factory=list)
    client_id: str | None = None
    client_secret: str | None = None
    user_agent: str | None = None

    def require_api_credentials(self) -> None:
        if self.mode == "api" and not all((self.client_id, self.client_secret, self.user_agent)):
            raise ValueError("Approved Reddit Data API credentials are required in API mode.")


class SignalWeights(BaseModel):
    source_quality: float = 0.18
    author_quality: float = 0.10
    sentiment_strength: float = 0.12
    discussion_velocity: float = 0.14
    event_importance: float = 0.12
    freshness: float = 0.10
    news_confirmation: float = 0.06
    price_confirmation: float = 0.05
    volume_confirmation: float = 0.05
    liquidity: float = 0.04
    manipulation_safety: float = 0.04

    @model_validator(mode="after")
    def validate_weights(self) -> SignalWeights:
        values = self.model_dump().values()
        if any(value < 0 for value in values):
            raise ValueError("Signal weights cannot be negative.")
        if sum(values) <= 0:
            raise ValueError("At least one signal weight must be positive.")
        return self


class AnalysisConfig(BaseModel):
    minimum_source_samples: int = Field(default=5, ge=1)
    source_score_half_life_days: float = Field(default=30, gt=0)
    recent_window_days: int = Field(default=30, ge=1)
    low_volume_baseline_floor: float = Field(default=0.25, gt=0)
    signal_weights: SignalWeights = Field(default_factory=SignalWeights)


class RiskConfig(BaseModel):
    research_capital_cad: float = Field(default=5000, gt=0)
    max_order_value_cad: float = Field(default=500, gt=0)
    max_position_value_cad: float = Field(default=1000, gt=0)
    max_total_exposure_cad: float = Field(default=3000, gt=0)
    max_open_positions: int = Field(default=5, ge=1)
    max_trades_per_day: int = Field(default=10, ge=1)
    max_daily_loss_cad: float = Field(default=100, gt=0)
    minimum_stock_price: float = Field(default=1, gt=0)
    minimum_market_cap: float = Field(default=50_000_000, ge=0)
    minimum_average_daily_volume: float = Field(default=100_000, ge=0)
    maximum_bid_ask_spread: float = Field(default=0.02, gt=0)
    maximum_price_age_seconds: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def limits_fit_research_capital(self) -> RiskConfig:
        if self.max_order_value_cad > self.research_capital_cad:
            raise ValueError("Maximum order value cannot exceed research capital.")
        if self.max_position_value_cad > self.research_capital_cad:
            raise ValueError("Maximum position value cannot exceed research capital.")
        if self.max_total_exposure_cad > self.research_capital_cad:
            raise ValueError("Maximum exposure cannot exceed research capital.")
        return self


class IbkrConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=7497, ge=1, le=65535)
    client_id: int = Field(default=1, ge=0)
    environment: str = "paper"
    live_trading_enabled: bool = False
    order_submission_enabled: bool = False

    @model_validator(mode="after")
    def enforce_paper_only(self) -> IbkrConfig:
        if self.environment != "paper" or self.live_trading_enabled:
            raise RuntimeError("Live trading is not supported by TraderResearch.")
        if self.port in {4001, 7496}:
            raise RuntimeError("Standard live-trading ports are not supported.")
        return self


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: Path = Field(default_factory=lambda: user_data_path("TraderResearch"))
    log_level: str = "INFO"
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    ibkr: IbkrConfig = Field(default_factory=IbkrConfig)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "traderresearch.sqlite3"


def _nested_set(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = target
    for part in path[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[path[-1]] = value


def _environment_overrides() -> dict[str, Any]:
    values: dict[str, Any] = {}
    mappings: dict[str, tuple[tuple[str, ...], Any]] = {
        "TRADERRESEARCH_DATA_DIR": (("data_dir",), Path),
        "REDDIT_CLIENT_ID": (("reddit", "client_id"), str),
        "REDDIT_CLIENT_SECRET": (("reddit", "client_secret"), str),
        "REDDIT_USER_AGENT": (("reddit", "user_agent"), str),
        "IBKR_HOST": (("ibkr", "host"), str),
        "IBKR_PORT": (("ibkr", "port"), int),
        "IBKR_CLIENT_ID": (("ibkr", "client_id"), int),
        "IBKR_ENVIRONMENT": (("ibkr", "environment"), str),
        "IBKR_LIVE_TRADING_ENABLED": (
            ("ibkr", "live_trading_enabled"),
            lambda value: value.lower() in {"1", "true", "yes"},
        ),
    }
    for name, (path, converter) in mappings.items():
        raw = os.environ.get(name)
        if raw is not None and raw != "":
            _nested_set(values, path, converter(raw))
    return values


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | None = None) -> AppConfig:
    """Load optional YAML and then apply explicit environment overrides."""

    document: dict[str, Any] = {}
    if path is not None:
        with path.expanduser().open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError("Configuration root must be a mapping.")
        document = loaded
    return AppConfig.model_validate(_deep_merge(document, _environment_overrides()))
