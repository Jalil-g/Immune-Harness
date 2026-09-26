"""Opt-in real Atlas/replica-set test; only touches its own random database."""

import os
import time
from uuid import uuid4

import pytest

from db.atlas import Atlas, AtlasSettings, baseline_policies
from db.schemas import Action, Decision, Incident, LedgerEntry, Policy
from harness.policy_cache import PolicyCache

pytestmark = pytest.mark.integration


def wait_for(cache, predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if cache.healthy and predicate(cache.get_policies()):
            return
        time.sleep(0.05)
    raise AssertionError("Change stream did not deliver the expected policy state")


def test_real_bootstrap_bson_and_change_stream():
    uri = os.environ.get("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("Set MONGODB_TEST_URI to run against Atlas or a replica set")
    settings = AtlasSettings(uri=uri, database=f"immune_test_{uuid4().hex}")
    with Atlas(settings) as atlas:
        try:
            assert atlas.bootstrap() == 2
            assert atlas.bootstrap() == 0
            assert (
                atlas.security_policies.index_information()["policy_expiry"]["expireAfterSeconds"]
                == 0
            )
            action = Action(agent_id="beta", tool="read_file", target="/tmp/shared-note.txt")
            decision = Decision(decision="block", reason="channel", risk_score=0.95, latency_ms=1)
            row = LedgerEntry.from_action(action, decision)
            atlas.action_ledger.insert_one(row.to_mongo())
            stored = atlas.action_ledger.find_one({"target": action.target})
            assert LedgerEntry.from_mongo(stored).ts.tzinfo is not None
            incident = Incident(action=action, decision=decision, context=[row])
            atlas.security_incidents.insert_one(incident.to_mongo())
            with PolicyCache(atlas.security_policies) as cache:
                assert len(cache.get_policies()) == 2
                policy = Policy(
                    policy_id="p_tmp_channel",
                    status="active",
                    tool=["read_file"],
                    target_glob=["/tmp/*"],
                    rationale="test",
                    source_incident=incident.incident_id,
                )
                atlas.security_policies.insert_one(policy.to_mongo())
                wait_for(cache, lambda policies: len(policies) == 3)
                v2 = policy.model_copy(update={"version": 2, "target_glob": ("/var/tmp/*",)})
                with atlas.client.start_session() as session, session.start_transaction():
                    atlas.security_policies.update_one(
                        {"policy_id": policy.policy_id, "version": 1},
                        {"$set": {"status": "superseded"}},
                        session=session,
                    )
                    atlas.security_policies.insert_one(v2.to_mongo(), session=session)
                wait_for(cache, lambda policies: any(p.version == 2 for p in policies))
                atlas.security_policies.delete_one({"policy_id": policy.policy_id, "version": 2})
                wait_for(cache, lambda policies: len(policies) == len(baseline_policies()))
        finally:
            atlas.client.drop_database(settings.database)
