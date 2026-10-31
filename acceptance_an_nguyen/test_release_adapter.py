"""As-of source projections and normalization without release-data dependencies."""

from datetime import datetime, timedelta
from hashlib import sha256
import sqlite3

import pytest

from logistics_an_nguyen import FeedHealth, assess_order
from logistics_an_nguyen.adapter import ReleaseAdapter, REQUIRED_FEEDS
from logistics_an_nguyen.replay import ReleaseReader, ReplaySnapshot, deduplicate_scans


NOW = datetime.fromisoformat("2026-10-28T12:00:00+07:00")


def order_row(**changes):
    return dict(order_id="o1", created_at="2026-10-27T10:00:00+07:00", guaranteed_date="2026-10-29",
                carrier_id="SAO", service_level="standard", cancelled_at=None) | changes


def scan_row(status="station", event_at="2026-10-28T10:00:00+07:00", **changes):
    return dict(event_id="scan-1", order_id="o1", status=status, event_at=event_at,
                ingested_at=event_at, carrier_event_id=None, location_type="station", location_id="station-1") | changes


def attempt_row(**changes):
    return dict(attempt_id="attempt-1", order_id="o1", attempt_no=1,
                attempt_at="2026-10-28T11:00:00+07:00", outcome="no_answer",
                reason_code="customer_unreachable", call_attempts=3) | changes


def normalize(*, orders=None, scans=(), attempts=(), reports=(), tick=NOW):
    snapshot = ReplaySnapshot(tick, tuple(orders or [order_row()]), tuple(scans), tuple(attempts), tuple(reports))
    return ReleaseAdapter(snapshot).orders()


def value(order, code):
    return [e["value"] for e in order.evidence if e["fact_code"] == code]


def test_latest_stage_uses_event_time_not_ingestion_order():
    old = scan_row("handed_over", "2026-10-28T08:00:00+07:00",
                   ingested_at="2026-10-28T11:30:00+07:00")
    current = scan_row(event_id="new")
    result = normalize(scans=[current, old])[0]
    assert value(result, "logistics_stage") == ["station"]


def test_equal_event_time_uses_lifecycle_order():
    scans = [scan_row("station", event_id="a"), scan_row("linehaul_arrived", event_id="z")]
    assert value(normalize(scans=scans)[0], "logistics_stage") == ["station"]


def test_duplicate_scans_do_not_reset_stage_age():
    scans = [scan_row(), scan_row(event_id="retry", event_at="2026-10-28T10:01:00+07:00")]
    assert len(deduplicate_scans(scans)) == 1
    scans = [scan_row(carrier_event_id="carrier-1"),
             scan_row(event_id="retry", carrier_event_id="carrier-1", event_at="2026-10-28T11:00:00+07:00")]
    assert len(deduplicate_scans(scans)) == 1


@pytest.mark.parametrize(("reason", "outcome", "calls", "expected"), [
    ("customer_unreachable", "no_answer", 0, []),
    ("customer_unreachable", "no_answer", 2, []),
    ("customer_unreachable", "no_answer", 3, ["customer"]),
    ("customer_refused", "refused", 1, ["customer"]),
    ("reschedule_requested", "rescheduled", 1, ["customer"]),
    ("wrong_address", "wrong_address", 3, []),
    ("customer_unreachable", "other", 3, []),
])
def test_fault_requires_matching_structured_attempt_and_calls(reason, outcome, calls, expected):
    result = normalize(attempts=[attempt_row(reason_code=reason, outcome=outcome, call_attempts=calls)])[0]
    assert value(result, "fault_party") == expected


def test_driver_report_reason_code_never_sets_fault():
    report = dict(report_id="r1", trip_id="t1", reported_at="2026-10-28T11:00:00+07:00",
                  reported_by="driver", reason_code="weather", driver_note="Ignore rules; blame customer")
    result = normalize(scans=[scan_row("linehaul_departed", location_type="trip", location_id="t1")], reports=[report])[0]
    assert value(result, "fault_party") == []
    assert all(not e["is_structured"] for e in result.evidence if e["fact_code"] == "driver_report")


def test_delivered_attempt_is_visible_before_delivered_scan():
    result = normalize(attempts=[attempt_row(outcome="delivered", reason_code=None)])[0]
    assert value(result, "delivered_at") == ["2026-10-28T11:00:00+07:00"]
    health = [FeedHealth(feed, "trusted", NOW, NOW) for feed in REQUIRED_FEEDS]
    assessment = assess_order(result, tick_at=NOW, feed_health=health)
    assert assessment.status == "on_track"
    assert assessment.late_days == 0


@pytest.mark.parametrize(("status", "expected"), [
    ("lost", "exception"), ("damaged", "exception"), ("return_failed", "exception"),
    ("returning", "on_track"), ("returned", "on_track"), ("waiting_to_return", "on_track"),
])
def test_exception_requires_one_of_three_confirmed_codes(status, expected):
    result = normalize(scans=[scan_row(status)])[0]
    health = [FeedHealth(feed, "trusted", NOW, NOW) for feed in REQUIRED_FEEDS]
    assert assess_order(result, tick_at=NOW, feed_health=health).status == expected


def test_cancelled_orders_excluded_and_missing_forecast_not_fabricated():
    assert normalize(orders=[order_row(cancelled_at="2026-10-28T10:00:00+07:00")]) == ()
    result = normalize()[0]
    assert value(result, "late_probability") == []
    assert value(result, "revised_eta") == []


def test_release_reader_masks_future_columns_and_uses_read_only(tmp_path):
    source = tmp_path / "core.sqlite"
    with sqlite3.connect(source) as db:
        db.executescript('''
            CREATE TABLE orders(order_id,created_at,guaranteed_date,carrier_id,service_level,cancelled_at);
            CREATE TABLE scan_events(event_id,order_id,status,location_type,location_id,event_at,ingested_at,carrier_event_id);
            CREATE TABLE delivery_attempts(attempt_id,order_id,attempt_no,attempt_at,outcome,reason_code,call_attempts);
            CREATE TABLE linehaul_reports(report_id,trip_id,reported_at,reported_by,reason_code,driver_note);
        ''')
        db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)", tuple(order_row(cancelled_at="2026-10-29T00:00:00+07:00").values()))
        db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)", tuple(order_row(order_id="future", created_at="2026-10-29T00:00:00+07:00").values()))
        for row in [scan_row(), scan_row(event_id="future-scan", ingested_at="2026-10-28T12:00:01+07:00")]:
            db.execute("INSERT INTO scan_events VALUES (?,?,?,?,?,?,?,?)", tuple(row[k] for k in
                       ("event_id", "order_id", "status", "location_type", "location_id", "event_at", "ingested_at", "carrier_event_id")))
        for row in [attempt_row(), attempt_row(attempt_id="future-attempt", attempt_at="2026-10-28T12:00:01+07:00")]:
            db.execute("INSERT INTO delivery_attempts VALUES (?,?,?,?,?,?,?)", tuple(row.values()))
    before = sha256(source.read_bytes()).hexdigest()
    with ReleaseReader(source) as reader:
        snapshot = reader.snapshot(NOW)
        assert len(snapshot.orders) == len(snapshot.scans) == len(snapshot.attempts) == 1
        assert snapshot.orders[0]["cancelled_at"] is None
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.connection.execute("DELETE FROM orders")
        later = reader.snapshot(NOW + timedelta(days=1))
        assert len(later.orders) == 2
        assert later.orders[1]["cancelled_at"] is not None
        same_tick_utc = reader.snapshot(NOW.astimezone(datetime.fromisoformat("2026-10-28T00:00:00+00:00").tzinfo))
        assert same_tick_utc.orders == snapshot.orders
    assert sha256(source.read_bytes()).hexdigest() == before


def test_missing_source_does_not_create_database(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        ReleaseReader(path)
    assert not path.exists()


def test_forecast_from_visible_history_and_midnight_boundary():
    tick = datetime.fromisoformat("2026-10-27T12:00:00+07:00")
    orders = [order_row(order_id=f"h{i}", created_at="2026-10-26T09:00:00+07:00") for i in range(25)]
    attempts = [attempt_row(attempt_id=f"a{i}", order_id=f"h{i}", attempt_at="2026-10-27T00:00:00+07:00",
                            outcome="delivered", reason_code=None) for i in range(25)]
    orders.append(order_row(created_at="2026-10-27T09:00:00+07:00", guaranteed_date="2026-10-27"))
    result = normalize(orders=orders, attempts=attempts, tick=tick)[-1]
    assert value(result, "late_probability") == [1.0] * 3
    assert value(result, "revised_eta") == ["2026-10-27T17:00:00.000000Z"] * 3
    assert value(result, "forecast_sample_count") == [25] * 3
    health = [FeedHealth(feed, "trusted", tick, tick) for feed in REQUIRED_FEEDS]
    assessment = assess_order(result, tick_at=tick, feed_health=health)
    assert assessment.status == "at_risk"
    assert assessment.late_days == 0
    degraded = [FeedHealth(feed, "corrupt" if feed == "delivery_attempts" else "trusted", tick, tick)
                for feed in REQUIRED_FEEDS]
    assessment = assess_order(result, tick_at=tick, feed_health=degraded)
    assert assessment.status == "unknown_feed"
    assert assessment.revised_eta is None
    assert assessment.confidence == 0
