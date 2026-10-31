"""The replay command reads A3 state but never creates healthy state itself."""

from datetime import timedelta
import sqlite3

from logistics_an_nguyen.__main__ import runtime_health
from logistics_an_nguyen.models import utc_iso


def test_missing_a3_state_does_not_create_it(tmp_path, tick):
    path = tmp_path / "missing.sqlite"
    assert runtime_health(path, tick) == ()
    assert not path.exists()


def test_latest_visible_feed_snapshot_is_used_without_future_recovery(tmp_path, state, tick):
    past, future = tick - timedelta(minutes=30), tick + timedelta(minutes=30)
    for at, status in ((past, "healthy"), (tick, "blocked"), (future, "healthy")):
        state.execute("INSERT INTO guard_heartbeat(tick_at,recorded_at,proactive_contact_allowed) VALUES(?,?,0)",
                      (utc_iso(at), utc_iso(at)))
        state.execute("INSERT INTO feed_health(feed,tick_at,status,checked_at) VALUES(?,?,?,?)",
                      ("scan_events", utc_iso(at), status, utc_iso(at)))
    state.commit()
    path = tmp_path / "state.sqlite"
    with sqlite3.connect(path) as target:
        state.backup(target)
    result = runtime_health(path, tick)
    assert len(result) == 1
    assert result[0].status == "blocked"
    assert result[0].checked_at == tick
