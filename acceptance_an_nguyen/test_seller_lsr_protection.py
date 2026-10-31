"""The three literal seller-protection cases requested in the review."""

from datetime import datetime
import json

from logistics_an_nguyen import FeedHealth, ReleaseAdapter, ReplaySnapshot, assess_order


TICK = datetime.fromisoformat("2026-10-28T12:00:00+07:00")


def reviewed_order(*, handed_over_at: str, customer_refused: bool = False):
    source = ReplaySnapshot(
        tick_at=TICK,
        orders=(dict(order_id="review-order", created_at="2026-10-24T10:00:00+07:00",
                     guaranteed_date="2026-10-27", carrier_id="carrier-1",
                     service_level="standard", cancelled_at=None),),
        scans=(
            dict(event_id="handover-1", order_id="review-order", status="handed_over",
                 location_type="seller", location_id="shop-1", event_at=handed_over_at,
                 ingested_at=handed_over_at, carrier_event_id=None),
            dict(event_id="departure-1", order_id="review-order", status="linehaul_departed",
                 location_type="trip", location_id="trip-1", event_at="2026-10-27T01:00:00+07:00",
                 ingested_at="2026-10-27T01:00:00+07:00", carrier_event_id=None),
            dict(event_id="station-1", order_id="review-order", status="station",
                 location_type="station", location_id="station-1", event_at="2026-10-27T05:00:00+07:00",
                 ingested_at="2026-10-27T05:00:00+07:00", carrier_event_id=None),
        ),
        attempts=(dict(attempt_id="attempt-1", order_id="review-order", attempt_no=1,
                       attempt_at="2026-10-28T11:00:00+07:00", outcome="refused",
                       reason_code="customer_refused", call_attempts=1),) if customer_refused else (),
        reports=(dict(report_id="report-1", trip_id="trip-1", reported_at="2026-10-27T02:00:00+07:00",
                      reported_by="driver", reason_code="traffic", driver_note="Trip delayed"),),
        seller_prepare_days=2,
    )
    facts = ReleaseAdapter(source).orders()[0]
    health = tuple(FeedHealth(feed, "trusted", TICK, TICK)
                   for feed in ("orders", "scan_events", "delivery_attempts"))
    return assess_order(facts, tick_at=TICK, feed_health=health)


def test_carrier_has_literal_exemption_reason_and_source_rows():
    assessment = reviewed_order(handed_over_at="2026-10-26T10:00:00+07:00")
    assert assessment.fault_party == "carrier"
    assert "lsr_exempt:carrier" in assessment.reason_codes
    assert "fault:carrier" in assessment.reason_codes
    scan = next(e for e in assessment.evidence if e["fact_code"] == "handed_over_scan")
    report = next(e for e in assessment.evidence if e["fact_code"] == "linehaul_report")
    assert scan["source_table"] == "scan_events"
    assert scan["record_id"] == "handover-1"
    assert json.loads(scan["value"])["status"] == "handed_over"
    assert report["source_table"] == "linehaul_reports"
    assert report["record_id"] == "report-1"
    assert json.loads(report["value"])["trip_id"] == "trip-1"
    assert report["is_structured"] is False


def test_seller_has_literal_fault_and_no_exemption():
    assessment = reviewed_order(handed_over_at="2026-10-26T10:00:01+07:00")
    assert assessment.fault_party == "seller"
    assert "fault:seller" in assessment.reason_codes
    assert "lsr_exempt:carrier" not in assessment.reason_codes
    assert not any(reason.startswith("lsr_exempt") for reason in assessment.reason_codes)


def test_customer_refusal_with_one_call_keeps_literal_customer_fault():
    assessment = reviewed_order(handed_over_at="2026-10-26T10:00:00+07:00", customer_refused=True)
    assert assessment.fault_party == "customer"
    assert assessment.status == "customer_fault"
    assert "fault:customer" in assessment.reason_codes
    assert "lsr_exempt:carrier" not in assessment.reason_codes
    assert next(e["value"] for e in assessment.evidence if e["fact_code"] == "call_attempts") == 1
