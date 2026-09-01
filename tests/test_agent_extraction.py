"""
These tests prove the full extraction and tool pipeline works correctly with
zero live LLM calls, per the hackathon's no-live-model-required testing
requirement.
"""

import json

import pytest

from src.models import Post, PostType, PostStatus, Urgency
from src.agent import extract_post

from src.tools.category_tool import category_match_impl
from src.tools.geo_tool import geo_distance_impl
from src.tools.score_tool import score_match_impl
from src.tools.duplicate_tool import duplicate_check_impl
from src.tools.sla_tool import sla_check_impl


# ---------------------------------------------------------------------------
# A fake Agent that never makes a network/model call.
# ---------------------------------------------------------------------------

class FakeAgentClass:
    """Constructor accepts arbitrary kwargs; instances are callable and return
    a canned JSON string matching the extraction schema, regardless of prompt."""

    CANNED_RESPONSE = (
        '{"category": "food", "description": "canned", "location_zone": "pasadena", '
        '"urgency": "soon", "quantity": 3, "contact": "unknown", "timeframe": null}'
    )

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __call__(self, prompt):
        return self.CANNED_RESPONSE


class RaisingAgentClass:
    """A fake Agent whose call always raises, to exercise extract_post's
    fallback-on-exception path."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __call__(self, prompt):
        raise RuntimeError("simulated model failure")


class ExplodingOnInitAgentClass:
    """A fake Agent that raises the instant it is constructed. Used to prove
    that extract_post(..., model=None) never touches strands.Agent at all --
    if it did, this class's constructor would blow up the test."""

    def __init__(self, **kwargs):
        raise AssertionError(
            "src.agent.Agent must never be constructed when model=None"
        )

    def __call__(self, prompt):
        raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# (1) Deterministic fallback extraction, no model/network call.
# ---------------------------------------------------------------------------

def test_extract_post_fallback_urgent_water_need(monkeypatch):
    monkeypatch.setattr("src.agent.Agent", ExplodingOnInitAgentClass)

    post = extract_post("URGENT need water in Altadena, family of 4", "need", model=None)

    assert isinstance(post, Post)
    assert post.type == PostType.NEED
    assert post.category == "water"
    assert post.urgency == Urgency.URGENT
    assert post.location_zone == "altadena"
    assert post.quantity == 4
    assert post.raw_text == "URGENT need water in Altadena, family of 4"


def test_extract_post_fallback_generator_offer(monkeypatch):
    monkeypatch.setattr("src.agent.Agent", ExplodingOnInitAgentClass)

    post = extract_post(
        "have a generator to lend in Highland Park, available this week", "offer", model=None
    )

    assert isinstance(post, Post)
    assert post.type == PostType.OFFER
    assert post.category == "power"
    assert post.location_zone == "highland park"
    assert post.urgency == Urgency.SOON  # matched via "this week"
    assert post.quantity is None  # no digits in the raw text


def test_extract_post_fallback_messy_ambiguous_text(monkeypatch):
    monkeypatch.setattr("src.agent.Agent", ExplodingOnInitAgentClass)

    raw_text = "idk??? something maybe for someone, not sure region or timing"
    post = extract_post(raw_text, "need", model=None)

    assert isinstance(post, Post)
    assert post.category == "other"  # no taxonomy synonym present
    assert post.location_zone == "unknown"  # no gazetteer zone present
    assert post.urgency == Urgency.FLEXIBLE  # no urgency keywords present
    assert post.quantity is None  # no digits present
    assert post.raw_text == raw_text


def test_extract_post_model_none_never_touches_agent(monkeypatch):
    """model=None must never construct or call strands.Agent -- proven by
    swapping in a fake Agent whose constructor raises if invoked."""
    monkeypatch.setattr("src.agent.Agent", ExplodingOnInitAgentClass)
    # If extract_post touched Agent at all, this would raise AssertionError.
    post = extract_post("need water in Pasadena", "need", model=None)
    assert isinstance(post, Post)


# ---------------------------------------------------------------------------
# (2) The model-mocking seam: src.agent.Agent monkeypatched with a fake that
# returns a canned JSON response -- proves the parsing path with zero network.
# ---------------------------------------------------------------------------

def test_extract_post_with_mocked_agent_parses_canned_json(monkeypatch):
    monkeypatch.setattr("src.agent.Agent", FakeAgentClass)

    post = extract_post("some raw text", "offer", model=object())

    assert isinstance(post, Post)
    assert post.type == PostType.OFFER
    assert post.category == "food"
    assert post.description == "canned"
    assert post.location_zone == "pasadena"
    assert post.urgency == Urgency.SOON
    assert post.quantity == 3
    assert post.contact == "unknown"
    assert post.timeframe is None
    assert post.raw_text == "some raw text"


# ---------------------------------------------------------------------------
# (3) If the fake Agent's call raises, extract_post falls back gracefully
# rather than propagating the exception.
# ---------------------------------------------------------------------------

def test_extract_post_falls_back_when_agent_call_raises(monkeypatch):
    monkeypatch.setattr("src.agent.Agent", RaisingAgentClass)

    raw_text = "URGENT need water in Altadena, family of 4"
    post = extract_post(raw_text, "need", model=object())

    # No exception propagated -- we got a valid Post back via the fallback path.
    assert isinstance(post, Post)
    assert post.type == PostType.NEED
    assert post.category == "water"
    assert post.urgency == Urgency.URGENT
    assert post.location_zone == "altadena"
    assert post.raw_text == raw_text


# ---------------------------------------------------------------------------
# (4) Direct unit tests of each tools/*_impl plain function.
# ---------------------------------------------------------------------------

def test_category_match_impl():
    assert category_match_impl("water", "water") is True
    assert category_match_impl("water", "childcare") is False
    # Underlying category_matches handles None gracefully rather than raising.
    assert category_match_impl(None, None) is True
    assert category_match_impl(None, "water") is False


def test_geo_distance_impl_known_and_unknown_zones():
    distance = geo_distance_impl("eagle rock", "pasadena")
    assert isinstance(distance, float)
    assert 2.0 <= distance <= 10.0

    # Unknown zone name is handled gracefully: sentinel -1.0, not an exception.
    assert geo_distance_impl("nowhereville", "pasadena") == -1.0
    assert geo_distance_impl("eagle rock", "nowhereville") == -1.0


def test_score_match_impl_valid_json():
    need_json = json.dumps(
        {
            "id": "need-1",
            "type": "need",
            "category": "water",
            "description": "need water",
            "location_zone": "altadena",
            "urgency": "urgent",
            "contact": "test@example.com",
            "quantity": 4,
        }
    )
    offer_json = json.dumps(
        {
            "id": "offer-1",
            "type": "offer",
            "category": "water",
            "description": "have water",
            "location_zone": "pasadena",
            "urgency": "flexible",
            "contact": "test2@example.com",
            "quantity": 10,
        }
    )
    result = json.loads(score_match_impl(need_json, offer_json))
    assert "score" in result
    assert result["score"] > 0.0
    assert "reasons" in result
    assert isinstance(result["reasons"], list)


def test_score_match_impl_malformed_json_returns_error_not_raise():
    result = json.loads(score_match_impl("not valid json", "{}"))
    assert "error" in result


def test_duplicate_check_impl_valid_json():
    shared = {
        "id": "id-a",
        "type": "need",
        "category": "water",
        "description": "family needs bottled water urgently in altadena",
        "location_zone": "altadena",
        "urgency": "urgent",
        "contact": "a@example.com",
        "created_at": "2025-01-15T09:00:00+00:00",
    }
    post_a_json = json.dumps(shared)
    post_b = dict(shared)
    post_b["id"] = "id-b"
    post_b["contact"] = "b@example.com"
    post_b["created_at"] = "2025-01-15T09:05:00+00:00"
    post_b_json = json.dumps(post_b)

    assert duplicate_check_impl(post_a_json, post_b_json) is True


def test_duplicate_check_impl_malformed_json_returns_false_not_raise():
    assert duplicate_check_impl("not valid json", "{}") is False
    assert duplicate_check_impl("{}", "{}") is False  # missing required fields


def test_sla_check_impl_valid_json_flags_urgent_breach():
    needs_json = json.dumps(
        [
            {
                "id": "need-old",
                "type": "need",
                "category": "water",
                "description": "urgent need, long overdue",
                "location_zone": "altadena",
                "urgency": "urgent",
                "contact": "a@example.com",
                "status": "open",
                "created_at": "2020-01-01T00:00:00+00:00",
            }
        ]
    )
    result = json.loads(sla_check_impl(needs_json))
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "need-old"
    assert result[0]["urgency"] == "urgent"


def test_sla_check_impl_malformed_json_returns_error_not_raise():
    result = json.loads(sla_check_impl("not a json array"))
    assert "error" in result
