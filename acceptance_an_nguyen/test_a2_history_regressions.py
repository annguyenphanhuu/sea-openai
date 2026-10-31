"""Independent regression checks for A2's visible-history training boundary."""

from datetime import datetime

import pytest

from logistics_an_nguyen import FeedHealth, ReleaseAdapter, assess_order
from logistics_an_nguyen.adapter import REQUIRED_FEEDS
from logistics_an_nguyen.replay import ReplaySnapshot


TICK = datetime.fromisoformat("2026-10-28T12:00:00+07:00")


def order_row(**changes):
    return dict(order_id="history", created_at="2026-10-27T00:00:00+07:00",
                guaranteed_date="2026-10-29", carrier_id="carrier",
                service_level="standard", cancelled_at=None) | changes


def scan_row(status, event_at, **changes):
    return dict(event_id=status, order_id="history", status=status,
                event_at=event_at, ingested_at=event_at, carrier_event_id=None,
                location_type="station", location_id="s1") | changes


def attempt_row(at, **changes):
    return dict(attempt_id="delivery", order_id="history", attempt_no=1,
                attempt_at=at, outcome="delivered", reason_code=None,
                call_attempts=0) | changes


@pytest.mark.parametrize("terminal", [
    "cancelled", "returning", "returned", "waiting_to_return", "lost", "damaged", "return_failed",
])
@pytest.mark.parametrize("delivery_source", ["scan", "attempt"])
def test_training_censors_at_terminal_before_later_delivery(terminal, delivery_source):
    """A later delivery must not turn an earlier terminal event into training success."""
    end = "2026-10-27T10:00:00+07:00"
    delivery = "2026-10-27T20:00:00+07:00"
    order = order_row(cancelled_at=end if terminal == "cancelled" else None)
    scans = [] if terminal == "cancelled" else [scan_row(terminal, end)]
    attempts = []
    if delivery_source == "scan":
        scans.append(scan_row("delivered", delivery))
    else:
        attempts.append(attempt_row(delivery))
    adapter = ReleaseAdapter(ReplaySnapshot(TICK, (order,), tuple(scans), tuple(attempts), ()))
    sample = adapter.curves[("carrier", "standard", "created")].samples[0]
    assert (sample.order_id, sample.seconds, sample.delivered) == ("history", 36000, False)


def test_delivery_before_later_return_remains_a_training_delivery():
    snapshot = ReplaySnapshot(TICK, (order_row(),), (
        scan_row("delivered", "2026-10-27T10:00:00+07:00"),
        scan_row("returning", "2026-10-27T20:00:00+07:00"),
    ), (), ())
    sample = ReleaseAdapter(snapshot).curves[("carrier", "standard", "created")].samples[0]
    assert (sample.seconds, sample.delivered) == (36000, True)


def test_terminal_delivery_tie_is_not_a_training_success():
    at = "2026-10-27T10:00:00+07:00"
    snapshot = ReplaySnapshot(TICK, (order_row(cancelled_at=at),), (), (attempt_row(at),), ())
    sample = ReleaseAdapter(snapshot).curves[("carrier", "standard", "created")].samples[0]
    assert (sample.seconds, sample.delivered) == (36000, False)


def test_stages_after_terminal_do_not_reenter_forecast_training():
    snapshot = ReplaySnapshot(TICK, (order_row(),), (
        scan_row("returning", "2026-10-27T10:00:00+07:00"),
        scan_row("station", "2026-10-27T15:00:00+07:00"),
        scan_row("delivered", "2026-10-27T20:00:00+07:00"),
    ), (), ())
    adapter = ReleaseAdapter(snapshot)
    assert ("carrier", "standard", "station") not in adapter.curves


def test_attempt_order_does_not_change_customer_fault():
    failed = attempt_row("2026-10-28T08:00:00+07:00", attempt_id="failed", attempt_no=1,
                         outcome="no_answer", reason_code="customer_unreachable", call_attempts=3)
    delivered = attempt_row("2026-10-28T10:00:00+07:00", attempt_no=2)
    health = tuple(FeedHealth(feed, "trusted", TICK, TICK) for feed in REQUIRED_FEEDS)
    results = []
    for attempts in ((failed, delivered), (delivered, failed)):
        snapshot = ReplaySnapshot(TICK, (order_row(),), (), attempts, ())
        facts = ReleaseAdapter(snapshot).orders()[0]
        results.append(assess_order(facts, tick_at=TICK, feed_health=health))
    assert results[0] == results[1]
    assert results[0].fault_party == "unknown"


@pytest.mark.parametrize("future_field", ["created_at", "cancelled_at", "scan_ingestion", "scan_event", "attempt", "report"])
def test_adapter_rejects_unfiltered_future_snapshot(future_field):
    """A custom platform projection must not let future rows influence today's cohort."""
    future = "2026-10-29T00:00:00+07:00"
    order, scans, attempts, reports = order_row(), (), (), ()
    if future_field in ("created_at", "cancelled_at"):
        order = order_row(**{future_field: future})
    elif future_field.startswith("scan"):
        scan = scan_row("station", "2026-10-28T10:00:00+07:00")
        scan["ingested_at" if future_field == "scan_ingestion" else "event_at"] = future
        scans = (scan,)
    elif future_field == "attempt":
        attempts = (attempt_row(future),)
    else:
        reports = (dict(report_id="r1", trip_id="trip", reported_at=future,
                        reason_code="weather", driver_note="future", reported_by="driver"),)
    with pytest.raises(ValueError, match="snapshot|future|tick"):
        ReleaseAdapter(ReplaySnapshot(TICK, (order,), scans, attempts, reports))


def test_terminal_histories_cannot_supply_the_minimum_delivery_support():
    orders, scans, attempts = [], [], []
    for index in range(25):
        order_id = f"history-{index}"
        orders.append(order_row(order_id=order_id))
        scans.append(scan_row("returning", "2026-10-27T10:00:00+07:00",
                              order_id=order_id, event_id=f"return-{index}"))
        attempts.append(attempt_row("2026-10-27T20:00:00+07:00",
                                    order_id=order_id, attempt_id=f"delivery-{index}"))
    orders.append(order_row(order_id="target", created_at="2026-10-28T09:00:00+07:00",
                            guaranteed_date="2026-10-28"))
    adapter = ReleaseAdapter(ReplaySnapshot(TICK, tuple(orders), tuple(scans), tuple(attempts), ()))
    target = next(order for order in adapter.orders() if order.order_id == "target")
    assert not any(item["fact_code"] in ("forecast_method", "revised_eta", "late_probability")
                   for item in target.evidence)
