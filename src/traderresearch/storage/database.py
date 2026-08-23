"""Database engine and schema.

SQLAlchemy keeps analysis code independent from SQLite and permits a later
PostgreSQL URL without changing domain services.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class SocialContentRow(Base):
    __tablename__ = "social_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    subreddit: Mapped[str] = mapped_column(String(128), index=True)
    content_type: Mapped[str] = mapped_column(String(16))
    post_or_comment_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author_identifier: Mapped[str] = mapped_column(String(256), index=True)
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    num_comments: Mapped[int] = mapped_column(Integer, default=0)
    permalink: Mapped[str] = mapped_column(Text, default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_tickers_json: Mapped[str] = mapped_column(Text, default="[]")
    detected_companies_json: Mapped[str] = mapped_column(Text, default="[]")
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    manipulation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    manipulation_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    synthetic_outcomes_json: Mapped[str] = mapped_column(Text, default="{}")


class TickerMentionRow(Base):
    __tablename__ = "ticker_mentions"
    __table_args__ = (UniqueConstraint("content_id", "ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(
        ForeignKey("social_content.post_or_comment_id"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    company_name: Mapped[str] = mapped_column(String(256))
    matched_text: Mapped[str] = mapped_column(String(256))
    extraction_method: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SourceRow(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("platform", "channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(128))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthorRow(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_identifier: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SignalRow(Base):
    __tablename__ = "signals"

    signal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    content_id: Mapped[str] = mapped_column(
        ForeignKey("social_content.post_or_comment_id"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    source: Mapped[str] = mapped_column(String(32))
    subreddit: Mapped[str] = mapped_column(String(128), index=True)
    author_identifier: Mapped[str] = mapped_column(String(256), index=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    sentiment_score: Mapped[float] = mapped_column(Float)
    source_score: Mapped[float] = mapped_column(Float)
    signal_score: Mapped[float] = mapped_column(Float, index=True)
    manipulation_score: Mapped[float] = mapped_column(Float)
    factors_json: Mapped[str] = mapped_column(Text)
    content_created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_retrieved_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_generated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)


class MarketSnapshotRow(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (UniqueConstraint("ticker", "price_observed_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    price_observed_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_price: Mapped[float] = mapped_column(Float)
    bid: Mapped[float] = mapped_column(Float)
    ask: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    benchmark_ticker: Mapped[str] = mapped_column(String(24))


class ForwardReturnRow(Base):
    __tablename__ = "forward_returns"
    __table_args__ = (UniqueConstraint("signal_id", "horizon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.signal_id"), index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    horizon: Mapped[str] = mapped_column(String(16), index=True)
    price_observed_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    future_price_observed_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_return: Mapped[float] = mapped_column(Float)
    benchmark_adjusted_return: Mapped[float] = mapped_column(Float)
    benchmark_ticker: Mapped[str] = mapped_column(String(24))


class PaperOrderRow(Base):
    __tablename__ = "paper_orders"

    order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    signal_id: Mapped[str] = mapped_column(String(128), index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32), index=True)
    order_submitted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaperFillRow(Base):
    __tablename__ = "paper_fills"

    fill_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("paper_orders.order_id"), index=True)
    ticker: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[int] = mapped_column(Integer)
    fill_price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float)
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourcePerformanceRow(Base):
    __tablename__ = "source_performance"
    __table_args__ = (UniqueConstraint("key", "sector", "event_type", "horizon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(256), index=True)
    sector: Mapped[str] = mapped_column(String(128), default="*")
    event_type: Mapped[str] = mapped_column(String(64), default="*")
    horizon: Mapped[str] = mapped_column(String(16), default="1d")
    metrics_json: Mapped[str] = mapped_column(Text)
    combined_score: Mapped[float] = mapped_column(Float, index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthorPerformanceRow(Base):
    __tablename__ = "author_performance"
    __table_args__ = (UniqueConstraint("author_identifier", "sector", "event_type", "horizon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    author_identifier: Mapped[str] = mapped_column(String(256), index=True)
    sector: Mapped[str] = mapped_column(String(128), default="*")
    event_type: Mapped[str] = mapped_column(String(64), default="*")
    horizon: Mapped[str] = mapped_column(String(16), default="1d")
    metrics_json: Mapped[str] = mapped_column(Text)
    combined_score: Mapped[float] = mapped_column(Float, index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StrategyRunRow(Base):
    __tablename__ = "strategy_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dataset_partition: Mapped[str] = mapped_column(String(32))
    configuration_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))


class SymbolRow(Base):
    __tablename__ = "symbols"

    ticker: Mapped[str] = mapped_column(String(24), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(256))
    exchange: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(8))
    currency: Mapped[str] = mapped_column(String(8))
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_daily_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")


class Database:
    """Own the SQLAlchemy engine and session factory."""

    def __init__(self, url: str) -> None:
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(url, future=True, connect_args=connect_args)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._configure_sqlite)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    @classmethod
    def from_sqlite_path(cls, path: Path) -> Database:
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path}")

    @staticmethod
    def _configure_sqlite(dbapi_connection: Any, connection_record: Any) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    def initialize_schema(self) -> None:
        Base.metadata.create_all(self.engine)
