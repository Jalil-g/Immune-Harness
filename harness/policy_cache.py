"""In-memory active-policy snapshots, refreshed by a background change stream.

No policy matching belongs here: Sentry owns condition evaluation. All reads are
local. Invalid documents or a broken stream make reads fail closed until recovery.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Self

from pymongo.collection import Collection

from db.schemas import Policy, utc_now

logger = logging.getLogger(__name__)


class PolicyCacheUnavailable(RuntimeError):
    """Gateway must block/return 503; never interpret this as no matching policies."""


class PolicyCache:
    def __init__(
        self,
        collection: Collection,
        *,
        retry_seconds: float = 1.0,
        refresh_seconds: float = 30.0,
        max_await_time_ms: int = 1000,
    ) -> None:
        if retry_seconds <= 0 or refresh_seconds <= 0 or max_await_time_ms <= 0:
            raise ValueError("Cache intervals must be positive")
        self.collection = collection
        self.retry_seconds = retry_seconds
        self.refresh_seconds = refresh_seconds
        self.max_await_time_ms = max_await_time_ms
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._policies: tuple[Policy, ...] = ()
        self._healthy = False
        self._last_error: str | None = None

    @property
    def healthy(self) -> bool:
        with self._lock:
            return self._healthy

    @property
    def last_error(self) -> str | None:
        """Exception class only, so credentials/document contents never leak."""
        with self._lock:
            return self._last_error

    def get_policies(self, *, now: datetime | None = None) -> tuple[Policy, ...]:
        """Return an immutable snapshot; expired policies disappear without TTL lag."""
        now = now or utc_now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        with self._lock:
            if not self._healthy:
                raise PolicyCacheUnavailable("Policy cache is not ready; block evaluation")
            snapshot = self._policies
        return tuple(p for p in snapshot if p.expires_at is None or p.expires_at > now)

    def start(self, *, timeout: float = 15.0) -> Self:
        """Wait for an initial validated snapshot or raise; start before serving traffic.

        Call lifecycle methods from one owner (e.g. FastAPI lifespan).
        """
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._ready.clear()
            self._thread = threading.Thread(target=self._run, name="policy-cache", daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout) or not self.healthy:
            self.stop()
            raise PolicyCacheUnavailable(
                "Could not load active policies and open their change stream"
            )
        return self

    def stop(self, *, timeout: float = 15.0) -> None:
        self._stop.set()
        self._mark_unavailable(None)
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise TimeoutError("Policy cache watcher did not stop; close the Atlas client")
            self._thread = None

    def _mark_unavailable(self, error: str | None) -> None:
        with self._lock:
            self._healthy = False
            self._last_error = error
            self._ready.clear()

    def _reload(self) -> None:
        # Build off-lock; readers see the whole previous or whole next snapshot.
        latest: dict[str, Policy] = {}
        for document in self.collection.find({"status": "active"}):
            policy = Policy.from_mongo(document)
            previous = latest.get(policy.policy_id)
            if previous is None or policy.version > previous.version:
                latest[policy.policy_id] = policy
        snapshot = tuple(latest[key] for key in sorted(latest))
        with self._lock:
            if not self._stop.is_set():
                self._policies = snapshot
                self._healthy = True
                self._last_error = None
                self._ready.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                # Watch FIRST, then read: writes during the scan are queued.
                # On reconnect, open a NEW stream and rescan. This is state
                # synchronization, not an event consumer needing persisted tokens.
                with self.collection.watch(max_await_time_ms=self.max_await_time_ms) as stream:
                    self._reload()
                    refreshed_at = time.monotonic()
                    while not self._stop.is_set():
                        event = stream.try_next()
                        if not stream.alive:
                            raise PolicyCacheUnavailable("Policy stream was invalidated")
                        # Never filter to active inserts: deletes, replacements,
                        # and superseding old versions also change the snapshot.
                        if (
                            event is not None
                            or time.monotonic() - refreshed_at >= self.refresh_seconds
                        ):
                            self._reload()
                            refreshed_at = time.monotonic()
            except Exception as exc:
                self._mark_unavailable(type(exc).__name__)
                if not self._stop.is_set():
                    logger.warning("Policy cache unavailable (%s); retrying", type(exc).__name__)
                    self._stop.wait(self.retry_seconds)
        self._mark_unavailable(None)

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()
