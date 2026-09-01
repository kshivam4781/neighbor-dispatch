# src/tools/score_tool.py
import json

from strands import tool
from src.models import Post, PostType, Urgency, PostStatus
from src.matching import score_match


def _dict_to_post(d: dict) -> Post:
    d = dict(d)
    d["type"] = PostType(d["type"])
    d["urgency"] = Urgency(d["urgency"])
    d["status"] = PostStatus(d["status"]) if "status" in d and d["status"] is not None else PostStatus.OPEN
    return Post(**d)


def score_match_impl(need_json: str, offer_json: str) -> str:
    """Compute a match score between a need post and an offer post, both passed as JSON objects
    (matching the Post dataclass fields). Returns a JSON string like
    {"score": <float>, "reasons": [<str>, ...]}, or {"error": "<message>"} if the input is malformed.
    """
    try:
        need_dict = json.loads(need_json)
        offer_dict = json.loads(offer_json)
        need = _dict_to_post(need_dict)
        offer = _dict_to_post(offer_dict)
        score, reasons = score_match(need, offer)
        return json.dumps({"score": score, "reasons": reasons})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


score_match_tool = tool(score_match_impl)
