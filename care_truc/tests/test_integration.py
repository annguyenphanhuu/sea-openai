import asyncio
from dataclasses import replace
import pytest
from contracts.types import ContactTask
from care_truc.runtime_types import CareError, TrustedRequestContext
from .helpers import CUSTOMER, NOW
from .test_turn_loop import harness

SYSTEM = TrustedRequestContext('customer', frozenset({'care_contact'}))

def contact(**changes):
    return replace(ContactTask('c','o1',NOW,NOW,'chat',True,'late','key'), **changes)

def test_contact_requires_explicit_server_permission(tmp_path):
    async def check():
        h=harness(tmp_path)
        with pytest.raises(CareError, match='system_context_required'):
            await h.open_contact(contact(), CUSTOMER)
        assert not h.store.db.execute('SELECT id FROM sessions').fetchall()
        h.store.close()
    asyncio.run(check())

def test_contact_retry_binds_full_payload_and_replays_without_context(tmp_path):
    async def check():
        h=harness(tmp_path)
        first=await h.open_contact(contact(), SYSTEM)
        assert first.status=='pending_delivery'
        assert h.store.load_session(first.session_id).turn_count==0
        async def offline(*args): raise OSError('offline')
        h.context_provider.load=offline
        assert await h.open_contact(contact(), SYSTEM)==first
        for task in (contact(reason_code='changed'), contact(contact_id='other'), contact(channel='web_voice')):
            with pytest.raises(CareError, match='request_conflict'):
                await h.open_contact(task, SYSTEM)
        assert len(h.store.effects())==1
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('text,count',[('Tôi muốn gặp nhân viên và hủy đơn',1),('ngu',3),('Tại sao?',8)])
def test_terminal_replays_without_counting_or_new_effects(tmp_path,text,count):
    async def check():
        h=harness(tmp_path)
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        for n in range(count):
            result=await h.handle_message(sid,str(n),text,CUSTOMER)
        before=h.store.load_session(sid)
        assert before.status=='handoff_pending' and before.turn_count==count
        assert await h.handle_message(sid,str(n),text,CUSTOMER)==result
        with pytest.raises(CareError,match='session_state_conflict'):
            await h.handle_message(sid,'new','cho tôi xu',CUSTOMER)
        assert h.store.load_session(sid)==before
        assert len(h.store.effects())==1
        h.store.close()
    asyncio.run(check())

def test_customer_open_id_conflicts_on_different_order(tmp_path):
    async def check():
        h=harness(tmp_path)
        first=await h.open_chat('o1','open',CUSTOMER)
        assert await h.open_chat('o1','open',CUSTOMER)==first
        with pytest.raises(CareError,match='request_conflict'):
            await h.open_chat('o2','open',CUSTOMER)
        h.store.close()
    asyncio.run(check())


def test_input_veto_cannot_erase_abuse_or_human_handoff(tmp_path):
    from care_truc.hooks import RuntimeHooks
    from care_truc.runtime_types import HookDecision
    async def check():
        h=harness(tmp_path)
        async def veto(data): return HookDecision('veto')
        h.hooks=RuntimeHooks({'on_input':(veto,)},h.clock)
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        for n in range(3): await h.handle_message(sid,str(n),'ngu',CUSTOMER)
        assert h.store.load_session(sid).abusive_turn_count==3
        assert h.store.load_session(sid).status=='handoff_pending'
        other=(await h.open_chat('o1','other',CUSTOMER)).session_id
        await h.handle_message(other,'human','Tôi muốn gặp nhân viên',CUSTOMER)
        assert h.store.load_session(other).status=='handoff_pending'
        h.store.close()
    asyncio.run(check())


def test_response_contains_safe_evidence_and_assessment_references(tmp_path):
    async def check():
        h=harness(tmp_path); ctx=h.context_provider.snapshot
        fact={'feed':'ops','source_table':'scans','record_id':'private-id','ingested_at':NOW,
              'fact_code':'logistics_stage','value':'damaged','is_structured':True}
        h.context_provider.snapshot=replace(ctx,assessment=replace(ctx.assessment,evidence=(fact,)))
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        result=await h.handle_message(sid,'m','tại sao',CUSTOMER)
        assert result.assessment_ref and result.evidence_refs and result.public_evidence
        assert 'private-id' not in str(result)
        staff=TrustedRequestContext('staff',frozenset({'care_evidence'}))
        assert 'private-id' in await h.resolve(result.evidence_refs[0],staff)
        assert await h.handle_message(sid,'m','tại sao',CUSTOMER)==result
        h.store.close()
    asyncio.run(check())
