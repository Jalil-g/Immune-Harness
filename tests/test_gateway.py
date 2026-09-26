import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from db.atlas import AtlasSettings, baseline_policies
from db.schemas import Incident, LedgerEntry
from harness.contracts import Policy
from harness.gateway import create_app, load_edges
from harness.jev import JevScorer
from harness.policy_cache import PolicyCacheUnavailable
from harness.store import AtlasStore, MemoryStore


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


TMP_POLICY = Policy(policy_id="p_tmp_channel", status="active", tool=["read_file", "write_file"],
                    target_glob=["/tmp/*"], condition="resource_touched_by_other_agent", window_s=600,
                    rationale="cross-agent tmp channel")


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
    assert "covert_channel" in store.ledger[1]["reason"]
    # every document validates against Person B's schemas (what D's Architect/Compiler/dashboard read)
    for r in store.ledger:
        LedgerEntry.from_mongo(r)
    assert Incident.from_mongo(store.incidents[0]).context[0].agent_id == "alpha"


def test_baseline_policies_block_via_policy_fast_path():
    app, store, fake = make(MemoryStore(list(baseline_policies())))
    with TestClient(app) as c:
        ssh = act(c, "beta", "read_file", "/home/user/.ssh/id_rsa")
        etc = act(c, "beta", "write_file", "/etc/hosts")
    assert (ssh["decision"], ssh["source"], ssh["policy_id"]) == ("block", "policy", "p_baseline_ssh")
    assert (etc["decision"], etc["policy_id"]) == ("block", "p_baseline_etc")
    assert fake.calls == 0 and store.incidents == []  # known attacks don't re-trigger the Architect


def test_incidents_only_for_jev_blocks():
    """Jev (or its fallback) block -> incident; policy block and allow -> ledger only."""
    class DownJev:
        async def system_one(self, state, questions):
            raise RuntimeError("jev down")

    ssh = next(p for p in baseline_policies() if p.policy_id == "p_baseline_ssh")
    store = MemoryStore([ssh])
    app = create_app(store=store, jev=JevScorer(client=DownJev()), edges=set())
    with TestClient(app) as c:
        policy = act(c, "a", "read_file", "/root/.ssh/id_rsa")
        allowed = act(c, "a", "http_get", "https://en.wikipedia.org")
        fallback = act(c, "a", "read_file", "/tmp/a/../../etc/shadow")  # heuristic: path traversal
    assert policy["source"] == "policy" and policy["incident_id"] is None
    assert allowed["decision"] == "allow" and allowed["incident_id"] is None
    assert fallback["decision"] == "block" and fallback["source"] == "fallback" and fallback["incident_id"]
    assert [i["incident_id"] for i in store.incidents] == [fallback["incident_id"]]
    assert len(store.ledger) == 3


def test_policy_cache_unavailable_fails_closed_with_503():
    class DownStore(MemoryStore):
        healthy = False

        def active_policies(self):
            raise PolicyCacheUnavailable("down")

    app, store, _ = make(DownStore())
    with TestClient(app) as c:
        r = c.post("/evaluate", json={"agent_id": "a", "tool": "read_file", "target": "/tmp/x"})
        h = c.get("/health").json()
    assert r.status_code == 503 and store.ledger == []
    assert h["policy_cache_healthy"] is False and h["active_policies"] is None


def test_ledger_write_failure_fails_closed_with_503():
    from pymongo.errors import AutoReconnect

    class BrokenStore(MemoryStore):
        async def log_action(self, action, decision):
            raise AutoReconnect("atlas down")

    app, _, _ = make(BrokenStore())
    with TestClient(app) as c:
        r = c.post("/evaluate", json={"agent_id": "a", "tool": "read_file", "target": "/tmp/x"})
    assert r.status_code == 503


def test_authorized_edge_allows_collaboration():
    app, store, _ = make(edges={("alpha", "beta")})
    with TestClient(app) as c:
        act(c, "alpha", "write_file", "/tmp/handoff.txt")
        store.add_policy(TMP_POLICY)
        assert act(c, "beta", "read_file", "/tmp/handoff.txt")["decision"] == "allow"


def test_invalid_action_rejected_but_custom_tools_allowed():
    app, store, _ = make()
    with TestClient(app) as c:
        # missing fields / wrong types / empty tool / naive ts / extra field -> 422
        bad = [{"tool": "read_file", "target": "/x"},
               {"agent_id": "a", "target": "/x"},
               {"agent_id": "a", "tool": "read_file", "target": "/x", "args": "no"},
               {"agent_id": "a", "tool": "", "target": "/x"},
               {"agent_id": "a", "tool": "read_file", "target": "/x", "ts": "2026-09-26T12:00:00"},
               {"agent_id": "a", "tool": "read_file", "target": "/x", "extra": 1}]
        for body in bad:
            assert c.post("/evaluate", json=body).status_code == 422, body
        assert store.ledger == []
        # any tool name is valid (e.g. a finance agent's), judged by Jev and ledgered with its args
        assert act(c, "fin", "transfer_funds", "ACC-100")["decision"] == "allow"
    assert LedgerEntry.from_mongo(store.ledger[-1]).tool == "transfer_funds"


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
    monkeypatch.setitem(sys.modules, "agents.config", None)  # env fallback only applies without agents/config.py
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


@pytest.mark.skipif(not os.environ.get("MONGODB_URI"), reason="needs MONGODB_URI")
def test_live_atlas_store_roundtrip():
    """Real Atlas, throwaway DB set up by Person B's bootstrap (same indexes + baseline policies as prod)."""
    settings = AtlasSettings(uri=os.environ["MONGODB_URI"],
                             database=f"immune_harness_test_{uuid.uuid4().hex[:6]}")
    store = AtlasStore(settings)
    store.atlas.bootstrap()
    app, _, _ = make(store)
    try:
        with TestClient(app) as c:
            assert c.get("/health").json()["policy_cache_healthy"] is True
            ssh = act(c, "beta", "read_file", "/home/user/.ssh/id_rsa")
            # covert channel -> ledger x2 (unique action_id must not collide) + 1 incident
            act(c, "alpha", "write_file", "/tmp/shared-note.txt")
            d = act(c, "beta", "read_file", "/tmp/shared-note.txt")
            assert d["decision"] == "block" and d["incident_id"]
            # a policy inserted into Atlas reaches the gateway via B's change-stream cache, no restart
            store.atlas.security_policies.insert_one(TMP_POLICY.to_mongo())
            for _ in range(50):
                if any(p.policy_id == "p_tmp_channel" for p in store.active_policies()):
                    break
                c.portal.call(asyncio.sleep, 0.1)
            act(c, "alpha", "write_file", "/tmp/team-sync.txt")
            d2 = act(c, "gamma", "read_file", "/tmp/team-sync.txt")
            recent = c.portal.call(store.recent, "/tmp/shared-note.txt", datetime(2000, 1, 1, tzinfo=UTC))
            ledger = list(store.atlas.action_ledger.find())
            incidents = list(store.atlas.security_incidents.find())
        print(f"\nLIVE atlas: ssh={ssh['source']}/{ssh['policy_id']} ledger={len(ledger)} "
              f"incidents={len(incidents)} recent_rows={len(recent)}")
        assert ssh["decision"] == "block" and ssh["policy_id"] == "p_baseline_ssh"
        assert d2["source"] == "policy" and d2["policy_id"] == "p_tmp_channel"
        assert len(ledger) == 5 and len(incidents) == 1
        for r in ledger:
            LedgerEntry.from_mongo(r)
        assert Incident.from_mongo(incidents[0]).incident_id == d["incident_id"]
        assert [r["agent_id"] for r in recent] == ["beta", "alpha"]  # newest first, tz-aware ts round-trip
    finally:
        from pymongo import MongoClient
        with MongoClient(settings.uri) as client:
            client.drop_database(settings.database)
