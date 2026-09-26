"""Immune Harness dashboard: every step of the loop, live or in slow motion.

Run from the repo root:  uv run streamlit run dashboard/app.py
Reads Atlas only (MONGODB_URI / MONGODB_DB from .env). The Compiler's checks are
recomputed here with the same functions the Compiler uses, so nothing extra is stored.
"""
import html
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from db.atlas import Atlas  # noqa: E402
from db.schemas import Action, Policy  # noqa: E402
from harness.compiler import BAD_GLOBS, MAX_FP  # noqa: E402
from harness.sentry import policy_matches  # noqa: E402

try:
    from agents.config import AUTHORIZED_EDGES
except ImportError:
    AUTHORIZED_EDGES = set()

THRESHOLD = float(os.environ.get("RISK_THRESHOLD", "0.8"))
REASON_RE = re.compile(r"^(jev|fallback) risk=([\d.]+) category=(\w+) \(([\d.]+)\)")
REPLAY_ROWS = 200

st.set_page_config(page_title="Immune Harness", page_icon="🛡️", layout="wide")

# Status colours (good/critical) always ship with an icon + label; blue = policy memory, orange = Jev.
st.markdown("""<style>
.ih{--blk:#d03b3b;--ok:#0ca30c;--pol:#2a78d6;--jev:#eb6834;--arc:#1baf7a;--line:rgba(128,128,128,.28);--soft:rgba(128,128,128,.07)}
.ih-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:4px 0 14px}
.ih-kpi{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--soft)}
.ih-kpi b{display:block;font-size:1.6rem;line-height:1.2;font-variant-numeric:tabular-nums}
.ih-kpi span{font-size:.78rem;opacity:.75}
.ih-strip{display:flex;flex-wrap:wrap;align-items:stretch;gap:6px;margin:6px 0 4px}
.ih-node{flex:1 1 110px;border:1px solid var(--line);border-radius:9px;padding:7px 9px;background:var(--soft);font-size:.8rem;min-width:105px}
.ih-node small{display:block;font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;opacity:.65}
.ih-node.off{opacity:.3}
.ih-node.hit{border-color:var(--pol);box-shadow:inset 0 0 0 1px var(--pol)}
.ih-node.bad{border-color:var(--blk);box-shadow:inset 0 0 0 1px var(--blk)}
.ih-node.good{border-color:var(--ok);box-shadow:inset 0 0 0 1px var(--ok)}
.ih-node.busy{border-color:var(--arc);box-shadow:inset 0 0 0 1px var(--arc);animation:ihpulse 1.1s infinite}
@keyframes ihpulse{50%{opacity:.55}}
.ih-arrow{align-self:center;opacity:.45;font-size:.9rem}
.ih-stage{display:flex;gap:14px;padding:12px 14px;border-radius:12px;border:1px solid var(--line);margin:0 0 8px;background:var(--soft)}
.ih-stage.pending{opacity:.28}
.ih-stage.active{border-color:var(--pol);box-shadow:0 0 0 3px rgba(42,120,214,.28)}
.ih-num{flex:0 0 32px;height:32px;border-radius:50%;display:grid;place-items:center;font-weight:700;background:rgba(128,128,128,.2)}
.ih-stage.done .ih-num,.ih-stage.active .ih-num{background:var(--pol);color:#fff}
.ih-who{font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;opacity:.7}
.ih-title{font-weight:650;font-size:1.03rem;margin-top:1px}
.ih-body{font-size:.9rem;margin-top:5px;line-height:1.5}
.ih-body code{font-size:.82rem}
.chip{display:inline-block;padding:0 8px;border-radius:999px;font-size:.74rem;font-weight:650;border:1px solid;white-space:nowrap}
.chip.block{color:var(--blk);border-color:var(--blk)}
.chip.allow{color:var(--ok);border-color:var(--ok)}
.chip.policy{color:var(--pol);border-color:var(--pol)}
.chip.jev{color:var(--jev);border-color:var(--jev)}
.chip.arc{color:var(--arc);border-color:var(--arc)}
.chip.mute{opacity:.7;border-color:var(--line)}
.meter{position:relative;height:12px;border-radius:6px;background:rgba(128,128,128,.22);width:100%;max-width:420px;margin:6px 0 2px}
.meter>span{position:absolute;left:0;top:0;bottom:0;border-radius:6px}
.meter>i{position:absolute;top:-5px;bottom:-5px;width:2px;background:currentColor;opacity:.8}
.meter-l{display:flex;justify-content:space-between;max-width:420px;font-size:.72rem;opacity:.7}
.ih-feed{width:100%;border-collapse:collapse;font-size:.82rem}
.ih-feed td,.ih-feed th{white-space:nowrap;padding:5px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
.ih-feed th{font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;opacity:.65;font-weight:600}
.ih-feed td.num{text-align:right;font-variant-numeric:tabular-nums}
.ih-feed tr.new td{animation:ihflash 1.6s ease-out}
@keyframes ihflash{from{background:rgba(42,120,214,.25)}to{background:transparent}}
.ih-pol{border:1px solid var(--line);border-radius:10px;padding:9px 11px;margin-bottom:8px;background:var(--soft);font-size:.84rem}
.ih-pol .v{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-top:3px}
.ih-pol .old{opacity:.5;text-decoration:line-through}
.ih-pol .add{color:var(--arc);font-weight:650}
.ih-ok{color:var(--ok);font-weight:650}.ih-bad{color:var(--blk);font-weight:650}
</style>""", unsafe_allow_html=True)


# ---------- data ----------

@st.cache_resource
def atlas() -> Atlas:
    return Atlas()


def load():
    a = atlas()
    ledger = list(a.action_ledger.find({}, {"_id": 0}).sort("ts", -1).limit(400))[::-1]
    incidents = list(a.security_incidents.find({}, {"_id": 0}).sort("ts", -1).limit(100))[::-1]
    inc_ts = {i["incident_id"]: utc(i["ts"]) for i in incidents}
    policies = []
    for d in a.security_policies.find({}):
        # ObjectId time is floored to the second; a policy can't exist before the incident it came from
        d["oid_time"] = d.pop("_id").generation_time
        src = inc_ts.get(d.get("source_incident"))
        d["created"] = max(d["oid_time"], src + timedelta(milliseconds=1)) if src else d["oid_time"]
        policies.append(d)
    policies.sort(key=lambda d: (d["policy_id"], d["version"]))
    return {"ledger": ledger, "incidents": incidents, "policies": policies}


def utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def to_policy(d: dict, status: str | None = None) -> Policy:
    doc = {k: v for k, v in d.items() if k not in ("created", "oid_time")}
    if status:
        doc["status"] = status
    return Policy.from_mongo(doc)


def to_action(r: dict) -> Action:
    return Action(agent_id=r["agent_id"], tool=r["tool"], target=r["target"], args=r.get("args") or {}, ts=r["ts"])


def path_of(r: dict) -> str:
    if r.get("policy_id") or r.get("reason", "").startswith("policy "):
        return "policy"
    m = REASON_RE.match(r.get("reason", ""))
    return m.group(1) if m else "other"


def jev_of(r: dict):
    m = REASON_RE.match(r.get("reason", ""))
    if not m:
        return r.get("risk_score"), None, None
    return float(m.group(2)), m.group(3), float(m.group(4))


def rows_before(ledger, ts):
    return [r for r in ledger if utc(r["ts"]) < utc(ts)]


def policies_at(policies, t):
    """The version of each policy that was live at time t (ObjectId times have 1s resolution)."""
    live = {}
    for d in policies:
        if d.get("status") in ("active", "superseded") and d["created"] <= utc(t):
            if d["policy_id"] not in live or d["version"] > live[d["policy_id"]]["version"]:
                live[d["policy_id"]] = d
    return list(live.values())


def incident_for(data, r):
    for inc in data["incidents"]:
        a = inc["action"]
        if a["agent_id"] == r["agent_id"] and a["target"] == r["target"] and a["tool"] == r["tool"] \
                and abs((utc(a["ts"]) - utc(r["ts"])).total_seconds()) < 1:
            return inc
    return None


def row_for(data, inc):
    a = inc["action"]
    for r in reversed(data["ledger"]):
        if r["agent_id"] == a["agent_id"] and r["target"] == a["target"] and r["tool"] == a["tool"] \
                and abs((utc(r["ts"]) - utc(a["ts"])).total_seconds()) < 1:
            return r
    return None


def policy_from_incident(data, inc):
    return next((d for d in data["policies"] if d.get("source_incident") == inc["incident_id"]), None)


def previous_version(data, pol):
    return next((d for d in data["policies"]
                 if d["policy_id"] == pol["policy_id"] and d["version"] == pol["version"] - 1), None)


def is_baseline(d) -> bool:
    return d["policy_id"].startswith("p_baseline")


# ---------- html helpers ----------

def e(x) -> str:
    return html.escape(str(x))


def ago(ts) -> str:
    s = (datetime.now(UTC) - utc(ts)).total_seconds()
    return f"{s:.0f}s ago" if s < 90 else f"{s / 60:.0f}m ago" if s < 5400 else utc(ts).strftime("%H:%M")


def chip(text, kind) -> str:
    return f'<span class="chip {kind}">{e(text)}</span>'


def decision_chip(r) -> str:
    return chip("✗ BLOCK", "block") if r["decision"] == "block" else chip("✓ ALLOW", "allow")


def path_chip(r) -> str:
    p = path_of(r)
    if p == "policy":
        return chip(f"policy {r.get('policy_id') or ''}".strip(), "policy")
    return chip("Jev" if p == "jev" else "fallback rules", "jev")


def meter(risk: float, fill: float | None = None) -> str:
    fill = risk if fill is None else fill
    color = "var(--blk)" if risk > THRESHOLD else "var(--ok)"
    return (f'<div class="meter"><span style="width:{fill * 100:.0f}%;background:{color}"></span>'
            f'<i style="left:{THRESHOLD * 100:.0f}%"></i></div>'
            f'<div class="meter-l"><span>0 safe</span><span>block &gt; {THRESHOLD:.2f}</span><span>1 attack</span></div>')


def action_text(r) -> str:
    args = r.get("args") or {}
    extra = ""
    if args.get("content"):
        extra = f'<br>content: <code>{e(str(args["content"])[:90])}</code>'
    elif args.get("body"):
        extra = f'<br>message: <code>{e(str(args["body"])[:110])}</code>'
    return f'<b>{e(r["agent_id"])}</b> → <code>{e(r["tool"])}</code> <code>{e(r["target"])}</code>{extra}'


def card(i, s, state) -> str:
    body = s["body"](s.get("fill")) if callable(s["body"]) else s["body"]
    return (f'<div class="ih"><div class="ih-stage {state}"><div class="ih-num">{i}</div><div>'
            f'<div class="ih-who">{e(s["who"])}</div><div class="ih-title">{s["title"]}</div>'
            f'<div class="ih-body">{body}</div></div></div></div>')


# ---------- the story of one action, stage by stage ----------

def explain_miss(p: Policy, action: Action, before) -> str:
    from fnmatch import fnmatchcase
    if action.tool not in p.tool:
        return f"doesn't cover <code>{e(action.tool)}</code>"
    if not any(fnmatchcase(action.target, g) for g in p.target_glob):
        return "path not in " + ", ".join(f"<code>{e(g)}</code>" for g in p.target_glob)
    if p.condition == "resource_touched_by_other_agent":
        return "no other agent touched this file"
    return "condition not met"


def build_stages(data, r):
    ledger, stages = data["ledger"], []
    action, before = to_action(r), rows_before(data["ledger"], r["ts"])
    path = path_of(r)

    stages.append(dict(who="Agent (sandboxed)", title="Proposes an action", body=action_text(r)
                       + f'<br><span style="opacity:.7">{utc(r["ts"]).strftime("%H:%M:%S.%f")[:-3]} UTC · '
                       f'intercepted by <code>harness.call()</code> → <code>POST /evaluate</code></span>'))

    live = policies_at(data["policies"], r["ts"])
    lines, hit = [], None
    for d in live:
        p = to_policy(d, "active")
        if policy_matches(p, action, before, set(AUTHORIZED_EDGES)):
            hit = d
            name = f"{d['policy_id']} v{d['version']}"
            lines.append(f'<span class="ih-bad">✗ match</span> {chip(name, "policy")}')
        else:
            lines.append(f'<span style="opacity:.7">– {e(d["policy_id"])} v{d["version"]}: '
                         f'{explain_miss(p, action, before)}</span>')
    if path == "policy":
        title = f'Known attack: matches {chip(r.get("policy_id") or "policy", "policy")}'
    else:
        title = f"No policy matches ({len(live)} checked) → ask Jev"
    stages.append(dict(who="Gateway · policy memory (Atlas, hot-reloaded)", title=title,
                       body="<br>".join(lines) or "no policies yet"))

    if path == "policy":
        pol = next((d for d in data["policies"] if d["policy_id"] == r.get("policy_id")), None)
        stages.append(dict(who="Jev", title="Skipped — no LLM call needed",
                           body=f'The attack is already in memory. Rule: <i>{e(pol["rationale"]) if pol else ""}</i>'))
        stages.append(dict(who="Gateway", title=f'{decision_chip(r)} in {r["latency_ms"]:.0f} ms',
                           body="Tool never runs. Known attack → no incident, so the Architect is not triggered again."))
        return stages

    others = [x for x in before if x["target"] == r["target"] and x["agent_id"] != r["agent_id"]
              and utc(r["ts"]) - utc(x["ts"]) <= timedelta(seconds=600)][-5:]
    ctx = "<br>".join(f'{decision_chip(x)} <b>{e(x["agent_id"])}</b> <code>{e(x["tool"])}</code> '
                      f'{(utc(r["ts"]) - utc(x["ts"])).total_seconds():.1f}s earlier' for x in others)
    stages.append(dict(who="Gateway · action_ledger (Atlas)", title="Collects evidence on the same resource",
                       body=ctx or "No other agent touched this resource recently."))

    risk, cat, conf = jev_of(r)
    who = "Jev (OpenRouter)" if path == "jev" else "Fallback rules (Jev unavailable)"
    risk = risk if risk is not None else 0.0

    def jev_body(fill, risk=risk, cat=cat, conf=conf):
        c = chip(cat or "?", "block" if (cat and cat != "benign") else "allow")
        return f'risk <b>{risk:.2f}</b> · category {c} · confidence {conf or 0:.2f}' + meter(risk, fill)
    stages.append(dict(who=who, title="Scores the action", body=jev_body, risk=risk))

    blocked = r["decision"] == "block"
    stages.append(dict(who="Gateway", title=f'{decision_chip(r)} in {r["latency_ms"]:.0f} ms',
                       body=(f"risk {risk:.2f} &gt; {THRESHOLD:.2f} → tool never runs"
                             if blocked else "Tool runs inside ./sandbox. Every action is logged to action_ledger.")))
    if not blocked:
        return stages

    inc = incident_for(data, r)
    if not inc:
        stages.append(dict(who="Atlas · security_incidents", title="Incident not found",
                           body="No incident recorded for this block."))
        return stages
    stages.append(dict(who="Atlas · security_incidents", title=f'New incident <code>{e(inc["incident_id"][:12])}…</code>',
                       body=f'{len(inc.get("context", []))} evidence rows attached · change stream wakes the Architect'))

    pol = policy_from_incident(data, inc)
    if not pol:
        waited = (datetime.now(UTC) - utc(inc["ts"])).total_seconds()
        stages.append(dict(who="Architect (LLM)", title="Drafting a policy…" if waited < 30 else "No policy produced",
                           body="Waiting for the incident watcher." if waited < 30 else
                           "The Compiler rejected the draft, or <code>harness.incident_watcher</code> isn't running."))
        return stages

    took = learn_time(pol, inc)
    prev = previous_version(data, pol)
    globs = " ".join(f'<code>{e(g)}</code>' for g in pol["target_glob"])
    stages.append(dict(who="Architect (LLM → structured output)",
                       title=f'Drafts {chip(pol["policy_id"] + " v" + str(pol["version"]), "arc")}'
                             + (" — widens the existing rule" if prev else " — new rule"),
                       body=f'<i>“{e(pol["rationale"])}”</i><br>deny <code>{e(", ".join(pol["tool"]))}</code> on {globs}'
                            f' · when <code>{e(pol["condition"])}</code>'))

    stages.append(dict(who="Compiler (pure Python, same matcher as the gateway)", title="Validates before activating",
                       body=compiler_checks(data, pol, inc, prev)))

    stages.append(dict(who="Atlas · security_policies → change stream",
                       title=f'{chip(pol["policy_id"] + " v" + str(pol["version"]), "policy")} is live · '
                             f'{took} after the incident',
                       body=(f'v{prev["version"]} marked <i>superseded</i>. ' if prev else "")
                            + "Every gateway reloads it instantly — no restart."))

    nxt = next((x for x in ledger if x.get("policy_id") == pol["policy_id"] and utc(x["ts"]) >= pol["created"]), None)
    if nxt:
        stages.append(dict(who="Next attempt", title=f'{decision_chip(nxt)} by memory in {nxt["latency_ms"]:.0f} ms',
                           body=action_text(nxt) + f'<br>No Jev call · no new incident · first catch took '
                                                   f'{r["latency_ms"]:.0f} ms, then {took} to learn'))
    else:
        stages.append(dict(who="Next attempt", title="Waiting for the next attempt…",
                           body="The next matching action will be blocked by this policy, without Jev."))
    return stages


def learn_time(pol, inc) -> str:
    """Incident -> policy saved. ObjectId time has 1s resolution, so report a range."""
    t = (pol["oid_time"] - utc(inc["ts"])).total_seconds()
    return "under 1 s" if t < 1 else f"{t:.0f}–{t + 1:.0f} s"


def compiler_checks(data, pol, inc, prev) -> str:
    edges = set(AUTHORIZED_EDGES)
    p = to_policy(pol, "active")
    scope_ok = not any(g in BAD_GLOBS for g in p.target_glob)
    trig = to_action(inc["action"])
    history = rows_before(data["ledger"], inc["ts"])
    trig_ok = policy_matches(p, trig, rows_before(history, trig.ts), edges)
    allowed = [x for x in history if x["decision"] == "allow"][-REPLAY_ROWS:]
    hits = [x for x in allowed if policy_matches(p, to_action(x), rows_before(history, x["ts"]), edges)]
    fp = len(hits) / len(allowed) if allowed else 0.0
    ok = lambda b: '<span class="ih-ok">✓</span>' if b else '<span class="ih-bad">✗</span>'  # noqa: E731
    out = [f'{ok(scope_ok)} scope not too broad (no <code>*</code>, <code>/*</code>)',
           f'{ok(p.effect == "deny")} deny-only',
           f'{ok(trig_ok)} would have blocked the triggering action',
           f'{ok(fp < MAX_FP)} replay: {len(hits)} of {len(allowed)} past allowed actions blocked '
           f'({fp:.0%} false positives, limit {MAX_FP:.0%})']
    if prev:
        added = [g for g in pol["target_glob"] if g not in prev["target_glob"]]
        out.append(f'{ok(True)} only widens v{prev["version"]}: keeps '
                   + " ".join(f'<code>{e(g)}</code>' for g in prev["target_glob"])
                   + ", adds " + " ".join(f'<code class="add">{e(g)}</code>' for g in added))
    return "<br>".join(out)


def play(stages, speed, animate):
    slots = [st.empty() for _ in stages]
    for i, s in enumerate(stages, 1):
        slots[i - 1].html(card(i, s, "pending" if animate else "done"))
    if not animate:
        return
    for i, s in enumerate(stages, 1):
        if "risk" in s:  # animate Jev's meter filling up
            for k in range(1, 9):
                s["fill"] = s["risk"] * k / 8
                slots[i - 1].html(card(i, s, "active"))
                time.sleep(speed / 10)
            s["fill"] = None
        slots[i - 1].html(card(i, s, "active"))
        time.sleep(speed)
        slots[i - 1].html(card(i, s, "done"))


# ---------- live view pieces ----------

def kpis(data):
    L = data["ledger"]
    pol_blocks = [r for r in L if r["decision"] == "block" and path_of(r) == "policy"]
    jev_rows = [r for r in L if path_of(r) in ("jev", "fallback")]
    jev_blocks = [r for r in jev_rows if r["decision"] == "block"]
    learned = [d for d in data["policies"] if not is_baseline(d)]
    med = lambda rows: f'{median(r["latency_ms"] for r in rows):.0f} ms' if rows else "–"  # noqa: E731
    tiles = [(len(L), "actions seen"), (sum(r["decision"] == "allow" for r in L), "✓ allowed"),
             (len(jev_blocks), "✗ caught by Jev"), (len(pol_blocks), "✗ blocked by memory"),
             (len(data["incidents"]), "incidents"), (len(learned), "policy versions learned"),
             (med(pol_blocks), "memory block (median)"), (med(jev_rows), "Jev decision (median)")]
    return '<div class="ih"><div class="ih-kpis">' + "".join(
        f'<div class="ih-kpi"><b>{v}</b><span>{e(t)}</span></div>' for v, t in tiles) + "</div></div>"


def strip(data, r) -> str:
    path, blocked = path_of(r), r["decision"] == "block"
    inc = incident_for(data, r) if blocked and path != "policy" else None
    pol = policy_from_incident(data, inc) if inc else None
    nodes = [("Agent", f'{e(r["agent_id"])} · {e(r["tool"])}', "good")]
    if path == "policy":
        nodes += [("Policy memory", f'match {e(r.get("policy_id"))}', "hit"), ("Jev", "skipped", "off")]
    else:
        risk, cat, _ = jev_of(r)
        nodes += [("Policy memory", "no match", ""),
                  ("Jev", f'{risk or 0:.2f} {e(cat or "")}', "bad" if blocked else "good")]
    nodes.append(("Decision", "✗ BLOCK" if blocked else "✓ ALLOW", "bad" if blocked else "good"))
    if inc:
        nodes.append(("Incident", inc["incident_id"][:10], "bad"))
        if pol:
            nodes += [("Architect", f'{e(pol["policy_id"])}', "good"), ("Compiler", "✓ validated", "good"),
                      ("Policy live", f'v{pol["version"]}', "hit")]
        elif (datetime.now(UTC) - utc(inc["ts"])).total_seconds() < 30:
            nodes += [("Architect", "drafting…", "busy"), ("Compiler", "", "off"), ("Policy live", "", "off")]
        else:
            nodes += [("Architect", "no policy", "off"), ("Compiler", "rejected / not run", "off"),
                      ("Policy live", "–", "off")]
    else:
        nodes += [("Incident", "–", "off"), ("Architect", "–", "off"), ("Compiler", "–", "off"),
                  ("Policy live", "–", "off")]
    out = []
    for k, (title, sub, cls) in enumerate(nodes):
        if k:
            out.append('<span class="ih-arrow">→</span>')
        out.append(f'<div class="ih-node {cls}"><small>{title}</small>{sub}</div>')
    return '<div class="ih"><div class="ih-strip">' + "".join(out) + "</div></div>"


def feed(data, n=22) -> str:
    rows = data["ledger"][-n:][::-1]
    now = datetime.now(UTC)
    body = []
    for r in rows:
        risk, cat, _ = jev_of(r)
        new = "new" if (now - utc(r["ts"])).total_seconds() < 3 else ""
        body.append(f'<tr class="{new}"><td>{ago(r["ts"])}</td><td><b>{e(r["agent_id"])}</b></td>'
                    f'<td><code>{e(r["tool"])}</code></td><td><code>{e(r["target"][:34])}</code></td>'
                    f'<td>{decision_chip(r)}</td><td>{path_chip(r)}</td>'
                    f'<td class="num">{"" if risk is None else f"{risk:.2f}"}</td>'
                    f'<td>{e(cat or "")}</td><td class="num">{r["latency_ms"]:.0f} ms</td></tr>')
    head = "<tr><th>when</th><th>agent</th><th>tool</th><th>target</th><th>decision</th><th>decided by</th>" \
           "<th>risk</th><th>category</th><th>latency</th></tr>"
    return f'<div class="ih"><table class="ih-feed">{head}{"".join(body)}</table></div>'


def memory(data) -> str:
    by = {}
    for d in data["policies"]:
        by.setdefault(d["policy_id"], []).append(d)
    learned = sorted((k for k in by if not k.startswith("p_baseline")), key=lambda k: -max(
        d["created"].timestamp() for d in by[k]))
    out = []
    for pid in learned + sorted(k for k in by if k.startswith("p_baseline")):
        versions = sorted(by[pid], key=lambda d: d["version"])
        kind = "baseline (seeded)" if pid.startswith("p_baseline") else "learned"
        lines, prev = [], None
        for d in versions:
            globs = []
            for g in d["target_glob"]:
                cls = "add" if prev and g not in prev["target_glob"] else ""
                globs.append(f'<code class="{cls}">{e(g)}</code>')
            st_chip = chip(d["status"], "policy" if d["status"] == "active" else "mute")
            lines.append(f'<div class="v {"old" if d["status"] == "superseded" else ""}"><b>v{d["version"]}</b> '
                         f'{st_chip} {" ".join(globs)} <span style="opacity:.6">{ago(d["created"])}</span></div>')
            prev = d
        out.append(f'<div class="ih-pol"><b>{e(pid)}</b> <span style="opacity:.6">· {kind} · '
                   f'{e(", ".join(versions[-1]["tool"]))}</span>{"".join(lines)}'
                   f'<div style="opacity:.7;margin-top:3px"><i>{e(versions[-1]["rationale"])}</i></div></div>')
    return '<div class="ih">' + ("".join(out) or "No policies yet.") + "</div>"


def label(r) -> str:
    p = path_of(r)
    who = "memory" if p == "policy" else p
    return (f'{utc(r["ts"]).strftime("%H:%M:%S")} · {r["agent_id"]} {r["tool"]} {r["target"][:40]} · '
            f'{r["decision"].upper()} ({who})')


# ---------- page ----------

with st.sidebar:
    st.markdown("### 🛡️ Immune Harness")
    mode = st.radio("View", ["Live", "Slow-mo replay"], horizontal=True)
    speed = st.slider("Slow-mo: seconds per step", 0.3, 4.0, 1.4, 0.1)
    refresh = st.slider("Live refresh (s)", 0.5, 5.0, 1.0, 0.5)
    try:
        s = atlas().settings
        st.caption(f"Atlas database: `{s.database}`")
    except Exception as ex:  # noqa: BLE001
        st.error(f"Atlas not reachable: {ex}")
        st.stop()
    with st.expander("Reset demo data"):
        st.caption("Deletes all actions, incidents and learned policies in this database. Baselines stay.")
        sure = st.checkbox("I'm sure")
        if st.button("Reset", disabled=not sure, type="primary"):
            a = atlas()
            a.action_ledger.delete_many({})
            a.security_incidents.delete_many({})
            a.security_policies.delete_many({"policy_id": {"$not": {"$regex": "^p_baseline"}}})
            st.session_state.pop("played", None)
            st.success("Reset done")

st.markdown("## Immune Harness — watching agents learn to be safe")
st.caption("Agent → policy memory → Jev → decision → incident → Architect → Compiler → Atlas → next attempt "
           "blocked from memory")

if mode == "Live":
    @st.fragment(run_every=refresh)
    def live():
        data = load()
        st.html(kpis(data))
        if data["ledger"]:
            last = data["ledger"][-1]
            focus = last
            # while the Architect is still working, keep the pipeline on the newest incident
            if data["incidents"]:
                inc = data["incidents"][-1]
                r = row_for(data, inc)
                if r and (datetime.now(UTC) - utc(inc["ts"])).total_seconds() < 12:
                    focus = r
            st.markdown(f"**Pipeline** — {e(label(focus))}")
            st.html(strip(data, focus))
        else:
            st.info("No actions yet — run `./run_demo.sh` or `uv run python -m agents.scenarios --all`.")
        left, right = st.columns([3, 2], gap="large")
        with left:
            st.markdown("**Every action, newest first**")
            st.html(feed(data))
        with right:
            st.markdown("**Policy memory** (Atlas `security_policies`)")
            st.html(memory(data))
    live()

else:
    data = load()
    follow = st.toggle("Auto-play each new incident as it happens", value=False,
                       help="Leave this on during the live demo: every new Jev block is replayed step by step.")
    if follow:
        @st.fragment(run_every=1.0)
        def follower():
            d = load()
            played = st.session_state.setdefault("played", {i["incident_id"] for i in d["incidents"]})
            new = [i for i in d["incidents"] if i["incident_id"] not in played]
            if not new:
                last = st.session_state.get("last_story")
                if last:
                    play(last, speed, animate=False)
                else:
                    st.info("Watching for the next incident… (run the demo now)")
                return
            inc = new[0]
            r = row_for(d, inc)
            if not r:
                return
            # give the Architect time to finish so the whole story is there
            t0 = time.time()
            while not policy_from_incident(d, inc) and time.time() - t0 < 12:
                time.sleep(0.5)
                d = load()
            played.add(inc["incident_id"])
            st.markdown(f"**Replaying:** {e(label(r))}")
            stages = build_stages(d, r)
            play(stages, speed, animate=True)
            st.session_state["last_story"] = stages
        follower()
    else:
        rows = data["ledger"][-80:][::-1]
        if not rows:
            st.info("No actions yet.")
            st.stop()
        default = 0
        if data["incidents"]:
            r0 = row_for(data, data["incidents"][-1])
            default = next((k for k, r in enumerate(rows) if r is r0), 0)
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        pick = c1.selectbox("Action to replay", range(len(rows)), index=default, format_func=lambda k: label(rows[k]))
        go = c2.button("▶ Play", type="primary", use_container_width=True)
        play(build_stages(data, rows[pick]), speed, animate=go)
