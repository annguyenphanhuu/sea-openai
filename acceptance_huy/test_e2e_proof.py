"""Real executor tests with explicit local fixtures; no fabricated source verdicts."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3
from dataclasses import replace
import asyncio
import time

import pytest

from platform_huy.demo_provenance import DemoEvidence
from platform_huy.dto import SourceIdentity
from platform_huy.state import bootstrap, connect_state, utc
from care_truc.policy import CarePolicy
from care_truc.runtime_types import (ContextSnapshot, CustomerEvent, EffectProposal, FeedSnapshot,
    GuardSnapshot, PolicyOutcome, SessionState, TurnResult, canonical as care_canonical)
from care_truc.store import MemoryStore
from contracts.types import Action, OrderAssessment
from platform_huy.dto import ServerContext
from platform_huy.money import execute_action, get_receipt
from platform_huy.state_store import SqliteStateStore


NOW = datetime.fromisoformat('2026-10-24T14:30:00+07:00')


@pytest.fixture
def proof(tmp_path):
    core, ops = tmp_path / 'core.sqlite', tmp_path / 'ops.sqlite'
    db = sqlite3.connect(core)
    db.executescript("""
      CREATE TABLE orders(order_id,customer_id,seller_id,created_at,guaranteed_date,
        items_value_vnd,payment_method,cancelled_at,dest_station_id,warehouse_id);
      INSERT INTO orders VALUES('o','c','s','2026-10-21T08:00:00+07:00','2026-10-22',525000,'COD',NULL,'st','wh');
      CREATE TABLE scan_events(event_id,order_id,status,location_type,location_id,event_at,ingested_at);
      INSERT INTO scan_events VALUES('ev','o','out_for_delivery','station','st','2026-10-24T13:00:00+07:00','2026-10-24T13:01:00+07:00');
      INSERT INTO scan_events VALUES('future','o','delivered','customer',NULL,'2026-10-24T15:36:00+07:00','2026-10-24T15:37:00+07:00');
      CREATE TABLE delivery_attempts(attempt_id,order_id,attempt_at,outcome,reason_code,call_attempts);
      CREATE TABLE compensation_ledger(entry_id,order_id,kind,created_at);
      INSERT INTO compensation_ledger VALUES('v','o','voucher','2026-10-24T12:00:00+07:00');
      CREATE TABLE linehaul_reports(report_id,trip_id,reported_at,reason_code,driver_note);
      CREATE TABLE external_events(event_id,ts,kind,province_code,title,detail);
      CREATE TABLE stations(station_id,province_code);
      INSERT INTO stations VALUES('st','79');
      CREATE TABLE warehouses(warehouse_id,province_code);
      INSERT INTO warehouses VALUES('wh','79');
      CREATE TABLE sorting_centers(sc_id,province_code);
    """)
    db.commit(); db.close()
    sqlite3.connect(ops).close()
    conn = connect_state(tmp_path / 'runtime.sqlite')
    identity = SourceIdentity(sha256(core.read_bytes()).hexdigest(), sha256(ops.read_bytes()).hexdigest(),
                              datetime(2026, 10, 18, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc))
    bootstrap(conn, run_id='r', identity=identity, start_at=NOW)
    conn.execute('UPDATE demo_clock SET current_at=?', (utc(NOW),))
    yield DemoEvidence(conn, core, ops), conn
    conn.close()


def test_source_asof_and_independent_kind_history_require_human_review(proof):
    service, _ = proof
    facts = service.inspect_order('o', NOW)
    assert facts['order']['delivered_at'] is None
    assert facts['order']['payment_method'] == 'COD'
    assert facts['order']['items_value_vnd'] == 525000
    assert facts['late_days'] == 2
    assert facts['history'] == {'coins': 'not_granted', 'voucher': 'already_granted'}
    assert (facts['responsibility'], facts['force_majeure'], facts['verification_required']) == ('unknown', 'unknown', True)
    assert 'core:scan_events:future' not in facts['evidence_refs']


def test_review_is_audited_bound_to_actual_refs_and_current_material(proof):
    service, conn = proof
    with pytest.raises(ValueError, match='evidence_refs'):
        service.verify('o', NOW, reviewed_by='Huy', reason='reviewed', responsibility='carrier',
                       force_majeure='absent', evidence_refs=['invented'])
    refs = service.inspect_order('o', NOW)['evidence_refs']
    result = service.verify('o', NOW, reviewed_by='Huy', reason='Manual review of the fixture order and source scan',
                            responsibility='carrier', force_majeure='absent', evidence_refs=refs)
    assert result['verification_required'] is False
    assert result['evidence_ready'] is True
    assert conn.execute('SELECT reviewed_by,reason FROM eligibility_reviews').fetchone() == ('Huy', 'Manual review of the fixture order and source scan')
    later = datetime.fromisoformat('2026-10-24T16:00:00+07:00')
    assert service.inspect_order('o', later)['verification_required'] is True


def test_latest_withdrawn_review_never_resurrects_older_active_review(proof):
    service, conn = proof
    refs = service.inspect_order('o', NOW)['evidence_refs']
    for reason in ('first review', 'replacement review'):
        service.verify('o', NOW, reviewed_by='Huy', reason=reason, responsibility='carrier',
                       force_majeure='absent', evidence_refs=refs)
    conn.execute("UPDATE eligibility_reviews SET state='withdrawn' WHERE revision=2")
    result = service.inspect_order('o', NOW)
    assert (result['review_id'], result['responsibility'], result['force_majeure']) == (None, 'unknown', 'unknown')
    assert (result['verification_required'], result['evidence_ready']) == (True, False)


def persisted_request(proof, tmp_path, text='Xin boi thuong xu', *, cancel=False):
    """Fixture transport persists a real policy result; executor is always real."""
    service, conn = proof
    care = MemoryStore.open(tmp_path / 'care.sqlite')
    state = SessionState('session', 'r', 'customer', 'o', opened_by='a1', contact_id='contact')
    care.create_session(state, 'opening')
    opening = EffectProposal('opening-effect','opening-effect','session','o','contact_send','{}','')
    care.db.execute("INSERT INTO pending_effects(id,run_id,effect_key,session_id,proposal,session_version,state,outcome,attempts) VALUES ('opening-effect','r','opening-effect','session',?,0,'delivered','succeeded',1)", (care_canonical(opening),))
    conn.execute("INSERT INTO contact_log(contact_id,order_id,channel,initiated_by,status,requested_at,opened_at,provider_session_id) VALUES ('contact','o','chat','A1','active',?,?,'session')", (utc(NOW), utc(NOW)))
    for feed in ('orders','scan_events','delivery_attempts'):
        if not conn.execute('SELECT 1 FROM guard_heartbeat').fetchone():
            conn.execute("INSERT INTO guard_heartbeat VALUES (?,'A3',?,1,'[]')", (utc(NOW), utc(NOW)))
        conn.execute('INSERT INTO feed_health VALUES (?,?,?,?,?,?,?)', (feed, utc(NOW), 'trusted', utc(NOW), utc(NOW), utc(NOW), '[]'))
    assessment = OrderAssessment('o', NOW, 'late', datetime(2026,10,22).date(), None, 2, 1.0, 0.9, 'carrier', (), ())
    snapshot = ContextSnapshot('customer', 'o', NOW, assessment,
        GuardSnapshot('a3', NOW, (FeedSnapshot('orders','trusted',NOW),), ('orders',), True, True),
        525000, False, True, True, ledger_pending=False)

    def commit(event):
        nonlocal state
        req = care.begin_request('session', 'customer', event, event.request_id)
        outcome = CarePolicy().evaluate(state, event, snapshot)
        if outcome.state.pending:
            outcome = replace(outcome, state=replace(outcome.state, pending=replace(outcome.state.pending, reply_to=req['id'] + ':response')))
        proposals = tuple(replace(p, evidence_ref=req['id'], payload=care_canonical({**json.loads(p.payload), 'evidence_ref':req['id']})) for p in outcome.proposals)
        outcome = replace(outcome, proposals=proposals)
        response = TurnResult('committed','session', confirmation_id=outcome.state.pending.confirmation_id if outcome.state.pending else None)
        bundle = {'snapshot':snapshot,'session':state,'event':event,'proposals':proposals}
        care.commit_turn(req['id'], state.version, outcome, response, care_canonical(bundle), '{}')
        state = care.load_session('session')
        return proposals

    if cancel:
        commit(CustomerEvent('message','want-cancel','Toi muon huy don'))
        proposals = commit(CustomerEvent('confirm_cancel','confirm', confirmation_id=state.pending.confirmation_id,
            reply_to=state.pending.reply_to, confirmed=True))
    else:
        proposals = commit(CustomerEvent('message','text',text))
    return care, proposals[0] if proposals else None


def executor(proof):
    from platform_huy.demo_provenance import EVIDENCE_PRODUCER, MESSAGE_RECORDER, REQUEST_RULE
    return SqliteStateStore(proof[1], evidence_producers=frozenset({EVIDENCE_PRODUCER}),
        message_recorders=frozenset({MESSAGE_RECORDER}), request_rule_versions=frozenset({REQUEST_RULE}))


def test_real_policy_text_cannot_grant_until_review_then_success_and_replay(proof, tmp_path):
    service, conn = proof
    care, proposal = persisted_request(proof, tmp_path)
    evidence = service.record_text(care, proposal, NOW)
    context = ServerContext('a1-service','a1','c',None,frozenset({'actions:coins'}))
    payload = json.loads(proposal.payload)
    action = Action(**{**payload,'requested_at':NOW,'evidence_ref':evidence,'idempotency_key':'xu:o'})
    blocked = execute_action(action, store=executor(proof), context=context)
    assert blocked.reason_codes == ('eligibility_unverified',)
    assert conn.execute('SELECT count(*) FROM ledger_new').fetchone() == (0,)
    refs = service.inspect_order('o',NOW)['evidence_refs']
    service.verify('o',NOW,reviewed_by='Huy',reason='Explicit test human review',responsibility='carrier',force_majeure='absent',evidence_refs=refs)
    evidence = service.record_text(care, proposal, NOW)
    action = replace(action,evidence_ref=evidence)
    success = execute_action(action, store=executor(proof), context=context)
    assert (success.decision,success.amount_xu) == ('succeeded',26000)
    assert get_receipt('xu:o',store=executor(proof),context=context).replayed is True
    assert conn.execute('SELECT count(*),sum(amount_xu) FROM ledger_new').fetchone() == (1,26000)
    assert conn.execute('SELECT count(*) FROM voucher_ledger').fetchone() == (0,)


def test_forged_event_does_not_inherit_saved_customer_authority(proof,tmp_path):
    service, conn = proof
    care, proposal = persisted_request(proof,tmp_path)
    row = care.db.execute('SELECT data FROM evidence_bundles WHERE ref=?',(proposal.evidence_ref,)).fetchone()
    bundle = json.loads(row[0]); bundle['event']['text'] = 'khong xin xu'
    care.db.execute('UPDATE evidence_bundles SET data=? WHERE ref=?',(care_canonical(bundle),proposal.evidence_ref))
    with pytest.raises(ValueError,match='care_provenance_invalid'):
        service.record_text(care,proposal,NOW)
    assert conn.execute('SELECT count(*) FROM customer_messages').fetchone() == (0,)


def test_confirmed_cancel_queues_review_without_money_and_replays(proof,tmp_path):
    service,conn = proof
    care,proposal = persisted_request(proof,tmp_path,cancel=True)
    evidence = service.record_text(care,proposal,NOW)
    context = ServerContext('a1-service','a1','c',None,frozenset({'cancel:request'}))
    action = Action(**{**json.loads(proposal.payload),'requested_at':NOW,'evidence_ref':evidence})
    result = execute_action(action,store=executor(proof),context=context)
    assert (result.decision,result.amount_xu,result.amount_vnd) == ('succeeded',None,None)
    assert result.cancel_id
    assert conn.execute('SELECT status,needs_approval,amount_vnd FROM outbox').fetchone() == ('pending',1,0)
    assert conn.execute('SELECT status,customer_id FROM cancel_requests').fetchone() == ('awaiting_review','c')
    assert conn.execute('SELECT count(*) FROM ledger_new').fetchone() == (0,)
    assert get_receipt(action.idempotency_key,store=executor(proof),context=context).cancel_id == result.cancel_id
    assert execute_action(action,store=executor(proof),context=context).replayed is True


def test_cancel_confirmation_requires_prior_real_response(proof,tmp_path):
    service,_ = proof
    care,proposal = persisted_request(proof,tmp_path,cancel=True)
    care.db.execute("DELETE FROM events WHERE kind='response'")
    with pytest.raises(ValueError,match='cancel_prior_confirmation_missing'):
        service.record_text(care,proposal,NOW)


def test_gateway_acknowledges_cancel_as_awaiting_approval(proof,tmp_path):
    from platform_huy.effect_gateway import SqliteEffectGateway
    service,conn = proof
    care,proposal = persisted_request(proof,tmp_path,cancel=True)
    evidence = service.record_text(care,proposal,NOW)
    care.db.execute('UPDATE pending_effects SET attempts=1 WHERE id=?',(proposal.effect_id,))
    gateway = SqliteEffectGateway(executor(proof),care,
        context=ServerContext('a1-service','a1','c',None,frozenset({'cancel:request'})),
        customer_principal='customer',evidence_bindings={proposal.evidence_ref:evidence})
    receipt = asyncio.run(gateway.submit(proposal,deadline=time.monotonic()+2))
    assert receipt.outcome == 'awaiting_approval'
    recovered = asyncio.run(gateway.lookup(proposal.key,deadline=time.monotonic()+2))
    assert recovered == receipt
    assert conn.execute('SELECT status FROM cancel_requests').fetchone() == ('awaiting_review',)
    assert conn.execute('SELECT count(*) FROM ledger_new').fetchone() == (0,)


def test_cancel_transaction_rolls_back_if_receipt_write_fails(proof,tmp_path):
    from platform_huy.dto import PlatformError
    service,conn = proof
    care,proposal = persisted_request(proof,tmp_path,cancel=True)
    evidence = service.record_text(care,proposal,NOW)
    action = Action(**{**json.loads(proposal.payload),'requested_at':NOW,'evidence_ref':evidence})
    conn.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON action_receipts BEGIN SELECT RAISE(ABORT,'fail'); END")
    with pytest.raises(PlatformError,match='Runtime state is unavailable'):
        execute_action(action,store=executor(proof),context=ServerContext('a1-service','a1','c',None,frozenset({'cancel:request'})))
    assert conn.execute('SELECT count(*) FROM outbox').fetchone() == (0,)
    assert conn.execute('SELECT count(*) FROM cancel_requests').fetchone() == (0,)


def test_unchanged_contact_cannot_replace_actual_delivered_opening(proof,tmp_path):
    service,conn = proof
    care,proposal = persisted_request(proof,tmp_path,cancel=True)
    care.db.execute("UPDATE pending_effects SET outcome='unknown' WHERE id='opening-effect'")
    with pytest.raises(ValueError,match='a1_delivery_missing'):
        service.record_text(care,proposal,NOW)
    assert conn.execute('SELECT count(*) FROM execution_evidence').fetchone() == (0,)


def test_customer_text_does_not_clear_source_fault_or_force_majeure(proof,tmp_path):
    service,conn = proof
    care,proposal = persisted_request(proof,tmp_path,text='Xin xu boi thuong, toi khong co loi va khong co thien tai')
    evidence = service.record_text(care,proposal,NOW)
    payload = json.loads(conn.execute('SELECT payload_json FROM execution_evidence WHERE evidence_id=?',(evidence,)).fetchone()[0])
    assert (payload['responsibility'],payload['force_majeure'],payload['review_id']) == ('unknown','unknown',None)


@pytest.mark.parametrize('changed', ['principal', 'run', 'key', 'order', 'stale_assessment'])
def test_demo_gateway_rechecks_final_authority_and_context(proof, tmp_path, changed):
    """A previously accepted gate cannot authorize changed durable delivery facts."""
    from types import SimpleNamespace
    from care_truc.guardrails import Guardrails
    from care_truc.runtime_types import CareError
    from platform_huy.demo_flow import _Gateway

    _, conn = proof
    care = MemoryStore.open(tmp_path / 'final-care.sqlite')
    try:
        state = SessionState('session', 'r', 'customer', 'o', opened_by='a1', contact_id='contact')
        care.create_session(state, 'opening')
        proposal = EffectProposal('opening', 'opening', 'session', 'o', 'contact_send',
                                  care_canonical({'text': 'Opening'}), '')
        care.db.execute("INSERT INTO pending_effects(id,run_id,effect_key,session_id,proposal,session_version,state,outcome,attempts) "
                        "VALUES ('opening','r','opening','session',?,0,'in_flight','unknown',1)",
                        (care_canonical(proposal),))
        conn.execute('CREATE TABLE demo_inbox(effect_id PRIMARY KEY,effect_key,session_id,order_id,text,created_at)')
        conn.execute('CREATE TABLE demo_handoffs(effect_id PRIMARY KEY,session_id,payload,created_at)')
        assessment = OrderAssessment('o', NOW, 'late', datetime(2026,10,22).date(),
                                     None, 2, 1.0, 0.9, 'carrier', (), ())
        if changed == 'stale_assessment':
            assessment = replace(assessment, assessed_at=datetime.fromisoformat('2026-10-24T13:00:00+07:00'))
        elif changed == 'key':
            care.db.execute("UPDATE pending_effects SET effect_key='another-key'")
        else:
            field = {'principal': 'principal_id', 'run': 'run_id', 'order': 'order_id'}[changed]
            altered = replace(state, **{field: 'another'})
            care.db.execute('UPDATE sessions SET data=? WHERE id=?', (care_canonical(altered), state.session_id))
        snapshot = ContextSnapshot('customer', 'o', NOW, assessment,
            GuardSnapshot('a3', NOW, (FeedSnapshot('orders','trusted',NOW),), ('orders',), True, True))
        flow = SimpleNamespace(conn=conn, run_id='r', now=NOW, gateway_errors=[],
            care=SimpleNamespace(store=care, harness=SimpleNamespace(guards=Guardrails())),
            context=SimpleNamespace(snapshot=lambda ctx, order_id: snapshot),
            _inspect=lambda order_id: {'order': {'customer_id': 'c'}},
            _principal=lambda facts: 'customer', _allowed=lambda: True,
            _contacted_today=lambda customer, excluding=None: False)
        expected = 'final_dispatch_blocked' if changed == 'stale_assessment' else 'effect_binding_invalid'
        with pytest.raises(CareError, match=expected):
            asyncio.run(_Gateway(flow).submit(proposal, deadline=time.monotonic() + 2))
        for table in ('demo_inbox', 'demo_handoffs', 'contact_log'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone() == (0,)
    finally:
        care.close()


@pytest.mark.parametrize('adapter', ['recorder', 'gateway'])
@pytest.mark.parametrize('changed', ['confirmed', 'reply_to'])
def test_platform_cancellation_requires_explicit_bound_consent(proof, tmp_path, adapter, changed):
    from care_truc.runtime_types import CareError
    from platform_huy.effect_gateway import SqliteEffectGateway

    service, conn = proof
    care, proposal = persisted_request(proof, tmp_path, cancel=True)
    try:
        evidence = service.record_text(care, proposal, NOW) if adapter == 'gateway' else None
        row = care.db.execute('SELECT data FROM evidence_bundles WHERE ref=?', (proposal.evidence_ref,)).fetchone()
        bundle = json.loads(row[0])
        bundle['event'][changed] = False if changed == 'confirmed' else 'different-prompt'
        care.db.execute('UPDATE evidence_bundles SET data=? WHERE ref=?',
                        (care_canonical(bundle), proposal.evidence_ref))
        care.db.execute('UPDATE requests SET payload=? WHERE id=?',
                        (care_canonical(bundle['event']), proposal.evidence_ref))
        if adapter == 'recorder':
            with pytest.raises(ValueError, match='cancel_confirmation_invalid'):
                service.record_text(care, proposal, NOW)
        else:
            care.db.execute('UPDATE pending_effects SET attempts=1 WHERE id=?', (proposal.effect_id,))
            gateway = SqliteEffectGateway(executor(proof), care,
                context=ServerContext('a1-service','a1','c',None,frozenset({'cancel:request'})),
                customer_principal='customer', evidence_bindings={proposal.evidence_ref: evidence})
            with pytest.raises(CareError, match='care_evidence_invalid'):
                asyncio.run(gateway.submit(proposal, deadline=time.monotonic() + 2))
        for table in ('cancel_requests', 'outbox', 'ledger_new', 'action_receipts'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone() == (0,)
    finally:
        care.close()


def test_financial_acceptance_holds_care_authority_lock(proof, tmp_path, monkeypatch):
    from platform_huy.effect_gateway import SqliteEffectGateway

    service, conn = proof
    care, proposal = persisted_request(proof, tmp_path, cancel=True)
    contender = sqlite3.connect(tmp_path / 'care.sqlite', isolation_level=None, timeout=0)
    try:
        evidence = service.record_text(care, proposal, NOW)
        care.db.execute('UPDATE pending_effects SET attempts=1 WHERE id=?', (proposal.effect_id,))
        gateway = SqliteEffectGateway(executor(proof), care,
            context=ServerContext('a1-service','a1','c',None,frozenset({'cancel:request'})),
            customer_principal='customer', evidence_bindings={proposal.evidence_ref: evidence})
        original = gateway._verify_provenance
        checked = []

        def attempt_authority_change(*args):
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                contender.execute("UPDATE sessions SET principal='another' WHERE id='session'")
            checked.append(True)
            return original(*args)

        monkeypatch.setattr(gateway, '_verify_provenance', attempt_authority_change)
        receipt = asyncio.run(gateway.submit(proposal, deadline=time.monotonic() + 2))
        assert checked == [True]
        assert receipt.outcome == 'awaiting_approval'
        assert conn.execute('SELECT count(*) FROM cancel_requests').fetchone() == (1,)
        assert conn.execute('SELECT count(*) FROM ledger_new').fetchone() == (0,)
    finally:
        contender.close()
        care.close()


@pytest.fixture
def nonfinancial_gateway(proof, tmp_path):
    from types import SimpleNamespace
    from care_truc.guardrails import Guardrails
    from platform_huy.demo_flow import _Gateway

    _, conn = proof
    care = MemoryStore.open(tmp_path / 'deadline-care.sqlite')
    conn.execute('CREATE TABLE demo_inbox(effect_id PRIMARY KEY,effect_key,session_id,order_id,text,created_at)')
    conn.execute('CREATE TABLE demo_handoffs(effect_id PRIMARY KEY,session_id,payload,created_at)')
    assessment = OrderAssessment('o', NOW, 'late', datetime(2026,10,22).date(),
                                 None, 2, 1.0, 0.9, 'carrier', (), ())
    snapshot = ContextSnapshot('customer', 'o', NOW, assessment,
        GuardSnapshot('a3', NOW, (FeedSnapshot('orders','trusted',NOW),), ('orders',), True, True))
    flow = SimpleNamespace(conn=conn, run_id='r', now=NOW, gateway_errors=[],
        care=SimpleNamespace(store=care, harness=SimpleNamespace(guards=Guardrails())),
        context=SimpleNamespace(snapshot=lambda ctx, order_id: snapshot),
        _inspect=lambda order_id: {'order': {'customer_id': 'c'}},
        _principal=lambda facts: 'customer', _allowed=lambda: True,
        _contacted_today=lambda customer, excluding=None: False)

    def prepare(kind):
        state = SessionState('session', 'r', 'customer', 'o', opened_by='a1', contact_id='contact',
                             status='handoff_pending' if kind == 'handoff_request' else 'active')
        care.create_session(state, 'opening')
        proposal = EffectProposal('effect', 'effect', 'session', 'o', kind,
                                  care_canonical({'text': 'Opening', 'reason': 'human'}), '')
        care.db.execute("INSERT INTO pending_effects(id,run_id,effect_key,session_id,proposal,session_version,state,outcome,attempts) "
                        "VALUES ('effect','r','effect','session',?,0,'in_flight','unknown',1)",
                        (care_canonical(proposal),))
        return _Gateway(flow), proposal

    yield flow, prepare
    care.close()


@pytest.mark.parametrize('kind', ['contact_send', 'handoff_request'])
@pytest.mark.parametrize('expire_during', ['validation', 'write'])
def test_nonfinancial_deadline_expiry_rolls_back_all_effects(nonfinancial_gateway, monkeypatch, kind, expire_during):
    flow, prepare = nonfinancial_gateway
    gateway, proposal = prepare(kind)
    now = [0.0]
    monkeypatch.setattr('platform_huy.demo_flow.time.monotonic', lambda: now[0])
    before_timeouts = [conn.execute('PRAGMA busy_timeout').fetchone()[0]
                       for conn in (flow.conn, flow.care.store.db)]

    def expire():
        now[0] = 2.0
        return 0

    if expire_during == 'validation':
        original = flow._inspect

        def inspect(order_id):
            expire()
            return original(order_id)

        flow._inspect = inspect
    else:
        table = 'demo_inbox' if kind == 'contact_send' else 'demo_handoffs'
        flow.conn.create_function('expire_deadline', 0, expire)
        flow.conn.execute(f'CREATE TRIGGER expire_write AFTER INSERT ON {table} BEGIN SELECT expire_deadline(); END')
    with pytest.raises(TimeoutError, match='deadline_exceeded'):
        asyncio.run(gateway.submit(proposal, deadline=1.0))
    for table in ('demo_inbox', 'demo_handoffs', 'contact_log'):
        assert flow.conn.execute(f'SELECT count(*) FROM {table}').fetchone() == (0,)
    assert not flow.conn.in_transaction
    assert not flow.care.store.db.in_transaction
    assert [conn.execute('PRAGMA busy_timeout').fetchone()[0]
            for conn in (flow.conn, flow.care.store.db)] == before_timeouts


@pytest.mark.parametrize('locked_store', ['care', 'platform'])
def test_nonfinancial_sqlite_lock_wait_is_bounded(nonfinancial_gateway, locked_store):
    from platform_huy.dto import PlatformError

    flow, prepare = nonfinancial_gateway
    gateway, proposal = prepare('handoff_request')
    conn = flow.care.store.db if locked_store == 'care' else flow.conn
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    contender = sqlite3.connect(path, isolation_level=None)
    try:
        contender.execute('BEGIN IMMEDIATE')
        started = time.monotonic()
        with pytest.raises((TimeoutError, sqlite3.OperationalError, PlatformError)):
            asyncio.run(gateway.submit(proposal, deadline=started + 0.05))
        assert time.monotonic() - started < 0.75
        assert flow.conn.execute('SELECT count(*) FROM demo_handoffs').fetchone() == (0,)
    finally:
        contender.rollback()
        contender.close()
