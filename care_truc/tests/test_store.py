"""Task 3 invariants ported to the main MemoryStore and effect journal."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
import pytest
from care_truc.runtime_types import (CareError, CustomerEvent, EffectProposal,
    PendingCancellation, PolicyOutcome, Receipt, SessionState, TurnResult, canonical, fingerprint)
from care_truc.store import MemoryStore
from .helpers import NOW


def setup(path):
    store=MemoryStore.open(path)
    store.create_session(SessionState('s','run','customer','o1'),'open')
    return store


def turn(store, sid='s', key='m', proposals=(), pending=None):
    state=store.load_session(sid)
    event=CustomerEvent('message',key,'hello')
    request=store.begin_request(sid,'customer',event,fingerprint(event))
    outcome=PolicyOutcome(replace(state,turn_count=state.turn_count+1,pending=pending),
                          'off_topic','clarify',proposals=proposals)
    result=TurnResult('committed',sid,'answer',effect_ids=tuple(p.effect_id for p in proposals))
    return store.commit_turn(request['id'],state.version,outcome,result,'{"private":"trace"}','{}')


def effect(key='coin',sid='s',order='o1',kind='coins'):
    return EffectProposal(key,key,sid,order,'action_request',
                          canonical({'order_id':order,'kind':kind}),'evidence')


def test_retry_restart_scope_and_version(tmp_path):
    path=tmp_path/'care.sqlite'; store=setup(path)
    result=turn(store); store.close(); store=MemoryStore.open(path)
    request=store.find_request('s','customer','m')
    assert store.response(request)==result
    assert turn(store)==result
    assert store.load_session('s').turn_count==1
    with pytest.raises(CareError,match='request_conflict'):
        store.begin_request('s','customer',CustomerEvent('message','m','changed'),'changed')
    with pytest.raises(CareError):
        store.begin_request('s','other',CustomerEvent('message','new','hello'),'hash')
    event=CustomerEvent('message','new','hello')
    request=store.begin_request('s','customer',event,fingerprint(event))
    with pytest.raises(CareError,match='state_conflict'):
        store.commit_turn(request['id'],0,PolicyOutcome(store.load_session('s'),'accept','clarify'),result,'{}','{}')
    store.close()


def test_open_key_identity_is_immutable(tmp_path):
    store=setup(tmp_path/'care.sqlite')
    original=store.load_session('s')
    assert store.create_session(replace(original,session_id='other'),'open')==original
    with pytest.raises(CareError,match='request_conflict'):
        store.create_session(replace(original,session_id='other',order_id='o2'),'open')
    store.close()


def test_two_connections_commit_one_request(tmp_path):
    path=tmp_path/'care.sqlite'; setup(path).close()
    def execute(_):
        store=MemoryStore.open(path)
        try: return turn(store)
        finally: store.close()
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(execute,range(2)))
    assert results[0]==results[1]
    store=MemoryStore.open(path)
    assert store.load_session('s').turn_count==1
    assert len(store.events('s'))==2
    store.close()


def test_effect_claim_receipt_restart_and_coin_uniqueness(tmp_path):
    path=tmp_path/'care.sqlite'; a=setup(path)
    a.create_session(SessionState('s2','run','customer','o1'),'open2')
    proposal=effect(); turn(a,proposals=(proposal,))
    with pytest.raises(CareError): turn(a,'s2',proposals=(effect('other','s2'),))
    assert a.load_session('s2').version==0
    b=MemoryStore.open(path)
    assert a.claim_effect('coin',1,1,0)==proposal
    assert b.claim_effect('coin',1,1,0) is None
    a.close(); a=MemoryStore.open(path)
    assert a.claim_effect('coin',1,1,100) is None
    # In-flight work requires reconciliation; elapsed time never permits blind resend.
    good=Receipt('coin','coin',fingerprint(proposal.payload),2,'succeeded','remote')
    assert a.record_receipt(good)
    assert not a.record_receipt(replace(good,revision=1,outcome='accepted'))
    assert not a.record_receipt(good)
    with pytest.raises(CareError,match='receipt_terminal_conflict'):
        a.record_receipt(replace(good,revision=3,outcome='rejected'))
    assert a.effect('coin')['outcome']=='succeeded'
    assert len([e for e in a.events('s') if e['kind']=='receipt'])==1
    assert 'private' in a.db.execute('SELECT data FROM evidence_bundles').fetchone()[0]
    a.close(); b.close()


def test_late_outbox_failure_rolls_back_all_turn_writes(tmp_path):
    store=setup(tmp_path/'care.sqlite')
    pending=PendingCancellation('cancel','prompt',NOW)
    turn(store,proposals=(effect(),),pending=pending)
    before=store.load_session('s'); events=store.events('s')
    handoff=EffectProposal('handoff','handoff','s','o1','handoff_request','{}','e')
    with pytest.raises(CareError):
        turn(store,key='second',proposals=(handoff,effect('distinct')),pending=None)
    assert store.load_session('s')==before
    assert store.events('s')==events
    assert store.load_session('s').pending==pending
    assert len(store.effects())==1
    assert store.db.execute('SELECT count(*) FROM evidence_bundles').fetchone()[0]==1
    turn(store,key='second',proposals=(handoff,))
    assert len(store.effects())==2
    store.close()


def test_handoff_unique_and_writer_busy(tmp_path):
    path=tmp_path/'care.sqlite'; a=setup(path); b=MemoryStore.open(path)
    first=EffectProposal('h','h','s','o1','handoff_request','{}','e')
    turn(a,proposals=(first,))
    with pytest.raises(CareError): turn(b,key='new',proposals=(replace(first,key='other',effect_id='other'),))
    a.db.execute('BEGIN IMMEDIATE'); b.db.execute('PRAGMA busy_timeout=1')
    try:
        with pytest.raises(sqlite3.OperationalError,match='locked'): turn(b,key='busy')
    finally: a.db.rollback()
    a.close(); b.close()

@pytest.mark.parametrize('kind',['coins','cancel_request','eta_notice'])
def test_action_order_must_match_session(tmp_path,kind):
    store=setup(tmp_path/'care.sqlite')
    with pytest.raises(CareError,match='invalid_delivery_order'):
        turn(store,proposals=(effect(order='other',kind=kind),))
    assert store.load_session('s').version==0 and not store.effects()
    store.close()


def test_distinct_coin_keys_race_across_sessions(tmp_path):
    path=tmp_path/'care.sqlite'; store=setup(path)
    store.create_session(SessionState('s2','run','customer','o1'),'open2'); store.close()
    def execute(sid):
        store=MemoryStore.open(path)
        try:
            turn(store,sid,proposals=(effect('coin-'+sid,sid),)); return 'persisted'
        except CareError: return 'conflict'
        finally: store.close()
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(execute,('s','s2')))
    assert sorted(results)==['conflict','persisted']
    store=MemoryStore.open(path)
    assert len(store.effects())==1
    assert store.db.execute('SELECT count(*) FROM evidence_bundles').fetchone()[0]==1
    store.close()


@pytest.mark.parametrize('field,value',[('session_id','other'),('run_id','other'),
    ('principal_id','other'),('order_id','o2'),('channel','web_voice'),('opened_by','a1')])
def test_commit_cannot_change_session_identity(tmp_path,field,value):
    store=setup(tmp_path/'care.sqlite')
    state=store.load_session('s'); event=CustomerEvent('message','m','hello')
    request=store.begin_request('s','customer',event,fingerprint(event))
    outcome=PolicyOutcome(replace(state,**{field:value}),'off_topic','clarify')
    with pytest.raises(CareError):
        store.commit_turn(request['id'],0,outcome,TurnResult('committed','s'),'{}','{}')
    assert store.load_session('s')==state
    assert not store.events('s')
    store.close()
