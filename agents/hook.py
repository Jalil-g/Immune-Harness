"""harness.call(): ask the gateway, then run the tool if allowed."""
import fnmatch
import json
import time
import urllib.request
from datetime import datetime, timezone

from agents import tool_runner
from agents.config import GATEWAY_URL, MOCK_GATEWAY, is_authorized

# Action/Decision are plain dicts matching db/schemas.py (Person B) so we don't depend on it yet


def _mock_evaluate(action: dict) -> dict:
    """Crude local stand-in for the gateway. Only for dev before /evaluate exists."""
    start = time.perf_counter()
    tool, target, agent = action["tool"], action["target"], action["agent_id"]

    def decide(decision, reason, score=None, policy_id=None):
        return {"decision": decision, "reason": reason, "risk_score": score,
                "policy_id": policy_id, "latency_ms": (time.perf_counter() - start) * 1000}

    if fnmatch.fnmatch(target, "~/.ssh/*") or fnmatch.fnmatch(target, "/etc/*"):
        return decide("block", "baseline policy", policy_id="p_baseline")
    if tool == "send_message" and not is_authorized(agent, target):
        return decide("block", "unauthorized recipient", 0.9)
    if tool in ("read_file", "write_file") and any(
        fnmatch.fnmatch(target, g) for g in ("/tmp/*", "/var/tmp/*", "/dev/shm/*")
    ):
        others = [a for a, t in _mock_writes.get(target, []) if a != agent and time.time() - t < 600]
        if tool == "read_file" and others:
            return decide("block", f"reads file written by {others[-1]} (covert channel)", 0.95)
    return decide("allow", "mock allow", 0.1)


_mock_writes: dict[str, list[tuple[str, float]]] = {}


def evaluate(action: dict) -> dict:
    if MOCK_GATEWAY:
        return _mock_evaluate(action)
    req = urllib.request.Request(
        GATEWAY_URL,
        data=json.dumps(action).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def call(agent_id: str, tool: str, target: str, args: dict | None = None) -> dict:
    action = {
        "agent_id": agent_id,
        "tool": tool,
        "target": target,
        "args": args or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    decision = evaluate(action)

    result = None
    if decision["decision"] == "allow":
        try:
            result = tool_runner.run(agent_id, tool, target, action["args"])
        except Exception as e:
            result = f"tool error: {e}"
        if MOCK_GATEWAY and tool == "write_file":
            _mock_writes.setdefault(target, []).append((agent_id, time.time()))

    _log(action, decision)
    return {"action": action, "decision": decision, "result": result}


def _log(action: dict, decision: dict):
    icon = "✓" if decision["decision"] == "allow" else "✗"
    score = decision.get("risk_score")
    score_s = f" risk={score:.2f}" if score is not None else ""
    pol = f" policy={decision['policy_id']}" if decision.get("policy_id") else ""
    print(f"  {icon} {action['agent_id']:>9} {action['tool']:<12} {action['target']:<28}"
          f" {decision['decision'].upper()}{score_s}{pol} ({decision['latency_ms']:.1f}ms) — {decision['reason']}")
