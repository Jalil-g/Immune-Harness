# Person D — Architect + Compiler

Files: `harness/architect.py`, `harness/compiler.py`, `scripts/simulate_policy_learning.py` (dashboard is separate, `dashboard/`).

## What it does

```
Incident (Jev blocked an action)
   │
   ▼
Architect  ── draft Policy (status=draft) ──►  Compiler  ──► CompileResult
 mock or Claude                                 validate, replay, version
```

Given a blocked action, the Architect drafts a deny-only `Policy`. The Compiler checks it and decides whether it becomes the next active version. Policies are the memory: the first attack is caught by Jev, later attacks and variants are caught by the policy.

## Interface (what other people call)

```python
from harness.compiler import process_incident, CompileResult

result = process_incident(incident, active, ledger)
# incident: db.schemas.Incident
# active:   list[Policy]        currently active policies
# ledger:   list[LedgerEntry]   recent actions, sorted by ts ascending
```

`CompileResult`:

| field | meaning |
|---|---|
| `ok` | policy accepted |
| `reason` | why accepted/rejected (e.g. `ok (replay FP 0% over 23 rows)`, `scope too broad`) |
| `policy` | new **active** `Policy` version to insert into `security_policies` |
| `superseded` | the old version, already copied with `status="superseded"`, to update in Atlas (else `None`) |

**The functions never write anywhere.** The caller persists. When `ok`:
1. insert `result.policy` (new version first, so the cache never sees zero active versions)
2. if `result.superseded`: set that `(policy_id, version)` to `superseded`
3. set `incident.policy_id = result.policy.policy_id`

`PolicyCache` hot-reloads from the change stream, so the next request is blocked by policy.

## Decisions and why

- **Use the shared `db.schemas` types, no local models.** Originally D had its own `Policy` and used dicts and an in-memory `store`. Person B's schemas are strict (`extra="forbid"`, tuples, datetime `ts`), so everything is now typed against theirs. `Tool` is any non-empty string, so custom tools work.
- **Pure functions, caller persists.** Keeps D independent of Mongo. It's testable without Atlas and the gateway or a change-stream listener decides where writes happen.
- **The LLM gets its own loose `PolicyDraft` model** (lists, two conditions, `window_s`). `Policy` has validators and tuples that are awkward for structured output. `_to_policy` converts and validates.
- **Generalize to the directory.** A file-exact glob (`/tmp/shared-note.txt`) would miss every variant, so drafts become `/tmp/*`. The prompt says so and `_to_policy` enforces it (small models ignore prompts).
- **`window_s` is at least 600.** Small models return tiny windows that make the covert-channel condition useless.
- **Version by widening only.** If the draft reuses an active `policy_id`, the Compiler unions the old globs and tools into the new version (v2). Nothing the old version blocked is dropped. The old one is marked `superseded`, matching the v1 → v2 demo.
- **Compiler gates, in order:**
  1. reject `*`, `/*`, `**` (`scope too broad`)
  2. the policy must have blocked the triggering action, using `incident.context` plus the ledger as history
  3. **replay** against up to the last 200 *allowed* ledger rows, and reject at 5% or more false positives
- **Replay uses Sentry's `policy_matches`, not our own matcher.** One source of truth, so replay predicts what the gateway will do: it honors `authorized_edges` (both directions), counts only `allow` rows as touching a resource, and supports all four conditions. Replay only passes rows *earlier* than the action being tested, since the gateway only sees the past. `process_incident` and `compile_policy` take an optional `authorized_edges`; pass the gateway's set or replay can over-count false positives on authorized pairs.
- **The Architect only drafts `always` and `resource_touched_by_other_agent`.** The Compiler could validate `rate_exceeds` and `unauthorized_recipient` too, but the draft model doesn't produce them yet.
- **Mock Architect by default.** With no `OPENROUTER_API_KEY` (or with `MOCK_ARCHITECT=1`) it drafts deterministically, so the demo and tests are repeatable and free. With a key it calls Claude through OpenRouter (`ARCHITECT_MODEL`, default `anthropic/claude-sonnet-4.5`).

## What D needs from others

- **Person A (gateway/Sentry):** a call to `process_incident` after a block, passing active policies and a ts-ascending ledger. Persist the result as above.
- **Person B (Atlas):** nothing new. `Incident` has no place for the Compiler's `reason`; if we want it in the dashboard, add an optional `compiler_note` field.
- Nothing triggers `process_incident` yet: the gateway writes to `security_incidents` and stops. D needs a watcher on that collection (see Known gaps).

## Run it

```
uv run python scripts/simulate_policy_learning.py            # fake gateway + Jev, in-memory store, full v1 → v2 story
uv run pytest -q
```

The demo shows: benign traffic passes, alpha-writes/beta-reads is blocked by Jev and produces `p_tmp_channel v1`, a same-directory variant is blocked by policy with no LLM call, a `/var/tmp` variant slips through and widens to v2, and two bad drafts are rejected (too broad; false positives).

## Known gaps

- No Mongo wrapper yet (fetch active and ledger, then persist). About 15 lines once the gateway is ready.
- No unit tests for D beyond the demo.
- No watcher yet: nothing calls `process_incident` when the gateway inserts an incident.
- The Architect doesn't draft `rate_exceeds` or `unauthorized_recipient`.
- `Incident` drops Jev's `threat_category`, so the Architect can't use it.
- The mock only knows one policy (`p_tmp_channel`); other threats need the LLM path.
