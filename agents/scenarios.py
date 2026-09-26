"""Scripted demo, driven by a JSON scenario file (agents/scenario_files/*.json). Usage:
    python3 -m agents.scenarios --all                    # default scenario, normal pace, runs by itself
    python3 -m agents.scenarios --all --pace fast        # quick run (fewer benign actions, short gaps)
    python3 -m agents.scenarios --all --pace demo        # presentation pace (pause after every action)
    python3 -m agents.scenarios --all --file agents/scenario_files/quick.json
    python3 -m agents.scenarios --list                   # show the steps of a scenario
    python3 -m agents.scenarios --step 2                 # one step
    python3 -m agents.scenarios --all --manual           # press Enter between steps
    python3 -m agents.scenarios --all --gap 1 --slow 0.5 --benign-rounds 2   # fine-tune any preset
    MOCK_GATEWAY=1 python3 -m agents.scenarios --all --no-pause
"""
import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

from agents.config import GATEWAY_URL, MOCK_GATEWAY
from agents.hook import call

SCENARIO_DIR = Path(__file__).resolve().parent / "scenario_files"
DEFAULT_FILE = SCENARIO_DIR / "default.json"

# gap = seconds between steps, slow = seconds after every action, benign_rounds = size of the benign step
PACES = {
    "fast": {"gap": 0.3, "slow": 0.0, "benign_rounds": 1},
    "normal": {"gap": 2.0, "slow": 0.0, "benign_rounds": 3},
    "demo": {"gap": 2.5, "slow": 1.2, "benign_rounds": 2},
}


def load_scenario(path=None) -> dict:
    with open(path or DEFAULT_FILE) as f:
        sc = json.load(f)
    for s in sc["steps"]:
        s["id"] = str(s["id"])
    return sc


def benign_actions(rounds: int = 3) -> list[dict]:
    """Normal worker traffic — all should be allowed; also the Compiler's false-positive replay baseline."""
    out = []
    for i in range(rounds):
        out += [
            {"agent": "worker_1", "tool": "write_file", "target": f"/workspace/worker_1/report_{i}.txt",
             "args": {"content": f"report {i}"}},
            {"agent": "worker_1", "tool": "read_file", "target": f"/workspace/worker_1/report_{i}.txt"},
            {"agent": "worker_2", "tool": "write_file", "target": f"/workspace/worker_2/notes_{i}.md",
             "args": {"content": "notes"}},
            {"agent": "worker_2", "tool": "http_get", "target": "https://pypi.org/simple/requests/"},
            {"agent": "worker_3", "tool": "shell", "target": "ls -la /workspace/worker_3"},
            {"agent": "worker_1", "tool": "send_message", "target": "worker_2", "args": {"body": f"report {i} ready"}},
            {"agent": "worker_2", "tool": "send_message", "target": "worker_3", "args": {"body": "please review"}},
        ]
    # a worker using /tmp for itself (write+read by the same agent) should stay allowed
    out += [{"agent": "worker_3", "tool": "write_file", "target": "/tmp/worker_3_cache.json", "args": {"content": "{}"}},
            {"agent": "worker_3", "tool": "read_file", "target": "/tmp/worker_3_cache.json"}]
    return out


def run_actions(actions):
    for a in actions:
        call(a["agent"], a["tool"], a["target"], a.get("args") or {})


def step_actions(step: dict, benign_rounds: int | None = None) -> list[dict]:
    if "benign_rounds" in step:
        return benign_actions(step["benign_rounds"] if benign_rounds is None else benign_rounds)
    return step.get("actions", [])


# The default scenario's steps as functions (used by the tests and handy from a REPL).
_DEFAULT = load_scenario()


def _default_step(sid):
    return next(s for s in _DEFAULT["steps"] if s["id"] == sid)


def step1_benign(rounds: int = 3):
    run_actions(benign_actions(rounds))


def step2_covert_channel():
    run_actions(_default_step("2")["actions"])


def step4_repeat():
    run_actions(_default_step("4")["actions"])


def step5_variant():
    run_actions(_default_step("5")["actions"])


def step5b_retry():
    run_actions(_default_step("5b")["actions"])


def step6_baseline():
    run_actions(_default_step("6")["actions"])


# ---------- waiting for the immune loop ----------

_atlas = None


def learned_versions():
    """(policy_id, version) of every learned policy in Atlas, or None if Atlas isn't configured."""
    global _atlas
    if not os.environ.get("MONGODB_URI"):
        from dotenv import load_dotenv
        load_dotenv()
    if not os.environ.get("MONGODB_URI"):
        return None
    try:
        if _atlas is None:
            from db.atlas import Atlas
            _atlas = Atlas()
        docs = _atlas.security_policies.find({"policy_id": {"$not": {"$regex": "^p_baseline"}}},
                                             {"_id": 0, "policy_id": 1, "version": 1})
        return {(d["policy_id"], d["version"]) for d in docs}
    except Exception:
        return None


def wait_for_policy(before, timeout=30.0, poll=0.5):
    """Block until a new policy version shows up in Atlas (or timeout). Returns it, or None."""
    print("  … waiting for the immune loop to learn a policy", flush=True)
    if before is None:
        time.sleep(5)
        print("  (no Atlas configured — waited 5s)")
        return None
    t0 = time.time()
    while time.time() - t0 < timeout:
        new = (learned_versions() or set()) - before
        if new:
            pid, v = sorted(new)[-1]
            print(f"  ✓ learned {pid} v{v} after {time.time() - t0:.1f}s", flush=True)
            return pid, v
        time.sleep(poll)
    print(f"  ! no new policy after {timeout:.0f}s — is harness.incident_watcher running?")
    return None


def gateway_up() -> bool:
    if MOCK_GATEWAY:
        return True
    try:
        urllib.request.urlopen(GATEWAY_URL.rsplit("/", 1)[0] + "/health", timeout=3)
        return True
    except Exception:
        return False


# ---------- running ----------

def run_step(step: dict, benign_rounds: int | None = None):
    print(f"\n=== Step {step['id']}: {step['title']} ===", flush=True)
    run_actions(step_actions(step, benign_rounds))


def run_all(sc: dict, gap: float, benign_rounds: int | None, manual=False, no_pause=False):
    steps = sc["steps"]
    for n, step in enumerate(steps):
        learns = step.get("learns", False)
        before = learned_versions() if learns and not (manual or no_pause) else None
        run_step(step, benign_rounds)
        if no_pause or n == len(steps) - 1:
            continue
        if manual:
            input("  [enter] next step...")
            continue
        if learns:
            wait_for_policy(before)
        time.sleep(gap)


def main():
    ap = argparse.ArgumentParser(description="Run a scripted attack scenario against the gateway.")
    ap.add_argument("--file", help="scenario JSON (default: agents/scenario_files/default.json)")
    ap.add_argument("--all", action="store_true", help="run every step")
    ap.add_argument("--step", help="run one step by id (see --list)")
    ap.add_argument("--list", action="store_true", help="list the scenario's steps")
    ap.add_argument("--pace", choices=PACES, help="speed preset: fast / normal / demo (default: normal)")
    ap.add_argument("--gap", type=float, help="seconds between steps (overrides the pace)")
    ap.add_argument("--slow", type=float, help="seconds after every action (overrides the pace)")
    ap.add_argument("--benign-rounds", type=int, help="size of the benign step, 7 actions per round (overrides the pace)")
    ap.add_argument("--manual", action="store_true", help="press Enter between steps")
    ap.add_argument("--no-pause", action="store_true", help="no waiting at all (tests / quick checks)")
    a = ap.parse_args()

    sc = load_scenario(a.file)
    pace_name = a.pace or "normal"
    pace = PACES[pace_name]
    gap = pace["gap"] if a.gap is None else a.gap
    slow = pace["slow"] if a.slow is None else a.slow
    # benign step size: --benign-rounds > an explicitly chosen --pace > the scenario file
    rounds = a.benign_rounds if a.benign_rounds is not None else (pace["benign_rounds"] if a.pace else None)

    if a.list:
        print(f"{sc.get('name', 'scenario')}  ({a.file or DEFAULT_FILE})")
        for s in sc["steps"]:
            n = len(step_actions(s, rounds))
            print(f"  {s['id']:>3}  {s['title']}  · {n} actions{'  · learns a policy' if s.get('learns') else ''}")
        return

    if slow:
        global call
        real_call = call

        def call(*args, **kwargs):
            out = real_call(*args, **kwargs)
            time.sleep(slow)
            return out

    if (a.step or a.all) and not gateway_up():
        raise SystemExit(f"Gateway not running at {GATEWAY_URL}\n"
                         "Start everything with:  ./scripts/demo.sh\n"
                         "Or just the gateway:    uv run uvicorn harness.gateway:app --port 8000\n"
                         "Or without a gateway:   MOCK_GATEWAY=1 uv run python -m agents.scenarios --all")

    if a.step:
        step = next((s for s in sc["steps"] if s["id"] == a.step), None)
        if not step:
            raise SystemExit(f"No step {a.step!r}. Steps: {', '.join(s['id'] for s in sc['steps'])}")
        run_step(step, rounds)
    elif a.all:
        br = "from file" if rounds is None else rounds
        print(f"▶ {sc.get('name', 'scenario')} · pace {pace_name} (gap {gap}s, {slow}s per action, "
              f"benign rounds: {br})", flush=True)
        t0 = time.time()
        run_all(sc, gap, rounds, manual=a.manual, no_pause=a.no_pause)
        print(f"\n✓ done in {time.time() - t0:.0f}s")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
