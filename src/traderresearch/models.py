"""Shared domain models.

Models deliberately exclude account identifiers and other unnecessary personal data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ContentType(StrEnum):
    POST = "post"
    COMMENT = "comment"


class SentimentLabel(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SignalDirection(StrEnum):
    LONG = "long"
    AVOID = "avoid"
    NEUTRAL = "neutral"


class SocialContent(BaseModel):
    """Permitted public content and derived research fields."""

    model_config = ConfigDict(extra="forbid")

    platform: str = "reddit"
    subreddit: str
    content_type: ContentType
    post_or_comment_id: str
    parent_id: str | None = None
    author_identifier: str
    created_utc: datetime
    title: str = ""
    body: str = ""
    score: int = 0
    num_comments: int = 0
    permalink: str = ""
    retrieved_at: datetime
    detected_tickers: list[str] = Field(default_factory=list)
    detected_companies: list[str] = Field(default_factory=list)
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    sentiment_label: SentimentLabel | None = None
    event_type: str | None = None
    event_strength: float | None = Field(default=None, ge=0, le=1)
    source_score: float | None = Field(default=None, ge=-100, le=100)
    signal_score: float | None = Field(default=None, ge=0, le=100)
    manipulation_score: float | None = Field(default=None, ge=0, le=1)
    manipulation_flags: list[str] = Field(default_factory=list)
    synthetic_outcomes: dict[str, dict[str, dict[str, float]]] = Field(default_factory=dict)

    @field_validator("created_utc", "retrieved_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("author_identifier")
    @classmethod
    def author_identifier_is_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("author_identifier cannot be empty")
        return value.strip()

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.title, self.body) if part).strip()


class SymbolRecord(BaseModel):
    ticker: str
    company_name: str
    exchange: str
    country: str
    currency: str
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = Field(default=None, ge=0)
    average_daily_volume: float | None = Field(default=None, ge=0)
    active: bool = True
    aliases: list[str] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def canonicalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class TickerMention(BaseModel):
    content_id: str
    ticker: str
    company_name: str
    matched_text: str
    extraction_method: Literal["cashtag", "ticker", "company"]
    confidence: float = Field(ge=0, le=1)
    created_utc: datetime


class SentimentResult(BaseModel):
    score: float = Field(ge=-1, le=1)
    label: SentimentLabel
    confidence: float = Field(ge=0, le=1)


class EventResult(BaseModel):
    event_type: str
    strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    new_information: bool = False
    primary_source_confirmed: bool = False


class DiscussionVelocity(BaseModel):
    current_mentions_5m: int = Field(ge=0)
    current_mentions_1h: int = Field(ge=0)
    historical_average_5m: float = Field(ge=0)
    historical_average_1h: float = Field(ge=0)
    mention_velocity: float = Field(ge=0)
    unique_authors: int = Field(ge=0)
    comment_velocity: float = Field(ge=0)
    score_velocity: float = Field(ge=0)


class ManipulationAssessment(BaseModel):
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)


class SignalFactors(BaseModel):
    source_quality: float = Field(default=0.5, ge=0, le=1)
    author_quality: float = Field(default=0.5, ge=0, le=1)
    sentiment_strength: float = Field(default=0, ge=0, le=1)
    discussion_velocity: float = Field(default=0, ge=0, le=1)
    event_importance: float = Field(default=0, ge=0, le=1)
    freshness: float = Field(default=0, ge=0, le=1)
    news_confirmation: float = Field(default=0, ge=0, le=1)
    price_confirmation: float = Field(default=0, ge=0, le=1)
    volume_confirmation: float = Field(default=0, ge=0, le=1)
    liquidity: float = Field(default=0.5, ge=0, le=1)
    manipulation_safety: float = Field(default=1, ge=0, le=1)


class ResearchSignal(BaseModel):
    signal_id: str
    content_id: str
    ticker: str
    source: str
    subreddit: str
    author_identifier: str
    sector: str | None = None
    event_type: str
    direction: SignalDirection
    sentiment_score: float = Field(ge=-1, le=1)
    source_score: float = Field(ge=-100, le=100)
    signal_score: float = Field(ge=0, le=100)
    manipulation_score: float = Field(ge=0, le=1)
    factors: SignalFactors
    content_created_time: datetime
    content_retrieved_time: datetime
    signal_generated_time: datetime
    reason: str

    @field_validator("content_created_time", "content_retrieved_time", "signal_generated_time")
    @classmethod
    def signal_times_are_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class MarketSnapshot(BaseModel):
    ticker: str
    price_observed_time: datetime
    last_price: float = Field(gt=0)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    volume: float = Field(ge=0)
    currency: str
    benchmark_ticker: str

    @property
    def relative_spread(self) -> float:
        midpoint = (self.bid + self.ask) / 2
        return (self.ask - self.bid) / midpoint if midpoint > 0 else float("inf")


class ForwardReturn(BaseModel):
    signal_id: str
    ticker: str
    horizon: str
    price_observed_time: datetime
    future_price_observed_time: datetime
    raw_return: float
    benchmark_adjusted_return: float
    benchmark_ticker: str


class PerformanceObservation(BaseModel):
    observed_at: datetime
    raw_return: float
    benchmark_adjusted_return: float
    predicted_direction: int = Field(ge=-1, le=1)
    lead_time_minutes: float = Field(ge=0)
    manipulation_score: float = Field(default=0, ge=0, le=1)


class PerformanceScore(BaseModel):
    key: str
    sample_count: int
    directional_hit_rate: float
    average_forward_return: float
    median_forward_return: float
    average_benchmark_adjusted_return: float
    volatility: float
    consistency: float
    statistical_confidence: float
    average_lead_time_minutes: float
    recent_score: float
    historical_score: float
    combined_score: float
    manipulation_risk: float
    sector: str | None = None
    event_type: str | None = None
    horizon: str = "1d"


class OrderSide(StrEnum):
    BUY = "BUY"


class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PaperOrderRequest(BaseModel):
    client_order_id: str
    signal_id: str
    ticker: str
    quantity: int = Field(gt=0)
    limit_price: float = Field(gt=0)
    currency: Literal["CAD", "USD"]
    exchange: str = "SMART"
    side: OrderSide = OrderSide.BUY
    security_type: Literal["STK"] = "STK"
    order_type: Literal["LMT"] = "LMT"


class PaperOrder(BaseModel):
    order_id: str
    request: PaperOrderRequest
    status: OrderStatus
    order_submitted_time: datetime | None = None
    filled_quantity: int = Field(default=0, ge=0)
    average_fill_price: float | None = Field(default=None, gt=0)
    rejection_reason: str | None = None


class PaperFill(BaseModel):
    fill_id: str
    order_id: str
    ticker: str
    quantity: int = Field(gt=0)
    fill_price: float = Field(gt=0)
    commission: float = Field(ge=0)
    fill_time: datetime


class PaperOrderEvent(BaseModel):
    """Broker callback data stripped of account identifiers."""

    order_id: str
    status: OrderStatus
    filled_quantity: float = Field(default=0, ge=0)
    remaining_quantity: float = Field(default=0, ge=0)
    average_fill_price: float | None = Field(default=None, ge=0)
    observed_at: datetime = Field(default_factory=utc_now)
    rejection_code: int | None = None


class Position(BaseModel):
    ticker: str
    quantity: float = Field(ge=0)
    average_cost: float = Field(ge=0)
    currency: str

    @property
    def value(self) -> float:
        return self.quantity * self.average_cost


class PortfolioState(BaseModel):
    connected: bool = False
    positions: list[Position] = Field(default_factory=list)
    open_orders: list[PaperOrder] = Field(default_factory=list)
    trades_today: int = Field(default=0, ge=0)
    daily_realized_pnl_cad: float = 0
    reported_exposure_cad: float | None = Field(default=None, ge=0)

    @property
    def total_exposure_cad(self) -> float | None:
        """Return safe CAD exposure or None when an FX conversion is required."""

        if self.reported_exposure_cad is not None:
            return self.reported_exposure_cad
        if not self.positions:
            return 0.0
        if all(position.currency == "CAD" for position in self.positions):
            return sum(position.value for position in self.positions)
        return None


class RiskCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class RiskDecision(BaseModel):
    approved: bool
    checks: list[RiskCheck]
    reason_for_rejection: str | None = None


class PaperAccountStatus(BaseModel):
    """Non-sensitive connectivity summary; financial values and account IDs are omitted."""

    connected: bool
    environment: Literal["paper"] = "paper"
    positions_count: int = Field(default=0, ge=0)
    open_orders_count: int = Field(default=0, ge=0)
    message: str
    observed_at: datetime = Field(default_factory=utc_now)


class DecisionAudit(BaseModel):
    """Serializable audit record without brokerage account data."""

    timestamp: datetime
    signal_id: str
    ticker: str
    source: str
    subreddit: str
    author_identifier: str
    event_type: str
    sentiment: float
    source_score: float
    signal_score: float
    market_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    risk_checks: list[dict[str, Any]] = Field(default_factory=list)
    decision: str
    order_id: str | None = None
    order_price: float | None = None
    fill_price: float | None = None
    quantity: int | None = None
    commission: float | None = None
    order_status: str | None = None
    reason_for_trade: str | None = None
    reason_for_rejection: str | None = None
