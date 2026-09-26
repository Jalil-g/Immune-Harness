"""Gateway storage: where the Sentry reads policies/context and where the gateway logs actions/incidents.

MemoryStore — tests and offline demo.
MongoStore  — Atlas (action_ledger, security_incidents, security_policies).
Policies are read from an in-memory cache refreshed by polling; Person B's change-stream
policy_cache replaces `refresh_policies` later without touching the Sentry.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime

from pydantic import ValidationError
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient

from harness.contracts import Action, Decision, Policy, utcnow

log = logging.getLogger("harness.store")

CONTEXT_LIMIT = 50  # max ledger rows handed to the Sentry/Jev per action


def ledger_doc(action: Action, decision: Decision) -> dict:
    return {**action.model_dump(), **decision.model_dump(), "logged_at": utcnow()}


def incident_doc(action: Action, decision: Decision, rows: list[dict]) -> dict:
    return {
        "incident_id": f"inc_{uuid.uuid4().hex[:8]}",
        "ts": utcnow(),
        "status": "open",  # Architect sets "policy_proposed" / "resolved"
        "action": action.model_dump(),
        "decision": decision.model_dump(),
        "context": [{k: v for k, v in r.items() if k != "_id"} for r in rows],
        "policy_id": None,  # filled in by the Architect
    }


class MemoryStore:
    kind = "memory"

    def __init__(self, policies: list[Policy] | None = None):
        self.policies: list[Policy] = list(policies or [])
        self.ledger: list[dict] = []
        self.incidents: list[dict] = []

    def active_policies(self) -> list[Policy]:
        return [p for p in self.policies if p.status == "active"]

    def add_policy(self, p: Policy) -> None:
        self.policies.append(p)

    async def recent(self, target: str, since: datetime) -> list[dict]:
        rows = [r for r in self.ledger if r["target"] == target and r["ts"] >= since]
        return sorted(rows, key=lambda r: r["ts"], reverse=True)[:CONTEXT_LIMIT]

    async def log_action(self, action: Action, decision: Decision) -> None:
        self.ledger.append(ledger_doc(action, decision))

    async def log_incident(self, action: Action, decision: Decision, rows: list[dict]) -> str:
        doc = incident_doc(action, decision, rows)
        self.incidents.append(doc)
        return doc["incident_id"]

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass


class MongoStore:
    kind = "atlas"

    def __init__(self, uri: str, db_name: str = "immune_harness", refresh_s: float = 1.0):
        self.client = AsyncMongoClient(uri, tz_aware=True, appname="immune-harness-gateway")
        db = self.client[db_name]
        self.ledger = db["action_ledger"]
        self.incidents = db["security_incidents"]
        self.policies_col = db["security_policies"]
        self.refresh_s = refresh_s
        self._policies: list[Policy] = []
        self._task: asyncio.Task | None = None

    def active_policies(self) -> list[Policy]:
        return self._policies

    async def refresh_policies(self) -> None:
        fresh = []
        async for doc in self.policies_col.find({"status": "active"}, {"_id": 0}):
            try:
                fresh.append(Policy(**doc))
            except ValidationError as e:  # a bad policy doc must not take the gateway down
                log.warning("skipping invalid policy %s: %s", doc.get("policy_id"), e.errors()[:1])
        self._policies = fresh

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await self.refresh_policies()
            except Exception as e:  # noqa: BLE001 — keep serving the last good cache if Atlas blips
                log.warning("policy refresh failed: %s", e)
            await asyncio.sleep(self.refresh_s)

    async def start(self) -> None:
        # Only the index this gateway's hot query needs; TTLs and the rest are Person B's (db/atlas.py).
        await self.ledger.create_index([("target", ASCENDING), ("ts", DESCENDING)])
        await self.refresh_policies()
        self._task = asyncio.create_task(self._refresh_loop())

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
        await self.client.close()

    async def recent(self, target: str, since: datetime) -> list[dict]:
        cur = self.ledger.find({"target": target, "ts": {"$gte": since}}, {"_id": 0}) \
            .sort("ts", DESCENDING).limit(CONTEXT_LIMIT)
        return await cur.to_list()

    async def log_action(self, action: Action, decision: Decision) -> None:
        await self.ledger.insert_one(ledger_doc(action, decision))

    async def log_incident(self, action: Action, decision: Decision, rows: list[dict]) -> str:
        doc = incident_doc(action, decision, rows)
        await self.incidents.insert_one(doc)
        return doc["incident_id"]


def store_from_env() -> MemoryStore | MongoStore:
    uri = os.environ.get("MONGODB_URI")
    if uri:
        return MongoStore(uri, os.environ.get("MONGODB_DB", "immune_harness"))
    log.warning("MONGODB_URI not set — using in-memory store (nothing persisted)")
    return MemoryStore()
