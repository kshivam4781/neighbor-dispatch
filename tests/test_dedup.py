"""Tests for src.dedup: duplicate post detection."""

import pytest

from src.models import Post, PostType, PostStatus, Urgency
from src.dedup import is_duplicate, find_duplicates


def _make_post(**overrides):
    defaults = dict(
        type=PostType.NEED,
        category="water",
        description="need water",
        location_zone="altadena",
        urgency=Urgency.FLEXIBLE,
        contact="test@example.com",
        status=PostStatus.OPEN,
        created_at="2025-01-15T09:00:00+00:00",
    )
    defaults.update(overrides)
    return Post.new(**defaults)


def test_is_duplicate_false_for_different_types():
    post_a = _make_post(
        type=PostType.NEED,
        category="water",
        location_zone="altadena",
        description="family needs bottled water urgently",
        created_at="2025-01-15T09:00:00+00:00",
    )
    post_b = _make_post(
        type=PostType.OFFER,
        category="water",
        location_zone="altadena",
        description="family needs bottled water urgently",
        created_at="2025-01-15T09:05:00+00:00",
    )
    assert is_duplicate(post_a, post_b) is False


def test_is_duplicate_true_for_near_identical_same_category_zone_close_in_time():
    post_a = _make_post(
        type=PostType.NEED,
        category="water",
        location_zone="altadena",
        description="Family of 4 in Altadena urgently needs bottled water after the storm",
        contact="maria@example.com",
        created_at="2025-01-15T09:00:00+00:00",
    )
    post_b = _make_post(
        type=PostType.NEED,
        category="water",
        location_zone="altadena",
        description="Family of 4 in Altadena urgently need bottled water after the storm",
        contact="gabriela@example.com",
        created_at="2025-01-15T09:08:00+00:00",
    )
    assert is_duplicate(post_a, post_b, time_window_minutes=120) is True


def test_is_duplicate_false_once_time_gap_exceeds_window():
    post_a = _make_post(
        type=PostType.NEED,
        category="water",
        location_zone="altadena",
        description="Family of 4 in Altadena urgently needs bottled water after the storm",
        contact="maria@example.com",
        created_at="2025-01-15T09:00:00+00:00",
    )
    post_b = _make_post(
        type=PostType.NEED,
        category="water",
        location_zone="altadena",
        description="Family of 4 in Altadena urgently need bottled water after the storm",
        contact="gabriela@example.com",
        created_at="2025-01-15T12:00:00+00:00",  # 180 minutes later
    )
    assert is_duplicate(post_a, post_b, time_window_minutes=120) is False


def test_find_duplicates_on_sample_posts_finds_intentional_pair_once(sample_posts):
    pairs = find_duplicates(sample_posts, time_window_minutes=120)

    assert len(pairs) >= 1

    # Every pair should only appear once (no reverse duplicate of the same pair).
    seen_id_pairs = set()
    for post_a, post_b in pairs:
        key = tuple(sorted((post_a.id, post_b.id)))
        assert key not in seen_id_pairs
        seen_id_pairs.add(key)

    # The intentional near-duplicate pair is the two Altadena "water" needs.
    water_altadena_needs = [
        p
        for p in sample_posts
        if p.type == PostType.NEED
        and p.category == "water"
        and p.location_zone == "altadena"
    ]
    assert len(water_altadena_needs) == 2

    found_ids = set()
    for post_a, post_b in pairs:
        found_ids.add(post_a.id)
        found_ids.add(post_b.id)

    expected_ids = {p.id for p in water_altadena_needs}
    assert expected_ids.issubset(found_ids)
