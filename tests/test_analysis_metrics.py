from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import make_content

from traderresearch.analysis.forward_returns import calculate_forward_return
from traderresearch.analysis.manipulation import assess_manipulation
from traderresearch.analysis.signal_scoring import calculate_signal_score
from traderresearch.analysis.velocity import calculate_discussion_velocity
from traderresearch.config import SignalWeights
from traderresearch.models import SignalFactors


def test_benchmark_adjusted_return(now: datetime) -> None:
    result = calculate_forward_return(
        signal_id="sig_synthetic",
        ticker="NVDA",
        horizon="1d",
        start_price=100,
        future_price=105,
        benchmark_start_price=200,
        benchmark_future_price=202,
        benchmark_ticker="QQQ",
        price_observed_time=now,
        future_price_observed_time=now + timedelta(days=1),
    )
    assert result.raw_return == pytest.approx(0.05)
    assert result.benchmark_adjusted_return == pytest.approx(0.04)


def test_forward_return_rejects_non_future_timestamp(now: datetime) -> None:
    with pytest.raises(ValueError, match="must follow"):
        calculate_forward_return(
            signal_id="sig_synthetic",
            ticker="NVDA",
            horizon="1d",
            start_price=100,
            future_price=101,
            benchmark_start_price=100,
            benchmark_future_price=100,
            benchmark_ticker="QQQ",
            price_observed_time=now,
            future_price_observed_time=now,
        )


def test_mention_velocity_handles_zero_baseline(now: datetime) -> None:
    recent = make_content(content_id="recent", created_at=now - timedelta(minutes=1))
    velocity = calculate_discussion_velocity([recent], now, baseline_floor=0.25)
    assert velocity.current_mentions_5m == 1
    assert velocity.historical_average_1h == 0
    assert velocity.mention_velocity > 0


def test_mention_velocity_detects_burst(now: datetime) -> None:
    historical = [
        make_content(content_id=f"old_{index}", created_at=now - timedelta(hours=10 + index))
        for index in range(2)
    ]
    recent = [
        make_content(content_id=f"new_{index}", created_at=now - timedelta(minutes=index))
        for index in range(5)
    ]
    velocity = calculate_discussion_velocity([*historical, *recent], now)
    assert velocity.current_mentions_5m == 5
    assert velocity.mention_velocity > 1


def test_manipulation_indicators_flag_coordinated_promotion(now: datetime) -> None:
    content = [
        make_content(
            content_id=f"promo_{index}",
            text="$TSLA guaranteed moon buy now https://example.invalid/promo",
            created_at=now + timedelta(minutes=index),
            author=f"research_user_{index:03}",
            subreddit="sample_promotions",
        )
        for index in range(4)
    ]
    assessment = assess_manipulation(content)
    assert assessment.score >= 0.5
    assert "highly_similar_wording" in assessment.flags
    assert "repeated_urls" in assessment.flags
    assert "synchronized_posting_burst" in assessment.flags


def test_signal_score_uses_configurable_weights() -> None:
    factors = SignalFactors(sentiment_strength=1, manipulation_safety=0)
    sentiment_only = SignalWeights(
        source_quality=0,
        author_quality=0,
        sentiment_strength=1,
        discussion_velocity=0,
        event_importance=0,
        freshness=0,
        news_confirmation=0,
        price_confirmation=0,
        volume_confirmation=0,
        liquidity=0,
        manipulation_safety=0,
    )
    manipulation_only = sentiment_only.model_copy(
        update={"sentiment_strength": 0, "manipulation_safety": 1}
    )
    assert calculate_signal_score(factors, sentiment_only) == 100
    assert calculate_signal_score(factors, manipulation_only) == 0
