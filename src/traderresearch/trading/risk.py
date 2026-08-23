"""Pre-submission hard risk controls for simulated stock orders."""

from __future__ import annotations

from datetime import datetime

from traderresearch.config import RiskConfig
from traderresearch.models import (
    MarketSnapshot,
    PaperOrderRequest,
    PortfolioState,
    RiskCheck,
    RiskDecision,
    SymbolRecord,
)


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def assess(
        self,
        request: PaperOrderRequest,
        snapshot: MarketSnapshot,
        symbol: SymbolRecord | None,
        portfolio: PortfolioState,
        *,
        now: datetime,
        duplicate_order: bool,
        fx_to_cad: float = 1.0,
    ) -> RiskDecision:
        order_value = request.quantity * request.limit_price * fx_to_cad
        current_position = next(
            (position for position in portfolio.positions if position.ticker == request.ticker),
            None,
        )
        position_value = current_position.value if current_position else 0.0
        is_new_position = current_position is None
        age_seconds = (now - snapshot.price_observed_time).total_seconds()

        checks = [
            RiskCheck(
                name="paper_connection",
                passed=portfolio.connected,
                detail="Paper broker connection must be active.",
            ),
            RiskCheck(
                name="duplicate_order",
                passed=not duplicate_order,
                detail="Client order ID must be unique.",
            ),
            RiskCheck(
                name="valid_ticker",
                passed=symbol is not None and symbol.active,
                detail="Ticker must be active in the symbol master.",
            ),
            RiskCheck(
                name="stocks_long_only",
                passed=(
                    request.security_type == "STK"
                    and request.side == "BUY"
                    and request.quantity > 0
                ),
                detail="Only long stock purchases are supported.",
            ),
            RiskCheck(
                name="limit_order",
                passed=request.order_type == "LMT",
                detail="Market orders are prohibited.",
            ),
            RiskCheck(
                name="fresh_price",
                passed=0 <= age_seconds <= self._config.maximum_price_age_seconds,
                detail=f"Price age is {age_seconds:.1f} seconds.",
            ),
            RiskCheck(
                name="spread_limit",
                passed=snapshot.relative_spread <= self._config.maximum_bid_ask_spread,
                detail=f"Relative spread is {snapshot.relative_spread:.4f}.",
            ),
            RiskCheck(
                name="minimum_price",
                passed=snapshot.last_price >= self._config.minimum_stock_price,
                detail=f"Observed price is {snapshot.last_price:.2f}.",
            ),
            RiskCheck(
                name="minimum_market_cap",
                passed=(
                    symbol is not None
                    and symbol.market_cap is not None
                    and symbol.market_cap >= self._config.minimum_market_cap
                ),
                detail="Market capitalization must meet the tradeability filter.",
            ),
            RiskCheck(
                name="minimum_liquidity",
                passed=(
                    symbol is not None
                    and symbol.average_daily_volume is not None
                    and symbol.average_daily_volume >= self._config.minimum_average_daily_volume
                ),
                detail="Average daily volume must meet the liquidity filter.",
            ),
            RiskCheck(
                name="order_value",
                passed=order_value <= self._config.max_order_value_cad,
                detail=f"Order value is {order_value:.2f} CAD-equivalent.",
            ),
            RiskCheck(
                name="position_value",
                passed=(position_value + order_value <= self._config.max_position_value_cad),
                detail="Resulting position must remain within its limit.",
            ),
            RiskCheck(
                name="total_exposure",
                passed=(
                    portfolio.total_exposure + order_value
                    <= min(
                        self._config.max_total_exposure_cad,
                        self._config.research_capital_cad,
                    )
                ),
                detail="Exposure uses configured research capital, not broker balance.",
            ),
            RiskCheck(
                name="open_positions",
                passed=(
                    not is_new_position
                    or len(portfolio.positions) < self._config.max_open_positions
                ),
                detail="Open-position count must remain within its limit.",
            ),
            RiskCheck(
                name="daily_trade_count",
                passed=portfolio.trades_today < self._config.max_trades_per_day,
                detail="Daily trade count must remain within its limit.",
            ),
            RiskCheck(
                name="daily_loss",
                passed=(portfolio.daily_realized_pnl_cad > -self._config.max_daily_loss_cad),
                detail="Trading stops after the configured daily loss is reached.",
            ),
        ]
        failed = [check for check in checks if not check.passed]
        return RiskDecision(
            approved=not failed,
            checks=checks,
            reason_for_rejection=("; ".join(check.name for check in failed) if failed else None),
        )
