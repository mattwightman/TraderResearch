"""Point-in-time forward-return calculations."""

from __future__ import annotations

from datetime import datetime

from traderresearch.models import ForwardReturn

SUPPORTED_HORIZONS = ("5m", "15m", "30m", "1h", "close", "1d", "5d")


def simple_return(start_price: float, end_price: float) -> float:
    if start_price <= 0 or end_price <= 0:
        raise ValueError("Prices must be positive.")
    return end_price / start_price - 1


def calculate_forward_return(
    *,
    signal_id: str,
    ticker: str,
    horizon: str,
    start_price: float,
    future_price: float,
    benchmark_start_price: float,
    benchmark_future_price: float,
    benchmark_ticker: str,
    price_observed_time: datetime,
    future_price_observed_time: datetime,
) -> ForwardReturn:
    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")
    if future_price_observed_time <= price_observed_time:
        raise ValueError("Future price timestamp must follow the initial observation.")
    raw = simple_return(start_price, future_price)
    benchmark = simple_return(benchmark_start_price, benchmark_future_price)
    return ForwardReturn(
        signal_id=signal_id,
        ticker=ticker,
        horizon=horizon,
        price_observed_time=price_observed_time,
        future_price_observed_time=future_price_observed_time,
        raw_return=raw,
        benchmark_adjusted_return=raw - benchmark,
        benchmark_ticker=benchmark_ticker,
    )
