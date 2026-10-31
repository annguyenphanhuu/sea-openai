import asyncio
from dataclasses import replace
import json
import pytest
from care_truc.dispatcher import EffectDispatcher
from care_truc.runtime_types import CareError, TrustedRequestContext
from .helpers import CUSTOMER, STAFF, Gate, ScriptedGateway
from .test_turn_loop import harness

RETRY = TrustedRequestContext('staff', frozenset({'care_handoff_retry'}))

def test_contextual_summary_and_missing_needed_data(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'cancel', 'hủy đơn', CUSTOMER)
        pending = h.session(sid).pending
        result = await h.request_handoff(sid, 'human', CUSTOMER)
        row = h.store.effect(result.effect_ids[0])
        summary = json.loads(json.loads(row['proposal'])['payload'])['summary']
        summary = json.loads(summary)
        assert summary['reason'] == 'customer_requested_human'
        assert summary['evidence_refs'] == list(result.evidence_refs)
        assert summary['invalidated_confirmation']['confirmation_id'] == pending.confirmation_id
        assert summary['cancellation_state'] == 'invalidated'
        assert summary['customer_statements'][0]['label'] == 'customer_statement'
        assert summary['facts_trust']['current_and_trusted'] is True
        assert summary['facts_trust']['assessed_at']
        assert summary['facts_trust']['cutoff']
        assert 'summary' not in json.dumps(await h.get_messages(sid, CUSTOMER))
        other = (await h.open_chat('o1', 'other', CUSTOMER)).session_id
        h.context_provider.snapshot = replace(h.context_provider.snapshot, assessment=None)
        await h.handle_message(other, 'eta', 'bao giờ giao', CUSTOMER)
        assert h.session(other).status == 'active'
        await h.handle_message(other, 'cancel', 'hủy đơn', CUSTOMER)
        assert h.session(other).status == 'handoff_pending'
        h.store.close()
    asyncio.run(check())

def test_internal_retry_only_unsent_same_envelope_fresh_gate(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        original = await h.request_handoff(sid, 'human', CUSTOMER)
        eid = original.effect_ids[0]
        gate = Gate(); gate.allowed = False
        gateway = ScriptedGateway(); h.dispatcher = EffectDispatcher(h, gateway, gate)
        await h.drain_pending()
        before = dict(h.store.effect(eid)); version = h.session(sid).version
        with pytest.raises(CareError, match='forbidden'):
            await h.retry_handoff(sid, CUSTOMER)
        assert await h.retry_handoff(sid, RETRY) == 'blocked'
        gate.allowed = True
        assert await h.retry_handoff(sid, RETRY) == 'pending_delivery'
        assert h.store.effect(eid)['proposal'] == before['proposal']
        assert h.session(sid).version == version
        assert len(h.store.effects()) == 1
        with pytest.raises(CareError, match='session_state_conflict'):
            await h.request_handoff(sid, 'new', CUSTOMER)
        gateway.submit_error = TimeoutError()
        await h.drain_pending()
        assert h.session(sid).status == 'handoff_pending'
        with pytest.raises(CareError, match='handoff_retry_not_allowed'):
            await h.retry_handoff(sid, RETRY)
        await h.drain_pending()
        assert h.session(sid).status == 'transferred'
        assert len(gateway.submissions) == 1
        assert await h.request_handoff(sid, 'human', CUSTOMER) == original
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('trigger,reason', [('turn', 'turn_limit'), ('abuse', 'abuse_limit')])
def test_limit_reasons_are_structured(tmp_path, trigger, reason):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        state = h.session(sid)
        state = replace(state, turn_count=7 if trigger == 'turn' else 0,
                        abusive_turn_count=2 if trigger == 'abuse' else 0)
        from care_truc.runtime_types import canonical
        h.store.db.execute('UPDATE sessions SET data=? WHERE id=?', (canonical(state), sid))
        result = await h.handle_message(sid, 'limit', 'đồ ngu' if trigger == 'abuse' else 'hello', CUSTOMER)
        summary = json.loads(json.loads(json.loads(h.store.effect(result.effect_ids[0])['proposal'])['payload'])['summary'])
        assert summary['reason'] == reason
        assert len(h.store.effects()) == 1
        h.store.close()
    asyncio.run(check())

def test_summary_contains_known_receipts_and_staff_decision(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        prompt = await h.handle_message(sid, 'cancel', 'hủy đơn', CUSTOMER)
        action = await h.confirm_cancel(prompt.confirmation_id, 'confirm', CUSTOMER)
        gateway = ScriptedGateway()
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        result = await h.request_handoff(sid, 'human', CUSTOMER)
        summary = json.loads(json.loads(json.loads(h.store.effect(result.effect_ids[0])['proposal'])['payload'])['summary'])
        assert summary['action_receipts'][0]['effect_id'] == action.effect_ids[0]
        assert summary['action_receipts'][0]['outcome'] == 'accepted'
        assert summary['next_decision']
        assert summary['assessment_ref']
        assert (await h.get_handoffs(STAFF))['handoffs'][0]['summary']
        h.store.close()
    asyncio.run(check())

def test_handoff_listing_filters_other_runs(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.request_handoff(sid, 'human', CUSTOMER)
        from care_truc.harness import CareHarness
        other = CareHarness('another', h.store, h.context_provider, h.clock)
        assert await other.get_handoffs(STAFF) == {'handoffs': []}
        h.store.close()
    asyncio.run(check())
