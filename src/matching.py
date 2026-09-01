"""Matching logic: distance calculations, category matching, and need/offer scoring.

This module turns a set of open "need" and "offer" Posts into ranked
MatchProposal candidates. It relies only on the taxonomy and gazetteer
lookup tables defined in src.models -- there is no external geocoding or
language-model call involved; all matching is deterministic arithmetic
and string comparison against the fixed taxonomy.
"""

from typing import Optional, List, Tuple
import math

from src.models import Post, PostStatus, Urgency, MatchProposal, CATEGORY_TAXONOMY, ZONE_GAZETTEER

_EARTH_RADIUS_MILES = 3958.8


def geo_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in miles between two lat/lon points.

    Uses the haversine formula with the Earth's mean radius (3958.8 miles).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_MILES * c


def zone_coords(zone_name: str) -> Optional[Tuple[float, float]]:
    """Case-insensitively look up a named zone's (lat, lon) in ZONE_GAZETTEER.

    Returns None if the zone name is not present in the gazetteer.
    """
    if zone_name is None:
        return None
    return ZONE_GAZETTEER.get(zone_name.strip().lower())


def zone_distance_miles(zone_a: str, zone_b: str) -> Optional[float]:
    """Return the distance in miles between two named zones, or None if either is unknown."""
    coords_a = zone_coords(zone_a)
    coords_b = zone_coords(zone_b)
    if coords_a is None or coords_b is None:
        return None
    return geo_distance_miles(coords_a[0], coords_a[1], coords_b[0], coords_b[1])


def _resolve_taxonomy_keys(category: str) -> set:
    """Return the set of CATEGORY_TAXONOMY keys that `category` resolves to.

    A category resolves to a key either because it *is* that key (case-insensitive)
    or because it appears as a synonym in that key's synonym list.
    """
    if category is None:
        return set()
    cat_lower = category.strip().lower()
    keys = set()
    if cat_lower in CATEGORY_TAXONOMY:
        keys.add(cat_lower)
    for key, synonyms in CATEGORY_TAXONOMY.items():
        if cat_lower in (s.lower() for s in synonyms):
            keys.add(key)
    return keys


def category_matches(category_a: str, category_b: str) -> bool:
    """Return True if two free-text categories should be considered the same category.

    True when the two strings are equal (case-insensitive), or when they both
    resolve (directly as a taxonomy key, or as a synonym) to at least one
    common CATEGORY_TAXONOMY key.
    """
    if category_a is None or category_b is None:
        return category_a == category_b
    if category_a.strip().lower() == category_b.strip().lower():
        return True
    keys_a = _resolve_taxonomy_keys(category_a)
    keys_b = _resolve_taxonomy_keys(category_b)
    return len(keys_a & keys_b) > 0


def score_match(need: Post, offer: Post) -> Tuple[float, List[str]]:
    """Score how well an offer satisfies a need, returning (score, reasons).

    The score is in [0.0, 1.0]. See module spec / task description for the
    exact rules governing category match, distance, urgency, and quantity.
    """
    if not category_matches(need.category, offer.category):
        return (0.0, ["category mismatch"])

    score = 0.5
    reasons = [f"category match: {need.category}"]

    distance = zone_distance_miles(need.location_zone, offer.location_zone)
    if distance is not None:
        if distance <= 2:
            score += 0.3
            reasons.append(f"very close ({distance:.1f} mi)")
        elif distance <= 5:
            score += 0.2
            reasons.append(f"nearby ({distance:.1f} mi)")
        elif distance <= 15:
            score += 0.1
            reasons.append(f"within service radius ({distance:.1f} mi)")
        else:
            reasons.append(f"far ({distance:.1f} mi)")
    else:
        reasons.append("distance unknown")

    if need.urgency == Urgency.URGENT or need.urgency.value == "urgent":
        score += 0.2
        reasons.append("need marked urgent")

    if need.quantity and offer.quantity and offer.quantity >= need.quantity:
        score += 0.1
        reasons.append("offer covers requested quantity")

    score = min(score, 1.0)
    return (round(score, 2), reasons)


def propose_matches(
    needs: List[Post],
    offers: List[Post],
    max_distance_miles: float = 15.0,
    min_score: float = 0.4,
) -> List[MatchProposal]:
    """Generate ranked MatchProposals for every viable open need/offer pair.

    Only OPEN needs and OPEN offers are considered. A pair is skipped if
    both zones are known and their distance exceeds max_distance_miles.
    A pair is kept only if its score_match score is >= min_score. Results
    are sorted by score descending, then by distance ascending (unknown
    distances sort last).
    """
    open_needs = [n for n in needs if n.status == PostStatus.OPEN]
    open_offers = [o for o in offers if o.status == PostStatus.OPEN]

    proposals: List[MatchProposal] = []

    for need in open_needs:
        for offer in open_offers:
            distance = zone_distance_miles(need.location_zone, offer.location_zone)
            if distance is not None and distance > max_distance_miles:
                continue

            score, reasons = score_match(need, offer)
            if score < min_score:
                continue

            proposals.append(
                MatchProposal.new(
                    need_id=need.id,
                    offer_id=offer.id,
                    score=score,
                    distance_miles=distance,
                    reasons=reasons,
                )
            )

    proposals.sort(
        key=lambda p: (
            -p.score,
            p.distance_miles if p.distance_miles is not None else float("inf"),
        )
    )
    return proposals
