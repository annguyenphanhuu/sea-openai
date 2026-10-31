import asyncio
from dataclasses import replace
import json
import sqlite3
import pytest

from care_truc.harness import CareHarness
from care_truc.store import MemoryStore
from care_truc.runtime_types import CareError, CustomerEvent, TrustedRequestContext, fingerprint
from .helpers import ContextAdapter, CUSTOMER, FakeClock, BlockingSelector


def harness(tmp_path, **kwargs):
    return CareHarness('run',MemoryStore.open(tmp_path/'care.sqlite'),
                       ContextAdapter(),FakeClock(),**kwargs)


def test_retry_is_immutable_and_counted_once(tmp_path):
    async def check():
        h=harness(tmp_path)
        opened=await h.open_chat('o1','open',CUSTOMER)
        sid=opened.session_id
        assert h.store.load_session(sid).turn_count==0
        one=await h.handle_message(sid,'m','tại sao',CUSTOMER)
        assert one==await h.handle_message(sid,'m','tại sao',CUSTOMER)
        assert h.store.load_session(sid).turn_count==1
        with pytest.raises(CareError,match='conflict'):
            await h.handle_message(sid,'m','other',CUSTOMER)
        with pytest.raises(CareError):
            await h.handle_message(sid,'m','tại sao',TrustedRequestContext('stranger'))
        trace=json.loads(h.store.db.execute('SELECT trace FROM evidence_bundles').fetchone()[0])
        assert trace['phases']==list(range(1,11))
        h.store.close()
    asyncio.run(check())


def test_live_owner_busy_and_other_session_progress(tmp_path):
    async def check():
        selector=BlockingSelector(); h=harness(tmp_path,selector=selector)
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        sid2=(await h.open_chat('o2','open2',CUSTOMER)).session_id
        running=asyncio.create_task(h.handle_message(sid,'m','tại sao',CUSTOMER))
        await selector.started.wait()
        assert (await h.handle_message(sid,'m','tại sao',CUSTOMER)).status=='processing'
        assert (await h.handle_message(sid,'other','hello',CUSTOMER)).status=='session_busy'
        other=await h.request_handoff(sid2,'human',CUSTOMER)
        assert other.status=='pending_delivery'
        assert h.store.load_session(sid2).turn_count==1
        selector.release.set(); await running
        assert selector.calls==1
        h.store.close()
    asyncio.run(check())


def test_orphan_resume_does_not_call_model_twice(tmp_path):
    async def check():
        selector=BlockingSelector(); h=harness(tmp_path,selector=selector)
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        running=asyncio.create_task(h.handle_message(sid,'m','tại sao',CUSTOMER))
        await selector.started.wait()
        running.cancel()
        with pytest.raises(asyncio.CancelledError): await running
        assert not h.owners
        result=await h.handle_message(sid,'m','tại sao',CUSTOMER)
        assert result.status=='committed' and result.source=='template'
        assert selector.calls==1
        assert h.store.load_session(sid).turn_count==1
        h.store.close()
    asyncio.run(check())


def test_commit_failure_does_not_change_state_or_dispatch(tmp_path):
    async def check():
        h=harness(tmp_path); sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        h.store.db.execute("CREATE TRIGGER fail BEFORE INSERT ON evidence_bundles BEGIN SELECT RAISE(ABORT,'disk failure'); END")
        with pytest.raises(CareError,match='service_error'):
            await h.request_handoff(sid,'h',CUSTOMER)
        assert h.store.load_session(sid).turn_count==0
        assert h.store.effects()==[]
        h.store.close()
    asyncio.run(check())
