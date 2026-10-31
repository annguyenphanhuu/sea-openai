import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import pytest

from contracts.types import ContactTask
from care_truc.api import CareApi
from care_truc.lifecycle import CareRuntime
from care_truc.runtime_types import Receipt, TrustedRequestContext, fingerprint, CareError
from .helpers import SYSTEM, CUSTOMER, STAFF, NOW
from .test_recovery import adapters


def test_full_contact_coins_receipt_and_restart(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        contact=ContactTask('contact','o1',NOW,NOW,'chat',True,'late','contact-key')
        opening=await runtime.harness.open_contact(contact,SYSTEM)
        sid=opening.session_id; api=CareApi(runtime.harness)
        await runtime.harness.drain_pending()
        refused=await api.handle('handle_message',{'session_id':sid,'message_id':'early','text':'cho tôi xu'},CUSTOMER)
        assert refused.body['effect_ids']==[]
        receipt=ports['gateway'].receipts['contact-key']
        ports['gateway'].receipts['contact-key']=replace(receipt,revision=2,outcome='succeeded')
        ports['context_provider'].snapshot=replace(ports['context_provider'].snapshot,contact_sent=True)
        ports['clock'].advance(1); await runtime.harness.drain_pending()
        assert (await api.handle('handle_message',{'session_id':sid,'message_id':'why','text':'tại sao'},CUSTOMER)).status==200
        payload={'session_id':sid,'message_id':'coins','text':'cho tôi xu'}
        result=await api.handle('handle_message',payload,CUSTOMER)
        assert result.body['status']=='pending_delivery'
        assert 'đã cấp' not in result.body['text']
        ports['gateway'].outcome='succeeded'; await runtime.harness.drain_pending()
        assert await api.handle('handle_message',payload,CUSTOMER)==result
        history=await api.handle('get_messages',{'session_id':sid},CUSTOMER)
        assert any(e['outcome']=='succeeded' for e in history.body['effects'])
        await runtime.shutdown()
        runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        assert await CareApi(runtime.harness).handle('handle_message',payload,CUSTOMER)==result
        assert len([p for p in ports['gateway'].submissions if p.kind=='action_request'])==1
        await runtime.shutdown()
    asyncio.run(check())


def test_repeated_human_request_keeps_one_pending_handoff(tmp_path):
    async def check():
        runtime=await CareRuntime.start('run',adapters(),root=tmp_path,background=False)
        api=CareApi(runtime.harness)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        for request_id in ('h1','h1'):
            result=await api.handle('request_handoff',{'session_id':sid,'request_id':request_id},CUSTOMER)
            assert result.status==200
        assert len(runtime.store.effects())==1
        assert runtime.store.effects()[0]['state']=='pending_delivery'
        await runtime.harness.drain_pending()
        staff=await api.handle('get_handoffs',{},STAFF)
        assert staff.body['handoffs'][0]['status']=='transferred'
        await runtime.shutdown()
    asyncio.run(check())


def test_context_outage_does_not_create_cancel_action(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        async def unavailable(ctx,order): raise OSError('context down')
        ports['context_provider'].load=unavailable
        result=await CareApi(runtime.harness).handle('prepare_cancel',{'session_id':sid,'request_id':'c'},CUSTOMER)
        assert result.status==200
        assert result.body['confirmation_id'] is None
        assert not any(json.loads(r['proposal'])['kind']=='action_request' for r in runtime.store.effects())
        await runtime.shutdown()
    asyncio.run(check())


def test_cancel_then_handoff_invalidates_unsent_action(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        api=CareApi(runtime.harness); sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        pending=await api.handle('prepare_cancel',{'session_id':sid,'request_id':'c'},CUSTOMER)
        await api.handle('confirm_cancel',{'confirmation_id':pending.body['confirmation_id'],'request_id':'yes','reply_to':pending.body['message_id'],'confirmed':True},CUSTOMER)
        await api.handle('request_handoff',{'session_id':sid,'request_id':'h'},CUSTOMER)
        await runtime.harness.drain_pending()
        assert [p.kind for p in ports['gateway'].submissions]==['handoff_request']
        await runtime.shutdown()
    asyncio.run(check())


def test_executor_can_resolve_durable_evidence_under_server_permission(tmp_path):
    async def check():
        runtime=await CareRuntime.start('run',adapters(),root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        result=await runtime.harness.request_handoff(sid,'h',CUSTOMER)
        proposal=json.loads(runtime.store.effect(result.effect_ids[0])['proposal'])
        with pytest.raises(CareError):
            await runtime.harness.resolve(proposal['evidence_ref'],CUSTOMER)
        bundle=json.loads(await runtime.harness.resolve(proposal['evidence_ref'],
            TrustedRequestContext('staff',frozenset({'care_evidence'}))))
        assert bundle['event']['kind']=='request_handoff'
        assert bundle['session']['opened_by']=='customer'
        assert bundle['snapshot']['order_id']=='o1'
        trace=await runtime.harness.get_trace(sid,STAFF)
        assert trace['decisions'][0]['elapsed_runtime_s']>=0
        await runtime.shutdown()
    asyncio.run(check())
