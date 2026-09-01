"""Duplicate-post detection.

Two posts of the same type (both needs, or both offers) posted close
together in time are treated as duplicates if they share a contact and
category, or if they share a category, zone, and sufficiently similar
free-text description. This is plain string/time comparison -- no
language model is involved.
"""

from typing import List, Tuple
from difflib import SequenceMatcher
from datetime import datetime

from src.models import Post


def _minutes_between(iso_a: str, iso_b: str) -> float:
    """Parse two ISO-8601 timestamps and return the absolute difference in minutes."""
    dt_a = datetime.fromisoformat(iso_a)
    dt_b = datetime.fromisoformat(iso_b)
    delta = dt_a - dt_b
    return abs(delta.total_seconds()) / 60.0


def is_duplicate(
    post_a: Post,
    post_b: Post,
    time_window_minutes: int = 120,
    text_similarity_threshold: float = 0.7,
) -> bool:
    """Return True if post_a and post_b appear to be duplicate posts.

    Posts of different ids and the same type, posted within
    time_window_minutes of each other, are considered duplicates if
    either: (a) they share a non-empty contact and the same category, or
    (b) they share the same category and location zone and their
    descriptions are similar enough (SequenceMatcher ratio >=
    text_similarity_threshold).
    """
    if post_a.id == post_b.id:
        return False
    if post_a.type != post_b.type:
        return False
    if _minutes_between(post_a.created_at, post_b.created_at) > time_window_minutes:
        return False

    if post_a.contact and post_a.contact == post_b.contact and post_a.category == post_b.category:
        return True

    if (
        post_a.category == post_b.category
        and post_a.location_zone.lower() == post_b.location_zone.lower()
        and SequenceMatcher(
            None, post_a.description.lower(), post_b.description.lower()
        ).ratio()
        >= text_similarity_threshold
    ):
        return True

    return False


def find_duplicates(posts: List[Post], time_window_minutes: int = 120) -> List[Tuple[Post, Post]]:
    """Return all unique duplicate pairs (post_a, post_b) among `posts`.

    Pairs are ordered so post_a.id < post_b.id (string comparison) to avoid
    reporting the same pair twice.
    """
    duplicates: List[Tuple[Post, Post]] = []
    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            post_x, post_y = posts[i], posts[j]
            post_a, post_b = (post_x, post_y) if post_x.id < post_y.id else (post_y, post_x)
            if is_duplicate(post_a, post_b, time_window_minutes):
                duplicates.append((post_a, post_b))
    return duplicates
