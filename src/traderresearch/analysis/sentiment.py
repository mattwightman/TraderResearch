"""Simple deterministic sentiment boundary, replaceable by structured providers."""

from __future__ import annotations

import re
from typing import Protocol

from traderresearch.models import SentimentLabel, SentimentResult


class SentimentClassifier(Protocol):
    def classify(self, text: str) -> SentimentResult: ...


class LexiconSentimentClassifier:
    POSITIVE = frozenset(
        {
            "beat",
            "bullish",
            "growth",
            "improved",
            "raises",
            "strong",
            "surge",
            "upgrade",
            "upside",
        }
    )
    NEGATIVE = frozenset(
        {
            "bearish",
            "cut",
            "decline",
            "downgrade",
            "miss",
            "risk",
            "slowing",
            "weak",
            "warning",
        }
    )

    def classify(self, text: str) -> SentimentResult:
        words = re.findall(r"[a-z]+", text.casefold())
        positive = sum(word in self.POSITIVE for word in words)
        negative = sum(word in self.NEGATIVE for word in words)
        total = positive + negative
        score = (positive - negative) / max(total, 1)
        label = (
            SentimentLabel.BULLISH
            if score > 0.15
            else SentimentLabel.BEARISH
            if score < -0.15
            else SentimentLabel.NEUTRAL
        )
        confidence = min(1.0, 0.35 + total * 0.12) if total else 0.25
        return SentimentResult(score=score, label=label, confidence=confidence)
