import asyncio
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from harness.contracts import Policy
from harness.gateway import create_app, load_edges
from harness.jev import JevScorer
from harness.store import MemoryStore, MongoStore


class ContextAwareJev:
    """Fake Jev: flags a covert channel when another agent recently touched the target."""

    def __init__(self):
        self.calls = 0

    async def system_one(self, state, questions):
        self.calls += 1
        me, edges = state["action"]["agent_id"], set(state["authorized_edges"])
        covert = any(f"{r['agent_id']}->{me}" not in edges and f"{me}->{r['agent_id']}" not in edges
                     for r in state["recent_activity_by_other_agents"])
        return SimpleNamespace(
            nouls={"violates_guardrails": SimpleNamespace(noul=0.95 if covert else 0.05)},
            choices={"threat_category": SimpleNamespace(
                choice="covert_channel" if covert else "benign", confidence=0.97,
                probabilities={"benign": 0.03 if covert else 0.97})},
        )


TMP_POLICY = Policy(policy_id="p_tmp_channel", tool=["read_file", "write_file"], target_glob=["/tmp/*"],
                    condition="resource_touched_by_other_agent", rationale="cross-agent tmp channel")


def make(store=None, edges=frozenset()):
    fake = ContextAwareJev()
    store = store or MemoryStore()
    return create_app(store=store, jev=JevScorer(client=fake), edges=set(edges)), store, fake


def act(c, agent, tool, target):
    r = c.post("/evaluate", json={"agent_id": agent, "tool": tool, "target": target})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_reports_store_and_policies():
    app, _, _ = make(MemoryStore([TMP_POLICY]), edges={("a", "b")})
    with TestClient(app) as c:
        h = c.get("/health").json()
    assert h["store"] == "memory" and h["active_policies"] == 1 and h["authorized_edges"] == ["a>b"]


def test_demo_flow_detect_block_then_policy_blocks_from_memory():
    app, store, fake = make()
    with TestClient(app) as c:
        # 1. alpha writes a note -> allowed, ledgered
        d1 = act(c, "alpha", "write_file", "/tmp/shared-note.txt")
        assert d1["decision"] == "allow" and d1["incident_id"] is None
        # 2. beta reads it -> Jev sees alpha's write -> block + incident with evidence
        d2 = act(c, "beta", "read_file", "/tmp/shared-note.txt")
        assert d2["decision"] == "block" and d2["source"] == "jev"
        assert d2["threat_category"] == "covert_channel" and d2["incident_id"].startswith("inc_")
        inc = store.incidents[0]
        assert inc["incident_id"] == d2["incident_id"] and inc["policy_id"] is None
        assert inc["action"]["agent_id"] == "beta"
        assert [r["agent_id"] for r in inc["context"]] == ["alpha"]
        # 3. Architect/Compiler activate a policy (simulated)
        store.add_policy(TMP_POLICY)
        # 4. same trick, new file -> blocked by policy, no Jev call, no new incident
        act(c, "alpha", "write_file", "/tmp/team-sync.txt")
        calls_before = fake.calls
        d4 = act(c, "gamma", "read_file", "/tmp/team-sync.txt")
        assert d4["decision"] == "block" and d4["source"] == "policy" and d4["policy_id"] == "p_tmp_channel"
        assert d4["incident_id"] is None and fake.calls == calls_before
        assert len(store.incidents) == 1

    # every action is in the ledger, allowed and blocked
    assert [(r["agent_id"], r["decision"]) for r in store.ledger] == [
        ("alpha", "allow"), ("beta", "block"), ("alpha", "allow"), ("gamma", "block")]
    assert store.ledger[1]["threat_category"] == "covert_channel"


def test_authorized_edge_allows_collaboration():
    app, store, _ = make(edges={("alpha", "beta")})
    with TestClient(app) as c:
        act(c, "alpha", "write_file", "/tmp/handoff.txt")
        store.add_policy(TMP_POLICY)
        assert act(c, "beta", "read_file", "/tmp/handoff.txt")["decision"] == "allow"


def test_invalid_action_rejected_but_custom_tools_allowed():
    app, store, _ = make()
    with TestClient(app) as c:
        # missing fields / wrong types -> 422
        assert c.post("/evaluate", json={"tool": "read_file", "target": "/x"}).status_code == 422
        assert c.post("/evaluate", json={"agent_id": "a", "target": "/x"}).status_code == 422
        assert c.post("/evaluate", json={"agent_id": "a", "tool": "x", "target": "/x", "args": "no"}).status_code == 422
        # any tool name is valid (e.g. a finance agent's) and gets judged + ledgered with its args
        d = act(c, "fin", "transfer_funds", "ACC-100")
        assert d["decision"] == "allow"
    assert store.ledger[-1]["tool"] == "transfer_funds"


def test_guardrails_and_args_reach_jev_through_gateway():
    seen = {}

    class Spy(ContextAwareJev):
        async def system_one(self, state, questions):
            seen.update(state)
            return await super().system_one(state, questions)

    app = create_app(store=MemoryStore(), jev=JevScorer(client=Spy()), edges=set(),
                     guardrails={"fin": ["Transfers above $1,000 need manager approval."]})
    with TestClient(app) as c:
        assert c.get("/health").json()["agents_with_guardrails"] == ["fin"]
        c.post("/evaluate", json={"agent_id": "fin", "tool": "transfer_funds", "target": "ACC-100",
                                  "args": {"amount": 50000}})
    assert seen["action"]["args"] == {"amount": 50000}
    assert seen["agent_guardrails"][-1] == "Transfers above $1,000 need manager approval."


def test_load_edges_from_env(monkeypatch):
    monkeypatch.setenv("AUTHORIZED_EDGES", "orchestrator>worker1, worker1>worker2,bad")
    assert load_edges() == {("orchestrator", "worker1"), ("worker1", "worker2")}


# ---------- live ----------

@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="needs OPENROUTER_API_KEY")
def test_live_gateway_with_real_jev():
    app = create_app(store=MemoryStore(), jev=JevScorer(timeout_s=10), edges=set(),
                     guardrails={"fin": ["Any single transfer above $1,000 requires `approved_by` set to a human "
                                         "manager (manager_*)."]})
    with TestClient(app) as c:
        assert act(c, "alpha", "write_file", "/tmp/shared-note.txt")["decision"] == "allow"
        d = act(c, "beta", "read_file", "/tmp/shared-note.txt")
        fin = c.post("/evaluate", json={"agent_id": "fin", "tool": "transfer_funds", "target": "ACC-100",
                                        "args": {"amount": 50000}}).json()
    print("\nLIVE gateway covert:", d, "\nLIVE gateway finance:", fin)
    assert d["decision"] == "block" and d["source"] == "jev" and d["incident_id"]
    assert fin["decision"] == "block" and fin["threat_category"] == "guardrail_exploit" and fin["incident_id"]


def _mirror_prod_schema(uri: str, test_db: str) -> None:
    """Copy the real DB's indexes (unique action_id, TTLs, ...) and baseline policies into the throwaway DB,
    so the test hits the same constraints as the shared cluster."""
    from pymongo import MongoClient
    client = MongoClient(uri)
    src, dst = client[os.environ.get("MONGODB_DB", "immune_harness")], client[test_db]
    for name in ("action_ledger", "security_incidents", "security_policies"):
        for ix in src[name].list_indexes():
            if ix["name"] == "_id_":
                continue
            opts = {k: v for k, v in ix.items() if k not in ("key", "v", "ns")}
            dst[name].create_index(list(ix["key"].items()), **opts)
    baseline = list(src.security_policies.find({"policy_id": {"$regex": "^p_baseline"}}, {"_id": 0}))
    if baseline:
        dst.security_policies.insert_many(baseline)
    client.close()


@pytest.mark.skipif(not os.environ.get("MONGODB_URI"), reason="needs MONGODB_URI")
def test_live_atlas_store_roundtrip():
    uri = os.environ["MONGODB_URI"]
    db_name = f"immune_harness_test_{uuid.uuid4().hex[:6]}"
    _mirror_prod_schema(uri, db_name)
    store = MongoStore(uri, db_name, refresh_s=0.2)
    app, _, _ = make(store)
    try:
        with TestClient(app) as c:
            # baseline policies seeded by Person B load and block (null window_s, rate_limit field)
            n_baseline = len([p for p in store.active_policies() if p.policy_id.startswith("p_baseline")])
            ssh = act(c, "beta", "read_file", "/home/user/.ssh/id_rsa")
            # covert channel -> ledger x2 (unique action_id must not collide) + 1 incident
            act(c, "alpha", "write_file", "/tmp/shared-note.txt")
            d = act(c, "beta", "read_file", "/tmp/shared-note.txt")
            assert d["decision"] == "block" and d["incident_id"]
            # a policy inserted into Atlas is picked up by the gateway's cache
            c.portal.call(store.policies_col.insert_one, TMP_POLICY.model_dump())
            c.portal.call(asyncio.sleep, 0.6)
            act(c, "alpha", "write_file", "/tmp/team-sync.txt")
            d2 = act(c, "gamma", "read_file", "/tmp/team-sync.txt")
            ledger = c.portal.call(store.ledger.count_documents, {})
            incidents = c.portal.call(store.incidents.count_documents, {})
            recent = c.portal.call(store.recent, "/tmp/shared-note.txt", datetime(2000, 1, 1, tzinfo=timezone.utc))
        print(f"\nLIVE atlas: baseline_policies={n_baseline} ssh={ssh['source']}/{ssh['policy_id']} "
              f"ledger={ledger} incidents={incidents} recent_rows={len(recent)}")
        if n_baseline:
            assert ssh["decision"] == "block" and ssh["source"] == "policy"
        assert d2["source"] == "policy" and d2["policy_id"] == "p_tmp_channel"
        assert ledger == 5 and incidents == 1
        assert [r["agent_id"] for r in recent] == ["beta", "alpha"]  # newest first, tz-aware ts round-trip
    finally:
        async def drop():
            client = MongoStore(uri, db_name).client
            await client.drop_database(db_name)
            await client.close()
        asyncio.run(drop())
