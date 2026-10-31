from dataclasses import replace
from datetime import timedelta
import json
import pytest

from care_truc.policy import CarePolicy
from care_truc.runtime_types import CustomerEvent, SessionState
from .helpers import context, NOW


def state(**changes):
    return replace(SessionState("s", "run", "customer", "o1", opened_by="a1"), **changes)


@pytest.mark.parametrize('text,intent', [
    ('đồ ngu','unreasonable_abusive'), ('gap nhan vien','ask_human'),
    ('tôi muốn hủy','want_cancel'), ('cho tôi xu','want_more'),
    ('tại sao','ask_why'), ('đồng ý','accept'), ('xin chào','off_topic'),
    ('tôi không muốn hủy','off_topic'), ('tài xế bảo tôi hủy','off_topic'),
    ('đồ ngu tôi muốn gặp người','ask_human')])
def test_rules_intents(text, intent):
    out = CarePolicy().evaluate(state(), CustomerEvent('message','m',text), context())
    assert out.intent == intent
    if 'ngu' in text:
        assert out.state.abusive_turn_count == 1


@pytest.mark.parametrize('changes', [{'turn_count':7}, {'abusive_turn_count':2}])
def test_stop_precedes_money(changes):
    out = CarePolicy().evaluate(state(**changes), CustomerEvent('message','m','đồ ngu cho tôi xu'), context(contact_sent=True))
    assert out.state.status == 'handoff_pending'
    assert [p.kind for p in out.proposals] == ['handoff_request']
    assert out.invalidate_unsent


def test_only_explicit_current_text_grants_coins():
    policy = CarePolicy()
    for source in ('customer', 'a1'):
        for sent in (False, True):
            out = policy.evaluate(state(opened_by=source), CustomerEvent('message','m','cho tôi xu'), context(contact_sent=sent))
            assert bool(out.proposals) == (source == 'a1' and sent)
    out = policy.evaluate(state(), CustomerEvent('message','m','hỗ trợ thêm'), context(contact_sent=True))
    assert not out.proposals
    for channel in ('chat', 'web_voice'):
        out = policy.evaluate(state(channel=channel), CustomerEvent('message','m','cho tôi xu'), context(contact_sent=True))
        assert bool(out.proposals) == (channel == 'chat')
        if out.proposals:
            action = json.loads(out.proposals[0].payload)
            assert (action['amount_vnd'], action['source'], action['queue'], action['needs_approval']) == (50000,'a1','care',False)


@pytest.mark.parametrize('fault', ['customer','force_majeure','unknown'])
def test_fault_blocks_coins(fault):
    ctx = context(contact_sent=True)
    out = CarePolicy().evaluate(state(), CustomerEvent('message','m','cho tôi xu'), replace(ctx, assessment=replace(ctx.assessment, fault_party=fault)))
    assert not out.proposals


def test_cancel_confirmation_and_expiry():
    policy = CarePolicy()
    first = policy.evaluate(state(), CustomerEvent('message','m','muốn hủy'), context())
    pending = first.state.pending
    assert pending is not None
    first = replace(first, state=replace(first.state, version=pending.version))
    event = CustomerEvent('confirm_cancel','confirm',confirmation_id=pending.confirmation_id, reply_to=pending.reply_to, confirmed=True)
    out = policy.evaluate(first.state, event, context())
    payload = json.loads(out.proposals[0].payload)
    assert (payload['amount_vnd'], payload['queue'], payload['needs_approval']) == (0,'cancel_review',True)
    expired = policy.evaluate(first.state, event, context(cutoff=NOW + timedelta(minutes=10)))
    assert not expired.proposals
    assert 'cancel_confirmation_expired' in expired.codes
    wrong = policy.evaluate(first.state, replace(event, confirmation_id='wrong'), context())
    assert not wrong.proposals
    mind = policy.evaluate(first.state, CustomerEvent('message','new','tôi không muốn hủy'), context())
    assert mind.state.pending is None and mind.invalidate_unsent
