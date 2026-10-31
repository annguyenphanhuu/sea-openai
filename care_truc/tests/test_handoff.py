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
        pending = (await h.session(sid)).pending
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
        assert (await h.session(other)).status == 'active'
        await h.handle_message(other, 'cancel', 'hủy đơn', CUSTOMER)
        assert (await h.session(other)).status == 'handoff_pending'
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
        before = dict(h.store.effect(eid)); version = (await h.session(sid)).version
        with pytest.raises(CareError, match='forbidden'):
            await h.retry_handoff(sid, CUSTOMER)
        assert await h.retry_handoff(sid, RETRY) == 'blocked'
        gate.allowed = True
        assert await h.retry_handoff(sid, RETRY) == 'pending_delivery'
        assert h.store.effect(eid)['proposal'] == before['proposal']
        assert (await h.session(sid)).version == version
        assert len(h.store.effects()) == 1
        with pytest.raises(CareError, match='session_state_conflict'):
            await h.request_handoff(sid, 'new', CUSTOMER)
        gateway.submit_error = TimeoutError()
        await h.drain_pending()
        assert (await h.session(sid)).status == 'handoff_pending'
        with pytest.raises(CareError, match='handoff_retry_not_allowed'):
            await h.retry_handoff(sid, RETRY)
        await h.drain_pending()
        assert (await h.session(sid)).status == 'transferred'
        assert len(gateway.submissions) == 1
        assert await h.request_handoff(sid, 'human', CUSTOMER) == original
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('trigger,reason', [('turn', 'turn_limit'), ('abuse', 'abuse_limit')])
def test_limit_reasons_are_structured(tmp_path, trigger, reason):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        state = (await h.session(sid))
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
        action = await h.confirm_cancel(prompt.confirmation_id, 'confirm', CUSTOMER, reply_to=(await h.session(sid)).pending.reply_to, confirmed=True)
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

@pytest.mark.parametrize('accepted', [False, True])
def test_late_retry_cannot_resurrect_effect_from_other_connection(tmp_path, accepted):
    async def check():
        from care_truc.harness import CareHarness
        from care_truc.store import MemoryStore
        from care_truc.runtime_types import GateDecision

        class LateGate(Gate):
            def __init__(self):
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def check(self, proposal, ctx, *, deadline):
                self.started.set()
                await self.release.wait()
                return GateDecision(True)

        class PausedGateway(ScriptedGateway):
            def __init__(self):
                super().__init__()
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def submit(self, proposal, *, deadline):
                self.started.set()
                await self.release.wait()
                return await super().submit(proposal, deadline=deadline)

        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        result = await h.request_handoff(sid, 'human', CUSTOMER)
        eid = result.effect_ids[0]
        h.store.set_effect(eid, state='blocked')
        late = LateGate()
        h.dispatcher = EffectDispatcher(h, ScriptedGateway(), late)
        waiting = asyncio.create_task(h.retry_handoff(sid, RETRY))
        await late.started.wait()
        other = CareHarness('run', MemoryStore.open(tmp_path / 'care.sqlite'), h.context_provider, h.clock)
        gateway = PausedGateway()
        other.dispatcher = EffectDispatcher(other, gateway, Gate())
        assert await other.retry_handoff(sid, RETRY) == 'pending_delivery'
        dispatch = asyncio.create_task(other.drain_pending())
        await gateway.started.wait()
        if accepted:
            gateway.release.set()
            await dispatch
        before = dict(other.store.effect(eid))
        late.release.set()
        with pytest.raises(CareError, match='handoff_retry_not_allowed'):
            await waiting
        assert dict(other.store.effect(eid)) == before
        assert before['state'] == ('delivered' if accepted else 'in_flight')
        if not accepted:
            gateway.release.set()
            await dispatch
        assert (await other.session(sid)).status == 'transferred'
        assert len(gateway.submissions) == 1
        other.store.close()
        h.store.close()
    asyncio.run(check())
