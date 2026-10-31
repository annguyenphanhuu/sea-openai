"""Normalize replay projections into the A2 API and fit a visible-history baseline."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import json
from statistics import median

from contracts.types import Evidence

from .forecast import Observation, SurvivalCurve
from .models import OrderFacts, VIETNAM, aware, parse_instant, utc_iso
from .replay import ReplaySnapshot, TERMINAL, deduplicate_scans, grouped, handover_milestones


REQUIRED_FEEDS = ("orders", "scan_events", "delivery_attempts")


def _evidence(feed: str, record_id: str, ingested_at: datetime, code: str,
              value: str | float | int | bool | None, *, structured: bool = True,
              table: str | None = None) -> Evidence:
    return dict(feed=feed, source_table=table or feed, record_id=record_id,
                ingested_at=ingested_at, fact_code=code, value=value, is_structured=structured)


class ReleaseAdapter:
    """All timestamps used for fitting and inference are at or before snapshot.tick_at."""

    def __init__(self, snapshot: ReplaySnapshot) -> None:
        tick_at = aware(snapshot.tick_at, "snapshot tick_at")
        # Custom platform projections must satisfy the same cutoff as ReleaseReader.
        # Validate before fitting: future labels can otherwise become tick-time forecasts.
        for rows, fields in (
            (snapshot.orders, ("created_at", "cancelled_at")),
            (snapshot.scans, ("event_at", "ingested_at")),
            (snapshot.attempts, ("attempt_at",)),
            (snapshot.reports, ("reported_at",)),
        ):
            for row in rows:
                for field in fields:
                    if field == "cancelled_at" and row[field] is None:
                        continue
                    if parse_instant(row[field], field) > tick_at:
                        raise ValueError(f"snapshot {field} exceeds tick_at")
        self.snapshot = snapshot
        self.scan_records = {row["event_id"]: row for row in snapshot.scans}
        self.handovers = handover_milestones(snapshot.scans, {
            row["order_id"]: parse_instant(row["created_at"], "created_at")
            for row in snapshot.orders if not row["cancelled_at"]
        }, tick_at)
        scans = grouped(snapshot.scans, "order_id")
        self.scans = {key: deduplicate_scans(rows) for key, rows in scans.items()}
        self.attempts = grouped(tuple(sorted(snapshot.attempts, key=lambda row: (
            parse_instant(row["attempt_at"], "attempt_at"), row["attempt_id"],
        ))), "order_id")
        self.reports = grouped(snapshot.reports, "trip_id")
        self.histories = {}
        cohorts = defaultdict(list)
        dwell_times = defaultdict(list)
        for order in snapshot.orders:
            order_id = order["order_id"]
            history = self.scans.get(order_id, [])
            delivery = [(row["event_at"], row["ingested_at"], "scan_events", row["event_id"])
                        for row in history if row["status"] == "delivered"]
            delivery += [(row["attempt_at"], row["attempt_at"], "delivery_attempts", row["attempt_id"])
                         for row in self.attempts.get(order_id, []) if row["outcome"] == "delivered"]
            delivered = min(delivery) if delivery else None
            terminal_times = [row["event_at"] for row in history
                              if row["status"] in TERMINAL and row["status"] != "delivered"]
            if order["cancelled_at"]:
                terminal_times.append(order["cancelled_at"])
            terminal_at = min((datetime.fromisoformat(value) for value in terminal_times), default=None)
            delivered_at = datetime.fromisoformat(delivered[0]) if delivered else None
            training_delivery = delivered_at is not None and (
                terminal_at is None or delivered_at < terminal_at
            )
            end = min(value for value in (tick_at, terminal_at, delivered_at) if value is not None)
            training_history = [row for row in history if datetime.fromisoformat(row["event_at"]) <= end]
            stages = {"created": datetime.fromisoformat(order["created_at"])}
            for row in training_history:
                if row["status"] not in TERMINAL:
                    stages[row["status"]] = datetime.fromisoformat(row["event_at"])
            previous_stage, previous_at = "created", datetime.fromisoformat(order["created_at"])
            for row in training_history:
                event_at = datetime.fromisoformat(row["event_at"])
                if row["status"] != previous_stage:
                    dwell_times[(order["carrier_id"], order["service_level"], previous_stage)].append(
                        (event_at - previous_at).total_seconds()
                    )
                    previous_stage, previous_at = row["status"], event_at
            self.histories[order_id] = (history, delivered, stages)
            for stage, started in stages.items():
                seconds = (end - started).total_seconds()
                if seconds < 0:
                    continue
                key = (order["carrier_id"], order["service_level"], stage)
                cohorts[key].append(Observation(order_id, seconds, training_delivery))
        self.curves = {key: SurvivalCurve(samples) for key, samples in cohorts.items()}
        self.stage_medians = {key: median(values) for key, values in dwell_times.items() if len(values) >= 20}

    def orders(self) -> tuple[OrderFacts, ...]:
        """Omit cancelled orders; terminal logistics exceptions remain reviewable."""
        result = []
        tick_at = self.snapshot.tick_at
        for order in self.snapshot.orders:
            if order["cancelled_at"]:
                continue
            order_id = order["order_id"]
            created_at = datetime.fromisoformat(order["created_at"])
            guaranteed = date.fromisoformat(order["guaranteed_date"])
            history, delivered, stages = self.histories[order_id]
            last = history[-1] if history else None
            stage = last["status"] if last else "created"
            evidence = [_evidence("orders", order_id, created_at, "guaranteed_date", guaranteed.isoformat())]
            evidence.append(_evidence("orders", order_id, created_at, "created_at", utc_iso(created_at)))
            if self.snapshot.seller_prepare_days is not None:
                # Static release policy is available with the order, not a live feed.
                evidence.append(_evidence(
                    "orders", "seller_prepare_days", created_at, "seller_prepare_days",
                    self.snapshot.seller_prepare_days, table="policy",
                ))
            if order_id in self.handovers:
                event_at, ingested_at, record_id = self.handovers[order_id]
                evidence.append(_evidence(
                    "scan_events", record_id, ingested_at, "handed_over_at", utc_iso(event_at),
                ))
                evidence.append(_evidence(
                    "scan_events", record_id, ingested_at, "handed_over_scan",
                    json.dumps(self.scan_records[record_id], ensure_ascii=False, sort_keys=True),
                ))
            for code in ("payment_method", "items_value_vnd"):
                if order.get(code) is not None:
                    evidence.append(_evidence("orders", order_id, created_at, code, order[code]))
            if last:
                seen = datetime.fromisoformat(last["ingested_at"])
                evidence += [
                    _evidence("scan_events", last["event_id"], seen, "logistics_stage", stage),
                    _evidence("scan_events", last["event_id"], seen, "stage_event_at", last["event_at"]),
                    _evidence("scan_events", last["event_id"], seen, "stage_location", last["location_id"]),
                ]
                if stage in ("lost", "damaged", "return_failed"):
                    evidence.append(_evidence("scan_events", last["event_id"], seen, "exception", True))
                if stage in ("lost", "damaged"):
                    fault = "platform" if last["location_type"] == "warehouse" else (
                        "carrier" if last["location_type"] in ("station", "trip", "sorting_center") else "unknown"
                    )
                    evidence.append(_evidence("scan_events", last["event_id"], seen, "fault_party", fault))
            if delivered:
                at, ingested, feed, record_id = delivered
                evidence += [
                    _evidence(feed, record_id, datetime.fromisoformat(ingested), "delivered_at", at),
                    _evidence(feed, record_id, datetime.fromisoformat(ingested), "confidence", 1.0),
                ]
            attempts = self.attempts.get(order_id, [])
            for failed in attempts:
                if failed["outcome"] in ("no_answer", "rescheduled", "refused", "wrong_address", "other"):
                    seen = datetime.fromisoformat(failed["attempt_at"])
                    evidence += [
                        _evidence("delivery_attempts", failed["attempt_id"], seen, "failed_delivery_attempt", True),
                        _evidence("delivery_attempts", failed["attempt_id"], seen, "attempt_outcome", failed["outcome"]),
                    ]
            if attempts:
                attempt = attempts[-1]
                seen = datetime.fromisoformat(attempt["attempt_at"])
                reason, calls = attempt["reason_code"], attempt["call_attempts"] or 0
                evidence += [_evidence("delivery_attempts", attempt["attempt_id"], seen, code, value)
                             for code, value in (("attempt_reason", reason), ("call_attempts", calls))]
                customer_fault = (
                    (attempt["outcome"] == "no_answer" and reason == "customer_unreachable" and calls >= 3)
                    or (attempt["outcome"] == "refused" and reason == "customer_refused" and calls >= 1)
                    or (attempt["outcome"] == "rescheduled" and reason == "reschedule_requested" and calls >= 1)
                )
                if customer_fault and stage not in ("lost", "damaged"):
                    evidence.append(_evidence("delivery_attempts", attempt["attempt_id"], seen, "fault_party", "customer"))

            if not delivered and stage not in TERMINAL and stage in stages:
                deadline = datetime.combine(guaranteed + timedelta(days=1), time.min, VIETNAM)
                # Already-late orders still need an ETA; their probability is factual in A2.
                remaining = max(0.0, (deadline - tick_at).total_seconds() - 0.000001)
                curve = self.curves[(order["carrier_id"], order["service_level"], stage)]
                forecast = curve.predict(age_seconds=(tick_at - stages[stage]).total_seconds(),
                                         remaining_seconds=remaining, tick_at=tick_at)
                if forecast:
                    values = {"late_probability": forecast.late_probability,
                              "confidence": forecast.confidence,
                              "revised_eta": utc_iso(forecast.revised_eta) if forecast.revised_eta else None,
                              "forecast_sample_count": forecast.sample_count,
                              "forecast_delivered_count": forecast.delivered_count,
                              "forecast_method": "kaplan_meier_carrier_service_stage_v1"}
                    normal_dwell = self.stage_medians.get((order["carrier_id"], order["service_level"], stage))
                    if normal_dwell is not None:
                        values["slow_safe"] = (tick_at - stages[stage]).total_seconds() > normal_dwell
                    # Derived results depend on all three feeds, not just the final scan.
                    for feed in REQUIRED_FEEDS:
                        evidence += [_evidence(feed, forecast.cohort_id, tick_at, code, value,
                                               table="a2_survival_v1") for code, value in values.items()]

            # Keep trip provenance after arrival or later stages. Claims remain
            # unverified regardless of how structured a reported reason appears.
            trip_scans = {}
            for scan in history:
                if scan["location_type"] == "trip" and scan["status"] in ("linehaul_departed", "linehaul_arrived"):
                    trip_scans.setdefault(scan["location_id"], scan)
            for trip_id, scan in sorted(trip_scans.items()):
                evidence.append(_evidence(
                    "scan_events", scan["event_id"], datetime.fromisoformat(scan["ingested_at"]),
                    "linehaul_trip_id", trip_id,
                ))
                for report in self.reports.get(trip_id, []):
                    seen = datetime.fromisoformat(report["reported_at"])
                    evidence += [
                        _evidence("linehaul_reports", report["report_id"], seen, "linehaul_report",
                                  json.dumps(report, ensure_ascii=False, sort_keys=True), structured=False),
                        _evidence("linehaul_reports", report["report_id"], seen, "driver_report",
                                  (report["reason_code"] or "") + ": " + (report["driver_note"] or ""),
                                  structured=False),
                    ]
            result.append(OrderFacts(order_id, guaranteed, created_at, REQUIRED_FEEDS, tuple(evidence)))
        return tuple(result)
