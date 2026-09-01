"""Tests for src.matching: distance, category matching, scoring, and proposal generation."""

import pytest

from src.models import Post, PostType, PostStatus, Urgency, ZONE_GAZETTEER
from src.matching import (
    geo_distance_miles,
    zone_coords,
    zone_distance_miles,
    category_matches,
    score_match,
    propose_matches,
)


def _make_post(**overrides):
    defaults = dict(
        type=PostType.NEED,
        category="water",
        description="need water",
        location_zone="altadena",
        urgency=Urgency.FLEXIBLE,
        contact="test@example.com",
        quantity=None,
        status=PostStatus.OPEN,
    )
    defaults.update(overrides)
    return Post.new(**defaults)


# ---------------------------------------------------------------------------
# geo_distance_miles / zone_distance_miles
# ---------------------------------------------------------------------------

def test_geo_distance_miles_known_pair_in_sane_range():
    lat1, lon1 = ZONE_GAZETTEER["eagle rock"]
    lat2, lon2 = ZONE_GAZETTEER["pasadena"]
    distance = geo_distance_miles(lat1, lon1, lat2, lon2)
    assert 2.0 <= distance <= 10.0


def test_geo_distance_miles_self_is_near_zero():
    lat1, lon1 = ZONE_GAZETTEER["eagle rock"]
    distance = geo_distance_miles(lat1, lon1, lat1, lon1)
    assert distance == pytest.approx(0.0, abs=1e-6)


def test_zone_distance_miles_unknown_zone_returns_none():
    assert zone_distance_miles("eagle rock", "nowhereville") is None
    assert zone_distance_miles("nowhereville", "pasadena") is None
    assert zone_distance_miles("nowhereville", "also-nowhere") is None


def test_zone_coords_known_and_unknown():
    assert zone_coords("eagle rock") == ZONE_GAZETTEER["eagle rock"]
    assert zone_coords("Eagle Rock") == ZONE_GAZETTEER["eagle rock"]
    assert zone_coords("nowhereville") is None


# ---------------------------------------------------------------------------
# category_matches
# ---------------------------------------------------------------------------

def test_category_matches_identical_categories():
    assert category_matches("water", "water") is True
    assert category_matches("Water", "water") is True


def test_category_matches_unrelated_categories_false():
    assert category_matches("water", "childcare") is False


# ---------------------------------------------------------------------------
# score_match
# ---------------------------------------------------------------------------

def test_score_match_category_mismatch_scores_zero():
    need = _make_post(type=PostType.NEED, category="water", location_zone="altadena")
    offer = _make_post(type=PostType.OFFER, category="childcare", location_zone="altadena")
    score, reasons = score_match(need, offer)
    assert score == 0.0
    assert any("category mismatch" in r for r in reasons)


def test_score_match_nearby_zone_scores_higher_than_unknown_zone():
    need = _make_post(
        type=PostType.NEED, category="water", location_zone="altadena", urgency=Urgency.FLEXIBLE
    )
    offer_nearby = _make_post(
        type=PostType.OFFER, category="water", location_zone="pasadena", urgency=Urgency.FLEXIBLE
    )
    offer_far_unknown = _make_post(
        type=PostType.OFFER, category="water", location_zone="nowhereville", urgency=Urgency.FLEXIBLE
    )

    score_nearby, _ = score_match(need, offer_nearby)
    score_unknown, _ = score_match(need, offer_far_unknown)

    assert score_nearby > score_unknown


# ---------------------------------------------------------------------------
# propose_matches
# ---------------------------------------------------------------------------

def test_propose_matches_on_sample_posts(sample_posts):
    needs = [p for p in sample_posts if p.type == PostType.NEED]
    offers = [p for p in sample_posts if p.type == PostType.OFFER]

    proposals = propose_matches(needs, offers, min_score=0.4)

    assert len(proposals) > 0

    # All returned proposals must be at or above min_score.
    for p in proposals:
        assert p.score >= 0.4

    # Sorted descending by score.
    scores = [p.score for p in proposals]
    assert scores == sorted(scores, reverse=True)

    # Never a match between two posts of the same type.
    need_ids = {n.id for n in needs}
    offer_ids = {o.id for o in offers}
    for p in proposals:
        assert p.need_id in need_ids
        assert p.offer_id in offer_ids
        assert p.need_id not in offer_ids
        assert p.offer_id not in need_ids


def test_propose_matches_never_pairs_same_type():
    need_a = _make_post(type=PostType.NEED, category="water", location_zone="altadena")
    need_b = _make_post(type=PostType.NEED, category="water", location_zone="pasadena")
    offer_a = _make_post(type=PostType.OFFER, category="water", location_zone="altadena")

    proposals = propose_matches([need_a, need_b], [offer_a], min_score=0.0)

    for p in proposals:
        assert p.need_id in (need_a.id, need_b.id)
        assert p.offer_id == offer_a.id
    # Specifically, need_a/need_b should never appear paired with each other.
    pairs = {(p.need_id, p.offer_id) for p in proposals}
    assert (need_a.id, need_b.id) not in pairs
    assert (need_b.id, need_a.id) not in pairs
