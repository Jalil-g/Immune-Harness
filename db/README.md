# db/ — Atlas layer (Person B)

Shared schemas, Atlas storage, baseline policies, and a live in-memory policy cache.
The original project scope is preserved in [ARCHITECTURE.md](../ARCHITECTURE.md).
Python 3.11+ is required. Teams A, C, and D own the gateway, matchers, tools,
Architect, Compiler, and dashboard; those components are not implemented here.

## Setup

```sh
uv sync
cp .env.example .env
```

In Atlas, create/select a cluster, create a database user with `readWrite` on
`immune_harness`, and allow your development machine's IP in Network Access.
Copy the Python driver connection string into `MONGODB_URI` in `.env` and replace
the placeholders. Percent-encode special characters in the password. The `.env`
file is ignored by Git. Set `MONGODB_DB` if using a different database name and
grant the user access to that database. Cloud provisioning requires your Atlas
account; the bootstrap command creates the collections and indexes inside it.

```sh
uv run python -m db.atlas bootstrap
uv run python -m db.atlas check
```

`bootstrap` creates indexes and inserts two permanent baseline policies: deny
file reads/writes under SSH directories and `/etc`. Re-running it preserves
existing policies, versions, and statuses. `check` verifies connectivity and
permission to open the policy change stream. Neither command prints the URI.
The same commands are available as `uv run immune-db bootstrap` and `uv run immune-db check`.

Use Atlas or a replica set for change streams; standalone MongoDB is insufficient.
See MongoDB's [change stream documentation](https://www.mongodb.com/docs/manual/changestreams/)
and [PyMongo guide](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/monitoring-and-logging/change-streams/).

## Shared contracts

Import `Action`, `Decision`, `Policy`, `LedgerEntry`, and `Incident` from
`db.schemas`. Models reject unknown fields. Tools, decisions, policy effects,
statuses, and conditions are fixed enums. Scores must be finite and in `[0, 1]`;
latency must be finite and nonnegative. All timestamps must include a timezone
and are normalized to UTC. `Action.ts` defaults to the current UTC time.

Use `model_dump(mode="json")` / `model_dump_json()` for HTTP and LLM JSON.
Use **`to_mongo()` for database writes** to preserve BSON dates; ISO strings do
not work with TTL indexes. Read database documents using `Model.from_mongo(doc)`,
which strips MongoDB's `_id` and validates the remaining fields. The client uses
timezone-aware date decoding.

The additions below settle fields missing from the architecture for implementation;
share them with A and D before integration:

| Contract | Representation |
| --- | --- |
| Policy lifecycle | `draft` (default), `active`, `superseded`; effect always `deny` |
| Version | Positive integer; unique `(policy_id, version)` in MongoDB |
| Expiration | Optional `expires_at`; `None` means no expiration |
| Source incident | Optional `source_incident`; baseline policies have none |
| Ledger | Flat Action + Decision fields plus generated `action_id`, so `target` and `ts` are at the top level |
| Incident | Generated `incident_id`, nested `action`, nested `decision`, ledger `context`, `ts`, nullable resulting `policy_id` |
| Risk/latency | On `Decision`, and thus each ledger entry; incident retains the whole decision |

Policy `tool` and `target_glob` serialize as arrays. Python instances expose
immutable tuples; policy instances are frozen so callers cannot alter the cache.
Use `Policy.model_json_schema()` for D's structured-output schema. Pydantic
validation is necessary but not sufficient: D still owns breadth checks,
false-positive replay, and activation approval.

### Condition semantics for A and D

All matchers first check the action's tool and logical target against the policy's
tool list and any `target_glob`. Use case-sensitive glob semantics (for example,
`fnmatch.fnmatchcase`) consistently in Sentry and Compiler replay. A/C must agree
on target normalization; baseline globs alone do not resolve `..`, symlinks, URL
encoding, or inspect a shell command's arguments. Tool execution remains in C's
sandbox.

| Condition | Parameters and proposed matching contract |
| --- | --- |
| `always` | No additional condition |
| `resource_touched_by_other_agent` | Required positive `window_s`; at least one earlier allowed action on the same target by another agent within the window |
| `rate_exceeds` | Required positive `window_s` and `rate_limit`; count earlier allowed actions by the same agent, tool, and exact target within the window, add the proposed action, and block if greater than `rate_limit` |
| `unauthorized_recipient` | Only valid for `send_message`; the `(agent_id, target)` edge is absent from C's authorized-edge config |

Window comparisons use the proposed action's `ts`: include rows at or after
`action.ts - window_s` and no later than `action.ts`. Exclude the current proposal
if it has already been persisted. Cache loading does not evaluate these conditions.
`rate_limit` is rejected for other conditions; `window_s` may be present but is
ignored by conditions without a time window.

## Team A: cache and persistence

Create one `Atlas` and one `PolicyCache` per gateway process. The client is shared
and thread safe. The cache starts its own watcher thread; request-time reads use
only a lock, immutable tuples, and a timestamp comparison.

```python
from db.atlas import Atlas
from db.schemas import Action, Decision, Incident, LedgerEntry
from harness.policy_cache import PolicyCache, PolicyCacheUnavailable

with Atlas() as atlas:
    with PolicyCache(atlas.security_policies) as cache:
        action = Action(agent_id="beta", tool="read_file", target="/tmp/shared-note.txt")
        try:
            policies = cache.get_policies()
        except PolicyCacheUnavailable:
            # Gateway must block/return 503. Do not run the proposed tool.
            raise
        # Sentry matches policies, then calls Jev on a miss, and produces a Decision.
        decision = Decision(
            decision="block", reason="Example Jev result", risk_score=0.95, latency_ms=20
        )
        row = LedgerEntry.from_action(action, decision)
        atlas.action_ledger.insert_one(row.to_mongo())
        if decision.decision == "block":
            incident = Incident(action=action, decision=decision, context=[])
            atlas.security_incidents.insert_one(incident.to_mongo())
```

For an async FastAPI lifespan, call `await asyncio.to_thread(cache.start)` before
yielding, and `await asyncio.to_thread(cache.stop)` during shutdown, then close
Atlas. Synchronous database writes/queries also need `asyncio.to_thread` or a sync
route; `cache.get_policies()` can be called directly. Ensure shutdown runs in
`finally` even if startup fails. Run bootstrap once before starting the gateway.

Recent Jev context uses a bounded query against the `(target, ts)` index:

```python
from datetime import timedelta

rows = list(
    atlas.action_ledger.find(
        {
            "target": action.target,
            "ts": {"$gte": action.ts - timedelta(seconds=600), "$lte": action.ts},
        }
    )
    .sort("ts", -1)
    .limit(50)
)
context = [LedgerEntry.from_mongo(row) for row in rows]
```

This context includes allowed and blocked proposals as the architecture specifies;
condition matchers separately filter to allowed rows per the contract above.

### Cache guarantees and limits

- The watcher opens **before** the first scan, so writes during loading are queued.
- Inserts, updates, replacements, deletes, and TTL deletions trigger a full refresh.
  This favors simple correctness for the demo's small policy collection.
- Each refresh validates a complete snapshot before swapping it under a lock.
  If multiple versions are temporarily active, only the highest version per ID is
  returned. Expiry never resurrects an older active version.
- Expiration is checked on every local read. MongoDB's asynchronous TTL cleanup
  can lag; it is storage cleanup, not the policy expiration clock.
- On stream failure or an invalid active policy, reads raise
  `PolicyCacheUnavailable`. Recovery opens a new stream and reloads the full
  collection, including changes made during the outage. A periodic 30-second
  refresh also reconciles state. No resume-token persistence is needed because
  the cache reconstructs state rather than processing every event exactly once.
- Updates propagate asynchronously; this is not a linearizable authorization
  service. A network outage is detected on driver failure/timeout, not instantly.
  `healthy` and `last_error` are available for gateway health reporting.
- A legitimately empty active-policy collection is a valid empty cache. Bootstrap
  establishes baseline rules; D is responsible for controlled lifecycle changes.

`stop()` waits for the watcher and closes its cursor. The default client socket
timeout bounds stalled calls; if shutdown times out it raises, and the owner
should close the client. Do not start/stop the same cache from multiple owners.

## Team D: versioning and activation

The database enforces unique `(policy_id, version)`. D chooses the next version,
validates the candidate, replays allowed ledger rows, and publishes it. Supersede
old versions and insert the new active version in **one transaction**:

```python
active = Policy.model_validate({**candidate.model_dump(), "status": "active"})
with atlas.client.start_session() as session:
    with session.start_transaction():
        atlas.security_policies.update_many(
            {"policy_id": active.policy_id, "status": "active"},
            {"$set": {"status": "superseded"}},
            session=session,
        )
        atlas.security_policies.insert_one(active.to_mongo(), session=session)
        if active.source_incident:
            atlas.security_incidents.update_one(
                {"incident_id": active.source_incident},
                {"$set": {"policy_id": active.policy_id}},
                session=session,
            )
```

Handle duplicate-version and transaction conflicts by re-reading and retrying
the publication workflow; don't silently overwrite an existing version. This
example assumes drafts live in memory. If D persists draft documents, promote
the existing draft with a validated update in the same transaction instead of
inserting the same `(policy_id, version)` twice. Architect's incident watcher
should consume **insert events**, so updating `policy_id` does not re-trigger it.

## Collections and retention

| Collection | Indexes |
| --- | --- |
| `security_policies` | Unique `(policy_id, version)`, `status`, TTL `expires_at` with `expireAfterSeconds=0` |
| `action_ledger` | Unique `action_id`, `(target, ts desc)`, `(decision, ts desc)`, TTL `ts` (7 days by default) |
| `security_incidents` | Unique `incident_id`, `ts desc`; retained indefinitely for the demo |

Superseded policies retain their document until its `expires_at` deadline, if any.
Use no expiry if history must be retained indefinitely, or archive it separately.
Changing `LEDGER_TTL_SECONDS` after indexes exist requires an explicit `collMod`
migration; bootstrap does not silently shorten retention. Details:
[MongoDB TTL indexes](https://www.mongodb.com/docs/manual/core/index-ttl/).

## Verification

For a visible demonstration against the database in `.env`, run:

```sh
python scripts/live_demo.py
```

It bootstraps the database, starts the cache, inserts a uniquely named policy on
a synthetic target, publishes v2 in a transaction, and reports propagation and
cache-read timings. It retires only its own demo policy afterward; those documents
expire after ten minutes. It does not call Jev, execute tools, or create incidents.
This tests B's live behavior, not the full agent/gateway workflow.

Without an Atlas connection, `python scripts/run_local_integration.py --demo`
runs the same demonstration against a temporary local replica set.

```sh
uv run pytest -q
ruff check .
ruff format --check .
```

Offline tests cover contracts, BSON round trips, seed/index configuration,
version selection, expiration, startup races, invalid policies, reconnection,
invalidation, shutdown, and periodic refresh. The real integration test is skipped
unless `MONGODB_TEST_URI` is exported in the shell (pytest does not load `.env`).
It uses a random `immune_test_*` database and deletes only that database afterward.
Its database user must have permission to create/drop that test database and its
collections; the normal app user's single-database role is intentionally narrower.

If `mongod` is installed locally:

```sh
python scripts/run_local_integration.py
```

This starts an isolated replica set on a free loopback port, runs the real
integration test, stops the server, and removes its temporary data directory.
It does not use an existing MongoDB service. Alternatively, export an Atlas test
URI as `MONGODB_TEST_URI` and run `uv run pytest -q -m integration`.
