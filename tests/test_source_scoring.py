from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from traderresearch.analysis.source_scoring import score_performance
from traderresearch.models import PerformanceObservation


def _observations(now: datetime, count: int, excess: float = 0.02) -> list[PerformanceObservation]:
    return [
        PerformanceObservation(
            observed_at=now - timedelta(days=index),
            raw_return=excess + 0.002,
            benchmark_adjusted_return=excess,
            predicted_direction=1,
            lead_time_minutes=1440,
        )
        for index in range(count)
    ]


def test_source_score_reports_expected_statistics(now: datetime) -> None:
    score = score_performance(
        "reddit/sample",
        _observations(now, 10),
        now=now,
        minimum_samples=5,
        half_life_days=30,
        recent_window_days=30,
    )
    assert score.sample_count == 10
    assert score.directional_hit_rate == 1
    assert score.average_benchmark_adjusted_return == pytest.approx(0.02)
    assert score.median_forward_return == pytest.approx(0.022)
    assert score.combined_score > 50


def test_small_samples_are_penalized(now: datetime) -> None:
    small = score_performance(
        "small",
        _observations(now, 2),
        now=now,
        minimum_samples=20,
    )
    large = score_performance(
        "large",
        _observations(now, 20),
        now=now,
        minimum_samples=20,
    )
    assert abs(small.combined_score) < abs(large.combined_score)
    assert small.statistical_confidence < large.statistical_confidence


def test_manipulation_risk_reduces_score(now: datetime) -> None:
    clean = _observations(now, 10)
    risky = [item.model_copy(update={"manipulation_score": 0.8}) for item in clean]
    clean_score = score_performance("clean", clean, now=now, minimum_samples=5)
    risky_score = score_performance("risky", risky, now=now, minimum_samples=5)
    assert risky_score.combined_score < clean_score.combined_score
