"""Price-provider contracts and deterministic fixtures."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from traderresearch.models import MarketSnapshot


class PriceProvider(Protocol):
    def snapshot(self, ticker: str, observed_at: datetime) -> MarketSnapshot: ...


class InMemoryPriceProvider:
    def __init__(self, snapshots: dict[str, MarketSnapshot]) -> None:
        self._snapshots = {ticker.upper(): value for ticker, value in snapshots.items()}

    def snapshot(self, ticker: str, observed_at: datetime) -> MarketSnapshot:
        del observed_at
        try:
            return self._snapshots[ticker.upper()]
        except KeyError as error:
            raise LookupError(f"No market snapshot is available for {ticker.upper()}.") from error
