# Spec: Incident Watcher (Person D)

Target file: `harness/incident_watcher.py`. Tests: `tests/test_incident_watcher.py`.
Written against `origin/main` at `806275a` (gateway + Atlas merged). If main has moved, re-check the "Depends on" list first.

## Purpose

Close the learning loop. The gateway inserts an `Incident` when Jev blocks a novel attack, then stops. The watcher notices the insert, runs the Architect and Compiler, and persists the new policy version. `PolicyCache` hot-reloads it, so the next attempt is blocked by policy.

```
gateway ─► security_incidents (insert) ─► WATCHER ─► process_incident ─► security_policies (v_n active, v_n-1 superseded)
                                                                     └► incident.policy_id set
```

Policy blocks never create incidents (gateway `INCIDENT_SOURCES = ("jev", "fallback")`), so the new policy can't retrigger the watcher.

## Depends on (verify these still exist on main)

| Need | Where | Used as |
|---|---|---|
| `Atlas` (`.security_policies`, `.action_ledger`, `.security_incidents`, `.close()`, context manager) | `db/atlas.py` | DB access. Env: `MONGODB_URI`, `MONGODB_DB` |
| `Policy`, `Incident`, `LedgerEntry` with `from_mongo()` / `to_mongo()` | `db/schemas.py` | all reads and writes go through these |
| `process_incident(incident, active, ledger, authorized_edges) -> CompileResult` | `harness/compiler.py` | the pipeline |
| `CompileResult(ok, reason, policy, superseded)` | `harness/compiler.py` | what to persist |
| Unique index `(policy_id, version)` on `security_policies` | `Atlas.ensure_indexes` | guards against double-processing |
| `AUTHORIZED_EDGES` in `agents/config.py`, else env `AUTHORIZED_EDGES="a>b,b>c"` | same source as `gateway.load_edges` | passed to the Compiler |

Do not import `harness.gateway` for edges: it builds the app at import time (`app = create_app()`). Re-implement the ~6-line loader.

## Behavior

### Trigger
Change stream on `security_incidents`, pipeline `[{"$match": {"operationType": "insert"}}]`, `max_await_time_ms=1000`. Updates (such as the watcher setting `policy_id`) are ignored, so there is no self-loop.

### Per incident (`handle_incident(incident, store, authorized_edges) -> CompileResult`)
1. `active` = all `security_policies` with `status == "active"`, parsed with `Policy.from_mongo` (skip invalid docs, log a warning).
2. `ledger` = newest 200 `action_ledger` rows (by `ts` desc), parsed with `LedgerEntry.from_mongo` (skip invalid), returned **oldest first**. The Compiler expects ts ascending and replays over at most 200 rows.
3. `res = process_incident(incident, active, ledger, authorized_edges)`.
4. If `not res.ok`: log `incident <id>: no policy (<reason>)` and stop. Nothing is written.
5. If `res.ok`, in this order:
   1. insert `res.policy.to_mongo()` into `security_policies`. **First**, so the cache never sees zero active versions. On `DuplicateKeyError`, log and return: another watcher won the race, so do no supersede or link.
   2. if `res.superseded`: `update_one({"policy_id", "version"}, {"$set": {"status": "superseded"}})` for that exact version.
   3. `update_one({"incident_id": ...}, {"$set": {"policy_id": res.policy.policy_id}})` on `security_incidents`. `Incident.policy_id` holds only the id, not `"p x v2"`.
6. Log one line per outcome including the reason and the version.

### Loop and failure handling (`run(store, authorized_edges, stop, retry_seconds)`)
- Loop until `stop` (a `threading.Event`) is set.
- Use `stream.try_next()`. `None` means keep waiting, and it lets the loop notice `stop`.
- Parse `event["fullDocument"]` with `Incident.from_mongo`. Any exception on one incident is logged with a traceback and the loop **continues**.
- `PyMongoError` from the stream: log the class name only (never the message, which can hold connection details), wait `retry_seconds` (default 2.0, `stop.wait`), reopen a **new** stream.
- No resume tokens and no catch-up on startup: an incident inserted while the watcher is down is missed. This is accepted for the hackathon.

### Entry point
`uv run python -m harness.incident_watcher`. It calls `load_dotenv()`, sets logging (`INFO`), and runs with `Atlas()` as a context manager. `KeyboardInterrupt` exits cleanly.

## Structure (keeps it testable without Atlas)

- `AtlasWatcherStore(atlas)` is the only class that touches PyMongo. Methods: `watch_incidents()`, `active_policies()`, `recent_ledger()`, `save_policy(policy)`, `mark_superseded(policy)`, `link_incident(incident_id, policy_id)`.
- `handle_incident` and `run` take any object with those methods, so tests use an in-memory fake.

## Out of scope

- Startup catch-up of unprocessed incidents. Rejected incidents also have `policy_id = None`, so "no policy_id" can't mean "unprocessed" without a marker field.
- Storing the Compiler's `reason` on the incident. `Incident` has no field for it. If wanted, Person B adds an optional `compiler_note`, and the watcher sets it in step 5.3 and on rejection.
- Multiple-watcher coordination beyond the unique-index guard.
- Running inside the gateway process. It runs as a separate process.

## Tests (`tests/test_incident_watcher.py`, in-memory `FakeStore` with a `(policy_id, version)` uniqueness check)

1. New attack: v1 saved as active, incident linked to `p_tmp_channel`.
2. Variant: v2 saved active, v1 `superseded`, v2 globs are the union.
3. Rejected draft: nothing saved, nothing linked.
4. `authorized_edges` reaches the Compiler (an authorized pair is rejected as "would not have blocked").
5. `DuplicateKeyError` on save: no crash, no supersede, no link.
6. `run` with a fake stream: processes a valid event, survives a malformed one, and exits when `stop` is set.

Set `OPENROUTER_API_KEY` off in the tests (`monkeypatch.delenv`), so the deterministic mock Architect is used.

### Live database test (`tests/test_incident_watcher_integration.py`, opt-in)

Marked `integration` and skipped unless `MONGODB_TEST_URI` is set (same convention as Person B's `tests/test_integration.py`). It uses its own random database `immune_test_<uuid>` and always drops it in `finally`.

    MONGODB_TEST_URI=<atlas uri> uv run pytest tests/test_incident_watcher_integration.py -q

Flow, using the real `Atlas`, the real change stream and the real `PolicyCache`:
1. `atlas.bootstrap()`, then start `run(AtlasWatcherStore(atlas), stop=...)` on a daemon thread and wait 3 s for the stream to open.
2. Insert 20 benign ledger rows, `alpha write_file /tmp/shared-note.txt` (5 s ago), then an incident for `beta read_file /tmp/shared-note.txt`.
3. Wait (up to 20 s each) for `p_tmp_channel` v1 `active` and for the incident's `policy_id` to be `p_tmp_channel`.
4. Insert `alpha write_file /var/tmp/x` and an incident for `gamma read_file /var/tmp/x`.
5. Wait for v2 `active` and v1 `superseded`. Assert v2 globs are `{"/tmp/*", "/var/tmp/*"}`.
6. Open a `PolicyCache`. Assert only v2 of `p_tmp_channel` is in its active snapshot.
7. Stop the watcher and drop the database.

Requirements: the cluster is reachable (Atlas IP access list, cluster not paused, port 27017 open) and the database user can create databases and open change streams.

Caveat: Person A's `tests/test_gateway.py::test_live_atlas_store_roundtrip` runs whenever `MONGODB_URI` is set, including from `.env` (`tests/conftest.py` calls `load_dotenv()`). If the cluster isn't reachable, that test fails with `ServerSelectionTimeoutError`. That is a connectivity failure, not a bug in the watcher. This D test is separate on purpose: it needs `MONGODB_TEST_URI`, so it never runs by accident.

## Manual acceptance (live Atlas, use a throwaway `MONGODB_DB=d_test`)

1. `python -m db.atlas check`, then `bootstrap`.
2. Start the watcher. Expect `watching security_incidents`.
3. Insert 20 benign ledger rows, one `alpha write_file /tmp/shared-note.txt` (allowed, a few seconds ago), and an incident for `beta read_file /tmp/shared-note.txt`. Expect `p_tmp_channel v1 active` and the incident's `policy_id` set.
4. Repeat for `/var/tmp/x` (alpha writes, gamma reads). Expect v2 active, v1 `superseded`, globs `/tmp/*` and `/var/tmp/*`.
5. `PolicyCache(atlas.security_policies).start().get_policies()` returns `p_tmp_channel` v2.
6. Drop `d_test`.

The same flow is automated in `tests/test_incident_watcher_integration.py` (see above).

## Definition of done

- `uv run pytest -q` passes with the six watcher tests (the live one skips).
- `tests/test_incident_watcher_integration.py` passes against a real cluster. Not yet run as of writing: the author's machine couldn't reach Atlas. The manual acceptance steps below cover the same flow.
- `PersonD.md` "Incident watcher" section and Known gaps match the implementation.
