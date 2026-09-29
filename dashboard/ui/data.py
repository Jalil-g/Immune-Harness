"""Data layer: reads Atlas, interprets ledger rows, and recomputes the Compiler's checks.

No HTML here. The Compiler checks use the same functions the Compiler uses, so nothing extra is stored.
"""
import os
import re
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase

import streamlit as st

from db.atlas import Atlas
from db.schemas import Action, Policy
from harness.compiler import BAD_GLOBS, MAX_FP
from harness.sentry import policy_matches

try:
    from agents.config import AUTHORIZED_EDGES
except ImportError:
    AUTHORIZED_EDGES = set()

THRESHOLD = float(os.environ.get("RISK_THRESHOLD", "0.8"))
HOLD_S = 8  # how long the pipeline stays on a fresh memory block
REASON_RE = re.compile(r"^(jev|fallback) risk=([\d.]+) category=(\w+) \(([\d.]+)\)")
REPLAY_ROWS = 200


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


def reset_demo_data():
    a = atlas()
    a.action_ledger.delete_many({})
    a.security_incidents.delete_many({})
    a.security_policies.delete_many({"policy_id": {"$not": {"$regex": "^p_baseline"}}})


def utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def age_s(ts) -> float:
    return (datetime.now(UTC) - utc(ts)).total_seconds()


def to_policy(d: dict, status: str | None = None) -> Policy:
    doc = {k: v for k, v in d.items() if k not in ("created", "oid_time")}
    if status:
        doc["status"] = status
    return Policy.from_mongo(doc)


def to_action(r: dict) -> Action:
    return Action(agent_id=r["agent_id"], tool=r["tool"], target=r["target"], args=r.get("args") or {}, ts=r["ts"])


def path_of(r: dict) -> str:
    """'policy' (blocked from memory), 'jev', 'fallback' or 'other'."""
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
    """The version of each policy that was live at time t."""
    live = {}
    for d in policies:
        if d.get("status") in ("active", "superseded") and d["created"] <= utc(t):
            if d["policy_id"] not in live or d["version"] > live[d["policy_id"]]["version"]:
                live[d["policy_id"]] = d
    return list(live.values())


def check_policies(data, r):
    """Re-run the gateway's policy check for row r: [(policy_doc, matched, miss_reason)]."""
    action, before = to_action(r), rows_before(data["ledger"], r["ts"])
    out = []
    for d in policies_at(data["policies"], r["ts"]):
        p = to_policy(d, "active")
        if policy_matches(p, action, before, set(AUTHORIZED_EDGES)):
            out.append((d, True, None))
        elif action.tool not in p.tool:
            out.append((d, False, ("tool", action.tool)))
        elif not any(fnmatchcase(action.target, g) for g in p.target_glob):
            out.append((d, False, ("path", list(p.target_glob))))
        elif p.condition == "resource_touched_by_other_agent":
            out.append((d, False, ("untouched", None)))
        else:
            out.append((d, False, ("condition", p.condition)))
    return out


def evidence(data, r, limit=5):
    """Other agents' recent actions on the same resource (what the gateway hands Jev)."""
    before = rows_before(data["ledger"], r["ts"])
    return [x for x in before if x["target"] == r["target"] and x["agent_id"] != r["agent_id"]
            and utc(r["ts"]) - utc(x["ts"]) <= timedelta(seconds=600)][-limit:]


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


def policy_doc(data, policy_id):
    docs = [d for d in data["policies"] if d["policy_id"] == policy_id]
    return max(docs, key=lambda d: d["version"]) if docs else None


def next_blocked_by(data, pol):
    return next((x for x in data["ledger"]
                 if x.get("policy_id") == pol["policy_id"] and utc(x["ts"]) >= pol["created"]), None)


def is_baseline(d) -> bool:
    return d["policy_id"].startswith("p_baseline")


def learn_time(pol, inc) -> str:
    """Incident -> policy saved. ObjectId time has 1s resolution, so report a range."""
    t = (pol["oid_time"] - utc(inc["ts"])).total_seconds()
    return "under 1 s" if t < 1 else f"{t:.0f}–{t + 1:.0f} s"


def compiler_checks(data, pol, inc, prev) -> dict:
    edges = set(AUTHORIZED_EDGES)
    p = to_policy(pol, "active")
    trig = to_action(inc["action"])
    history = rows_before(data["ledger"], inc["ts"])
    allowed = [x for x in history if x["decision"] == "allow"][-REPLAY_ROWS:]
    hits = [x for x in allowed if policy_matches(p, to_action(x), rows_before(history, x["ts"]), edges)]
    return {
        "scope_ok": not any(g in BAD_GLOBS for g in p.target_glob),
        "deny_ok": p.effect == "deny",
        "trigger_ok": policy_matches(p, trig, rows_before(history, trig.ts), edges),
        "hits": len(hits), "replayed": len(allowed),
        "fp": len(hits) / len(allowed) if allowed else 0.0, "max_fp": MAX_FP,
        "kept": list(prev["target_glob"]) if prev else [],
        "added": [g for g in pol["target_glob"] if prev and g not in prev["target_glob"]],
    }


def stats(data) -> dict:
    L = data["ledger"]
    mem = [r for r in L if r["decision"] == "block" and path_of(r) == "policy"]
    jev = [r for r in L if path_of(r) in ("jev", "fallback")]
    return {
        "actions": len(L),
        "allowed": sum(r["decision"] == "allow" for r in L),
        "caught_by_jev": sum(r["decision"] == "block" for r in jev),
        "blocked_by_memory": len(mem),
        "incidents": len(data["incidents"]),
        "learned": sum(not is_baseline(d) for d in data["policies"]),
        "mem_ms": _median([r["latency_ms"] for r in mem]),
        "jev_ms": _median([r["latency_ms"] for r in jev]),
    }


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def focus_row(data):
    """The event the pipeline should show. Priority: an incident still being learned, then a memory block held
    for HOLD_S seconds so the payoff frame can be read, else the newest action."""
    if not data["ledger"]:
        return None
    focus = data["ledger"][-1]
    if data["incidents"]:
        inc = data["incidents"][-1]
        r = row_for(data, inc)
        if r and age_s(inc["ts"]) < 12:
            return r
    for r in reversed(data["ledger"][-12:]):
        if r["decision"] == "block" and path_of(r) == "policy" and age_s(r["ts"]) < HOLD_S:
            return r
    return focus
