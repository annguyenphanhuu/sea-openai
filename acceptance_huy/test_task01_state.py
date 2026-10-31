"""Task 01: immutable run identity, atomic state and neutral command metadata."""

from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from platform_huy.dto import CommandKeyRecord, PlatformError, SourceIdentity
from platform_huy.state import (
    bootstrap, canonical, connect_state, current_clock, immediate, lookup_key, utc,
)


START = datetime(2026, 10, 31, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 1, 0, tzinfo=timezone.utc)
NOW = "2026-10-31T00:00:00.000000Z"
IDENTITY = SourceIdentity("a" * 64, "b" * 64, START, END)
V0_SCHEMA = Path(__file__).resolve().parents[1] / "contracts/schema_state.sql"


@pytest.fixture
def db(tmp_path):
    connection = connect_state(tmp_path / "runtime.sqlite")
    bootstrap(connection, run_id="r", identity=IDENTITY, start_at=START)
    yield connection
    connection.close()


def assert_code(code, call):
    with pytest.raises(PlatformError) as error:
        call()
    assert error.value.code == code


def contact(db):
    db.execute(
        "INSERT INTO contact_log(contact_id,order_id,channel,initiated_by,requested_at) "
        "VALUES ('c','o','chat','A1',?)", (NOW,),
    )


def outbox(db, key="action-key"):
    db.execute(
        "INSERT INTO outbox(action_id,idempotency_key,order_id,kind,amount_vnd,source,"
        "evidence_ref,needs_approval,queue,requested_at,available_at) "
        "VALUES ('a',?,'o','coins',10000,'a1','evidence:e',0,'care',?,?)",
        (key, NOW, NOW),
    )


def attempt(db):
    db.execute(
        "INSERT INTO tick_attempts(attempt_id,tick_at,clock_version,status,a3_status,"
        "retry_count,errors_json,started_wall_at) "
        "VALUES ('t',?,1,'pending','pending',0,'[]',?)", (NOW, NOW),
    )


def cancellation(db):
    outbox(db)
    db.execute(
        "INSERT INTO cancel_requests(cancel_id,request_action_id,order_id,customer_id,"
        "status,confirmation_id,version,order_snapshot_sha256,requested_at) "
        "VALUES ('cancel','a','o','customer','awaiting_confirmation','confirm',1,'hash',?)",
        (NOW,),
    )


def review(db, key="review-key"):
    db.execute(
        "INSERT INTO eligibility_reviews(review_id,order_id,revision,state,source_identity_json,"
        "evidence_as_of,material_fingerprints_json,decision_json,evidence_refs_json,reason,"
        "reviewed_by,reviewed_wall_at,idempotency_key,request_hash) "
        "VALUES ('review','o',1,'active','{}',?,'{}','{}','[]','verified','human',?,?, 'rh')",
        (NOW, NOW, key),
    )


def test_canonical_json_has_literal_utf8_order_and_no_whitespace():
    assert canonical({"z": [2, 1], "a": "Việt"}) == '{"a":"Việt","z":[2,1]}'


def test_local_dto_time_round_trip_and_freezing():
    assert canonical(IDENTITY) == (
        '{"core_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        '"coverage_end":"2026-11-01T00:00:00.000000Z",'
        '"coverage_start":"2026-10-31T00:00:00.000000Z",'
        '"ops_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'
    )
    assert json.loads(canonical(IDENTITY))["coverage_start"] == NOW
    with pytest.raises(FrozenInstanceError):
        IDENTITY.core_sha256 = "changed"


def test_utc_normalizes_aware_offset_and_fixed_precision():
    value = datetime(2026, 10, 31, 7, 0, 1, 25, timezone(timedelta(hours=7)))
    assert utc(value) == "2026-10-31T00:00:01.000025Z"
    assert datetime.fromisoformat(utc(START)) == START


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_canonical_rejects_nonfinite_json(value):
    with pytest.raises((ValueError, PlatformError)):
        canonical({"amount": value})


def test_utc_and_canonical_reject_naive_time():
    assert_code("validation_error", lambda: utc(datetime(2026, 10, 31)))
    assert_code("validation_error", lambda: canonical({"at": datetime(2026, 10, 31)}))


def test_bootstrap_is_idempotent_and_clock_starts_unready(db):
    bootstrap(db, run_id="r", identity=IDENTITY, start_at=START)
    assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
    assert db.execute("SELECT current_at,version FROM demo_clock").fetchone() == (None, 0)
    assert db.execute("SELECT tick_at,version FROM replay_checkpoint").fetchone() == (None, 0)
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.isolation_level is None
    assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert db.execute("SELECT run_id,start_at,policy_version FROM run_metadata").fetchone() == (
        "r", NOW, "huy-demo-v1",
    )
    assert_code("run_not_ready", lambda: current_clock(db))


def test_current_clock_reads_persisted_business_time(db):
    db.execute("UPDATE demo_clock SET current_at=?,version=7", (NOW,))
    assert current_clock(db) == (datetime(2026, 10, 31, 0, tzinfo=timezone.utc), 7)


def test_real_file_transaction_rolls_back_insert_on_exception(db):
    with pytest.raises(RuntimeError, match="abort"):
        with immediate(db):
            contact(db)
            raise RuntimeError("abort")
    assert db.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0] == 0
    assert not db.in_transaction
    with immediate(db):
        contact(db)
    assert db.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0] == 1


def test_two_file_connections_report_busy_without_partial_changes(tmp_path):
    first = connect_state(tmp_path / "busy.sqlite")
    second = connect_state(tmp_path / "busy.sqlite")
    try:
        bootstrap(first, run_id="r", identity=IDENTITY, start_at=START)
        second.execute("PRAGMA busy_timeout=10")
        with immediate(first):
            contact(first)
            def blocked():
                with immediate(second):
                    second.execute("INSERT INTO controls VALUES ('k','global','true',?,'human','test')", (NOW,))
            assert_code("state_busy", blocked)
        assert second.execute("SELECT COUNT(*) FROM controls").fetchone()[0] == 0
        assert second.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0] == 1
        assert not second.in_transaction
    finally:
        first.close()
        second.close()


def test_connection_open_io_failure_is_state_unavailable(tmp_path):
    assert_code("state_unavailable", lambda: connect_state(tmp_path / "missing" / "state.sqlite"))


def test_existing_empty_v0_is_adopted_unchanged(tmp_path):
    conn = connect_state(tmp_path / "v0.sqlite")
    try:
        conn.executescript(V0_SCHEMA.read_text(encoding="utf-8"))
        before = conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        bootstrap(conn, run_id="r", identity=IDENTITY, start_at=START)
        assert len(before) == 8
        for name, sql in before:
            assert conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0] == sql
    finally:
        conn.close()


def test_nonempty_unattributed_v0_fails_without_schema_writes(tmp_path):
    conn = connect_state(tmp_path / "unattributed.sqlite")
    try:
        conn.executescript(V0_SCHEMA.read_text(encoding="utf-8"))
        contact(conn)
        before = conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        assert_code("source_invalid", lambda: bootstrap(conn, run_id="r", identity=IDENTITY, start_at=START))
        assert conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall() == before
        assert conn.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0] == 1
    finally:
        conn.close()


def test_nonempty_unrecognized_state_is_not_adopted(tmp_path):
    conn = connect_state(tmp_path / "foreign-state.sqlite")
    try:
        conn.execute("CREATE TABLE unrelated_source(record_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO unrelated_source VALUES ('source-row')")
        before = tuple(conn.iterdump())
        assert_code("source_invalid", lambda: bootstrap(conn, run_id="r", identity=IDENTITY, start_at=START))
        assert tuple(conn.iterdump()) == before
        assert conn.execute("SELECT COUNT(*) FROM unrelated_source").fetchone()[0] == 1
    finally:
        conn.close()


def test_bootstrap_enables_foreign_keys_before_begin_on_raw_connection(tmp_path):
    conn = sqlite3.connect(tmp_path / "raw.sqlite", isolation_level=None)
    try:
        bootstrap(conn, run_id="r", identity=IDENTITY, start_at=START)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("SELECT current_at,version FROM demo_clock").fetchone() == (None, 0)
    finally:
        conn.close()


@pytest.mark.parametrize("change", ["run", "source", "start"])
def test_identity_mismatch_never_mutates_existing_state(db, change):
    before = tuple(db.iterdump())
    identity = SourceIdentity("c" * 64, "b" * 64, START, END) if change == "source" else IDENTITY
    assert_code("source_invalid", lambda: bootstrap(
        db, run_id="other" if change == "run" else "r", identity=identity,
        start_at=END if change == "start" else START,
    ))
    assert tuple(db.iterdump()) == before


def test_unsupported_schema_version_never_mutates_state(db):
    db.execute("INSERT INTO schema_migrations(version,applied_at) VALUES (99,?)", (NOW,))
    before = tuple(db.iterdump())
    assert_code("source_invalid", lambda: bootstrap(db, run_id="r", identity=IDENTITY, start_at=START))
    assert tuple(db.iterdump()) == before


def test_failed_migration_is_atomic_on_real_file(tmp_path):
    conn = connect_state(tmp_path / "broken.sqlite")
    try:
        conn.executescript(V0_SCHEMA.read_text(encoding="utf-8"))
        # Real incompatible state causes SQLite failure after companion DDL starts.
        conn.execute("CREATE VIEW tick_attempts AS SELECT 'incompatible' AS x")
        before = conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        assert_code("state_unavailable", lambda: bootstrap(conn, run_id="r", identity=IDENTITY, start_at=START))
        assert conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall() == before
        assert not conn.in_transaction
    finally:
        conn.close()


def test_lookup_absence_and_untrusted_legacy_outbox(db):
    with immediate(db):
        assert lookup_key(db, "absent") is None
        outbox(db)
        record = lookup_key(db, "action-key")
        assert isinstance(record, CommandKeyRecord)
        assert (record.namespace, record.key, record.reference_id) == ("outbox", "action-key", "a")
        assert (record.principal_id, record.request_hash, record.result_json) == (None, None, None)
        assert json.loads(record.payload_json) == {
            "action_id": "a", "idempotency_key": "action-key", "order_id": "o", "kind": "coins",
            "amount_vnd": 10000, "source": "a1", "confirmation_id": None,
            "evidence_ref": "evidence:e", "needs_approval": False, "queue": "care", "requested_at": NOW,
        }


def test_lookup_outbox_receipt_uses_trusted_metadata(db):
    outbox(db)
    db.execute(
        "INSERT INTO action_receipts(action_id,request_hash,principal_id,attested_source,"
        "decision_code,result_json,decided_at) VALUES ('a','rh','human','a1','blocked','{}',?)", (NOW,),
    )
    record = lookup_key(db, "action-key")
    assert (record.principal_id, record.request_hash, record.result_json) == ("human", "rh", "{}")


def test_lookup_replay_metadata(db):
    attempt(db)
    db.execute("INSERT INTO replay_commands VALUES ('replay-key','operator','rh','t','{}')")
    assert asdict(lookup_key(db, "replay-key")) == {
        "namespace": "replay_commands", "key": "replay-key", "principal_id": "operator",
        "request_hash": "rh", "reference_id": "t", "payload_json": None, "result_json": "{}",
    }


def test_lookup_workflow_metadata(db):
    cancellation(db)
    db.execute("INSERT INTO workflow_commands VALUES ('workflow-key','rh','human','cancel','{}',?)", (NOW,))
    assert asdict(lookup_key(db, "workflow-key")) == {
        "namespace": "workflow_commands", "key": "workflow-key", "principal_id": "human",
        "request_hash": "rh", "reference_id": "cancel", "payload_json": None, "result_json": "{}",
    }


def test_lookup_review_metadata(db):
    review(db)
    assert asdict(lookup_key(db, "review-key")) == {
        "namespace": "eligibility_reviews", "key": "review-key", "principal_id": "human",
        "request_hash": "rh", "reference_id": "review", "payload_json": None, "result_json": None,
    }


def test_lookup_conflicting_namespaces_refuses_key(db):
    outbox(db, "collision")
    review(db, "collision")
    assert_code("idempotency_conflict", lambda: lookup_key(db, "collision"))


@pytest.mark.parametrize("table,column,value", [
    ("tick_results", "result_json", "not json"),
    ("a2_progress", "records_json", "not json"),
])
def test_companion_json_constraints_reject_invalid_payloads(db, table, column, value):
    with pytest.raises(sqlite3.IntegrityError):
        if table == "tick_results":
            db.execute("INSERT INTO tick_results VALUES (?,?,'hash')", (NOW, value))
        else:
            db.execute("INSERT INTO a2_progress VALUES (1,?,?)", (NOW, value))


def test_voucher_ledger_is_independent_and_enforces_face_value(db):
    contact(db)
    outbox(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO voucher_ledger VALUES ('v','voucher:o','o','a','c',9999,'huy-demo-v1',?)", (NOW,))
    db.execute("INSERT INTO ledger_new VALUES ('l','xu:o','o','a','c',10000,'late_delivery',?)", (NOW,))
    db.execute("INSERT INTO voucher_ledger VALUES ('v','voucher:o','o','a','c',10000,'huy-demo-v1',?)", (NOW,))
    assert db.execute("SELECT COUNT(*) FROM ledger_new").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM voucher_ledger").fetchone()[0] == 1
