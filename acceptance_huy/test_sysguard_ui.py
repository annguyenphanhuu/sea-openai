"""HTTP acceptance checks for the local A3 demo, using real SQLite state."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from platform_huy import serve_ui


@pytest.fixture
def core(tmp_path):
    path = tmp_path / "core.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE sim_clock(id INTEGER PRIMARY KEY, now TEXT);
            INSERT INTO sim_clock VALUES (1,'2026-10-24T16:00:00+07:00');
            CREATE TABLE orders(order_id TEXT, created_at TEXT, guaranteed_date TEXT,
              carrier_id TEXT, service_level TEXT, cancelled_at TEXT);
            CREATE TABLE scan_events(event_id TEXT,order_id TEXT,status TEXT,location_type TEXT,
              location_id TEXT,event_at TEXT,ingested_at TEXT,carrier_event_id TEXT);
            CREATE TABLE delivery_attempts(attempt_id TEXT,order_id TEXT,attempt_no INTEGER,
              attempt_at TEXT,outcome TEXT,reason_code TEXT,call_attempts INTEGER);
            CREATE TABLE linehaul_reports(report_id TEXT,trip_id TEXT,reported_at TEXT,
              reported_by TEXT,reason_code TEXT,driver_note TEXT);
        """)
        for suffix, timestamp in (
            ("0", "2026-10-24T16:00:00+07:00"),
            ("1", "2026-10-24T16:30:00+07:00"),
            ("2", "2026-10-24T17:00:00+07:00"),
            ("3", "2026-10-24T17:30:00+07:00"),
        ):
            conn.execute("INSERT INTO orders VALUES (?,?,'2026-10-25','carrier','standard',NULL)",
                         ("order-" + suffix, timestamp))
            conn.execute("INSERT INTO scan_events VALUES (?,?,'station','station','S',?,?,NULL)",
                         ("scan-" + suffix, "order-" + suffix, timestamp, timestamp))
            conn.execute("INSERT INTO delivery_attempts VALUES (?,?,1,?,'failed','no_answer',1)",
                         ("attempt-" + suffix, "order-" + suffix, timestamp))
    conn.close()
    return path


@pytest.fixture
def running(core, tmp_path):
    state_path = tmp_path / "runtime" / "state.sqlite"
    server = serve_ui.create_server(core_path=core, state_path=state_path,
                                    start_at=datetime.fromisoformat("2026-10-24T16:00:00+07:00"), port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_port), state_path
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def call(base, route, *, post=False):
    request = Request(base + route, data=b"{}" if post else None,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def test_real_http_kill_two_next_revive_and_draft_gate(running, core):
    base, state_path = running
    original_hash = hashlib.sha256(core.read_bytes()).hexdigest()
    code, status = call(base, "/api/a3/status")
    assert code == 200
    assert status["now"] == "2026-10-24T16:00:00+07:00"
    assert status["guard_alive"] is False
    assert status["proactive_allowed"] is False
    assert status["last_heartbeat_at"] is None
    assert status["feed_health"][0]["age_minutes"] == 0
    assert call(base, "/api/a3/proactive-check", post=True)[1]["proactive_allowed"] is False
    _, status = call(base, "/api/next", post=True)
    assert status["now"] == "2026-10-24T16:30:00+07:00"
    assert status["guard_alive"] is True
    assert status["proactive_allowed"] is True
    last_heartbeat = status["last_heartbeat_at"]
    _, killed = call(base, "/api/a3/kill", post=True)
    assert killed["killed"] is True
    assert killed["guard_alive"] is False
    # A cached healthy browser cannot authorize a draft after the server kill.
    assert call(base, "/api/a3/proactive-check", post=True)[1]["proactive_allowed"] is False
    assert call(base, "/api/a3/status")[1]["last_heartbeat_at"] == last_heartbeat
    assert call(base, "/api/next", post=True)[1]["now"] == "2026-10-24T17:00:00+07:00"
    _, stopped = call(base, "/api/next", post=True)
    assert stopped["now"] == "2026-10-24T17:30:00+07:00"
    assert stopped["guard_alive"] is False
    assert stopped["proactive_allowed"] is False
    assert stopped["last_heartbeat_at"] == last_heartbeat
    _, pending = call(base, "/api/a3/revive", post=True)
    assert pending["guard_alive"] is False
    assert pending["proactive_allowed"] is False
    _, resumed = call(base, "/api/next", post=True)
    assert resumed["now"] == "2026-10-24T18:00:00+07:00"
    assert resumed["guard_alive"] is True
    assert resumed["proactive_allowed"] is True
    assert resumed["actions"] == []
    with sqlite3.connect(state_path) as state:
        assert state.execute("SELECT COUNT(*) FROM outbox").fetchone() == (0,)
        assert state.execute("SELECT COUNT(*) FROM ledger_new").fetchone() == (0,)
        assert state.execute("SELECT COUNT(*) FROM contact_log").fetchone() == (0,)
    assert hashlib.sha256(core.read_bytes()).hexdigest() == original_hash


def test_http_next_is_serialized_and_clock_survives_restart(running, core):
    base, state_path = running
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: call(base, "/api/next", post=True), range(2)))
    assert [result[0] for result in results] == [200, 200]
    assert sorted(result[1]["now"] for result in results) == [
        "2026-10-24T16:30:00+07:00", "2026-10-24T17:00:00+07:00"]
    second = serve_ui.create_server(core_path=core, state_path=state_path,
                                   start_at=datetime.fromisoformat("2026-10-24T16:00:00+07:00"), port=0)
    thread = Thread(target=second.serve_forever, daemon=True)
    thread.start()
    try:
        assert call("http://127.0.0.1:" + str(second.server_port), "/api/a3/status")[1]["now"] == "2026-10-24T17:00:00+07:00"
    finally:
        second.shutdown()
        thread.join(timeout=5)
        second.server_close()


def test_status_reads_do_not_heartbeat_and_source_failures_close_gate(running, core):
    base, state_path = running
    call(base, "/api/next", post=True)
    with sqlite3.connect(state_path) as state:
        assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone() == (1,)
    assert call(base, "/api/a3/status")[1]["guard_alive"] is True
    assert call(base, "/api/a3/status")[1]["guard_alive"] is True
    with sqlite3.connect(state_path) as state:
        assert state.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone() == (1,)
    core.rename(core.with_suffix(".unavailable"))
    code, result = call(base, "/api/a3/proactive-check", post=True)
    assert code == 503
    assert result["proactive_allowed"] is False


def test_http_revive_never_clears_policy_block(running):
    base, state_path = running
    call(base, "/api/next", post=True)
    with sqlite3.connect(state_path) as state:
        state.execute("INSERT INTO controls VALUES ('proactive_block','global','true','audit','A3','test')")
    call(base, "/api/a3/kill", post=True)
    call(base, "/api/a3/revive", post=True)
    _, status = call(base, "/api/next", post=True)
    assert status["guard_alive"] is True
    assert status["proactive_allowed"] is False


def test_kill_and_revive_controls_persist_when_source_is_unavailable(running, core):
    base, state_path = running
    call(base, "/api/next", post=True)
    core.rename(core.with_suffix(".unavailable"))
    code, result = call(base, "/api/a3/kill", post=True)
    assert code == 503
    assert result["proactive_allowed"] is False
    with sqlite3.connect(state_path) as state:
        assert state.execute(
            "SELECT value_json FROM controls WHERE control_key='a3_killed' AND scope='global'"
        ).fetchone() == ("true",)
    code, result = call(base, "/api/a3/revive", post=True)
    assert code == 503
    assert result["proactive_allowed"] is False
    with sqlite3.connect(state_path) as state:
        assert state.execute(
            "SELECT value_json FROM controls WHERE control_key='a3_killed' AND scope='global'"
        ).fetchone() == ("false",)
        assert state.execute(
            "SELECT value_json FROM controls WHERE control_key='a3_resume_pending' AND scope='global'"
        ).fetchone() == ("true",)
        assert state.execute("SELECT COUNT(*) FROM outbox").fetchone() == (0,)
        assert state.execute("SELECT COUNT(*) FROM ledger_new").fetchone() == (0,)


@pytest.mark.parametrize("location", ["source", "data"])
def test_runtime_cannot_target_source_or_data(core, tmp_path, location):
    target = core if location == "source" else tmp_path / "data" / "state.sqlite"
    with pytest.raises(ValueError):
        serve_ui.create_server(core_path=core, state_path=target, port=0)
