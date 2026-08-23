"""Deterministic event classification with structured output."""

from __future__ import annotations

from typing import Protocol

from traderresearch.models import EventResult


class EventClassifier(Protocol):
    def classify(self, text: str) -> EventResult: ...


class KeywordEventClassifier:
    _EVENTS: tuple[tuple[str, tuple[str, ...], float], ...] = (
        ("earnings_guidance", ("earnings", "guidance", "revenue", "quarter"), 0.90),
        ("merger_acquisition", ("acquisition", "acquire", "merger", "takeover"), 0.90),
        ("regulatory", ("regulator", "approval", "investigation", "lawsuit"), 0.80),
        ("product_launch", ("launch", "product", "release", "chip"), 0.65),
        ("analyst_action", ("analyst", "upgrade", "downgrade", "price target"), 0.55),
        ("promotion", ("guaranteed", "moon", "buy now", "can't lose"), 0.35),
    )

    def classify(self, text: str) -> EventResult:
        lowered = text.casefold()
        ranked: list[tuple[int, str, float]] = []
        for event_type, keywords, importance in self._EVENTS:
            matches = sum(keyword in lowered for keyword in keywords)
            if matches:
                ranked.append((matches, event_type, importance))
        if not ranked:
            return EventResult(event_type="general_discussion", strength=0.2, confidence=0.4)
        matches, event_type, importance = max(ranked)
        return EventResult(
            event_type=event_type,
            strength=min(1.0, importance * (0.75 + matches * 0.1)),
            confidence=min(0.95, 0.55 + matches * 0.12),
            new_information=event_type
            in {"earnings_guidance", "merger_acquisition", "regulatory", "product_launch"},
            primary_source_confirmed=False,
        )
