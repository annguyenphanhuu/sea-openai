from dataclasses import replace
import sqlite3

import pytest

from care_truc.store import MemoryStore
from care_truc.runtime_types import (CustomerEvent, PendingCancellation, PolicyOutcome,
    SessionState, TurnResult, fingerprint)
from .helpers import NOW


def setup_turn(path):
    store = MemoryStore.open(path)
    state = SessionState("s", "run", "customer", "o1")
    store.create_session(state, "open")
    event = CustomerEvent("message", "m", "why")
    request = store.begin_request("s", "customer", event, fingerprint(event))
    outcome = PolicyOutcome(replace(state, turn_count=1,
        pending=PendingCancellation("c", "m", NOW)), "ask_why", "explain")
    return store, request, outcome


def test_turn_commit_is_atomic(tmp_path):
    store, request, outcome = setup_turn(tmp_path / "care.sqlite")
    result = TurnResult("committed", "s", "answer")
    store.commit_turn(request["id"], 0, outcome, result, "{}", "{}")
    assert store.load_session("s").turn_count == 1
    assert store.load_session("s").version == 1
    assert store.request(request["id"])["phase"] == "committed"
    assert len(store.events("s")) == 2
    assert store.response(store.request(request["id"])) == result
    store.close()


def test_commit_failure_rolls_back_everything(tmp_path):
    store, request, outcome = setup_turn(tmp_path / "care.sqlite")
    store.db.execute("CREATE TRIGGER fail_events BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
    with pytest.raises(sqlite3.DatabaseError):
        store.commit_turn(request["id"], 0, outcome, TurnResult("committed", "s"), "{}", "{}")
    assert store.load_session("s").turn_count == 0
    assert store.request(request["id"])["phase"] == "processing"
    assert store.events("s") == []
    assert store.db.execute("SELECT count(*) FROM evidence_bundles").fetchone()[0] == 0
    store.close()


def test_reopen_preserves_confirmation_and_events(tmp_path):
    path = tmp_path / "care.sqlite"
    store, request, outcome = setup_turn(path)
    store.commit_turn(request["id"], 0, outcome, TurnResult("committed", "s"), "{}", "{}")
    store.close()
    store = MemoryStore.open(path)
    assert store.load_session("s").pending.confirmation_id == "c"
    assert store.load_session("s").turn_count == 1
    assert len(store.events("s")) == 2
    store.close()


def test_corrupt_or_future_schema_is_not_reset(tmp_path):
    path = tmp_path / "bad.sqlite"
    path.write_bytes(b"corrupt database")
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        MemoryStore.open(path)
    assert path.read_bytes() == before
    path = tmp_path / "future.sqlite"
    store = MemoryStore.open(path)
    store.db.execute("UPDATE runtime_meta SET schema_version=999")
    store.close()
    before = path.read_bytes()
    with pytest.raises(ValueError, match="schema"):
        MemoryStore.open(path)
    assert path.read_bytes() == before
