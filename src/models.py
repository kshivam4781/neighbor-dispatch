"""Shared data contracts for the neighbor-dispatch project.

This module defines the plain-data types (Post, MatchProposal), the
enumerations that constrain their fields (PostType, Urgency, PostStatus),
and the two lookup tables (CATEGORY_TAXONOMY, ZONE_GAZETTEER) that the
rest of the codebase treats as ground truth. Every other module in this
project -- matching, deduplication, escalation -- imports its data
structures from here rather than defining its own, so a "need" or an
"offer" or a "match proposal" means exactly the same thing everywhere in
the system. Nothing in this module ever calls a language model; it is
pure, dependency-free Python.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
from datetime import datetime, timezone
import uuid


class PostType(str, Enum):
    NEED = "need"
    OFFER = "offer"


class Urgency(str, Enum):
    URGENT = "urgent"
    SOON = "soon"
    FLEXIBLE = "flexible"


class PostStatus(str, Enum):
    OPEN = "open"
    MATCHED = "matched"
    EXPIRED = "expired"
    FULFILLED = "fulfilled"


# Fixed category taxonomy: category key -> list of free-text synonyms used for keyword matching.
CATEGORY_TAXONOMY = {
    "water": ["water", "bottled water", "drinking water"],
    "food": ["food", "groceries", "meal", "meals", "snacks", "produce", "formula", "baby formula"],
    "shelter": ["shelter", "housing", "hotel", "place to stay", "room"],
    "medical": ["medical", "medicine", "first aid", "prescription", "oxygen", "inhaler"],
    "transportation": ["transportation", "ride", "car", "gas", "fuel", "evacuation ride"],
    "childcare": ["childcare", "babysitting", "kids", "child care"],
    "power": ["generator", "battery", "batteries", "power bank", "charging", "solar charger"],
    "supplies": ["diapers", "blankets", "clothing", "clothes", "supplies", "hygiene", "masks", "n95"],
    "other": [],
}

# Named LA-area neighborhood zones -> (lat, lon), used for the demo dataset and geo distance lookups.
ZONE_GAZETTEER = {
    "eagle rock": (34.1397, -118.2151),
    "highland park": (34.1141, -118.1959),
    "altadena": (34.1897, -118.1310),
    "pasadena": (34.1478, -118.1445),
    "glassell park": (34.1119, -118.2372),
}


@dataclass
class Post:
    id: str
    type: PostType
    category: str
    description: str
    location_zone: str
    urgency: Urgency
    contact: str
    quantity: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timeframe: Optional[str] = None
    status: PostStatus = PostStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_text: Optional[str] = None

    @staticmethod
    def new(**kwargs) -> "Post":
        kwargs.setdefault("id", str(uuid.uuid4()))
        return Post(**kwargs)


@dataclass
class MatchProposal:
    id: str
    need_id: str
    offer_id: str
    score: float
    distance_miles: Optional[float]
    reasons: List[str]
    status: str = "pending"  # pending | approved | rejected -- MUST default to pending
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @staticmethod
    def new(**kwargs) -> "MatchProposal":
        kwargs.setdefault("id", str(uuid.uuid4()))
        return MatchProposal(**kwargs)
