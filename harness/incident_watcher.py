"""Incident watcher: new security_incidents -> Architect + Compiler -> new policy version in Atlas.

The gateway inserts an Incident when Jev blocks a novel attack. This process watches for those
inserts, runs `process_incident`, and persists the result. PolicyCache then hot-reloads the policy,
so the next attempt is blocked by policy. Policy blocks never create incidents, so there is no loop.

Run: uv run python -m harness.incident_watcher
"""
import logging
import os
import threading

from dotenv import load_dotenv
from pydantic import ValidationError
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from db.atlas import Atlas
from db.schemas import Incident, LedgerEntry, Policy
from harness.compiler import CompileResult, process_incident

log = logging.getLogger("harness.incident_watcher")

LEDGER_LIMIT = 200  # matches the Compiler's replay window


class AtlasWatcherStore:
    """Everything the watcher reads and writes in Atlas."""

    def __init__(self, atlas: Atlas):
        self.atlas = atlas

    def watch_incidents(self):
        return self.atlas.security_incidents.watch(
            [{"$match": {"operationType": "insert"}}], max_await_time_ms=1000)

    def active_policies(self) -> list[Policy]:
        out = []
        for doc in self.atlas.security_policies.find({"status": "active"}):
            try:
                out.append(Policy.from_mongo(doc))
            except ValidationError:
                log.warning("skipping invalid policy %s", doc.get("policy_id"))
        return out

    def recent_ledger(self) -> list[LedgerEntry]:
        """Newest LEDGER_LIMIT rows, oldest first (the Compiler expects ts ascending)."""
        rows = self.atlas.action_ledger.find().sort("ts", DESCENDING).limit(LEDGER_LIMIT)
        out = []
        for doc in rows:
            try:
                out.append(LedgerEntry.from_mongo(doc))
            except ValidationError:
                log.warning("skipping invalid ledger row %s", doc.get("action_id"))
        return sorted(out, key=lambda e: e.ts)

    def save_policy(self, policy: Policy) -> None:
        self.atlas.security_policies.insert_one(policy.to_mongo())

    def mark_superseded(self, policy: Policy) -> None:
        self.atlas.security_policies.update_one(
            {"policy_id": policy.policy_id, "version": policy.version},
            {"$set": {"status": "superseded"}})

    def link_incident(self, incident_id: str, policy_id: str) -> None:
        self.atlas.security_incidents.update_one(
            {"incident_id": incident_id}, {"$set": {"policy_id": policy_id}})


def handle_incident(incident: Incident, store, authorized_edges=frozenset()) -> CompileResult:
    """Run the pipeline for one incident and persist the outcome."""
    res = process_incident(incident, store.active_policies(), store.recent_ledger(), authorized_edges)
    if not res.ok:
        log.info("incident %s: no policy (%s)", incident.incident_id, res.reason)
        return res
    try:
        store.save_policy(res.policy)  # new version first: the cache must never see zero active versions
    except DuplicateKeyError:
        log.info("incident %s: %s v%s already saved by another watcher", incident.incident_id,
                 res.policy.policy_id, res.policy.version)
        return res
    if res.superseded:
        store.mark_superseded(res.superseded)
    store.link_incident(incident.incident_id, res.policy.policy_id)
    log.info("incident %s: %s v%s active — %s", incident.incident_id, res.policy.policy_id,
             res.policy.version, res.reason)
    return res


def load_edges() -> frozenset[tuple[str, str]]:
    """Same source as the gateway: agents/config.py if present, else AUTHORIZED_EDGES="a>b,b>c"."""
    try:
        from agents.config import AUTHORIZED_EDGES  # type: ignore[import-not-found]
        return frozenset(AUTHORIZED_EDGES)
    except ImportError:
        raw = os.environ.get("AUTHORIZED_EDGES", "")
        return frozenset(tuple(x.strip() for x in e.split(">", 1)) for e in raw.split(",") if ">" in e)


def run(store, authorized_edges=frozenset(), stop: threading.Event | None = None,
        retry_seconds: float = 2.0) -> None:
    """Watch forever. One bad incident never stops the loop; a broken stream is reopened."""
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            with store.watch_incidents() as stream:
                log.info("watching security_incidents")
                while not stop.is_set():
                    event = stream.try_next()
                    if event is None:
                        continue
                    try:
                        handle_incident(Incident.from_mongo(event["fullDocument"]), store, authorized_edges)
                    except Exception:  # noqa: BLE001 — log and keep watching
                        log.exception("failed to process incident")
        except PyMongoError as e:
            log.warning("incident stream lost (%s); reopening", type(e).__name__)
            stop.wait(retry_seconds)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    with Atlas() as atlas:
        try:
            run(AtlasWatcherStore(atlas), load_edges())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
