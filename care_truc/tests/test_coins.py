from dataclasses import replace
import pytest
from care_truc.coins import evaluate_coins
from care_truc.runtime_types import CustomerEvent, SessionState
from .helpers import context


def test_pending_and_unknown_ledger_fail_closed():
    state = SessionState('s', 'r', 'customer', 'o1', opened_by='a1')
    event = CustomerEvent('message', 'm', 'cho tôi xu')
    for pending in (None, True):
        result = evaluate_coins(state, event, context(contact_sent=True, ledger_pending=pending))
        assert not result.allowed
        assert 'coins_grant_pending' in result.codes or 'coins_grant_unknown' in result.codes

from datetime import timedelta
from care_truc.coins import build_coin_action
from care_truc.policy import CarePolicy
from .helpers import NOW


def eligible(**changes):
    return context(contact_sent=True, **changes)


def state(**changes):
    return replace(SessionState('s', 'r', 'customer', 'o1', opened_by='a1'), **changes)


def event(text='cho tôi xu'):
    return CustomerEvent('message', 'm', text)


@pytest.mark.parametrize('value,amount', [(None,10000),(0,10000),(300000,15000),(1,10000),(100000000,1000000)])
def test_contract_amounts(value, amount):
    result = evaluate_coins(state(), event(), eligible(items_value_vnd=value))
    assert result.allowed and result.amount_vnd == amount
    action = build_coin_action(state(), result, NOW, 'durable')
    assert (action.amount_vnd, action.evidence_ref, action.idempotency_key) == (amount,'durable','r:coins:o1')
    assert (action.source, action.queue, action.needs_approval) == ('a1','care',False)


@pytest.mark.parametrize('value', [True,False,'300000',1.0,-1])
def test_contract_rejects_invalid_amount(value):
    assert 'invalid_items_value' in evaluate_coins(state(),event(),eligible(items_value_vnd=value)).codes


@pytest.mark.parametrize('field,value,code', [
    ('ledger_pending',True,'coins_grant_pending'),('ledger_pending',None,'coins_grant_unknown'),
    ('ledger_granted',True,'coins_already_granted'),('ledger_granted',None,'coins_grant_unknown'),
    ('evidence_resolvable',False,'coins_evidence_unavailable'),('contact_sent',False,'coins_contact_unsent'),
])
def test_snapshot_conditions(field,value,code):
    ctx = replace(eligible(), **{field:value})
    result = evaluate_coins(state(),event(),ctx)
    assert not result.allowed and code in result.codes
    assert not CarePolicy().evaluate(state(),event(),ctx).proposals


@pytest.mark.parametrize('changes,code', [({'opened_by':'customer'},'coins_origin_ineligible'),({'channel':'web_voice'},'coins_text_only')])
def test_session_conditions(changes,code):
    assert code in evaluate_coins(state(**changes),event(),eligible()).codes


@pytest.mark.parametrize('changes,code', [
    ({'late_days':1},'coins_lateness_insufficient'),({'late_days':True},'coins_lateness_insufficient'),
    ({'fault_party':'customer'},'coins_fault_ineligible'),({'fault_party':'force_majeure'},'coins_fault_ineligible'),
    ({'fault_party':'unknown'},'coins_fault_ineligible'),({'status':'unknown_feed'},'coins_status_unknown'),
    ({'assessed_at':NOW-timedelta(minutes=30,seconds=1)},'assessment_stale'),
    ({'assessed_at':NOW+timedelta(seconds=1)},'assessment_stale'),
    ({'reason_codes':('untrusted_fact:value',)},'facts_unverified')])
def test_assessment_conditions(changes,code):
    ctx=eligible()
    result=evaluate_coins(state(),event(),replace(ctx,assessment=replace(ctx.assessment,**changes)))
    assert not result.allowed and code in result.codes


@pytest.mark.parametrize('text', ['hỗ trợ thêm','xu là gì','hôm qua tôi đã yêu cầu xu','tài xế bảo tôi xin xu','tôi không muốn xu'])
def test_current_explicit_request_required(text):
    assert not evaluate_coins(state(),event(text),eligible()).allowed


def test_guard_and_assessment_boundaries():
    ctx=eligible()
    assert evaluate_coins(state(),event(),replace(ctx,assessment=replace(ctx.assessment,assessed_at=NOW-timedelta(minutes=30)))).allowed
    for guard in (None, replace(ctx.guard,actions_allowed=False), replace(ctx.guard,heartbeat=NOW-timedelta(minutes=61)),replace(ctx.guard,feeds=())):
        assert not evaluate_coins(state(),event(),replace(ctx,guard=guard)).allowed

import asyncio
import json
from care_truc.lifecycle import CareRuntime
from care_truc.runtime_types import TrustedRequestContext
from .helpers import CUSTOMER, SYSTEM
from .test_harness_acceptance import adapters
from .test_integration import contact


def test_local_reservation_refuses_new_message_and_durable_evidence(tmp_path):
    async def check():
        ports=adapters()
        runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        h=runtime.harness
        first=await h.open_contact(contact(),SYSTEM)
        ports['gateway'].outcome='succeeded'
        await h.drain_pending()
        ports['context_provider'].snapshot=replace(ports['context_provider'].snapshot,contact_sent=True)
        result=await h.handle_message(first.session_id,'coins','cho tôi xu',CUSTOMER)
        assert len(result.effect_ids)==1
        refused=await h.handle_message(first.session_id,'coins-again','cho tôi xu',CUSTOMER)
        assert not refused.effect_ids and 'coins_grant_pending' in refused.codes
        other=await h.open_contact(contact(contact_id='other',idempotency_key='other-contact'),SYSTEM)
        await h.drain_pending()
        refused=await h.handle_message(other.session_id,'new-session','cho tôi xu',CUSTOMER)
        assert not refused.effect_ids and 'coins_grant_pending' in refused.codes
        effects=[row for row in h.store.effects() if json.loads(row['proposal'])['kind']=='action_request']
        assert len(effects)==1
        proposal=json.loads(effects[0]['proposal'])
        evidence=json.loads(await h.resolve(proposal['evidence_ref'],TrustedRequestContext('staff',frozenset({'care_evidence'}))))
        assert evidence['event']['text']=='cho tôi xu'
        assert evidence['session']['contact_id']=='c'
        assert evidence['snapshot']['assessment']['order_id']=='o1'
        assert evidence['snapshot']['contact_sent'] is True
        await runtime.shutdown()
    asyncio.run(check())


def test_run_scoped_key_uses_contract_quote(monkeypatch):
    import care_truc.coins as coins
    monkeypatch.setattr(coins, 'late_xu_for', lambda value: 12345)
    decision=coins.evaluate_coins(state(),event(),eligible())
    assert decision.amount_vnd==12345
    assert coins.build_coin_action(state(run_id='other'),decision,NOW).idempotency_key=='other:coins:o1'
