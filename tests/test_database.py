from __future__ import annotations

from datetime import datetime

from conftest import make_content

from traderresearch.reddit.mock_collector import MockRedditCollector
from traderresearch.storage.repository import ResearchRepository


def test_ingest_is_idempotent(repository: ResearchRepository, now: datetime) -> None:
    content = make_content(created_at=now)
    assert repository.ingest_content([content]) == 1
    assert repository.ingest_content([content]) == 0
    assert repository.record_counts()["content"] == 1
    stored = repository.list_content()[0]
    assert stored.post_or_comment_id == content.post_or_comment_id


def test_bundled_sample_is_valid_and_synthetic() -> None:
    content = list(MockRedditCollector().collect())
    assert len(content) >= 15
    assert all(item.post_or_comment_id.startswith("synthetic_") for item in content)
    assert all(item.author_identifier.startswith("research_user_") for item in content)
