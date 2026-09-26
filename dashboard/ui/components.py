"""HTML render helpers. Pure presentation: every number comes from ui.data."""
import html
from datetime import UTC

from ui import data as D


TONE = {"allow": "var(--allow)", "block": "var(--block)", "jev": "var(--jev)", "mem": "var(--mem)",
        "learn": "var(--learn)", "muted": "var(--muted)"}


def e(x) -> str:
    return html.escape(str(x))


def svg(name, size=20) -> str:
    """Icon as a CSS mask (Streamlit strips inline <svg>). Takes the text colour."""
    return f'<i class="ico ico-{name}" style="font-size:{size}px"></i>'


def hhmmss(ts) -> str:
    return D.utc(ts).astimezone(UTC).strftime("%H:%M:%S")


def chip(text, cls="") -> str:
    return f'<span class="chip {cls}">{e(text)}</span>'


def globs(gs, prev=None, limit=None) -> str:
    gs = list(gs)
    shown = gs if limit is None else gs[:limit]
    out = [chip(("+ " if prev is not None and g not in prev else "") + g,
                "add" if prev is not None and g not in prev else "") for g in shown]
    if limit is not None and len(gs) > limit:
        out.append(chip(f"+{len(gs) - limit} more", "old"))
    return "".join(out)


def decision_pill(r) -> str:
    return '<span class="pill block">✕ BLOCK</span>' if r["decision"] == "block" else '<span class="pill allow">✓ ALLOW</span>'


def by_pill(r) -> str:
    p = D.path_of(r)
    if p == "policy":
        pid = r.get("policy_id") or "policy"
        return f'<span class="pill mem" title="{e(pid)}">{svg("memory", 13)} {e(pid)}</span>'
    return f'<span class="pill jev">{svg("jev", 13)} {"Jev" if p == "jev" else "fallback"}</span>'


def section(title, sub="") -> str:
    return f'<div class="ih-sec"><h3>{e(title)}</h3><span>{e(sub)}</span></div>'


def empty(msg) -> str:
    return f'<div class="ih-empty">{msg}</div>'


def risk_color(risk) -> str:
    if risk is None:
        return "var(--faint)"
    return "var(--block)" if risk > D.THRESHOLD else "var(--jev)" if risk >= 0.4 else "var(--allow)"


# ---------- header + KPIs ----------

def header(live: bool, db: str) -> str:
    mode = ('<span class="ih-live"><i></i>LIVE</span>' if live
            else '<span class="ih-live ih-replay"><i></i>SLOW-MO</span>')
    logo = '<i class="ico ico-logo" style="font-size:26px"></i>'
    return (f'<div class="ih-head"><div class="ih-logo">{logo}</div><div><div class="ih-brand">Immune Harness</div>'
            f'<div class="ih-tag">AI agents that get attacked once — and remember it forever</div></div>'
            f'<div class="ih-head-r">{mode}<span class="ih-badge">{svg("memory", 14)} Atlas <b>{e(db)}</b></span>'
            f'</div></div>')


def count(value, prev) -> str:
    """Integer that counts up from its previous value when it changes."""
    if value is None:
        return "–"
    v = int(round(value))
    p = v if prev is None else int(round(prev))
    cls = "count up" if p != v else "count"
    return f'<span class="{cls}" style="--from:{p};--to:{v}" aria-label="{v}"></span>'


def kpis(s: dict, prev: dict | None) -> str:
    pv = (prev or {}).get

    def hero(key, label, sub, tone):
        return (f'<div class="ih-card ih-hero" style="--c:{TONE[tone]}"><div class="n">{count(s[key], pv(key))}</div>'
                f'<div class="l">{label}</div><div class="s">{sub}</div></div>')

    mem, jev = s["mem_ms"], s["jev_ms"]
    if mem and jev:
        x = jev / mem
        speed = f'<div class="x">{x:.1f}×<small>faster from memory</small></div>'
        wm, wj = max(mem / max(mem, jev) * 100, 3), 100
    else:
        speed = '<div class="x" style="color:var(--faint)">—<small>no memory blocks yet</small></div>'
        wm, wj = 0, 100 if jev else 0
    ms = lambda v: f'{v:.0f} ms' if v else "–"  # noqa: E731
    speed_card = (
        f'<div class="ih-card ih-speed"><div class="top"><div class="t">Speed · median decision</div></div>{speed}'
        f'<div class="ih-bars">'
        f'<div class="ih-bar"><span style="color:var(--mem);font-weight:700">{svg("memory", 14)} Memory</span>'
        f'<div class="track"><div class="fill" style="width:{wm:.0f}%;background:var(--mem)"></div></div>'
        f'<span class="v" style="color:var(--mem)">{ms(mem)}</span></div>'
        f'<div class="ih-bar"><span style="color:var(--jev);font-weight:700">{svg("jev", 14)} Jev (LLM)</span>'
        f'<div class="track"><div class="fill" style="width:{wj:.0f}%;background:var(--jev)"></div></div>'
        f'<span class="v" style="color:var(--jev)">{ms(jev)}</span></div></div></div>')
    top = ('<div class="ih-kpis">'
           + hero("caught_by_jev", "caught by Jev", "new attacks, scored by the LLM", "jev")
           + hero("blocked_by_memory", "blocked by memory", "known attacks · no LLM call", "mem")
           + hero("learned", "policy versions learned", "rules the system wrote itself", "learn")
           + speed_card + "</div>")

    def mini(key, label, color):
        return (f'<div class="ih-card ih-mini"><span class="n" style="color:{color}">{count(s[key], pv(key))}</span>'
                f'<span class="l">{label}</span></div>')
    bottom = ('<div class="ih-kpis2">' + mini("actions", "actions seen", "var(--text)")
              + mini("allowed", "✓ allowed", "var(--allow)") + mini("incidents", "incidents → Architect", "var(--block)")
              + "</div>")
    return top + bottom


# ---------- pipeline ----------

def event_header(r) -> str:
    return (f'<div class="ih-evt"><span class="time">{hhmmss(r["ts"])}</span>'
            f'<span class="pill agent">{svg("agent", 13)} {e(r["agent_id"])}</span>'
            f'<span class="pill ghost mono">{e(r["tool"])}</span>'
            f'<span class="tgt" title="{e(r["target"])}">{e(r["target"])}</span>'
            f'{decision_pill(r)}{by_pill(r)}</div>')


def pipeline(data, r) -> str:
    path, blocked = D.path_of(r), r["decision"] == "block"
    color = "mem" if path == "policy" else ("block" if blocked else "allow")
    inc = D.incident_for(data, r) if blocked and path != "policy" else None
    pol = D.policy_from_incident(data, inc) if inc else None
    risk, cat, _ = D.jev_of(r)
    # (icon, label, sub, state, tone)
    nodes = [("agent", "Agent", r["agent_id"], "on", color)]
    if path == "policy":
        nodes += [("memory", "Memory", f'match {r.get("policy_id") or ""}', "on", "mem"),
                  ("jev", "Jev", "skipped", "skip", "mem")]
    else:
        nodes += [("memory", "Memory", "no match", "on", color),
                  ("jev", "Jev", f'{risk or 0:.2f} {cat or ""}', "on", color)]
    nodes.append(("decision", "Decision", "✕ BLOCK" if blocked else "✓ ALLOW", "on", color))
    if inc:
        nodes.append(("incident", "Incident", inc["incident_id"][4:12], "on", "block"))
        if pol:
            nodes += [("architect", "Architect", pol["policy_id"], "on", "learn"),
                      ("compiler", "Compiler", "✓ validated", "on", "learn"),
                      ("live", "Policy live", f'v{pol["version"]} active', "on", "learn")]
        elif D.age_s(inc["ts"]) < 30:
            nodes += [("architect", "Architect", "drafting…", "busy", "learn"),
                      ("compiler", "Compiler", "", "off", "learn"), ("live", "Policy live", "", "off", "learn")]
        else:
            nodes += [("architect", "Architect", "no policy", "off", "learn"),
                      ("compiler", "Compiler", "rejected", "off", "learn"), ("live", "Policy live", "–", "off", "learn")]
    else:
        tail = "known attack" if path == "policy" else "not needed"
        nodes += [("incident", "Incident", tail, "off", "block"), ("architect", "Architect", "", "off", "learn"),
                  ("compiler", "Compiler", "", "off", "learn"), ("live", "Policy live", "", "off", "learn")]

    fresh = D.age_s(r["ts"]) < 6
    cells = []
    for i, (icon, lab, sub, state, tone) in enumerate(nodes):
        conn = ""
        if i < len(nodes) - 1:
            nxt = nodes[i + 1]
            on = state in ("on", "skip") and nxt[3] in ("on", "skip", "busy")
            pk = f'<span class="pk" style="--d:{i * .22:.2f}s"></span>' if on and fresh else ""
            conn = f'<span class="ih-conn {"on" if on else ""}" style="--c:{TONE[nxt[4]]}">{pk}</span>'
        cls = {"on": "on", "busy": "busy", "skip": "on skip", "off": ""}[state]
        dot_style = "border-style:dashed;" if state == "skip" else ""
        cells.append(f'<div class="ih-node {cls}" style="--c:{TONE[tone]}">{conn}'
                     f'<div class="dot" style="{dot_style}">{svg(icon, 20)}</div><div class="lab">{lab}</div>'
                     f'<div class="sub" title="{e(sub)}">{e(sub) or "&nbsp;"}</div></div>')
    return f'<div class="ih-pipe">{event_header(r)}<div class="ih-flow">{"".join(cells)}</div></div>'


# ---------- feed ----------

def feed(data, n=18) -> str:
    rows = data["ledger"][-n:][::-1]
    body = []
    for r in rows:
        path, blocked = D.path_of(r), r["decision"] == "block"
        cls = ("b-mem" if path == "policy" else "b-jev") if blocked else ""
        if D.age_s(r["ts"]) < 5:
            cls += " new"
        risk, cat, _ = D.jev_of(r)
        if risk is None:
            risk_html = '<span class="ih-dim">—</span>'
        else:
            risk_html = (f'<div class="ih-risk" title="{e(cat or "")}"><span class="rb"><i style="width:{risk * 100:.0f}%;'
                         f'background:{risk_color(risk)}"></i></span><span class="rn" style="color:{risk_color(risk)}">'
                         f'{risk:.2f}</span></div><span class="cat">{e(cat or "")}</span>')
        fast = "fast" if path == "policy" and blocked else ""
        body.append(
            f'<tr class="{cls}"><td><span class="ag">{e(r["agent_id"])}</span><span class="t" style="display:block">'
            f'{hhmmss(r["ts"])}</span></td>'
            f'<td><span class="tool">{e(r["tool"])}</span><span class="tg" title="{e(r["target"])}">{e(r["target"])}</span></td>'
            f'<td><div class="res">{decision_pill(r)}{by_pill(r)}</div></td><td>{risk_html}</td>'
            f'<td class="lat {fast}">{r["latency_ms"]:.0f} ms</td></tr>')
    # widths on <th>: Streamlit's HTML sanitizer drops <colgroup>
    head = ('<tr><th style="width:84px">Agent</th><th>Action</th><th style="width:138px">Decision · by</th>'
            '<th style="width:96px">Risk</th><th style="width:82px;text-align:right">Latency</th></tr>')
    return f'<div class="ih-panel"><table class="ih-feed">{head}{"".join(body)}</table></div>'


# ---------- policy memory ----------

def memory(data) -> str:
    by = {}
    for d in data["policies"]:
        by.setdefault(d["policy_id"], []).append(d)
    learned = sorted((k for k in by if not k.startswith("p_baseline")),
                     key=lambda k: -max(d["created"].timestamp() for d in by[k]))
    cards = []
    for pid in learned + sorted(k for k in by if k.startswith("p_baseline")):
        vs = sorted(by[pid], key=lambda d: d["version"])
        latest, base = vs[-1], pid.startswith("p_baseline")
        new = not base and D.age_s(latest["created"]) < 10
        origin = '<span class="pill ghost">baseline · seeded</span>' if base else '<span class="pill learn">learned</span>'
        tl, prev = [], None
        for d in vs:
            status = d["status"]
            st_pill = (f'<span class="pill {"ghost" if base else "learn"}">{e(status)}</span>' if status == "active"
                       else f'<span class="pill ghost">{e(status)}</span>')
            tl.append(f'<div class="ver {status} {"" if base else "learned"}"><div class="vh"><b>v{d["version"]}</b>'
                      f'{st_pill}<span class="when">{hhmmss(d["created"])}</span></div>'
                      f'{globs(d["target_glob"], prev["target_glob"] if prev else None, 4 if base else None)}</div>')
            prev = d
        widen = ""
        if len(vs) > 1:
            added = [g for g in vs[-1]["target_glob"] if g not in vs[-2]["target_glob"]]
            widen = (f'<div class="ih-widen">↗ widened v{vs[-2]["version"]} → v{vs[-1]["version"]}: '
                     + " ".join(e(g) for g in added) + "</div>")
        cards.append(
            f'<div class="ih-pol {"" if base else "learned"} {"new" if new else ""}"><div class="hd">'
            f'<span class="nm">{e(pid)}</span>{origin}{"<span class=newtag>NEW</span>" if new else ""}</div>'
            f'<div class="desc">{e(latest["rationale"])}</div>'
            f'<div class="tools">covers {"".join(chip(t) for t in latest["tool"])}'
            f'{" · when " + chip(latest["condition"]) if latest["condition"] != "always" else ""}</div>'
            f'{widen}<div class="ih-tl">{"".join(tl)}</div></div>')
    return "".join(cards) or empty("No policies yet.")


# ---------- slow-mo story ----------

def meter(risk: float, fill: float | None = None) -> str:
    fill = risk if fill is None else fill
    return (f'<div class="ih-meter"><div class="f" style="width:{fill * 100:.0f}%;background:linear-gradient(90deg,'
            f'var(--allow),var(--jev) 55%,var(--block))"></div><div class="th" style="left:{D.THRESHOLD * 100:.0f}%">'
            f'</div></div><div class="ih-meter-l"><span>0 · safe</span><span>block above {D.THRESHOLD:.2f}</span>'
            f'<span>1 · attack</span></div>')


def action_text(r) -> str:
    args = r.get("args") or {}
    extra = ""
    if args.get("content"):
        extra = f'<div class="ih-line">content {chip(str(args["content"])[:90])}</div>'
    elif args.get("body"):
        extra = f'<div class="ih-line">message {chip(str(args["body"])[:110])}</div>'
    return (f'<div class="ih-line"><span class="pill agent">{svg("agent", 13)} {e(r["agent_id"])}</span>'
            f'{chip(r["tool"])}{chip(r["target"])}</div>{extra}')


def build_stages(data, r):
    path, blocked = D.path_of(r), r["decision"] == "block"
    stages = [dict(who="Agent · sandboxed", tone="muted", title="Proposes an action",
                   body=action_text(r) + f'<div class="ih-dim" style="margin-top:4px">{hhmmss(r["ts"])} UTC · '
                        f'intercepted by <code>harness.call()</code> → <code>POST /evaluate</code></div>')]

    checks = D.check_policies(data, r)
    lines = []
    for d, matched, why in checks:
        name = f'{d["policy_id"]} v{d["version"]}'
        if matched:
            lines.append(f'<div class="ih-line"><span class="ih-no">✕ match</span><span class="pill mem">'
                         f'{svg("memory", 13)} {e(name)}</span></div>')
            continue
        kind, val = why
        reason = {"tool": lambda: f"doesn't cover {chip(val)}", "path": lambda: "path not in " + globs(val, limit=3),
                  "untouched": lambda: "no other agent touched this file",
                  "condition": lambda: "condition not met"}[kind]()
        lines.append(f'<div class="ih-line"><span class="ih-dim">– {e(name)}</span> {reason}</div>')
    if path == "policy":
        title = f'Known attack — matches <span class="pill mem">{svg("memory", 13)} {e(r.get("policy_id"))}</span>'
    else:
        title = f"No policy matches ({len(checks)} checked) → ask Jev"
    stages.append(dict(who="Gateway · policy memory (Atlas, hot-reloaded)", tone="mem", title=title,
                       body="".join(lines) or "no policies yet"))

    if path == "policy":
        pol = D.policy_doc(data, r.get("policy_id"))
        stages.append(dict(who="Jev", tone="muted", title="Skipped — no LLM call needed",
                           body=f'The attack is already in memory. Rule: '
                                f'<span class="ih-quote">“{e(pol["rationale"]) if pol else ""}”</span>'))
        stages.append(dict(who="Gateway", tone="block",
                           title=f'{decision_pill(r)} from memory in <span class="mono">{r["latency_ms"]:.0f} ms</span>',
                           body="Tool never runs. Known attack → no incident, so the Architect isn't triggered again."))
        return stages

    ev = D.evidence(data, r)
    ctx = "".join(f'<div class="ih-line">{decision_pill(x)}<b>{e(x["agent_id"])}</b>{chip(x["tool"])}'
                  f'<span class="ih-dim">{(D.utc(r["ts"]) - D.utc(x["ts"])).total_seconds():.1f}s earlier</span></div>'
                  for x in ev)
    stages.append(dict(who="Gateway · action_ledger (Atlas)", tone="muted", title="Collects evidence on the same resource",
                       body=ctx or "No other agent touched this resource recently."))

    risk, cat, conf = D.jev_of(r)
    risk = risk if risk is not None else 0.0

    def jev_body(fill, risk=risk, cat=cat, conf=conf):
        c = f'<span class="pill {"block" if cat and cat != "benign" else "allow"}">{e(cat or "?")}</span>'
        return (f'<div class="ih-line">risk <b class="mono" style="font-size:1.25rem;color:{risk_color(risk)}">'
                f'{risk:.2f}</b> · category {c} · confidence <b class="mono">{conf or 0:.2f}</b></div>' + meter(risk, fill))
    stages.append(dict(who="Jev · OpenRouter" if path == "jev" else "Fallback rules (Jev unavailable)", tone="jev",
                       title="Scores the action", body=jev_body, risk=risk))

    stages.append(dict(who="Gateway", tone="block" if blocked else "allow",
                       title=f'{decision_pill(r)} in <span class="mono">{r["latency_ms"]:.0f} ms</span>',
                       body=(f"risk {risk:.2f} &gt; {D.THRESHOLD:.2f} → the tool never runs" if blocked
                             else "Tool runs inside ./sandbox. Every action is logged to action_ledger.")))
    if not blocked:
        return stages

    inc = D.incident_for(data, r)
    if not inc:
        stages.append(dict(who="Atlas · security_incidents", tone="block", title="Incident not found", body=""))
        return stages
    stages.append(dict(who="Atlas · security_incidents", tone="block",
                       title=f'New incident {chip(inc["incident_id"][:14] + "…")}',
                       body=f'{len(inc.get("context", []))} evidence rows attached · the change stream wakes the Architect'))

    pol = D.policy_from_incident(data, inc)
    if not pol:
        waiting = D.age_s(inc["ts"]) < 30
        stages.append(dict(who="Architect · LLM", tone="learn", title="Drafting a policy…" if waiting else "No policy produced",
                           body="Waiting for the incident watcher." if waiting else
                           "The Compiler rejected the draft, or <code>harness.incident_watcher</code> isn't running."))
        return stages

    took = D.learn_time(pol, inc)
    prev = D.previous_version(data, pol)
    name = f'{pol["policy_id"]} v{pol["version"]}'
    stages.append(dict(who="Architect · LLM → structured output", tone="learn",
                       title=f'Drafts <span class="pill learn">{e(name)}</span>'
                             + (" — widens the existing rule" if prev else " — a new rule"),
                       body=f'<div class="ih-quote">“{e(pol["rationale"])}”</div><div class="ih-line" style="margin-top:6px">'
                            f'deny {"".join(chip(t) for t in pol["tool"])} on '
                            f'{globs(pol["target_glob"], prev["target_glob"] if prev else None)}'
                            f' when {chip(pol["condition"])}</div>'))

    c = D.compiler_checks(data, pol, inc, prev)
    ok = lambda b: '<span class="ih-ok">✓</span>' if b else '<span class="ih-no">✕</span>'  # noqa: E731
    lines = [f'<div class="ih-line">{ok(c["scope_ok"])} scope not too broad (no {chip("*")}{chip("/*")})</div>',
             f'<div class="ih-line">{ok(c["deny_ok"])} deny-only</div>',
             f'<div class="ih-line">{ok(c["trigger_ok"])} would have blocked the triggering action</div>',
             f'<div class="ih-line">{ok(c["fp"] < c["max_fp"])} replay: <b>{c["hits"]} of {c["replayed"]}</b> past allowed '
             f'actions blocked ({c["fp"]:.0%} false positives, limit {c["max_fp"]:.0%})</div>']
    if prev:
        lines.append(f'<div class="ih-line">{ok(True)} only widens v{prev["version"]}: keeps {globs(c["kept"])} adds '
                     f'{"".join(chip("+ " + g, "add") for g in c["added"])}</div>')
    stages.append(dict(who="Compiler · same matcher as the gateway", tone="learn", title="Validates before activating",
                       body="".join(lines)))

    stages.append(dict(who="Atlas · security_policies → change stream", tone="mem",
                       title=f'<span class="pill mem">{svg("memory", 13)} {e(name)}</span> is live · {took} after the incident',
                       body=(f'v{prev["version"]} marked <i>superseded</i>. ' if prev else "")
                            + "Every gateway reloads it instantly — no restart."))

    nxt = D.next_blocked_by(data, pol)
    if nxt:
        stages.append(dict(who="Next attempt", tone="mem",
                           title=f'{decision_pill(nxt)} by memory in <span class="mono">{nxt["latency_ms"]:.0f} ms</span>',
                           body=action_text(nxt) + f'<div class="ih-dim" style="margin-top:4px">No Jev call · no new '
                                f'incident · first catch took {r["latency_ms"]:.0f} ms, then {took} to learn</div>'))
    else:
        stages.append(dict(who="Next attempt", tone="mem", title="Waiting for the next attempt…",
                           body="The next matching action will be blocked by this policy, without Jev."))
    return stages


def stage_card(i, s, state, last=False) -> str:
    body = s["body"](s.get("fill")) if callable(s["body"]) else s["body"]
    return (f'<div class="ih-stage {state} {"last" if last else ""}" style="--c:{TONE[s["tone"]]}">'
            f'<div class="rail"><div class="num">{i}</div></div><div class="box"><div class="who">{e(s["who"])}</div>'
            f'<div class="ttl">{s["title"]}</div><div class="bd">{body}</div></div></div>')


def label(r) -> str:
    p = D.path_of(r)
    who = "memory" if p == "policy" else p
    return f'{hhmmss(r["ts"])} · {r["agent_id"]} {r["tool"]} {r["target"][:40]} · {r["decision"].upper()} ({who})'
