import asyncio
import pytest

from care_truc.api import CareApi
from care_truc.runtime_types import TrustedRequestContext
from .helpers import CUSTOMER, STAFF
from .test_turn_loop import harness


@pytest.mark.parametrize('key', ['source','proactive','role','guard_allowed','cutoff','amount'])
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
        assert 'trace' not in str(history.body) and 'evidence_ref' not in str(history.body)
        assert (await api.handle('get_trace',{'session_id':sid},CUSTOMER)).status==403
        trace=await api.handle('get_trace',{'session_id':sid},STAFF)
        assert trace.status==200 and trace.body['decisions'][0]['phases']==list(range(1,11))
        stranger=TrustedRequestContext('stranger')
        assert (await api.handle('get_messages',{'session_id':sid},stranger)).status==403
        assert (await api.handle('handle_message',{'session_id':sid,'message_id':'m','text':'tại sao'},stranger)).status==403
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
