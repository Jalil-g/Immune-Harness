"""Live end-to-end: my agents -> real running gateway (Person A) -> Jev or fallback.

Skipped unless a gateway answers at GATEWAY_URL. Easiest way: ./run_demo.sh test
"""
import json
import os
import urllib.request
import uuid

import pytest

from agents import hook, scenarios, tool_runner

HEALTH_URL = hook.GATEWAY_URL.rsplit("/", 1)[0] + "/health"


def _health():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


HEALTH = _health()
pytestmark = pytest.mark.skipif(HEALTH is None, reason=f"no gateway at {HEALTH_URL}")


@pytest.fixture(autouse=True)
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(tool_runner, "SANDBOX_ROOT", tmp_path)
    monkeypatch.setattr(hook, "MOCK_GATEWAY", False)


RUN_ID = uuid.uuid4().hex[:6]


def uniq(target):
    """Fresh file names per run — the gateway (and Atlas) remember earlier runs' file access."""
    if target.startswith(("/tmp/", "/var/tmp/", "/workspace/")):
        root, ext = os.path.splitext(target)
        return f"{root}-{RUN_ID}{ext}"
    return target


def run(step, monkeypatch):
    out = []

    def call(agent_id, tool, target, args=None):
        r = hook.call(agent_id, tool, uniq(target), args)
        out.append((agent_id, target, r["decision"]["decision"]))

    monkeypatch.setattr(scenarios, "call", call)
    step()
    return out


def test_gateway_knows_my_edges():
    print(f"\ngateway: {HEALTH}")
    assert "worker_1>worker_2" in HEALTH["authorized_edges"]


def test_step1_benign_all_allowed(monkeypatch):
    out = run(scenarios.step1_benign, monkeypatch)
    blocked = [o for o in out if o[2] == "block"]
    assert not blocked, f"false positives: {blocked}"


def test_step2_covert_channel_blocked(monkeypatch):
    out = run(scenarios.step2_covert_channel, monkeypatch)
    assert out == [("alpha", "/tmp/shared-note.txt", "allow"), ("beta", "/tmp/shared-note.txt", "block")]


def test_step5_variant_blocked(monkeypatch):
    out = run(scenarios.step5_variant, monkeypatch)
    assert out[-1] == ("gamma", "/var/tmp/x", "block")


def test_step6_baseline_all_blocked(monkeypatch):
    out = run(scenarios.step6_baseline, monkeypatch)
    assert [o[2] for o in out] == ["block"] * 3, out
