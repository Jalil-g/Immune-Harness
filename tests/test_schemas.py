from datetime import UTC, datetime, timedelta

import pytest
from bson import BSON
from bson.codec_options import CodecOptions
from pydantic import ValidationError

from db.atlas import baseline_policies
from db.schemas import Action, Decision, Incident, LedgerEntry, Policy


def make_policy(**changes):
    return Policy.model_validate(
        {
            "policy_id": "p_tmp_channel",
            "version": 2,
            "status": "active",
            "effect": "deny",
            "tool": ["read_file", "write_file"],
            "target_glob": ["/tmp/*", "/var/tmp/*"],
            "condition": "resource_touched_by_other_agent",
            "window_s": 600,
            "source_incident": "inc_42",
            "rationale": "Cross-agent channel",
            **changes,
        }
    )


def test_architecture_policy_round_trips_json_and_bson():
    policy = make_policy(expires_at=datetime.now(UTC).replace(microsecond=0))
    assert Policy.model_validate_json(policy.model_dump_json()) == policy
    decoded = BSON.encode(policy.to_mongo()).decode(codec_options=CodecOptions(tz_aware=True))
    assert isinstance(decoded["expires_at"], datetime)
    assert isinstance(decoded["tool"], list)
    assert Policy.from_mongo({"_id": "mongo-id", **decoded}) == policy


@pytest.mark.parametrize(
    "changes",
    [
        {"effect": "allow"},
        {"tool": [""]},
        {"tool": []},
        {"target_glob": []},
        {"condition": "python_eval"},
        {"version": 0},
        {"version": True},
        {"window_s": None},
        {"window_s": -1},
        {"expires_at": datetime(2026, 1, 1)},
        {"condition": "rate_exceeds"},
        {"rate_limit": 2},
        {"extra_code": "print('oops')"},
        {"condition": "unauthorized_recipient"},
    ],
)
def test_invalid_policies_rejected(changes):
    with pytest.raises(ValidationError):
        make_policy(**changes)


def test_condition_parameters_and_immutable_cache_values():
    assert make_policy(condition="rate_exceeds", rate_limit=10).rate_limit == 10
    assert make_policy(condition="unauthorized_recipient", tool=["send_message"])
    policy = make_policy()
    assert isinstance(policy.tool, tuple)
    with pytest.raises(ValidationError):
        policy.version = 3


def test_action_defaults_are_independent_and_timezone_is_utc():
    first = Action(agent_id="alpha", tool="read_file", target="/tmp/x")
    second = Action(agent_id="beta", tool="read_file", target="/tmp/x")
    first.args["x"] = 1
    assert second.args == {}
    assert first.ts.utcoffset() == timedelta(0)
    assert (
        Action(agent_id="a", tool="shell", target="ls", ts="2026-09-26T12:00:00-04:00").ts.hour
        == 16
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"risk_score": -0.1},
        {"risk_score": 1.1},
        {"risk_score": float("nan")},
        {"latency_ms": -1},
        {"latency_ms": float("inf")},
        {"decision": "maybe"},
    ],
)
def test_invalid_decisions_rejected(changes):
    with pytest.raises(ValidationError):
        Decision.model_validate({"decision": "allow", "reason": "OK", "latency_ms": 1, **changes})


def test_ledger_is_flat_and_incidents_require_block():
    action = Action(agent_id="beta", tool="read_file", target="/tmp/x")
    allow = Decision(decision="allow", reason="benign", latency_ms=1)
    block = Decision(decision="block", reason="channel", risk_score=0.95, latency_ms=20)
    row = LedgerEntry.from_action(action, block)
    assert row.to_mongo()["target"] == "/tmp/x"
    assert row.to_mongo()["decision"] == "block"
    assert row.to_mongo()["ts"] == action.ts
    incident = Incident(action=action, decision=block, context=[row])
    assert Incident.from_mongo(incident.to_mongo()) == incident
    with pytest.raises(ValidationError):
        Incident(action=action, decision=allow)


def test_baselines_cover_demo_targets_and_do_not_expire():
    from fnmatch import fnmatchcase

    policies = baseline_policies()
    for tool, target in [("read_file", "~/.ssh/id_rsa"), ("write_file", "/etc/hosts")]:
        assert any(
            tool in p.tool and any(fnmatchcase(target, g) for g in p.target_glob) for p in policies
        )
    assert all(p.expires_at is None and p.status == "active" for p in policies)
