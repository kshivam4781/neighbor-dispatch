"""Tests for src.escalation: SLA breach detection and stale-offer expiry."""

from datetime import timedelta

import pytest

from src.models import Post, PostType, PostStatus, Urgency
from src.escalation import check_sla_breaches, expire_stale_offers


def _iso(dt):
    return dt.isoformat()


def _make_post(**overrides):
    defaults = dict(
        type=PostType.NEED,
        category="water",
        description="need water",
        location_zone="altadena",
        urgency=Urgency.URGENT,
        contact="test@example.com",
        status=PostStatus.OPEN,
    )
    defaults.update(overrides)
    return Post.new(**defaults)


# ---------------------------------------------------------------------------
# check_sla_breaches
# ---------------------------------------------------------------------------

def test_check_sla_breaches_flags_urgent_need_well_past_sla(now_fixed):
    created = now_fixed - timedelta(minutes=45)  # urgent_sla_minutes default is 30
    need = _make_post(
        urgency=Urgency.URGENT,
        status=PostStatus.OPEN,
        created_at=_iso(created),
    )
    breaches = check_sla_breaches([need], urgent_sla_minutes=30, now=now_fixed)
    assert need in breaches


def test_check_sla_breaches_does_not_flag_urgent_need_created_1_minute_ago(now_fixed):
    created = now_fixed - timedelta(minutes=1)
    need = _make_post(
        urgency=Urgency.URGENT,
        status=PostStatus.OPEN,
        created_at=_iso(created),
    )
    breaches = check_sla_breaches([need], urgent_sla_minutes=30, now=now_fixed)
    assert need not in breaches
    assert breaches == []


def test_check_sla_breaches_ignores_matched_need_even_if_old(now_fixed):
    created = now_fixed - timedelta(hours=5)
    need = _make_post(
        urgency=Urgency.URGENT,
        status=PostStatus.MATCHED,
        created_at=_iso(created),
    )
    breaches = check_sla_breaches([need], urgent_sla_minutes=30, now=now_fixed)
    assert need not in breaches
    assert breaches == []


def test_check_sla_breaches_ignores_expired_need_even_if_old(now_fixed):
    created = now_fixed - timedelta(hours=5)
    need = _make_post(
        urgency=Urgency.URGENT,
        status=PostStatus.EXPIRED,
        created_at=_iso(created),
    )
    breaches = check_sla_breaches([need], urgent_sla_minutes=30, now=now_fixed)
    assert need not in breaches
    assert breaches == []


def test_check_sla_breaches_soon_need_uses_soon_sla(now_fixed):
    # Well past the soon SLA (default 240 minutes), but well under the urgent SLA span
    created = now_fixed - timedelta(minutes=300)
    need = _make_post(
        urgency=Urgency.SOON,
        status=PostStatus.OPEN,
        created_at=_iso(created),
    )
    breaches = check_sla_breaches([need], urgent_sla_minutes=30, soon_sla_minutes=240, now=now_fixed)
    assert need in breaches


# ---------------------------------------------------------------------------
# expire_stale_offers
# ---------------------------------------------------------------------------

def test_expire_stale_offers_mutates_and_returns_only_old_open_offers(now_fixed):
    old_open_offer = _make_post(
        type=PostType.OFFER,
        status=PostStatus.OPEN,
        created_at=_iso(now_fixed - timedelta(hours=72)),  # older than 48h expiry
    )
    recent_open_offer = _make_post(
        type=PostType.OFFER,
        status=PostStatus.OPEN,
        created_at=_iso(now_fixed - timedelta(hours=2)),
    )
    already_expired_offer = _make_post(
        type=PostType.OFFER,
        status=PostStatus.EXPIRED,
        created_at=_iso(now_fixed - timedelta(hours=100)),
    )

    newly_expired = expire_stale_offers(
        [old_open_offer, recent_open_offer, already_expired_offer],
        expiry_hours=48,
        now=now_fixed,
    )

    # Only the old OPEN offer is returned as newly expired.
    assert newly_expired == [old_open_offer]

    # It was mutated in place to EXPIRED.
    assert old_open_offer.status == PostStatus.EXPIRED

    # The recent offer is untouched and not returned.
    assert recent_open_offer.status == PostStatus.OPEN
    assert recent_open_offer not in newly_expired

    # The already-expired offer stays EXPIRED and is not returned again.
    assert already_expired_offer.status == PostStatus.EXPIRED
    assert already_expired_offer not in newly_expired
