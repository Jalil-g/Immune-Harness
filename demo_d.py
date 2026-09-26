"""End-to-end demo of D with fake upstream (gateway/Jev) and in-memory store.
Run: .venv/bin/python demo_d.py
"""
import time
from harness.architect import Policy
from harness.compiler import matches, compile_policy, process_incident

store = {"ledger": [], "incidents": [], "policies": []}
clock = [1000.0]


def step(msg):
    print(msg)


def fake_jev(action):
    """Stand-in for Person A's Jev call: flag reads of /tmp-ish files another agent wrote."""
    tmpish = action["target"].startswith(("/tmp/", "/var/tmp/", "/dev/shm/"))
    if action["tool"] == "read_file" and tmpish and matches(
        {"tool": ["read_file"], "target_glob": ["*"], "condition": "resource_touched_by_other_agent", "window_s": 600},
        action, store["ledger"],
    ):
        return 0.95
    return 0.02


def call(agent, tool, target):
    """Stand-in for the gateway: policy match -> Jev -> ledger -> incident."""
    clock[0] += 1
    a = {"agent_id": agent, "tool": tool, "target": target, "ts": clock[0]}
    active = [p for p in store["policies"] if p["status"] == "active"]
    hit = next((p for p in active if matches(p, a, store["ledger"])), None)
    if hit:
        store["ledger"].append({**a, "decision": "block", "by": f'policy {hit["policy_id"]} v{hit["version"]}'})
        step(f"  {agent} {tool} {target} -> BLOCK by policy {hit['policy_id']} v{hit['version']} (no LLM call)")
        return
    risk = fake_jev(a)
    if risk > 0.8:
        store["ledger"].append({**a, "decision": "block", "by": f"jev {risk}"})
        inc = {"incident_id": f"inc_{len(store['incidents']) + 1}", "action": a, "risk": risk,
               "threat_category": "covert_channel", "policy_id": None, "compiler": None}
        store["incidents"].append(inc)
        step(f"  {agent} {tool} {target} -> BLOCK by Jev ({risk}) -> incident {inc['incident_id']}")
        t = time.time()
        process_incident(inc, store)
        step(f"    architect+compiler: {inc['compiler']} -> {inc['policy_id']} in {time.time() - t:.2f}s")
    else:
        store["ledger"].append({**a, "decision": "allow", "by": f"jev {risk}"})
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

print("5. compiler rejects a bad draft (too broad)")
bad = Policy(policy_id="p_bad", tool=["read_file"], target_glob=["/*"], condition="always")
print("  ", compile_policy(bad, store["incidents"][0], store)[:2])
bad2 = Policy(policy_id="p_bad2", tool=["read_file", "write_file"], target_glob=["/tmp/*", "/workspace/*"], condition="always")
print("  ", compile_policy(bad2, store["incidents"][0], store)[:2])

print("\nfinal policies:")
for p in store["policies"]:
    print(f"  {p['policy_id']} v{p['version']} [{p['status']}] {p['target_glob']}")
