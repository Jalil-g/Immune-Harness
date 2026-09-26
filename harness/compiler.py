"""Compiler: validate a draft Policy, replay it against the ledger, then activate it (version + supersede)."""
from fnmatch import fnmatch
from harness.architect import Policy

MAX_FP = 0.05
BAD_GLOBS = {"*", "/*", "**"}


def matches(policy: dict, action: dict, ledger: list[dict]) -> bool:
    if action["tool"] not in policy["tool"]:
        return False
    if not any(fnmatch(action["target"], g) for g in policy["target_glob"]):
        return False
    if policy["condition"] == "always":
        return True
    # resource_touched_by_other_agent
    return any(
        r["target"] == action["target"] and r["agent_id"] != action["agent_id"]
        and 0 <= action["ts"] - r["ts"] <= policy["window_s"]
        for r in ledger if r["ts"] < action["ts"]
    )


def compile_policy(draft: Policy, incident: dict, store: dict):
    """Returns (ok, reason, policy_dict)."""
    p = draft.model_dump()
    if any(g in BAD_GLOBS for g in p["target_glob"]):
        return False, "scope too broad", None

    old = next((x for x in store["policies"] if x["policy_id"] == p["policy_id"] and x["status"] == "active"), None)
    if old:  # a new version may only widen: keep everything the old version covered
        p["target_glob"] = old["target_glob"] + [g for g in p["target_glob"] if g not in old["target_glob"]]
        p["tool"] = old["tool"] + [t for t in p["tool"] if t not in old["tool"]]

    ledger = store["ledger"]
    if not matches(p, incident["action"], ledger):
        return False, "policy would not have blocked the triggering action", None

    allowed = [r for r in ledger if r["decision"] == "allow"][-200:]
    hits = [r for r in allowed if matches(p, r, ledger)]
    fp = len(hits) / len(allowed) if allowed else 0.0
    if fp >= MAX_FP:
        return False, f"false positive rate {fp:.0%} >= {MAX_FP:.0%}", None

    if old:
        old["status"] = "superseded"
        p["version"] = old["version"] + 1
    p["status"] = "active"
    return True, f"ok (replay FP {fp:.0%} over {len(allowed)} rows)", p


def process_incident(incident: dict, store: dict) -> None:
    """The whole D pipeline. Swap `store` reads/writes for Mongo later."""
    from harness.architect import draft_policy
    active = [p for p in store["policies"] if p["status"] == "active"]
    draft = draft_policy(incident, active, store["ledger"])
    ok, reason, policy = compile_policy(draft, incident, store)
    if ok:
        store["policies"].append(policy)
        incident["policy_id"] = f'{policy["policy_id"]} v{policy["version"]}'
    incident["compiler"] = reason
