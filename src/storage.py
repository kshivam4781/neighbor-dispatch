"""JSON-file-backed repository for Posts and MatchProposals.

A simple, thread-naive store suitable for a single-process demo. Persists
everything to one JSON file as {"posts": [...], "matches": [...]}.
"""

import json
import os
import tempfile
import dataclasses
from typing import List, Optional

from src.models import Post, MatchProposal, PostType, PostStatus, Urgency

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "dispatch_state.json")


def _post_to_dict(post: Post) -> dict:
    d = dataclasses.asdict(post)
    d["type"] = post.type.value if isinstance(post.type, PostType) else post.type
    d["urgency"] = post.urgency.value if isinstance(post.urgency, Urgency) else post.urgency
    d["status"] = post.status.value if isinstance(post.status, PostStatus) else post.status
    return d


def _dict_to_post(d: dict) -> Post:
    d = dict(d)
    if "type" in d and d["type"] is not None:
        d["type"] = PostType(d["type"])
    if "urgency" in d and d["urgency"] is not None:
        d["urgency"] = Urgency(d["urgency"])
    if "status" in d and d["status"] is not None:
        d["status"] = PostStatus(d["status"])
    return Post(**d)


def _match_to_dict(match: MatchProposal) -> dict:
    # MatchProposal.status is already a plain string ("pending"/"approved"/"rejected").
    return dataclasses.asdict(match)


def _dict_to_match(d: dict) -> MatchProposal:
    return MatchProposal(**d)


class Store:
    """Thread-naive JSON file store (fine for a single-process hackathon demo). Holds two lists:
    posts (List[Post]) and matches (List[MatchProposal]), persisted as one JSON object
    {"posts": [...], "matches": [...]} with dataclasses serialized via dataclasses.asdict, enums via .value."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.posts: List[Post] = []
        self.matches: List[MatchProposal] = []
        self._load()

    def _load(self):
        if not os.path.exists(self.db_path):
            self.posts = []
            self.matches = []
            return
        try:
            with open(self.db_path, "r") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.posts = []
            self.matches = []
            return

        self.posts = [_dict_to_post(p) for p in raw.get("posts", [])]
        self.matches = [_dict_to_match(m) for m in raw.get("matches", [])]

    def _save(self):
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        payload = {
            "posts": [_post_to_dict(p) for p in self.posts],
            "matches": [_match_to_dict(m) for m in self.matches],
        }

        fd, tmp_path = tempfile.mkstemp(
            prefix=".dispatch_state_", suffix=".tmp", dir=parent or "."
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp_path, self.db_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def add_post(self, post: Post) -> Post:
        self.posts.append(post)
        self._save()
        return post

    def list_posts(self, type: Optional[PostType] = None, status: Optional[PostStatus] = None) -> List[Post]:
        result = self.posts
        if type is not None:
            result = [p for p in result if p.type == type]
        if status is not None:
            result = [p for p in result if p.status == status]
        return result

    def get_post(self, post_id: str) -> Optional[Post]:
        for p in self.posts:
            if p.id == post_id:
                return p
        return None

    def set_match_proposals(self, proposals: List[MatchProposal]):
        existing_pairs = {(m.need_id, m.offer_id) for m in self.matches}
        for proposal in proposals:
            pair = (proposal.need_id, proposal.offer_id)
            if pair in existing_pairs:
                continue
            self.matches.append(proposal)
            existing_pairs.add(pair)
        self._save()

    def list_matches(self, status: Optional[str] = None) -> List[MatchProposal]:
        if status is None:
            return self.matches
        return [m for m in self.matches if m.status == status]

    def get_match(self, match_id: str) -> Optional[MatchProposal]:
        for m in self.matches:
            if m.id == match_id:
                return m
        return None

    def approve_match(self, match_id: str) -> Optional[MatchProposal]:
        match = self.get_match(match_id)
        if match is None or match.status != "pending":
            return None

        match.status = "approved"

        need = self.get_post(match.need_id)
        offer = self.get_post(match.offer_id)
        if need is not None:
            need.status = PostStatus.MATCHED
        if offer is not None:
            offer.status = PostStatus.MATCHED

        self._save()
        return match

    def reject_match(self, match_id: str) -> Optional[MatchProposal]:
        match = self.get_match(match_id)
        if match is None or match.status != "pending":
            return None

        match.status = "rejected"
        self._save()
        return match
