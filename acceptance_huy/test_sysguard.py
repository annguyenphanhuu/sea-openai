from datetime import datetime
import importlib
from pathlib import Path
import sqlite3

import pytest

from logistics_an_nguyen.models import FeedHealth
from logistics_an_nguyen.replay import ReplaySnapshot


def instant(value):
    return datetime.fromisoformat(value)


@pytest.fixture(autouse=True)
def state():
    connection = sqlite3.connect(":memory:", isolation_level=None)
    schema = Path(__file__).resolve().parents[1] / "contracts/schema_state.sql"
    connection.executescript(schema.read_text(encoding="utf-8"))
    yield connection
    assert connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM ledger_new").fetchone()[0] == 0
    connection.close()


def guard():
    return importlib.import_module("platform_huy.sysguard")


@pytest.mark.parametrize("now,source,corrupt,expected", [
    ("2026-10-24T10:29:00+07:00", "2026-10-24T10:00:00+07:00", False, "trusted"),
    ("2026-10-24T10:30:00+07:00", "2026-10-24T10:00:00+07:00", False, "trusted"),
    ("2026-10-24T10:31:00+07:00", "2026-10-24T10:00:00+07:00", False, "stale"),
    ("2026-10-24T10:29:00+07:00", None, False, "missing"),
    ("2026-10-24T10:29:00+07:00", "2026-10-24T10:00:00+07:00", True, "corrupt"),
    ("2026-10-24T10:29:00+07:00", None, True, "corrupt"),
])
def test_feed_status_obeys_source_freshness_and_corruption_precedence(now, source, corrupt, expected):
    assert guard().feed_status(instant(now), None if source is None else instant(source), corrupt) == expected


def snapshot(now, *, orders=(), scans=(), attempts=()):
    return ReplaySnapshot(now, tuple(orders), tuple(scans), tuple(attempts), ())


def test_health_for_aggregates_three_source_times_without_writing(state):
    now = instant("2026-10-24T10:29:00+07:00")
    world = snapshot(now,
        orders=[{"order_id": "o1", "created_at": "2026-10-24T10:00:00+07:00"},
                {"order_id": "o2", "created_at": "2026-10-24T09:00:00+07:00"}],
        scans=[{"event_id": "s1", "order_id": "o1", "status": "station",
                "event_at": "2026-10-24T10:05:00+07:00", "ingested_at": "2026-10-24T10:28:00+07:00"},
               {"event_id": "s2", "order_id": "o2", "status": "packed",
                "event_at": "2026-10-24T09:00:00+07:00", "ingested_at": "2026-10-24T10:27:00+07:00"}],
        attempts=[{"attempt_id": "a1", "order_id": "o1", "attempt_at": "2026-10-24T09:58:00+07:00"}])
    health = guard().health_for(world, state, now)
    assert len(health) == 3
    assert all(isinstance(item, FeedHealth) for item in health)
    assert [(item.feed, item.status, item.source_timestamp) for item in health] == [
        ("orders", "trusted", instant("2026-10-24T10:00:00+07:00")),
        ("scan_events", "trusted", instant("2026-10-24T10:05:00+07:00")),
        ("delivery_attempts", "stale", instant("2026-10-24T09:58:00+07:00")),
    ]
    assert health[1].last_ingested_at == instant("2026-10-24T10:28:00+07:00")
    assert all(item.checked_at == now for item in health)
    assert state.execute("SELECT COUNT(*) FROM feed_health").fetchone()[0] == 0
    assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 0


def test_empty_snapshot_has_exactly_three_missing_feeds(state):
    now = instant("2026-10-24T10:29:00+07:00")
    assert [(item.feed, item.status, item.source_timestamp) for item in guard().health_for(snapshot(now), state, now)] == [
        ("orders", "missing", None), ("scan_events", "missing", None), ("delivery_attempts", "missing", None),
    ]


def test_invalid_scan_does_not_supply_a_trusted_timestamp(state):
    now = instant("2026-10-24T10:29:00+07:00")
    world = snapshot(now, scans=[
        {"event_id": "s1", "status": "station", "event_at": "invalid", "ingested_at": "2026-10-24T10:28:00+07:00"},
        {"event_id": "s2", "status": "packed", "event_at": "2026-10-24T09:00:00+07:00", "ingested_at": "2026-10-24T10:27:00+07:00"},
    ])
    health = guard().health_for(world, state, now)
    assert health[1].status == "corrupt"
    assert health[1].source_timestamp == instant("2026-10-24T09:00:00+07:00")


def test_guard_is_dead_without_a3_heartbeat(state):
    assert guard().guard_alive(state, instant("2026-10-24T12:29:00+07:00")) is False


@pytest.mark.parametrize("now,expected", [
    ("2026-10-24T12:29:00+07:00", True),
    ("2026-10-24T12:30:00+07:00", True),
    ("2026-10-24T12:31:00+07:00", False),
])
def test_guard_alive_obeys_ninety_minute_boundary(state, now, expected):
    guard().heartbeat(state, instant("2026-10-24T11:00:00+07:00"))
    assert guard().guard_alive(state, instant(now)) is expected


def test_heartbeat_records_actual_a3_tick_idempotently(state):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().heartbeat(state, now)
    guard().heartbeat(state, now)
    assert state.execute("SELECT tick_at,agent_id FROM guard_heartbeat").fetchall() == [
        ("2026-10-24T04:00:00.000000Z", "A3"),
    ]


def test_non_a3_heartbeat_does_not_resurrect_guard(state):
    state.execute("INSERT INTO guard_heartbeat VALUES (?,?,?,?,?)",
                  ("2026-10-24T04:00:00.000000Z", "A2", "2026-10-24T04:00:00.000000Z", 1, "[]"))
    assert guard().guard_alive(state, instant("2026-10-24T11:01:00+07:00")) is False


def fresh_world(now):
    text = now.isoformat()
    return snapshot(now,
        orders=[{"order_id": "o1", "created_at": text}],
        scans=[{"event_id": "s1", "status": "station", "event_at": text, "ingested_at": text}],
        attempts=[{"attempt_id": "a1", "attempt_at": text}])


def test_run_records_real_heartbeat_before_health_with_foreign_keys_enabled(state):
    now = instant("2026-10-24T11:00:00+07:00")
    result = guard().run(fresh_world(now), state, now)
    assert set(result) == {"feed_health", "guard_alive", "proactive_allowed", "actions"}
    assert result["guard_alive"] is True
    assert result["proactive_allowed"] is True
    assert result["actions"] == []
    assert [(item.feed, item.status) for item in result["feed_health"]] == [
        ("orders", "trusted"), ("scan_events", "trusted"), ("delivery_attempts", "trusted"),
    ]
    assert state.execute("PRAGMA foreign_key_check").fetchall() == []
    assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 1
    assert state.execute("SELECT COUNT(*) FROM feed_health").fetchone()[0] == 3
    assert state.execute("SELECT proactive_contact_allowed FROM guard_heartbeat").fetchone()[0] == 1


@pytest.mark.parametrize("feed", ["orders", "scan_events", "delivery_attempts"])
@pytest.mark.parametrize("status", ["stale", "corrupt", "missing"])
def test_every_untrusted_required_feed_blocks_proactive(state, feed, status):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(now), state, now)
    state.execute("UPDATE feed_health SET status=? WHERE feed=?", (status, feed))
    assert guard().proactive_allowed(state, now) is False


def test_missing_feed_row_and_expired_source_block_proactive(state):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(now), state, now)
    assert guard().proactive_allowed(state, instant("2026-10-24T11:31:00+07:00")) is False
    state.execute("DELETE FROM feed_health WHERE feed='orders'")
    assert guard().proactive_allowed(state, now) is False


def test_dead_guard_blocks_even_when_old_feed_rows_are_trusted(state):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(now), state, now)
    assert guard().proactive_allowed(state, instant("2026-10-24T12:31:00+07:00")) is False


def test_a3_controls_can_only_tighten_proactive_block(state):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(now), state, now)
    guard().set_control(state, "proactive_block", True)
    guard().set_control(state, "proactive_block", True)
    assert guard().proactive_allowed(state, now) is False
    with pytest.raises(ValueError):
        guard().set_control(state, "proactive_block", False)
    assert state.execute("SELECT value_json,updated_by FROM controls WHERE control_key='proactive_block'").fetchone() == ("true", "A3")


@pytest.mark.parametrize("key,value", [("unknown", True), ("proactive_block", 1), ("proactive_block", "false")])
def test_control_rejects_unknown_keys_and_non_booleans(state, key, value):
    with pytest.raises(ValueError):
        guard().set_control(state, key, value)
    assert state.execute("SELECT COUNT(*) FROM controls").fetchone()[0] == 0


def test_kill_immediately_stops_guard_without_fabricating_heartbeats_for_four_ticks(state):
    first = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(first), state, first)
    guard().kill(state)
    assert guard().guard_alive(state, first) is False
    assert guard().proactive_allowed(state, first) is False
    for timestamp in ["2026-10-24T11:30:00+07:00", "2026-10-24T12:00:00+07:00",
                      "2026-10-24T12:30:00+07:00", "2026-10-24T13:00:00+07:00"]:
        now = instant(timestamp)
        result = guard().run(fresh_world(now), state, now)
        assert result["guard_alive"] is False
        assert result["proactive_allowed"] is False
        assert result["actions"] == []
        assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 1
        assert state.execute("SELECT COUNT(*) FROM feed_health").fetchone()[0] == 3


def test_revive_waits_for_new_tick_and_keeps_explicit_policy_block(state):
    first = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(first), state, first)
    guard().set_control(state, "proactive_block", True)
    guard().kill(state)
    guard().revive(state)
    assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 1
    later = instant("2026-10-24T13:30:00+07:00")
    result = guard().run(fresh_world(later), state, later)
    assert result["guard_alive"] is True
    assert result["proactive_allowed"] is False
    assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 2
    assert state.execute("SELECT value_json FROM controls WHERE control_key='proactive_block'").fetchone()[0] == "true"


def test_revive_with_all_fresh_feeds_resumes_proactive(state):
    first = instant("2026-10-24T11:00:00+07:00")
    guard().kill(state)
    guard().revive(state)
    assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 0
    result = guard().run(fresh_world(first), state, first)
    assert result["guard_alive"] is True
    assert result["proactive_allowed"] is True


def test_revive_does_not_bypass_missing_feed(state):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().kill(state)
    guard().revive(state)
    result = guard().run(snapshot(now), state, now)
    assert result["guard_alive"] is True
    assert result["proactive_allowed"] is False


def test_run_rolls_back_heartbeat_when_health_persistence_fails(state):
    state.execute("CREATE TRIGGER reject_health BEFORE INSERT ON feed_health BEGIN SELECT RAISE(ABORT,'test failure'); END")
    now = instant("2026-10-24T11:00:00+07:00")
    with pytest.raises(Exception):
        guard().run(fresh_world(now), state, now)
    assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 0
    assert state.execute("SELECT COUNT(*) FROM feed_health").fetchone()[0] == 0


def test_revive_keeps_guard_dead_until_actual_a3_heartbeat(state):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(now), state, now)
    guard().kill(state)
    guard().revive(state)
    assert guard().guard_alive(state, now) is False
    assert guard().proactive_allowed(state, now) is False
    guard().heartbeat(state, instant("2026-10-24T11:30:00+07:00"))
    assert guard().guard_alive(state, instant("2026-10-24T11:30:00+07:00")) is True


def test_repeated_revive_does_not_disable_healthy_guard(state):
    now = instant("2026-10-24T11:00:00+07:00")
    guard().run(fresh_world(now), state, now)
    guard().revive(state)
    guard().revive(state)
    assert guard().guard_alive(state, now) is True
    assert guard().proactive_allowed(state, now) is True


@pytest.mark.parametrize("feed,world_args", [
    ("orders", {"orders": [{"created_at": "2026-10-24T11:01:00+07:00"}]}),
    ("scan_events", {"scans": [{"event_at": "2026-10-24T11:01:00+07:00", "ingested_at": "2026-10-24T11:01:00+07:00", "status": "station"}]}),
    ("delivery_attempts", {"attempts": [{"attempt_at": "2026-10-24T11:01:00+07:00"}]}),
])
def test_future_source_rows_are_corrupt_not_fresh(state, feed, world_args):
    now = instant("2026-10-24T11:00:00+07:00")
    result = guard().run(snapshot(now, **world_args), state, now)
    assert {item.feed: item.status for item in result["feed_health"]}[feed] == "corrupt"
    assert result["proactive_allowed"] is False


def test_future_heartbeat_cannot_prove_guard_alive(state):
    guard().heartbeat(state, instant("2026-10-24T11:30:00+07:00"))
    assert guard().guard_alive(state, instant("2026-10-24T11:00:00+07:00")) is False
