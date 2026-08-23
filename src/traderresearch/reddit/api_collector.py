"""Approved Reddit Data API collector boundary.

No undocumented endpoints, webpage scraping, or account actions are implemented.
"""

from __future__ import annotations

from collections.abc import Iterable

from traderresearch.config import RedditConfig
from traderresearch.models import SocialContent


class RedditApiCollector:
    """Future read-only adapter requiring explicitly approved credentials."""

    def __init__(self, config: RedditConfig) -> None:
        config.require_api_credentials()
        self._config = config

    def collect(self) -> Iterable[SocialContent]:
        raise NotImplementedError(
            "Approved Reddit Data API access is not configured in this release. "
            "Use mock mode with bundled synthetic data."
        )
