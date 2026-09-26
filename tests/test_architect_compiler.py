from datetime import UTC, datetime, timedelta

import pytest

from db.schemas import Action, Decision, Incident, LedgerEntry, Policy
from harness.architect import PolicyDraft, _mock_draft, _to_policy, draft_policy
from harness.compiler import compile_policy, process_incident

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def t(n: int) -> datetime:
    return T0 + timedelta(seconds=n)


def entry(agent, tool, target, n, decision="allow") -> LedgerEntry:
    return LedgerEntry(agent_id=agent, tool=tool, target=target, ts=t(n), decision=decision,
                       reason="test", latency_ms=1.0)


def incident(agent, tool, target, n, context=()) -> Incident:
    return Incident(
        action=Action(agent_id=agent, tool=tool, target=target, ts=t(n)),
        decision=Decision(decision="block", reason="covert channel", risk_score=0.95, latency_ms=1.0),
        context=list(context),
    )


def channel_policy(globs=("/tmp/*",), version=1, status="active", tools=("read_file", "write_file")) -> Policy:
    return Policy(policy_id="p_tmp_channel", version=version, status=status, tool=tools,
                  target_glob=globs, condition="resource_touched_by_other_agent", window_s=600,
                  rationale="Cross-agent covert channel via shared temp files")


def benign(n=20) -> list[LedgerEntry]:
    return [entry(f"worker{i % 3}", "write_file", f"/workspace/w{i % 3}/f{i}.txt", i) for i in range(n)]


@pytest.fixture(autouse=True)
def mock_architect(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# --- Architect ---

def test_mock_draft_generalizes_file_to_directory():
    inc = incident("beta", "read_file", "/tmp/shared-note.txt", 10)
    p = draft_policy(inc, [], [])
    assert p.policy_id == "p_tmp_channel"
    assert p.target_glob == ("/tmp/*",)
    assert p.condition == "resource_touched_by_other_agent"
    assert p.status == "draft" and p.source_incident == inc.incident_id


def test_mock_draft_widens_existing_policy():
    inc = incident("gamma", "read_file", "/var/tmp/x", 10)
    p = _mock_draft(inc, [channel_policy()])
    assert p.policy_id == "p_tmp_channel"
    assert p.target_glob == ("/tmp/*", "/var/tmp/*")
    assert "widened" in p.rationale


def test_llm_draft_is_normalized():
    inc = incident("beta", "read_file", "/tmp/a.txt", 10)
    d = PolicyDraft(policy_id="p_x", tool=["read_file"], target_glob=["/tmp/a.txt"],
                    condition="resource_touched_by_other_agent", window_s=5, rationale="")
    p = _to_policy(d, inc)
    assert p.target_glob == ("/tmp/*",)  # exact file -> directory
    assert p.window_s == 600             # tiny window raised
    assert p.rationale                   # never empty


def test_always_policy_has_no_window():
    d = PolicyDraft(policy_id="p_ssh", tool=["read_file"], target_glob=["~/.ssh/*"],
                    condition="always", rationale="no one touches ssh keys")
    assert _to_policy(d, incident("a", "read_file", "~/.ssh/id_rsa", 1)).window_s is None


# --- Compiler ---

def test_first_version_is_activated():
    ledger = [*benign(), entry("alpha", "write_file", "/tmp/shared-note.txt", 30)]
    inc = incident("beta", "read_file", "/tmp/shared-note.txt", 31)
    res = process_incident(inc, [], ledger)
    assert res.ok and res.superseded is None
    assert res.policy.version == 1 and res.policy.status == "active"
    assert "FP 0%" in res.reason


def test_variant_widens_to_v2_and_supersedes_v1():
    v1 = channel_policy()
    ledger = [*benign(), entry("alpha", "write_file", "/var/tmp/x", 30)]
    res = process_incident(incident("gamma", "read_file", "/var/tmp/x", 31), [v1], ledger)
    assert res.ok
    assert res.policy.version == 2 and res.policy.status == "active"
    assert res.policy.target_glob == ("/tmp/*", "/var/tmp/*")
    assert (res.superseded.policy_id, res.superseded.version, res.superseded.status) == \
        ("p_tmp_channel", 1, "superseded")


def test_new_version_keeps_everything_old_one_covered():
    v1 = channel_policy(globs=("/tmp/*", "/dev/shm/*"))
    draft = channel_policy(globs=("/var/tmp/*",), tools=("read_file",))
    ledger = [entry("alpha", "write_file", "/var/tmp/x", 30)]
    res = compile_policy(draft, incident("gamma", "read_file", "/var/tmp/x", 31), [v1], ledger)
    assert set(res.policy.target_glob) == {"/tmp/*", "/dev/shm/*", "/var/tmp/*"}
    assert set(res.policy.tool) == {"read_file", "write_file"}


@pytest.mark.parametrize("glob", ["*", "/*", "**"])
def test_too_broad_is_rejected(glob):
    draft = Policy(policy_id="p_bad", tool=("read_file",), target_glob=(glob,), rationale="too broad")
    res = compile_policy(draft, incident("a", "read_file", "/tmp/x", 5), [], [])
    assert not res.ok and res.reason == "scope too broad" and res.policy is None


def test_policy_that_misses_the_trigger_is_rejected():
    draft = channel_policy(globs=("/workspace/*",))
    ledger = [entry("alpha", "write_file", "/tmp/x", 30)]
    res = compile_policy(draft, incident("beta", "read_file", "/tmp/x", 31), [], ledger)
    assert not res.ok and "would not have blocked" in res.reason


def test_high_false_positive_rate_is_rejected():
    draft = Policy(policy_id="p_bad2", tool=("read_file", "write_file"),
                   target_glob=("/tmp/*", "/workspace/*"), rationale="hits benign traffic")
    ledger = [*benign(), entry("alpha", "write_file", "/tmp/x", 30)]
    res = compile_policy(draft, incident("beta", "read_file", "/tmp/x", 31), [], ledger)
    assert not res.ok and "false positive rate" in res.reason


def test_authorized_edge_is_exempt_only_when_passed():
    ledger = [entry("alpha", "write_file", "/tmp/x", 30)]
    inc = incident("beta", "read_file", "/tmp/x", 31)
    assert compile_policy(channel_policy(), inc, [], ledger).ok
    res = compile_policy(channel_policy(), inc, [], ledger, authorized_edges={("alpha", "beta")})
    assert not res.ok and "would not have blocked" in res.reason


def test_replay_only_uses_earlier_rows():
    # beta read (t=1) happened BEFORE alpha's write (t=2): it must not count as a hit on the policy.
    ledger = [entry("beta", "read_file", "/tmp/x", 1), entry("alpha", "write_file", "/tmp/x", 2)]
    draft = channel_policy(tools=("read_file",))
    res = compile_policy(draft, incident("gamma", "read_file", "/tmp/x", 3), [], ledger)
    assert res.ok and "FP 0%" in res.reason


def test_incident_context_is_used_as_history():
    ctx = [entry("alpha", "write_file", "/tmp/x", 30)]
    res = compile_policy(channel_policy(), incident("beta", "read_file", "/tmp/x", 31, ctx), [], [])
    assert res.ok


def test_blocked_rows_do_not_count_as_touching_the_resource():
    ledger = [entry("alpha", "write_file", "/tmp/x", 30, decision="block")]
    res = compile_policy(channel_policy(), incident("beta", "read_file", "/tmp/x", 31), [], ledger)
    assert not res.ok and "would not have blocked" in res.reason
