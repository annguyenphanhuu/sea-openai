"""Durable cancellation lifecycle, participating in the existing turn transaction."""
import json

from .runtime_types import CareError, canonical

SCHEMA = """CREATE TABLE IF NOT EXISTS cancellations(
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, principal_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id), data TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','invalidated','expired','consumed')),
    consumed_request TEXT REFERENCES requests(id));"""


def commit_lifecycle(store, current, state, outcome, request_id):
    old, new = current.pending, state.pending
    if old and old != new:
        cancel = any(json.loads(p.payload).get('kind') == 'cancel_request'
                     for p in outcome.proposals if p.kind == 'action_request')
        status = 'consumed' if cancel else ('expired' if 'cancel_confirmation_expired' in outcome.codes else 'invalidated')
        changed = store.db.execute(
            "UPDATE cancellations SET status=?,consumed_request=? WHERE id=? AND run_id=? "
            "AND principal_id=? AND session_id=? AND status='pending'",
            (status, request_id if cancel else None, old.confirmation_id, current.run_id,
             current.principal_id, current.session_id)).rowcount
        if cancel and not changed:
            raise CareError('cancel_confirmation_invalid')
    if new and new != old:
        if (new.principal_id, new.session_id, new.order_id, new.contact_id, new.version) != (
                state.principal_id, state.session_id, state.order_id, state.contact_id, state.version):
            raise CareError('cancel_confirmation_invalid')
        store.db.execute('INSERT INTO cancellations VALUES(?,?,?,?,?,?,NULL)',
            (new.confirmation_id, state.run_id, state.principal_id, state.session_id, canonical(new), 'pending'))


def validate_action(store, payload, request_id, state):
    row = store.db.execute('SELECT * FROM cancellations WHERE id=?',
                           (payload.get('confirmation_id'),)).fetchone()
    if row is None or row['status'] != 'consumed' or row['consumed_request'] != request_id:
        raise CareError('cancel_confirmation_invalid')
    data = json.loads(row['data'])
    if (row['run_id'], row['principal_id'], row['session_id'], data['order_id'], data['contact_id']) != (
            state.run_id, state.principal_id, state.session_id, state.order_id, state.contact_id):
        raise CareError('cancel_confirmation_invalid')
    if data['version'] != state.version - 1:
        raise CareError('cancel_confirmation_invalid')
    if (type(payload.get('amount_vnd')) is not int or payload.get('amount_vnd') != 0
            or payload.get('source') != 'a1' or payload.get('queue') != 'cancel_review'
            or payload.get('needs_approval') is not True
            or payload.get('idempotency_key') != f"{state.run_id}:cancel:{row['id']}"):
        raise CareError('cancel_confirmation_invalid')


def lacks_cancellation_evidence(store, effect) -> bool:
    """Old cancellation proposals cannot manufacture a second-confirmation grant."""
    proposal = json.loads(effect['proposal'])
    payload = json.loads(proposal['payload'])
    if proposal['kind'] != 'action_request' or payload.get('kind') != 'cancel_request':
        return False
    record = store.db.execute('SELECT * FROM cancellations WHERE id=?',
                              (payload.get('confirmation_id'),)).fetchone()
    if record is None or record['status'] != 'consumed':
        return True
    state = store.load_session(effect['session_id'])
    data = json.loads(record['data'])
    source = store.db.execute('SELECT request_id FROM effect_proposals WHERE effect_id=? AND revision=?',
                             (effect['id'], effect['revision'])).fetchone()
    return (source is None or source['request_id'] != record['consumed_request']
        or (record['run_id'], record['principal_id'], record['session_id'], data['order_id'], data['contact_id']) !=
           (effect['run_id'], state.principal_id, state.session_id, state.order_id, state.contact_id)
        or proposal['order_id'] != state.order_id or payload.get('order_id') != state.order_id
        or proposal['key'] != f"{state.run_id}:cancel:{record['id']}"
        or payload.get('idempotency_key') != proposal['key'])


def quarantine_legacy_cancellations(store) -> None:
    """Never send unproven unsent effects; preserve uncertain remote outcomes."""
    for effect in store.db.execute("SELECT * FROM pending_effects WHERE state IN ('pending_delivery','retry_wait')").fetchall():
        if lacks_cancellation_evidence(store, effect):
            store.set_effect(effect['id'], state='needs_reconciliation' if effect['attempts'] else 'blocked')
