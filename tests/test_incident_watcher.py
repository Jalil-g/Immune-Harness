from datetime import UTC, datetime, timedelta

import pytest
from pymongo.errors import DuplicateKeyError

from db.schemas import Action, Decision, Incident, LedgerEntry
from harness.incident_watcher import handle_incident

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def t(n):
    return T0 + timedelta(seconds=n)


def entry(agent, tool, target, n):
    return LedgerEntry(agent_id=agent, tool=tool, target=target, ts=t(n), decision="allow",
                       reason="test", latency_ms=1.0)


def incident(agent, tool, target, n):
    return Incident(
        action=Action(agent_id=agent, tool=tool, target=target, ts=t(n)),
        decision=Decision(decision="block", reason="covert channel", risk_score=0.95, latency_ms=1.0))


class FakeStore:
    """In-memory stand-in for AtlasWatcherStore, including the unique (policy_id, version) index."""

    def __init__(self, policies=(), ledger=()):
        self.policies = list(policies)
        self.ledger = list(ledger)
        self.links = {}

    def active_policies(self):
        return [p for p in self.policies if p.status == "active"]

    def recent_ledger(self):
        return sorted(self.ledger, key=lambda e: e.ts)

    def save_policy(self, policy):
        if any((p.policy_id, p.version) == (policy.policy_id, policy.version) for p in self.policies):
            raise DuplicateKeyError("duplicate")
        self.policies.append(policy)

    def mark_superseded(self, policy):
        self.policies = [p.model_copy(update={"status": "superseded"})
                         if (p.policy_id, p.version) == (policy.policy_id, policy.version) else p
                         for p in self.policies]

    def link_incident(self, incident_id, policy_id):
        self.links[incident_id] = policy_id


@pytest.fixture(autouse=True)
def mock_architect(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def benign():
    return [entry(f"worker{i % 3}", "write_file", f"/workspace/w{i % 3}/f{i}.txt", i) for i in range(20)]


def test_new_attack_saves_v1_and_links_incident():
    store = FakeStore(ledger=[*benign(), entry("alpha", "write_file", "/tmp/x", 30)])
    inc = incident("beta", "read_file", "/tmp/x", 31)
    res = handle_incident(inc, store)
    assert res.ok
    assert [(p.policy_id, p.version, p.status) for p in store.policies] == [("p_tmp_channel", 1, "active")]
    assert store.links == {inc.incident_id: "p_tmp_channel"}


def test_variant_saves_v2_and_supersedes_v1():
    store = FakeStore(ledger=[*benign(), entry("alpha", "write_file", "/tmp/x", 30)])
    handle_incident(incident("beta", "read_file", "/tmp/x", 31), store)
    store.ledger.append(entry("alpha", "write_file", "/var/tmp/y", 40))
    handle_incident(incident("gamma", "read_file", "/var/tmp/y", 41), store)
    state = {(p.version, p.status): p.target_glob for p in store.policies}
    assert state == {(1, "superseded"): ("/tmp/*",), (2, "active"): ("/tmp/*", "/var/tmp/*")}


def test_rejected_draft_saves_nothing():
    # the trigger was never written by another agent, so the policy would not have blocked it
    store = FakeStore(ledger=benign())
    inc = incident("beta", "read_file", "/tmp/x", 31)
    res = handle_incident(inc, store)
    assert not res.ok
    assert store.policies == [] and store.links == {}


def test_authorized_edge_is_passed_to_the_compiler():
    store = FakeStore(ledger=[entry("alpha", "write_file", "/tmp/x", 30)])
    res = handle_incident(incident("beta", "read_file", "/tmp/x", 31), store,
                          authorized_edges=frozenset({("alpha", "beta")}))
    assert not res.ok and store.policies == []


def test_duplicate_version_from_another_watcher_is_skipped():
    store = FakeStore(ledger=[entry("alpha", "write_file", "/tmp/x", 30)])

    def already_saved(policy):
        raise DuplicateKeyError("another watcher saved this version first")

    store.save_policy = already_saved
    res = handle_incident(incident("beta", "read_file", "/tmp/x", 31), store)
    assert res.ok
    assert store.policies == [] and store.links == {}  # no crash, no supersede, no link


class FakeStream:
    def __init__(self, events, stop):
        self.events, self.stop = list(events), stop

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def try_next(self):
        if self.events:
            return self.events.pop(0)
        self.stop.set()
        return None


def test_run_processes_stream_events_and_survives_a_bad_one():
    import threading

    from harness.incident_watcher import run

    stop = threading.Event()
    store = FakeStore(ledger=[entry("alpha", "write_file", "/tmp/x", 30)])
    inc = incident("beta", "read_file", "/tmp/x", 31)
    events = [{"fullDocument": {"garbage": True}}, {"fullDocument": inc.to_mongo()}]
    store.watch_incidents = lambda: FakeStream(events, stop)
    run(store, stop=stop)
    assert store.links == {inc.incident_id: "p_tmp_channel"}
