"""Opt-in destructive compatibility checks for a dedicated Turso test database.

No business adapter uses this module. Unknown COMMIT outcomes are reconciled by
receipt; writes are never retried. Only random probe_* tables are created/dropped.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


CHECKS = ("migration", "foreign_key", "check", "unique", "rollback",
          "duplicate_race", "cas_race", "lost_commit_receipt", "reconnect")


class ProbeError(Exception):
    """A sanitized transport/protocol failure."""


class SqlError(ProbeError):
    def __init__(self, code: str):
        super().__init__("remote SQL rejected")
        self.code = code


def _endpoint(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if (parsed.scheme not in {"https", "libsql"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ProbeError("HTTPS database origin required")
    return f"https://{parsed.netloc}"


class HranaSession:
    """One server-side SQL stream; never share it between concurrent tasks."""

    def __init__(self, client: httpx.AsyncClient, database_url: str, token: str):
        self.client = client
        self.base_url = _endpoint(database_url)
        self.token = token
        self.baton: str | None = None
        self.broken = False

    async def _request(self, item: dict | list[dict]) -> dict:
        if self.broken:
            raise ProbeError("stream outcome unknown")
        try:
            response = await self.client.post(
                self.base_url + "/v3/pipeline",
                headers={"Authorization": "Bearer " + self.token},
                json={"baton": self.baton, "requests": item if isinstance(item, list) else [item]},
            )
            response.raise_for_status()
            body = response.json()
            self.baton = body["baton"]
            # Fail closed instead of forwarding credentials to an arbitrary host.
            redirected = body.get("base_url")
            if redirected is not None and redirected.rstrip("/") != self.base_url:
                raise ProbeError("server routing change requires review")
            results = body["results"]
            if len(results) != (len(item) if isinstance(item, list) else 1):
                raise ProbeError("invalid protocol result count")
            for result in results:
                if result["type"] == "error":
                    raise SqlError(str(result["error"].get("code", "UNKNOWN")))
                if result["type"] != "ok":
                    raise ProbeError("invalid protocol result")
            return results[0]["response"]
        except SqlError:
            raise
        except Exception:
            self.broken = True
            raise ProbeError("remote request failed; outcome unknown") from None

    async def execute(self, sql: str, args: tuple = ()) -> dict:
        encoded = [{"type": "integer" if isinstance(v, int) else "text", "value": str(v)} for v in args]
        response = await self._request({"type": "execute", "stmt": {
            "sql": sql, "args": encoded, "want_rows": True,
        }})
        return response["result"]

    async def close(self) -> None:
        if self.baton and not self.broken:
            await self._request({"type": "close"})


def _scalar(result: dict) -> str:
    return result["rows"][0][0]["value"]


class _DropCommitResponse(httpx.AsyncBaseTransport):
    """Drop bytes after the server has answered COMMIT, without resending it."""

    def __init__(self, inner: httpx.AsyncBaseTransport):
        self.inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        await response.aread()
        body = json.loads(request.content)
        if any(item.get("stmt", {}).get("sql") == "COMMIT" for item in body["requests"]):
            await response.aclose()
            raise httpx.ReadError("injected response loss", request=request)
        return response

    async def aclose(self) -> None:
        await self.inner.aclose()


async def _run_checks(database_url: str, token: str, *, transport=None) -> dict:
    """Internal runner; caller must enforce the dedicated-test opt-in."""
    report = {"status": "FAIL", "checks": dict.fromkeys(CHECKS, "NOT_RUN"),
              "engine": "libSQL via Hrana 3 HTTPS", "engine_version": "UNVERIFIED",
              "driver": f"httpx=={httpx.__version__}", "python": platform.python_version(),
              "limitations": ["Single serial stream per transaction; no write retry.",
                              "Changed routing origins fail closed.",
                              "Reconnect proves new-client persistence, not a hosted server restart."]}
    prefix = "probe_" + uuid4().hex
    parent, child = prefix + "_parent", prefix + "_child"
    sessions = []
    clients = []
    current = "migration"
    try:
        async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=False) as client:
            def session():
                value = HranaSession(client, database_url, token)
                sessions.append(value)
                return value

            first = session()
            report["engine_version"] = _scalar(await first.execute("SELECT sqlite_version()"))
            await first.execute("PRAGMA foreign_keys=ON")
            if _scalar(await first.execute("PRAGMA foreign_keys")) != "1":
                raise ProbeError("foreign keys unavailable")
            async def migrate():
                await first.execute(f"CREATE TABLE IF NOT EXISTS {parent} (id TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version >= 0))")
                await first.execute(f"CREATE TABLE IF NOT EXISTS {child} (id TEXT PRIMARY KEY, parent_id TEXT NOT NULL REFERENCES {parent}(id))")
            await migrate()
            await first.execute(f"INSERT INTO {parent} VALUES ('seed', 0)")
            before = await first.execute(f"SELECT id, version FROM {parent} ORDER BY id")
            await migrate()
            after = await first.execute(f"SELECT id, version FROM {parent} ORDER BY id")
            if before["rows"] != after["rows"]:
                raise ProbeError("migration changed existing data")
            report["checks"][current] = "PASS"

            for current, sql in (
                ("foreign_key", f"INSERT INTO {child} VALUES ('bad', 'missing')"),
                ("check", f"INSERT INTO {parent} VALUES ('bad', -1)"),
                ("unique", f"INSERT INTO {parent} VALUES ('seed', 0)"),
            ):
                try:
                    await first.execute(sql)
                except SqlError as exc:
                    if not exc.code.startswith("SQLITE_CONSTRAINT"):
                        raise
                else:
                    raise ProbeError("constraint accepted invalid row")
                report["checks"][current] = "PASS"

            current = "rollback"
            await first.execute("BEGIN IMMEDIATE")
            await first.execute(f"INSERT INTO {parent} VALUES ('rolled-back', 0)")
            await first.execute("ROLLBACK")
            if _scalar(await first.execute(f"SELECT count(*) FROM {parent} WHERE id='rolled-back'")) != "0":
                raise ProbeError("rollback leaked row")
            report["checks"][current] = "PASS"

            current = "duplicate_race"
            async def contender():
                own = session()
                try:
                    await own.execute(f"INSERT INTO {parent} VALUES ('duplicate', 0)")
                    return True
                except SqlError as exc:
                    if not exc.code.startswith("SQLITE_CONSTRAINT"):
                        raise
                    return False
            if sorted(await asyncio.gather(contender(), contender())) != [False, True]:
                raise ProbeError("duplicate race did not have one winner")
            if _scalar(await first.execute(f"SELECT count(*) FROM {parent} WHERE id='duplicate'")) != "1":
                raise ProbeError("duplicate receipt mismatch")
            report["checks"][current] = "PASS"

            current = "cas_race"
            async def cas():
                return (await session().execute(f"UPDATE {parent} SET version=1 WHERE id='seed' AND version=0"))["affected_row_count"]
            if sorted(await asyncio.gather(cas(), cas())) != [0, 1]:
                raise ProbeError("CAS did not have one winner")
            report["checks"][current] = "PASS"

            current = "lost_commit_receipt"
            # Separate client/stream performs real BEGIN/COMMIT. The fault wrapper
            # consumes a real response, then raises before the caller sees it.
            fault_client = httpx.AsyncClient(transport=_DropCommitResponse(
                transport or httpx.AsyncHTTPTransport(retries=0)), timeout=10, follow_redirects=False)
            clients.append(fault_client)
            fault = HranaSession(fault_client, database_url, token)
            await fault.execute("BEGIN IMMEDIATE")
            await fault.execute(f"INSERT INTO {parent} VALUES ('commit-receipt', 0)")
            try:
                await fault._request([
                    {"type": "execute", "stmt": {"sql": "COMMIT", "args": [], "want_rows": False}},
                    {"type": "close"},
                ])
            except ProbeError:
                pass
            else:
                raise ProbeError("commit response loss was not injected")
            # COMMIT and close share one pipeline, so response loss cannot leak
            # this stream. Never reuse the old baton or retry COMMIT/INSERT.
            async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=False) as fresh_client:
                fresh = HranaSession(fresh_client, database_url, token)
                try:
                    if _scalar(await fresh.execute(f"SELECT count(*) FROM {parent} WHERE id='commit-receipt'")) != "1":
                        raise ProbeError("committed receipt missing")
                    report["checks"][current] = "PASS"
                    current = "reconnect"
                    if _scalar(await fresh.execute(f"SELECT version FROM {parent} WHERE id='seed'")) != "1":
                        raise ProbeError("state missing after client restart")
                    report["checks"][current] = "PASS"
                finally:
                    await fresh.close()
            for value in sessions:
                await value.close()
            report["status"] = "PASS"
    except Exception:
        report["checks"][current] = "FAIL"
        report["error"] = "Compatibility check failed; details suppressed to protect credentials."
    finally:
        # Cleanup uses a new stream even when the original stream is broken.
        try:
            async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=False) as cleanup_client:
                cleanup = HranaSession(cleanup_client, database_url, token)
                await cleanup.execute(f"DROP TABLE IF EXISTS {child}")
                await cleanup.execute(f"DROP TABLE IF EXISTS {parent}")
                await cleanup.close()
            report["cleanup"] = "PASS"
        except Exception:
            report["cleanup"] = "FAIL"
            report["namespace"] = prefix
            report["status"] = "FAIL"
        for value in sessions:
            try:
                await value.close()
            except Exception:
                report["status"] = "FAIL"
        for client in clients:
            await client.aclose()
    return report


def probe(database_url: str, token: str) -> dict:
    """Run only when operator attests this is an isolated test database."""
    if os.environ.get("TURSO_PROBE_ALLOW_WRITES") != "isolated-test-database":
        return {"status": "BLOCKED", "reason": "Set TURSO_PROBE_ALLOW_WRITES=isolated-test-database only for a dedicated test DB."}
    try:
        _endpoint(database_url)
        if not token.strip():
            raise ProbeError("missing token")
    except (ProbeError, ValueError):
        return {"status": "BLOCKED", "reason": "Valid HTTPS database origin and token required."}
    return asyncio.run(_run_checks(database_url, token))


def main() -> int:
    result = probe(os.environ.get("TURSO_TEST_DATABASE_URL", ""), os.environ.get("TURSO_TEST_AUTH_TOKEN", ""))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
