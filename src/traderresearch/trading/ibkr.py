"""Interactive Brokers paper client and deterministic test double."""

from __future__ import annotations

import threading
import time
from typing import Any, Literal, Protocol, cast

from traderresearch.config import IbkrConfig
from traderresearch.models import (
    OrderStatus,
    PaperAccountStatus,
    PaperFill,
    PaperOrder,
    PaperOrderEvent,
    PaperOrderRequest,
    PortfolioState,
    Position,
    utc_now,
)


def enforce_paper_only(environment: str, live_trading_enabled: bool = False) -> None:
    if environment != "paper" or live_trading_enabled:
        raise RuntimeError("Live trading is not supported by TraderResearch.")


class PaperBrokerClient(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def reconnect(self) -> None: ...

    def is_connected(self) -> bool: ...

    def read_account_summary(self) -> PaperAccountStatus: ...

    def read_positions(self) -> list[Position]: ...

    def read_open_orders(self) -> list[PaperOrder]: ...

    def submit_limit_order(self, request: PaperOrderRequest) -> PaperOrder: ...

    def cancel_order(self, order_id: str) -> None: ...

    def drain_order_events(self) -> list[PaperOrderEvent]: ...

    def drain_fills(self) -> list[PaperFill]: ...


def _map_order_status(status: str) -> OrderStatus:
    normalized = status.casefold()
    if normalized == "filled":
        return OrderStatus.FILLED
    if normalized in {"cancelled", "apicancelled"}:
        return OrderStatus.CANCELLED
    if normalized == "inactive":
        return OrderStatus.REJECTED
    if normalized in {"submitted", "presubmitted", "pendingsubmit"}:
        return OrderStatus.SUBMITTED
    return OrderStatus.PENDING


class MockIbkrClient:
    """No-network paper broker used in tests and explicit simulations."""

    def __init__(self, config: IbkrConfig | None = None) -> None:
        self._config = config or IbkrConfig()
        enforce_paper_only(self._config.environment, self._config.live_trading_enabled)
        self._connected = False
        self._positions: list[Position] = []
        self._orders: dict[str, PaperOrder] = {}
        self._events: list[PaperOrderEvent] = []
        self._fills: list[PaperFill] = []
        self._next_order_id = 1

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def reconnect(self) -> None:
        self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        return self._connected

    def read_account_summary(self) -> PaperAccountStatus:
        return PaperAccountStatus(
            connected=self._connected,
            positions_count=len(self._positions),
            open_orders_count=len(self.read_open_orders()),
            message="Mock paper session is connected. No account identifiers are displayed.",
        )

    def read_positions(self) -> list[Position]:
        return list(self._positions)

    def read_open_orders(self) -> list[PaperOrder]:
        return [
            order
            for order in self._orders.values()
            if order.status
            in {
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIALLY_FILLED,
            }
        ]

    def submit_limit_order(self, request: PaperOrderRequest) -> PaperOrder:
        if not self._connected:
            raise ConnectionError("Paper broker is not connected.")
        if not self._config.order_submission_enabled:
            raise RuntimeError("Paper order submission is disabled by configuration.")
        order_id = f"mock-paper-{self._next_order_id}"
        self._next_order_id += 1
        order = PaperOrder(
            order_id=order_id,
            request=request,
            status=OrderStatus.SUBMITTED,
            order_submitted_time=utc_now(),
        )
        self._orders[order_id] = order
        self._events.append(
            PaperOrderEvent(
                order_id=order_id,
                status=OrderStatus.SUBMITTED,
                remaining_quantity=request.quantity,
            )
        )
        return order

    def cancel_order(self, order_id: str) -> None:
        order = self._orders.get(order_id)
        if order is None:
            raise LookupError(f"Unknown paper order: {order_id}")
        order.status = OrderStatus.CANCELLED
        self._events.append(
            PaperOrderEvent(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                filled_quantity=order.filled_quantity,
                remaining_quantity=order.request.quantity - order.filled_quantity,
                average_fill_price=order.average_fill_price,
            )
        )

    def simulate_fill(self, order_id: str, quantity: int, fill_price: float) -> PaperOrder:
        """Apply full or partial fills deterministically for tests."""

        order = self._orders[order_id]
        remaining = order.request.quantity - order.filled_quantity
        if quantity <= 0 or quantity > remaining:
            raise ValueError("Fill quantity must be within the unfilled quantity.")
        previous_value = (order.average_fill_price or 0) * order.filled_quantity
        order.filled_quantity += quantity
        order.average_fill_price = (previous_value + fill_price * quantity) / order.filled_quantity
        order.status = (
            OrderStatus.FILLED
            if order.filled_quantity == order.request.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        self._fills.append(
            PaperFill(
                fill_id=f"{order_id}-fill-{len(self._fills) + 1}",
                order_id=order_id,
                ticker=order.request.ticker,
                quantity=quantity,
                fill_price=fill_price,
                commission=0,
                fill_time=utc_now(),
            )
        )
        self._events.append(
            PaperOrderEvent(
                order_id=order_id,
                status=order.status,
                filled_quantity=order.filled_quantity,
                remaining_quantity=order.request.quantity - order.filled_quantity,
                average_fill_price=order.average_fill_price,
            )
        )
        return order

    def simulate_rejection(self, order_id: str, rejection_code: int = 201) -> PaperOrder:
        order = self._orders[order_id]
        order.status = OrderStatus.REJECTED
        order.rejection_reason = f"Paper broker rejection code {rejection_code}."
        self._events.append(
            PaperOrderEvent(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                remaining_quantity=order.request.quantity - order.filled_quantity,
                rejection_code=rejection_code,
            )
        )
        return order

    def drain_order_events(self) -> list[PaperOrderEvent]:
        events, self._events = self._events, []
        return events

    def drain_fills(self) -> list[PaperFill]:
        fills, self._fills = self._fills, []
        return fills


class IbkrPaperClient:
    """Optional official-API adapter restricted to an IBKR paper session."""

    def __init__(self, config: IbkrConfig, timeout_seconds: float = 5.0) -> None:
        enforce_paper_only(config.environment, config.live_trading_enabled)
        self._config = config
        self._timeout = timeout_seconds
        self._app: Any = None
        self._thread: threading.Thread | None = None

    def _build_app(self) -> Any:
        try:
            from ibapi.client import EClient
            from ibapi.wrapper import EWrapper
        except ImportError as error:
            raise RuntimeError(
                "IBKR support is optional. Install it with: pip install -e '.[ibkr]'"
            ) from error

        class App(EWrapper, EClient):  # type: ignore[misc]
            def __init__(self) -> None:
                EWrapper.__init__(self)
                EClient.__init__(self, self)
                self.ready = threading.Event()
                self.positions_ready = threading.Event()
                self.orders_ready = threading.Event()
                self.next_order_id: int | None = None
                self.positions: list[Position] = []
                self.open_orders: list[PaperOrder] = []
                self.open_order_count = 0
                self.order_events: list[PaperOrderEvent] = []
                self.fills: list[PaperFill] = []

            def nextValidId(self, orderId: int) -> None:
                self.next_order_id = orderId
                self.ready.set()

            def managedAccounts(self, accountsList: str) -> None:
                # Account identifiers are intentionally discarded.
                del accountsList

            def position(
                self, account: str, contract: Any, position: float, avgCost: float
            ) -> None:
                del account
                if position >= 0 and getattr(contract, "secType", "") == "STK":
                    self.positions.append(
                        Position(
                            ticker=str(contract.symbol),
                            quantity=position,
                            average_cost=max(float(avgCost), 0),
                            currency=str(contract.currency),
                        )
                    )

            def positionEnd(self) -> None:
                self.positions_ready.set()

            def openOrder(self, orderId: int, contract: Any, order: Any, orderState: Any) -> None:
                self.open_order_count += 1
                if (
                    str(getattr(contract, "secType", "")) == "STK"
                    and str(getattr(order, "action", "")).upper() == "BUY"
                    and str(getattr(order, "orderType", "")).upper() == "LMT"
                ):
                    self.open_orders.append(
                        PaperOrder(
                            order_id=f"ibkr-paper-{orderId}",
                            request=PaperOrderRequest(
                                client_order_id=f"broker-order-{orderId}",
                                signal_id="unattributed-paper-order",
                                ticker=str(contract.symbol),
                                quantity=int(float(order.totalQuantity)),
                                limit_price=float(order.lmtPrice),
                                currency=cast(Literal["CAD", "USD"], str(contract.currency)),
                                exchange=str(contract.exchange or "SMART"),
                            ),
                            status=_map_order_status(str(orderState.status)),
                        )
                    )

            def openOrderEnd(self) -> None:
                self.orders_ready.set()

            def orderStatus(
                self,
                orderId: int,
                status: str,
                filled: Any,
                remaining: Any,
                avgFillPrice: float,
                permId: int,
                parentId: int,
                lastFillPrice: float,
                clientId: int,
                whyHeld: str,
                mktCapPrice: float,
            ) -> None:
                del permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice
                mapped = _map_order_status(status)
                filled_value = float(filled)
                remaining_value = float(remaining)
                if mapped == OrderStatus.SUBMITTED and filled_value > 0 and remaining_value > 0:
                    mapped = OrderStatus.PARTIALLY_FILLED
                self.order_events.append(
                    PaperOrderEvent(
                        order_id=f"ibkr-paper-{orderId}",
                        status=mapped,
                        filled_quantity=filled_value,
                        remaining_quantity=remaining_value,
                        average_fill_price=max(float(avgFillPrice), 0),
                    )
                )

            def execDetails(self, reqId: int, contract: Any, execution: Any) -> None:
                del reqId
                self.fills.append(
                    PaperFill(
                        fill_id=str(execution.execId),
                        order_id=f"ibkr-paper-{int(execution.orderId)}",
                        ticker=str(contract.symbol),
                        quantity=int(float(execution.shares)),
                        fill_price=float(execution.price),
                        commission=0,
                        fill_time=utc_now(),
                    )
                )

            def commissionReport(self, commissionReport: Any) -> None:
                for index, fill in enumerate(self.fills):
                    if fill.fill_id == str(commissionReport.execId):
                        self.fills[index] = fill.model_copy(
                            update={"commission": max(float(commissionReport.commission), 0)}
                        )
                        break

            def error(
                self,
                reqId: int,
                errorCode: int,
                errorString: str,
                advancedOrderRejectJson: str = "",
            ) -> None:
                del errorString, advancedOrderRejectJson
                if reqId >= 0 and errorCode in {103, 105, 107, 109, 110, 111, 201}:
                    self.order_events.append(
                        PaperOrderEvent(
                            order_id=f"ibkr-paper-{reqId}",
                            status=OrderStatus.REJECTED,
                            rejection_code=errorCode,
                        )
                    )

        return App()

    def connect(self) -> None:
        if self.is_connected():
            return
        self._app = self._build_app()
        self._app.connect(self._config.host, self._config.port, clientId=self._config.client_id)
        self._thread = threading.Thread(target=self._app.run, name="ibkr-paper-reader", daemon=True)
        self._thread.start()
        if not self._app.ready.wait(self._timeout):
            self.disconnect()
            raise ConnectionError(
                "Could not establish an IBKR paper API session. Verify TWS or Gateway paper mode."
            )

    def disconnect(self) -> None:
        if self._app is not None:
            self._app.disconnect()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._app = None
        self._thread = None

    def reconnect(self) -> None:
        self.disconnect()
        last_error: Exception | None = None
        for delay in (0.0, 0.25, 0.75):
            if delay:
                time.sleep(delay)
            try:
                self.connect()
                return
            except ConnectionError as error:
                last_error = error
        raise ConnectionError("Unable to reconnect to the IBKR paper session.") from last_error

    def is_connected(self) -> bool:
        return bool(self._app is not None and self._app.isConnected())

    def read_positions(self) -> list[Position]:
        if not self.is_connected():
            raise ConnectionError("Paper broker is not connected.")
        self._app.positions = []
        self._app.positions_ready.clear()
        self._app.reqPositions()
        self._app.positions_ready.wait(self._timeout)
        self._app.cancelPositions()
        return list(self._app.positions)

    def read_open_orders(self) -> list[PaperOrder]:
        if not self.is_connected():
            raise ConnectionError("Paper broker is not connected.")
        self._app.open_order_count = 0
        self._app.open_orders = []
        self._app.orders_ready.clear()
        self._app.reqOpenOrders()
        self._app.orders_ready.wait(self._timeout)
        return list(self._app.open_orders)

    def read_account_summary(self) -> PaperAccountStatus:
        """Return only connectivity and counts; IDs and financial values are omitted."""

        positions = self.read_positions()
        open_orders = self.read_open_orders()
        return PaperAccountStatus(
            connected=self.is_connected(),
            positions_count=len(positions),
            open_orders_count=len(open_orders),
            message="IBKR paper session is connected. Financial and account data are omitted.",
        )

    def submit_limit_order(self, request: PaperOrderRequest) -> PaperOrder:
        enforce_paper_only(self._config.environment, self._config.live_trading_enabled)
        if not self._config.order_submission_enabled:
            raise RuntimeError("Paper order submission is disabled by configuration.")
        if not self.is_connected() or self._app.next_order_id is None:
            raise ConnectionError("Paper broker is not connected or has no valid order ID.")
        from ibapi.contract import Contract
        from ibapi.order import Order

        contract = Contract()
        contract.symbol = request.ticker
        contract.secType = "STK"
        contract.exchange = request.exchange
        contract.currency = request.currency
        order = Order()
        order.action = "BUY"
        order.orderType = "LMT"
        order.totalQuantity = request.quantity
        order.lmtPrice = request.limit_price
        order.transmit = True

        order_id = int(self._app.next_order_id)
        self._app.next_order_id += 1
        self._app.placeOrder(order_id, contract, order)
        return PaperOrder(
            order_id=f"ibkr-paper-{order_id}",
            request=request,
            status=OrderStatus.SUBMITTED,
            order_submitted_time=utc_now(),
        )

    def cancel_order(self, order_id: str) -> None:
        if not self.is_connected():
            raise ConnectionError("Paper broker is not connected.")
        try:
            numeric_id = int(order_id.removeprefix("ibkr-paper-"))
        except ValueError as error:
            raise ValueError("Invalid paper order identifier.") from error
        self._app.cancelOrder(numeric_id, "TraderResearch paper cancellation")

    def drain_order_events(self) -> list[PaperOrderEvent]:
        if self._app is None:
            return []
        events, self._app.order_events = self._app.order_events, []
        return list(events)

    def drain_fills(self) -> list[PaperFill]:
        if self._app is None:
            return []
        fills, self._app.fills = self._app.fills, []
        return list(fills)

    def portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            connected=self.is_connected(),
            positions=self.read_positions(),
            open_orders=self.read_open_orders(),
        )
