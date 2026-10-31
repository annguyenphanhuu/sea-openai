"""SQLite-only persistence boundary for the local financial executor.

Producer allowlists are trusted startup configuration, never request parameters.
This module does not manufacture order facts, request signals or source reviews.
"""
from contextlib import AbstractContextManager
from dataclasses import asdict
from datetime import datetime, timezone
import json
import sqlite3
from typing import Protocol
from uuid import uuid4

from contracts.types import Action
from .dto import CommandKeyRecord, ExecutionResult, ServerContext
from .state import canonical, current_clock, immediate, lookup_key, utc
from . import sysguard


class StateStore(Protocol):
    """Operations used in a single executor-owned atomic transaction."""

    def transaction(self) -> AbstractContextManager[None]: ...
    def clock(self) -> datetime: ...
    def lookup(self, key: str) -> CommandKeyRecord | None: ...
    def receipt_is_committed(self, record: CommandKeyRecord, result: ExecutionResult) -> bool: ...
    def guard_allows(self, now: datetime) -> bool: ...
    def evidence(self, reference: str) -> dict | None: ...
    def trusts(self, evidence: dict, message: dict) -> bool: ...
    def has_grant(self, kind: str, order_id: str) -> bool: ...
    def has_action(self, action_id: str) -> bool: ...
    def audit_denial(self, action: Action, context: ServerContext, reason: str, now: datetime) -> None: ...
    def grant(self, action: Action, context: ServerContext, request_hash: str,
              result: ExecutionResult, contact_id: str, now: datetime) -> None: ...


def _one(conn: sqlite3.Connection, sql: str, values: tuple = ()) -> dict | None:
    cursor = conn.execute(sql, values)
    row = cursor.fetchone()
    return None if row is None else dict(zip((item[0] for item in cursor.description), row))


class SqliteStateStore:
    """Use an already bootstrapped runtime connection, never a release database.

    Empty default allowlists deliberately disable grants until real, trusted
    server integrations persist evidence and explicitly configure their names.
    The caller owns the connection lifecycle; no network backend exists.
    """

    def __init__(self, conn: sqlite3.Connection, *,
                 evidence_producers: frozenset[str] = frozenset(),
                 message_recorders: frozenset[str] = frozenset(),
                 request_rule_versions: frozenset[str] = frozenset()) -> None:
        self.conn = conn
        self.evidence_producers = frozenset(evidence_producers)
        self.message_recorders = frozenset(message_recorders)
        self.request_rule_versions = frozenset(request_rule_versions)

    def transaction(self) -> AbstractContextManager[None]:
        return immediate(self.conn)

    def clock(self) -> datetime:
        return current_clock(self.conn)[0]

    def lookup(self, key: str) -> CommandKeyRecord | None:
        return lookup_key(self.conn, key)

    def receipt_is_committed(self, record: CommandKeyRecord, result: ExecutionResult) -> bool:
        row = _one(self.conn, 'SELECT status,kind,order_id,amount_vnd,source FROM outbox WHERE action_id=?', (record.reference_id,))
        receipt = _one(self.conn, 'SELECT decision_code,attested_source FROM action_receipts WHERE action_id=?', (record.reference_id,))
        if (row is None or receipt is None or row['status'] != 'succeeded'
                or receipt['decision_code'] != 'succeeded' or row['kind'] != result.kind
                or receipt['attested_source'] != row['source']
                or result.action_id != record.reference_id or result.decision != 'succeeded'):
            return False
        if record.key != f'{"xu" if result.kind == "coins" else "voucher"}:{row["order_id"]}':
            return False
        if result.kind == 'coins':
            effect = _one(self.conn, 'SELECT ledger_id,amount_xu FROM ledger_new WHERE action_id=? AND idempotency_key=? AND order_id=?',
                          (result.action_id, record.key, row['order_id']))
            return (effect is not None and effect['ledger_id'] == result.ledger_id
                    and effect['amount_xu'] == result.amount_xu == row['amount_vnd']
                    and result.amount_vnd is None and result.voucher_ledger_id is None
                    and result.cancel_id is None)
        if result.kind == 'voucher':
            effect = _one(self.conn, 'SELECT voucher_ledger_id,face_value_vnd FROM voucher_ledger WHERE action_id=? AND idempotency_key=? AND order_id=?',
                          (result.action_id, record.key, row['order_id']))
            return (effect is not None and effect['voucher_ledger_id'] == result.voucher_ledger_id
                    and effect['face_value_vnd'] == result.amount_vnd == row['amount_vnd'] == 10000
                    and result.amount_xu is None and result.ledger_id is None and result.cancel_id is None)
        return False

    def guard_allows(self, now: datetime) -> bool:
        return sysguard.proactive_allowed(self.conn, now)

    def evidence(self, reference: str) -> dict | None:
        evidence = _one(self.conn, 'SELECT * FROM execution_evidence WHERE evidence_id=?', (reference,))
        if evidence is None:
            return None
        return {
            'evidence': evidence,
            'contact': _one(self.conn, 'SELECT * FROM contact_log WHERE contact_id=?', (evidence['contact_id'],)),
            'message': _one(self.conn, 'SELECT * FROM customer_messages WHERE message_id=?', (evidence['message_id'],)),
            'run': _one(self.conn, 'SELECT * FROM run_metadata WHERE singleton=1'),
        }

    def trusts(self, evidence: dict, message: dict) -> bool:
        return (evidence['created_by'] in self.evidence_producers
                and message['recorded_by'] in self.message_recorders
                and message['request_rule_version'] in self.request_rule_versions)

    def has_grant(self, kind: str, order_id: str) -> bool:
        table = 'ledger_new' if kind == 'coins' else 'voucher_ledger'
        return self.conn.execute(f'SELECT 1 FROM {table} WHERE order_id=?', (order_id,)).fetchone() is not None

    def has_action(self, action_id: str) -> bool:
        return self.conn.execute('SELECT 1 FROM outbox WHERE action_id=?', (action_id,)).fetchone() is not None

    def audit_denial(self, action: Action, context: ServerContext, reason: str, now: datetime) -> None:
        audit = {'action_id': action.action_id, 'idempotency_key': action.idempotency_key,
                 'kind': action.kind, 'principal_id': context.principal_id,
                 'source': context.source, 'reason_code': reason,
                 'evidence_ref': action.evidence_ref, 'wall_at': utc(datetime.now(timezone.utc))}
        self.conn.execute(
            "INSERT INTO incidents(incident_id,order_id,detected_at,severity,summary,evidence_json) VALUES (?,?,?,'warning',?,?)",
            (str(uuid4()), action.order_id, utc(now), f'financial_action_blocked:{reason}', canonical(audit)),
        )

    def grant(self, action: Action, context: ServerContext, request_hash: str,
              result: ExecutionResult, contact_id: str, now: datetime) -> None:
        timestamp = utc(now)
        self.conn.execute(
            'INSERT INTO outbox(action_id,idempotency_key,order_id,kind,amount_vnd,source,confirmation_id,evidence_ref,needs_approval,queue,requested_at,available_at,status,completed_at) '
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'succeeded',?)",
            (action.action_id, action.idempotency_key, action.order_id, action.kind, action.amount_vnd,
             action.source, action.confirmation_id, action.evidence_ref, int(action.needs_approval),
             action.queue, utc(action.requested_at), timestamp, timestamp),
        )
        if action.kind == 'coins':
            self.conn.execute("INSERT INTO ledger_new VALUES (?,?,?,?,?,?,'late_delivery',?)",
                              (result.ledger_id, action.idempotency_key, action.order_id,
                               action.action_id, contact_id, result.amount_xu, timestamp))
        else:
            self.conn.execute("INSERT INTO voucher_ledger VALUES (?,?,?,?,?,10000,'huy-demo-v1',?)",
                              (result.voucher_ledger_id, action.idempotency_key, action.order_id,
                               action.action_id, contact_id, timestamp))
        self.conn.execute('INSERT INTO action_receipts VALUES (?,?,?,?,?,?,?,?)',
                          (action.action_id, request_hash, context.principal_id, context.source,
                           action.evidence_ref, 'succeeded', canonical(asdict(result)), timestamp))
