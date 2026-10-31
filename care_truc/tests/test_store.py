from dataclasses import replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from care_truc.models import Session, Mutation, TurnResponse, DomainError
from care_truc.store import SqliteSessionStore


def session(id='s'):
    return Session(id, 'p', 'run', 'order', 'chat', 'customer', None, None, 'active', 0, 0, 0, None)


def transition(s):
    return Mutation(replace(s, version=s.version + 1, turn_count=s.turn_count + 1),
                    TurnResponse('m', 'hello', 'accept', None, (), (), (), 'template', None))


def test_retry_restart_ownership_and_snapshot(tmp_path):
    path = tmp_path / 'care.sqlite'
    a = SqliteSessionStore(path)
    a.create_session(session(), 'contact')
    response = a.mutate('p', 's', 'r', 'hash', transition)
    a.close()
    a = SqliteSessionStore(path)
    assert a.mutate('p', 's', 'r', 'hash', lambda s: 1/0) == response
    assert a.history('p', 's').session.turn_count == 1
    for principal, digest, code in [('p', 'other', 'request_conflict'), ('other', 'hash', 'session_not_found')]:
        with pytest.raises(DomainError) as error:
            a.mutate(principal, 's', 'r', digest, transition)
        assert error.value.code == code
    with pytest.raises(DomainError):
        a.mutate('p', 's', 'r2', 'hash', transition, expected_version=0)


def test_atomic_rollback_and_contact_unique(tmp_path):
    a = SqliteSessionStore(tmp_path / 'care.sqlite')
    a.create_session(session(), 'contact')
    with pytest.raises(DomainError):
        a.create_session(session('s2'), 'contact')
    def broken(s):
        raise RuntimeError('broken')
    with pytest.raises(RuntimeError):
        a.mutate('p', 's', 'r', 'hash', broken)
    assert a.history('p', 's').session.version == 0
    assert a.history('p', 's').responses == ()


def test_two_connections_one_mutation(tmp_path):
    path = tmp_path / 'care.sqlite'
    a, b = SqliteSessionStore(path), SqliteSessionStore(path)
    a.create_session(session(), None)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda store: store.mutate('p', 's', 'r', 'hash', transition), (a,b)))
    assert results[0] == results[1]
    assert a.history('p', 's').session.turn_count == 1


from contracts.types import Action
from care_truc.models import PendingDelivery, Receipt, PendingCancel, StoredMessage, StoredEvidence
from datetime import timedelta

NOW = datetime(2026,10,31,tzinfo=timezone.utc)


def with_delivery(s, key='key'):
    mutation = transition(s)
    action = Action(key, s.order_id, 'coins', 100, 'a1', NOW, key, 'e', False, 'care')
    delivery = PendingDelivery(key,s.id,'action',key,action,'pending_delivery',None)
    return replace(mutation, deliveries=(delivery,),
                   messages=(StoredMessage('message-'+s.id,'customer','hello',NOW),),
                   evidence=(StoredEvidence('e-'+s.id,'public','private'),))


def test_outbox_lease_receipt_restart_and_coin_uniqueness(tmp_path):
    path = tmp_path / 'care.sqlite'
    a,b = SqliteSessionStore(path), SqliteSessionStore(path)
    a.create_session(session(), None)
    a.create_session(session('s2'), None)
    a.mutate('p','s','r','hash',with_delivery)
    with pytest.raises(DomainError):
        b.mutate('p','s2','r','hash',lambda s: with_delivery(s,'key2'))
    assert b.history('p','s2').session.version == 0
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda store: store.claim_deliveries(NOW,10),(a,b)))
    assert sorted(map(len,claims)) == [0,1]
    a.close()
    a = SqliteSessionStore(path)
    assert a.claim_deliveries(NOW,10) == ()
    assert len(a.claim_deliveries(NOW+timedelta(minutes=1),10)) == 1
    for receipt in [Receipt('key','external','succeeded',2,'e'),Receipt('key',None,'pending',1,None),Receipt('key',None,'failed',3,None)]:
        a.record_receipt(receipt)
    history = a.history('p','s')
    assert history.receipts[0].status == 'succeeded'
    assert len(history.events) == 1
    assert len(history.messages) == 1
    assert history.deliveries[0].status == 'succeeded'
    assert a.claim_deliveries(NOW+timedelta(minutes=2),10) == ()
    assert a.staff_trace('s')[0].trace == 'private'


def test_cancel_durable_and_late_failure_rolls_back_every_table(tmp_path):
    path = tmp_path / 'care.sqlite'
    a = SqliteSessionStore(path)
    a.create_session(session(),None)
    cancel = PendingCancel('cancel','p','s','order',None,1,'prompt',NOW,'pending')
    def change(s):
        return replace(with_delivery(s),pending_cancel=cancel)
    a.mutate('p','s','r','hash',change)
    a.close()
    a = SqliteSessionStore(path)
    assert a.get_cancellation('p','s','cancel') == cancel
    before = a.history('p','s')

    # The last delivery conflicts only after fresh messages/evidence, a changed
    # cancellation and the first outbox row/handoff reservation were written.
    from care_truc.models import HandoffSummary
    summary = HandoffSummary('handoff', 's', 'reason', 'need', (), (), (), None, ())
    handoff = PendingDelivery('fresh-handoff', 's', 'handoff', 'fresh-handoff',
                              summary, 'pending_delivery', None)
    def late_conflict(s):
        mutation = with_delivery(s)
        return replace(
            mutation,
            messages=(StoredMessage('fresh-message', 'customer', 'new text', NOW),),
            evidence=(StoredEvidence('fresh-evidence', 'new public', 'new trace'),),
            pending_cancel=replace(cancel, status='confirmed'),
            deliveries=(handoff, mutation.deliveries[0]),
        )
    with pytest.raises(DomainError):
        a.mutate('p','s','r2','hash',late_conflict)
    assert a.history('p','s') == before
    assert a.get_cancellation('p', 's', 'cancel') == cancel
    assert a.staff_trace('s') == (StoredEvidence('e-s', 'public', 'private'),)
    for table in ('requests', 'messages', 'evidence', 'cancellations', 'deliveries'):
        assert a.connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 1
    # Reusing the rolled-back id/key and handoff reservation now succeeds.
    a.mutate('p', 's', 'r2', 'hash',
             lambda s: replace(transition(s), deliveries=(handoff,)))
    assert len(a.history('p', 's').deliveries) == 2


def test_one_handoff_and_busy_are_conflicts(tmp_path):
    from care_truc.models import HandoffSummary
    path = tmp_path / 'care.sqlite'
    a,b = SqliteSessionStore(path),SqliteSessionStore(path)
    a.create_session(session(),None)
    summary = HandoffSummary('h','s','reason','need',(),(),(),None,())
    a.mutate('p','s','r','hash',lambda s: replace(transition(s),handoff=summary))
    with pytest.raises(DomainError):
        b.mutate('p','s','r2','hash',lambda s: replace(transition(s),handoff=summary))
    a.connection.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(DomainError) as error:
            b.mutate('p','s','r2','hash',transition)
        assert error.value.code == 'store_busy'
    finally:
        a.connection.rollback()

@pytest.mark.parametrize('kind', ['coins', 'cancel_request', 'eta_notice'])
def test_action_order_must_match_session(tmp_path, kind):
    a = SqliteSessionStore(tmp_path / 'care.sqlite')
    a.create_session(session(), None)
    def wrong_order(s):
        mutation = with_delivery(s)
        delivery = mutation.deliveries[0]
        action = replace(delivery.payload, order_id='different-order', kind=kind)
        return replace(mutation, deliveries=(replace(delivery, payload=action),))
    with pytest.raises(DomainError) as error:
        a.mutate('p', 's', 'r', 'hash', wrong_order)
    assert error.value.code == 'invalid_delivery_order'
    assert a.history('p', 's').session.version == 0
    assert a.connection.execute('SELECT count(*) FROM deliveries').fetchone()[0] == 0


def test_distinct_coin_keys_race_across_sessions(tmp_path):
    path = tmp_path / 'care.sqlite'
    a, b = SqliteSessionStore(path), SqliteSessionStore(path)
    a.create_session(session(), None)
    a.create_session(session('s2'), None)
    def attempt(args):
        store, session_id, key = args
        try:
            store.mutate('p', session_id, 'r', 'hash', lambda s: with_delivery(s, key))
            return 'persisted'
        except DomainError as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, ((a, 's', 'coin-1'), (b, 's2', 'coin-2'))))
    assert sorted(results) == ['persisted', 'store_conflict']
    for table in ('requests', 'deliveries', 'messages', 'evidence'):
        assert a.connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 1
