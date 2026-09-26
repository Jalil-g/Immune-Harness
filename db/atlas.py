"""Atlas client, collection indexes, and idempotent baseline bootstrap.

Run `python -m db.atlas bootstrap` after configuring .env.
Importing this module never connects to MongoDB.
"""

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, IndexModel, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from db.schemas import Policy


@dataclass(frozen=True, repr=False)
class AtlasSettings:
    uri: str
    database: str = "immune_harness"
    ledger_ttl_seconds: int = 604800
    timeout_ms: int = 5000

    def __post_init__(self) -> None:
        if not self.uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URI must be a mongodb:// or mongodb+srv:// URI")
        if not self.database or any(char in self.database for char in '/\\. "$*<>:|?\x00'):
            raise ValueError("MONGODB_DB must be a valid nonempty database name")
        if not 0 < self.ledger_ttl_seconds <= 2147483647:
            raise ValueError("LEDGER_TTL_SECONDS must be in 1..2147483647")
        if self.timeout_ms < 2000:
            raise ValueError("MONGODB_TIMEOUT_MS must be at least 2000")

    @classmethod
    def from_env(cls) -> Self:
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
        return cls(
            uri=os.environ.get("MONGODB_URI", ""),
            database=os.environ.get("MONGODB_DB", "immune_harness"),
            ledger_ttl_seconds=int(os.environ.get("LEDGER_TTL_SECONDS", "604800")),
            timeout_ms=int(os.environ.get("MONGODB_TIMEOUT_MS", "5000")),
        )


def baseline_policies() -> tuple[Policy, ...]:
    """Permanent demo guardrails. Logical targets are sandbox paths, never real I/O."""
    return (
        Policy(
            policy_id="p_baseline_ssh",
            status="active",
            tool=("read_file", "write_file"),
            target_glob=(
                "~/.ssh",
                "~/.ssh/*",
                "/home/*/.ssh",
                "/home/*/.ssh/*",
                "/Users/*/.ssh",
                "/Users/*/.ssh/*",
                "/root/.ssh",
                "/root/.ssh/*",
            ),
            rationale="Deny access to SSH credentials and configuration.",
        ),
        Policy(
            policy_id="p_baseline_etc",
            status="active",
            tool=("read_file", "write_file"),
            target_glob=("/etc", "/etc/*", "/private/etc", "/private/etc/*"),
            rationale="Deny access to system configuration paths.",
        ),
    )


class Atlas:
    def __init__(self, settings: AtlasSettings | None = None) -> None:
        self.settings = settings or AtlasSettings.from_env()
        self.client: MongoClient[dict[str, Any]] = MongoClient(
            self.settings.uri,
            appname="immune-harness",
            tz_aware=True,
            serverSelectionTimeoutMS=self.settings.timeout_ms,
            connectTimeoutMS=self.settings.timeout_ms,
            socketTimeoutMS=self.settings.timeout_ms,
            waitQueueTimeoutMS=self.settings.timeout_ms,
            retryWrites=True,
        )
        self.db: Database[dict[str, Any]] = self.client.get_database(
            self.settings.database,
            read_concern=ReadConcern("majority"),
            write_concern=WriteConcern("majority", wtimeout=self.settings.timeout_ms),
        )
        self.security_policies: Collection = self.db["security_policies"]
        self.action_ledger: Collection = self.db["action_ledger"]
        self.security_incidents: Collection = self.db["security_incidents"]

    def ping(self) -> None:
        self.client.admin.command("ping")

    def ensure_indexes(self) -> None:
        # create_indexes also creates absent collections. Re-running with the same
        # options is safe; changed TTL settings require an explicit migration.
        self.security_policies.create_indexes(
            [
                IndexModel(
                    [("policy_id", ASCENDING), ("version", ASCENDING)],
                    unique=True,
                    name="policy_version_unique",
                ),
                IndexModel([("status", ASCENDING)], name="policy_status"),
                IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="policy_expiry"),
            ]
        )
        self.action_ledger.create_indexes(
            [
                IndexModel([("action_id", ASCENDING)], unique=True, name="action_id_unique"),
                IndexModel([("target", ASCENDING), ("ts", DESCENDING)], name="target_recent"),
                IndexModel([("decision", ASCENDING), ("ts", DESCENDING)], name="decision_recent"),
                IndexModel(
                    [("ts", ASCENDING)],
                    expireAfterSeconds=self.settings.ledger_ttl_seconds,
                    name="ledger_retention",
                ),
            ]
        )
        self.security_incidents.create_indexes(
            [
                IndexModel([("incident_id", ASCENDING)], unique=True, name="incident_id_unique"),
                IndexModel([("ts", DESCENDING)], name="incident_recent"),
            ]
        )

    def seed_baselines(self) -> int:
        inserted = 0
        for policy in baseline_policies():
            try:
                result = self.security_policies.update_one(
                    {"policy_id": policy.policy_id},
                    {"$setOnInsert": policy.to_mongo()},
                    upsert=True,
                )
                inserted += int(result.upserted_id is not None)
            except DuplicateKeyError:
                # A concurrent bootstrap may have inserted this version first.
                if self.security_policies.find_one({"policy_id": policy.policy_id}) is None:
                    raise
        return inserted

    def bootstrap(self) -> int:
        self.ping()
        self.ensure_indexes()
        return self.seed_baselines()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bootstrap", "check"))
    args = parser.parse_args()
    try:
        with Atlas() as atlas:
            if args.command == "bootstrap":
                inserted = atlas.bootstrap()
                print(f"Atlas ready: {atlas.settings.database}; {inserted} baselines inserted")
            else:
                atlas.ping()
                # Opening the stream verifies permissions and replica-set support.
                with atlas.security_policies.watch(max_await_time_ms=1000):
                    pass
                print(
                    f"Atlas reachable; policy change streams available: {atlas.settings.database}"
                )
    except (ValueError, PyMongoError) as exc:
        # Driver exception messages can contain connection details; do not print them.
        parser.exit(
            1,
            f"Atlas setup failed ({type(exc).__name__}). "
            "Check .env, Atlas database-user permissions, and network access.\n",
        )


if __name__ == "__main__":
    main()
