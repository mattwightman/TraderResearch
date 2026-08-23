from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from traderresearch.models import SocialContent
from traderresearch.storage.database import Database
from traderresearch.storage.repository import ResearchRepository


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 2, 1, 15, 0, tzinfo=UTC)


@pytest.fixture
def repository(tmp_path: Path) -> ResearchRepository:
    database = Database.from_sqlite_path(tmp_path / "test.sqlite3")
    database.initialize_schema()
    return ResearchRepository(database)


def make_content(
    *,
    content_id: str = "synthetic_test_001",
    text: str = "NVDA earnings were strong",
    created_at: datetime,
    author: str = "research_user_test",
    subreddit: str = "sample_test",
    score: int = 10,
    comments: int = 2,
) -> SocialContent:
    return SocialContent(
        subreddit=subreddit,
        content_type="post",
        post_or_comment_id=content_id,
        author_identifier=author,
        created_utc=created_at,
        title=text,
        score=score,
        num_comments=comments,
        permalink=f"/synthetic/{content_id}",
        retrieved_at=created_at,
    )
