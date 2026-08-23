"""Author performance is evaluated in context, never as a universal ability."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from traderresearch.analysis.source_scoring import score_performance
from traderresearch.models import PerformanceObservation, PerformanceScore


def score_author_context(
    author_identifier: str,
    observations: Sequence[PerformanceObservation],
    *,
    sector: str,
    event_type: str,
    horizon: str,
    now: datetime,
    minimum_samples: int,
    half_life_days: float,
    recent_window_days: int,
) -> PerformanceScore:
    return score_performance(
        author_identifier,
        observations,
        now=now,
        minimum_samples=minimum_samples,
        half_life_days=half_life_days,
        recent_window_days=recent_window_days,
        sector=sector,
        event_type=event_type,
        horizon=horizon,
    )
