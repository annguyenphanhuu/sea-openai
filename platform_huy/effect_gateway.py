"""A1's local effect port backed by the real SQLite financial executor.

Bindings and ServerContext are trusted server configuration, never HTTP input.
This adapter does not mint eligibility evidence or simulate contact delivery.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import json
import math
import sqlite3
import time
from types import MappingProxyType
from typing import Iterator, Mapping

from care_truc.runtime_types import CareError, EffectProposal, Receipt, canonical, fingerprint
from care_truc.store import MemoryStore
from contracts.types import Action
from .dto import ExecutionResult, PlatformError, ServerContext
from .money import execute_action, get_receipt
from .state_store import SqliteStateStore


def check_deadline(deadline: float) -> float:
    if not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
        raise ValueError('Invalid monotonic deadline')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('deadline_exceeded')
    return remaining


@contextmanager
def sqlite_deadline(connections: tuple[sqlite3.Connection, ...], deadline: float) -> Iterator[None]:
    """Bound synchronous SQLite work; callers check again before committing."""
    check_deadline(deadline)
    saved = []
    try:
        for conn in connections:
            old = conn.execute('PRAGMA busy_timeout').fetchone()[0]
            saved.append((conn, old))
            milliseconds = max(1, min(50, int(check_deadline(deadline) * 1000)))
            conn.execute(f'PRAGMA busy_timeout={milliseconds}')
            conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
        try:
            yield
        except (sqlite3.Error, PlatformError) as error:
            if time.monotonic() >= deadline:
                raise TimeoutError('deadline_exceeded') from error
            raise
    finally:
        for conn, timeout in saved:
            conn.set_progress_handler(None, 0)
            conn.execute(f'PRAGMA busy_timeout={timeout}')


class SqliteEffectGateway:
    """Scoped server adapter; use on the same event-loop thread as both stores.

    A1 retains its envelope key; only the platform Action gets the canonical
    entitlement key. Persisted A1 proposals provide restart lookup bindings.
    Unsupported effect kinds are rejected, never acknowledged as delivered.
    """

    supports_deadlines = True
    idempotent = True
    atomic_final_validation = True

    def __init__(self, store: SqliteStateStore, care_store: MemoryStore, *,
                 context: ServerContext, customer_principal: str,
                 evidence_bindings: Mapping[str, str]) -> None:
        if not isinstance(context, ServerContext) or not customer_principal:
            raise ValueError('Trusted server context and customer principal are required')
        self.store = store
        self.care_store = care_store
        self.context = context
        self.customer_principal = customer_principal
        self.evidence_bindings = MappingProxyType(dict(evidence_bindings))
        row = store.conn.execute('SELECT run_id FROM run_metadata WHERE singleton=1').fetchone()
        if row is None:
            raise ValueError('Platform runtime must be bootstrapped')
        self.run_id = row[0]

    def _deadline(self, deadline: float):
        return sqlite_deadline((self.store.conn, self.care_store.db), deadline)

    def _prepare(self, proposal: EffectProposal):
        row = self.care_store.effect(proposal.effect_id)
        if (row is None or row['run_id'] != self.run_id or row['attempts'] < 1
                or canonical(json.loads(row['proposal'])) != canonical(proposal)
                or row['effect_key'] != proposal.key or row['session_id'] != proposal.session_id):
            raise CareError('effect_binding_invalid', 403)
        state = self.care_store.load_session(proposal.session_id)
        if (state.run_id != self.run_id or state.principal_id != self.customer_principal
                or state.order_id != proposal.order_id):
            raise CareError('forbidden', 403)
        if proposal.kind != 'action_request':
            raise CareError('effect_kind_not_supported', 409)
        try:
            payload = json.loads(proposal.payload)
            payload['requested_at'] = datetime.fromisoformat(payload['requested_at'].replace('Z', '+00:00'))
            action = Action(**payload)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise CareError('action_invalid', 400) from error
        if (action.order_id != proposal.order_id or action.evidence_ref != proposal.evidence_ref
                or action.idempotency_key != proposal.key or action.kind not in ('coins', 'voucher', 'cancel_request')):
            raise CareError('action_binding_invalid', 403)
        prefix = 'xu' if action.kind == 'coins' else 'voucher'
        key = (f'{self.run_id}:cancel:{action.confirmation_id}' if action.kind == 'cancel_request'
               else f'{prefix}:{action.order_id}')
        allowed = {key}
        if action.kind == 'coins':
            allowed.add(f'{self.run_id}:coins:{action.order_id}')
        if action.kind == 'cancel_request':
            allowed.add(f'cancel:{action.order_id}:{action.confirmation_id}')
            if action.amount_vnd != 0 or not action.needs_approval or not action.confirmation_id:
                raise CareError('cancel_confirmation_invalid', 403)
        if action.idempotency_key not in allowed:
            raise CareError('action_key_invalid', 403)
        platform_reference = self.evidence_bindings.get(proposal.evidence_ref)
        if not platform_reference:
            raise CareError('platform_evidence_missing', 409)
        return replace(action, idempotency_key=key, evidence_ref=platform_reference), state

    def _verify_provenance(self, proposal, action, state):
        row = self.care_store.db.execute(
            'SELECT e.data,r.payload,r.phase,r.principal,r.session_id FROM evidence_bundles e '
            'JOIN requests r ON r.id=e.request_id WHERE e.ref=?', (proposal.evidence_ref,),
        ).fetchone()
        if row is None:
            raise CareError('care_evidence_missing', 409)
        try:
            bundle, request = json.loads(row['data']), json.loads(row['payload'])
            session, event = bundle['session'], bundle['event']
            actual = self.store.evidence(action.evidence_ref)
            message, contact = actual['message'], actual['contact']
            if (row['phase'] != 'committed' or row['principal'] != self.customer_principal
                    or row['session_id'] != state.session_id
                    or session['session_id'] != state.session_id
                    or session['run_id'] != self.run_id or session['order_id'] != action.order_id
                    or session['principal_id'] != self.customer_principal
                    or session['channel'] != 'chat' or session['opened_by'] != 'a1'
                    or session['contact_id'] != contact['contact_id']
                    or state.contact_id != contact['contact_id']
                    or state.channel != 'chat' or state.opened_by != 'a1'
                    or event != request
                    or message['customer_id'] != self.context.customer_id
                    or message['order_id'] != action.order_id or contact['order_id'] != action.order_id
                    or canonical(proposal) not in [canonical(item) for item in bundle['proposals']]):
                raise ValueError('Provenance does not match')
            if action.kind == 'cancel_request':
                facts = json.loads(actual['evidence']['payload_json'])
                confirmation, pending = facts['cancellation'], session['pending']
                if (not pending or confirmation['confirmed'] is not True
                        or pending['confirmation_id'] != action.confirmation_id
                        or confirmation['confirmation_id'] != action.confirmation_id
                        or confirmation['request_id'] != proposal.evidence_ref
                        or confirmation['reply_to'] != pending['reply_to']
                        or confirmation['expires_at'] != pending['expires_at']):
                    raise ValueError('Cancellation provenance does not match')
                if event['kind'] == 'confirm_cancel':
                    if (event.get('confirmed') is not True or event.get('reply_to') != pending['reply_to']
                            or event.get('confirmation_id') != action.confirmation_id
                            or message['body'] != 'confirm_cancel:' + action.confirmation_id):
                        raise ValueError('Cancellation event does not match')
                elif event['kind'] == 'message':
                    from care_truc.policy import signals
                    if (signals(event.get('text') or '')[0] != 'accept' or event.get('reply_to') != pending['reply_to']
                            or event['text'] != message['body']):
                        raise ValueError('Cancellation acceptance does not match')
                else:
                    raise ValueError('Cancellation requires customer confirmation')
            elif event['kind'] != 'message' or not isinstance(event['text'], str) or event['text'] != message['body']:
                raise ValueError('Customer text does not match')
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise CareError('care_evidence_invalid', 403) from error

    @staticmethod
    def _receipt(proposal: EffectProposal, result: ExecutionResult) -> Receipt:
        success = result.decision == 'succeeded'
        return Receipt(proposal.effect_id, proposal.key, fingerprint(proposal.payload), 1,
                       ('awaiting_approval' if result.cancel_id else 'succeeded') if success else 'rejected',
                       result.action_id if success else 'blocked:' + ','.join(result.reason_codes))

    async def submit(self, proposal: EffectProposal, *, deadline: float) -> Receipt:
        """Execute a persisted A1 request; receipt means an actual local effect."""
        with self._deadline(deadline):
            # Freeze durable care authority/provenance through platform acceptance.
            # execute_action owns the separate platform transaction; do not nest it.
            with self.care_store.transaction():
                action, state = self._prepare(proposal)
                existing = get_receipt(action.idempotency_key, store=self.store, context=self.context)
                if existing is None:
                    if state.status != 'active':
                        raise CareError('session_not_active', 409)
                    self._verify_provenance(proposal, action, state)
                if time.monotonic() >= deadline:
                    raise TimeoutError('deadline_exceeded')
                result = execute_action(action, store=self.store, context=self.context)
                return self._receipt(proposal, result)

    async def lookup(self, key: str, *, deadline: float) -> Receipt | None:
        """Recover real committed success after response loss or adapter restart."""
        with self._deadline(deadline):
            row = self.care_store.db.execute(
                'SELECT proposal FROM pending_effects WHERE run_id=? AND effect_key=?',
                (self.run_id, key),
            ).fetchone()
            if row is None:
                return None
            proposal = EffectProposal(**json.loads(row['proposal']))
            action, _ = self._prepare(proposal)
            result = get_receipt(action.idempotency_key, store=self.store, context=self.context)
            if result is None:
                return None
            # Never attach another successful grant to a different care proposal.
            stored = self.store.conn.execute(
                'SELECT order_id,kind,amount_vnd,source,evidence_ref,needs_approval,queue,confirmation_id '
                'FROM outbox WHERE action_id=?',
                (result.action_id,),
            ).fetchone()
            expected = (action.order_id, action.kind, action.amount_vnd, action.source, action.evidence_ref,
                        int(action.needs_approval), action.queue, action.confirmation_id)
            if stored is None or tuple(stored) != expected:
                raise CareError('receipt_binding_invalid', 409)
            return self._receipt(proposal, result)
