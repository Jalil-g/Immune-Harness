"""Immune Harness dashboard: every step of the loop, live or in slow motion.

Run from the repo root:  uv run streamlit run dashboard/app.py
Reads Atlas only (MONGODB_URI / MONGODB_DB from .env).
If Atlas can't be reached (or DASHBOARD_DEMO=1) it shows built-in sample data, clearly badged, and never writes.
Data + logic: ui/data.py · styles: ui/styles.py · render helpers: ui/components.py
"""
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(HERE.parent / ".env")

from ui import components as C  # noqa: E402
from ui import data as D  # noqa: E402
from ui.styles import CSS  # noqa: E402

st.set_page_config(page_title="Immune Harness", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def play(stages, speed, animate):
    slots = [st.empty() for _ in stages]
    n = len(stages)
    for i, s in enumerate(stages, 1):
        slots[i - 1].html(C.stage_card(i, s, "pending" if animate else "done", last=i == n))
    if not animate:
        return
    for i, s in enumerate(stages, 1):
        if "risk" in s:  # Jev's meter fills up
            for k in range(1, 11):
                s["fill"] = s["risk"] * k / 10
                slots[i - 1].html(C.stage_card(i, s, "active", last=i == n))
                time.sleep(speed / 12)
            s["fill"] = None
        slots[i - 1].html(C.stage_card(i, s, "active", last=i == n))
        time.sleep(speed)
        slots[i - 1].html(C.stage_card(i, s, "done", last=i == n))


# ---------- sidebar ----------

with st.sidebar:
    st.markdown('<div class="ih-side-h">View</div>', unsafe_allow_html=True)
    view = st.segmented_control("View", ["Live", "Slow-mo"], default="Live", key="view",
                                label_visibility="collapsed") or "Live"
    st.markdown('<div class="ih-side-h">Timing</div>', unsafe_allow_html=True)
    refresh = st.slider("Live refresh", 0.5, 5.0, 1.0, 0.5, format="every %.1f s")
    speed = st.slider("Slow-mo speed", 0.3, 4.0, 1.4, 0.1, format="%.1f s per step")
    demo = D.demo_mode()
    db = D.db_name()
    st.markdown('<div class="ih-side-h">Demo data</div>', unsafe_allow_html=True)
    if demo:
        st.caption("Sample data is on, so nothing here can be reset. Reconnect to Atlas to see real actions.")
    else:
        st.caption("Clears actions, incidents and learned policies. Baseline policies stay.")
    sure = st.checkbox("I want to reset", key="reset_sure", disabled=demo)
    if st.button("Reset demo data", key="reset_btn", disabled=demo or not sure, use_container_width=True):
        D.reset_demo_data()
        for k in ("kpi_prev", "played", "last_story"):
            st.session_state.pop(k, None)
        st.toast("Demo data cleared — ready for a fresh run")

st.html(C.header(live=view == "Live", db=db, demo=demo))

# ---------- live ----------

if view == "Live":
    @st.fragment(run_every=refresh)
    def live():
        data = D.load()
        s = D.stats(data)
        prev = st.session_state.get("kpi_prev")
        st.session_state["kpi_prev"] = s
        r = D.focus_row(data)
        st.html(C.section("Latest decision", f"each action passes the gateway before its tool runs · updated {datetime.now(UTC):%H:%M:%S} UTC"))
        st.html(C.pipeline(data, r) if r else C.empty(
            "Waiting for the first agent action. Baseline policies are armed.", hint="uv run python -m agents.scenarios --all"))
        st.html(C.kpis(s, prev))
        left, right = st.columns([7, 4], gap="large")
        with left:
            st.html(C.section("Action log", C.tally(s)))
            st.html(C.feed(data))
        with right:
            st.html(C.section("Policy memory", "what the gateway has learned, versioned"))
            st.html(C.memory(data))
    live()

# ---------- slow-mo ----------

else:
    follow = st.toggle("Auto-play each new incident as it happens", value=False,
                       help="Leave this on during the live demo: every new Jev block is replayed step by step.")
    if follow:
        @st.fragment(run_every=1.0)
        def follower():
            d = D.load()
            played = st.session_state.setdefault("played", {i["incident_id"] for i in d["incidents"]})
            new = [i for i in d["incidents"] if i["incident_id"] not in played]
            if not new:
                last = st.session_state.get("last_story")
                if last:
                    st.html(C.event_header(last[0]))
                    play(last[1], speed, animate=False)
                else:
                    st.html(C.empty("Watching for the next incident… run the demo now."))
                return
            inc = new[0]
            r = D.row_for(d, inc)
            if not r:
                return
            t0 = time.time()  # give the Architect time to finish so the whole story is there
            while not D.policy_from_incident(d, inc) and time.time() - t0 < 12:
                time.sleep(0.5)
                d = D.load()
            played.add(inc["incident_id"])
            stages = C.build_stages(d, r)
            st.html(C.event_header(r))
            play(stages, speed, animate=True)
            st.session_state["last_story"] = (r, stages)
        follower()
    else:
        data = D.load()
        rows = data["ledger"][-80:][::-1]
        if not rows:
            st.html(C.empty("No actions yet."))
            st.stop()
        default = 0
        if data["incidents"]:  # open on the newest incident that taught a policy (the best story), else the newest
            learned = [i for i in data["incidents"] if D.policy_from_incident(data, i)]
            r0 = D.row_for(data, (learned or data["incidents"])[-1])
            default = next((k for k, r in enumerate(rows) if r is r0), 0)
        c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
        pick = c1.selectbox("Action to replay", range(len(rows)), index=default, format_func=lambda k: C.label(rows[k]))
        go = c2.button("▶ Play", type="primary", use_container_width=True, key="play_btn")
        st.html(C.event_header(rows[pick]))
        play(C.build_stages(data, rows[pick]), speed, animate=go)
