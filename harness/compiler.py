"""Compiler: validate a draft Policy, replay it against the ledger, then version it (supersede the old one).

Pure functions over the shared db.schemas types; the caller persists the result.
"""
from dataclasses import dataclass
from datetime import timedelta
from fnmatch import fnmatch

from db.schemas import Action, Incident, LedgerEntry, Policy

MAX_FP = 0.05
BAD_GLOBS = {"*", "/*", "**"}
SUPPORTED = {"always", "resource_touched_by_other_agent"}


@dataclass
class CompileResult:
    ok: bool
    reason: str
    policy: Policy | None = None      # new active version to insert
    superseded: Policy | None = None  # old version to mark superseded (status="superseded")


def matches(policy: Policy, action: Action, ledger: list[LedgerEntry]) -> bool:
    if action.tool not in policy.tool:
        return False
    if not any(fnmatch(action.target, g) for g in policy.target_glob):
        return False
    if policy.condition == "always":
        return True
    window = timedelta(seconds=policy.window_s)
    return any(
        r.target == action.target and r.agent_id != action.agent_id
        and timedelta(0) <= action.ts - r.ts <= window
        for r in ledger if r.ts < action.ts
    )


def compile_policy(draft: Policy, incident: Incident, active: list[Policy], ledger: list[LedgerEntry]) -> CompileResult:
    if draft.condition not in SUPPORTED:
        return CompileResult(False, f"unsupported condition {draft.condition}")
    if any(g in BAD_GLOBS for g in draft.target_glob):
        return CompileResult(False, "scope too broad")

    old = max((p for p in active if p.policy_id == draft.policy_id and p.status == "active"),
              key=lambda p: p.version, default=None)
    fields = draft.model_dump()
    if old:  # a new version may only widen: keep everything the old version covered
        fields["target_glob"] = (*old.target_glob, *(g for g in draft.target_glob if g not in old.target_glob))
        fields["tool"] = (*old.tool, *(t for t in draft.tool if t not in old.tool))
        fields["version"] = old.version + 1
    fields["status"] = "active"
    policy = Policy(**fields)

    history = list({e.action_id: e for e in [*ledger, *incident.context]}.values())
    if not matches(policy, incident.action, history):
        return CompileResult(False, "policy would not have blocked the triggering action")

    allowed = sorted((r for r in history if r.decision == "allow"), key=lambda r: r.ts)[-200:]
    hits = [r for r in allowed if matches(policy, r, history)]
    fp = len(hits) / len(allowed) if allowed else 0.0
    if fp >= MAX_FP:
        return CompileResult(False, f"false positive rate {fp:.0%} >= {MAX_FP:.0%}")

    superseded = old.model_copy(update={"status": "superseded"}) if old else None
    return CompileResult(True, f"ok (replay FP {fp:.0%} over {len(allowed)} rows)", policy, superseded)


def process_incident(incident: Incident, active: list[Policy], ledger: list[LedgerEntry]) -> CompileResult:
    """The whole D pipeline. Caller inserts result.policy, supersedes result.superseded, sets incident.policy_id."""
    from harness.architect import draft_policy
    draft = draft_policy(incident, active, ledger)
    return compile_policy(draft, incident, active, ledger)
