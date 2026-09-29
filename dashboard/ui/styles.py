"""The one stylesheet: a flight-recorder ledger for an agent-safety gateway.
Paper and ink. Vermilion = block (the only alarm colour). Cobalt = decided or learned by memory.
Jev decisions are outlined marks, memory decisions are filled marks; every state also carries a text label.
"""

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --paper: #f3efe6; --card: #fbf9f4; --side: #ebe6da; --rule: #d6cfbe; --rule-2: #b9b09b;
  --ink: #15171c; --muted: #454a55; --faint: #5b606b;
  --block: #bf2a12; --mem: #1c3ab5; --jev: #7a4a00; --ok: #1f6b45;
  --block-bg: #f7dfd8; --mem-bg: #dfe4f7; --jev-bg: #f1e4c8; --ok-bg: #e0eadf;
  --radius: 6px;
  --serif: 'Newsreader', Georgia, 'Times New Roman', serif;
  --sans: 'Hanken Grotesk', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --ease: cubic-bezier(.2,.8,.2,1);
}

/* ---------- app shell ---------- */
html, body, [class*="st-"], .stApp, button, input, textarea { font-family: var(--sans); }
.stApp { background: var(--paper); color: var(--ink); }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1760px; }
[data-testid="stSidebar"] { background: var(--side); border-right: 1px solid var(--rule); }
[data-testid="stSidebar"] .ih-side-h { font-size: .8rem; color: var(--muted); margin: 18px 0 6px; font-weight: 700; border-bottom: 1px solid var(--rule); padding-bottom: 4px; }
.st-key-reset_btn button { background: var(--block-bg) !important; border: 1px solid var(--block) !important; color: var(--block) !important; font-weight: 600; }
.st-key-reset_btn button:disabled { opacity: 1; background: transparent !important; border-color: var(--rule-2) !important; color: var(--faint) !important; }
.st-key-play_btn button { font-weight: 700; }
code, .mono { font-family: var(--mono); }
::selection { background: var(--mem); color: var(--card); }
:focus-visible { outline: 2px solid var(--mem); outline-offset: 2px; }
.ih-sec { display: flex; align-items: baseline; gap: 4px 12px; flex-wrap: wrap; margin: 30px 0 10px; }
.ih-sec h3 { white-space: nowrap; font-family: var(--serif); font-size: 1.4rem; font-weight: 600; margin: 0; letter-spacing: -.01em; color: var(--ink); }
.ih-sec span { font-size: .88rem; color: var(--faint); }
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p { color: var(--ink); }

/* ---------- header ---------- */
.ih-head { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 6px; }
.ih-logo { width: 44px; height: 44px; border-radius: var(--radius); display: grid; place-items: center; background: var(--ink); color: var(--card); }
.ih-brand { font-family: var(--serif); font-size: 2rem; font-weight: 600; letter-spacing: -.02em; line-height: 1; color: var(--ink); }
.ih-tag { color: var(--muted); font-size: .95rem; margin-top: 5px; }
.ih-head-r { margin-left: auto; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.ih-live { display: inline-flex; align-items: center; gap: 8px; padding: 5px 12px; border-radius: 3px; font-weight: 700;
  font-size: .82rem; letter-spacing: .06em; color: var(--ink); background: var(--card); border: 1px solid var(--ink); }
.ih-live i { width: 8px; height: 8px; border-radius: 50%; background: var(--block); animation: ihlive 1.6s ease-in-out infinite; }
@keyframes ihlive { 50% { opacity: .25; } }
.ih-replay i { background: var(--mem); animation: none; }
.ih-badge { display: inline-flex; align-items: center; gap: 7px; padding: 5px 11px; border-radius: 3px; font-size: .84rem;
  color: var(--muted); background: transparent; border: 1px solid var(--rule-2); }
.ih-badge.demo { color: var(--jev); border-color: var(--jev); background: var(--jev-bg); font-weight: 600; }
.ih-badge b { font-family: var(--mono); color: var(--ink); font-weight: 500; }

/* ---------- figures strip ---------- */
.ih-strip { margin-top: 18px; border-top: 2px solid var(--ink); border-bottom: 1px solid var(--rule-2); background: var(--card); }
@media (max-width: 700px) { .ih-figs { grid-template-columns: 1fr; } .ih-fig { border-right: 0; border-bottom: 1px solid var(--rule); } }
.ih-figs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.ih-fig { padding: 16px 20px 16px 20px; border-right: 1px solid var(--rule); }
.ih-fig .n { font-family: var(--serif); font-size: 2.3rem; font-weight: 600; line-height: 1; color: var(--c); font-variant-numeric: tabular-nums; }
.ih-fig .l { margin-top: 8px; font-size: .95rem; font-weight: 700; color: var(--ink); }
.ih-fig .s { margin-top: 2px; font-size: .9rem; color: var(--muted); }

@property --ihn { syntax: '<integer>'; inherits: false; initial-value: 0; }
.count { --ihn: var(--to); counter-reset: ihn var(--ihn); }
.count.up { animation: ihcount .6s var(--ease); }
.count::after { content: counter(ihn); }
@keyframes ihcount { from { --ihn: var(--from); } to { --ihn: var(--to); } }

/* ---------- marks: filled = memory, outlined = Jev ---------- */
.pill { display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px; border-radius: 3px; font-size: .88rem; font-weight: 700;
  white-space: nowrap; line-height: 1.4; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
.pill svg { flex: 0 0 auto; }
.pill.allow { background: var(--ok-bg); color: var(--ok); border: 1px solid var(--ok); }
.pill.block { background: var(--block); color: var(--card); border: 1px solid var(--block); }
.pill.jev { background: transparent; color: var(--jev); border: 1px solid var(--jev); }
.pill.mem { background: var(--mem); color: var(--card); border: 1px solid var(--mem); }
.pill.learn { background: var(--mem-bg); color: var(--mem); border: 1px solid var(--mem); }
.pill.ghost { background: transparent; color: var(--muted); border: 1px solid var(--rule-2); font-weight: 600; }
.pill.agent { background: var(--card); color: var(--ink); border: 1px solid var(--rule-2); }
.chip { display: inline-block; font-family: var(--mono); font-size: .86rem; padding: 1px 7px; border-radius: 3px;
  background: var(--card); border: 1px solid var(--rule); color: var(--ink); margin: 2px 4px 2px 0; white-space: nowrap;
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }
.chip.add { background: var(--ok-bg); border-color: var(--ok); color: var(--ok); font-weight: 600; }
.chip.old { color: var(--faint); }

/* ---------- latest decision: the pipeline ---------- */
.ih-pipe { background: var(--card); border: 1px solid var(--rule-2); border-top: 2px solid var(--ink); border-radius: 0; padding: 22px 26px 26px; }
.ih-evt { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 22px; }
.ih-evt .time { font-family: var(--mono); color: var(--faint); font-size: .88rem; margin-right: 4px; }
.ih-evt .tgt { font-family: var(--mono); font-size: .92rem; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 46ch; }
.ih-verdict { display: flex; align-items: baseline; gap: 10px 22px; flex-wrap: wrap; }
.ih-verdict .w { font-family: var(--serif); font-size: 4rem; font-weight: 600; line-height: 1; letter-spacing: -.02em; }
.ih-verdict.block .w { color: var(--block); }
.ih-verdict.allow .w { color: var(--ink); }
.ih-verdict .by { font-size: 1.05rem; color: var(--muted); display: inline-flex; align-items: center; gap: 8px; }
.ih-verdict .ms { margin-left: auto; font-size: 1.5rem; font-weight: 500; color: var(--ink); }
.ih-vsub { margin-top: 6px; color: var(--muted); font-size: 1rem; }
.ih-lineage { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 22px; border-top: 1px solid var(--rule-2); }
.ih-led { padding: 14px 18px 4px 0; margin-right: 18px; border-right: 1px solid var(--rule); min-width: 0; }
.ih-led:last-child { border-right: 0; margin-right: 0; }
.ih-led .k { font-size: .9rem; font-weight: 700; color: var(--ink); }
.ih-led .ttl { font-size: .9rem; color: var(--muted); margin-top: 1px; }
.ih-led .m { margin-top: 10px; font-size: 1.15rem; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ih-led .d { margin-top: 5px; font-size: .9rem; color: var(--muted); overflow-wrap: anywhere; }
.ih-led.busy .m { color: var(--mem); animation: ihbusy 1.1s ease-in-out infinite; }
.ih-led.wait .m { color: var(--faint); }
@keyframes ihbusy { 50% { opacity: .45; } }
@media (max-width: 900px) { .ih-lineage { grid-template-columns: 1fr; } .ih-led { border-right: 0; margin-right: 0; border-bottom: 1px solid var(--rule); padding-bottom: 12px; }
  .ih-verdict .w { font-size: 2.8rem; } .ih-verdict .ms { margin-left: 0; } .ih-pipe { padding: 16px 14px 18px; } .ih-brand { font-size: 1.6rem; }
  .ih-feed { min-width: 640px; } }
/* path marks: filled square = memory, outlined square = Jev */
.path { display: inline-flex; align-items: center; gap: 7px; font-weight: 700; font-size: .95rem; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.path.mem { color: var(--mem); font-family: var(--mono); font-weight: 600; font-size: .9rem; }
.path.jev { color: var(--jev); }
.sq { display: inline-block; width: 11px; height: 11px; flex: 0 0 auto; box-sizing: border-box; }
.path.mem .sq, .sq.mem { background: var(--mem); border: 2px solid var(--mem); }
.path.jev .sq, .sq.jev { background: transparent; border: 2px solid var(--jev); }
.ih-legend { display: flex; gap: 8px 22px; flex-wrap: wrap; margin-top: 22px; padding-top: 12px; border-top: 1px solid var(--rule); font-size: .92rem; color: var(--muted); }
.ih-legend span { display: inline-flex; align-items: center; gap: 7px; }
.ih-legend .red { color: var(--block); }
.ih-legend b { color: var(--ink); }
.ih-glossary { font-size: .92rem; color: var(--muted); margin-top: 8px; }
.ih-glossary b { color: var(--ink); }

/* ---------- action log ---------- */
.ih-panel { background: var(--card); border: 1px solid var(--rule-2); border-top: 2px solid var(--ink); padding: 0 6px 6px; overflow-x: auto; }
.ih-feed { width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed; font-size: .92rem; }
.ih-feed th { font-size: .9rem; color: var(--muted); font-weight: 700; text-align: left; padding: 12px 8px 8px; border-bottom: 1px solid var(--rule-2); }
.ih-feed td { padding: 10px 8px; border-bottom: 1px solid var(--rule); vertical-align: middle; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ih-feed tr:last-child td { border-bottom: 0; }
.ih-feed tr.b-mem, .ih-feed tr.b-jev { background: var(--block-bg); }
.ih-feed tr.new td { animation: ihrow 1.6s var(--ease); }
@keyframes ihrow { 0% { background: var(--rule); opacity: 0; } 30% { opacity: 1; } }
.ih-feed .t { font-family: var(--mono); color: var(--faint); font-size: .84rem; }
.ih-feed .ag { font-weight: 700; }
.ih-feed .tool { font-family: var(--mono); color: var(--muted); font-size: .86rem; display: block; }
.ih-feed .tg { font-family: var(--mono); font-size: .88rem; display: block; overflow: hidden; text-overflow: ellipsis; }
.ih-feed .lat { font-family: var(--mono); color: var(--muted); text-align: right; font-size: .86rem; }
.ih-feed .lat.fast { color: var(--mem); font-weight: 600; }
.ih-risk { display: flex; align-items: center; gap: 8px; }
.ih-risk .rb { flex: 0 0 48px; height: 8px; background: var(--rule); overflow: hidden; }
.ih-risk .rb i { display: block; height: 100%; }
.ih-risk .rn { font-family: var(--mono); font-size: .86rem; font-weight: 600; }
.ih-risk .cat { display: block; font-size: .86rem; color: var(--faint); overflow: hidden; text-overflow: ellipsis; }

/* narrow screens (e.g. 1280 with the sidebar open): log full width, policy memory underneath */
@media (max-width: 1360px) {
  [data-testid="stHorizontalBlock"]:has(.ih-panel) { flex-wrap: wrap; }
  [data-testid="stHorizontalBlock"]:has(.ih-panel) > [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; min-width: 100%; }
}

/* ---------- policy memory: signed, versioned ledger entries ---------- */
.ih-pol { background: var(--card); border: 1px solid var(--rule-2); border-top: 2px solid var(--rule-2); padding: 16px 18px; margin-bottom: 12px; }
.ih-pol.learned { border-top-color: var(--mem); }
.ih-pol.new { animation: ihnew 1.8s var(--ease) 1; }
@keyframes ihnew { 0% { background: var(--mem-bg); } 100% { background: var(--card); } }
.ih-pol .hd { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ih-pol .nm { font-family: var(--mono); font-weight: 600; font-size: 1rem; }
.ih-pol .newtag { font-size: .8rem; font-weight: 700; color: var(--card); background: var(--mem); padding: 1px 7px; border-radius: 3px; }
.ih-pol .desc { margin-top: 8px; color: var(--muted); font-size: .92rem; line-height: 1.5; }
.ih-pol .tools { margin-top: 8px; font-size: .84rem; color: var(--muted); }
.ih-tl { margin-top: 12px; border-left: 2px solid var(--rule-2); margin-left: 7px; padding-left: 16px; }
.ih-tl .ver { position: relative; padding: 2px 0 10px; }
.ih-tl .ver::before { content: ""; position: absolute; left: -23px; top: 6px; width: 12px; height: 12px; background: var(--card); border: 2px solid var(--faint); }
.ih-tl .ver.active::before { border-color: var(--mem); background: var(--mem); }
.ih-tl .vh { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: .9rem; }
.ih-tl .vh b { font-family: var(--mono); }
.ih-tl .ver.superseded .vh b { text-decoration: line-through; color: var(--faint); }
.ih-tl .when { color: var(--faint); font-size: .82rem; margin-left: auto; font-family: var(--mono); }
.ih-widen { margin-top: 4px; font-size: .88rem; font-weight: 700; color: var(--ok); }

/* ---------- slow-mo story ---------- */
.ih-stage { display: grid; grid-template-columns: 52px 1fr; gap: 0 14px; position: relative; }
.ih-stage .rail { position: relative; display: flex; justify-content: center; }
.ih-stage .rail::after { content: ""; position: absolute; top: 44px; bottom: -6px; width: 2px; background: var(--rule-2); }
.ih-stage.last .rail::after { display: none; }
.ih-stage .num { width: 40px; height: 40px; border-radius: 4px; display: grid; place-items: center; font-weight: 700; font-size: .95rem;
  background: var(--card); border: 2px solid var(--rule-2); color: var(--faint); position: relative; z-index: 1; font-family: var(--mono); }
.ih-stage .box { background: var(--card); border: 1px solid var(--rule-2); padding: 14px 18px; margin-bottom: 12px; transition: border-color .2s var(--ease), background-color .2s var(--ease); }
.ih-stage .who { font-size: .82rem; font-weight: 700; color: var(--c); }
.ih-stage .ttl { font-family: var(--serif); font-size: 1.3rem; font-weight: 600; margin-top: 3px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ih-stage .bd { margin-top: 7px; color: var(--muted); font-size: .97rem; line-height: 1.55; }
.ih-stage .bd b { color: var(--ink); }
.ih-stage.done .num { border-color: var(--c); color: var(--c); }
.ih-stage.active .num { border-color: var(--c); background: var(--c); color: var(--card); }
.ih-stage.active .box { border-color: var(--c); border-top: 3px solid var(--c); }
.ih-stage.pending .box, .ih-stage.pending .num { border-style: dashed; }
.ih-stage.pending .who { color: var(--faint); }
.ih-stage.pending .ttl, .ih-stage.pending .bd { color: var(--faint); }
.ih-line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 2px 0; }
.ih-ok { color: var(--ok); font-weight: 800; } .ih-no { color: var(--block); font-weight: 800; } .ih-dim { color: var(--faint); }
.ih-meter { position: relative; height: 14px; background: var(--rule); max-width: 520px; margin: 10px 0 4px; }
.ih-meter .f { position: absolute; inset: 0 auto 0 0; }
.ih-meter .th { position: absolute; top: -6px; bottom: -6px; width: 2px; background: var(--ink); }
.ih-meter-l { display: flex; justify-content: space-between; max-width: 520px; font-size: .82rem; color: var(--faint); }
.ih-quote { color: var(--ink); font-family: var(--serif); font-style: italic; font-size: 1.05rem; }
.ih-empty { color: var(--muted); padding: 32px; text-align: center; background: var(--card); border: 1px dashed var(--rule-2); font-size: 1rem; }
.ih-empty code { display: block; margin-top: 10px; font-size: .84rem; color: var(--faint); }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}

/* ---------- icons (CSS masks: Streamlit strips inline svg) ---------- */
.ico { display: inline-block; width: 1em; height: 1em; flex: 0 0 auto; background: currentColor; vertical-align: -.14em; -webkit-mask: var(--m) center / contain no-repeat; mask: var(--m) center / contain no-repeat; }
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
.ih-feed .res .pill { font-size: .86rem; padding: 1px 8px; }
"""
