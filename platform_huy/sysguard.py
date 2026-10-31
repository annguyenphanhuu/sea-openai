"""A3 source health, heartbeat, and fail-closed proactive-contact guard.

Only guard_heartbeat, feed_health, and controls are written here. Source data is
an existing read-only ReleaseReader ReplaySnapshot; this module executes no actions.
"""

from datetime import datetime, timedelta, timezone
import json
import sqlite3

from contracts.params import guard_heartbeat_max_min

from logistics_an_nguyen.models import FeedHealth, FeedStatus, aware, parse_instant, utc_iso
from logistics_an_nguyen.replay import ReplaySnapshot, STAGES


_REQUIRED_FEEDS = ("orders", "scan_events", "delivery_attempts")
_FEED_MAX_AGE = timedelta(minutes=30)
_GUARD_MAX_AGE = timedelta(minutes=90)


def feed_status(now: datetime, source_at: datetime | None, corrupt: bool = False) -> FeedStatus:
    """Corruption takes precedence over absence and source timestamp freshness."""
    aware(now, "now")
    if corrupt:
        return "corrupt"
    if source_at is None:
        return "missing"
    aware(source_at, "source_at")
    if source_at > now:
        return "corrupt"
    return "stale" if now - source_at > _FEED_MAX_AGE else "trusted"


def _health(feed: str, rows: tuple[dict, ...], timestamp_key: str, now: datetime) -> FeedHealth:
    timestamps = []
    ingested = []
    corrupt = False
    for row in rows:
        try:
            source_at = parse_instant(row[timestamp_key], timestamp_key)
            if source_at > now:
                raise ValueError("Future source timestamp")
            if feed == "scan_events":
                ingested_at = parse_instant(row["ingested_at"], "ingested_at")
                if ingested_at > now or source_at > ingested_at or row["status"] not in STAGES:
                    raise ValueError("Invalid scan projection")
                ingested.append(ingested_at)
            timestamps.append(source_at)
        except (KeyError, TypeError, ValueError):
            corrupt = True
    source_at = max(timestamps, default=None)
    return FeedHealth(feed, feed_status(now, source_at, corrupt), now,
                      source_at, max(ingested, default=None))


def health_for(world: ReplaySnapshot, state: sqlite3.Connection, now: datetime) -> list[FeedHealth]:
    """Compute exactly three feed statuses without mutating runtime or source data."""
    aware(now, "now")
    return [
        _health("orders", world.orders, "created_at", now),
        _health("scan_events", world.scans, "event_at", now),
        _health("delivery_attempts", world.attempts, "attempt_at", now),
    ]


def _control(state: sqlite3.Connection, key: str) -> bool:
    row = state.execute("SELECT value_json FROM controls WHERE control_key=? AND scope='global'", (key,)).fetchone()
    if row is None:
        return False
    try:
        value = json.loads(row[0])
    except (TypeError, ValueError):
        return True
    # An invalid stored control is never permission to contact customers.
    return value is not False


def heartbeat(state: sqlite3.Connection, now: datetime) -> None:
    """Record an actual A3 tick; a killed agent cannot produce a heartbeat."""
    tick = utc_iso(now)
    if _control(state, "a3_killed"):
        return
    state.execute(
        "INSERT INTO guard_heartbeat(tick_at,agent_id,recorded_at,proactive_contact_allowed) "
        "VALUES (?,'A3',?,0) ON CONFLICT(tick_at) DO UPDATE SET "
        "agent_id='A3',recorded_at=excluded.recorded_at",
        (tick, utc_iso(datetime.now(timezone.utc))),
    )
    if _control(state, "a3_resume_pending"):
        _write_control(state, "a3_resume_pending", False, "A3", "actual_a3_heartbeat")


def guard_alive(state: sqlite3.Connection, now: datetime) -> bool:
    """A runtime kill is immediate; unexpected death expires strictly after 90 min."""
    aware(now, "now")
    if _control(state, "a3_killed") or _control(state, "a3_resume_pending"):
        return False
    row = state.execute("SELECT tick_at FROM guard_heartbeat WHERE agent_id='A3' ORDER BY tick_at DESC LIMIT 1").fetchone()
    if row is None:
        return False
    try:
        age = now - parse_instant(row[0], "heartbeat tick_at")
    except (TypeError, ValueError):
        return False
    return timedelta(0) <= age <= _GUARD_MAX_AGE


def proactive_allowed(state: sqlite3.Connection, now: datetime) -> bool:
    """Require a live guard, all current feed evidence, and no policy block."""
    if not guard_alive(state, now) or _control(state, "proactive_block"):
        return False
    tick = state.execute("SELECT tick_at FROM guard_heartbeat WHERE agent_id='A3' ORDER BY tick_at DESC LIMIT 1").fetchone()[0]
    if now - parse_instant(tick, "heartbeat tick_at") > timedelta(minutes=guard_heartbeat_max_min):
        return False
    rows = state.execute(
        "SELECT feed,status,source_timestamp,last_ingested_at,checked_at FROM feed_health WHERE tick_at=?", (tick,),
    ).fetchall()
    by_feed = {row[0]: row for row in rows}
    for feed in _REQUIRED_FEEDS:
        row = by_feed.get(feed)
        if row is None:
            return False
        try:
            health = FeedHealth(row[0], row[1], parse_instant(row[4], "checked_at"),
                                None if row[2] is None else parse_instant(row[2], "source_timestamp"),
                                None if row[3] is None else parse_instant(row[3], "last_ingested_at"))
        except (TypeError, ValueError):
            return False
        if not health.usable_at(now):
            return False
    return True


def _write_control(state: sqlite3.Connection, key: str, value: bool, actor: str, reason: str) -> None:
    state.execute(
        "INSERT INTO controls(control_key,scope,value_json,updated_at,updated_by,reason_code) "
        "VALUES (?,'global',?,?,?,?) ON CONFLICT(control_key,scope) DO UPDATE SET "
        "value_json=excluded.value_json,updated_at=excluded.updated_at,"
        "updated_by=excluded.updated_by,reason_code=excluded.reason_code",
        (key, json.dumps(value), utc_iso(datetime.now(timezone.utc)), actor, reason),
    )


def set_control(state: sqlite3.Connection, key: str, value: bool) -> None:
    """A3 may set proactive_block=True; relaxing policy requires human authority."""
    if key != "proactive_block" or type(value) is not bool:
        raise ValueError("Only the boolean proactive_block control is supported")
    if value is not True:
        raise ValueError("A3 controls may only tighten policy")
    _write_control(state, key, True, "A3", "a3_proactive_block")


def kill(state: sqlite3.Connection) -> None:
    """Human demo control: stop A3 immediately, retaining previous audit evidence."""
    _write_control(state, "a3_killed", True, "human", "human_kill_a3")


def revive(state: sqlite3.Connection) -> None:
    """Human demo control: enable the next A3 tick without clearing policy blocks."""
    if not _control(state, "a3_killed"):
        return
    state.execute("SAVEPOINT sysguard_revive")
    try:
        _write_control(state, "a3_resume_pending", True, "human", "await_actual_a3_heartbeat")
        _write_control(state, "a3_killed", False, "human", "human_revive_a3")
    except BaseException:
        state.execute("ROLLBACK TO sysguard_revive")
        state.execute("RELEASE sysguard_revive")
        raise
    state.execute("RELEASE sysguard_revive")


def run(world: ReplaySnapshot, state: sqlite3.Connection, now: datetime) -> dict:
    """Record one live A3 tick atomically, with no external or financial actions."""
    health = health_for(world, state, now)
    if not _control(state, "a3_killed"):
        state.execute("SAVEPOINT sysguard_tick")
        try:
            # The existing schema references guard_heartbeat from feed_health.
            heartbeat(state, now)
            tick = utc_iso(now)
            for item in health:
                state.execute(
                    "INSERT INTO feed_health(feed,tick_at,status,source_timestamp,last_ingested_at,checked_at) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(feed,tick_at) DO UPDATE SET "
                    "status=excluded.status,source_timestamp=excluded.source_timestamp,"
                    "last_ingested_at=excluded.last_ingested_at,checked_at=excluded.checked_at",
                    (item.feed, tick, item.status,
                     None if item.source_timestamp is None else utc_iso(item.source_timestamp),
                     None if item.last_ingested_at is None else utc_iso(item.last_ingested_at), tick),
                )
            allowed = proactive_allowed(state, now)
            state.execute("UPDATE guard_heartbeat SET proactive_contact_allowed=? WHERE tick_at=? AND agent_id='A3'", (int(allowed), tick))
        except BaseException:
            state.execute("ROLLBACK TO sysguard_tick")
            state.execute("RELEASE sysguard_tick")
            raise
        state.execute("RELEASE sysguard_tick")
    return {"feed_health": health, "guard_alive": guard_alive(state, now),
            "proactive_allowed": proactive_allowed(state, now), "actions": []}
