"""SLA breach detection and stale-offer expiry.

Pure time-based bookkeeping over Post objects: flagging open needs that
have blown past their urgency-appropriate response window, and expiring
open offers that have sat unclaimed too long. No language model is
involved.
"""

from typing import List, Optional
from datetime import datetime, timezone

from src.models import Post, PostType, Urgency, PostStatus


def minutes_since(post: Post, now: Optional[datetime] = None) -> float:
    """Return how many minutes have elapsed since `post.created_at`.

    `now` defaults to the current UTC time. `post.created_at` is parsed
    with datetime.fromisoformat; if the parsed value is naive (no
    tzinfo), it is assumed to already be UTC.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    created = datetime.fromisoformat(post.created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    return (now - created).total_seconds() / 60.0


def check_sla_breaches(
    needs: List[Post],
    urgent_sla_minutes: int = 30,
    soon_sla_minutes: int = 240,
    now: Optional[datetime] = None,
) -> List[Post]:
    """Return the open needs that have breached their urgency SLA.

    An URGENT need breaches after urgent_sla_minutes; a SOON need
    breaches after soon_sla_minutes. FLEXIBLE needs never breach.
    Only OPEN needs are considered.
    """
    breached = []
    for post in needs:
        if post.status != PostStatus.OPEN:
            continue
        elapsed = minutes_since(post, now)
        if post.urgency == Urgency.URGENT and elapsed > urgent_sla_minutes:
            breached.append(post)
        elif post.urgency == Urgency.SOON and elapsed > soon_sla_minutes:
            breached.append(post)
    return breached


def expire_stale_offers(
    offers: List[Post],
    expiry_hours: int = 48,
    now: Optional[datetime] = None,
) -> List[Post]:
    """Mark open offers older than expiry_hours as EXPIRED, in place.

    Returns only the offers that were newly transitioned to EXPIRED by
    this call.
    """
    newly_expired = []
    expiry_minutes = expiry_hours * 60
    for post in offers:
        if post.status != PostStatus.OPEN:
            continue
        if minutes_since(post, now) > expiry_minutes:
            post.status = PostStatus.EXPIRED
            newly_expired.append(post)
    return newly_expired
