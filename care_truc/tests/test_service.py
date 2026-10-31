from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from contracts.types import ContactTask, OrderAssessment
from care_truc.models import (CareContext, DomainError, FeedSnapshot, GuardSnapshot,
                              MessageCommand, Principal, TrustedContext)
from care_truc.service import CareService
from care_truc.store import SqliteSessionStore

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


class Reader:
    def __init__(self):
        evidence = ({'feed': 'ops', 'source_table': 'scans', 'record_id': 'private',
                     'ingested_at': NOW, 'fact_code': 'logistics_stage',
                     'value': 'damaged', 'is_structured': True},)
        assessment = OrderAssessment('o1', NOW, 'late', date(2026, 10, 29),
                                     None, 2, .9, .9, 'carrier', (), evidence)
        guard = GuardSnapshot('a3', NOW, ('ops',), (FeedSnapshot('ops', 'trusted', NOW),), ())
        self.ctx = CareContext(assessment, None, 100000, guard, 'none')
        self.calls = 0
        self.error = None

    def read(self, trusted, order_id, assessment_ref=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.ctx


@pytest.fixture
def setup(tmp_path):
    store = SqliteSessionStore(tmp_path / 'care.sqlite')
    reader = Reader()
    trusted = TrustedContext(Principal('c1', False), 'run1', NOW)
    service = CareService(store, reader)
    yield service, store, reader, trusted
    store.close()


def contact(**changes):
    return replace(ContactTask('ct1', 'o1', NOW, NOW, 'chat', True, 'late', 'contact-key'), **changes)


def command(key='m1', text='Tại sao giao chậm?'):
    return MessageCommand(key, text, 'chat')


def test_open_customer_idempotent_and_payload_conflict(setup):
    service, store, reader, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    assert session.origin == 'customer' and session.turn_count == 0
    reader.error = RuntimeError('offline')
    assert service.open_chat(trusted, 'o1', 'open1') == session
    with pytest.raises(DomainError, match='request_conflict'):
        service.open_chat(trusted, 'other', 'open1')
    assert not store.history('c1', session.id).deliveries
    with pytest.raises(DomainError, match='request_conflict'):
        service.open_chat(replace(trusted, run_id='other'), 'o1', 'open1')


def test_client_open_never_promotes_to_a1_even_for_staff(setup):
    service, _, _, trusted = setup
    system = replace(trusted, principal=Principal('c1', True), source='system')
    assert service.open_chat(system, 'o1', 'open1').origin == 'customer'


def test_contact_requires_system_staff_and_only_prepares_delivery(setup):
    service, store, reader, trusted = setup
    for identity in (trusted, replace(trusted, principal=Principal('c1', True))):
        with pytest.raises(DomainError, match='system_context_required'):
            service.prepare_contact(identity, contact())
    system = replace(trusted, principal=Principal('c1', True), source='system')
    session = service.prepare_contact(system, contact())
    assert session.origin == 'a1' and session.turn_count == 0
    assert session.contact_delivery_status == 'pending_delivery'
    history = store.history('c1', session.id)
    assert len(history.deliveries) == 1 and not history.receipts
    reader.error = RuntimeError('offline')
    assert service.prepare_contact(system, contact()) == session
    with pytest.raises(DomainError, match='request_conflict'):
        service.prepare_contact(system, contact(reason_code='different'))
    with pytest.raises(DomainError, match='request_conflict'):
        service.prepare_contact(replace(system, run_id='other'), contact())
    with pytest.raises(DomainError, match='request_conflict'):
        service.prepare_contact(system, contact(channel='web_voice'))


@pytest.mark.parametrize('change', ['missing', 'old', 'feed', 'different_contact'])
def test_invalid_contact_context_never_creates_session(setup, change):
    service, store, reader, trusted = setup
    if change == 'missing':
        reader.ctx = replace(reader.ctx, assessment=None)
    elif change == 'old':
        reader.ctx = replace(reader.ctx, assessment=replace(reader.ctx.assessment, assessed_at=NOW-timedelta(minutes=31)))
    elif change == 'feed':
        reader.ctx = replace(reader.ctx, guard=None)
    else:
        reader.ctx = replace(reader.ctx, contact=contact(contact_id='other'))
    system = replace(trusted, principal=Principal('c1', True), source='system')
    with pytest.raises(DomainError):
        service.prepare_contact(system, contact())
    assert store.connection.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0


def test_message_persists_trace_and_replay_before_reader(setup):
    service, store, reader, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    response = service.message(trusted, session.id, command())
    assert response.assessment_ref.order_id == 'o1'
    assert response.evidence_refs and 'private' not in response.text
    history = store.history('c1', session.id)
    assert history.session.turn_count == 1 and len(history.messages) == 2
    assert {e.id for e in store.staff_trace(session.id)} == set(response.evidence_refs)
    assert 'private' in store.staff_trace(session.id)[0].trace
    assert 'private' not in str(store.public_evidence('c1', session.id))
    reader.error = RuntimeError('offline')
    calls = reader.calls
    assert service.message(trusted, session.id, command()) == response
    assert reader.calls == calls
    with pytest.raises(DomainError, match='request_conflict'):
        service.message(trusted, session.id, command(text='changed'))


@pytest.mark.parametrize('text,count', [('Tôi muốn gặp nhân viên và hủy đơn', 1), ('ngu', 3), ('Tại sao?', 8)])
def test_terminal_triggers_never_create_actions_and_retry_is_immutable(setup, text, count):
    service, store, reader, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    for number in range(count):
        cmd = command(str(number), text)
        response = service.message(trusted, session.id, cmd)
    history = store.history('c1', session.id)
    assert history.session.state == 'handoff_pending'
    assert history.session.turn_count == count
    assert not history.deliveries and not response.action_refs
    assert history.session.pending_cancel_id is None
    reader.error = RuntimeError('offline')
    assert service.message(trusted, session.id, cmd) == response
    with pytest.raises(DomainError, match='session_state_conflict'):
        service.message(trusted, session.id, command('new', 'Tôi muốn nhận xu'))
    assert store.history('c1', session.id) == history


def test_missing_facts_still_allows_human_handoff(setup):
    service, store, reader, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    reader.ctx = CareContext(None, None, None, None, 'unknown')
    result = service.message(trusted, session.id, command(text='Tôi muốn gặp nhân viên'))
    assert result.assessment_ref is None and not result.action_refs
    assert store.get_session('c1', session.id).state == 'handoff_pending'


def test_selector_runs_outside_transaction_after_classification_and_version_race_rejected(setup):
    service, store, reader, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    class Selector:
        def select(self, template_id, allowed):
            assert not store.connection.in_transaction
            assert template_id == 'ask_human'
            # Simulate another accepted turn using the public store boundary.
            from care_truc.models import Mutation, TurnResponse
            response = TurnResponse('race', 'race', 'off_topic', None, (), (), (), 'template', None)
            store.mutate('c1', session.id, 'race', 'race', lambda s: Mutation(replace(s, version=s.version+1, turn_count=s.turn_count+1), response))
            return {'phrase_id': 'warm'}
    service.phrase_selector = Selector()
    with pytest.raises(DomainError, match='session_version_conflict'):
        service.message(trusted, session.id, command(text='Tôi muốn gặp nhân viên'))
    assert store.get_session('c1', session.id).turn_count == 1
    assert len(store.history('c1', session.id).responses) == 1


def test_repeated_evidence_is_persisted_for_each_turn_and_scope_enforced(setup):
    service, store, _, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    for key in ('m1', 'm2'):
        service.message(trusted, session.id, command(key))
    assert len(store.staff_trace(session.id)) == 2
    for bad in (replace(trusted, run_id='other'), replace(trusted, principal=Principal('other', False))):
        with pytest.raises(DomainError, match='session_not_found'):
            service.message(bad, session.id, command())


def test_cached_open_contact_and_turn_survive_restart(tmp_path):
    path = tmp_path / 'restart.sqlite'
    trusted = TrustedContext(Principal('c1', False), 'run1', NOW)
    reader = Reader()
    store = SqliteSessionStore(path)
    service = CareService(store, reader)
    session = service.open_chat(trusted, 'o1', 'open1')
    response = service.message(trusted, session.id, command())
    system = replace(trusted, principal=Principal('c1', True), source='system')
    prepared = service.prepare_contact(system, contact())
    store.close()
    reader.error = RuntimeError('offline')
    store = SqliteSessionStore(path)
    try:
        service = CareService(store, reader)
        assert service.open_chat(trusted, 'o1', 'open1') == session
        assert service.prepare_contact(system, contact()) == prepared
        assert service.message(trusted, session.id, command()) == response
        assert store.get_session('c1', session.id).turn_count == 1
    finally:
        store.close()


def test_concurrent_contact_creation_reserves_one_session_and_delivery(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path = tmp_path / 'concurrent.sqlite'
    barrier = Barrier(2)
    trusted = TrustedContext(Principal('c1', True), 'run1', NOW, 'system')
    initial = SqliteSessionStore(path)
    initial.close()
    class ConcurrentReader(Reader):
        def read(self, *args):
            barrier.wait(timeout=5)
            return self.ctx
    def prepare():
        store = SqliteSessionStore(path)
        try:
            return CareService(store, ConcurrentReader()).prepare_contact(trusted, contact())
        finally:
            store.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(prepare) for _ in range(2)]
        sessions = [future.result() for future in futures]
    assert sessions[0] == sessions[1]
    store = SqliteSessionStore(path)
    try:
        assert store.connection.execute('SELECT count(*) FROM sessions').fetchone()[0] == 1
        assert len(store.history('c1', sessions[0].id).deliveries) == 1
    finally:
        store.close()


def test_reader_authorization_failure_is_never_treated_as_missing_facts(setup):
    service, store, reader, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    reader.error = DomainError('order_not_found', 404)
    with pytest.raises(DomainError, match='order_not_found'):
        service.message(trusted, session.id, command(text='Tôi muốn gặp nhân viên'))
    assert store.get_session('c1', session.id).turn_count == 0
    assert not store.history('c1', session.id).responses


@pytest.mark.parametrize('state', ['transferred', 'completed'])
def test_other_terminal_states_replay_old_turn_but_reject_new_message(setup, state):
    from care_truc.models import Mutation, TurnResponse
    service, store, reader, trusted = setup
    session = service.open_chat(trusted, 'o1', 'open1')
    old = service.message(trusted, session.id, command())
    synthetic = TurnResponse('finish', 'finish', 'accept', None, (), (), (), 'template', None)
    store.mutate('c1', session.id, 'finish', 'finish',
                 lambda s: Mutation(replace(s, state=state, version=s.version+1), synthetic))
    reader.error = RuntimeError('offline')
    assert service.message(trusted, session.id, command()) == old
    with pytest.raises(DomainError, match='session_state_conflict'):
        service.message(trusted, session.id, command('new'))
