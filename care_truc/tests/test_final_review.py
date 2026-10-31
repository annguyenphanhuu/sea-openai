"""Final review regressions using algorithm fixtures and isolated SQLite."""
import asyncio
from dataclasses import replace
from datetime import timedelta
import json

import pytest

from care_truc.dispatcher import EffectDispatcher
from care_truc.policy import CarePolicy
from care_truc.rules import classify
from care_truc.runtime_types import CareError, CustomerEvent, SessionState, canonical
from .helpers import CUSTOMER, STAFF, NOW, Gate, ScriptedGateway, context
from .test_handoff import RETRY
from .test_turn_loop import harness


@pytest.mark.parametrize('prefix', ['Trước đây', 'Truoc day', 'Nếu', 'Neu', 'Giả sử', 'Gia su'])
@pytest.mark.parametrize('join', [' và ', ', '])
def test_scoped_coordinated_wishes_never_propose_coins(prefix, join):
    text = prefix + ' tôi muốn hỗ trợ thêm' + join + 'muốn nhận xu'
    assert not classify(text).explicit_coins
    outcome = CarePolicy().evaluate(SessionState('s', 'r', 'customer', 'o1', opened_by='a1'),
        CustomerEvent('message', 'm', text), context(contact_sent=True))
    assert not outcome.proposals
    assert 'coins_eligible' not in outcome.codes


@pytest.mark.parametrize('text', [
    'Trước đây tôi muốn hỗ trợ thêm và muốn nhận xu',
    'Truoc day toi muon ho tro them va muon nhan xu',
    'Nếu tôi muốn hỗ trợ thêm và muốn nhận xu thì sao?',
    'Neu toi muon ho tro them va muon nhan xu thi sao?',
])
def test_report_probes_and_clear_current_request(text):
    state = SessionState('s', 'r', 'customer', 'o1', opened_by='a1')
    for current, expected in [(text, False), (text + '; bây giờ tôi muốn nhận xu', True)]:
        outcome = CarePolicy().evaluate(state, CustomerEvent('message', 'm', current),
                                       context(contact_sent=True))
        assert classify(current).explicit_coins is expected
        assert bool(outcome.proposals) is expected
        assert ('coins_eligible' in outcome.codes) is expected


def invalid_context(snapshot, defect):
    if defect == 'cutoff':
        return replace(snapshot, cutoff=NOW.replace(tzinfo=None))
    if defect == 'regressed':
        return replace(snapshot, cutoff=NOW - timedelta(seconds=1))
    if defect == 'evidence':
        evidence = dict(feed='ops', source_table='private', record_id='REJECTED-SECRET',
            ingested_at=NOW + timedelta(seconds=1), fact_code='note', value='REJECTED-SECRET',
            is_structured=False)
        return replace(snapshot, assessment=replace(snapshot.assessment, evidence=(evidence,)))
    return replace(snapshot, assessment=replace(snapshot.assessment,
        assessed_at=NOW.replace(tzinfo=None) if defect == 'naive' else NOW + timedelta(seconds=1),
        reason_codes=('REJECTED-SECRET',)))


@pytest.mark.parametrize('defect,code,known_time', [
    (defect, code, known_time)
    for defect, code in [('future', 'assessment_invalid'), ('naive', 'assessment_invalid'),
        ('cutoff', 'context_cutoff_invalid'), ('regressed', 'context_cutoff_regressed'), ('evidence', 'evidence_future')]
    for known_time in (False, True) if known_time or defect != 'regressed'
])
@pytest.mark.parametrize('trigger,reason', [('text', 'customer_requested_human'),
    ('endpoint', 'customer_requested_human'), ('turn', 'turn_limit'), ('abuse', 'abuse_limit')])
def test_handoff_survives_rejected_business_context(tmp_path, defect, code, trigger, reason, known_time):
    async def check():
        h = harness(tmp_path)
        try:
            sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
            state = replace(h.session(sid), last_cutoff=NOW if known_time else None,
                turn_count=7 if trigger == 'turn' else 0,
                abusive_turn_count=2 if trigger == 'abuse' else 0)
            h.store.db.execute('UPDATE sessions SET data=? WHERE id=?', (canonical(state), sid))
            h.context_provider.snapshot = invalid_context(h.context_provider.snapshot, defect)
            if trigger == 'endpoint':
                result = await h.request_handoff(sid, 'human', CUSTOMER)
            else:
                text = 'đồ ngu' if trigger == 'abuse' else 'cho tôi xu' if trigger == 'turn' else 'tôi muốn gặp nhân viên'
                result = await h.handle_message(sid, 'human', text, CUSTOMER)
            assert reason in result.codes and code in result.codes
            assert h.session(sid).status == 'handoff_pending'
            assert h.session(sid).last_cutoff == state.last_cutoff
            proposal = json.loads(h.store.effect(result.effect_ids[0])['proposal'])
            assert proposal['kind'] == 'handoff_request'
            summary = json.loads(json.loads(proposal['payload'])['summary'])
            assert summary['facts'] == {} and summary['assessment_ref'] is None
            assert not summary['facts_trust']['current_and_trusted']
            trace = await h.get_trace(sid, STAFF)
            assert code in trace['decisions'][0]['codes']
            bundle = h.store.db.execute('SELECT data FROM evidence_bundles').fetchone()[0]
            snapshot = json.loads(bundle)['snapshot']
            assert snapshot['assessment'] is None and snapshot['guard'] is None
            assert snapshot['items_value_vnd'] is None
            assert 'REJECTED-SECRET' not in bundle + canonical(summary) + canonical(result)
        finally:
            h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('binding', ['principal', 'order', 'assessment'])
def test_invalid_cutoff_does_not_mask_identity_failure(tmp_path, binding):
    async def check():
        h = harness(tmp_path)
        try:
            sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
            rejected = invalid_context(h.context_provider.snapshot, 'cutoff')
            if binding == 'principal':
                rejected = replace(rejected, principal_id='other')
            elif binding == 'order':
                rejected = replace(rejected, order_id='other')
            else:
                rejected = replace(rejected, assessment=replace(rejected.assessment, order_id='other'))
            async def load(ctx, order_id):
                return rejected
            h.context_provider.load = load
            with pytest.raises(CareError, match='context_binding_invalid'):
                await h.request_handoff(sid, 'human', CUSTOMER)
            assert not h.store.effects()
        finally:
            h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('defect', ['future', 'naive', 'cutoff', 'evidence'])
def test_existing_handoff_dispatch_and_retry_with_invalid_context(tmp_path, defect):
    async def check():
        h = harness(tmp_path)
        try:
            sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
            result = await h.request_handoff(sid, 'human', CUSTOMER)
            h.context_provider.snapshot = invalid_context(h.context_provider.snapshot, defect)
            gate = Gate(); gate.allowed = False
            gateway = ScriptedGateway()
            h.dispatcher = EffectDispatcher(h, gateway, gate)
            await h.drain_pending()
            eid = result.effect_ids[0]
            before = h.store.effect(eid)['proposal']
            assert h.store.effect(eid)['state'] == 'blocked'
            assert await h.retry_handoff(sid, RETRY) == 'blocked'
            gate.allowed = True
            assert await h.retry_handoff(sid, RETRY) == 'pending_delivery'
            await h.drain_pending()
            assert h.store.effect(eid)['proposal'] == before
            assert len(gateway.submissions) == 1
            assert h.session(sid).status == 'transferred'
            assert (await h.get_trace(sid, STAFF))['runtime_events']
        finally:
            h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('operation', ['text', 'endpoint', 'dispatch', 'retry'])
def test_handoff_does_not_swallow_authorization_failure(tmp_path, operation):
    async def check():
        h = harness(tmp_path)
        try:
            sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
            gateway = ScriptedGateway()
            h.dispatcher = EffectDispatcher(h, gateway, Gate())
            if operation in ('dispatch', 'retry'):
                result = await h.request_handoff(sid, 'human', CUSTOMER)
                if operation == 'retry':
                    h.store.set_effect(result.effect_ids[0], state='blocked')
            h.context_provider.snapshot = invalid_context(h.context_provider.snapshot, 'cutoff')
            async def deny(ctx, order_id):
                raise CareError('forbidden', 403)
            h.context_provider.authorize = deny
            with pytest.raises(CareError, match='forbidden'):
                if operation == 'text':
                    await h.handle_message(sid, 'human', 'gặp nhân viên', CUSTOMER)
                elif operation == 'endpoint':
                    await h.request_handoff(sid, 'human', CUSTOMER)
                elif operation == 'dispatch':
                    await h.drain_pending()
                else:
                    await h.retry_handoff(sid, RETRY)
            assert not gateway.submissions
        finally:
            h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('text', ['tại sao', 'cho tôi xu'])
def test_ordinary_requests_still_reject_invalid_business_facts(tmp_path, text):
    async def check():
        h = harness(tmp_path)
        try:
            sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
            h.context_provider.snapshot = invalid_context(h.context_provider.snapshot, 'future')
            with pytest.raises(CareError, match='assessment_invalid'):
                await h.handle_message(sid, 'message', text, CUSTOMER)
            assert not h.store.effects()
        finally:
            h.store.close()
    asyncio.run(check())
