"""Read-only collector contract."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from traderresearch.models import SocialContent


class RedditCollector(Protocol):
    """Only collection is exposed; mutating Reddit actions are intentionally absent."""

    def collect(self) -> Iterable[SocialContent]:
        """Return permitted public content from a configured source."""
        ...
