# src/tools/sla_tool.py
import json

from strands import tool
from src.models import Post, PostType, Urgency, PostStatus
from src.escalation import check_sla_breaches


def _dict_to_post(d: dict) -> Post:
    d = dict(d)
    d["type"] = PostType(d["type"])
    d["urgency"] = Urgency(d["urgency"])
    d["status"] = PostStatus(d["status"]) if "status" in d and d["status"] is not None else PostStatus.OPEN
    return Post(**d)


def sla_check_impl(needs_json: str) -> str:
    """Check a JSON array of need-post dicts (matching the Post dataclass fields) for SLA
    breaches (urgent/soon needs that have gone unmatched too long). Returns a JSON string
    array of {"id", "description", "urgency"} for each breaching need, or
    '{"error": "<message>"}' if the input is malformed.
    """
    try:
        needs_list = json.loads(needs_json)
        needs = [_dict_to_post(d) for d in needs_list]
        breaches = check_sla_breaches(needs)
        return json.dumps(
            [
                {"id": p.id, "description": p.description, "urgency": p.urgency.value}
                for p in breaches
            ]
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


sla_check_tool = tool(sla_check_impl)
