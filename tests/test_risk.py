from __future__ import annotations

from datetime import datetime, timedelta

from traderresearch.config import RiskConfig
from traderresearch.market.symbols import sample_symbol_master
from traderresearch.models import (
    MarketSnapshot,
    PaperOrderRequest,
    PortfolioState,
)
from traderresearch.trading.risk import RiskManager


def _request() -> PaperOrderRequest:
    return PaperOrderRequest(
        client_order_id="synthetic-order-1",
        signal_id="sig_synthetic",
        ticker="SHOP",
        quantity=2,
        limit_price=100,
        currency="CAD",
    )


def _snapshot(now: datetime) -> MarketSnapshot:
    return MarketSnapshot(
        ticker="SHOP",
        price_observed_time=now - timedelta(seconds=2),
        last_price=100,
        bid=99.90,
        ask=100.10,
        volume=500_000,
        currency="CAD",
        benchmark_ticker="XIT.TO",
    )


def test_valid_paper_order_passes_risk_checks(now: datetime) -> None:
    decision = RiskManager(RiskConfig()).assess(
        _request(),
        _snapshot(now),
        sample_symbol_master().get("SHOP"),
        PortfolioState(connected=True),
        now=now,
        duplicate_order=False,
    )
    assert decision.approved
    assert all(check.passed for check in decision.checks)


def test_duplicate_order_is_rejected(now: datetime) -> None:
    decision = RiskManager(RiskConfig()).assess(
        _request(),
        _snapshot(now),
        sample_symbol_master().get("SHOP"),
        PortfolioState(connected=True),
        now=now,
        duplicate_order=True,
    )
    assert not decision.approved
    assert "duplicate_order" in (decision.reason_for_rejection or "")


def test_stale_quote_and_limits_are_rejected(now: datetime) -> None:
    request = _request().model_copy(update={"quantity": 6})
    snapshot = _snapshot(now).model_copy(
        update={"price_observed_time": now - timedelta(minutes=5), "ask": 105}
    )
    portfolio = PortfolioState(
        connected=True,
        trades_today=10,
        daily_realized_pnl_cad=-100,
    )
    decision = RiskManager(RiskConfig()).assess(
        request,
        snapshot,
        sample_symbol_master().get("SHOP"),
        portfolio,
        now=now,
        duplicate_order=False,
    )
    assert not decision.approved
    reasons = decision.reason_for_rejection or ""
    assert "fresh_price" in reasons
    assert "spread_limit" in reasons
    assert "order_value" in reasons
    assert "daily_trade_count" in reasons
    assert "daily_loss" in reasons


def test_invalid_ticker_and_connection_are_rejected(now: datetime) -> None:
    decision = RiskManager(RiskConfig()).assess(
        _request(),
        _snapshot(now),
        None,
        PortfolioState(connected=False),
        now=now,
        duplicate_order=False,
    )
    assert not decision.approved
    assert "valid_ticker" in (decision.reason_for_rejection or "")
    assert "paper_connection" in (decision.reason_for_rejection or "")
