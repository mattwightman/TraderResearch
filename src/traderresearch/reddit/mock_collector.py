"""Collector backed exclusively by bundled synthetic data."""

from __future__ import annotations

import json
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path

from traderresearch.models import SocialContent


class MockRedditCollector:
    def __init__(self, sample_path: Path | None = None) -> None:
        self._sample_path = sample_path

    def collect(self) -> Iterable[SocialContent]:
        if self._sample_path is not None:
            raw = self._sample_path.read_text(encoding="utf-8")
        else:
            raw = (
                files("traderresearch")
                .joinpath("data/synthetic_reddit.json")
                .read_text(encoding="utf-8")
            )
        document = json.loads(raw)
        if not isinstance(document, list):
            raise ValueError("Synthetic sample data must contain a JSON array.")
        return [SocialContent.model_validate(item) for item in document]
