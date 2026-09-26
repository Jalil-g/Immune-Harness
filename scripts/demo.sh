#!/usr/bin/env bash
# One command for the whole demo: gateway + immune loop + dashboard + agents.
#
#   ./scripts/demo.sh                      # presentation pace, default scenario
#   ./scripts/demo.sh --fast               # quick run (~15 s)
#   ./scripts/demo.sh --quick              # short scenario: learn it, block it, widen it
#   ./scripts/demo.sh --file my.json       # your own scenario (see agents/scenario_files/)
#   ./scripts/demo.sh --real-architect     # real Claude writes the policies (default: mock, instant + v1 -> v2)
#   ./scripts/demo.sh --no-dashboard       # terminal only
#   ./scripts/demo.sh --no-reset           # keep previous actions / learned policies in Atlas
#   ./scripts/demo.sh --exit               # stop everything when the scenario ends
#   ./scripts/demo.sh -- --gap 1 --slow 0.5 --benign-rounds 2   # anything after -- goes to the scenario runner
#
# Resets the demo data in the MONGODB_DB database from .env (baselines stay) unless --no-reset.
# Logs: .demo-logs/  ·  Dashboard: http://localhost:8501  ·  Ctrl+C stops everything.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

PACE=demo; FILE=""; ARCH=mock; DASH=1; RESET=1; KEEP=1; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --fast) PACE=fast ;;
    --normal) PACE=normal ;;
    --slow) PACE=demo ;;
    --quick) FILE=agents/scenario_files/quick.json ;;
    --file) FILE="$2"; shift ;;
    --real-architect) ARCH=real ;;
    --no-dashboard) DASH=0 ;;
    --no-reset) RESET=0 ;;
    --exit) KEEP=0 ;;
    --) shift; EXTRA=("$@"); break ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)"; exit 1 ;;
  esac
  shift
done

LOG=.demo-logs; mkdir -p "$LOG"
B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; N=$'\033[0m'
say()  { echo "${B}▸${N} $*"; }
ok()   { echo "  ${G}✓${N} $*"; }
fail() { echo "  ${R}✗${N} $*"; exit 1; }

stop_all() {
  pkill -f "uvicorn harness.gateway:app --port 8000" 2>/dev/null
  pkill -f "harness.incident_watcher" 2>/dev/null
  pkill -f "streamlit run dashboard/app.py" 2>/dev/null
}
trap 'echo; say "stopping gateway, immune loop and dashboard"; stop_all; exit 0' INT TERM
trap 'stop_all' EXIT

wait_for() {  # wait_for <seconds> <command...>
  local t=$1; shift
  for _ in $(seq 1 $((t * 2))); do "$@" >/dev/null 2>&1 && return 0; sleep 0.5; done
  return 1
}

# ---------- checks ----------
say "checking setup"
command -v uv >/dev/null || fail "uv not installed: curl -LsSf https://astral.sh/uv/install.sh | sh"
[ -f .env ] || fail ".env missing: cp .env.example .env and fill in OPENROUTER_API_KEY + MONGODB_URI"
grep -qE '^MONGODB_URI=\s*mongodb' .env || fail "MONGODB_URI is empty in .env"
grep -qE '^OPENROUTER_API_KEY=\s*\S' .env && ok "OpenRouter key set" || echo "  ${Y}!${N} no OPENROUTER_API_KEY: Jev falls back to heuristic rules"
uv sync -q || fail "uv sync failed"
ok "dependencies"

stop_all; sleep 1   # leftovers from a previous run

# ---------- Atlas ----------
say "preparing Atlas"
uv run --env-file .env python -m db.atlas bootstrap >"$LOG/atlas.log" 2>&1 || { cat "$LOG/atlas.log"; fail "Atlas bootstrap failed (network access / URI?)"; }
ok "$(tail -1 "$LOG/atlas.log")"
if [ "$RESET" = 1 ]; then
  uv run --env-file .env python - >>"$LOG/atlas.log" 2>&1 <<'PY' || fail "reset failed"
from db.atlas import Atlas
with Atlas() as a:
    a.action_ledger.delete_many({})
    a.security_incidents.delete_many({})
    a.security_policies.delete_many({"policy_id": {"$not": {"$regex": "^p_baseline"}}})
PY
  ok "demo data reset (baseline policies kept)"
fi

# ---------- services ----------
say "starting services"
uv run --env-file .env uvicorn harness.gateway:app --port 8000 --log-level warning >"$LOG/gateway.log" 2>&1 &
wait_for 30 curl -sf localhost:8000/health || { tail -20 "$LOG/gateway.log"; fail "gateway didn't start"; }
ok "gateway      http://localhost:8000  ${D}($(curl -s localhost:8000/health | grep -o '"jev":"[a-z-]*"'))${N}"

if [ "$ARCH" = mock ]; then
  MOCK_ARCHITECT=1 PYTHONPATH=. uv run --env-file .env python -m harness.incident_watcher >"$LOG/watcher.log" 2>&1 &
else
  PYTHONPATH=. uv run --env-file .env python -m harness.incident_watcher >"$LOG/watcher.log" 2>&1 &
fi
wait_for 30 grep -q "watching security_incidents" "$LOG/watcher.log" || { tail -20 "$LOG/watcher.log"; fail "immune loop didn't start"; }
ok "immune loop  ${D}(architect: $ARCH)${N}"

if [ "$DASH" = 1 ]; then
  uv run streamlit run dashboard/app.py --server.port 8501 >"$LOG/dashboard.log" 2>&1 &
  wait_for 40 curl -sf localhost:8501/_stcore/health || { tail -20 "$LOG/dashboard.log"; fail "dashboard didn't start"; }
  ok "dashboard    http://localhost:8501"
  [ -z "${DEMO_NO_BROWSER:-}" ] && command -v open >/dev/null && open http://localhost:8501
  sleep 4   # give the browser a moment before the first action
fi

# ---------- scenario ----------
say "running the agents"
ARGS=(--all --pace "$PACE")
[ -n "$FILE" ] && ARGS+=(--file "$FILE")
uv run python -m agents.scenarios "${ARGS[@]}" "${EXTRA[@]+"${EXTRA[@]}"}" < /dev/null

echo
if grep -q " active — " "$LOG/watcher.log"; then ok "policies learned:"; grep -o "p_[a-z_]* v[0-9]* active" "$LOG/watcher.log" | sed 's/^/      /'; fi
if [ "$KEEP" = 1 ] && [ "$DASH" = 1 ]; then
  say "dashboard stays up at http://localhost:8501 — ${B}Ctrl+C${N} to stop everything"
  wait
fi
