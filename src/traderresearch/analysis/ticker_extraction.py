"""Context-aware ticker and company-name extraction."""

from __future__ import annotations

import re
from typing import Protocol

from traderresearch.market.symbols import SymbolMaster
from traderresearch.models import TickerMention

AMBIGUOUS_TICKERS = frozenset(
    {"A", "IT", "ON", "ALL", "FOR", "ARE", "CAN", "LOVE", "AI", "NOW", "SO"}
)
_CASHTAG = re.compile(r"(?<!\w)\$([A-Za-z][A-Za-z.\-]{0,9})(?!\w)")
_UPPER_TOKEN = re.compile(r"(?<![$\w])([A-Z][A-Z.\-]{0,9})(?!\w)")


class TickerExtractor(Protocol):
    def extract(self, content_id: str, text: str, created_utc: object) -> list[TickerMention]: ...


class DeterministicTickerExtractor:
    """Resolve cashtags, unambiguous uppercase tickers, and company aliases."""

    def __init__(self, symbol_master: SymbolMaster) -> None:
        self._symbols = symbol_master

    def extract(self, content_id: str, text: str, created_utc: object) -> list[TickerMention]:
        from datetime import datetime

        if not isinstance(created_utc, datetime):
            raise TypeError("created_utc must be a datetime")
        found: dict[str, TickerMention] = {}

        for match in _CASHTAG.finditer(text):
            ticker = match.group(1).upper()
            symbol = self._symbols.get(ticker)
            if symbol:
                found[ticker] = TickerMention(
                    content_id=content_id,
                    ticker=ticker,
                    company_name=symbol.company_name,
                    matched_text=match.group(0),
                    extraction_method="cashtag",
                    confidence=0.99,
                    created_utc=created_utc,
                )

        for match in _UPPER_TOKEN.finditer(text):
            ticker = match.group(1)
            if ticker in found or ticker in AMBIGUOUS_TICKERS:
                continue
            symbol = self._symbols.get(ticker)
            if symbol:
                found[ticker] = TickerMention(
                    content_id=content_id,
                    ticker=ticker,
                    company_name=symbol.company_name,
                    matched_text=match.group(0),
                    extraction_method="ticker",
                    confidence=0.90,
                    created_utc=created_utc,
                )

        candidates = sorted(
            self._symbols.active_symbols(),
            key=lambda symbol: max(
                [len(symbol.company_name), *(len(alias) for alias in symbol.aliases)]
            ),
            reverse=True,
        )
        for symbol in candidates:
            if symbol.ticker in found:
                continue
            names = sorted({symbol.company_name, *symbol.aliases}, key=len, reverse=True)
            for name in names:
                if len(name) < 3:
                    continue
                company_match = re.search(
                    rf"(?<!\w){re.escape(name)}(?!\w)", text, flags=re.IGNORECASE
                )
                if company_match:
                    found[symbol.ticker] = TickerMention(
                        content_id=content_id,
                        ticker=symbol.ticker,
                        company_name=symbol.company_name,
                        matched_text=company_match.group(0),
                        extraction_method="company",
                        confidence=0.95,
                        created_utc=created_utc,
                    )
                    break
        return sorted(found.values(), key=lambda mention: mention.ticker)
