"""Two consecutive replay intervals, retries, changed stage and unhealthy gaps."""

from datetime import timedelta

import pytest

from logistics_an_nguyen import FeedHealth, ProgressTracker, assess_order


def trusted(at):
    return [FeedHealth(feed, "trusted", at, at) for feed in ("core", "ops")]


def test_watch_requires_two_unchanged_intervals_and_retry_does_not_count(tick, order):
    tracker = ProgressTracker()
    for minutes, expected in [(0, "on_track"), (30, "on_track"), (30, "on_track"), (60, "watch")]:
        at = tick + timedelta(minutes=minutes)
        health = trusted(at)
        snapshot = tracker.apply([order()], tick_at=at, feed_health=health)[0]
        assert assess_order(snapshot, tick_at=at, feed_health=health).status == expected
    restored = ProgressTracker(tracker.records)
    at = tick + timedelta(minutes=60)
    assert restored.apply([order()], tick_at=at, feed_health=trusted(at)) == (snapshot,)


def test_changed_stage_unhealthy_or_skipped_tick_resets_watch(tick, order, fact):
    for interruption in ("stage", "health", "gap"):
        tracker = ProgressTracker()
        tracker.apply([order()], tick_at=tick, feed_health=trusted(tick))
        at = tick + timedelta(minutes=30)
        tracker.apply([order()], tick_at=at, feed_health=trusted(at))
        at += timedelta(minutes=60 if interruption == "gap" else 30)
        current = order(fact("logistics_stage", "station")) if interruption == "stage" else order()
        health = [] if interruption == "health" else trusted(at)
        result = tracker.apply([current], tick_at=at, feed_health=health)[0]
        assert all(e["value"] == 0 for e in result.evidence if e["fact_code"] == "stationary_ticks")


def test_rewind_needs_separate_progress_state(tick, order):
    tracker = ProgressTracker()
    tracker.apply([order()], tick_at=tick + timedelta(minutes=30), feed_health=trusted(tick))
    with pytest.raises(ValueError, match="rewind"):
        tracker.apply([order()], tick_at=tick, feed_health=trusted(tick))


def test_slow_safe_requires_an_eta_within_guaranteed_day(tick, order, fact):
    health = trusted(tick)
    for eta, status in [(None, "on_track"), ("2026-11-01T22:00:00+07:00", "slow_safe"),
                        ("2026-11-02T00:00:00+07:00", "at_risk")]:
        result = assess_order(order(fact("slow_safe", True), fact("revised_eta", eta)),
                              tick_at=tick, feed_health=health)
        assert result.status == status


def test_recent_ingestion_and_audit_do_not_refresh_old_source(tick, order):
    health = [FeedHealth(feed, "trusted", tick, tick - timedelta(minutes=31), tick)
              for feed in ("core", "ops")]
    assert assess_order(order(), tick_at=tick, feed_health=health).status == "unknown_feed"
