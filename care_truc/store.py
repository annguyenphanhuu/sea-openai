"""Durable A1 state. Transition callbacks must be pure and perform no adapter IO."""
from contextlib import contextmanager
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Callable
from contracts import types as contracts
from care_truc import models
from care_truc.models import DomainError, History, Mutation, PendingDelivery, Receipt, Session, TurnResponse, normalize_utc


def _encode(value):
    if isinstance(value, datetime):
        return {'$time': normalize_utc(value).isoformat()}
    if is_dataclass(value):
        return {'$type': type(value).__name__, 'fields': {f.name: _encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, tuple):
        return {'$tuple': [_encode(v) for v in value]}
    if isinstance(value, dict):
        return {k: _encode(v) for k,v in value.items()}
    return value


def _decode(value):
    if not isinstance(value, dict):
        return value
    if '$time' in value:
        return normalize_utc(datetime.fromisoformat(value['$time']))
    if '$tuple' in value:
        return tuple(_decode(v) for v in value['$tuple'])
    if '$type' in value:
        cls = getattr(models, value['$type'], None) or getattr(contracts, value['$type'])
        return cls(**{k: _decode(v) for k,v in value['fields'].items()})
    return {k:_decode(v) for k,v in value.items()}


def _dump(value):
    return json.dumps(_encode(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _load(value):
    return _decode(json.loads(value))


def payload_hash(operation: str, text: str, reply_to: str | None = None) -> str:
    return hashlib.sha256(_dump({'operation':operation, 'text':text, 'reply_to':reply_to}).encode('utf-8')).hexdigest()


class SqliteSessionStore:
    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(str(path), timeout=1, isolation_level=None, check_same_thread=False)
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.executescript(Path(__file__).with_name('schema.sql').read_text())

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def _transaction(self):
        try:
            self.connection.execute('BEGIN IMMEDIATE')
            yield
            self.connection.commit()
        except Exception as error:
            if self.connection.in_transaction:
                self.connection.rollback()
            if isinstance(error, sqlite3.IntegrityError):
                raise DomainError('store_conflict', 409) from error
            if isinstance(error, sqlite3.OperationalError) and ('locked' in str(error) or 'busy' in str(error)):
                raise DomainError('store_busy', 409) from error
            raise

    def _session(self, principal_id: str, session_id: str) -> Session:
        row = self.connection.execute('SELECT body FROM sessions WHERE id=? AND principal=?', (session_id, principal_id)).fetchone()
        if row is None:
            raise DomainError('session_not_found', 404)
        return _load(row[0])

    def get_session(self, principal_id: str, session_id: str) -> Session:
        return self._session(principal_id, session_id)

    def create_session(self, session: Session, contact_key: str | None = None) -> Session:
        with self._transaction():
            self.connection.execute('INSERT INTO sessions VALUES(?,?,?,?)', (session.id,session.principal_id,contact_key,_dump(session)))
        return session

    def mutate(self, principal_id: str, session_id: str, request_id: str, payload_hash: str,
               transition: Callable[[Session], Mutation], *, expected_version: int | None = None) -> TurnResponse:
        with self._transaction():
            before = self._session(principal_id, session_id)
            cached = self.connection.execute('SELECT hash,response FROM requests WHERE principal=? AND session=? AND request=?', (principal_id,session_id,request_id)).fetchone()
            if cached:
                if cached[0] != payload_hash:
                    raise DomainError('request_conflict', 409)
                return _load(cached[1])
            if expected_version is not None and before.version != expected_version:
                raise DomainError('session_version_conflict', 409)
            mutation = transition(before)
            after = mutation.session
            if any(getattr(before,k) != getattr(after,k) for k in ('id','principal_id','run_id','order_id','channel','origin')) or after.version != before.version + 1:
                raise DomainError('invalid_session_transition',409)
            self.connection.execute('UPDATE sessions SET body=? WHERE id=?', (_dump(after),session_id))
            self.connection.execute('INSERT INTO requests VALUES(?,?,?,?,?)', (principal_id,session_id,request_id,payload_hash,_dump(mutation.response)))
            for message in mutation.messages:
                self.connection.execute('INSERT INTO messages VALUES(?,?,?)',(message.id,session_id,_dump(message)))
            for evidence in mutation.evidence:
                self.connection.execute('INSERT INTO evidence VALUES(?,?,?)',(evidence.id,session_id,_dump(evidence)))
            if mutation.pending_cancel:
                cancel = mutation.pending_cancel
                if (cancel.principal_id,cancel.session_id,cancel.order_id) != (principal_id,session_id,before.order_id):
                    raise DomainError('invalid_cancellation',409)
                existing = self.connection.execute('SELECT session FROM cancellations WHERE id=?',(cancel.id,)).fetchone()
                if existing and existing[0] != session_id:
                    raise DomainError('store_conflict',409)
                self.connection.execute('INSERT INTO cancellations VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(cancel.id,session_id,_dump(cancel)))
            if mutation.handoff:
                if mutation.handoff.session_id != session_id:
                    raise DomainError('invalid_handoff',409)
                self.connection.execute('INSERT INTO handoffs VALUES(?,?)',(session_id,_dump(mutation.handoff)))
            for delivery in mutation.deliveries:
                if delivery.session_id != session_id or delivery.status != 'pending_delivery' or delivery.lease_until is not None:
                    raise DomainError('invalid_delivery',409)
                action = delivery.payload
                if delivery.kind == 'action' and action.order_id != before.order_id:
                    raise DomainError('invalid_delivery_order', 409)
                coin = _dump((before.run_id,before.order_id)) if delivery.kind == 'action' and action.kind == 'coins' else None
                self.connection.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)', (delivery.id,session_id,delivery.key,coin,session_id if delivery.kind == 'handoff' else None,_dump(delivery),delivery.status,None))
            return mutation.response

    def history(self, principal_id: str, session_id: str) -> History:
        # One read transaction prevents a mixed session/message snapshot.
        self.connection.execute('BEGIN')
        try:
            session = self._session(principal_id,session_id)
            responses = tuple(_load(r[0]) for r in self.connection.execute('SELECT response FROM requests WHERE session=? ORDER BY rowid',(session_id,)))
            receipts = tuple(_load(r[0]) for r in self.connection.execute('SELECT r.body FROM receipts r JOIN deliveries d ON d.key=r.key WHERE d.session=? ORDER BY d.rowid',(session_id,)))
            messages = tuple(_load(r[0]) for r in self.connection.execute('SELECT body FROM messages WHERE session=? ORDER BY rowid',(session_id,)))
            pending = tuple(self._delivery(r) for r in self.connection.execute('SELECT body,status,lease_until FROM deliveries WHERE session=? ORDER BY rowid',(session_id,)))
            deliveries = tuple(models.DeliveryState(item.id, item.kind, item.key, item.status) for item in pending)
            events = tuple(models.SystemEvent(*r) for r in self.connection.execute('SELECT key,revision,status FROM system_events WHERE session=? ORDER BY rowid',(session_id,)))
            return History(session,responses,receipts,messages,events,deliveries)
        finally:
            self.connection.rollback()

    def get_cancellation(self, principal_id: str, session_id: str, cancellation_id: str):
        self._session(principal_id,session_id)
        row = self.connection.execute('SELECT body FROM cancellations WHERE id=? AND session=?',(cancellation_id,session_id)).fetchone()
        return _load(row[0]) if row else None

    def staff_trace(self, session_id: str):
        """Internal only: caller must authorize staff before invoking."""
        return tuple(_load(r[0]) for r in self.connection.execute('SELECT body FROM evidence WHERE session=? ORDER BY rowid',(session_id,)))

    @staticmethod
    def _delivery(row):
        return replace(_load(row[0]),status=row[1],lease_until=datetime.fromisoformat(row[2]) if row[2] else None)

    def claim_deliveries(self, cutoff: datetime, limit: int) -> tuple[PendingDelivery,...]:
        cutoff = normalize_utc(cutoff)
        if type(limit) is not int or limit < 1:
            raise DomainError('invalid_limit')
        with self._transaction():
            rows = self.connection.execute("SELECT body,status,lease_until FROM deliveries WHERE status IN ('pending_delivery','accepted','pending','unknown') AND (lease_until IS NULL OR lease_until<=?) ORDER BY rowid LIMIT ?",(cutoff.isoformat(),limit)).fetchall()
            lease = cutoff + timedelta(seconds=60)
            result = tuple(replace(self._delivery(row),lease_until=lease) for row in rows)
            for delivery in result:
                self.connection.execute('UPDATE deliveries SET lease_until=? WHERE key=?',(lease.isoformat(),delivery.key))
            return result

    def record_receipt(self, receipt: Receipt) -> None:
        with self._transaction():
            delivery = self.connection.execute('SELECT session,status FROM deliveries WHERE key=?',(receipt.delivery_key,)).fetchone()
            if delivery is None:
                raise DomainError('delivery_not_found',404)
            previous = self.connection.execute('SELECT revision,body FROM receipts WHERE key=?',(receipt.delivery_key,)).fetchone()
            if previous:
                old = _load(previous[1])
                if receipt.revision <= old.revision or old.status in ('succeeded','failed','blocked'):
                    return
            self.connection.execute('INSERT INTO receipts VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET revision=excluded.revision,body=excluded.body',(receipt.delivery_key,receipt.revision,_dump(receipt)))
            self.connection.execute('UPDATE deliveries SET status=?,lease_until=NULL WHERE key=?',(receipt.status,receipt.delivery_key))
            self.connection.execute('INSERT INTO system_events VALUES(?,?,?,?)',(delivery[0],receipt.delivery_key,receipt.revision,receipt.status))
            session_row = self.connection.execute('SELECT body FROM sessions WHERE id=?',(delivery[0],)).fetchone()
            session = _load(session_row[0])
            body = self.connection.execute('SELECT body FROM deliveries WHERE key=?',(receipt.delivery_key,)).fetchone()
            pending = _load(body[0])
            changes = {'version':session.version + 1}
            if pending.kind == 'contact':
                changes['contact_delivery_status'] = receipt.status
            if pending.kind == 'handoff' and receipt.status == 'succeeded' and session.state == 'handoff_pending':
                changes['state'] = 'transferred'
            self.connection.execute('UPDATE sessions SET body=? WHERE id=?',(_dump(replace(session,**changes)),session.id))



    def public_evidence(self, principal_id: str, session_id: str) -> tuple[tuple[str, str], ...]:
        """Ownership-scoped public evidence; internal trace never crosses this API."""
        self._session(principal_id, session_id)
        return tuple((item.id, item.public_text) for item in self.staff_trace(session_id))

    def get_handoff(self, session_id: str):
        """Internal staff/dispatcher API; authorize at service boundary."""
        row = self.connection.execute('SELECT body FROM handoffs WHERE session=?', (session_id,)).fetchone()
        return _load(row[0]) if row else None
