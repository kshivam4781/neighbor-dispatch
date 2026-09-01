import json
import re
from typing import Optional

from strands import Agent

from src.models import Post, PostType, Urgency, PostStatus, CATEGORY_TAXONOMY, ZONE_GAZETTEER
from src.tools.category_tool import category_match_tool
from src.tools.geo_tool import geo_distance_tool
from src.tools.score_tool import score_match_tool
from src.tools.duplicate_tool import duplicate_check_tool
from src.tools.sla_tool import sla_check_tool


ADVISOR_SYSTEM_PROMPT = (
    "You are the Neighbor Dispatch Match Advisor for a volunteer mutual-aid coordinator. "
    "You have tools to check category matches, geo distance between named zones, compute a "
    "match score between a need and an offer, detect duplicate posts, and check SLA breaches "
    "on urgent needs. Always call the relevant tool rather than guessing, and cite the tool's "
    "numeric output in your answer. Never claim a match is confirmed -- a human coordinator always "
    "makes the final approval decision; you only recommend."
)

EXTRACTION_SYSTEM_PROMPT = (
    "You convert one raw, informal mutual-aid post (a need or an offer) into a single strict JSON "
    "object and output ONLY that JSON object, no prose, no markdown fences. Schema: "
    '{"category": one of ' + str(list(CATEGORY_TAXONOMY.keys())) + ', "description": short string, '
    '"location_zone": one of ' + str(list(ZONE_GAZETTEER.keys())) + ' or best-guess free text if none match, '
    '"urgency": one of ["urgent","soon","flexible"], "quantity": integer or null, '
    '"contact": string or "unknown", "timeframe": string or null}'
)


def build_agent(model=None, callback_handler=None) -> Agent:
    """Build the tool-using Match Advisor agent. model=None lets Strands use its own default;
    pass a configured model instance from config.build_model() for real API use, or a
    ScriptedAdvisorModel (src/scripted_model.py) for the fully offline worked example.
    callback_handler is optional and passed straight through to Strands' Agent -- leave it
    unset to keep Strands' normal default (prints "Tool #N: <name>" as tools are called)."""
    kwargs = {
        "tools": [
            category_match_tool,
            geo_distance_tool,
            score_match_tool,
            duplicate_check_tool,
            sla_check_tool,
        ],
        "system_prompt": ADVISOR_SYSTEM_PROMPT,
    }
    if model is not None:
        kwargs["model"] = model
    if callback_handler is not None:
        kwargs["callback_handler"] = callback_handler
    return Agent(**kwargs)


def ask_match_advisor(question: str, model=None) -> str:
    """Ask the Match Advisor a free-form question; it will use its tools. Requires a real model
    (raises RuntimeError if model is None, since there is nothing useful a mock advisor can say)."""
    if model is None:
        raise RuntimeError("ask_match_advisor requires a live model; set MODEL_PROVIDER to bedrock/anthropic/openai.")
    agent = build_agent(model=model)
    result = agent(question)
    return str(result)


def _fallback_extract(raw_text: str, post_type: str) -> Post:
    """Deterministic keyword/regex extractor used when no model is configured or JSON parsing fails."""
    text = raw_text.lower()

    category = "other"
    for cat, synonyms in CATEGORY_TAXONOMY.items():
        for synonym in synonyms:
            if synonym in text:
                category = cat
                break
        if category != "other":
            break

    location_zone = "unknown"
    for zone in ZONE_GAZETTEER.keys():
        if zone in text:
            location_zone = zone
            break

    if any(kw in text for kw in ["urgent", "asap", "now", "emergency"]):
        urgency = Urgency.URGENT
    elif any(kw in text for kw in ["today", "this week", "soon"]):
        urgency = Urgency.SOON
    else:
        urgency = Urgency.FLEXIBLE

    match = re.search(r"\d+", raw_text)
    quantity = int(match.group()) if match else None

    return Post.new(
        type=PostType(post_type),
        category=category,
        description=raw_text.strip(),
        location_zone=location_zone,
        urgency=urgency,
        quantity=quantity,
        contact="unknown",
        timeframe=None,
        raw_text=raw_text,
    )


def _call_agent_for_text(prompt: str, system_prompt: str, model) -> str:
    """Thin seam kept as its own function (calling the module-level `Agent` name) so tests can
    monkeypatch `src.agent.Agent` to avoid any real model call."""
    agent = Agent(model=model, tools=[], system_prompt=system_prompt)
    return str(agent(prompt))


def extract_post(raw_text: str, post_type: str, model=None) -> Post:
    """Turn one raw free-text post into a structured Post. If model is None, use _fallback_extract
    directly (no LLM call at all). If model is not None, call the model via _call_agent_for_text and
    parse its JSON response, falling back to _fallback_extract on any failure."""
    if model is None:
        return _fallback_extract(raw_text, post_type)

    try:
        raw_response = _call_agent_for_text(raw_text, EXTRACTION_SYSTEM_PROMPT, model)
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned)
        cleaned = cleaned.strip()
        parsed = json.loads(cleaned)

        return Post.new(
            type=PostType(post_type),
            category=parsed.get("category", "other"),
            description=parsed.get("description", raw_text),
            location_zone=parsed.get("location_zone", "unknown"),
            urgency=Urgency(parsed.get("urgency", "flexible")),
            quantity=parsed.get("quantity"),
            contact=parsed.get("contact", "unknown"),
            timeframe=parsed.get("timeframe"),
            raw_text=raw_text,
        )
    except Exception:
        return _fallback_extract(raw_text, post_type)
