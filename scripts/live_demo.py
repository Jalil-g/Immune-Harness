"""Show B's live policy propagation using the database configured in .env.

Creates one uniquely named test policy, versions it, then retires its versions.
Does not execute tools, generate incidents, or call an LLM.
"""

import sys
import time
from datetime import timedelta
from uuid import uuid4

from pymongo.errors import PyMongoError

from db.atlas import Atlas
from db.schemas import Policy, utc_now
from harness.policy_cache import PolicyCache, PolicyCacheUnavailable


def wait_for_version(cache: PolicyCache, policy_id: str, version: int | None) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if cache.healthy:
            current = next((p for p in cache.get_policies() if p.policy_id == policy_id), None)
            if (version is None and current is None) or (
                current is not None and current.version == version
            ):
                return
        time.sleep(0.01)
    raise TimeoutError("Policy change did not reach the cache within 15 seconds")


def run_demo(atlas: Atlas) -> None:
    inserted = atlas.bootstrap()
    print(
        f"Connected to {atlas.settings.database}; {inserted} baseline policies seeded", flush=True
    )
    run_id = uuid4().hex
    policy = Policy(
        policy_id=f"p_live_demo_{run_id}",
        status="active",
        tool=["read_file"],
        target_glob=[f"/__immune_live_demo__/{run_id}/tmp/*"],
        expires_at=utc_now() + timedelta(minutes=10),
        rationale="Team B live connectivity test; synthetic target only",
    )
    with PolicyCache(atlas.security_policies) as cache:
        print(f"Cache ready: {len(cache.get_policies())} active policies", flush=True)
        try:
            start = time.perf_counter()
            atlas.security_policies.insert_one(policy.to_mongo())
            wait_for_version(cache, policy.policy_id, 1)
            print(
                f"PASS v1 appeared in cache ({(time.perf_counter() - start) * 1000:.1f} ms)",
                flush=True,
            )

            v2 = Policy.model_validate(
                {
                    **policy.model_dump(),
                    "version": 2,
                    "target_glob": [
                        *policy.target_glob,
                        f"/__immune_live_demo__/{run_id}/var/tmp/*",
                    ],
                }
            )
            start = time.perf_counter()
            with atlas.client.start_session() as session, session.start_transaction():
                atlas.security_policies.update_one(
                    {"policy_id": policy.policy_id, "version": 1},
                    {"$set": {"status": "superseded"}},
                    session=session,
                )
                atlas.security_policies.insert_one(v2.to_mongo(), session=session)
            wait_for_version(cache, policy.policy_id, 2)
            cached = next(p for p in cache.get_policies() if p.policy_id == policy.policy_id)
            if cached.target_glob != v2.target_glob:
                raise AssertionError("Version updated without the new target patterns")
            print(
                f"PASS v2 replaced v1 without restart "
                f"({(time.perf_counter() - start) * 1000:.1f} ms)",
                flush=True,
            )

            start = time.perf_counter()
            for _ in range(10000):
                cache.get_policies()
            average_ms = (time.perf_counter() - start) * 1000 / 10000
            print(f"Cache snapshot read: {average_ms:.4f} ms average over 10,000 reads", flush=True)
        finally:
            print("Retiring the temporary demo policy in Atlas...", flush=True)
            atlas.security_policies.update_many(
                {"policy_id": policy.policy_id}, {"$set": {"status": "superseded"}}
            )
        print(
            "Policy retired in Atlas; waiting for the cache to confirm (up to 15s)...", flush=True
        )
        wait_for_version(cache, policy.policy_id, None)
        print("PASS demo policy retired and removed from active cache", flush=True)
    print(
        "B live demo complete. Timings cover database propagation and cache reads, "
        "not Sentry decisions.",
        flush=True,
    )


def main() -> int:
    try:
        with Atlas() as atlas:
            run_demo(atlas)
    except KeyboardInterrupt:
        print(
            "\nDemo interrupted. Any temporary demo policy still active expires within "
            "10 minutes. You can rerun the demo safely.",
            file=sys.stderr,
        )
        return 130
    except (ValueError, PyMongoError, PolicyCacheUnavailable, TimeoutError) as exc:
        print(
            f"Live demo failed ({type(exc).__name__}). Check .env, database permissions, "
            "Atlas Network Access, and cluster availability.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
