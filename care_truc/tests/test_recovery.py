import asyncio
import json
import sqlite3
import pytest

from care_truc.lifecycle import CareRuntime
from care_truc.runtime_types import CareError, CustomerEvent, fingerprint
from .helpers import ContextAdapter, CUSTOMER, FakeClock, Gate, ScriptedGateway, BlockingSelector


def adapters(**changes):
    return dict(context_provider=ContextAdapter(),clock=FakeClock(),gateway=ScriptedGateway(),gate=Gate(),**changes)


def test_restart_recovers_orphan_without_second_model_attempt(tmp_path):
    async def check():
        ports=adapters(selector=BlockingSelector())
        runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        event=CustomerEvent('message','m','tại sao')
        req=runtime.store.begin_request(sid,'customer',event,fingerprint(event))
        runtime.store.reserve_processing(req['id'],runtime.store.boot_generation,0)
        runtime.store.reserve_model(req['id'])
        await runtime.shutdown()
        again=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        assert again.store.load_session(sid).turn_count==1
        assert ports['selector'].calls==0
        assert (await again.harness.handle_message(sid,'m','tại sao',CUSTOMER)).source=='template'
        await again.shutdown()
    asyncio.run(check())


def test_health_and_lock_are_real_and_missing_adapters_are_not_fake(tmp_path):
    async def check():
        runtime=await CareRuntime.start('run',adapters(),root=tmp_path,background=False)
        assert runtime.get_health().status=='degraded'
        assert 'model_unavailable' in runtime.get_health().codes
        with pytest.raises(RuntimeError):
            await CareRuntime.start('run',adapters(),root=tmp_path,background=False)
        await runtime.shutdown()
        with pytest.raises(CareError,match='not_ready'):
            await runtime.harness.open_chat('o1','open',CUSTOMER)
        assert runtime.get_health().status=='not_ready'
    asyncio.run(check())


def test_live_recovery_worker_resumes_due_request(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        event=CustomerEvent('message','m','tại sao')
        row=runtime.store.begin_request(sid,'customer',event,fingerprint(event))
        runtime.store.reserve_processing(row['id'],runtime.store.boot_generation,0)
        runtime.store.retry_request(row['id'],ports['clock'].utcnow().timestamp())
        await runtime.recover()
        assert runtime.store.load_session(sid).turn_count==0
        ports['clock'].advance(1)
        await runtime.recover()
        assert runtime.store.load_session(sid).turn_count==1
        await runtime.shutdown()
    asyncio.run(check())


def test_corrupt_database_is_not_overwritten_by_startup(tmp_path):
    path=tmp_path/'run'/'care.sqlite'; path.parent.mkdir(); path.write_bytes(b'bad')
    with pytest.raises(sqlite3.DatabaseError):
        asyncio.run(CareRuntime.start('run',adapters(),root=tmp_path,background=False))
    assert path.read_bytes()==b'bad'


def test_restart_classifies_inflight_before_readiness(tmp_path):
    async def check():
        ports=adapters(); runtime=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        sid=(await runtime.harness.open_chat('o1','open',CUSTOMER)).session_id
        result=await runtime.harness.request_handoff(sid,'h',CUSTOMER)
        row=runtime.store.effect(result.effect_ids[0])
        runtime.store.claim_effect(row['id'],1,1,0)
        await runtime.shutdown()
        again=await CareRuntime.start('run',ports,root=tmp_path,background=False)
        assert again.store.effect(row['id'])['state']=='needs_reconciliation'
        assert again.get_health().reconciliation==1
        assert not ports['gateway'].submissions
        await again.shutdown()
    asyncio.run(check())
