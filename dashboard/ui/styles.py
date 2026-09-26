"""The one stylesheet. Semantic colours are used the same way everywhere:
allow = emerald, block = rose, Jev = amber, memory/policy = cyan, learning/new policy = violet.

"""

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --bg: #0a0b0f; --surface: #12141a; --surface-2: #181b23; --border: rgba(255,255,255,.08); --border-2: rgba(255,255,255,.14);
  --text: #eef0f5; --muted: #a3aabb; --faint: #6b7385;
  --allow: #34d399; --block: #fb7185; --jev: #fbbf24; --mem: #22d3ee; --learn: #a78bfa;
  --allow-bg: rgba(52,211,153,.14); --block-bg: rgba(251,113,133,.14); --jev-bg: rgba(251,191,36,.13);
  --mem-bg: rgba(34,211,238,.13); --learn-bg: rgba(167,139,250,.15);
  --radius: 14px; --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* ---------- app shell ---------- */
html, body, [class*="st-"], .stApp, button, input, textarea { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
.stApp {
  background:
    radial-gradient(900px 520px at 12% -8%, rgba(34,211,238,.07), transparent 60%),
    radial-gradient(800px 480px at 95% 0%, rgba(167,139,250,.06), transparent 60%),
    linear-gradient(rgba(255,255,255,.018) 1px, transparent 1px) 0 0 / 100% 36px,
    linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px) 0 0 / 36px 100%,
    var(--bg);
  color: var(--text);
}
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1760px; }
[data-testid="stSidebar"] { background: #0d0f14; border-right: 1px solid var(--border); }
[data-testid="stSidebar"] .ih-side-h { font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--faint); margin: 18px 0 6px; font-weight: 600; }
.st-key-reset_btn button { background: var(--block-bg) !important; border: 1px solid rgba(251,113,133,.5) !important; color: var(--block) !important; font-weight: 600; }
.st-key-reset_btn button:disabled { opacity: .45; }
.st-key-play_btn button { font-weight: 700; }
code, .mono { font-family: var(--mono); }

.ih-sec { display: flex; align-items: baseline; gap: 4px 10px; flex-wrap: wrap; margin: 26px 0 10px; }
.ih-sec h3 { white-space: nowrap; font-size: 1.02rem; font-weight: 700; margin: 0; letter-spacing: -.01em; color: var(--text); }
.ih-sec span { font-size: .8rem; color: var(--faint); }

/* ---------- header ---------- */
.ih-head { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
.ih-logo { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center;
  background: linear-gradient(145deg, rgba(34,211,238,.18), rgba(167,139,250,.18)); border: 1px solid var(--border-2); }
.ih-brand { font-size: 1.75rem; font-weight: 800; letter-spacing: -.03em; line-height: 1; color: var(--text); }
.ih-tag { color: var(--muted); font-size: .9rem; margin-top: 4px; }
.ih-head-r { margin-left: auto; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.ih-live { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; font-weight: 700;
  font-size: .78rem; letter-spacing: .12em; color: var(--allow); background: var(--allow-bg); border: 1px solid rgba(52,211,153,.35); }
.ih-live i { width: 8px; height: 8px; border-radius: 50%; background: var(--allow); box-shadow: 0 0 0 0 rgba(52,211,153,.7); animation: ihlive 1.6s infinite; }
@keyframes ihlive { 70% { box-shadow: 0 0 0 9px rgba(52,211,153,0); } 100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); } }
.ih-replay { color: var(--learn); background: var(--learn-bg); border-color: rgba(167,139,250,.35); }
.ih-replay i { background: var(--learn); animation: none; }
.ih-badge { display: inline-flex; align-items: center; gap: 7px; padding: 6px 11px; border-radius: 999px; font-size: .78rem;
  color: var(--muted); background: var(--surface); border: 1px solid var(--border); }
.ih-badge b { font-family: var(--mono); color: var(--text); font-weight: 500; }

/* ---------- KPIs ---------- */
.ih-kpis { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)) minmax(0,1.7fr); gap: 14px; }
.ih-kpis2 { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 14px; margin-top: 14px; }
@media (max-width: 1100px) { .ih-kpis { grid-template-columns: repeat(3, minmax(0,1fr)); } .ih-speed { grid-column: 1 / -1; } }
.ih-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px 20px; position: relative; overflow: hidden; }
.ih-hero { border-top: 3px solid var(--c); background: linear-gradient(180deg, color-mix(in srgb, var(--c) 9%, var(--surface)), var(--surface) 70%); }
.ih-hero .n { font-size: 3.3rem; font-weight: 800; line-height: 1; letter-spacing: -.04em; color: var(--c); font-variant-numeric: tabular-nums; }
.ih-hero .l { margin-top: 10px; font-size: .95rem; font-weight: 600; color: var(--text); }
.ih-hero .s { margin-top: 3px; font-size: .78rem; color: var(--muted); }
.ih-mini { display: flex; align-items: baseline; gap: 12px; padding: 12px 18px; }
.ih-mini .n { font-size: 1.7rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.ih-mini .l { color: var(--muted); font-size: .88rem; }
.ih-speed .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.ih-speed .t { font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
.ih-speed .x { font-size: 2.6rem; font-weight: 800; letter-spacing: -.04em; color: var(--mem); line-height: 1; }
.ih-speed .x small { display: block; font-size: .95rem; font-weight: 700; color: var(--text); margin-top: 6px; letter-spacing: 0; }
.ih-bars { margin-top: 14px; display: grid; gap: 9px; }
.ih-bar { display: grid; grid-template-columns: auto minmax(40px, 1fr) auto; align-items: center; gap: 10px; font-size: .86rem; }
.ih-bar > span:first-child { min-width: 84px; white-space: nowrap; }
.ih-bar .track { height: 12px; border-radius: 6px; background: rgba(255,255,255,.06); overflow: hidden; }
.ih-bar .fill { height: 100%; border-radius: 6px; animation: ihgrow .9s cubic-bezier(.2,.8,.2,1); transform-origin: left; }
@keyframes ihgrow { from { transform: scaleX(0); } }
.ih-bar .v { font-family: var(--mono); text-align: right; font-weight: 600; }

@property --ihn { syntax: '<integer>'; inherits: false; initial-value: 0; }
.count { --ihn: var(--to); counter-reset: ihn var(--ihn); }
.count.up { animation: ihcount .9s cubic-bezier(.2,.8,.2,1); }
.count::after { content: counter(ihn); }
@keyframes ihcount { from { --ihn: var(--from); } to { --ihn: var(--to); } }

/* ---------- pills ---------- */
.pill { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 999px; font-size: .76rem; font-weight: 700;
  white-space: nowrap; line-height: 1.35; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
.pill svg { flex: 0 0 auto; }
.pill.allow { background: var(--allow); color: #04140d; }
.pill.block { background: var(--block); color: #1f0509; }
.pill.jev { background: var(--jev-bg); color: var(--jev); border: 1px solid rgba(251,191,36,.35); }
.pill.mem { background: var(--mem-bg); color: var(--mem); border: 1px solid rgba(34,211,238,.35); }
.pill.learn { background: var(--learn-bg); color: var(--learn); border: 1px solid rgba(167,139,250,.4); }
.pill.ghost { background: rgba(255,255,255,.05); color: var(--muted); border: 1px solid var(--border); font-weight: 600; }
.pill.agent { background: rgba(255,255,255,.07); color: var(--text); border: 1px solid var(--border-2); }
.chip { display: inline-block; font-family: var(--mono); font-size: .76rem; padding: 2px 8px; border-radius: 7px;
  background: rgba(255,255,255,.05); border: 1px solid var(--border); color: var(--text); margin: 2px 4px 2px 0; white-space: nowrap; }
.chip { max-width: 100%; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }
.chip.add { background: var(--allow-bg); border-color: rgba(52,211,153,.45); color: var(--allow); font-weight: 600; }
.chip.old { opacity: .55; }

/* ---------- event header + pipeline ---------- */
.ih-pipe { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 18px 22px 20px; }
.ih-evt { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.ih-evt .time { font-family: var(--mono); color: var(--faint); font-size: .85rem; margin-right: 4px; }
.ih-evt .tgt { font-family: var(--mono); font-size: .88rem; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 46ch; }
.ih-flow { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); }
.ih-node { position: relative; text-align: center; padding: 0 4px; }
.ih-node .dot { width: 46px; height: 46px; margin: 0 auto; border-radius: 50%; display: grid; place-items: center; position: relative; z-index: 2;
  background: var(--surface-2); border: 2px solid var(--border-2); color: var(--faint); transition: all .3s; }
.ih-node .lab { margin-top: 9px; font-size: .74rem; letter-spacing: .08em; text-transform: uppercase; font-weight: 700; color: var(--faint); }
.ih-node .sub { margin-top: 3px; font-size: .84rem; color: var(--faint); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ih-node.on .dot { border-color: var(--c); color: var(--c); background: color-mix(in srgb, var(--c) 16%, var(--surface-2));
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--c) 14%, transparent), 0 0 26px color-mix(in srgb, var(--c) 45%, transparent); }
.ih-node.on .lab { color: var(--text); }
.ih-node.on .sub { color: var(--c); font-weight: 650; }
.ih-node.busy .dot { border-color: var(--learn); color: var(--learn); animation: ihbusy 1.1s ease-in-out infinite; }
.ih-node.busy .sub { color: var(--learn); }
@keyframes ihbusy { 50% { box-shadow: 0 0 0 8px rgba(167,139,250,.18), 0 0 30px rgba(167,139,250,.5); } }
.ih-conn { position: absolute; top: 22px; left: calc(50% + 27px); width: calc(100% - 54px); height: 2px; background: rgba(255,255,255,.1); z-index: 1; }
.ih-conn.on { background: var(--c); box-shadow: 0 0 10px color-mix(in srgb, var(--c) 60%, transparent); }
.ih-conn .pk { position: absolute; top: -4px; left: 0; width: 10px; height: 10px; border-radius: 50%; background: #fff;
  box-shadow: 0 0 12px 3px var(--c); opacity: 0; animation: ihpacket 1.2s ease-in-out var(--d) 2 both; }
@keyframes ihpacket { 0% { left: 0; opacity: 0; } 15% { opacity: 1; } 85% { opacity: 1; } 100% { left: calc(100% - 10px); opacity: 0; } }

/* ---------- feed ---------- */
.ih-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 6px 6px 8px; overflow-x: auto; }
.ih-feed { width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed; font-size: .88rem; }
.ih-feed th { font-size: .68rem; letter-spacing: .1em; text-transform: uppercase; color: var(--faint); font-weight: 700;
  text-align: left; padding: 10px 8px 8px; border-bottom: 1px solid var(--border); }
.ih-feed td { padding: 9px 8px; border-bottom: 1px solid rgba(255,255,255,.045); vertical-align: middle;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ih-feed tr:last-child td { border-bottom: 0; }
.ih-feed td:first-child { border-left: 3px solid transparent; }
.ih-feed tr.b-mem td:first-child { border-left-color: var(--mem); }
.ih-feed tr.b-jev td:first-child { border-left-color: var(--block); }
.ih-feed tr.b-mem { background: linear-gradient(90deg, rgba(34,211,238,.07), transparent 45%); }
.ih-feed tr.b-jev { background: linear-gradient(90deg, rgba(251,113,133,.07), transparent 45%); }
.ih-feed tr.new td { animation: ihrow 2.2s ease-out; }
@keyframes ihrow { 0% { background: rgba(255,255,255,.13); transform: translateY(-5px); opacity: 0; } 25% { opacity: 1; transform: none; } }
.ih-feed .t { font-family: var(--mono); color: var(--faint); font-size: .8rem; }
.ih-feed .ag { font-weight: 700; }
.ih-feed .tool { font-family: var(--mono); color: var(--muted); font-size: .76rem; display: block; }
.ih-feed .tg { font-family: var(--mono); font-size: .84rem; display: block; overflow: hidden; text-overflow: ellipsis; }
.ih-feed .lat { font-family: var(--mono); color: var(--faint); text-align: right; font-size: .82rem; }
.ih-feed .lat.fast { color: var(--mem); font-weight: 700; }
.ih-risk { display: flex; align-items: center; gap: 6px; }
.ih-risk .rb { flex: 0 0 28px; height: 6px; border-radius: 3px; background: rgba(255,255,255,.08); overflow: hidden; }
.ih-risk .rb i { display: block; height: 100%; border-radius: 3px; }
.ih-risk .rn { font-family: var(--mono); font-size: .8rem; font-weight: 600; }
.ih-risk .cat { display: block; font-size: .72rem; color: var(--faint); overflow: hidden; text-overflow: ellipsis; }

/* narrow screens (e.g. 1280 with the sidebar open): feed full width, policy memory underneath */
@media (max-width: 1360px) {
  [data-testid="stHorizontalBlock"]:has(.ih-panel) { flex-wrap: wrap; }
  [data-testid="stHorizontalBlock"]:has(.ih-panel) > [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; min-width: 100%; }
}

/* ---------- policy memory ---------- */
.ih-pol { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; margin-bottom: 12px; }
.ih-pol.learned { border-color: rgba(167,139,250,.28); }
.ih-pol.new { animation: ihnew 2.4s ease-out 2; }
@keyframes ihnew { 0%, 100% { box-shadow: 0 0 0 0 rgba(167,139,250,0); } 40% { box-shadow: 0 0 0 4px rgba(167,139,250,.35), 0 0 40px rgba(167,139,250,.45); } }
.ih-pol .hd { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ih-pol .nm { font-family: var(--mono); font-weight: 600; font-size: .98rem; }
.ih-pol .newtag { font-size: .66rem; font-weight: 800; letter-spacing: .12em; color: #150d2b; background: var(--learn); padding: 2px 7px; border-radius: 5px; }
.ih-pol .desc { margin-top: 7px; color: var(--muted); font-size: .86rem; line-height: 1.45; }
.ih-pol .tools { margin-top: 8px; font-size: .78rem; color: var(--faint); }
.ih-tl { margin-top: 12px; border-left: 2px solid var(--border-2); margin-left: 7px; padding-left: 16px; }
.ih-tl .ver { position: relative; padding: 2px 0 10px; }
.ih-tl .ver::before { content: ""; position: absolute; left: -23px; top: 6px; width: 12px; height: 12px; border-radius: 50%;
  background: var(--surface); border: 2px solid var(--faint); }
.ih-tl .ver.active::before { border-color: var(--mem); background: var(--mem); box-shadow: 0 0 10px var(--mem); }
.ih-tl .ver.learned.active::before { border-color: var(--learn); background: var(--learn); box-shadow: 0 0 10px var(--learn); }
.ih-tl .vh { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: .84rem; }
.ih-tl .vh b { font-family: var(--mono); }
.ih-tl .ver.superseded .vh b { text-decoration: line-through; color: var(--faint); }
.ih-tl .when { color: var(--faint); font-size: .76rem; margin-left: auto; }
.ih-widen { margin-top: 2px; font-size: .82rem; font-weight: 600; color: var(--allow); }

/* ---------- slow-mo story ---------- */
.ih-stage { display: grid; grid-template-columns: 52px 1fr; gap: 0 14px; position: relative; }
.ih-stage .rail { position: relative; display: flex; justify-content: center; }
.ih-stage .rail::after { content: ""; position: absolute; top: 44px; bottom: -6px; width: 2px; background: var(--border-2); }
.ih-stage.last .rail::after { display: none; }
.ih-stage .num { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; font-weight: 800; font-size: .95rem;
  background: var(--surface-2); border: 2px solid var(--border-2); color: var(--faint); position: relative; z-index: 1; }
.ih-stage .box { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 18px; margin-bottom: 12px; transition: all .3s; }
.ih-stage .who { font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; font-weight: 700; color: var(--c); }
.ih-stage .ttl { font-size: 1.12rem; font-weight: 700; margin-top: 3px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ih-stage .bd { margin-top: 7px; color: var(--muted); font-size: .93rem; line-height: 1.55; }
.ih-stage .bd b { color: var(--text); }
.ih-stage.done .num { border-color: var(--c); color: var(--c); }
.ih-stage.active .num { border-color: var(--c); background: var(--c); color: #0a0b0f; box-shadow: 0 0 22px color-mix(in srgb, var(--c) 70%, transparent); }
.ih-stage.active .box { border-color: color-mix(in srgb, var(--c) 60%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--c) 40%, transparent), 0 10px 40px -10px color-mix(in srgb, var(--c) 45%, transparent); }
.ih-stage.pending { opacity: .3; }
.ih-stage.pending .who { color: var(--faint); }
.ih-line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 2px 0; }
.ih-ok { color: var(--allow); font-weight: 800; } .ih-no { color: var(--block); font-weight: 800; } .ih-dim { color: var(--faint); }
.ih-meter { position: relative; height: 14px; border-radius: 7px; background: rgba(255,255,255,.07); max-width: 520px; margin: 10px 0 4px; }
.ih-meter .f { position: absolute; inset: 0 auto 0 0; border-radius: 7px; }
.ih-meter .th { position: absolute; top: -6px; bottom: -6px; width: 2px; background: var(--text); }
.ih-meter-l { display: flex; justify-content: space-between; max-width: 520px; font-size: .74rem; color: var(--faint); }
.ih-quote { color: var(--text); font-style: italic; }
.ih-empty { color: var(--muted); padding: 28px; text-align: center; background: var(--surface); border: 1px dashed var(--border-2); border-radius: var(--radius); }

/* ---------- icons (CSS masks: Streamlit strips inline svg) ---------- */
.ico { display: inline-block; width: 1em; height: 1em; flex: 0 0 auto; background: currentColor; vertical-align: -.14em; -webkit-mask: var(--m) center / contain no-repeat; mask: var(--m) center / contain no-repeat; }
.ico-logo { background: linear-gradient(135deg, #22d3ee, #a78bfa); }
.ico-agent { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='8' width='18' height='12' rx='2'/><path d='M12 8V4'/><circle cx='8.5' cy='14' r='1'/><circle cx='15.5' cy='14' r='1'/></svg>"); }
.ico-memory { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><ellipse cx='12' cy='5' rx='8' ry='3'/><path d='M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5'/><path d='M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3'/></svg>"); }
.ico-jev { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='M13 2 3 14h9l-1 8 10-12h-9l1-8z'/></svg>"); }
.ico-decision { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/></svg>"); }
.ico-incident { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'/><path d='M12 9v4'/><path d='M12 17h.01'/></svg>"); }
.ico-architect { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='M12 20h9'/><path d='M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z'/></svg>"); }
.ico-compiler { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='m9 11 3 3L22 4'/><path d='M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11'/></svg>"); }
.ico-live { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='2'/><path d='M16.2 7.8a6 6 0 0 1 0 8.5'/><path d='M7.8 16.2a6 6 0 0 1 0-8.5'/><path d='M19.1 4.9a10 10 0 0 1 0 14.1'/><path d='M4.9 19.1a10 10 0 0 1 0-14.1'/></svg>"); }
.ico-logo { --m: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/><path d='m9 12 2 2 4-4'/></svg>"); }

/* feed: decision + decided-by stacked in one cell */
.ih-feed .res { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.ih-feed .res .pill { font-size: .72rem; padding: 2px 9px; }
"""
