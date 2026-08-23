from __future__ import annotations

from datetime import datetime

from traderresearch.analysis.ticker_extraction import DeterministicTickerExtractor
from traderresearch.market.symbols import sample_symbol_master


def _tickers(text: str, now: datetime) -> set[str]:
    extractor = DeterministicTickerExtractor(sample_symbol_master())
    return {item.ticker for item in extractor.extract("synthetic", text, now)}


def test_extracts_ticker_cashtag_and_company_aliases(now: datetime) -> None:
    assert _tickers("NVDA and $SHOP are being compared with Apple.", now) == {
        "AAPL",
        "NVDA",
        "SHOP",
    }
    assert _tickers("Nvidia Corp raised guidance.", now) == {"NVDA"}
    assert _tickers("NVIDIA launched a chip.", now) == {"NVDA"}


def test_rejects_ambiguous_english_words(now: datetime) -> None:
    text = "A quiet day: it is on for all who are ready and can love AI now, so wait."
    assert _tickers(text, now) == set()


def test_explicit_known_cashtag_can_resolve_ambiguous_symbol(now: datetime) -> None:
    assert _tickers("$AI reported earnings, while AI is also a broad topic.", now) == {"AI"}
    assert _tickers("AI reported earnings.", now) == set()


def test_unknown_uppercase_tokens_are_ignored(now: datetime) -> None:
    assert _tickers("FAKE XYZQ and $NOPE are not in the symbol master.", now) == set()
