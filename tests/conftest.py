"""Shared pytest fixtures for the neighbor-dispatch test suite."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.models import Post, PostType, PostStatus, Urgency

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_posts():
    """Load tests/fixtures/sample_posts.json and return a list of Post objects."""
    with open(FIXTURES_DIR / "sample_posts.json", "r", encoding="utf-8") as f:
        raw_posts = json.load(f)

    posts = []
    for d in raw_posts:
        posts.append(
            Post.new(
                type=PostType(d["type"]),
                urgency=Urgency(d["urgency"]),
                status=PostStatus.OPEN,
                **{k: v for k, v in d.items() if k not in ("type", "urgency")},
            )
        )
    return posts


@pytest.fixture
def now_fixed():
    """A fixed, timezone-aware 'current time' for deterministic time-based tests."""
    return datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
