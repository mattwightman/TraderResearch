"""Extensible symbol-master implementations."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol

from traderresearch.models import SymbolRecord


class SymbolMaster(Protocol):
    def get(self, ticker: str) -> SymbolRecord | None: ...

    def active_symbols(self) -> list[SymbolRecord]: ...

    def search_company(self, text: str) -> list[SymbolRecord]: ...


class InMemorySymbolMaster:
    """Small seed implementation; accepts an arbitrarily broad supplied universe."""

    def __init__(self, symbols: list[SymbolRecord]) -> None:
        self._symbols = {symbol.ticker.upper(): symbol for symbol in symbols}

    def get(self, ticker: str) -> SymbolRecord | None:
        symbol = self._symbols.get(ticker.upper())
        return symbol if symbol and symbol.active else None

    def active_symbols(self) -> list[SymbolRecord]:
        return [symbol for symbol in self._symbols.values() if symbol.active]

    def search_company(self, text: str) -> list[SymbolRecord]:
        lowered = text.casefold()
        return [
            symbol
            for symbol in self.active_symbols()
            if symbol.company_name.casefold() in lowered
            or any(alias.casefold() in lowered for alias in symbol.aliases)
        ]

    @classmethod
    def from_csv(cls, path: Path) -> InMemorySymbolMaster:
        """Load a large exchange-provided symbol universe from a normalized CSV."""

        with path.open(newline="", encoding="utf-8") as handle:
            records = []
            for row in csv.DictReader(handle):
                records.append(
                    SymbolRecord(
                        ticker=row["ticker"],
                        company_name=row["company_name"],
                        exchange=row["exchange"],
                        country=row["country"],
                        currency=row["currency"],
                        sector=row.get("sector") or None,
                        industry=row.get("industry") or None,
                        market_cap=float(row["market_cap"]) if row.get("market_cap") else None,
                        average_daily_volume=(
                            float(row["average_daily_volume"])
                            if row.get("average_daily_volume")
                            else None
                        ),
                        active=row.get("active", "true").lower() == "true",
                        aliases=[
                            alias.strip()
                            for alias in row.get("aliases", "").split("|")
                            if alias.strip()
                        ],
                    )
                )
        return cls(records)


def sample_symbol_master() -> InMemorySymbolMaster:
    """Return representative US and Canadian symbols for synthetic examples."""

    return InMemorySymbolMaster(
        [
            SymbolRecord(
                ticker="NVDA",
                company_name="NVIDIA Corporation",
                aliases=["NVIDIA", "Nvidia Corp"],
                exchange="NASDAQ",
                country="US",
                currency="USD",
                sector="Technology",
                industry="Semiconductors",
                market_cap=3_000_000_000_000,
                average_daily_volume=300_000_000,
            ),
            SymbolRecord(
                ticker="AAPL",
                company_name="Apple Inc.",
                aliases=["Apple"],
                exchange="NASDAQ",
                country="US",
                currency="USD",
                sector="Technology",
                industry="Consumer Electronics",
                market_cap=3_000_000_000_000,
                average_daily_volume=50_000_000,
            ),
            SymbolRecord(
                ticker="TSLA",
                company_name="Tesla, Inc.",
                aliases=["Tesla"],
                exchange="NASDAQ",
                country="US",
                currency="USD",
                sector="Consumer Cyclical",
                industry="Auto Manufacturers",
                market_cap=700_000_000_000,
                average_daily_volume=90_000_000,
            ),
            SymbolRecord(
                ticker="SHOP",
                company_name="Shopify Inc.",
                aliases=["Shopify"],
                exchange="TSX",
                country="CA",
                currency="CAD",
                sector="Technology",
                industry="Software",
                market_cap=140_000_000_000,
                average_daily_volume=3_000_000,
            ),
            SymbolRecord(
                ticker="RY",
                company_name="Royal Bank of Canada",
                aliases=["Royal Bank", "RBC"],
                exchange="TSX",
                country="CA",
                currency="CAD",
                sector="Financial Services",
                industry="Banks",
                market_cap=280_000_000_000,
                average_daily_volume=4_000_000,
            ),
            SymbolRecord(
                ticker="AI",
                company_name="C3.ai, Inc.",
                aliases=["C3.ai"],
                exchange="NYSE",
                country="US",
                currency="USD",
                sector="Technology",
                industry="Software",
                market_cap=4_000_000_000,
                average_daily_volume=5_000_000,
            ),
            SymbolRecord(
                ticker="A",
                company_name="Agilent Technologies, Inc.",
                aliases=["Agilent Technologies", "Agilent"],
                exchange="NYSE",
                country="US",
                currency="USD",
                sector="Healthcare",
                industry="Diagnostics",
                market_cap=40_000_000_000,
                average_daily_volume=2_000_000,
            ),
        ]
    )
