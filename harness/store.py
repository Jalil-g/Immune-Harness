"""Gateway storage: where the Sentry reads policies/context and where the gateway logs actions/incidents.

MemoryStore — tests and offline demo.
AtlasStore  — Person B's db.atlas.Atlas client + harness.policy_cache.PolicyCache (change stream).
Documents are built with db.schemas (LedgerEntry / Incident) so every row validates for B and D.
"""
import asyncio
import logging
import os
from datetime import datetime

from pydantic import ValidationError
from pymongo import DESCENDING

from db.atlas import Atlas, AtlasSettings
from db.schemas import Incident, LedgerEntry
from harness.contracts import AtlasAction, Decision, Policy
from harness.policy_cache import PolicyCache

log = logging.getLogger("harness.store")

CONTEXT_LIMIT = 50  # max ledger rows handed to the Sentry/Jev per action


def ledger_entry(action: AtlasAction, decision: Decision) -> LedgerEntry:
    return LedgerEntry.from_action(action, decision.to_atlas())


def build_incident(action: AtlasAction, decision: Decision, rows: list[dict]) -> Incident:
    context = []
    for r in rows:
        try:
            context.append(LedgerEntry.from_mongo(r))
        except ValidationError:  # a malformed/legacy ledger row must not lose the incident
            log.warning("skipping invalid ledger row %s in incident context", r.get("action_id"))
    return Incident(action=action, decision=decision.to_atlas(), context=context)


class MemoryStore:
    kind = "memory"

    def __init__(self, policies: list[Policy] | None = None):
        self.policies: list[Policy] = list(policies or [])
        self.ledger: list[dict] = []
        self.incidents: list[dict] = []

    @property
    def healthy(self) -> bool:
        return True

    def active_policies(self) -> list[Policy]:
        return [p for p in self.policies if p.status == "active"]

    def add_policy(self, p: Policy) -> None:
        self.policies.append(p)

    async def recent(self, target: str, since: datetime) -> list[dict]:
        rows = [r for r in self.ledger if r["target"] == target and r["ts"] >= since]
        return sorted(rows, key=lambda r: r["ts"], reverse=True)[:CONTEXT_LIMIT]

    async def log_action(self, action: AtlasAction, decision: Decision) -> None:
        self.ledger.append(ledger_entry(action, decision).to_mongo())

    async def log_incident(self, action: AtlasAction, decision: Decision, rows: list[dict]) -> str:
        inc = build_incident(action, decision, rows)
        self.incidents.append(inc.to_mongo())
        return inc.incident_id

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass


class AtlasStore:
    """One Atlas client + one PolicyCache per gateway process. PyMongo is sync -> DB I/O runs in threads."""
    kind = "atlas"

    def __init__(self, settings: AtlasSettings | None = None, **cache_kwargs):
        self.atlas = Atlas(settings)
        self.cache = PolicyCache(self.atlas.security_policies, **cache_kwargs)

    @property
    def healthy(self) -> bool:
        return self.cache.healthy

    def active_policies(self) -> tuple[Policy, ...]:
        # Local snapshot, no DB I/O. Raises PolicyCacheUnavailable -> gateway fails closed (503).
        return self.cache.get_policies()

    async def start(self) -> None:
        # Indexes + baseline policies come from Person B's `python -m db.atlas bootstrap`.
        await asyncio.to_thread(self.atlas.ping)
        await asyncio.to_thread(self.cache.start)

    async def close(self) -> None:
        try:
            await asyncio.to_thread(self.cache.stop)
        finally:
            self.atlas.close()

    async def recent(self, target: str, since: datetime) -> list[dict]:
        def q():
            cur = self.atlas.action_ledger.find({"target": target, "ts": {"$gte": since}}, {"_id": 0}) \
                .sort("ts", DESCENDING).limit(CONTEXT_LIMIT)
            return list(cur)
        return await asyncio.to_thread(q)

    async def log_action(self, action: AtlasAction, decision: Decision) -> None:
        await asyncio.to_thread(self.atlas.action_ledger.insert_one, ledger_entry(action, decision).to_mongo())

    async def log_incident(self, action: AtlasAction, decision: Decision, rows: list[dict]) -> str:
        inc = build_incident(action, decision, rows)
        await asyncio.to_thread(self.atlas.security_incidents.insert_one, inc.to_mongo())
        return inc.incident_id


def store_from_env() -> MemoryStore | AtlasStore:
    if os.environ.get("MONGODB_URI"):
        return AtlasStore()
    log.warning("MONGODB_URI not set — using in-memory store (nothing persisted)")
    return MemoryStore()
