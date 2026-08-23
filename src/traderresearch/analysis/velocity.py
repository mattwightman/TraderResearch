"""Discussion-velocity measurements with safe low-volume handling."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from traderresearch.models import DiscussionVelocity, SocialContent


def calculate_discussion_velocity(
    content: Sequence[SocialContent],
    now: datetime,
    *,
    historical_hours: int = 24,
    baseline_floor: float = 0.25,
) -> DiscussionVelocity:
    """Compare recent counts to rates observed before the current hour."""

    five_minutes_ago = now - timedelta(minutes=5)
    one_hour_ago = now - timedelta(hours=1)
    history_start = now - timedelta(hours=historical_hours)
    recent_5m = [item for item in content if five_minutes_ago <= item.created_utc <= now]
    recent_1h = [item for item in content if one_hour_ago <= item.created_utc <= now]
    historical = [item for item in content if history_start <= item.created_utc < one_hour_ago]

    historical_duration_hours = max(historical_hours - 1, 1)
    average_1h = len(historical) / historical_duration_hours
    average_5m = average_1h / 12
    expected_1h = max(average_1h, baseline_floor)
    expected_5m = max(average_5m, baseline_floor / 12)
    velocity_5m = len(recent_5m) / expected_5m
    velocity_1h = len(recent_1h) / expected_1h

    return DiscussionVelocity(
        current_mentions_5m=len(recent_5m),
        current_mentions_1h=len(recent_1h),
        historical_average_5m=average_5m,
        historical_average_1h=average_1h,
        mention_velocity=(velocity_5m + velocity_1h) / 2,
        unique_authors=len({item.author_identifier for item in recent_1h}),
        comment_velocity=sum(item.num_comments for item in recent_1h) / 60,
        score_velocity=sum(max(item.score, 0) for item in recent_1h) / 60,
    )
