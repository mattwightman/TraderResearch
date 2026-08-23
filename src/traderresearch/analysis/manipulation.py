"""Preliminary coordinated-promotion indicators."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from datetime import timedelta

from traderresearch.models import ManipulationAssessment, SocialContent

_URL = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)


def _normalized_text(content: SocialContent) -> str:
    text = _URL.sub("", content.text.casefold())
    return " ".join(re.findall(r"[a-z0-9$]+", text))


def assess_manipulation(content: Sequence[SocialContent]) -> ManipulationAssessment:
    """Score repeated wording, URLs, author/source concentration, and posting bursts."""

    if not content:
        return ManipulationAssessment(score=0, flags=[])
    flags: list[str] = []
    components: list[float] = []

    normalized = [_normalized_text(item) for item in content]
    duplicate_count = sum(count - 1 for count in Counter(normalized).values() if count > 1)
    duplicate_ratio = duplicate_count / len(content)
    if duplicate_ratio >= 0.25:
        flags.append("highly_similar_wording")
        components.append(min(1.0, duplicate_ratio * 1.5))

    urls = [url.casefold() for item in content for url in _URL.findall(item.text)]
    repeated_urls = sum(count - 1 for count in Counter(urls).values() if count > 1)
    if repeated_urls:
        flags.append("repeated_urls")
        components.append(min(1.0, repeated_urls / max(len(content), 1)))

    author_counts = Counter(item.author_identifier for item in content)
    author_concentration = max(author_counts.values()) / len(content)
    if len(content) >= 3 and author_concentration >= 0.6:
        flags.append("author_concentration")
        components.append(author_concentration)

    source_counts = Counter(item.subreddit for item in content)
    source_concentration = max(source_counts.values()) / len(content)
    if len(content) >= 4 and source_concentration >= 0.8:
        flags.append("source_concentration")
        components.append(source_concentration * 0.6)

    ordered = sorted(item.created_utc for item in content)
    in_ten_minutes = max(
        (
            sum(timestamp <= other <= timestamp + timedelta(minutes=10) for other in ordered)
            for timestamp in ordered
        ),
        default=0,
    )
    burst_ratio = in_ten_minutes / len(content)
    if len(content) >= 3 and burst_ratio >= 0.6:
        flags.append("synchronized_posting_burst")
        components.append(burst_ratio * 0.75)

    promotional = sum(
        any(
            term in item.text.casefold() for term in ("guaranteed", "buy now", "can't lose", "moon")
        )
        for item in content
    )
    if promotional / len(content) >= 0.4:
        flags.append("repeated_ticker_promotion")
        components.append(min(1.0, promotional / len(content)))

    score = min(1.0, sum(components) / max(len(components), 1)) if components else 0.0
    return ManipulationAssessment(score=score, flags=flags)
