import asyncio
from dataclasses import replace
import json
import sqlite3

import pytest

from contracts.types import ContactTask
from care_truc.api import CareApi
from care_truc.lifecycle import CareRuntime
from care_truc.runtime_types import CareError, CustomerEvent, fingerprint
from care_truc.hooks import RuntimeHooks
from .helpers import SYSTEM, CUSTOMER, STAFF, NOW, Gate
from .test_recovery import adapters


def test_explicit_confirmation_replies_to_actual_assistant_message(tmp_path):
    async def check():
        runtime=await CareRuntime.start('run',adapters(),root=tmp_path,background=False)
        api=CareApi(runtime.harness)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        prepared=await api.handle('prepare_cancel',{'session_id':sid,'request_id':'cancel'},CUSTOMER)
        history=await api.handle('get_messages',{'session_id':sid},CUSTOMER)
        prompt=history.body['messages'][-1]['id']
        result=await api.handle('confirm_cancel',{'confirmation_id':prepared.body['confirmation_id'], 'request_id':'confirm',
            'confirmed':True,'reply_to':prompt},CUSTOMER)
        assert result.body['status']=='pending_delivery'
        assert json.loads(runtime.store.effects()[0]['proposal'])['kind']=='action_request'
        await runtime.shutdown()
    asyncio.run(check())


def test_interrupted_contact_opening_recovers_without_customer_turn(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        contact=ContactTask('contact','o1',NOW,NOW,'chat',True,'late','contact-key')
        runtime.store.db.execute("CREATE TRIGGER fail BEFORE INSERT ON evidence_bundles BEGIN SELECT RAISE(ABORT,'disk'); END")
        with pytest.raises((sqlite3.DatabaseError,CareError)):
            await runtime.harness.open_contact(contact,SYSTEM)
        runtime.store.db.execute('DROP TRIGGER fail')
        sid=runtime.store.db.execute('SELECT id FROM sessions').fetchone()[0]
        await runtime.shutdown()
        ports['clock'].advance(1)
        again=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        assert again.store.db.execute('SELECT phase FROM requests').fetchone()[0]=='committed'
        assert again.store.load_session(sid).turn_count==0
        assert len(again.store.effects())==1
        await again.shutdown()
    asyncio.run(check())


def test_blocked_effects_cannot_starve_new_pending_work(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        ports['gate'].allowed=False
        for n in range(20):
            sid=(await runtime.harness.open_chat('o1',f'open{n}',CUSTOMER)).session_id
            await runtime.harness.request_handoff(sid,'h',CUSTOMER)
        await runtime.harness.drain_pending()
        ports['gate'].allowed=True
        sid=(await runtime.harness.open_chat('o1','new',CUSTOMER)).session_id
        result=await runtime.harness.request_handoff(sid,'h',CUSTOMER)
        await runtime.harness.drain_pending()
        assert runtime.store.effect(result.effect_ids[0])['state']=='delivered'
        await runtime.shutdown()
    asyncio.run(check())


def test_shutdown_waits_for_external_drain_before_releasing_store(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        await runtime.harness.request_handoff(sid,'h',CUSTOMER)
        entered=asyncio.Event(); release=asyncio.Event()
        original=ports['gateway'].submit
        async def submit(proposal,*,deadline):
            entered.set(); await release.wait()
            return await original(proposal,deadline=deadline)
        ports['gateway'].submit=submit
        draining=asyncio.create_task(runtime.harness.drain_pending())
        await entered.wait()
        shutdown=asyncio.create_task(runtime.shutdown())
        for _ in range(5): await asyncio.sleep(0)
        assert not shutdown.done()
        release.set(); await draining; await shutdown
    asyncio.run(check())


def test_terminal_handoff_cannot_be_reopened_after_gate_denial(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        await runtime.harness.request_handoff(sid,'h1',CUSTOMER)
        ports['gate'].allowed=False; await runtime.harness.drain_pending()
        ports['gate'].allowed=True
        result=await CareApi(runtime.harness).handle('request_handoff',{'session_id':sid,'request_id':'h2'},CUSTOMER)
        assert result.status==409
        await runtime.harness.drain_pending()
        assert len(runtime.store.effects())==1
        assert runtime.store.load_session(sid).status=='handoff_pending'
        assert runtime.store.load_session(sid).turn_count==1
        await runtime.shutdown()
    asyncio.run(check())


def test_other_session_contact_receipt_does_not_open_d4(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        contact=ContactTask('a','o1',NOW,NOW,'chat',True,'late','key-a')
        first=await runtime.harness.open_contact(contact,SYSTEM)
        ports['gateway'].outcome='succeeded'; await runtime.harness.drain_pending()
        ports['context_provider'].snapshot=replace(ports['context_provider'].snapshot,contact_sent=True)
        second=await runtime.harness.open_contact(replace(contact,contact_id='b',idempotency_key='key-b'),SYSTEM)
        result=await runtime.harness.handle_message(second.session_id,'coins','cho tôi xu',CUSTOMER)
        assert not result.effect_ids
        assert not any(json.loads(row['proposal'])['kind']=='action_request' for row in runtime.store.effects())
        await runtime.shutdown()
    asyncio.run(check())


def test_why_uses_validated_reason_and_handoff_retains_need_and_actions(tmp_path):
    async def check():
        ports=adapters()
        ctx=ports['context_provider'].snapshot
        evidence={'feed':'ops','source_table':'scans','record_id':'1','ingested_at':NOW,
            'fact_code':'stationary_ticks','value':2,'is_structured':True}
        ports['context_provider'].snapshot=replace(ctx,assessment=replace(ctx.assessment,
            status='watch',reason_codes=('status:watch',),evidence=(evidence,)))
        runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        why=await runtime.harness.handle_message(sid,'why','tại sao đơn đứng yên',CUSTOMER)
        assert 'hai kỳ cập nhật' in why.text
        await runtime.harness.handle_message(sid,'cancel','muốn hủy',CUSTOMER)
        cid=runtime.store.load_session(sid).pending.confirmation_id
        await runtime.harness.confirm_cancel(cid,'confirm',CUSTOMER, reply_to=(await runtime.harness.session(sid)).pending.reply_to, confirmed=True)
        await runtime.harness.request_handoff(sid,'h',CUSTOMER)
        summary=json.loads((await runtime.harness.get_handoffs(STAFF))['handoffs'][0]['summary'])
        assert any('muốn hủy' in item['text'] for item in summary['customer_statements'])
        assert summary['actions'][0]['kind']=='action_request'
        assert summary['actions'][0]['outcome']=='unknown'
        assert summary['next_decision']
        await runtime.shutdown()
    asyncio.run(check())


def test_observer_failure_is_visible_without_changing_delivery(tmp_path):
    async def check():
        ports=adapters()
        async def failed(data): raise ValueError('secret observer message')
        hooks=RuntimeHooks({'after_action':(failed,)},ports['clock'])
        runtime=await CareRuntime.start('run',ports,hooks,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        result=await runtime.harness.request_handoff(sid,'h',CUSTOMER)
        await runtime.harness.drain_pending()
        assert runtime.store.effect(result.effect_ids[0])['state']=='delivered'
        assert 'hook_failed' in runtime.get_health().codes
        trace=await runtime.harness.get_trace(sid,STAFF)
        assert any(event['phase']=='after_action' and 'hook_failed' in event['codes']
                   for event in trace['runtime_events'])
        assert 'secret observer' not in str(trace)
        await runtime.harness.drain_pending()
        assert len(ports['gateway'].submissions)==1
        await runtime.shutdown()
    asyncio.run(check())


def test_contact_proposal_contains_validated_opening_text(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        contact=ContactTask('c','o1',NOW,NOW,'chat',True,'late','key')
        result=await runtime.harness.open_contact(contact,SYSTEM)
        proposal=json.loads(runtime.store.effect(result.effect_ids[0])['proposal'])
        payload=json.loads(proposal['payload'])
        assert 'xin lỗi' in result.text
        assert '28/10/2026' in result.text
        assert payload['text']==result.text
        assert payload['contact']['contact_id']=='c'
        history=await runtime.harness.get_messages(result.session_id,CUSTOMER)
        assert all('idempotency_key' not in message['text'] for message in history['messages'])
        await runtime.shutdown()
    asyncio.run(check())
