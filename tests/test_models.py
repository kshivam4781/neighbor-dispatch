"""Tests for src.models: Post/MatchProposal construction defaults."""

import uuid
from datetime import datetime

import pytest

from src.models import Post, PostType, PostStatus, Urgency, MatchProposal


def test_post_new_autogenerates_uuid_id():
    post = Post.new(
        type=PostType.NEED,
        category="water",
        description="need water",
        location_zone="altadena",
        urgency=Urgency.URGENT,
        contact="a@example.com",
    )
    assert post.id  # non-empty
    # Must parse as a valid UUID (this is what "UUID-format id" means).
    parsed = uuid.UUID(post.id)
    assert str(parsed) == post.id


def test_post_new_defaults_status_open():
    post = Post.new(
        type=PostType.OFFER,
        category="food",
        description="have food",
        location_zone="pasadena",
        urgency=Urgency.FLEXIBLE,
        contact="b@example.com",
    )
    assert post.status == PostStatus.OPEN


def test_post_new_defaults_created_at_to_parseable_iso_string():
    post = Post.new(
        type=PostType.NEED,
        category="food",
        description="need food",
        location_zone="eagle rock",
        urgency=Urgency.SOON,
        contact="c@example.com",
    )
    assert isinstance(post.created_at, str)
    # Must not raise -- proves it's a well-formed ISO 8601 string.
    parsed = datetime.fromisoformat(post.created_at)
    assert isinstance(parsed, datetime)


def test_post_new_respects_explicit_id_and_created_at():
    explicit_id = "my-custom-id-123"
    explicit_created_at = "2025-01-01T00:00:00+00:00"
    post = Post.new(
        id=explicit_id,
        type=PostType.NEED,
        category="water",
        description="need water",
        location_zone="altadena",
        urgency=Urgency.URGENT,
        contact="d@example.com",
        created_at=explicit_created_at,
    )
    assert post.id == explicit_id
    assert post.created_at == explicit_created_at


def test_match_proposal_new_defaults_status_to_pending_exactly():
    """Safety-critical: a freshly created match proposal must NEVER default to
    any status other than 'pending', since nothing downstream may treat a
    match as approved until a human explicitly approves it."""
    proposal = MatchProposal.new(
        need_id="need-1",
        offer_id="offer-1",
        score=0.9,
        distance_miles=1.2,
        reasons=["category match: water"],
    )
    assert proposal.status == "pending"
    assert proposal.status != "approved"
    assert proposal.status != "rejected"


def test_match_proposal_new_autogenerates_id():
    proposal = MatchProposal.new(
        need_id="need-2",
        offer_id="offer-2",
        score=0.5,
        distance_miles=None,
        reasons=[],
    )
    assert proposal.id
    parsed = uuid.UUID(proposal.id)
    assert str(parsed) == proposal.id
