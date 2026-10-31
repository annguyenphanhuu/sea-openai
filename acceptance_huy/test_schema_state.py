"""Exercise persistence constraints using isolated in-memory state only."""

from pathlib import Path
import sqlite3

import pytest


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
    state.execute(
        "INSERT INTO outbox "
        "(action_id, idempotency_key, order_id, kind, actor, contact_id, "
        "requested_at, available_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (action_id, key, order_id, "grant_late_xu", "A1", "contact-1", NOW, NOW),
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
