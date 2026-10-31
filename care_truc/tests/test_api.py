import asyncio
import pytest

from care_truc.api import CareApi
from care_truc.runtime_types import TrustedRequestContext
from .helpers import CUSTOMER, STAFF
from .test_turn_loop import harness


@pytest.mark.parametrize('key', ['source','proactive','role','guard_allowed','cutoff','amount','customer_id','allowed','channel'])
def test_forged_payload_authority_is_rejected(tmp_path,key):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        result=await api.handle('open_chat',{'order_id':'o1','request_id':'r',key:'forged'},CUSTOMER)
        assert result.status==400
        assert h.store.db.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
        h.store.close()
    asyncio.run(check())


def test_customer_history_and_staff_trace_use_distinct_projections(tmp_path):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        opened=await api.handle('open_chat',{'order_id':'o1','request_id':'r'},CUSTOMER)
        sid=opened.body['session_id']
        result=await api.handle('handle_message',{'session_id':sid,'message_id':'m','text':'tại sao'},CUSTOMER)
        assert result.status==200
        history=await api.handle('get_messages',{'session_id':sid},CUSTOMER)
        assert len(history.body['messages'])==2
        assert 'trace' not in str(history.body) and 'snapshot' not in str(history.body)
        assert (await api.handle('get_trace',{'session_id':sid},CUSTOMER)).status==403
        trace=await api.handle('get_trace',{'session_id':sid},STAFF)
        assert trace.status==200 and trace.body['decisions'][0]['phases']==list(range(1,11))
        stranger=TrustedRequestContext('stranger')
        assert (await api.handle('get_messages',{'session_id':sid},stranger)).status==404
        assert (await api.handle('handle_message',{'session_id':sid,'message_id':'m','text':'tại sao'},stranger)).status==404
        h.store.close()
    asyncio.run(check())


def test_confirm_and_handoff_share_request_namespace(tmp_path):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        sid=(await h.open_chat('o1','r',CUSTOMER)).session_id
        result=await api.handle('prepare_cancel',{'session_id':sid,'request_id':'cancel'},CUSTOMER)
        cid=result.body['confirmation_id']
        one=await api.handle('confirm_cancel',{'confirmation_id':cid,'request_id':'yes','reply_to':result.body['message_id'],'confirmed':True},CUSTOMER)
        assert one.body['status']=='pending_delivery'
        assert one==await api.handle('confirm_cancel',{'confirmation_id':cid,'request_id':'yes','reply_to':result.body['message_id'],'confirmed':True},CUSTOMER)
        conflict=await api.handle('request_handoff',{'session_id':sid,'request_id':'yes'},CUSTOMER)
        assert conflict.status==409
        h.store.close()
    asyncio.run(check())


def test_internal_runtime_operations_are_not_public(tmp_path):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        for operation in ('drain_pending','recover','get_health','arbitrary_action'):
            assert (await api.handle(operation,{},CUSTOMER)).status==400
        assert (await api.handle('open_chat',{'order_id':'o1','request_id':'r'},None)).status==401
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('ctx', [TrustedRequestContext(123), TrustedRequestContext(' '), TrustedRequestContext('customer', 'care_trace'), TrustedRequestContext('customer', None), TrustedRequestContext('customer', frozenset({1}))])
@pytest.mark.parametrize('operation,payload', [('open_chat', {'order_id':'o1','request_id':'r'}), ('get_handoffs', {}), ('get_trace', {'session_id':'missing'})])
def test_invalid_trusted_context_is_unauthenticated(tmp_path, ctx, operation, payload):
    async def check():
        h=harness(tmp_path)
        try:
            result=await CareApi(h).handle(operation,payload,ctx)
            assert result.status==401
        finally:
            h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('operation', ['get_messages','handle_message','prepare_cancel','request_handoff','get_trace'])
def test_resource_denial_does_not_reveal_existence(tmp_path, operation):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        try:
            sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
            ctx=TrustedRequestContext('stranger', frozenset({'care_trace'}) if operation=='get_trace' else frozenset())
            # Provider must reject this principal even if it has an unrelated read capability.
            async def deny(ctx, order_id):
                from care_truc.runtime_types import CareError
                raise CareError('forbidden',403)
            h.context_provider.authorize=deny
            base={'session_id':sid}
            if operation=='handle_message': base.update(message_id='m',text='hello')
            elif operation in ('prepare_cancel','request_handoff'): base['request_id']='r'
            denied=await api.handle(operation,base,ctx)
            missing=await api.handle(operation,dict(base,session_id='missing'),ctx)
            assert denied==missing
            assert denied.status==404
        finally: h.store.close()
    asyncio.run(check())


def test_public_response_history_preserves_metadata_and_separates_system_events(tmp_path):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        try:
            sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
            posted=await api.handle('handle_message',{'session_id':sid,'message_id':'m','text':'tại sao'},CUSTOMER)
            history=(await api.handle('get_messages',{'session_id':sid},CUSTOMER)).body
            response=history['messages'][-1]
            for key in ('intent','assessment_ref','evidence_refs','codes','effect_ids','source','message_id'):
                assert response[key]==posted.body[key]
            assert history['system_events']==[]
            assert 'trace' not in str(history)
            assert len({m['id'] for m in history['messages']})==2
        finally: h.store.close()
    asyncio.run(check())


def test_public_history_staff_permission_does_not_impersonate_customer(tmp_path):
    async def check():
        h=harness(tmp_path)
        try:
            sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
            assert (await CareApi(h).handle('get_messages',{'session_id':sid},STAFF)).status==404
        finally: h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('operation,payload', [('handle_message',{'session_id':'s','message_id':'m','text':'hi'}),('prepare_cancel',{'session_id':'s','request_id':'r'}),('confirm_cancel',{'confirmation_id':'c','request_id':'r','reply_to':'p','confirmed':True}),('request_handoff',{'session_id':'s','request_id':'r'}),('get_messages',{'session_id':'s'})])
def test_all_customer_handlers_require_authentication(tmp_path, operation, payload):
    async def check():
        h=harness(tmp_path)
        try:
            for ctx in (None, {}, TrustedRequestContext(1)):
                assert (await CareApi(h).handle(operation,payload,ctx)).status==401
        finally: h.store.close()
    asyncio.run(check())


def test_staff_capabilities_are_separate(tmp_path):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        try:
            sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
            assert (await api.handle('get_trace',{'session_id':sid},TrustedRequestContext('staff',frozenset({'care_handoffs'})))).status==403
            assert (await api.handle('get_handoffs',{},TrustedRequestContext('staff',frozenset({'care_trace'})))).status==403
            assert (await api.handle('get_handoffs',{},STAFF)).status==200
        finally: h.store.close()
    asyncio.run(check())


def test_missing_assessment_refusal_and_human_request_remain_public(tmp_path):
    from dataclasses import replace
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        try:
            h.context_provider.snapshot=replace(h.context_provider.snapshot,assessment=None)
            sid=(await api.handle('open_chat',{'order_id':'o1','request_id':'open'},CUSTOMER)).body['session_id']
            result=await api.handle('handle_message',{'session_id':sid,'message_id':'m','text':'why'},CUSTOMER)
            assert result.status==200 and 'assessment_missing' in result.body['codes']
            assert result.body['assessment_ref'] is None and 'on_track' not in str(result.body)
            handoff=await api.handle('request_handoff',{'session_id':sid,'request_id':'human'},CUSTOMER)
            assert handoff.status==200 and 'customer_requested_human' in handoff.body['codes']
        finally: h.store.close()
    asyncio.run(check())


def test_current_receipt_get_does_not_mutate_post(tmp_path):
    from care_truc.dispatcher import EffectDispatcher
    from .helpers import Gate, ScriptedGateway
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        try:
            sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
            payload={'session_id':sid,'request_id':'human'}
            original=await api.handle('request_handoff',payload,CUSTOMER)
            gateway=ScriptedGateway(); gateway.outcome='succeeded'
            await EffectDispatcher(h,gateway,Gate()).drain_pending()
            history=(await api.handle('get_messages',{'session_id':sid},CUSTOMER)).body
            assert history['effects'][0]['outcome']=='succeeded'
            assert history['system_events'][0]['kind']=='receipt'
            assert all(m['kind']!='receipt' for m in history['messages'])
            assert original==await api.handle('request_handoff',payload,CUSTOMER)
            assert original.body['status']=='pending_delivery'
        finally: h.store.close()
    asyncio.run(check())


def test_api_unready_and_storage_errors_are_503(tmp_path):
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        try:
            h.accepting=False
            assert (await api.handle('open_chat',{'order_id':'o1','request_id':'r'},CUSTOMER)).status==503
            h.accepting=True
            async def unavailable(ctx, order_id): raise OSError('private path')
            h.context_provider.authorize=unavailable
            response=await api.handle('open_chat',{'order_id':'o1','request_id':'r'},CUSTOMER)
            assert response.status==503 and response.body=={'error':'service_error'}
        finally: h.store.close()
    asyncio.run(check())


def test_order_and_confirmation_authorization_is_opaque(tmp_path):
    from care_truc.runtime_types import CareError
    async def check():
        h=harness(tmp_path); api=CareApi(h)
        try:
            sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
            prompt=await api.handle('prepare_cancel',{'session_id':sid,'request_id':'cancel'},CUSTOMER)
            other=TrustedRequestContext('stranger')
            base={'request_id':'confirm','reply_to':prompt.body['message_id'],'confirmed':True}
            denied=await api.handle('confirm_cancel',dict(base,confirmation_id=prompt.body['confirmation_id']),other)
            missing=await api.handle('confirm_cancel',dict(base,confirmation_id='missing'),other)
            assert denied==missing and denied.status==404
            async def deny(ctx,order_id): raise CareError('forbidden',403)
            h.context_provider.authorize=deny
            order=await api.handle('open_chat',{'order_id':'o1','request_id':'r'},other)
            assert order.status==404 and order.body=={'error':'not_found'}
        finally: h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('operation,payload', [
    ('get_messages', {}),
    ('handle_message', {'message_id': 'm', 'text': 'hello'}),
])
def test_storage_failure_preserves_service_error_response(tmp_path, operation, payload):
    async def check():
        h = harness(tmp_path)
        api = CareApi(h)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        h.store.close()
        response = await api.handle(operation, {'session_id': sid, **payload}, CUSTOMER)
        assert response.status == 503
        assert response.body == {'error': 'service_error'}
    asyncio.run(check())
