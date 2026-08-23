"""Configurable research signal score; it makes no predictive claim."""

from __future__ import annotations

from traderresearch.config import SignalWeights
from traderresearch.models import SignalFactors


def calculate_signal_score(factors: SignalFactors, weights: SignalWeights) -> float:
    """Return a normalized zero-to-100 research-prioritization score."""

    factor_values: dict[str, float] = factors.model_dump()
    weight_values: dict[str, float] = weights.model_dump()
    denominator = sum(weight_values.values())
    weighted = sum(factor_values[name] * weight for name, weight in weight_values.items())
    return round(100 * weighted / denominator, 4)


def normalize_source_score(score: float) -> float:
    return max(0.0, min(1.0, (score + 100) / 200))


def normalize_velocity(velocity: float) -> float:
    """Map velocity ratios to [0, 1], with 1x baseline mapped to 0.5."""

    if velocity <= 0:
        return 0.0
    return min(1.0, velocity / (velocity + 1))
