"""Boundaries and read-only source integration for the supplementary COD signal."""

from datetime import date, datetime, timedelta
from hashlib import sha256
import sqlite3

import pytest

from logistics_an_nguyen import FeedHealth, ReleaseAdapter, ReleaseReader, assess_order, evaluate_tick
from logistics_an_nguyen.adapter import REQUIRED_FEEDS


@pytest.mark.parametrize(("amount", "expected"), [
    (999_999, "cod_refusal_risk:medium"), (1_000_000, "cod_refusal_risk:high"),
    (None, "cod_refusal_risk:medium"), (True, "cod_refusal_risk:medium"),
    (1_000_000.0, "cod_refusal_risk:medium"),
])
def test_high_value_boundary_uses_integer_source_value(amount, expected, tick, fact, order, health):
    assessment = assess_order(order(
        fact("payment_method", "COD"), fact("items_value_vnd", amount),
        guaranteed_date=date(2026, 10, 31),
    ), tick_at=tick, feed_health=health)
    assert assessment.status == "late"
    assert tuple(code for code in assessment.reason_codes if code.startswith("cod_refusal_risk")) == (expected,)


@pytest.mark.parametrize("input_kind", ["future_failure", "driver_text", "future_value", "conflicting_payment"])
def test_unsafe_risk_inputs_cannot_promote_or_change_logistics(input_kind, tick, fact, order, health):
    facts = [fact("payment_method", "COD"), fact("items_value_vnd", 250_000)]
    expected = ("cod_refusal_risk:medium",)
    if input_kind == "future_failure":
        facts.append(fact("failed_delivery_attempt", True, ingested_at=tick + timedelta(seconds=1)))
    elif input_kind == "driver_text":
        facts.append(fact("failed_delivery_attempt", True, structured=False))
    elif input_kind == "future_value":
        facts.append(fact("items_value_vnd", 1_200_000, ingested_at=tick + timedelta(seconds=1)))
    else:
        facts.append(fact("payment_method", "PREPAID", record_id="conflicting-payment"))
        expected = ()
    assessment = assess_order(order(*facts, guaranteed_date=date(2026, 10, 31)),
                              tick_at=tick, feed_health=health)
    assert assessment.status == "late"
    assert assessment.fault_party == "unknown"
    assert assessment.late_days == 1
    assert tuple(code for code in assessment.reason_codes if code.startswith("cod_refusal_risk")) == expected


def test_untrusted_payment_cannot_produce_a_cod_badge(tick, fact, order, health):
    assessment = assess_order(order(
        fact("payment_method", "COD", structured=False), fact("items_value_vnd", 1_200_000),
        guaranteed_date=date(2026, 10, 31),
    ), tick_at=tick, feed_health=health)
    assert assessment.status == "late"
    assert not any(code.startswith("cod_refusal_risk") for code in assessment.reason_codes)


@pytest.mark.parametrize(("attempt_at", "expected"), [
    ("2026-10-28T11:00:00+07:00", "cod_refusal_risk:high"),
    ("2026-10-28T12:00:01+07:00", "cod_refusal_risk:medium"),
])
def test_source_attempt_signal_obeys_cutoff_and_retains_record_provenance(tmp_path, attempt_at, expected):
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE orders(order_id,created_at,guaranteed_date,carrier_id,service_level,cancelled_at,
                                customer_id,payment_method,items_value_vnd);
            CREATE TABLE scan_events(event_id,order_id,status,location_type,location_id,event_at,ingested_at,carrier_event_id);
            CREATE TABLE delivery_attempts(attempt_id,order_id,attempt_no,attempt_at,outcome,reason_code,call_attempts);
            CREATE TABLE linehaul_reports(report_id,trip_id,reported_at,reported_by,reason_code,driver_note);
            INSERT INTO orders VALUES ('o1','2026-10-27T09:00:00+07:00','2026-10-27','c1','standard',NULL,'u1','COD',250000);
        """)
        db.execute("INSERT INTO delivery_attempts VALUES ('failed-1','o1',1,?,'other',NULL,0)", (attempt_at,))
    before = sha256(path.read_bytes()).hexdigest()
    tick = datetime.fromisoformat("2026-10-28T12:00:00+07:00")
    with ReleaseReader(path) as reader:
        snapshot = reader.snapshot(tick)
    assert snapshot.orders[0]["items_value_vnd"] == 250_000
    health = tuple(FeedHealth(feed, "trusted", tick, tick) for feed in REQUIRED_FEEDS)
    assessment = evaluate_tick(ReleaseAdapter(snapshot).orders(), tick_at=tick, feed_health=health).assessments[0]
    assert assessment.status == "late"
    assert assessment.fault_party == "unknown"
    assert tuple(code for code in assessment.reason_codes if code.startswith("cod_refusal_risk")) == (expected,)
    failure = [item for item in assessment.evidence if item["fact_code"] == "failed_delivery_attempt"]
    if expected == "cod_refusal_risk:high":
        assert failure == [dict(feed="delivery_attempts", source_table="delivery_attempts", record_id="failed-1",
                                ingested_at=datetime.fromisoformat(attempt_at), fact_code="failed_delivery_attempt",
                                value=True, is_structured=True)]
    else:
        assert failure == []
    assert sha256(path.read_bytes()).hexdigest() == before
