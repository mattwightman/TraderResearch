"""Paper order state reconciliation helpers."""

from __future__ import annotations

from traderresearch.models import OrderStatus, PaperOrder

_TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}


def reconcile_order(local: PaperOrder, broker: PaperOrder) -> PaperOrder:
    """Adopt broker fill/status data while rejecting mismatched order identities."""

    if local.order_id != broker.order_id:
        raise ValueError("Cannot reconcile different order identifiers.")
    if local.request != broker.request:
        raise ValueError("Broker order details do not match the local request.")
    if local.status in _TERMINAL and broker.status != local.status:
        raise ValueError("A terminal local order cannot transition to another state.")
    if broker.filled_quantity < local.filled_quantity:
        raise ValueError("Filled quantity cannot decrease during reconciliation.")
    return broker.model_copy(deep=True)
