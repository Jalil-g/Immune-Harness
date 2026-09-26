# Immune Harness — Architecture

Single source of truth for what we're building. 6-hour scope.

## Core idea

Policies ARE the memory. When Jev flags a new attack, the Architect writes (or updates) a policy.
Next time, the policy blocks it in ~1ms — no similarity search or correlation engine needed.
If a variant slips through, Jev catches it and the Architect widens the policy (v1 → v2).

```
Detect (Jev) → Block → Architect rewrites policy → Compiler validates → Atlas → every agent protected
```

## Diagram

```
 Scripted agents (alpha, beta, gamma, workers) — one Python process
        │  harness.call(agent_id, tool, args)    ← the hook; agent-to-agent msgs are a tool too (send_message)
        ▼
 ┌──────────── GATEWAY (FastAPI POST /evaluate) ─────────────┐
 │ SENTRY                                                     │
 │  1. Policy match  in-memory cache (~1ms) → hit = BLOCK     │◄── change stream on security_policies
 │  2. Jev typed questions via OpenRouter (if no policy hit)  │    (new policy live instantly, no restart)
 │     violates_guardrails? (Noul) + threat_category (Choice) │
 │     context: recent action_ledger rows on same resource    │
 │  → BLOCK if violates_guardrails > 0.8                      │
 │  every action + decision → action_ledger                   │
 └──────┬──────────────────────────────┬──────────────────────┘
   allow│                         block│ → insert security_incidents
        ▼                              ▼
  Tool runner                  ARCHITECT (async, change stream on security_incidents)
  (fake FS in ./sandbox)         LLM + Pydantic structured output → new policy OR version+1 of existing
                                       ▼
                               COMPILER (pure Python)
                                 schema valid? deny-only? scope not too broad?
                                 replay last N allowed ledger rows → false positives < 5%?
                                 → insert security_policies {status: "active"}
                                       │
                                       └──► change stream → gateway cache reloads → next attempt blocked
```

## MongoDB Atlas

| Collection | Contents | Atlas feature |
|---|---|---|
| `security_policies` | Versioned deny rules (`policy_id`, `version`, `status`) | Change streams (hot reload), TTL index on `expires_at` |
| `action_ledger` | Every proposed action + decision + score | Index on `(target, ts)` for Jev context; TTL index; change stream feeds dashboard |
| `security_incidents` | Blocked action, Jev answers (risk, threat category + probabilities), context, resulting policy id | Change stream triggers Architect + dashboard |

Old policy versions stay in `security_policies` with `status: "superseded"` so the dashboard can show the diff.

## Models (one key: `OPENROUTER_API_KEY`)

| Use | Model | How |
|---|---|---|
| Sentry risk scoring | Jev (`~typesafe/jev-latest`) | `typesafe-sdk` pointed at OpenRouter: `AsyncTypeSafeClient(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api", model="~typesafe/jev-latest")` |
| Architect policy drafting | Claude via OpenRouter | OpenAI-compatible chat API + Pydantic structured output |

Jev does not write text. It answers typed questions with calibrated probabilities:
- `violates_guardrails` — **Noul** (0-1) → the risk score
- `threat_category` — **Choice** over `benign, covert_channel, credential_access, sandbox_escape, exfiltration, unauthorized_messaging, guardrail_exploit` → the "reason"
  - `guardrail_exploit` is the broad one: the agent goes against its own policy/guardrails or tries to exploit a weakness to get around them (limits, approvals, permissions, injected inputs, path traversal). Works for any domain, e.g. finance agents.
- Jev's state = the action (incl. `args`), the agent's **guardrails** (natural-language rules: defaults for all agents + per-agent ones, e.g. a payments agent's limits), recent activity by other agents on the target, authorized edges, and **learned policies** (plain-language summaries of active policies, so Jev also blocks *variants* the exact rule misses).
- Risk = `max(violates_guardrails, 1 − P(benign))`; block if > 0.8.

Free-text explanations come from the Architect (`rationale` field of the policy), off the fast path.
`typesafe-sdk` requires **Python 3.10+**.

## Shared schemas (`db/schemas.py`) — agree in hour 0-1, then build against mocks

```python
class Action(BaseModel):
    agent_id: str
    tool: str              # built-ins: read_file, write_file, http_get, shell, send_message; any custom tool (e.g. transfer_funds) allowed
    target: str            # path, URL, command, or recipient agent
    args: dict = {}
    ts: datetime

class Decision(BaseModel):
    decision: Literal["allow", "block"]
    reason: str
    risk_score: float | None = None
    policy_id: str | None = None
    latency_ms: float
```

Policy (data, never code — the Architect fills this, the Compiler validates it):

```json
{
  "policy_id": "p_tmp_channel", "version": 2, "status": "active", "effect": "deny",
  "tool": ["read_file", "write_file"],
  "target_glob": ["/tmp/*", "/var/tmp/*", "/dev/shm/*"],
  "condition": "resource_touched_by_other_agent",
  "window_s": 600,
  "expires_at": "...", "source_incident": "inc_42",
  "rationale": "Cross-agent covert channel via shared temp files"
}
```

`condition` is a small fixed enum, each mapping to a short Python matcher:
`always`, `resource_touched_by_other_agent`, `rate_exceeds`, `unauthorized_recipient`.

Authorized collaboration edges (who may message whom) live in `agents/config.py`.

## Folder layout

Tooling: **uv** (`pyproject.toml` + `uv.lock`, Python 3.12). `uv sync`, `uv add`, `uv run`. No pip / requirements.txt.

```
pyproject.toml, uv.lock, .python-version, .env.example   # shared — coordinate before editing
harness/
  gateway.py        # FastAPI /evaluate                          (A)
  sentry.py         # policy match + decision logic              (A)
  jev.py            # Jev via OpenRouter (typesafe-sdk)          (A)
  policy_cache.py   # load active policies + change stream       (B)
  architect.py      # incident → policy JSON (structured output) (D)
  compiler.py       # validate + replay + activate               (D)
agents/
  hook.py           # harness.call(): ask gateway, then run tool (C)
  tool_runner.py    # executes allowed tools inside ./sandbox    (C)
  config.py         # agents + authorized edges                  (C)
  scenarios.py      # scripted attacks + benign workers          (C)
db/
  atlas.py          # client, collections, indexes               (B)
  schemas.py        # Action, Decision, Policy                   (B)
dashboard/
  app.py            # Streamlit: live ledger, incidents, policies (D)
sandbox/            # fake filesystem — nothing touches real /tmp or ~/.ssh
```

## Team split

- **A — Gateway + Sentry:** `/evaluate`, policy matching, Jev typed questions via OpenRouter (with a heuristic fallback if Jev is slow/down), write to ledger/incidents.
- **B — Atlas:** cluster, collections, indexes, TTLs, `policy_cache.py` change stream, seed baseline policies (e.g. block `~/.ssh/*`, `/etc/*`).
- **C — Agents + scenarios:** hook, sandboxed tool runner, scripted attacks, benign traffic.
- **D — Architect + Compiler + Dashboard:** structured-output prompt, policy versioning, replay check, Streamlit.

## Demo script

1. Benign workers run — all allowed (also builds the false-positive replay baseline).
2. Alpha writes `/tmp/shared-note.txt` → allowed. Beta reads it → Jev sees Alpha's recent write, no authorized edge → **0.95, BLOCK** → incident.
3. Architect drafts `p_tmp_channel v1` → Compiler replays vs benign traffic (0 FP) → active. Dashboard shows it appear.
4. Gamma tries `/tmp/team-sync.txt` → **blocked by policy in ~1ms**, no LLM call.
5. Gamma tries `/var/tmp/x` → not covered → Jev flags → Architect widens to **v2** → next attempt blocked from memory.
6. Baseline policies: `read_file ~/.ssh/id_rsa`, write `/etc/hosts` → blocked instantly.

## Success metrics

| Metric | Target |
|---|---|
| Policy-hit block latency | < 10ms |
| Jev-path decision latency | < 500ms |
| Incident → active policy | < 5s |
| Repeated attack block rate | 100% |
| False positives on benign replay | < 5% |

## Timeline

- **0-1h:** schemas, Atlas cluster, repo skeleton
- **1-4h:** build own area against mocks
- **4-5h:** integrate end-to-end
- **5-6h:** freeze, rehearse demo, cache LLM responses as a fallback

## Out of scope (decided)

- Vector search / embeddings — policies are the memory; variants trigger a policy update instead
- Correlation aggregation engine — Jev gets recent ledger rows as context instead
- Strands Graph / A2A servers / A2A proxy — agents run in-process; messaging is a gated tool
- LLM-driven attackers — attacks are scripted so the demo is deterministic
