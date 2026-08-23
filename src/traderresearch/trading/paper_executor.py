"""Risk-gated paper order execution and structured decision auditing."""

from __future__ import annotations

import logging
from datetime import datetime

from traderresearch.models import (
    DecisionAudit,
    MarketSnapshot,
    PaperOrder,
    PaperOrderRequest,
    PortfolioState,
    ResearchSignal,
    SymbolRecord,
)
from traderresearch.storage.repository import ResearchRepository
from traderresearch.trading.ibkr import PaperBrokerClient
from traderresearch.trading.risk import RiskManager


class PaperExecutor:
    def __init__(
        self,
        broker: PaperBrokerClient,
        risk_manager: RiskManager,
        repository: ResearchRepository,
    ) -> None:
        self._broker = broker
        self._risk_manager = risk_manager
        self._repository = repository
        self._logger = logging.getLogger(__name__)

    def submit(
        self,
        signal: ResearchSignal,
        request: PaperOrderRequest,
        snapshot: MarketSnapshot,
        symbol: SymbolRecord | None,
        portfolio: PortfolioState,
        *,
        now: datetime,
        fx_to_cad: float = 1.0,
    ) -> PaperOrder | None:
        duplicate = self._repository.has_client_order_id(request.client_order_id) or any(
            order.request.client_order_id == request.client_order_id
            for order in portfolio.open_orders
        )
        decision = self._risk_manager.assess(
            request,
            snapshot,
            symbol,
            portfolio,
            now=now,
            duplicate_order=duplicate,
            fx_to_cad=fx_to_cad,
        )
        audit = DecisionAudit(
            timestamp=now,
            signal_id=signal.signal_id,
            ticker=signal.ticker,
            source=signal.source,
            subreddit=signal.subreddit,
            author_identifier=signal.author_identifier,
            event_type=signal.event_type,
            sentiment=signal.sentiment_score,
            source_score=signal.source_score,
            signal_score=signal.signal_score,
            market_price=snapshot.last_price,
            bid=snapshot.bid,
            ask=snapshot.ask,
            volume=snapshot.volume,
            risk_checks=[check.model_dump() for check in decision.checks],
            decision="submit" if decision.approved else "reject",
            order_price=request.limit_price,
            quantity=request.quantity,
            reason_for_trade=signal.reason if decision.approved else None,
            reason_for_rejection=decision.reason_for_rejection,
        )
        if not decision.approved:
            self._logger.warning("paper_order_rejected", extra=audit.model_dump())
            return None
        order = self._broker.submit_limit_order(request)
        self._repository.save_paper_order(order)
        audit.order_id = order.order_id
        audit.order_status = order.status.value
        self._logger.info("paper_order_submitted", extra=audit.model_dump())
        return order
