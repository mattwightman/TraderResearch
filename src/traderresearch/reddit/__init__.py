"""Read-only Reddit collection interfaces."""

from traderresearch.reddit.interface import RedditCollector
from traderresearch.reddit.mock_collector import MockRedditCollector

__all__ = ["MockRedditCollector", "RedditCollector"]
