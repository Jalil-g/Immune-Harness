# Person A — Gateway + Sentry: dev log

Log of every feature, change, and choice made in Person A's area. Newest feature at the bottom.

## Setup

- Branch: `feature/sentry`
- Python **3.12** venv (`uv venv --python 3.12 .venv`). The system Python is 3.9, and `typesafe-sdk` needs 3.10+.
- Deps: `typesafe-sdk fastapi uvicorn pymongo pydantic python-dotenv pytest httpx`
- Run tests: `.venv/bin/python -m pytest -q` (`pytest.ini` sets `pythonpath = .`)
- Env: `OPENROUTER_API_KEY` (Jev), optional `JEV_MODEL` (default `~typesafe/jev-latest`) and `RISK_THRESHOLD` (default `0.8`)

## Changes pushed directly to main (docs only)

- `ARCHITECTURE.md`, `README.md`, `CLAUDE.md`: Jev and the Architect both go through **OpenRouter** with one `OPENROUTER_API_KEY`. The Sentry asks Jev typed questions (Noul risk + Choice threat category) instead of asking for "score + reason". Python 3.10+ is required.
- Added `.gitignore` (`.venv`, `.env`, `__pycache__`, `sandbox/*`) and `.env.example`.

---

## Feature 1: Sentry (policy match + Jev via OpenRouter) ✅

### Files
| File | What |
|---|---|
| `harness/contracts.py` | `Action`, `Decision`, `Policy` pydantic models, copied from ARCHITECTURE.md. **Temporary.** Switch to `db/schemas.py` once Person B merges it. |
| `harness/jev.py` | `JevScorer`: calls Jev through OpenRouter with a heuristic fallback |
| `harness/sentry.py` | `Sentry.evaluate(action) -> Decision` and `policy_matches()` |
| `tests/test_sentry.py` | 14 tests |

### How it works
1. The Sentry fetches recent ledger rows on the **same target** (the injected `context(target, since)`, 600s window).
2. **Policy fast path:** it loops over active policies from the injected `policies()` and blocks on the first match. Jev is not called. Latency is under 1ms in tests.
3. If no policy matches, **Jev** gets:
   - state: the action, recent activity by *other* agents on that target, and the authorized edges
   - `violates_guardrails` (Noul, 0–1) → `risk_score`
   - `threat_category` (Choice: benign / covert_channel / credential_access / sandbox_escape / exfiltration / unauthorized_messaging) → `threat_category` and `category_confidence`
4. The action is blocked if `risk > 0.8`. The threshold is strict: exactly 0.8 is allowed.

### Choices and why
- **Jev through OpenRouter using `typesafe-sdk`**, not an OpenRouter chat SDK. TypeSafe's docs describe this exact setup: `AsyncTypeSafeClient(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api", model="~typesafe/jev-latest")`. Requests go to `https://openrouter.ai/api/v1/systemone`. OpenRouter's chat-completions API would not return Jev's typed answers and probabilities.
- **Storage is injected**, not imported. The Sentry takes `policies` and `context` callables, so it runs on mocks now. Person B's change-stream `policy_cache` and a ledger `find()` can plug in later without code changes.
- **The fallback heuristic never blocks the gateway on Jev.** Any error, a timeout (3s default, via `asyncio.wait_for`), or a missing key switches to rules (`source="fallback"`):
  - `.ssh`, `id_rsa`, `.env` and credentials files → credential_access, 0.95
  - writes to `/etc`, `/usr`, `/bin` → sandbox_escape, 0.95
  - `send_message` without an authorized edge → unauthorized_messaging, 0.85
  - a target another agent recently touched, with no edge → covert_channel, 0.9
  - anything else → benign, 0.05

  The demo keeps working without wifi or a key.
- **`Decision` has 3 extra optional fields:** `source` (policy / jev / fallback), `threat_category`, `category_confidence`. They're backwards compatible with the ARCHITECTURE.md contract. Person D's dashboard and architect can use them.
- **`Policy.max_count` was added** for the `rate_exceeds` condition. The contract in the docs had no field for it.
- **`rate_exceeds` counts per agent on the same target only.** Context rows are fetched by target, which keeps it to one indexed query. That's enough for the demo; a wider rate limit would need a per-agent query.
- An authorized edge counts in **both directions** for the cross-agent checks: alpha→beta allows beta to read alpha's file. For `send_message` it's directional (sender→recipient).
- Policies whose status isn't `active`, or whose `expires_at` has passed, are skipped even if the cache still holds them.

### Tests (`.venv/bin/python -m pytest -q`): **13 passed, 1 skipped**
- Policy path:
  - an `always` policy blocks without calling Jev
  - a cross-agent tmp policy blocks Gamma reading Alpha's file
  - the same policy ignores the agent's own file, authorized edges, and rows outside the window
  - superseded, expired and tool-mismatch policies are skipped
  - `rate_exceeds` and `unauthorized_recipient` work
- Jev path:
  - high risk blocks, with the category and confidence recorded
  - Jev receives the other agent's recent write as context
  - low risk allows
  - the 0.8 threshold is strict
- Fallback: a Jev exception, a Jev timeout (answers in under 1s), no API key, and the heuristic categories.
- **Real `typesafe-sdk` client with mocked HTTP:**
  - it calls `openrouter.ai/api/...` with `Bearer <OPENROUTER_API_KEY>` and model `~typesafe/jev-latest`
  - it parses the real response format into a Decision
- **Live Jev test:** skipped because there's no `OPENROUTER_API_KEY` on this machine yet. Run it with `OPENROUTER_API_KEY=... .venv/bin/python -m pytest -q -s -k live`.

### Still open / next
- Run the live test once the team has an OpenRouter key, then tune the threshold and question wording against real Jev scores.
- Feature 2: `harness/gateway.py`. FastAPI `POST /evaluate` wraps the Sentry and writes each action and decision to `action_ledger`, and blocks to `security_incidents`.
