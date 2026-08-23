"""Confidence-adjusted, decay-aware source and author performance scoring."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from datetime import datetime, timedelta

from traderresearch.models import PerformanceObservation, PerformanceScore


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _quality(observations: Sequence[PerformanceObservation]) -> float:
    if not observations:
        return 0.0
    directional = [
        1.0 if item.predicted_direction * item.benchmark_adjusted_return > 0 else 0.0
        for item in observations
    ]
    hit_component = (_mean(directional) - 0.5) * 2
    excess_component = math.tanh(
        _mean([item.predicted_direction * item.benchmark_adjusted_return for item in observations])
        / 0.02
    )
    return 100 * (0.55 * hit_component + 0.45 * excess_component)


def _decayed_quality(
    observations: Sequence[PerformanceObservation], now: datetime, half_life_days: float
) -> float:
    if not observations:
        return 0.0
    weighted_hits = 0.0
    weighted_returns = 0.0
    weight_sum = 0.0
    for item in observations:
        age_days = max(0.0, (now - item.observed_at).total_seconds() / 86_400)
        weight = 0.5 ** (age_days / half_life_days)
        weighted_hits += weight * (
            1.0 if item.predicted_direction * item.benchmark_adjusted_return > 0 else 0.0
        )
        weighted_returns += weight * item.predicted_direction * item.benchmark_adjusted_return
        weight_sum += weight
    hit_component = (weighted_hits / weight_sum - 0.5) * 2
    return_component = math.tanh((weighted_returns / weight_sum) / 0.02)
    return 100 * (0.55 * hit_component + 0.45 * return_component)


def score_performance(
    key: str,
    observations: Sequence[PerformanceObservation],
    *,
    now: datetime,
    minimum_samples: int = 20,
    half_life_days: float = 30,
    recent_window_days: int = 30,
    sector: str | None = None,
    event_type: str | None = None,
    horizon: str = "1d",
) -> PerformanceScore:
    """Calculate performance while penalizing tiny and manipulation-heavy samples."""

    sample_count = len(observations)
    if sample_count == 0:
        return PerformanceScore(
            key=key,
            sample_count=0,
            directional_hit_rate=0,
            average_forward_return=0,
            median_forward_return=0,
            average_benchmark_adjusted_return=0,
            volatility=0,
            consistency=0,
            statistical_confidence=0,
            average_lead_time_minutes=0,
            recent_score=0,
            historical_score=0,
            combined_score=0,
            manipulation_risk=0,
            sector=sector,
            event_type=event_type,
            horizon=horizon,
        )

    raw = [item.raw_return for item in observations]
    excess = [item.benchmark_adjusted_return for item in observations]
    directional = [
        1.0 if item.predicted_direction * item.benchmark_adjusted_return > 0 else 0.0
        for item in observations
    ]
    volatility = statistics.pstdev(excess) if sample_count > 1 else 0.0
    hit_rate = _mean(directional)
    consistency = max(0.0, 1.0 - 2 * statistics.pstdev(directional))
    standard_error = volatility / math.sqrt(sample_count) if volatility else 0.0
    signal_to_noise = (
        abs(_mean(excess)) / standard_error
        if standard_error > 0
        else (1.0 if _mean(excess) != 0 else 0.0)
    )
    evidence_factor = min(1.0, sample_count / minimum_samples)
    confidence = evidence_factor * math.tanh(signal_to_noise / 2)
    manipulation_risk = _mean([item.manipulation_score for item in observations])

    historical = _quality(observations)
    recent_cutoff = now - timedelta(days=recent_window_days)
    recent = [item for item in observations if item.observed_at >= recent_cutoff]
    recent_quality = _decayed_quality(recent or observations, now, half_life_days)
    combined = (0.6 * recent_quality + 0.4 * historical) * evidence_factor
    combined *= 1.0 - manipulation_risk

    return PerformanceScore(
        key=key,
        sample_count=sample_count,
        directional_hit_rate=hit_rate,
        average_forward_return=_mean(raw),
        median_forward_return=statistics.median(raw),
        average_benchmark_adjusted_return=_mean(excess),
        volatility=volatility,
        consistency=consistency,
        statistical_confidence=confidence,
        average_lead_time_minutes=_mean([item.lead_time_minutes for item in observations]),
        recent_score=max(-100.0, min(100.0, recent_quality)),
        historical_score=max(-100.0, min(100.0, historical)),
        combined_score=max(-100.0, min(100.0, combined)),
        manipulation_risk=manipulation_risk,
        sector=sector,
        event_type=event_type,
        horizon=horizon,
    )
