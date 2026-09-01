# src/tools/duplicate_tool.py
import json

from strands import tool
from src.models import Post, PostType, Urgency, PostStatus
from src.dedup import is_duplicate


def _dict_to_post(d: dict) -> Post:
    d = dict(d)
    d["type"] = PostType(d["type"])
    d["urgency"] = Urgency(d["urgency"])
    d["status"] = PostStatus(d["status"]) if "status" in d and d["status"] is not None else PostStatus.OPEN
    return Post(**d)


def duplicate_check_impl(post_a_json: str, post_b_json: str) -> bool:
    """Check whether two posts (each passed as a JSON object matching the Post dataclass fields)
    are likely duplicates of each other. Returns False (rather than raising) if the input JSON
    is malformed or otherwise fails to parse into a Post.
    """
    try:
        post_a_dict = json.loads(post_a_json)
        post_b_dict = json.loads(post_b_json)
        post_a = _dict_to_post(post_a_dict)
        post_b = _dict_to_post(post_b_dict)
        return is_duplicate(post_a, post_b)
    except Exception:
        return False


duplicate_check_tool = tool(duplicate_check_impl)
