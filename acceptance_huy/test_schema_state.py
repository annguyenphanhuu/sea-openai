"""Exercise persistence constraints using isolated in-memory state only."""

from pathlib import Path
from dataclasses import asdict
from datetime import datetime
import sqlite3
from typing import get_args

import pytest

from contracts import ALLOWED_SOURCES, Action, ActionKind, ActionSource


SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "schema_state.sql"
NOW = "2026-11-01T00:00:00.000000Z"


@pytest.fixture
def state():
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT INTO contact_log "
        "(contact_id, order_id, channel, initiated_by, requested_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("contact-1", "order-1", "chat", "A1", NOW),
    )
    yield connection
    connection.close()


def add_request(state, action_id, key, order_id="order-1"):
    action = Action(
        action_id=action_id,
        order_id=order_id,
        kind="coins",
        amount_vnd=10_000,
        source="a1",
        requested_at=datetime.fromisoformat(NOW),
        idempotency_key=key,
        evidence_ref="contact_log:contact-1",
        needs_approval=False,
        queue="care",
    )
    values = asdict(action)
    values["requested_at"] = NOW
    values["available_at"] = NOW
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    state.execute(
        f"INSERT INTO outbox ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def add_ledger_fixture(state, ledger_id, key, action_id, order_id="order-1", amount=10_000):
    state.execute(
        "INSERT INTO ledger_new "
        "(ledger_id, idempotency_key, order_id, action_id, contact_id, amount_xu, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ledger_id, key, order_id, action_id, "contact-1", amount, NOW),
    )


def test_schema_can_be_applied_again_without_erasing_state(state):
    state.executescript(SCHEMA.read_text(encoding="utf-8"))
    assert state.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0] == 1


def test_outbox_rejects_retry_with_same_key(state):
    add_request(state, "action-1", "same-key")
    with pytest.raises(sqlite3.IntegrityError, match="outbox.idempotency_key"):
        add_request(state, "action-2", "same-key")


def test_ledger_rejects_second_compensation_for_same_order(state):
    add_request(state, "action-1", "request-1")
    add_request(state, "action-2", "request-2")
    add_ledger_fixture(state, "ledger-1", "grant-1", "action-1")
    with pytest.raises(sqlite3.IntegrityError, match="ledger_new.order_id"):
        add_ledger_fixture(state, "ledger-2", "grant-2", "action-2")


def test_ledger_rejects_reused_key_across_orders(state):
    add_request(state, "action-1", "request-1")
    add_request(state, "action-2", "request-2", "order-2")
    add_ledger_fixture(state, "ledger-1", "same-key", "action-1")
    with pytest.raises(sqlite3.IntegrityError, match="ledger_new.idempotency_key"):
        add_ledger_fixture(state, "ledger-2", "same-key", "action-2", "order-2")


@pytest.mark.parametrize("amount", [9_000, 10_500, 10_000.5, 1_001_000])
def test_ledger_rejects_amount_outside_contract(state, amount):
    add_request(state, "action-1", "request-1")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_ledger_fixture(state, "ledger-1", "grant-1", "action-1", amount=amount)


def test_ledger_requires_an_existing_action(state):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        add_ledger_fixture(state, "ledger-1", "grant-1", "missing-action")


@pytest.mark.parametrize("kind", get_args(ActionKind))
@pytest.mark.parametrize("source", get_args(ActionSource))
def test_outbox_enforces_source_permissions(state, kind, source):
    add_request(state, "action-1", "request-1")
    if source in ALLOWED_SOURCES[kind]:
        state.execute("UPDATE outbox SET kind=?, source=?", (kind, source))
        assert state.execute("SELECT kind, source FROM outbox").fetchone() == (kind, source)
    else:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            state.execute("UPDATE outbox SET kind=?, source=?", (kind, source))


def test_action_round_trip_preserves_amount_and_review_fields(state):
    add_request(state, "action-1", "request-1")
    assert state.execute(
        "SELECT amount_vnd, source, evidence_ref, needs_approval, queue FROM outbox"
    ).fetchone() == (10_000, "a1", "contact_log:contact-1", 0, "care")


@pytest.mark.parametrize("status", ["trusted", "stale", "corrupt", "missing"])
def test_feed_health_preserves_source_time_separately_from_tick(state, status):
    source_time = "2026-10-31T23:20:00.000000Z"
    state.execute(
        "INSERT INTO guard_heartbeat (tick_at, agent_id, recorded_at, proactive_contact_allowed) "
        "VALUES (?, ?, ?, ?)", (NOW, "a3", NOW, 0),
    )
    state.execute(
        "INSERT INTO feed_health (feed, tick_at, status, source_timestamp, checked_at) "
        "VALUES (?, ?, ?, ?, ?)", ("scan_events", NOW, status, source_time, NOW),
    )
    assert state.execute("SELECT source_timestamp, tick_at FROM feed_health").fetchone() == (
        source_time, NOW,
    )
