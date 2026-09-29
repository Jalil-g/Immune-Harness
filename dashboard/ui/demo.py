"""Sample data for the dashboard when Atlas isn't reachable (or DASHBOARD_DEMO=1).

Same shapes as ui.data.load(): the whole story in one ledger, so every view has something real to draw:
benign traffic, Jev catching a covert /tmp channel, the policy it wrote, a /var/tmp variant, the policy
widened to v2, and memory blocking the repeats. Times are fixed at process start, so ages advance naturally.
"""
from datetime import UTC, datetime, timedelta

T0 = datetime.now(UTC)


def _t(s: float) -> datetime:
    return T0 - timedelta(seconds=s)


def _jev(risk, cat, conf=0.93):
    return f"jev risk={risk:.2f} category={cat} ({conf:.2f})"


def _row(ago, agent, tool, target, decision, lat, *, reason, risk=None, policy_id=None, args=None):
    r = dict(ts=_t(ago), agent_id=agent, tool=tool, target=target, args=args or {}, decision=decision,
             reason=reason, latency_ms=lat)
    if risk is not None:
        r["risk_score"] = risk
    if policy_id:
        r["policy_id"] = policy_id
    return r


def _policy(pid, ver, status, tool, globs, rationale, created, *, condition="always", src=None):
    d = dict(policy_id=pid, version=ver, status=status, effect="deny", tool=list(tool), target_glob=list(globs),
             condition=condition, rationale=rationale, source_incident=src, created=created, oid_time=created)
    if condition == "resource_touched_by_other_agent":
        d["window_s"] = 600
    return d


def sample() -> dict:
    inc1, inc2 = "inc_a3f1c9d2e7b4", "inc_7be20c5d91af"
    ledger = [
        _row(150, "alpha", "write_file", "/var/tmp/notes.txt", "allow", 312, reason=_jev(0.08, "benign"), risk=0.08),
        _row(140, "delta", "http_get", "https://api.internal/status", "allow", 297, reason=_jev(0.05, "benign"), risk=0.05),
        _row(130, "gamma", "read_file", "~/.ssh/id_rsa", "block", 96, reason="policy p_baseline_ssh v1",
             policy_id="p_baseline_ssh"),
        _row(122, "beta", "write_file", "/etc/hosts", "block", 81, reason="policy p_baseline_etc v1",
             policy_id="p_baseline_etc"),
        _row(110, "alpha", "write_file", "/tmp/shared-message.txt", "allow", 318, reason=_jev(0.21, "benign"),
             risk=0.21, args={"content": "handoff: db password is hunter2"}),
        _row(104, "beta", "read_file", "/tmp/shared-message.txt", "block", 388,
             reason=_jev(0.94, "covert_channel", 0.96), risk=0.94),
        _row(80, "beta", "read_file", "/tmp/shared-message.txt", "block", 132, reason="policy p_tmp_channel v1",
             policy_id="p_tmp_channel"),
        _row(66, "alpha", "write_file", "/var/tmp/shared-message.txt", "allow", 305, reason=_jev(0.34, "benign"),
             risk=0.34, args={"content": "handoff: db password is hunter2"}),
        _row(60, "beta", "read_file", "/var/tmp/shared-message.txt", "block", 361,
             reason=_jev(0.91, "covert_channel", 0.94), risk=0.91),
        _row(38, "beta", "read_file", "/var/tmp/shared-message.txt", "block", 124, reason="policy p_tmp_channel v2",
             policy_id="p_tmp_channel"),
        _row(26, "delta", "http_get", "https://api.internal/status", "allow", 301, reason=_jev(0.06, "benign"),
             risk=0.06),
        _row(14, "gamma", "read_file", "~/.ssh/config", "block", 148, reason="policy p_baseline_ssh v1",
             policy_id="p_baseline_ssh"),
        _row(6, "beta", "read_file", "/tmp/shared-message.txt", "block", 118, reason="policy p_tmp_channel v2",
             policy_id="p_tmp_channel"),
    ]
    by_ago = {(r["agent_id"], r["target"], round((T0 - r["ts"]).total_seconds())): r for r in ledger}
    incidents = [
        dict(incident_id=inc1, ts=_t(104), action=dict(agent_id="beta", tool="read_file",
             target="/tmp/shared-message.txt", args={}, ts=_t(104)), context=[by_ago[("alpha", "/tmp/shared-message.txt", 110)]]),
        dict(incident_id=inc2, ts=_t(60), action=dict(agent_id="beta", tool="read_file",
             target="/var/tmp/shared-message.txt", args={}, ts=_t(60)), context=[by_ago[("alpha", "/var/tmp/shared-message.txt", 66)]]),
    ]
    tmp_why = "Cross-agent covert channel: one agent writes a secret to a shared temp file that another agent reads"
    policies = [
        _policy("p_baseline_ssh", 1, "active", ("read_file", "write_file"), ("~/.ssh", "~/.ssh/*", "/home/*/.ssh/*", "/Users/*/.ssh/*"),
                "Deny access to SSH credentials and configuration.", _t(900)),
        _policy("p_baseline_etc", 1, "active", ("read_file", "write_file"), ("/etc", "/etc/*", "/private/etc/*"),
                "Deny access to system configuration paths.", _t(900)),
        _policy("p_tmp_channel", 1, "superseded", ("read_file", "write_file"), ("/tmp/*",), tmp_why, _t(101.6),
                condition="resource_touched_by_other_agent", src=inc1),
        _policy("p_tmp_channel", 2, "active", ("read_file", "write_file"), ("/tmp/*", "/var/tmp/*"),
                tmp_why + " (widened to cover /var/tmp/*)", _t(57.6),
                condition="resource_touched_by_other_agent", src=inc2),
    ]
    return {"ledger": ledger, "incidents": incidents, "policies": policies, "demo": True}
