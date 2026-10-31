"""Internal assessed-order export for UI/API integration, without contact authority."""

from datetime import date
from typing import Iterable

from contracts.types import STATUSES

from .adapter import REQUIRED_FEEDS
from .models import FeedHealth, TickResult, aware, parse_instant, utc_iso
from .replay import ReplaySnapshot
from .service import assessment_payload, evidence_payload


def assessed_orders_payload(
    snapshot: ReplaySnapshot, result: TickResult, *, feed_health: Iterable[FeedHealth],
) -> dict:
    """Join one complete assessment tick to visible order metadata and provenance.

    This is an internal export. HTTP callers still authorize ownership, redact
    evidence, and check A3 heartbeat/controls immediately before proactive contact.
    Unusable feeds suppress source metadata, while evidence retains observed facts.
    Priority follows STATUSES (1 is highest); cause only projects assessed facts.
    Evidence references are JSON Pointers within this exact exported envelope.
    """
    tick_at = aware(snapshot.tick_at, "snapshot tick_at")
    health = {}
    for item in feed_health:
        if item.feed in health:
            raise ValueError("feed_health must contain one snapshot per feed")
        if item.checked_at > tick_at or (
            item.last_ingested_at is not None and item.last_ingested_at > tick_at
        ) or (
            item.source_timestamp is not None and item.source_timestamp > tick_at
        ):
            raise ValueError("feed_health cannot come from a future tick")
        health[item.feed] = item

    orders = {}
    created = {}
    for row in snapshot.orders:
        created_at = parse_instant(row["created_at"], "created_at")
        if created_at > tick_at:
            continue
        cancelled_at = row["cancelled_at"]
        if cancelled_at and parse_instant(cancelled_at, "cancelled_at") <= tick_at:
            continue
        order_id = row["order_id"]
        if order_id in orders:
            raise ValueError("snapshot must contain one visible row per order_id")
        orders[order_id], created[order_id] = row, created_at

    handovers = {}
    for row in snapshot.scans:
        if row["order_id"] not in orders or row["status"] != "handed_over":
            continue
        ingested_at = parse_instant(row["ingested_at"], "handover ingested_at")
        if ingested_at > tick_at:
            continue
        event_at = parse_instant(row["event_at"], "handover event_at")
        if event_at > tick_at:
            continue
        if event_at < created[row["order_id"]]:
            raise ValueError("handed_over event cannot precede order creation")
        candidate = (event_at, ingested_at, row["event_id"])
        previous = handovers.get(row["order_id"])
        if previous is None or candidate < previous:
            handovers[row["order_id"]] = candidate

    assessments = {}
    for assessment in result.assessments:
        if aware(assessment.assessed_at, "assessed_at") != tick_at:
            raise ValueError("assessment and source snapshot must use the same tick")
        if assessment.order_id in assessments:
            raise ValueError("result must contain one assessment per order_id")
        if any(aware(item["ingested_at"], "evidence ingested_at") > tick_at
               for item in assessment.evidence):
            raise ValueError("assessment evidence cannot come from a future tick")
        assessments[assessment.order_id] = assessment
    if assessments.keys() != orders.keys():
        raise ValueError("assessments must match all visible, non-cancelled source orders")

    def usable(feed: str) -> bool:
        return feed in health and health[feed].usable_at(tick_at)

    items = []
    for order_id, assessment in sorted(assessments.items()):
        if assessment.guaranteed_date != date.fromisoformat(orders[order_id]["guaranteed_date"]):
            raise ValueError("assessment guaranteed_date differs from source order")
        metadata_evidence = [dict(
            feed="orders", source_table="orders", record_id=order_id,
            ingested_at=created[order_id], fact_code="created_at",
            value=utc_iso(created[order_id]), is_structured=True,
        )]
        reasons = []
        created_at = utc_iso(created[order_id]) if usable("orders") else None
        if created_at is None:
            reasons.append("created_at_feed_unavailable")
        handed_over_at = None
        handover = handovers.get(order_id)
        if handover is None:
            reasons.append("handed_over_scan_missing")
        else:
            event_at, ingested_at, record_id = handover
            metadata_evidence.append(dict(
                feed="scan_events", source_table="scan_events", record_id=record_id,
                ingested_at=ingested_at, fact_code="handed_over_at",
                value=utc_iso(event_at), is_structured=True,
            ))
            if usable("orders") and usable("scan_events"):
                handed_over_at = utc_iso(event_at)
        if not (usable("orders") and usable("scan_events")):
            reasons.append("handed_over_at_feed_unavailable")
        metadata = {}
        for field, source_field in (("customer_id", "customer_id"), ("payment", "payment_method")):
            value = orders[order_id].get(source_field)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{source_field} must be a nonempty string or null")
                if field == "payment" and value not in ("COD", "PREPAID"):
                    raise ValueError("payment_method must be COD, PREPAID or null")
                metadata_evidence.append(dict(
                    feed="orders", source_table="orders", record_id=order_id,
                    ingested_at=created[order_id], fact_code=source_field,
                    value=value, is_structured=True,
                ))
            metadata[field] = value if usable("orders") else None
        items.append(dict(
            assessment_payload(assessment), created_at=created_at,
            handed_over_at=handed_over_at, metadata_reason_codes=reasons,
            metadata_evidence=evidence_payload(tuple(metadata_evidence)),
            **metadata, priority=STATUSES.index(assessment.status) + 1,
            cause=dict(fault_party=assessment.fault_party, reason_codes=list(assessment.reason_codes)),
            evidence_ref=f"#/orders/{len(items)}/evidence",
        ))

    feed_payloads = []
    for feed in sorted(set(REQUIRED_FEEDS) | health.keys()):
        item = health.get(feed)
        feed_payloads.append(dict(
            feed=feed, status=item.status if item else "missing",
            checked_at=utc_iso(item.checked_at) if item else None,
            source_timestamp=utc_iso(item.source_timestamp) if item and item.source_timestamp else None,
            last_ingested_at=utc_iso(item.last_ingested_at) if item and item.last_ingested_at else None,
            usable_at_tick=usable(feed),
        ))
    return dict(
        payload_version="a2_order_list_v1", tick_at=utc_iso(tick_at),
        feed_health=feed_payloads, orders=items,
    )
