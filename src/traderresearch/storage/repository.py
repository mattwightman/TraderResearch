"""Repository operations for research and paper-trading records."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from traderresearch.models import (
    ContentType,
    ForwardReturn,
    OrderStatus,
    PaperFill,
    PaperOrder,
    PaperOrderRequest,
    PerformanceScore,
    ResearchSignal,
    SentimentLabel,
    SignalDirection,
    SocialContent,
    SymbolRecord,
    TickerMention,
    ensure_utc,
)
from traderresearch.storage.database import (
    AuthorPerformanceRow,
    AuthorRow,
    Database,
    ForwardReturnRow,
    PaperFillRow,
    PaperOrderRow,
    SignalRow,
    SocialContentRow,
    SourcePerformanceRow,
    SourceRow,
    SymbolRow,
    TickerMentionRow,
)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), default=str, sort_keys=True)


class ResearchRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def ingest_content(self, content: Iterable[SocialContent]) -> int:
        inserted = 0
        with self._database.session_factory.begin() as session:
            for item in content:
                existing = session.scalar(
                    select(SocialContentRow.id).where(
                        SocialContentRow.post_or_comment_id == item.post_or_comment_id
                    )
                )
                if existing is not None:
                    continue
                session.add(
                    SocialContentRow(
                        platform=item.platform,
                        subreddit=item.subreddit,
                        content_type=item.content_type.value,
                        post_or_comment_id=item.post_or_comment_id,
                        parent_id=item.parent_id,
                        author_identifier=item.author_identifier,
                        created_utc=item.created_utc,
                        title=item.title,
                        body=item.body,
                        score=item.score,
                        num_comments=item.num_comments,
                        permalink=item.permalink,
                        retrieved_at=item.retrieved_at,
                        detected_tickers_json=_json(item.detected_tickers),
                        detected_companies_json=_json(item.detected_companies),
                        sentiment_score=item.sentiment_score,
                        sentiment_label=(
                            item.sentiment_label.value if item.sentiment_label else None
                        ),
                        event_type=item.event_type,
                        event_strength=item.event_strength,
                        source_score=item.source_score,
                        signal_score=item.signal_score,
                        manipulation_score=item.manipulation_score,
                        manipulation_flags_json=_json(item.manipulation_flags),
                        synthetic_outcomes_json=_json(item.synthetic_outcomes),
                    )
                )
                self._touch_source_and_author(session, item)
                inserted += 1
        return inserted

    @staticmethod
    def _touch_source_and_author(session: Session, item: SocialContent) -> None:
        source = session.scalar(
            select(SourceRow).where(
                SourceRow.platform == item.platform,
                SourceRow.channel == item.subreddit,
            )
        )
        if source is None:
            session.add(
                SourceRow(
                    platform=item.platform,
                    channel=item.subreddit,
                    first_seen=item.created_utc,
                    last_seen=item.created_utc,
                )
            )
        else:
            source.first_seen = min(ensure_utc(source.first_seen), item.created_utc)
            source.last_seen = max(ensure_utc(source.last_seen), item.created_utc)
        author = session.scalar(
            select(AuthorRow).where(AuthorRow.author_identifier == item.author_identifier)
        )
        if author is None:
            session.add(
                AuthorRow(
                    author_identifier=item.author_identifier,
                    first_seen=item.created_utc,
                    last_seen=item.created_utc,
                )
            )
        else:
            author.first_seen = min(ensure_utc(author.first_seen), item.created_utc)
            author.last_seen = max(ensure_utc(author.last_seen), item.created_utc)

    def list_content(self) -> list[SocialContent]:
        with self._database.session_factory() as session:
            rows = session.scalars(
                select(SocialContentRow).order_by(SocialContentRow.created_utc)
            ).all()
        return [self._content_from_row(row) for row in rows]

    @staticmethod
    def _content_from_row(row: SocialContentRow) -> SocialContent:
        return SocialContent(
            platform=row.platform,
            subreddit=row.subreddit,
            content_type=ContentType(row.content_type),
            post_or_comment_id=row.post_or_comment_id,
            parent_id=row.parent_id,
            author_identifier=row.author_identifier,
            created_utc=row.created_utc,
            title=row.title,
            body=row.body,
            score=row.score,
            num_comments=row.num_comments,
            permalink=row.permalink,
            retrieved_at=row.retrieved_at,
            detected_tickers=json.loads(row.detected_tickers_json),
            detected_companies=json.loads(row.detected_companies_json),
            sentiment_score=row.sentiment_score,
            sentiment_label=(SentimentLabel(row.sentiment_label) if row.sentiment_label else None),
            event_type=row.event_type,
            event_strength=row.event_strength,
            source_score=row.source_score,
            signal_score=row.signal_score,
            manipulation_score=row.manipulation_score,
            manipulation_flags=json.loads(row.manipulation_flags_json),
            synthetic_outcomes=json.loads(row.synthetic_outcomes_json),
        )

    def clear_analysis(self) -> None:
        with self._database.session_factory.begin() as session:
            session.execute(delete(ForwardReturnRow))
            session.execute(delete(SignalRow))
            session.execute(delete(TickerMentionRow))
            session.execute(delete(SourcePerformanceRow))
            session.execute(delete(AuthorPerformanceRow))

    def update_content_analysis(self, content: SocialContent) -> None:
        with self._database.session_factory.begin() as session:
            row = session.scalar(
                select(SocialContentRow).where(
                    SocialContentRow.post_or_comment_id == content.post_or_comment_id
                )
            )
            if row is None:
                raise LookupError(f"Unknown content ID: {content.post_or_comment_id}")
            row.detected_tickers_json = _json(content.detected_tickers)
            row.detected_companies_json = _json(content.detected_companies)
            row.sentiment_score = content.sentiment_score
            row.sentiment_label = content.sentiment_label.value if content.sentiment_label else None
            row.event_type = content.event_type
            row.event_strength = content.event_strength
            row.source_score = content.source_score
            row.signal_score = content.signal_score
            row.manipulation_score = content.manipulation_score
            row.manipulation_flags_json = _json(content.manipulation_flags)

    def save_mentions(self, mentions: Iterable[TickerMention]) -> None:
        with self._database.session_factory.begin() as session:
            for mention in mentions:
                session.add(
                    TickerMentionRow(
                        content_id=mention.content_id,
                        ticker=mention.ticker,
                        company_name=mention.company_name,
                        matched_text=mention.matched_text,
                        extraction_method=mention.extraction_method,
                        confidence=mention.confidence,
                        created_utc=mention.created_utc,
                    )
                )

    def save_signal(self, signal: ResearchSignal) -> None:
        with self._database.session_factory.begin() as session:
            session.add(
                SignalRow(
                    signal_id=signal.signal_id,
                    content_id=signal.content_id,
                    ticker=signal.ticker,
                    source=signal.source,
                    subreddit=signal.subreddit,
                    author_identifier=signal.author_identifier,
                    sector=signal.sector,
                    event_type=signal.event_type,
                    direction=signal.direction.value,
                    sentiment_score=signal.sentiment_score,
                    source_score=signal.source_score,
                    signal_score=signal.signal_score,
                    manipulation_score=signal.manipulation_score,
                    factors_json=_json(signal.factors.model_dump()),
                    content_created_time=signal.content_created_time,
                    content_retrieved_time=signal.content_retrieved_time,
                    signal_generated_time=signal.signal_generated_time,
                    reason=signal.reason,
                )
            )

    def list_signals(self, limit: int = 100) -> list[ResearchSignal]:
        with self._database.session_factory() as session:
            rows = session.scalars(
                select(SignalRow).order_by(SignalRow.signal_score.desc()).limit(limit)
            ).all()
        return [
            ResearchSignal(
                signal_id=row.signal_id,
                content_id=row.content_id,
                ticker=row.ticker,
                source=row.source,
                subreddit=row.subreddit,
                author_identifier=row.author_identifier,
                sector=row.sector,
                event_type=row.event_type,
                direction=SignalDirection(row.direction),
                sentiment_score=row.sentiment_score,
                source_score=row.source_score,
                signal_score=row.signal_score,
                manipulation_score=row.manipulation_score,
                factors=json.loads(row.factors_json),
                content_created_time=row.content_created_time,
                content_retrieved_time=row.content_retrieved_time,
                signal_generated_time=row.signal_generated_time,
                reason=row.reason,
            )
            for row in rows
        ]

    def save_forward_return(self, result: ForwardReturn) -> None:
        with self._database.session_factory.begin() as session:
            session.add(
                ForwardReturnRow(
                    signal_id=result.signal_id,
                    ticker=result.ticker,
                    horizon=result.horizon,
                    price_observed_time=result.price_observed_time,
                    future_price_observed_time=result.future_price_observed_time,
                    raw_return=result.raw_return,
                    benchmark_adjusted_return=result.benchmark_adjusted_return,
                    benchmark_ticker=result.benchmark_ticker,
                )
            )

    def save_source_performance(
        self, performance: PerformanceScore, calculated_at: datetime
    ) -> None:
        with self._database.session_factory.begin() as session:
            session.add(
                SourcePerformanceRow(
                    key=performance.key,
                    sector=performance.sector or "*",
                    event_type=performance.event_type or "*",
                    horizon=performance.horizon,
                    metrics_json=performance.model_dump_json(),
                    combined_score=performance.combined_score,
                    calculated_at=calculated_at,
                )
            )

    def list_source_performance(self) -> list[PerformanceScore]:
        with self._database.session_factory() as session:
            rows = session.scalars(
                select(SourcePerformanceRow).order_by(SourcePerformanceRow.combined_score.desc())
            ).all()
        return [PerformanceScore.model_validate_json(row.metrics_json) for row in rows]

    def save_author_performance(
        self, performance: PerformanceScore, calculated_at: datetime
    ) -> None:
        with self._database.session_factory.begin() as session:
            session.add(
                AuthorPerformanceRow(
                    author_identifier=performance.key,
                    sector=performance.sector or "*",
                    event_type=performance.event_type or "*",
                    horizon=performance.horizon,
                    metrics_json=performance.model_dump_json(),
                    combined_score=performance.combined_score,
                    calculated_at=calculated_at,
                )
            )

    def list_author_performance(self) -> list[PerformanceScore]:
        with self._database.session_factory() as session:
            rows = session.scalars(
                select(AuthorPerformanceRow).order_by(AuthorPerformanceRow.combined_score.desc())
            ).all()
        return [PerformanceScore.model_validate_json(row.metrics_json) for row in rows]

    def upsert_symbols(self, symbols: Iterable[SymbolRecord]) -> None:
        with self._database.session_factory.begin() as session:
            for symbol in symbols:
                row = session.get(SymbolRow, symbol.ticker)
                if row is None:
                    session.add(
                        SymbolRow(
                            ticker=symbol.ticker,
                            company_name=symbol.company_name,
                            exchange=symbol.exchange,
                            country=symbol.country,
                            currency=symbol.currency,
                            sector=symbol.sector,
                            industry=symbol.industry,
                            market_cap=symbol.market_cap,
                            average_daily_volume=symbol.average_daily_volume,
                            active=symbol.active,
                            aliases_json=_json(symbol.aliases),
                        )
                    )
                else:
                    row.company_name = symbol.company_name
                    row.exchange = symbol.exchange
                    row.country = symbol.country
                    row.currency = symbol.currency
                    row.sector = symbol.sector
                    row.industry = symbol.industry
                    row.market_cap = symbol.market_cap
                    row.average_daily_volume = symbol.average_daily_volume
                    row.active = symbol.active
                    row.aliases_json = _json(symbol.aliases)

    def has_client_order_id(self, client_order_id: str) -> bool:
        with self._database.session_factory() as session:
            return (
                session.scalar(
                    select(PaperOrderRow.order_id).where(
                        PaperOrderRow.client_order_id == client_order_id
                    )
                )
                is not None
            )

    def save_paper_order(self, order: PaperOrder) -> None:
        with self._database.session_factory.begin() as session:
            session.add(
                PaperOrderRow(
                    order_id=order.order_id,
                    client_order_id=order.request.client_order_id,
                    signal_id=order.request.signal_id,
                    ticker=order.request.ticker,
                    quantity=order.request.quantity,
                    limit_price=order.request.limit_price,
                    currency=order.request.currency,
                    status=order.status.value,
                    order_submitted_time=order.order_submitted_time,
                    filled_quantity=order.filled_quantity,
                    average_fill_price=order.average_fill_price,
                    rejection_reason=order.rejection_reason,
                )
            )

    def update_paper_order(self, order: PaperOrder) -> None:
        with self._database.session_factory.begin() as session:
            row = session.get(PaperOrderRow, order.order_id)
            if row is None:
                raise LookupError(f"Unknown paper order: {order.order_id}")
            row.status = order.status.value
            row.filled_quantity = order.filled_quantity
            row.average_fill_price = order.average_fill_price
            row.rejection_reason = order.rejection_reason

    def list_paper_orders(self) -> list[PaperOrder]:
        with self._database.session_factory() as session:
            rows = session.scalars(
                select(PaperOrderRow).order_by(PaperOrderRow.order_submitted_time.desc())
            ).all()
        return [
            PaperOrder(
                order_id=row.order_id,
                request=PaperOrderRequest(
                    client_order_id=row.client_order_id,
                    signal_id=row.signal_id,
                    ticker=row.ticker,
                    quantity=row.quantity,
                    limit_price=row.limit_price,
                    currency=cast(Literal["CAD", "USD"], row.currency),
                ),
                status=OrderStatus(row.status),
                order_submitted_time=row.order_submitted_time,
                filled_quantity=row.filled_quantity,
                average_fill_price=row.average_fill_price,
                rejection_reason=row.rejection_reason,
            )
            for row in rows
        ]

    def save_paper_fill(self, fill: PaperFill) -> None:
        with self._database.session_factory.begin() as session:
            if session.get(PaperFillRow, fill.fill_id) is not None:
                return
            session.add(
                PaperFillRow(
                    fill_id=fill.fill_id,
                    order_id=fill.order_id,
                    ticker=fill.ticker,
                    quantity=fill.quantity,
                    fill_price=fill.fill_price,
                    commission=fill.commission,
                    fill_time=fill.fill_time,
                )
            )

    def record_counts(self) -> dict[str, int]:
        with self._database.session_factory() as session:
            return {
                "content": int(session.scalar(select(func.count(SocialContentRow.id))) or 0),
                "mentions": int(session.scalar(select(func.count(TickerMentionRow.id))) or 0),
                "signals": int(session.scalar(select(func.count(SignalRow.signal_id))) or 0),
                "forward_returns": int(
                    session.scalar(select(func.count(ForwardReturnRow.id))) or 0
                ),
            }
