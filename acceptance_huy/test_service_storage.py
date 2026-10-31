"""Protocol harness tests; these do not certify a live Turso engine."""

import asyncio
import importlib
import json
import sqlite3
import uuid

import httpx
import pytest


def storage():
    try:
        return importlib.import_module("scripts.probe_remote_storage")
    except ModuleNotFoundError:
        pytest.fail("remote storage compatibility probe is not implemented")


class HranaHarness:
    """Real SQLite constraints behind the documented Hrana JSON boundary."""

    def __init__(self):
        self.uri = f"file:{uuid.uuid4().hex}?mode=memory&cache=shared"
        self.anchor = sqlite3.connect(self.uri, uri=True, isolation_level=None)
        self.streams = {}
        self.calls = []
        self.delay = 0

    async def __call__(self, request):
        await asyncio.sleep(self.delay)
        body = json.loads(request.content)
        self.calls.append(body)
        baton = body["baton"]
        conn = self.streams.pop(baton) if baton else sqlite3.connect(
            self.uri, uri=True, isolation_level=None
        )
        results = []
        closed = False
        for item in body["requests"]:
            if item["type"] == "close":
                conn.close()
                closed = True
                results.append({"type": "ok", "response": {"type": "close"}})
                continue
            stmt = item["stmt"]
            try:
                cursor = conn.execute(stmt["sql"], [arg["value"] for arg in stmt["args"]])
                rows = [[{"type": "integer" if isinstance(v, int) else "text", "value": str(v)}
                         for v in row] for row in cursor.fetchall()]
                result = {"rows": rows, "affected_row_count": max(cursor.rowcount, 0)}
                results.append({"type": "ok", "response": {"type": "execute", "result": result}})
            except sqlite3.Error as exc:
                results.append({"type": "error", "error": {"code": exc.sqlite_errorname}})
        new_baton = None if closed else uuid.uuid4().hex
        if not closed:
            self.streams[new_baton] = conn
        return httpx.Response(200, json={"baton": new_baton, "base_url": None, "results": results})

    def close(self):
        for conn in self.streams.values():
            conn.close()
        self.anchor.close()


def test_probe_requires_dedicated_test_opt_in(monkeypatch):
    module = storage()
    monkeypatch.delenv("TURSO_PROBE_ALLOW_WRITES", raising=False)
    result = module.probe("https://example.turso.io", "never-print-me")
    assert result["status"] == "BLOCKED"
    assert "never-print-me" not in json.dumps(result)


@pytest.mark.parametrize("url", ["http://example.com", "file:test.db", "https://user:pass@example.com", "https://example.com/?token=secret"])
def test_probe_rejects_unsafe_urls(monkeypatch, url):
    module = storage()
    monkeypatch.setenv("TURSO_PROBE_ALLOW_WRITES", "isolated-test-database")
    assert module.probe(url, "secret")["status"] == "BLOCKED"


def test_complete_protocol_probe_and_cleanup():
    module = storage()
    harness = HranaHarness()
    async def run():
            return await module._run_checks("https://example.turso.io", "secret", transport=httpx.MockTransport(harness))
    try:
        result = asyncio.run(run())
        assert result["status"] == "PASS", result
        assert all(value == "PASS" for value in result["checks"].values())
        assert set(result["checks"]) == {"migration", "foreign_key", "check", "unique", "rollback", "duplicate_race", "cas_race", "lost_commit_receipt", "reconnect"}
        assert harness.anchor.execute("SELECT name FROM sqlite_master WHERE name LIKE 'probe_%'").fetchall() == []
        assert not harness.streams
    finally:
        harness.close()


def test_delayed_http_does_not_block_event_loop():
    module = storage()
    harness = HranaHarness()
    harness.delay = 0.1
    async def run():
        ticks = 0
        async with httpx.AsyncClient(transport=httpx.MockTransport(harness)) as client:
            session = module.HranaSession(client, "https://example.turso.io", "secret")
            task = asyncio.create_task(session.execute("SELECT 1"))
            while not task.done():
                ticks += 1
                await asyncio.sleep(0.001)
            await task
            await session.close()
        return ticks
    try:
        assert asyncio.run(run()) >= 2
    finally:
        harness.close()


def test_network_and_sql_errors_are_redacted():
    module = storage()
    async def fail(request):
        raise httpx.ReadError("secret https://private-host/", request=request)
    result = asyncio.run(module._run_checks("https://example.turso.io", "secret", transport=httpx.MockTransport(fail)))
    assert result["status"] == "FAIL"
    assert "secret" not in json.dumps(result)
    assert "private-host" not in json.dumps(result)


@pytest.mark.parametrize("failure", ["accept_constraint", "syntax_error", "malformed", "routing", "pre_commit_disconnect"])
def test_probe_detects_incompatible_or_uncertain_engine(failure):
    module = storage()
    harness = HranaHarness()
    async def inject(request):
        body = json.loads(request.content)
        sql = body["requests"][0].get("stmt", {}).get("sql", "")
        if failure == "pre_commit_disconnect" and sql == "COMMIT":
            raise httpx.ReadError("response lost before server commit", request=request)
        response = await harness(request)
        data = response.json()
        if failure == "malformed":
            return httpx.Response(200, json={"results": []})
        if failure == "routing":
            data["base_url"] = "https://untrusted.example/"
        if "VALUES ('bad', 'missing')" in sql:
            if failure == "accept_constraint":
                data["results"] = [{"type": "ok", "response": {"result": {"rows": []}}}]
            if failure == "syntax_error":
                data["results"] = [{"type": "error", "error": {"code": "SQLITE_ERROR"}}]
        return httpx.Response(200, json=data)
    try:
        result = asyncio.run(module._run_checks("https://example.turso.io", "secret", transport=httpx.MockTransport(inject)))
        assert result["status"] == "FAIL", result
        assert "untrusted.example" not in json.dumps(result)
        if failure in {"accept_constraint", "syntax_error"}:
            assert not harness.streams
        if failure == "pre_commit_disconnect":
            assert len(harness.streams) == 1
    finally:
        harness.close()


def test_sql_error_in_transaction_closes_stream_before_cleanup():
    module = storage()
    harness = HranaHarness()
    async def inject(request):
        body = json.loads(request.content)
        sql = body["requests"][0].get("stmt", {}).get("sql", "")
        response = await harness(request)
        if "VALUES ('rolled-back', 0)" in sql:
            data = response.json()
            data["results"] = [{"type": "error", "error": {"code": "SQLITE_ERROR"}}]
            return httpx.Response(200, json=data)
        return response
    try:
        result = asyncio.run(module._run_checks("https://example.turso.io", "secret", transport=httpx.MockTransport(inject)))
        assert result["status"] == "FAIL"
        assert result["checks"]["rollback"] == "FAIL"
        assert result["cleanup"] == "PASS", result
        assert not harness.streams
        assert harness.anchor.execute("SELECT name FROM sqlite_master WHERE name LIKE 'probe_%'").fetchall() == []
    finally:
        harness.close()


def test_protocol_failure_does_not_reuse_ambiguous_baton():
    module = storage()
    harness = HranaHarness()
    async def inject(request):
        response = await harness(request)
        if len(harness.calls) == 2:
            return httpx.Response(200, json={"results": []})
        return response
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(inject)) as client:
            session = module.HranaSession(client, "https://example.turso.io", "secret")
            await session.execute("BEGIN IMMEDIATE")
            with pytest.raises(module.ProbeError):
                await session.execute("SELECT 1")
            await session.close()
            with pytest.raises(module.ProbeError):
                await session.execute("ROLLBACK")
    try:
        asyncio.run(run())
        assert len(harness.calls) == 2
        assert len(harness.streams) == 1
    finally:
        harness.close()
