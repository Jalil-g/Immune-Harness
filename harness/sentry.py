"""Sentry: decides allow/block for one action.

1. Policy match against the in-memory cache (fast path, no LLM).
2. Otherwise ask Jev (via OpenRouter); block if violates_guardrails > threshold.

Storage-agnostic: the gateway injects where policies and recent ledger rows come from,
so this works with mocks now and Person B's Atlas policy_cache later.
"""
import os
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch

from harness.contracts import Action, Decision, Policy
from harness.jev import JevScorer

RISK_THRESHOLD = float(os.environ.get("RISK_THRESHOLD", "0.8"))

PolicySource = Callable[[], Iterable[Policy]]
# (target, since) -> recent ledger rows on that target: dicts with agent_id, tool, target, ts, decision
ContextSource = Callable[[str, datetime], list[dict]]


def _as_utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _others_on_target(action: Action, rows: list[dict], window_s: int,
                      authorized_edges: set[tuple[str, str]]) -> list[dict]:
    since = _as_utc(action.ts) - timedelta(seconds=window_s)
    return [
        r for r in rows
        if r["target"] == action.target
        and r["agent_id"] != action.agent_id
        and _as_utc(r["ts"]) >= since
        and (r["agent_id"], action.agent_id) not in authorized_edges
        and (action.agent_id, r["agent_id"]) not in authorized_edges
    ]


def policy_matches(p: Policy, action: Action, rows: list[dict],
                   authorized_edges: set[tuple[str, str]]) -> bool:
    if p.status != "active" or p.effect != "deny":
        return False
    if p.expires_at and _as_utc(p.expires_at) <= _as_utc(action.ts):
        return False
    if action.tool not in p.tool or not any(fnmatch(action.target, g) for g in p.target_glob):
        return False
    if p.condition == "always":
        return True
    if p.condition == "resource_touched_by_other_agent":
        return bool(_others_on_target(action, rows, p.window_s, authorized_edges))
    if p.condition == "rate_exceeds":
        since = _as_utc(action.ts) - timedelta(seconds=p.window_s)
        mine = [r for r in rows if r["agent_id"] == action.agent_id and _as_utc(r["ts"]) >= since]
        return len(mine) + 1 > (p.max_count or 0)
    if p.condition == "unauthorized_recipient":
        return (action.agent_id, action.target) not in authorized_edges
    return False


class Sentry:
    def __init__(self, policies: PolicySource, context: ContextSource, jev: JevScorer | None = None,
                 authorized_edges: set[tuple[str, str]] | None = None,
                 threshold: float = RISK_THRESHOLD, context_window_s: int = 600):
        self.policies = policies
        self.context = context
        self.jev = jev or JevScorer()
        self.authorized_edges = authorized_edges or set()
        self.threshold = threshold
        self.context_window_s = context_window_s

    async def evaluate(self, action: Action) -> Decision:
        start = time.perf_counter()
        since = _as_utc(action.ts) - timedelta(seconds=self.context_window_s)
        rows = self.context(action.target, since)

        for p in self.policies():
            if policy_matches(p, action, rows, self.authorized_edges):
                return Decision(
                    decision="block", source="policy", policy_id=p.policy_id,
                    reason=f"policy {p.policy_id} v{p.version}: {p.rationale or p.condition}",
                    latency_ms=(time.perf_counter() - start) * 1000,
                )

        j = await self.jev.score(action, rows, self.authorized_edges)
        block = j.risk > self.threshold
        return Decision(
            decision="block" if block else "allow",
            source=j.source,
            risk_score=round(j.risk, 4),
            threat_category=j.category,
            category_confidence=round(j.category_confidence, 4),
            reason=f"{j.source} risk={j.risk:.2f} category={j.category} ({j.category_confidence:.2f})",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
