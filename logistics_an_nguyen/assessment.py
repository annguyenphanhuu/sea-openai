"""Deterministic assessment of replay-visible, normalized logistics facts."""

from datetime import datetime, timezone
from math import isfinite
from typing import Iterable, get_args

from contracts.types import Evidence, FaultParty, OrderAssessment, STATUSES

from .models import (
    FeedHealth, OrderFacts, VIETNAM, aware, nonempty, parse_instant, probability,
)
from .replay import STAGES


FACT_CODES = frozenset({
    "exception", "fault_party", "delivered_at", "revised_eta",
    "late_probability", "confidence", "slow_safe", "logistics_stage", "stationary_ticks",
})


def _visible_evidence(order: OrderFacts, tick_at: datetime) -> tuple[Evidence, ...]:
    visible = []
    for item in order.evidence:
        if not isinstance(item, dict):
            raise ValueError("each evidence item must be a mapping")
        ingested_at = aware(item.get("ingested_at"), "evidence ingested_at")
        if ingested_at > tick_at:
            continue
        for key in ("feed", "source_table", "record_id", "fact_code"):
            nonempty(item.get(key), key)
        if type(item.get("is_structured")) is not bool:
            raise ValueError("is_structured must be a boolean")
        if "value" not in item:
            raise ValueError("evidence value is required")
        value = item["value"]
        if value is not None and type(value) not in (str, int, float, bool):
            raise ValueError("evidence value must be a JSON scalar")
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("evidence value must be finite")
        visible.append({key: item[key] for key in Evidence.__annotations__})
    return tuple(sorted(visible, key=lambda item: (
        item["ingested_at"], item["feed"], item["source_table"],
        item["record_id"], item["fact_code"], repr(item["value"]),
        item["is_structured"],
    )))


def _fact_value(item: Evidence) -> object:
    code, value = item["fact_code"], item["value"]
    # Null explicitly clears an earlier fact; absence does not resurrect it.
    if value is None:
        return None
    if code in ("exception", "slow_safe"):
        if type(value) is not bool:
            raise ValueError(f"{code} must be a boolean")
    elif code in ("late_probability", "confidence"):
        return probability(value, code)
    elif code == "fault_party":
        if value not in get_args(FaultParty):
            raise ValueError("invalid fault_party")
    elif code in ("delivered_at", "revised_eta"):
        return parse_instant(value, code)
    elif code == "logistics_stage" and value not in STAGES:
        raise ValueError("invalid logistics_stage")
    elif code == "stationary_ticks" and (type(value) is not int or value < 0):
        raise ValueError("stationary_ticks must be a nonnegative integer")
    return value


def assess_order(
    order: OrderFacts, *, tick_at: datetime, feed_health: Iterable[FeedHealth],
) -> OrderAssessment:
    """Assess one visible order; never send contacts or execute actions."""
    aware(tick_at, "tick_at")
    if order.ingested_at > tick_at:
        raise ValueError("order is not yet visible at this replay tick")
    health = {}
    for item in feed_health:
        if item.feed in health:
            raise ValueError("feed_health must contain one snapshot per feed")
        health[item.feed] = item
    evidence = _visible_evidence(order, tick_at)
    reasons = []
    unavailable = set()
    # Include every contributing feed, even if the adapter omitted it from required_feeds.
    feeds = set(order.required_feeds) | {
        item["feed"] for item in evidence if item["is_structured"]
    }
    for feed in sorted(feeds):
        item = health.get(feed)
        if item is None:
            reasons.append(f"feed_missing:{feed}")
            unavailable.add(feed)
        elif item.status != "trusted":
            reasons.append(f"feed_{item.status}:{feed}")
            unavailable.add(feed)
        elif not item.usable_at(tick_at):
            reasons.append(f"feed_snapshot_invalid:{feed}")
            unavailable.add(feed)

    latest: dict[str, list[Evidence]] = {}
    for item in evidence:
        code = item["fact_code"]
        if not item["is_structured"] or code not in FACT_CODES:
            continue
        if code not in latest or item["ingested_at"] > latest[code][0]["ingested_at"]:
            latest[code] = [item]
        elif item["ingested_at"] == latest[code][0]["ingested_at"]:
            latest[code].append(item)

    facts = {}
    conflicts = []
    for code, items in sorted(latest.items()):
        values = [_fact_value(item) for item in items]
        if any(value != values[0] for value in values[1:]):
            conflicts.append(code)
            reasons.append(f"conflicting_fact:{code}")
        elif any(item["feed"] in unavailable for item in items):
            reasons.append(f"untrusted_fact:{code}")
        else:
            facts[code] = values[0]

    delivered_at = facts.get("delivered_at")
    if delivered_at is not None and delivered_at > tick_at:
        raise ValueError("delivered_at cannot be later than tick_at")
    reference = delivered_at or tick_at
    late_days = max(0, (reference.astimezone(VIETNAM).date() - order.guaranteed_date).days)
    if late_days:
        reasons.append("guaranteed_day_exceeded")
    if delivered_at is not None:
        reasons.append("delivery_confirmed")

    forecast_missing = facts.get("late_probability") is None and not (
        late_days or delivered_at is not None
    )
    if late_days or delivered_at is not None:
        late_probability = float(late_days > 0)
    else:
        # Contract v0 has no nullable probability. This sentinel is never on_track.
        late_probability = facts.get("late_probability") or 0.0
    if forecast_missing:
        reasons.append("risk_estimate_missing")

    fault_party = facts.get("fault_party") or "unknown"
    reasons.append(f"fault:{fault_party}")
    revised_eta = facts.get("revised_eta") if delivered_at is None else None
    if revised_eta is not None and revised_eta < tick_at:
        revised_eta = None
        reasons.append("eta_expired")
    if revised_eta is not None:
        reasons.append("eta_from_structured_evidence")
    elif delivered_at is None:
        reasons.append("eta_missing")

    confidence = facts.get("confidence") or 0.0
    if facts.get("confidence") is None:
        reasons.append("confidence_missing")
    if unavailable or conflicts or forecast_missing:
        confidence = 0.0
    if any(not item["is_structured"] for item in evidence):
        confidence = min(confidence, 0.5)
        reasons.append("unstructured_text_unverified")

    active = delivered_at is None
    predicates = {
        "exception": facts.get("logistics_stage") in ("lost", "damaged", "return_failed"),
        "unknown_feed": bool(unavailable or conflicts),
        "customer_fault": fault_party == "customer",
        "late": late_days > 0,
        "at_risk": active and revised_eta is not None and revised_eta.astimezone(VIETNAM).date() > order.guaranteed_date,
        "watch": active and (facts.get("stationary_ticks") or 0) >= 2,
        "slow_safe": active and facts.get("slow_safe") is True and revised_eta is not None
        and revised_eta.astimezone(VIETNAM).date() <= order.guaranteed_date,
        "on_track": True,
    }
    status = next(status for status in STATUSES if predicates[status])
    reasons.insert(0, f"status:{status}")
    return OrderAssessment(
        order_id=order.order_id, assessed_at=tick_at.astimezone(timezone.utc),
        status=status, guaranteed_date=order.guaranteed_date,
        revised_eta=revised_eta.astimezone(timezone.utc) if revised_eta else None,
        late_days=late_days, late_probability=late_probability,
        confidence=confidence, fault_party=fault_party,
        reason_codes=tuple(reasons), evidence=evidence,
    )
