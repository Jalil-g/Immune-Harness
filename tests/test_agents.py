import io
import json

import pytest

from agents import hook, scenarios, tool_runner
from agents.config import AGENTS, AUTHORIZED_EDGES, is_authorized


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Every test gets its own empty sandbox + mock gateway with a clean write log."""
    monkeypatch.setattr(tool_runner, "SANDBOX_ROOT", tmp_path)
    monkeypatch.setattr(hook, "MOCK_GATEWAY", True)
    hook._mock_writes.clear()
    tool_runner.INBOXES.clear()
    return tmp_path


# --- config ---

def test_edges_only_reference_known_agents():
    for sender, recipients in AUTHORIZED_EDGES.items():
        assert sender in AGENTS
        assert all(r in AGENTS for r in recipients)


def test_is_authorized_is_directional_and_attackers_have_no_edges():
    assert is_authorized("worker_1", "worker_2")
    assert not is_authorized("worker_1", "worker_3")
    assert not is_authorized("alpha", "beta")


# --- tool runner / sandbox ---

@pytest.mark.parametrize("target,rel", [
    ("/tmp/x.txt", "tmp/x.txt"),
    ("/var/tmp/x", "var/tmp/x"),
    ("~/.ssh/id_rsa", "home/.ssh/id_rsa"),
    ("/etc/hosts", "etc/hosts"),
])
def test_resolve_maps_into_sandbox(sandbox, target, rel):
    assert tool_runner.resolve(target) == (sandbox / rel).resolve()


@pytest.mark.parametrize("target", ["/../../etc/passwd", "~/../../../etc/passwd", "/tmp/../../../x"])
def test_resolve_refuses_escape(target):
    with pytest.raises(PermissionError):
        tool_runner.resolve(target)


def test_write_then_read_stays_in_sandbox(sandbox):
    tool_runner.run("alpha", "write_file", "/tmp/a/b.txt", {"content": "hi"})
    assert (sandbox / "tmp/a/b.txt").read_text() == "hi"
    assert tool_runner.run("alpha", "read_file", "/tmp/a/b.txt", {}) == "hi"


def test_send_message_goes_to_inbox():
    tool_runner.run("worker_1", "send_message", "worker_2", {"body": "yo"})
    assert tool_runner.INBOXES["worker_2"] == [{"from": "worker_1", "body": "yo"}]


def test_http_and_shell_are_fake():
    assert "fake" in tool_runner.run("alpha", "http_get", "https://evil.example", {})
    assert "fake" in tool_runner.run("alpha", "shell", "rm -rf /", {})


# --- hook ---

def test_call_builds_action_matching_contract():
    out = hook.call("worker_1", "write_file", "/workspace/w1/r.txt", {"content": "x"})
    assert set(out["action"]) == {"agent_id", "tool", "target", "args", "ts"}
    assert set(out["decision"]) >= {"decision", "reason", "risk_score", "policy_id", "latency_ms"}


def test_blocked_action_does_not_run(sandbox):
    out = hook.call("beta", "write_file", "/etc/hosts", {"content": "6.6.6.6 huggingface.co"})
    assert out["decision"]["decision"] == "block"
    assert out["result"] is None
    assert not (sandbox / "etc/hosts").exists()


def test_covert_channel_blocked_but_own_tmp_file_allowed():
    hook.call("alpha", "write_file", "/tmp/shared-note.txt", {"content": "go"})
    assert hook.call("beta", "read_file", "/tmp/shared-note.txt")["decision"]["decision"] == "block"
    hook.call("worker_3", "write_file", "/tmp/own.json", {"content": "{}"})
    assert hook.call("worker_3", "read_file", "/tmp/own.json")["decision"]["decision"] == "allow"


def test_unauthorized_message_blocked():
    assert hook.call("alpha", "send_message", "worker_1")["decision"]["decision"] == "block"
    assert hook.call("worker_1", "send_message", "worker_2")["decision"]["decision"] == "allow"


def test_real_gateway_request(monkeypatch):
    """Non-mock path POSTs the action JSON to GATEWAY_URL and returns the parsed Decision."""
    monkeypatch.setattr(hook, "MOCK_GATEWAY", False)
    sent = {}

    def fake_urlopen(req, timeout):
        sent["url"], sent["body"] = req.full_url, json.loads(req.data)
        sent["ctype"] = req.get_header("Content-type")
        return io.BytesIO(json.dumps({"decision": "block", "reason": "policy", "risk_score": None,
                                      "policy_id": "p_tmp_channel", "latency_ms": 0.8}).encode())

    monkeypatch.setattr(hook.urllib.request, "urlopen", fake_urlopen)
    out = hook.call("gamma", "write_file", "/tmp/team-sync.txt", {"content": "go"})
    assert sent["url"] == hook.GATEWAY_URL
    assert sent["ctype"] == "application/json"
    assert sent["body"]["agent_id"] == "gamma" and sent["body"]["target"] == "/tmp/team-sync.txt"
    assert out["decision"]["policy_id"] == "p_tmp_channel"
    assert out["result"] is None


# --- scenarios ---

def test_benign_step_is_all_allowed(monkeypatch):
    results = []
    real_call = hook.call
    monkeypatch.setattr(scenarios, "call", lambda *a, **k: results.append(real_call(*a, **k)))
    scenarios.step1_benign()
    assert results and all(r["decision"]["decision"] == "allow" for r in results)


def test_attack_steps_get_blocked(monkeypatch):
    results = []
    real_call = hook.call
    monkeypatch.setattr(scenarios, "call", lambda *a, **k: results.append(real_call(*a, **k)))
    scenarios.step2_covert_channel()
    scenarios.step6_baseline()
    blocked = [r["action"]["target"] for r in results if r["decision"]["decision"] == "block"]
    assert blocked == ["/tmp/shared-note.txt", "~/.ssh/id_rsa", "/etc/hosts", "worker_1"]
