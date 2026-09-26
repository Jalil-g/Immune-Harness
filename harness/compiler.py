"""Compiler: validate a draft Policy, replay it against the ledger, then version it (supersede the old one).

Pure functions over the shared db.schemas types; the caller persists the result.
Matching is Sentry's `policy_matches`, so replay predicts exactly what the gateway will do.
"""
from dataclasses import dataclass

from db.schemas import Action, Incident, LedgerEntry, Policy
from harness.sentry import policy_matches

MAX_FP = 0.05
BAD_GLOBS = {"*", "/*", "**"}
NO_EDGES: frozenset[tuple[str, str]] = frozenset()


@dataclass
class CompileResult:
    ok: bool
    reason: str
    policy: Policy | None = None      # new active version to insert into security_policies
    superseded: Policy | None = None  # old version to mark superseded (status="superseded")


def _as_action(e: LedgerEntry) -> Action:
    return Action(agent_id=e.agent_id, tool=e.tool, target=e.target, args=e.args, ts=e.ts)


def _blocks(policy: Policy, action: Action, history: list[dict], edges) -> bool:
    """Would `policy` block `action` given only what happened before it (the gateway sees only the past)."""
    before = [r for r in history if r["ts"] < action.ts]
    return policy_matches(policy, action, before, set(edges))


def compile_policy(draft: Policy, incident: Incident, active: list[Policy], ledger: list[LedgerEntry],
                   authorized_edges=NO_EDGES) -> CompileResult:
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

    entries = list({e.action_id: e for e in [*ledger, *incident.context]}.values())
    history = [e.model_dump() for e in entries]
    if not _blocks(policy, incident.action, history, authorized_edges):
        return CompileResult(False, "policy would not have blocked the triggering action")

    allowed = sorted((e for e in entries if e.decision == "allow"), key=lambda e: e.ts)[-200:]
    hits = [e for e in allowed if _blocks(policy, _as_action(e), history, authorized_edges)]
    fp = len(hits) / len(allowed) if allowed else 0.0
    if fp >= MAX_FP:
        return CompileResult(False, f"false positive rate {fp:.0%} >= {MAX_FP:.0%}")

    superseded = old.model_copy(update={"status": "superseded"}) if old else None
    return CompileResult(True, f"ok (replay FP {fp:.0%} over {len(allowed)} rows)", policy, superseded)


def process_incident(incident: Incident, active: list[Policy], ledger: list[LedgerEntry],
                     authorized_edges=NO_EDGES) -> CompileResult:
    """The whole D pipeline. Caller inserts result.policy, supersedes result.superseded, sets incident.policy_id."""
    from harness.architect import draft_policy
    draft = draft_policy(incident, active, ledger)
    return compile_policy(draft, incident, active, ledger, authorized_edges)
