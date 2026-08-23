from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from traderresearch.config import IbkrConfig, RiskConfig
from traderresearch.market.symbols import sample_symbol_master
from traderresearch.models import (
    MarketSnapshot,
    OrderStatus,
    PaperOrderRequest,
    PortfolioState,
    ResearchSignal,
    SignalFactors,
)
from traderresearch.storage.repository import ResearchRepository
from traderresearch.trading.ibkr import MockIbkrClient, enforce_paper_only
from traderresearch.trading.paper_executor import PaperExecutor
from traderresearch.trading.risk import RiskManager


def test_live_trading_is_never_supported() -> None:
    with pytest.raises(RuntimeError, match="Live trading is not supported"):
        enforce_paper_only("live")
    with pytest.raises(RuntimeError, match="Live trading is not supported"):
        enforce_paper_only("paper", live_trading_enabled=True)


@pytest.mark.parametrize("port", [4001, 7496])
def test_standard_live_ports_are_rejected(port: int) -> None:
    with pytest.raises(RuntimeError, match="live-trading ports"):
        IbkrConfig(port=port)


def test_mock_requires_explicit_paper_submission_enablement() -> None:
    client = MockIbkrClient()
    client.connect()
    request = PaperOrderRequest(
        client_order_id="synthetic-order",
        signal_id="sig_synthetic",
        ticker="SHOP",
        quantity=1,
        limit_price=100,
        currency="CAD",
    )
    with pytest.raises(RuntimeError, match="disabled"):
        client.submit_limit_order(request)


def test_mock_handles_partial_and_complete_fills() -> None:
    client = MockIbkrClient(IbkrConfig(order_submission_enabled=True))
    client.connect()
    request = PaperOrderRequest(
        client_order_id="synthetic-order",
        signal_id="sig_synthetic",
        ticker="SHOP",
        quantity=3,
        limit_price=100,
        currency="CAD",
    )
    order = client.submit_limit_order(request)
    assert order.status == OrderStatus.SUBMITTED
    assert client.simulate_fill(order.order_id, 1, 99.5).status == OrderStatus.PARTIALLY_FILLED
    completed = client.simulate_fill(order.order_id, 2, 100)
    assert completed.status == OrderStatus.FILLED
    assert completed.average_fill_price == pytest.approx((99.5 + 200) / 3)
    assert len(client.drain_fills()) == 2
    assert client.drain_fills() == []
    assert client.drain_order_events()[-1].status == OrderStatus.FILLED


def test_mock_handles_rejected_orders() -> None:
    client = MockIbkrClient(IbkrConfig(order_submission_enabled=True))
    client.connect()
    request = PaperOrderRequest(
        client_order_id="synthetic-rejection",
        signal_id="sig_synthetic",
        ticker="SHOP",
        quantity=1,
        limit_price=100,
        currency="CAD",
    )
    order = client.submit_limit_order(request)
    rejected = client.simulate_rejection(order.order_id)
    assert rejected.status == OrderStatus.REJECTED
    assert client.drain_order_events()[-1].rejection_code == 201


def test_executor_prevents_persisted_duplicate_orders(
    repository: ResearchRepository,
    now: datetime,
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = MockIbkrClient(IbkrConfig(order_submission_enabled=True))
    broker.connect()
    executor = PaperExecutor(broker, RiskManager(RiskConfig()), repository)
    signal = ResearchSignal(
        signal_id="sig_synthetic",
        content_id="synthetic_content",
        ticker="SHOP",
        source="reddit",
        subreddit="sample_markets",
        author_identifier="research_user_test",
        sector="Technology",
        event_type="earnings_guidance",
        direction="long",
        sentiment_score=0.8,
        source_score=20,
        signal_score=75,
        manipulation_score=0,
        factors=SignalFactors(),
        content_created_time=now - timedelta(minutes=2),
        content_retrieved_time=now - timedelta(minutes=1),
        signal_generated_time=now - timedelta(minutes=1),
        reason="Synthetic test signal.",
    )
    request = PaperOrderRequest(
        client_order_id="synthetic-duplicate",
        signal_id=signal.signal_id,
        ticker="SHOP",
        quantity=1,
        limit_price=100,
        currency="CAD",
    )
    snapshot = MarketSnapshot(
        ticker="SHOP",
        price_observed_time=now,
        last_price=100,
        bid=99.9,
        ask=100.1,
        volume=1_000_000,
        currency="CAD",
        benchmark_ticker="XIT.TO",
    )
    portfolio = PortfolioState(connected=True)
    symbol = sample_symbol_master().get("SHOP")

    assert executor.submit(signal, request, snapshot, symbol, portfolio, now=now)
    assert executor.submit(signal, request, snapshot, symbol, portfolio, now=now) is None
    assert len(repository.list_paper_orders()) == 1
    audit_records = [record for record in caplog.records if hasattr(record, "author_identifier")]
    assert audit_records
    assert all(record.author_identifier == "[REDACTED]" for record in audit_records)
