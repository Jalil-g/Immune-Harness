import copy
import queue
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from pymongo.errors import AutoReconnect

from db.schemas import Policy
from harness.policy_cache import PolicyCache, PolicyCacheUnavailable


def document(policy_id="p1", **changes):
    return Policy.model_validate(
        {
            "policy_id": policy_id,
            "status": "active",
            "tool": ["read_file"],
            "target_glob": ["/tmp/*"],
            "rationale": "test",
            **changes,
        }
    ).to_mongo()


class FakeStream:
    def __init__(self):
        self.events = queue.Queue()
        self.alive = True
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def try_next(self):
        try:
            event = self.events.get(timeout=0.005)
        except queue.Empty:
            return None
        if isinstance(event, Exception):
            raise event
        if event.get("operationType") == "invalidate":
            self.alive = False
        return event


class FakeCollection:
    def __init__(self, docs=()):
        self.docs = list(docs)
        self.streams = []
        self.calls = []
        self.watch_error = None
        self.find_hook = None

    def watch(self, **kwargs):
        self.calls.append("watch")
        if self.watch_error:
            raise self.watch_error
        stream = FakeStream()
        self.streams.append(stream)
        return stream

    def find(self, query):
        self.calls.append("find")
        assert query == {"status": "active"}
        docs = copy.deepcopy([d for d in self.docs if d["status"] == "active"])
        if self.find_hook:
            hook, self.find_hook = self.find_hook, None
            hook()
        return docs

    def emit(self, kind="insert"):
        self.streams[-1].events.put({"operationType": kind})


def eventually(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Condition did not become true")


@pytest.fixture
def running_cache():
    collection = FakeCollection([document()])
    cache = PolicyCache(collection, retry_seconds=0.02)
    cache.start(timeout=1)
    yield collection, cache
    cache.stop(timeout=1)


def test_watch_opens_before_snapshot_and_reads_never_query(running_cache):
    collection, cache = running_cache
    assert collection.calls[:2] == ["watch", "find"]
    reads = collection.calls.count("find")
    for _ in range(100):
        assert cache.get_policies()[0].policy_id == "p1"
    assert collection.calls.count("find") == reads


@pytest.mark.parametrize("kind", ["insert", "update", "replace", "delete"])
def test_all_change_types_refresh_snapshot(running_cache, kind):
    collection, cache = running_cache
    collection.docs = [] if kind == "delete" else [document("p2")]
    collection.emit(kind)
    expected = [] if kind == "delete" else ["p2"]
    eventually(lambda: [p.policy_id for p in cache.get_policies()] == expected)


def test_superseded_versions_are_removed_and_highest_active_wins(running_cache):
    collection, cache = running_cache
    collection.docs = [
        document(version=2),
        document(version=1),
        document("superseded", status="superseded"),
    ]
    collection.emit("update")
    eventually(lambda: cache.get_policies()[0].version == 2)
    assert len(cache.get_policies()) == 1


def test_expiry_does_not_wait_for_ttl_or_revive_older_version():
    now = datetime.now(UTC)
    collection = FakeCollection(
        [
            document(version=1),
            document(version=2, expires_at=now + timedelta(seconds=10)),
        ]
    )
    with PolicyCache(collection) as cache:
        assert cache.get_policies(now=now)[0].version == 2
        assert cache.get_policies(now=now + timedelta(seconds=10)) == ()
        with pytest.raises(ValueError):
            cache.get_policies(now=datetime(2026, 1, 1))


def test_write_during_initial_scan_is_not_lost():
    collection = FakeCollection([document()])

    def write_during_scan():
        collection.docs = [document("new")]
        collection.emit()

    collection.find_hook = write_during_scan
    with PolicyCache(collection) as cache:
        eventually(lambda: cache.get_policies()[0].policy_id == "new")


def test_disconnect_fails_closed_then_rescans_changes_during_outage(running_cache):
    collection, cache = running_cache
    collection.watch_error = AutoReconnect("offline")
    collection.streams[-1].events.put(AutoReconnect("lost connection"))
    eventually(lambda: not cache.healthy)
    with pytest.raises(PolicyCacheUnavailable):
        cache.get_policies()
    assert cache.last_error == "AutoReconnect"
    collection.docs = [document("written_while_offline")]
    collection.watch_error = None
    eventually(lambda: cache.healthy)
    assert cache.get_policies()[0].policy_id == "written_while_offline"


def test_invalid_active_policy_fails_closed_and_recovers(running_cache):
    collection, cache = running_cache
    collection.docs = [{**document(), "condition": "run_arbitrary_code"}]
    collection.emit()
    eventually(lambda: not cache.healthy)
    with pytest.raises(PolicyCacheUnavailable):
        cache.get_policies()
    collection.docs = [document("fixed")]
    eventually(lambda: cache.healthy)
    assert cache.get_policies()[0].policy_id == "fixed"


def test_invalidation_reopens_stream(running_cache):
    collection, cache = running_cache
    collection.emit("invalidate")
    eventually(lambda: len(collection.streams) >= 2 and cache.healthy)
    assert collection.streams[0].closed


def test_periodic_refresh_repairs_missed_notification():
    collection = FakeCollection([document()])
    with PolicyCache(collection, refresh_seconds=0.02) as cache:
        collection.docs = [document("new")]
        eventually(lambda: cache.get_policies()[0].policy_id == "new")


def test_start_failure_stops_thread_and_never_exposes_empty_cache():
    collection = FakeCollection()
    collection.watch_error = AutoReconnect("offline")
    cache = PolicyCache(collection, retry_seconds=0.01)
    with pytest.raises(PolicyCacheUnavailable):
        cache.get_policies()
    with pytest.raises(PolicyCacheUnavailable):
        cache.start(timeout=0.03)
    assert cache._thread is None


def test_stop_during_reload_cannot_mark_cache_healthy_again():
    collection = FakeCollection([document()])
    entered, release = threading.Event(), threading.Event()

    def slow_reload():
        entered.set()
        assert release.wait(2)

    cache = PolicyCache(collection)
    cache.start(timeout=1)
    collection.find_hook = slow_reload
    collection.emit()
    assert entered.wait(1)
    with pytest.raises(TimeoutError):
        cache.stop(timeout=0.01)
    release.set()
    cache.stop(timeout=1)
    assert not cache.healthy


def test_start_stop_restart_and_empty_collection():
    collection = FakeCollection()
    cache = PolicyCache(collection)
    cache.start(timeout=1)
    cache.start(timeout=1)
    assert len(collection.streams) == 1
    assert cache.get_policies() == ()
    cache.stop(timeout=1)
    assert collection.streams[0].closed
    with pytest.raises(PolicyCacheUnavailable):
        cache.get_policies()
    cache.start(timeout=1)
    assert len(collection.streams) == 2
    cache.stop(timeout=1)
