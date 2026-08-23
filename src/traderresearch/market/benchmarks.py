"""Benchmark selection without a one-index-fits-all assumption."""

from __future__ import annotations

from typing import Protocol

from traderresearch.models import SymbolRecord


class BenchmarkSelector(Protocol):
    def select(self, symbol: SymbolRecord) -> str: ...


class SectorBenchmarkSelector:
    """Configurable country/sector mapping with broad-market fallbacks."""

    def __init__(
        self,
        sector_mapping: dict[tuple[str, str], str] | None = None,
        country_mapping: dict[str, str] | None = None,
    ) -> None:
        self._sector_mapping = sector_mapping or {
            ("US", "Technology"): "QQQ",
            ("US", "Financial Services"): "XLF",
            ("US", "Healthcare"): "XLV",
            ("CA", "Technology"): "XIT.TO",
            ("CA", "Financial Services"): "XFN.TO",
        }
        self._country_mapping = country_mapping or {"US": "SPY", "CA": "XIC.TO"}

    def select(self, symbol: SymbolRecord) -> str:
        if symbol.sector:
            selected = self._sector_mapping.get((symbol.country, symbol.sector))
            if selected:
                return selected
        try:
            return self._country_mapping[symbol.country]
        except KeyError as error:
            raise LookupError(
                f"No benchmark is configured for country {symbol.country}."
            ) from error
