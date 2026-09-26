from unittest.mock import MagicMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

from db.atlas import Atlas, AtlasSettings


@pytest.fixture
def atlas():
    with patch("db.atlas.MongoClient"):
        with Atlas(AtlasSettings(uri="mongodb://localhost:27017")) as value:
            yield value


def test_client_uses_timezone_aware_dates_and_bounded_timeouts():
    with patch("db.atlas.MongoClient") as client:
        with Atlas(AtlasSettings(uri="mongodb://localhost:27017")):
            kwargs = client.call_args.kwargs
            assert kwargs["tz_aware"] is True
            assert kwargs["socketTimeoutMS"] == 5000
            assert kwargs["serverSelectionTimeoutMS"] == 5000
        client.return_value.close.assert_called_once()


def test_collection_names_and_indexes(atlas):
    atlas.security_policies = MagicMock()
    atlas.action_ledger = MagicMock()
    atlas.security_incidents = MagicMock()
    atlas.ensure_indexes()
    policy = {
        i.document["name"]: i.document
        for i in atlas.security_policies.create_indexes.call_args.args[0]
    }
    ledger = {
        i.document["name"]: i.document for i in atlas.action_ledger.create_indexes.call_args.args[0]
    }
    assert policy["policy_version_unique"]["unique"] is True
    assert policy["policy_expiry"]["expireAfterSeconds"] == 0
    assert list(ledger["target_recent"]["key"].items()) == [("target", 1), ("ts", -1)]
    assert ledger["ledger_retention"]["expireAfterSeconds"] == 604800
    atlas.security_incidents.create_indexes.assert_called_once()


def test_seed_never_overwrites_existing_versions(atlas):
    atlas.security_policies.update_one.return_value.upserted_id = None
    assert atlas.seed_baselines() == 0
    for call in atlas.security_policies.update_one.call_args_list:
        assert set(call.args[0]) == {"policy_id"}
        assert set(call.args[1]) == {"$setOnInsert"}
        assert call.kwargs["upsert"] is True


def test_seed_concurrent_insert_is_idempotent(atlas):
    atlas.security_policies.update_one.side_effect = DuplicateKeyError("race")
    atlas.security_policies.find_one.return_value = {"policy_id": "existing"}
    assert atlas.seed_baselines() == 0
    atlas.security_policies.find_one.return_value = None
    with pytest.raises(DuplicateKeyError):
        atlas.seed_baselines()


@pytest.mark.parametrize(
    "changes",
    [
        {"uri": ""},
        {"uri": "https://example.com"},
        {"database": ""},
        {"database": "invalid.name"},
        {"ledger_ttl_seconds": 0},
        {"timeout_ms": 100},
    ],
)
def test_invalid_settings(changes):
    with pytest.raises(ValueError):
        AtlasSettings(**{"uri": "mongodb://localhost:27017", **changes})


def test_settings_do_not_expose_connection_string():
    assert "secret" not in repr(AtlasSettings(uri="mongodb://user:secret@localhost"))
