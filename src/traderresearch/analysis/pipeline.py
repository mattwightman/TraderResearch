"""Point-in-time synthetic analysis orchestration."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from traderresearch.analysis.author_scoring import score_author_context
from traderresearch.analysis.event_classifier import KeywordEventClassifier
from traderresearch.analysis.manipulation import assess_manipulation
from traderresearch.analysis.sentiment import LexiconSentimentClassifier
from traderresearch.analysis.signal_scoring import (
    calculate_signal_score,
    normalize_source_score,
    normalize_velocity,
)
from traderresearch.analysis.source_scoring import score_performance
from traderresearch.analysis.ticker_extraction import DeterministicTickerExtractor
from traderresearch.analysis.velocity import calculate_discussion_velocity
from traderresearch.config import AnalysisConfig
from traderresearch.market.benchmarks import SectorBenchmarkSelector
from traderresearch.market.symbols import SymbolMaster
from traderresearch.models import (
    ForwardReturn,
    PerformanceObservation,
    ResearchSignal,
    SignalDirection,
    SignalFactors,
    SocialContent,
    TickerMention,
)
from traderresearch.storage.repository import ResearchRepository

_HORIZON_DELTAS = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "close": timedelta(hours=6),
    "1d": timedelta(days=1),
    "5d": timedelta(days=7),
}


@dataclass(frozen=True)
class AnalysisSummary:
    content_count: int
    mention_count: int
    signal_count: int
    source_scores: int
    author_scores: int


@dataclass(frozen=True)
class _AttributedObservation:
    source_key: str
    author_identifier: str
    ticker: str
    sector: str
    event_type: str
    horizon: str
    value: PerformanceObservation


def _signal_id(content_id: str, ticker: str) -> str:
    digest = hashlib.sha256(f"{content_id}:{ticker}".encode()).hexdigest()[:20]
    return f"sig_{digest}"


def _direction(sentiment_score: float) -> SignalDirection:
    if sentiment_score > 0.15:
        return SignalDirection.LONG
    if sentiment_score < -0.15:
        return SignalDirection.AVOID
    return SignalDirection.NEUTRAL


def _predicted_direction(direction: SignalDirection) -> int:
    if direction == SignalDirection.LONG:
        return 1
    if direction == SignalDirection.AVOID:
        return -1
    return 0


class AnalysisPipeline:
    """Generate reproducible signals using only information available at each timestamp."""

    def __init__(
        self,
        repository: ResearchRepository,
        symbol_master: SymbolMaster,
        config: AnalysisConfig,
    ) -> None:
        self._repository = repository
        self._symbols = symbol_master
        self._config = config
        self._extractor = DeterministicTickerExtractor(symbol_master)
        self._sentiment = LexiconSentimentClassifier()
        self._events = KeywordEventClassifier()
        self._benchmarks = SectorBenchmarkSelector()

    def run(self) -> AnalysisSummary:
        content = sorted(self._repository.list_content(), key=lambda item: item.retrieved_at)
        self._repository.clear_analysis()
        extracted: dict[str, list[TickerMention]] = {
            item.post_or_comment_id: self._extractor.extract(
                item.post_or_comment_id, item.text, item.created_utc
            )
            for item in content
        }
        ticker_content: dict[str, list[SocialContent]] = defaultdict(list)
        for item in content:
            for mention in extracted[item.post_or_comment_id]:
                ticker_content[mention.ticker].append(item)

        attributed: list[_AttributedObservation] = []
        signal_count = 0
        mention_count = 0
        for item in content:
            mentions = extracted[item.post_or_comment_id]
            sentiment = self._sentiment.classify(item.text)
            event = self._events.classify(item.text)
            self._repository.save_mentions(mentions)
            mention_count += len(mentions)

            for mention in mentions:
                symbol = self._symbols.get(mention.ticker)
                if symbol is None:
                    continue
                available_cluster = [
                    candidate
                    for candidate in ticker_content[mention.ticker]
                    if candidate.retrieved_at <= item.retrieved_at
                ]
                manipulation = assess_manipulation(available_cluster)
                velocity = calculate_discussion_velocity(
                    available_cluster,
                    item.retrieved_at,
                    baseline_floor=self._config.low_volume_baseline_floor,
                )
                source_key = f"{item.platform}/{item.subreddit}"
                prior_source = [
                    observation.value
                    for observation in attributed
                    if observation.source_key == source_key
                    and observation.value.observed_at <= item.retrieved_at
                ]
                prior_author = [
                    observation.value
                    for observation in attributed
                    if observation.author_identifier == item.author_identifier
                    and observation.sector == (symbol.sector or "Unknown")
                    and observation.event_type == event.event_type
                    and observation.value.observed_at <= item.retrieved_at
                ]
                source_performance = score_performance(
                    source_key,
                    prior_source,
                    now=item.retrieved_at,
                    minimum_samples=self._config.minimum_source_samples,
                    half_life_days=self._config.source_score_half_life_days,
                    recent_window_days=self._config.recent_window_days,
                )
                author_performance = score_performance(
                    item.author_identifier,
                    prior_author,
                    now=item.retrieved_at,
                    minimum_samples=self._config.minimum_source_samples,
                    half_life_days=self._config.source_score_half_life_days,
                    recent_window_days=self._config.recent_window_days,
                )
                lag_seconds = max(0.0, (item.retrieved_at - item.created_utc).total_seconds())
                freshness = max(0.0, 1.0 - lag_seconds / 3600)
                factors = SignalFactors(
                    source_quality=normalize_source_score(source_performance.combined_score),
                    author_quality=normalize_source_score(author_performance.combined_score),
                    sentiment_strength=abs(sentiment.score),
                    discussion_velocity=normalize_velocity(velocity.mention_velocity),
                    event_importance=event.strength,
                    freshness=freshness,
                    news_confirmation=1.0 if event.primary_source_confirmed else 0.0,
                    price_confirmation=0.0,
                    volume_confirmation=0.0,
                    liquidity=0.75 if (symbol.average_daily_volume or 0) >= 1_000_000 else 0.4,
                    manipulation_safety=1.0 - manipulation.score,
                )
                signal_score = calculate_signal_score(factors, self._config.signal_weights)
                direction = _direction(sentiment.score)
                signal_id = _signal_id(item.post_or_comment_id, mention.ticker)
                signal = ResearchSignal(
                    signal_id=signal_id,
                    content_id=item.post_or_comment_id,
                    ticker=mention.ticker,
                    source=item.platform,
                    subreddit=item.subreddit,
                    author_identifier=item.author_identifier,
                    sector=symbol.sector,
                    event_type=event.event_type,
                    direction=direction,
                    sentiment_score=sentiment.score,
                    source_score=source_performance.combined_score,
                    signal_score=signal_score,
                    manipulation_score=manipulation.score,
                    factors=factors,
                    content_created_time=item.created_utc,
                    content_retrieved_time=item.retrieved_at,
                    signal_generated_time=item.retrieved_at,
                    reason=(
                        "Deterministic research score from point-in-time social factors; "
                        "not a prediction or investment recommendation."
                    ),
                )
                self._repository.save_signal(signal)
                signal_count += 1
                self._save_synthetic_outcomes(item, signal, symbol.sector or "Unknown", attributed)

            item.detected_tickers = [mention.ticker for mention in mentions]
            item.detected_companies = [mention.company_name for mention in mentions]
            item.sentiment_score = sentiment.score
            item.sentiment_label = sentiment.label
            item.event_type = event.event_type
            item.event_strength = event.strength
            if mentions:
                item.manipulation_score = max(
                    assess_manipulation(
                        [
                            candidate
                            for candidate in ticker_content[mention.ticker]
                            if candidate.retrieved_at <= item.retrieved_at
                        ]
                    ).score
                    for mention in mentions
                )
            else:
                item.manipulation_score = 0.0
            self._repository.update_content_analysis(item)

        now = max((item.retrieved_at for item in content), default=datetime.now().astimezone())
        source_count = self._score_sources(attributed, now)
        author_count = self._score_authors(attributed, now)
        return AnalysisSummary(
            content_count=len(content),
            mention_count=mention_count,
            signal_count=signal_count,
            source_scores=source_count,
            author_scores=author_count,
        )

    def _save_synthetic_outcomes(
        self,
        content: SocialContent,
        signal: ResearchSignal,
        sector: str,
        attributed: list[_AttributedObservation],
    ) -> None:
        outcomes = content.synthetic_outcomes.get(signal.ticker, {})
        symbol = self._symbols.get(signal.ticker)
        if symbol is None:
            return
        benchmark = self._benchmarks.select(symbol)
        for horizon, values in outcomes.items():
            delta = _HORIZON_DELTAS.get(horizon)
            if delta is None:
                continue
            raw_return = values["raw_return"]
            benchmark_return = values["benchmark_return"]
            observed_at = signal.signal_generated_time + delta
            result = ForwardReturn(
                signal_id=signal.signal_id,
                ticker=signal.ticker,
                horizon=horizon,
                price_observed_time=signal.signal_generated_time,
                future_price_observed_time=observed_at,
                raw_return=raw_return,
                benchmark_adjusted_return=raw_return - benchmark_return,
                benchmark_ticker=benchmark,
            )
            self._repository.save_forward_return(result)
            attributed.append(
                _AttributedObservation(
                    source_key=f"{signal.source}/{signal.subreddit}",
                    author_identifier=signal.author_identifier,
                    ticker=signal.ticker,
                    sector=sector,
                    event_type=signal.event_type,
                    horizon=horizon,
                    value=PerformanceObservation(
                        observed_at=observed_at,
                        raw_return=raw_return,
                        benchmark_adjusted_return=raw_return - benchmark_return,
                        predicted_direction=_predicted_direction(signal.direction),
                        lead_time_minutes=delta.total_seconds() / 60,
                        manipulation_score=signal.manipulation_score,
                    ),
                )
            )

    def _score_sources(self, observations: list[_AttributedObservation], now: datetime) -> int:
        groups: dict[tuple[str, str | None, str | None, str], list[PerformanceObservation]] = (
            defaultdict(list)
        )
        for item in observations:
            groups[(item.source_key, None, None, item.horizon)].append(item.value)
            groups[(item.source_key, item.sector, item.event_type, item.horizon)].append(item.value)
        for (key, sector, event_type, horizon), values in groups.items():
            score = score_performance(
                key,
                values,
                now=now,
                minimum_samples=self._config.minimum_source_samples,
                half_life_days=self._config.source_score_half_life_days,
                recent_window_days=self._config.recent_window_days,
                sector=sector,
                event_type=event_type,
                horizon=horizon,
            )
            self._repository.save_source_performance(score, now)
        return len(groups)

    def _score_authors(self, observations: list[_AttributedObservation], now: datetime) -> int:
        groups: dict[tuple[str, str, str, str], list[PerformanceObservation]] = defaultdict(list)
        for item in observations:
            groups[
                (
                    item.author_identifier,
                    item.sector,
                    item.event_type,
                    item.horizon,
                )
            ].append(item.value)
        for (author, sector, event_type, horizon), values in groups.items():
            score = score_author_context(
                author,
                values,
                sector=sector,
                event_type=event_type,
                horizon=horizon,
                now=now,
                minimum_samples=self._config.minimum_source_samples,
                half_life_days=self._config.source_score_half_life_days,
                recent_window_days=self._config.recent_window_days,
            )
            self._repository.save_author_performance(score, now)
        return len(groups)
