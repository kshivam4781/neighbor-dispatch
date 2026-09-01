"""Flask coordinator dashboard for Neighbor Dispatch.

A small, self-contained web UI + JSON API sitting on top of src.storage.Store,
src.matching.propose_matches, src.dedup.find_duplicates, and
src.escalation.{check_sla_breaches, expire_stale_offers}.
"""

import dataclasses

from flask import Flask, request, jsonify

from src.storage import Store
from src.matching import propose_matches
from src.dedup import find_duplicates
from src.escalation import check_sla_breaches, expire_stale_offers
from src.agent import extract_post
from src.config import build_model
from src.models import PostType, PostStatus


def _post_to_json(post):
    d = dataclasses.asdict(post)
    d["type"] = post.type.value
    d["urgency"] = post.urgency.value
    d["status"] = post.status.value
    return d


def _match_to_json(match):
    return dataclasses.asdict(match)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Neighbor Dispatch -- Coordinator Dashboard</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f7f5;
    --panel: #ffffff;
    --border: #ddd;
    --text: #1a1a1a;
    --muted: #666;
    --urgent: #ffd6d6;
    --urgent-text: #7a0000;
    --soon: #fff2c6;
    --soon-text: #7a5b00;
    --flexible: #dcf5dc;
    --flexible-text: #145214;
    --accent: #2b6cb0;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14161a;
      --panel: #1e2126;
      --border: #333;
      --text: #eaeaea;
      --muted: #aaa;
      --urgent: #4a1616;
      --urgent-text: #ff9d9d;
      --soon: #4a3c10;
      --soon-text: #ffd97a;
      --flexible: #163a1a;
      --flexible-text: #9ae6a0;
      --accent: #6ea8dd;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 24px;
  }
  h1 { font-size: 1.4rem; margin: 0 0 4px 0; }
  .subtitle { color: var(--muted); margin: 0 0 20px 0; font-size: 0.9rem; }
  section {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
  }
  h2 { margin-top: 0; font-size: 1.05rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--muted); font-weight: 600; }
  tr.urgency-urgent td.urgency-cell { background: var(--urgent); color: var(--urgent-text); font-weight: 600; }
  tr.urgency-soon td.urgency-cell { background: var(--soon); color: var(--soon-text); font-weight: 600; }
  tr.urgency-flexible td.urgency-cell { background: var(--flexible); color: var(--flexible-text); }
  button {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 5px 10px;
    cursor: pointer;
    font-size: 0.8rem;
    margin-right: 4px;
  }
  button.reject { background: #a33; }
  button:hover { opacity: 0.85; }
  .empty { color: var(--muted); font-style: italic; padding: 8px 0; }
  .grid-two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 800px) { .grid-two { grid-template-columns: 1fr; } }
  .table-wrap { overflow-x: auto; }
  .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; }
  .updated { color: var(--muted); font-size: 0.75rem; margin-top: 8px; }
</style>
</head>
<body>
<h1>Neighbor Dispatch -- Coordinator Dashboard</h1>
<p class="subtitle">Auto-refreshing every 15 seconds.</p>

<section>
  <h2>Open Needs &amp; Offers</h2>
  <div class="grid-two">
    <div>
      <h3>Needs</h3>
      <div class="table-wrap">
        <table id="needs-table">
          <thead><tr><th>Category</th><th>Description</th><th>Zone</th><th>Urgency</th><th>Qty</th><th>Contact</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
    <div>
      <h3>Offers</h3>
      <div class="table-wrap">
        <table id="offers-table">
          <thead><tr><th>Category</th><th>Description</th><th>Zone</th><th>Qty</th><th>Contact</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>
</section>

<section>
  <h2>Pending Match Proposals</h2>
  <div class="table-wrap">
    <table id="matches-table">
      <thead><tr><th>Score</th><th>Distance (mi)</th><th>Need</th><th>Offer</th><th>Reasons</th><th>Action</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</section>

<section>
  <h2>SLA Breaches &amp; Escalations</h2>
  <div id="escalations"></div>
</section>

<div class="updated" id="last-updated"></div>

<script>
function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function refreshPosts() {
  const [needsRes, offersRes] = await Promise.all([
    fetch("/api/posts?type=need&status=open"),
    fetch("/api/posts?type=offer&status=open"),
  ]);
  const needs = await needsRes.json();
  const offers = await offersRes.json();

  const needsBody = document.querySelector("#needs-table tbody");
  needsBody.innerHTML = "";
  if (needs.length === 0) {
    needsBody.innerHTML = '<tr><td colspan="6" class="empty">No open needs</td></tr>';
  } else {
    for (const n of needs) {
      const tr = document.createElement("tr");
      tr.className = "urgency-" + escapeHtml(n.urgency);
      tr.innerHTML = `
        <td>${escapeHtml(n.category)}</td>
        <td>${escapeHtml(n.description)}</td>
        <td>${escapeHtml(n.location_zone)}</td>
        <td class="urgency-cell">${escapeHtml(n.urgency)}</td>
        <td>${escapeHtml(n.quantity)}</td>
        <td>${escapeHtml(n.contact)}</td>
      `;
      needsBody.appendChild(tr);
    }
  }

  const offersBody = document.querySelector("#offers-table tbody");
  offersBody.innerHTML = "";
  if (offers.length === 0) {
    offersBody.innerHTML = '<tr><td colspan="5" class="empty">No open offers</td></tr>';
  } else {
    for (const o of offers) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(o.category)}</td>
        <td>${escapeHtml(o.description)}</td>
        <td>${escapeHtml(o.location_zone)}</td>
        <td>${escapeHtml(o.quantity)}</td>
        <td>${escapeHtml(o.contact)}</td>
      `;
      offersBody.appendChild(tr);
    }
  }
}

async function refreshMatches() {
  const res = await fetch("/api/matches?status=pending");
  const matches = await res.json();
  const body = document.querySelector("#matches-table tbody");
  body.innerHTML = "";
  if (matches.length === 0) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No pending matches</td></tr>';
    return;
  }
  for (const m of matches) {
    const tr = document.createElement("tr");
    const needDesc = m.need_description ? escapeHtml(m.need_description) : escapeHtml(m.need_id);
    const offerDesc = m.offer_description ? escapeHtml(m.offer_description) : escapeHtml(m.offer_id);
    tr.innerHTML = `
      <td>${escapeHtml(m.score)}</td>
      <td>${m.distance_miles !== null && m.distance_miles !== undefined ? escapeHtml(m.distance_miles.toFixed ? m.distance_miles.toFixed(1) : m.distance_miles) : "unknown"}</td>
      <td>${needDesc}</td>
      <td>${offerDesc}</td>
      <td>${escapeHtml((m.reasons || []).join("; "))}</td>
      <td>
        <button class="approve" data-id="${escapeHtml(m.id)}">Approve</button>
        <button class="reject" data-id="${escapeHtml(m.id)}">Reject</button>
      </td>
    `;
    body.appendChild(tr);
  }
  body.querySelectorAll("button.approve").forEach((btn) => {
    btn.addEventListener("click", () => decideMatch(btn.dataset.id, "approve"));
  });
  body.querySelectorAll("button.reject").forEach((btn) => {
    btn.addEventListener("click", () => decideMatch(btn.dataset.id, "reject"));
  });
}

async function decideMatch(matchId, action) {
  await fetch(`/api/matches/${matchId}/${action}`, { method: "POST" });
  await refreshAll();
}

async function refreshEscalations() {
  const res = await fetch("/api/escalations");
  const data = await res.json();
  const el = document.getElementById("escalations");
  const breaches = data.sla_breaches || [];
  const expired = data.newly_expired_offers || [];

  let html = "";
  html += "<h3>SLA Breaches (" + breaches.length + ")</h3>";
  if (breaches.length === 0) {
    html += '<div class="empty">None</div>';
  } else {
    html += "<ul>";
    for (const b of breaches) {
      html += `<li><span class="badge">${escapeHtml(b.urgency)}</span> ${escapeHtml(b.description)} (${escapeHtml(b.location_zone)}, contact: ${escapeHtml(b.contact)})</li>`;
    }
    html += "</ul>";
  }

  html += "<h3>Newly Expired Offers (" + expired.length + ")</h3>";
  if (expired.length === 0) {
    html += '<div class="empty">None</div>';
  } else {
    html += "<ul>";
    for (const e of expired) {
      html += `<li>${escapeHtml(e.description)} (${escapeHtml(e.location_zone)}, contact: ${escapeHtml(e.contact)})</li>`;
    }
    html += "</ul>";
  }

  el.innerHTML = html;
}

async function refreshAll() {
  try {
    await Promise.all([refreshPosts(), refreshMatches(), refreshEscalations()]);
    document.getElementById("last-updated").textContent =
      "Last updated: " + new Date().toLocaleTimeString();
  } catch (e) {
    console.error("refresh failed", e);
  }
}

refreshAll();
setInterval(refreshAll, 15000);
</script>
</body>
</html>
"""


def create_app(store: Store = None) -> Flask:
    app = Flask(__name__)
    app.config["STORE"] = store or Store()

    @app.route("/")
    def index():
        return INDEX_HTML

    @app.route("/api/posts", methods=["GET"])
    def api_list_posts():
        store = app.config["STORE"]
        type_param = request.args.get("type")
        status_param = request.args.get("status")

        post_type = PostType(type_param) if type_param else None
        post_status = PostStatus(status_param) if status_param else None

        posts = store.list_posts(type=post_type, status=post_status)
        return jsonify([_post_to_json(p) for p in posts])

    @app.route("/api/posts", methods=["POST"])
    def api_create_post():
        store = app.config["STORE"]
        body = request.get_json(force=True, silent=True) or {}
        raw_text = body.get("raw_text", "")
        post_type = body.get("type")

        model = build_model()
        post = extract_post(raw_text, post_type, model=model)
        store.add_post(post)

        open_needs = store.list_posts(type=PostType.NEED, status=PostStatus.OPEN)
        open_offers = store.list_posts(type=PostType.OFFER, status=PostStatus.OPEN)
        proposals = propose_matches(open_needs, open_offers)
        store.set_match_proposals(proposals)

        return jsonify(_post_to_json(post)), 201

    @app.route("/api/matches", methods=["GET"])
    def api_list_matches():
        store = app.config["STORE"]
        status_param = request.args.get("status")
        matches = store.list_matches(status=status_param)

        enriched = []
        for m in matches:
            d = _match_to_json(m)
            need = store.get_post(m.need_id)
            offer = store.get_post(m.offer_id)
            d["need_description"] = need.description if need else None
            d["offer_description"] = offer.description if offer else None
            enriched.append(d)
        return jsonify(enriched)

    @app.route("/api/matches/<match_id>/approve", methods=["POST"])
    def api_approve_match(match_id):
        store = app.config["STORE"]
        match = store.approve_match(match_id)
        if match is None:
            return jsonify({"error": "match not found or not pending"}), 404
        return jsonify(_match_to_json(match))

    @app.route("/api/matches/<match_id>/reject", methods=["POST"])
    def api_reject_match(match_id):
        store = app.config["STORE"]
        match = store.reject_match(match_id)
        if match is None:
            return jsonify({"error": "match not found or not pending"}), 404
        return jsonify(_match_to_json(match))

    @app.route("/api/escalations", methods=["GET"])
    def api_escalations():
        store = app.config["STORE"]
        open_needs = store.list_posts(type=PostType.NEED, status=PostStatus.OPEN)
        open_offers = store.list_posts(type=PostType.OFFER, status=PostStatus.OPEN)

        sla_breaches = check_sla_breaches(open_needs)
        newly_expired_offers = expire_stale_offers(open_offers)

        if newly_expired_offers:
            store._save()

        return jsonify(
            {
                "sla_breaches": [_post_to_json(p) for p in sla_breaches],
                "newly_expired_offers": [_post_to_json(p) for p in newly_expired_offers],
            }
        )

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5050, debug=True)
