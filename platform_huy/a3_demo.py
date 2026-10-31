"""Local A3 demo adapter; immutable replay input and a separate runtime clock."""

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock

from logistics_an_nguyen.models import aware, parse_instant
from logistics_an_nguyen.replay import ReleaseReader

from . import sysguard


def project_root() -> Path:
    """Find the local release when launched from a controller-owned worktree."""
    root = Path(__file__).resolve().parents[1]
    return next((path for path in (root, *root.parents)
                 if (path / "data/release_main/core_14d.sqlite").is_file()), root)


def release_dir() -> Path:
    """Allow deployment inputs without changing local release discovery."""
    configured = os.environ.get("SEA_RELEASE_DIR")
    return Path(configured) if configured else project_root() / "data/release_main"


class A3Demo:
    """Serialize local requests; only NEXT advances business time or runs A3."""

    def __init__(self, core_path: Path, state_path: Path,
                 start_at: datetime | None = None) -> None:
        self.core_path = Path(core_path).resolve(strict=True)
        self.state_path = Path(state_path).resolve()
        if self.state_path == self.core_path or any(
            parent.name.casefold() == "data" for parent in self.state_path.parents
        ):
            raise ValueError("Runtime must be separate from source and outside data directories")
        if self.state_path.exists():
            source_paths = (self.core_path, self.core_path.parent / 'ops_14d.sqlite')
            if any(path.exists() and self.state_path.samefile(path) for path in source_paths):
                raise ValueError("Runtime must not refer to a source file")
        self.lock = Lock()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as state:
            clock_exists = state.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='a3_demo_clock'"
            ).fetchone()
            if clock_exists:
                saved = state.execute(
                    "SELECT source_path,start_at FROM a3_demo_clock WHERE singleton=1"
                ).fetchone()
                if saved is None or saved[0] != str(self.core_path):
                    raise ValueError("A3 runtime belongs to a different source")
                if start_at is not None and parse_instant(saved[1], "start_at") != aware(start_at, "start_at"):
                    raise ValueError("A3 runtime belongs to a different start time")
                return
            if start_at is None:
                with ReleaseReader(self.core_path) as reader:
                    row = reader.connection.execute("SELECT now FROM sim_clock WHERE id=1").fetchone()
                    if row is None:
                        raise ValueError("Source simulation clock is missing; supply --start-at")
                    start_at = parse_instant(row[0], "source simulation clock")
            aware(start_at, "start_at")
            schema = Path(__file__).resolve().parents[1] / "contracts/schema_state.sql"
            state.executescript(schema.read_text(encoding="utf-8"))
            state.execute("BEGIN IMMEDIATE")
            try:
                state.execute(
                    "CREATE TABLE a3_demo_clock(singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
                    "current_at TEXT NOT NULL,start_at TEXT NOT NULL,source_path TEXT NOT NULL)"
                )
                state.execute("INSERT INTO a3_demo_clock VALUES (1,?,?,?)",
                              (start_at.isoformat(), start_at.isoformat(), str(self.core_path)))
                state.commit()
            except BaseException:
                state.rollback()
                raise

    def _connect(self) -> sqlite3.Connection:
        state = sqlite3.connect(self.state_path, isolation_level=None, timeout=10)
        state.execute("PRAGMA foreign_keys=ON")
        return state

    def _status(self, state: sqlite3.Connection, now: datetime, world) -> dict:
        health = sysguard.health_for(world, state, now)
        feed_health = []
        for item in health:
            entry = asdict(item)
            entry["age_minutes"] = (None if item.source_timestamp is None else
                                    (now - item.source_timestamp).total_seconds() / 60)
            feed_health.append(entry)
        heartbeat = state.execute(
            "SELECT tick_at FROM guard_heartbeat WHERE agent_id='A3' ORDER BY tick_at DESC LIMIT 1"
        ).fetchone()
        controls = dict(state.execute(
            "SELECT control_key,value_json FROM controls WHERE scope='global'"
        ))
        return {
            "now": now.isoformat(),
            "guard_alive": sysguard.guard_alive(state, now),
            "proactive_allowed": sysguard.proactive_allowed(state, now) and
                                 all(item.usable_at(now) for item in health),
            "feed_health": feed_health,
            "last_heartbeat_at": None if heartbeat is None else heartbeat[0],
            "killed": json.loads(controls.get("a3_killed", "false")) is not False,
            "resume_pending": json.loads(controls.get("a3_resume_pending", "false")) is not False,
            "actions": [],
            "mode": "local_a3_demo_draft_only",
        }

    def request(self, action: str = "status") -> dict:
        """A status/check never writes a heartbeat; mutations commit atomically."""
        if action not in ("status", "proactive-check", "next", "kill", "revive"):
            raise ValueError("Unknown A3 demo operation")
        with self.lock, closing(self._connect()) as state:
            state.execute("BEGIN IMMEDIATE" if action in ("next", "kill", "revive") else "BEGIN")
            try:
                row = state.execute("SELECT current_at FROM a3_demo_clock WHERE singleton=1").fetchone()
                now = parse_instant(row[0], "runtime clock")
                if action == "kill":
                    sysguard.kill(state)
                elif action == "revive":
                    sysguard.revive(state)
                elif action == "next":
                    now += timedelta(minutes=30)
                    state.execute("UPDATE a3_demo_clock SET current_at=? WHERE singleton=1", (now.isoformat(),))
                if action in ("kill", "revive"):
                    # Human stop/resume controls must survive an unavailable source.
                    # The response projection is a separate, fail-closed read.
                    state.commit()
                    state.execute("BEGIN")
                with ReleaseReader(self.core_path) as reader:
                    world = reader.snapshot(now)
                if action == "next":
                    sysguard.run(world, state, now)
                result = self._status(state, now, world)
                state.commit()
                return result
            except BaseException:
                state.rollback()
                raise
