"""Replay-tick progress state for D2's two stationary 30-minute intervals."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Iterable

from contracts.params import tick_min

from .models import FeedHealth, OrderFacts, parse_instant, utc_iso


class ProgressTracker:
    """Caller persists payload under runs/ after a successful tick, never in sources."""

    def __init__(self, records: dict | None = None) -> None:
        self.records = dict(records or {})

    def apply(self, orders: Iterable[OrderFacts], *, tick_at: datetime,
              feed_health: Iterable[FeedHealth]) -> tuple[OrderFacts, ...]:
        health = {item.feed: item for item in feed_health}
        result, next_records = [], {}
        for order in orders:
            facts = {e["fact_code"]: e["value"] for e in order.evidence
                     if e["is_structured"] and e["ingested_at"] <= tick_at}
            key = [facts.get("logistics_stage", "created"), facts.get("stage_location")]
            trusted = all(feed in health and health[feed].usable_at(tick_at) for feed in order.required_feeds)
            previous = self.records.get(order.order_id)
            count = 0
            if previous:
                previous_tick = parse_instant(previous["tick_at"], "previous tick")
                if previous_tick > tick_at:
                    raise ValueError("progress state is ahead of tick; use a separate run for rewind")
                if trusted and previous["trusted"] and previous["stage"] == key:
                    gap = tick_at - previous_tick
                    if gap == timedelta(0):
                        count = previous["stationary_ticks"]
                    elif gap == timedelta(minutes=tick_min):
                        count = min(2, previous["stationary_ticks"] + 1)
            if "delivered_at" in facts:
                count = 0
            next_records[order.order_id] = dict(
                tick_at=utc_iso(tick_at), stage=key, trusted=trusted, stationary_ticks=count,
            )
            # Publish once for every dependency so unavailable inputs cannot create watch.
            additions = tuple(dict(
                feed=feed, source_table="a2_tick_progress", record_id=order.order_id,
                ingested_at=tick_at, fact_code="stationary_ticks", value=count, is_structured=True,
            ) for feed in order.required_feeds)
            result.append(replace(order, evidence=order.evidence + additions))
        self.records = next_records
        return tuple(result)
