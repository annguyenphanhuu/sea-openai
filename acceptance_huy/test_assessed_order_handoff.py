"""Check the read-only source projection boundary used by the A2/UI handoff."""

from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
import json
import sqlite3

import pytest

from logistics_an_nguyen import (
    FeedHealth, ReleaseAdapter, ReleaseReader, assessed_orders_payload, evaluate_tick,
)
from logistics_an_nguyen.adapter import REQUIRED_FEEDS
from logistics_an_nguyen.models import utc_iso


TICK = datetime.fromisoformat("2026-10-28T12:00:00+07:00")
CREATED = "2026-10-27T10:00:00+07:00"


@pytest.fixture
def source():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE orders(order_id,created_at,guaranteed_date,carrier_id,service_level,cancelled_at);
        CREATE TABLE scan_events(event_id,order_id,status,location_type,location_id,event_at,ingested_at,carrier_event_id);
        CREATE TABLE delivery_attempts(attempt_id,order_id,attempt_no,attempt_at,outcome,reason_code,call_attempts);
        CREATE TABLE linehaul_reports(report_id,trip_id,reported_at,reported_by,reason_code,driver_note);
    """)
    db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)",
               ("o1", CREATED, "2026-10-29", "carrier-1", "standard", None))
    yield db
    db.close()


def add_scan(source, record_id="handover-1", *, event_at="2026-10-28T08:00:00+07:00",
             ingested_at="2026-10-28T08:05:00+07:00", status="handed_over", order_id="o1"):
    source.execute("INSERT INTO scan_events VALUES (?,?,?,?,?,?,?,?)", (
        record_id, order_id, status, "station", "station-1", event_at, ingested_at, None,
    ))


def healthy(tick=TICK):
    return tuple(FeedHealth(feed, "trusted", tick, tick) for feed in REQUIRED_FEEDS)


def project(source, tmp_path, *, tick=TICK, health=None):
    path = tmp_path / "source.sqlite"
    source.commit()
    with sqlite3.connect(path) as target:
        source.backup(target)
    before = sha256(path.read_bytes()).hexdigest()
    with ReleaseReader(path) as reader:
        snapshot = reader.snapshot(tick)
    health = healthy(tick) if health is None else health
    result = evaluate_tick(ReleaseAdapter(snapshot).orders(), tick_at=tick, feed_health=health)
    assert sha256(path.read_bytes()).hexdigest() == before
    return snapshot, result, health


def export(source, tmp_path, **kwargs):
    snapshot, result, health = project(source, tmp_path, **kwargs)
    return assessed_orders_payload(snapshot, result, feed_health=health)


def test_dates_keep_distinct_meanings_and_source_provenance(source, tmp_path):
    add_scan(source)
    payload = export(source, tmp_path)
    item = payload["orders"][0]
    assert item["created_at"] == "2026-10-27T03:00:00.000000Z"
    assert item["handed_over_at"] == "2026-10-28T01:00:00.000000Z"
    assert item["guaranteed_date"] == "2026-10-29"
    assert item["revised_eta"] is None
    assert item["metadata_reason_codes"] == []
    evidence = item["metadata_evidence"][1]
    assert evidence == dict(
        feed="scan_events", source_table="scan_events", record_id="handover-1",
        ingested_at="2026-10-28T01:05:00.000000Z", fact_code="handed_over_at",
        value=item["handed_over_at"], is_structured=True,
    )
    assert payload["tick_at"] == item["assessed_at"] == utc_iso(TICK)
    assert payload["payload_version"] == "a2_order_list_v1"
    assert all(row["usable_at_tick"] for row in payload["feed_health"])
    assert "proactive_contact_allowed" not in payload
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_missing_handover_does_not_use_creation_or_later_stage(source, tmp_path):
    add_scan(source, status="station")
    item = export(source, tmp_path)["orders"][0]
    assert item["created_at"] is not None
    assert item["handed_over_at"] is None
    assert item["metadata_reason_codes"] == ["handed_over_scan_missing"]
    assert len(item["metadata_evidence"]) == 1


@pytest.mark.parametrize("changes", [
    {"ingested_at": "2026-10-28T12:00:01+07:00"},
    {"event_at": "2026-10-28T12:00:01+07:00"},
])
def test_future_scan_is_not_exposed_even_from_unfiltered_snapshot(source, tmp_path, changes):
    snapshot, result, health = project(source, tmp_path)
    row = dict(event_id="future", order_id="o1", status="handed_over",
               event_at="2026-10-28T08:00:00+07:00", ingested_at="2026-10-28T08:05:00+07:00") | changes
    payload = assessed_orders_payload(replace(snapshot, scans=(row,)), result, feed_health=health)
    assert payload["orders"][0]["handed_over_at"] is None
    assert all(e["record_id"] != "future" for e in payload["orders"][0]["metadata_evidence"])


def test_delayed_handover_appears_only_when_ingested_without_reverting_stage(source, tmp_path):
    add_scan(source, ingested_at="2026-10-28T12:30:00+07:00")
    add_scan(source, "station-2", status="station", event_at="2026-10-28T10:00:00+07:00",
             ingested_at="2026-10-28T10:01:00+07:00")
    assert export(source, tmp_path)["orders"][0]["handed_over_at"] is None
    item = export(source, tmp_path, tick=TICK + timedelta(minutes=30))["orders"][0]
    assert item["handed_over_at"] == "2026-10-28T01:00:00.000000Z"
    assert [e["value"] for e in item["evidence"] if e["fact_code"] == "logistics_stage"] == ["station"]


def test_first_handover_wins_over_repeated_scans_and_other_orders(source, tmp_path):
    add_scan(source, "later", event_at="2026-10-28T09:00:00+07:00",
             ingested_at="2026-10-28T09:00:00+07:00")
    add_scan(source, "earlier", ingested_at="2026-10-28T11:00:00+07:00")
    add_scan(source, "unrelated", order_id="other", event_at="2026-10-28T07:00:00+07:00")
    snapshot, result, health = project(source, tmp_path)
    payload = assessed_orders_payload(snapshot, result, feed_health=health)
    assert payload == assessed_orders_payload(replace(snapshot, scans=tuple(reversed(snapshot.scans))),
                                             result, feed_health=reversed(health))
    assert payload["orders"][0]["metadata_evidence"][1]["record_id"] == "earlier"


@pytest.mark.parametrize("status", ["stale", "corrupt", "missing", "old_source"])
def test_unusable_scan_feed_suppresses_date_but_keeps_audit_evidence(source, tmp_path, status):
    add_scan(source)
    bad = FeedHealth("scan_events", "trusted" if status == "old_source" else status, TICK,
                     TICK - timedelta(minutes=31) if status == "old_source" else TICK)
    health = tuple(bad if item.feed == "scan_events" else item for item in healthy())
    item = export(source, tmp_path, health=health)["orders"][0]
    assert item["status"] == "unknown_feed"
    assert item["created_at"] is not None
    assert item["handed_over_at"] is None
    assert item["metadata_reason_codes"] == ["handed_over_at_feed_unavailable"]
    assert item["metadata_evidence"][1]["record_id"] == "handover-1"


def test_missing_a3_state_does_not_imply_trusted_dates(source, tmp_path):
    add_scan(source)
    payload = export(source, tmp_path, health=())
    item = payload["orders"][0]
    assert item["created_at"] is item["handed_over_at"] is None
    assert item["metadata_reason_codes"] == ["created_at_feed_unavailable", "handed_over_at_feed_unavailable"]
    assert all(row["status"] == "missing" and not row["usable_at_tick"] for row in payload["feed_health"])


def test_cancelled_and_future_orders_are_excluded(source, tmp_path):
    for order_id, created_at, cancelled_at in [
        ("cancelled", CREATED, "2026-10-28T11:00:00+07:00"),
        ("future", "2026-10-28T12:00:01+07:00", None),
        ("future_cancel", CREATED, "2026-10-29T11:00:00+07:00"),
    ]:
        source.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)",
                       (order_id, created_at, "2026-10-29", "carrier-1", "standard", cancelled_at))
    assert [item["order_id"] for item in export(source, tmp_path)["orders"]] == ["future_cancel", "o1"]


@pytest.mark.parametrize("change", ["tick", "missing_order", "duplicate", "wrong_order", "guarantee", "future_evidence"])
def test_reject_mixed_snapshot_and_assessment_inputs(source, tmp_path, change):
    snapshot, result, health = project(source, tmp_path)
    item = result.assessments[0]
    if change == "tick":
        result = replace(result, assessments=(replace(item, assessed_at=TICK - timedelta(minutes=30)),))
    elif change == "missing_order":
        result = replace(result, assessments=())
    elif change == "duplicate":
        result = replace(result, assessments=(item, item))
    elif change == "wrong_order":
        result = replace(result, assessments=(replace(item, order_id="other"),))
    elif change == "guarantee":
        result = replace(result, assessments=(replace(item, guaranteed_date=TICK.date()),))
    else:
        evidence = dict(item.evidence[0], ingested_at=TICK + timedelta(seconds=1))
        result = replace(result, assessments=(replace(item, evidence=(evidence,)),))
    with pytest.raises(ValueError):
        assessed_orders_payload(snapshot, result, feed_health=health)


def test_reject_duplicate_or_future_health(source, tmp_path):
    snapshot, result, health = project(source, tmp_path)
    for invalid in [
        health + (health[0],), healthy(TICK + timedelta(minutes=30)),
        (replace(health[0], source_timestamp=TICK + timedelta(seconds=1)),),
        (replace(health[0], last_ingested_at=TICK + timedelta(seconds=1)),),
    ]:
        with pytest.raises(ValueError):
            assessed_orders_payload(snapshot, result, feed_health=invalid)


def test_reject_handover_before_creation(source, tmp_path):
    snapshot, result, health = project(source, tmp_path)
    row = dict(event_id="invalid", order_id="o1", status="handed_over",
               event_at="2026-10-27T09:00:00+07:00", ingested_at=CREATED)
    with pytest.raises(ValueError, match="precede order creation"):
        assessed_orders_payload(replace(snapshot, scans=(row,)), result, feed_health=health)
