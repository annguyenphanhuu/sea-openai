"""Atomic primitives for the separate, local platform runtime database."""

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .dto import CommandKeyRecord, PlatformError, SourceIdentity


_ROOT = Path(__file__).resolve().parents[1]
_POLICY = "huy-demo-v1"


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, frozenset):
        return sorted(value)
    raise TypeError(f"Cannot serialize {type(value).__name__} as canonical JSON")


def canonical(value: object) -> str:
    """Stable UTF-8 JSON text; nonfinite numbers are never valid state."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False, default=_json_default)


def utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise PlatformError("validation_error", "Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _state_error(error: sqlite3.Error) -> PlatformError:
    code = getattr(error, "sqlite_errorcode", None)
    if code is not None and code & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return PlatformError("state_busy", "Runtime state is busy")
    return PlatformError("state_unavailable", "Runtime state is unavailable")


def connect_state(path: Path) -> sqlite3.Connection:
    conn = None
    try:
        conn = sqlite3.connect(path, isolation_level=None, timeout=5)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except sqlite3.Error as error:
        if conn is not None:
            conn.close()
        raise _state_error(error) from error


def _statements(script: str) -> Iterator[str]:
    """Split only complete SQLite statements, including multi-line CHECKs."""
    buffer = ""
    for char in script:
        buffer += char
        if char == ";" and sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ""
    if buffer.strip():
        # SQLite accepts a trailing comment without a semicolon.
        yield buffer


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


def bootstrap(conn: sqlite3.Connection, *, run_id: str,
              identity: SourceIdentity, start_at: datetime) -> None:
    """Bind one runtime to its immutable source/run/start identity atomically."""
    if not isinstance(run_id, str) or not run_id.strip() or not isinstance(identity, SourceIdentity):
        raise PlatformError("validation_error", "Run and source identity are required")
    start_text = utc(start_at)
    identity_text = canonical(identity)
    # PRAGMA foreign_keys is a no-op during a transaction, so set it first.
    try:
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.Error as error:
        raise _state_error(error) from error
    with immediate(conn):
        versions = []
        if _table_exists(conn, "schema_migrations"):
            versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
            if versions != [1]:
                raise PlatformError("source_invalid", "Unsupported runtime schema version")
        if _table_exists(conn, "run_metadata"):
            rows = conn.execute(
                "SELECT singleton,run_id,source_identity_json,start_at,policy_version FROM run_metadata"
            ).fetchall()
            if versions != [1] or rows != [(1, run_id, identity_text, start_text, _POLICY)]:
                raise PlatformError("source_invalid", "Runtime identity does not match")
            return
        if versions:
            raise PlatformError("source_invalid", "Runtime metadata is missing")
        existing_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table,) in existing_tables:
            quoted_table = '"' + table.replace('"', '""') + '"'
            if conn.execute(f"SELECT 1 FROM {quoted_table} LIMIT 1").fetchone():
                raise PlatformError("source_invalid", "Cannot adopt unattributed runtime data")
        for path in (_ROOT / "contracts/schema_state.sql", _ROOT / "platform_huy/migrations/001_platform.sql"):
            try:
                script = path.read_text(encoding="utf-8")
            except OSError as error:
                raise PlatformError("state_unavailable", "Runtime schema is unavailable") from error
            for statement in _statements(script):
                conn.execute(statement)
        conn.execute(
            "INSERT INTO run_metadata(singleton,run_id,source_identity_json,start_at,policy_version) "
            "VALUES (1,?,?,?,?)", (run_id, identity_text, start_text, _POLICY),
        )
        conn.execute("INSERT INTO demo_clock(singleton,current_at,version,current_attempt_id) VALUES (1,NULL,0,NULL)")
        conn.execute("INSERT INTO replay_checkpoint(singleton,tick_at,scan_watermark,version) VALUES (1,NULL,NULL,0)")
        conn.execute("INSERT INTO schema_migrations(version,applied_at) VALUES (1,?)", (utc(datetime.now(timezone.utc)),))


def current_clock(conn: sqlite3.Connection) -> tuple[datetime, int]:
    try:
        row = conn.execute("SELECT current_at,version FROM demo_clock WHERE singleton=1").fetchone()
    except sqlite3.Error as error:
        raise _state_error(error) from error
    if row is None or row[0] is None:
        raise PlatformError("run_not_ready", "Business clock has not been initialized")
    try:
        value = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        utc(value)
    except (TypeError, ValueError, AttributeError, PlatformError) as error:
        raise PlatformError("state_unavailable", "Stored business clock is invalid") from error
    return value.astimezone(timezone.utc), row[1]


@contextmanager
def immediate(conn: sqlite3.Connection) -> Iterator[None]:
    """Hold a write transaction; never commit partial work or fake success."""
    if conn.in_transaction:
        raise PlatformError("validation_error", "Nested runtime write transaction")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
    except sqlite3.Error as error:
        raise _state_error(error) from error


def lookup_key(conn: sqlite3.Connection, key: str) -> CommandKeyRecord | None:
    """Return stored metadata under the caller's transaction, without policy."""
    hits = []
    try:
        row = conn.execute(
            "SELECT o.action_id,o.order_id,o.kind,o.amount_vnd,o.source,o.requested_at,"
            "o.idempotency_key,o.evidence_ref,o.needs_approval,o.queue,o.confirmation_id,"
            "r.principal_id,r.request_hash,r.result_json FROM outbox o "
            "LEFT JOIN action_receipts r ON r.action_id=o.action_id WHERE o.idempotency_key=?", (key,),
        ).fetchone()
        if row is not None:
            columns = ("action_id", "order_id", "kind", "amount_vnd", "source", "requested_at",
                       "idempotency_key", "evidence_ref", "needs_approval", "queue", "confirmation_id")
            payload = dict(zip(columns, row[:11]))
            payload["needs_approval"] = bool(payload["needs_approval"])
            hits.append(CommandKeyRecord("outbox", key, row[11], row[12], row[0], canonical(payload), row[13]))
        for namespace, reference in (("replay_commands", "attempt_id"), ("workflow_commands", "cancel_id")):
            row = conn.execute(
                f"SELECT principal_id,request_hash,{reference},result_json FROM {namespace} WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            if row is not None:
                hits.append(CommandKeyRecord(namespace, key, row[0], row[1], row[2], None, row[3]))
        row = conn.execute(
            "SELECT reviewed_by,request_hash,review_id FROM eligibility_reviews WHERE idempotency_key=?", (key,),
        ).fetchone()
        if row is not None:
            hits.append(CommandKeyRecord("eligibility_reviews", key, row[0], row[1], row[2], None, None))
    except sqlite3.Error as error:
        raise _state_error(error) from error
    if len(hits) > 1:
        raise PlatformError("idempotency_conflict", "Command key exists in multiple namespaces")
    return hits[0] if hits else None
