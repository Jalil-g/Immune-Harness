"""Opt-in real Atlas test of the incident watcher; only touches its own random database.

Run: MONGODB_TEST_URI=<atlas uri> uv run pytest tests/test_incident_watcher_integration.py -q
"""

import os
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from db.atlas import Atlas, AtlasSettings
from db.schemas import Action, Decision, Incident, LedgerEntry
from harness.incident_watcher import AtlasWatcherStore, run
from harness.policy_cache import PolicyCache

pytestmark = pytest.mark.integration


def wait_for(predicate, what, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for: {what}")


def ledger_row(agent, tool, target, seconds_ago):
    return LedgerEntry(
        agent_id=agent, tool=tool, target=target, ts=datetime.now(UTC) - timedelta(seconds=seconds_ago),
        decision="allow", reason="test", latency_ms=1.0,
    ).to_mongo()


def incident(agent, target):
    return Incident(
        action=Action(agent_id=agent, tool="read_file", target=target),
        decision=Decision(decision="block", reason="covert channel", risk_score=0.95, latency_ms=1.0),
    )


def test_watcher_learns_v1_then_widens_to_v2(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)  # deterministic mock Architect
    uri = os.environ.get("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("Set MONGODB_TEST_URI to run against Atlas or a replica set")
    settings = AtlasSettings(uri=uri, database=f"immune_test_{uuid4().hex}")
    stop = threading.Event()
    with Atlas(settings) as atlas:
        try:
            atlas.bootstrap()
            policies = atlas.security_policies
            thread = threading.Thread(
                target=run, args=(AtlasWatcherStore(atlas),), kwargs={"stop": stop}, daemon=True)
            thread.start()
            time.sleep(3)  # let the change stream open before inserting

            # New attack: alpha wrote a /tmp file, beta read it.
            atlas.action_ledger.insert_many(
                [ledger_row(f"worker{i % 3}", "write_file", f"/workspace/w{i % 3}/f{i}.txt", 60 - i)
                 for i in range(20)])
            atlas.action_ledger.insert_one(ledger_row("alpha", "write_file", "/tmp/shared-note.txt", 5))
            first = incident("beta", "/tmp/shared-note.txt")
            atlas.security_incidents.insert_one(first.to_mongo())

            wait_for(lambda: policies.count_documents(
                {"policy_id": "p_tmp_channel", "version": 1, "status": "active"}) == 1, "v1 active")
            wait_for(lambda: atlas.security_incidents.find_one(
                {"incident_id": first.incident_id})["policy_id"] == "p_tmp_channel", "incident linked")

            # Variant in another directory: the policy widens.
            atlas.action_ledger.insert_one(ledger_row("alpha", "write_file", "/var/tmp/x", 5))
            atlas.security_incidents.insert_one(incident("gamma", "/var/tmp/x").to_mongo())

            wait_for(lambda: policies.count_documents(
                {"policy_id": "p_tmp_channel", "version": 2, "status": "active"}) == 1, "v2 active")
            wait_for(lambda: policies.find_one(
                {"policy_id": "p_tmp_channel", "version": 1})["status"] == "superseded", "v1 superseded")
            v2 = policies.find_one({"policy_id": "p_tmp_channel", "version": 2})
            assert set(v2["target_glob"]) == {"/tmp/*", "/var/tmp/*"}

            # Only the newest active version reaches the gateway's cache.
            with PolicyCache(policies) as cache:
                learned = [p for p in cache.get_policies() if p.policy_id == "p_tmp_channel"]
                assert [p.version for p in learned] == [2]
        finally:
            stop.set()
            atlas.client.drop_database(settings.database)
