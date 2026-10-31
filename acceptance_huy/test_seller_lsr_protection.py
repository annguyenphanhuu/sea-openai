"""An-owned regressions for the source/replay boundary of A2 seller protection."""

from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
import json
import sqlite3
from typing import get_args

import pytest

from contracts.types import FaultParty
from logistics_an_nguyen import (
    FeedHealth, ReleaseAdapter, ReleaseReader, ReplaySnapshot,
    assessed_orders_payload, assessment_payload, evaluate_tick,
)
from logistics_an_nguyen.adapter import REQUIRED_FEEDS
from logistics_an_nguyen.models import utc_iso


TICK = datetime.fromisoformat("2026-10-28T12:00:00+07:00")
CREATED = datetime.fromisoformat("2026-10-24T10:00:00+07:00")


def scan(record_id="handover", *, at=None, seen=None, status="handed_over", **changes):
    at = at or CREATED + timedelta(days=2)
    return dict(
        event_id=record_id, order_id="o1", status=status, location_type="station",
        location_id="s1", event_at=at.isoformat(), ingested_at=(seen or at).isoformat(),
        carrier_event_id=None,
    ) | changes


def snapshot(*, scans=None, policy=2, tick=TICK, attempts=(), reports=()):
    return ReplaySnapshot(
        tick, (dict(order_id="o1", created_at=CREATED.isoformat(),
                    guaranteed_date="2026-10-27", carrier_id="carrier", service_level="standard",
                    cancelled_at=None, payment_method="COD", items_value_vnd=100_000),),
        (scan(),) if scans is None else tuple(scans), tuple(attempts), tuple(reports),
        seller_prepare_days=policy,
    )


def healthy(tick=TICK):
    return tuple(FeedHealth(feed, "trusted", tick, tick) for feed in REQUIRED_FEEDS)


def evaluate(source=None, *, health=None, extra=()):
    source = source or snapshot()
    health = healthy(source.tick_at) if health is None else health
    facts = ReleaseAdapter(source).orders()[0]
    facts = replace(facts, evidence=facts.evidence + tuple(extra))
    result = evaluate_tick((facts,), tick_at=source.tick_at, feed_health=health)
    payload = assessed_orders_payload(source, result, feed_health=health)
    return result.assessments[0], payload["orders"][0]


def fact(code, value, *, feed="scan_events", structured=True, seen=TICK):
    return dict(feed=feed, source_table=feed, record_id="independent-fact",
                ingested_at=seen, fact_code=code, value=value, is_structured=structured)


@pytest.mark.parametrize(("elapsed", "expected"), [
    (timedelta(0), True), (timedelta(hours=48) - timedelta(microseconds=1), True),
    (timedelta(hours=48), True), (timedelta(hours=48, microseconds=1), False),
    (timedelta(hours=49), False),
])
def test_preparation_duration_uses_exact_elapsed_time(elapsed, expected):
    assessment, item = evaluate(snapshot(scans=[scan(at=CREATED + elapsed)]))
    assert assessment.status == "late"
    assert item["handover_on_time"] is expected
    assert item["fault_owner"] == item["fault_party"] == ("carrier" if expected else "unknown")
    assert (item["lsr_exemption"] is not None) is expected
    assert assessment_payload(assessment)["handover_on_time"] is expected
    assert item["cause"]["fault_party"] == item["fault_party"]
    assert json.loads(json.dumps(item, ensure_ascii=False, allow_nan=False)) == item
    if expected:
        assert "Miễn trừ LSR" in item["lsr_exemption"]
        assert "fault:unknown" not in item["reason_codes"]
    assert get_args(FaultParty) == ("customer", "carrier", "platform", "force_majeure", "unknown")


def test_audit_contains_actual_scan_creation_policy_and_derived_result():
    seen = TICK - timedelta(minutes=10)
    _, item = evaluate(snapshot(scans=[scan(seen=seen)]))
    evidence = {entry["fact_code"]: entry for entry in item["evidence"]}
    assert evidence["created_at"]["record_id"] == "o1"
    assert evidence["created_at"]["value"] == utc_iso(CREATED)
    assert evidence["seller_prepare_days"]["source_table"] == "policy"
    assert evidence["seller_prepare_days"]["record_id"] == "seller_prepare_days"
    assert evidence["seller_prepare_days"]["value"] == 2
    assert evidence["handed_over_at"]["record_id"] == "handover"
    assert evidence["handed_over_at"]["ingested_at"] == utc_iso(seen)
    assert evidence["handed_over_at"]["value"] == item["handed_over_at"]
    assert evidence["handover_on_time"]["value"] is True
    # A late ingestion cannot make a timely physical handover late.
    assert item["handover_on_time"] is True


@pytest.mark.parametrize(("policy", "expected"), [(None, None), (0, False), (1, False), (2, True), (3, True)])
def test_policy_is_projected_without_assuming_two_days(policy, expected):
    _, item = evaluate(snapshot(policy=policy))
    assert item["handover_on_time"] is expected
    assert (item["lsr_exemption"] is not None) is (expected is True)


@pytest.mark.parametrize("status", ["station", "packed", None])
def test_missing_handover_never_uses_another_stage_or_creation(status):
    _, item = evaluate(snapshot(scans=[] if status is None else [scan(status=status)]))
    assert item["handover_on_time"] is None
    assert item["fault_owner"] == "unknown"
    assert item["lsr_exemption"] is None
    assert "seller_handover_unverified" in item["reason_codes"]


@pytest.mark.parametrize("feed", REQUIRED_FEEDS)
@pytest.mark.parametrize("state", ["missing", "stale", "corrupt", "old_source", "absent"])
def test_unavailable_contributing_feeds_cannot_exempt_or_infer_carrier(feed, state):
    health = [item for item in healthy() if item.feed != feed]
    if state != "absent":
        health.append(FeedHealth(feed, "trusted" if state == "old_source" else state, TICK,
                                 TICK - timedelta(minutes=31) if state == "old_source" else TICK))
    _, item = evaluate(health=health)
    assert item["status"] == "unknown_feed"
    assert item["handover_on_time"] is None
    assert item["fault_owner"] == "unknown"
    assert item["lsr_exemption"] is None
    assert any(e["fact_code"] == "handed_over_at" for e in item["evidence"])


@pytest.mark.parametrize("owner", ["customer", "platform", "force_majeure", "carrier"])
def test_handover_does_not_overwrite_confirmed_other_faults(owner):
    _, item = evaluate(extra=[fact("fault_party", owner)])
    assert item["fault_party"] == item["fault_owner"] == owner
    assert item["handover_on_time"] is True
    assert item["status"] == ("customer_fault" if owner == "customer" else "late")
    assert (item["lsr_exemption"] is not None) is (owner == "carrier")


def test_customer_attempt_and_warehouse_exception_keep_precedence():
    attempt = dict(attempt_id="failed", order_id="o1", attempt_no=1, attempt_at=TICK.isoformat(),
                   outcome="refused", reason_code="customer_refused", call_attempts=1)
    _, item = evaluate(snapshot(attempts=[attempt]))
    assert (item["status"], item["fault_owner"], item["lsr_exemption"]) == ("customer_fault", "customer", None)
    _, item = evaluate(snapshot(scans=[scan(), scan("lost", at=TICK, status="lost", location_type="warehouse")]))
    assert (item["status"], item["fault_owner"], item["lsr_exemption"]) == ("exception", "platform", None)


def test_conflicting_fault_cannot_be_replaced_with_carrier():
    _, item = evaluate(extra=[fact("fault_party", "carrier"), fact("fault_party", "customer")])
    assert item["status"] == "unknown_feed"
    assert item["fault_owner"] == "unknown"
    assert item["lsr_exemption"] is None


@pytest.mark.parametrize("code", ["created_at", "handed_over_at", "seller_prepare_days"])
def test_latest_null_or_conflicting_fact_does_not_resurrect_earlier_proof(code):
    _, item = evaluate(extra=[fact(code, None)])
    assert item["handover_on_time"] is item["lsr_exemption"] is None
    values = [1, 2] if code == "seller_prepare_days" else [utc_iso(CREATED), utc_iso(TICK)]
    _, item = evaluate(extra=[fact(code, value) for value in values])
    assert item["status"] == "unknown_feed"
    assert item["fault_owner"] == "unknown"
    assert item["lsr_exemption"] is None


def test_unstructured_and_future_claims_cannot_change_handover_or_fault():
    baseline, _ = evaluate()
    result, item = evaluate(extra=[
        fact("fault_party", "customer", structured=False),
        fact("handed_over_at", utc_iso(CREATED), structured=False),
        fact("seller_prepare_days", 0, structured=False),
        fact("fault_party", "platform", seen=TICK + timedelta(seconds=1)),
    ])
    assert result.fault_party == baseline.fault_party == "carrier"
    assert item["handover_on_time"] is True
    assert result.confidence <= baseline.confidence
    _, missing = evaluate(snapshot(scans=[]), extra=[fact("handed_over_at", utc_iso(CREATED), structured=False)])
    assert missing["handover_on_time"] is missing["lsr_exemption"] is None


def test_first_visible_handover_is_stable_under_retries_and_input_order():
    scans = [scan("b", seen=TICK), scan("a", seen=TICK),
             scan("retry", at=CREATED + timedelta(days=3), carrier_event_id="same"),
             scan("other", at=CREATED, order_id="other")]
    left, item = evaluate(snapshot(scans=scans))
    right, reversed_item = evaluate(snapshot(scans=reversed(scans)))
    assert left == right
    assert item == reversed_item
    assert item["handover_on_time"] is True
    assert next(e["record_id"] for e in item["evidence"] if e["fact_code"] == "handed_over_at") == "a"


@pytest.mark.parametrize(("at", "late"), [
    ("2026-10-27T23:59:59+07:00", False), ("2026-10-28T00:00:00+07:00", True),
])
def test_protection_starts_only_after_guaranteed_day_ends(at, late):
    _, item = evaluate(snapshot(tick=datetime.fromisoformat(at)))
    assert (item["late_days"] > 0) is late
    assert item["handover_on_time"] is (True if late else None)
    assert (item["lsr_exemption"] is not None) is late


@pytest.mark.parametrize(("delivered", "expected"), [
    ("2026-10-27T23:59:59+07:00", None), ("2026-10-28T00:00:00+07:00", True),
])
def test_delivered_order_uses_delivery_time_for_actual_lateness(delivered, expected):
    _, item = evaluate(snapshot(scans=[scan(), scan("delivery", at=datetime.fromisoformat(delivered), status="delivered")]))
    assert item["handover_on_time"] is expected
    assert (item["lsr_exemption"] is not None) is (expected is True)


@pytest.mark.parametrize("at", [CREATED - timedelta(seconds=1), TICK])
def test_impossible_handover_timeline_is_rejected(at):
    with pytest.raises(ValueError, match="handed_over"):
        evaluate(snapshot(scans=[scan(at=at, seen=CREATED + timedelta(days=2))]))


@pytest.mark.parametrize("code", ["created_at", "handed_over_at"])
def test_normalized_source_timestamp_cannot_follow_ingestion(code):
    with pytest.raises(ValueError, match="cannot follow its ingestion"):
        evaluate(extra=[fact(code, utc_iso(TICK + timedelta(seconds=1)))])


def test_handover_after_confirmed_delivery_cannot_establish_exemption():
    with pytest.raises(ValueError, match="between creation and delivery"):
        evaluate(snapshot(scans=[scan(at=TICK)]), extra=[
            fact("delivered_at", utc_iso(TICK - timedelta(hours=1))),
        ])


@pytest.mark.parametrize("value", [-1, True, 2.0, "2"])
def test_custom_projection_rejects_invalid_policy(value):
    with pytest.raises(ValueError, match="seller_prepare_days"):
        snapshot(policy=value)


@pytest.fixture
def source():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE orders(order_id,created_at,guaranteed_date,carrier_id,service_level,cancelled_at);
        CREATE TABLE scan_events(event_id,order_id,status,location_type,location_id,event_at,ingested_at,carrier_event_id);
        CREATE TABLE delivery_attempts(attempt_id,order_id,attempt_no,attempt_at,outcome,reason_code,call_attempts);
        CREATE TABLE linehaul_reports(report_id,trip_id,reported_at,reported_by,reason_code,driver_note);
        CREATE TABLE policy(key TEXT PRIMARY KEY,value TEXT,note TEXT);
        INSERT INTO policy VALUES ('seller_prepare_days','2','Preparation limit');
        INSERT INTO policy VALUES ('seller_handover_days','3','Cancellation limit');
    """)
    db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)", (
        "o1", CREATED.isoformat(), "2026-10-27", "carrier", "standard", None,
    ))
    yield db
    db.close()


def copy_source(source, path):
    source.commit()
    with sqlite3.connect(path) as target:
        source.backup(target)


@pytest.mark.parametrize("already_late_scan", [False, True])
def test_read_only_replay_waits_for_ingestion_then_exposes_same_evidence(source, tmp_path, already_late_scan):
    seen = TICK + timedelta(minutes=30)
    row = scan(seen=seen)
    source.execute("INSERT INTO scan_events VALUES (?,?,?,?,?,?,?,?)", tuple(row.values()))
    if already_late_scan:
        later = scan("later-handover", at=CREATED + timedelta(days=3))
        source.execute("INSERT INTO scan_events VALUES (?,?,?,?,?,?,?,?)", tuple(later.values()))
    path = tmp_path / "core.sqlite"
    copy_source(source, path)
    before = sha256(path.read_bytes()).hexdigest()
    with ReleaseReader(path) as reader:
        assert reader.connection.execute("PRAGMA query_only").fetchone()[0] == 1
        early = reader.snapshot(TICK)
        assert early.seller_prepare_days == 2
        _, item = evaluate(early)
        assert item["handover_on_time"] is (False if already_late_scan else None)
        assert item["lsr_exemption"] is None
        later = reader.snapshot(seen)
        _, item = evaluate(later)
        assert item["handover_on_time"] is True
        assert item["fault_owner"] == "carrier"
        assert item["handed_over_at"] == utc_iso(CREATED + timedelta(days=2))
        assert item["lsr_exemption"] is not None
    assert sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("change", ["no_table", "no_row", "invalid", "negative", "fractional", "null"])
def test_reader_missing_policy_is_unknown_and_bad_policy_is_rejected(source, tmp_path, change):
    if change == "no_table":
        source.execute("DROP TABLE policy")
    elif change == "no_row":
        source.execute("DELETE FROM policy WHERE key='seller_prepare_days'")
    else:
        source.execute("UPDATE policy SET value=? WHERE key='seller_prepare_days'", ({
            "invalid": "grant exemption", "negative": "-1", "fractional": "2.5", "null": None,
        }[change],))
    path = tmp_path / "core.sqlite"
    copy_source(source, path)
    with ReleaseReader(path) as reader:
        if change in ("no_table", "no_row"):
            assert reader.snapshot(TICK).seller_prepare_days is None
        else:
            with pytest.raises(ValueError, match="policy.seller_prepare_days"):
                reader.snapshot(TICK)
