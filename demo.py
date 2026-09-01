#!/usr/bin/env python3
"""
Neighbor Dispatch -- offline-runnable demo.
Usage:
  python demo.py                 # full pipeline over seeded demo data, mock/offline mode, console report
  python demo.py --serve         # also launch the coordinator dashboard at http://localhost:5050
  python demo.py --ask "question"  # ask the live Match Advisor agent a question (requires MODEL_PROVIDER set to a real provider + API key; errors clearly if not configured)
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from src.agent import extract_post, ask_match_advisor
from src.config import build_model
from src.matching import propose_matches
from src.dedup import find_duplicates
from src.escalation import check_sla_breaches
from src.models import PostType, PostStatus
from src.storage import Store

SEED_PATH = os.path.join(os.path.dirname(__file__), "data", "seed_posts.json")

# Demo-specific state file so `--serve` can pick up exactly the posts/matches this run produced,
# without touching whatever DEFAULT_DB_PATH the rest of the app uses in normal operation.
DEMO_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "dispatch_state.json")

# Spacing (in minutes) between consecutive seeded posts' created_at timestamps, working backward
# from "now". Chosen so that the whole seeded set spans under two hours (comfortably inside
# find_duplicates' default 120-minute dedup window) while the oldest urgent posts are still well
# past the 30-minute urgent SLA threshold used by check_sla_breaches.
STAGGER_MINUTES = 6


def load_seed_posts(model):
    """Load data/seed_posts.json, run each raw post through extract_post, and stagger each
    resulting Post's created_at a few minutes apart working backward from "now" -- the first
    item in the file is treated as the oldest (posted first), the last item as the most recent.
    """
    with open(SEED_PATH, "r") as f:
        items = json.load(f)

    now = datetime.now(timezone.utc)
    total = len(items)
    posts = []
    for i, item in enumerate(items):
        post = extract_post(item["raw_text"], item["type"], model=model)
        offset_minutes = (total - i) * STAGGER_MINUTES
        post.created_at = (now - timedelta(minutes=offset_minutes)).isoformat()
        posts.append(post)
    return posts


def print_banner(text):
    line = "=" * (len(text) + 8)
    print(f"\n{line}\n=== {text} ===\n{line}")


def _fmt_post_line(post):
    qty = post.quantity if post.quantity is not None else "n/a"
    return (
        f"  [{post.type.value:>5}] {post.category:<14} | {post.location_zone:<14} | "
        f"{post.urgency.value:<9} | qty={qty!s:<4} | \"{post.description[:70]}\""
    )


def run_pipeline(model):
    provider_mode = "MOCK MODE -- offline fallback keyword/regex parser" if model is None else "LIVE MODEL configured -- calling the model for extraction"

    print_banner("INTAKE + EXTRACTION (seeded demo data modeled on MALAN's public Jan 2025 reporting)")
    print(f"Extraction mode: {provider_mode}\n")
    posts = load_seed_posts(model)
    for post in posts:
        print(f'raw: "{post.raw_text}"')
        print(_fmt_post_line(post))
        print()

    needs = [p for p in posts if p.type == PostType.NEED]
    offers = [p for p in posts if p.type == PostType.OFFER]
    print(f"Extracted {len(posts)} posts total: {len(needs)} needs, {len(offers)} offers.")

    # Fresh demo state every run so the dashboard (--serve) reflects exactly this run's seed data,
    # rather than accumulating duplicate seed posts across repeated invocations.
    if os.path.exists(DEMO_DB_PATH):
        os.remove(DEMO_DB_PATH)
    store = Store(db_path=DEMO_DB_PATH)
    for post in posts:
        store.add_post(post)

    print_banner("DUPLICATE CHECK")
    dup_pairs = find_duplicates(posts)
    if not dup_pairs:
        print("No likely duplicate posts detected.")
    else:
        print(f"Found {len(dup_pairs)} likely duplicate pair(s):")
        for post_a, post_b in dup_pairs:
            print(f'  - "{post_a.description[:60]}" ({post_a.location_zone}) '
                  f'<-> "{post_b.description[:60]}" ({post_b.location_zone})  [category={post_a.category}]')

    print_banner("MATCH PROPOSALS")
    proposals = propose_matches(needs, offers)
    post_by_id = {p.id: p for p in posts}
    if not proposals:
        print("No viable need/offer matches found.")
    else:
        print(f"{'score':>5}  {'need':<45} {'offer':<45} reasons")
        print("-" * 130)
        for proposal in proposals:
            need = post_by_id.get(proposal.need_id)
            offer = post_by_id.get(proposal.offer_id)
            need_desc = (need.description[:42] + "...") if need and len(need.description) > 42 else (need.description if need else proposal.need_id)
            offer_desc = (offer.description[:42] + "...") if offer and len(offer.description) > 42 else (offer.description if offer else proposal.offer_id)
            print(f"{proposal.score:>5.2f}  {need_desc:<45} {offer_desc:<45} {'; '.join(proposal.reasons)}")
    store.set_match_proposals(proposals)

    print_banner("SLA / ESCALATION CHECK")
    breaches = check_sla_breaches(needs)
    if not breaches:
        print("No SLA breaches -- all open needs are still within their urgency response window.")
    else:
        print(f"{len(breaches)} need(s) have breached their SLA window:")
        for post in breaches:
            print(f'  >>> NEEDS HUMAN ATTENTION NOW: [{post.urgency.value}] "{post.description[:70]}" '
                  f'({post.location_zone}, contact: {post.contact})')

    print_banner("HUMAN APPROVAL GATE")
    pending = store.list_matches(status="pending")
    print(
        "Every match proposal above has status=\"pending\". No neighbor is contacted and no match is\n"
        "considered confirmed until a human coordinator explicitly approves it -- either by clicking\n"
        "Approve in the dashboard, or by calling POST /api/matches/<id>/approve. This system proposes;\n"
        "it never auto-notifies.\n"
    )
    print(f"Pending matches awaiting human coordinator approval: {len(pending)}")

    return store


def main():
    parser = argparse.ArgumentParser(description="Neighbor Dispatch demo")
    parser.add_argument("--serve", action="store_true", help="launch the coordinator dashboard after the pipeline runs")
    parser.add_argument("--ask", type=str, default=None, help="ask the live Match Advisor agent a question (needs a real MODEL_PROVIDER)")
    parser.add_argument(
        "--worked-example",
        action="store_true",
        help=(
            "run a fully offline worked example of the Match Advisor agent reasoning step-by-step "
            "through its real five tools against real seeded data (no API key/network needed -- "
            "see examples/match_advisor_worked_example.py for what's real vs. scripted)"
        ),
    )
    args = parser.parse_args()

    if args.worked_example:
        # Local import: examples/match_advisor_worked_example.py imports load_seed_posts back out
        # of this module, so importing it lazily here (rather than at module load time) avoids a
        # circular import between demo.py and the examples package.
        from examples.match_advisor_worked_example import run_worked_example

        run_worked_example()
        return

    model = build_model()
    provider = os.environ.get("MODEL_PROVIDER", "mock")
    print(f"MODEL_PROVIDER={provider} ({'offline fallback parser' if model is None else 'live model configured'})\n")

    if args.ask:
        if model is None:
            print("ERROR: --ask requires a real MODEL_PROVIDER (bedrock/anthropic/openai) and API key. "
                  "See .env.example / README for setup. Running in mock mode has no live agent to ask.")
            sys.exit(1)
        print_banner("MATCH ADVISOR (live Strands agent + tools)")
        print(ask_match_advisor(args.ask, model=model))
        return

    store = run_pipeline(model)

    if args.serve:
        print_banner("LAUNCHING DASHBOARD at http://localhost:5050")
        from src.dashboard.app import create_app
        create_app(store).run(host="0.0.0.0", port=5050)


if __name__ == "__main__":
    main()
