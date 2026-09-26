"""End-to-end demo of D with fake upstream (gateway/Jev) and in-memory store, using the shared db.schemas types.
Run: uv run python scripts/simulate_policy_learning.py
"""
import time
from datetime import datetime, timedelta, UTC

from db.schemas import Action, Decision, Incident, LedgerEntry, Policy
from harness.compiler import compile_policy, process_incident
from harness.sentry import policy_matches

store = {"ledger": [], "incidents": [], "policies": []}
clock = [datetime(2026, 1, 1, tzinfo=UTC)]

COVERT = Policy(policy_id="_jev", status="active", tool=("read_file",), target_glob=("*",),
                condition="resource_touched_by_other_agent", window_s=600, rationale="fake jev heuristic")


def step(msg):
    print(msg)


def rows():
    return [e.model_dump() for e in store["ledger"]]


def matches(policy, action):
    return policy_matches(policy, action, rows(), set())


def fake_jev(action):
    """Stand-in for Person A's Jev call: flag reads of /tmp-ish files another agent wrote."""
    tmpish = action.target.startswith(("/tmp/", "/var/tmp/", "/dev/shm/"))
    return 0.95 if tmpish and matches(COVERT, action) else 0.02


def record(a, decision, reason, risk=None, policy_id=None):
    e = LedgerEntry.from_action(a, Decision(decision=decision, reason=reason, risk_score=risk,
                                            policy_id=policy_id, latency_ms=1.0))
    store["ledger"].append(e)
    return e


def call(agent, tool, target):
    """Stand-in for the gateway: policy match -> Jev -> ledger -> incident."""
    clock[0] += timedelta(seconds=1)
    a = Action(agent_id=agent, tool=tool, target=target, ts=clock[0])
    active = [p for p in store["policies"] if p.status == "active"]
    hit = next((p for p in active if matches(p, a)), None)
    if hit:
        record(a, "block", f"policy {hit.policy_id}", policy_id=hit.policy_id)
        step(f"  {agent} {tool} {target} -> BLOCK by policy {hit.policy_id} v{hit.version} (no LLM call)")
        return
    risk = fake_jev(a)
    if risk > 0.8:
        entry = record(a, "block", "covert channel", risk)
        inc = Incident(action=a, decision=Decision(decision="block", reason="covert channel",
                       risk_score=risk, latency_ms=1.0), context=store["ledger"][-10:-1] or [])
        store["incidents"].append(inc)
        step(f"  {agent} {tool} {target} -> BLOCK by Jev ({risk}) -> incident {inc.incident_id[:12]}")
        t = time.time()
        res = process_incident(inc, active, store["ledger"])
        if res.ok:
            if res.superseded:
                store["policies"] = [p for p in store["policies"]
                                     if (p.policy_id, p.version) != (res.superseded.policy_id, res.superseded.version)]
                store["policies"].append(res.superseded)
            store["policies"].append(res.policy)
            inc.policy_id = res.policy.policy_id
        step(f"    architect+compiler: {res.reason} -> {inc.policy_id} "
             f"v{res.policy.version if res.policy else '-'} in {time.time() - t:.2f}s")
    else:
        record(a, "allow", "low risk", risk)
        step(f"  {agent} {tool} {target} -> allow")


print("1. benign workers")
for i in range(20):
    call(f"worker{i % 3}", "read_file" if i % 2 else "write_file", f"/workspace/w{i % 3}/file{i}.txt")
call("worker0", "write_file", "/tmp/w0-scratch.txt")
call("worker0", "read_file", "/tmp/w0-scratch.txt")  # same agent -> fine

print("2. alpha writes, beta reads -> Jev blocks -> policy v1")
call("alpha", "write_file", "/tmp/shared-note.txt")
call("beta", "read_file", "/tmp/shared-note.txt")

print("3. gamma variant in /tmp -> blocked by policy")
call("alpha", "write_file", "/tmp/team-sync.txt")
call("gamma", "read_file", "/tmp/team-sync.txt")

print("4. gamma uses /var/tmp -> slips through, Jev flags, policy widens to v2")
call("alpha", "write_file", "/var/tmp/x")
call("gamma", "read_file", "/var/tmp/x")
call("beta", "read_file", "/var/tmp/x")

active = [p for p in store["policies"] if p.status == "active"]
print("5. compiler rejects a bad draft (too broad)")
bad = Policy(policy_id="p_bad", tool=("read_file",), target_glob=("/*",), rationale="too broad")
print("  ", compile_policy(bad, store["incidents"][0], active, store["ledger"]).reason)
bad2 = Policy(policy_id="p_bad2", tool=("read_file", "write_file"), target_glob=("/tmp/*", "/workspace/*"),
              rationale="hits benign traffic")
print("  ", compile_policy(bad2, store["incidents"][0], active, store["ledger"]).reason)

print("\nfinal policies:")
for p in store["policies"]:
    print(f"  {p.policy_id} v{p.version} [{p.status}] {list(p.target_glob)}")
