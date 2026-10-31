import asyncio
from dataclasses import replace
import pytest

from care_truc.dispatcher import EffectDispatcher
from care_truc.runtime_types import CareError, Receipt, fingerprint
from .helpers import Gate, ScriptedGateway, CUSTOMER
from .test_turn_loop import harness
from .test_dispatch_races import pending


def test_remote_accepted_then_timeout_is_reconciled_without_duplicate_submit(tmp_path):
    async def check():
        h=harness(tmp_path); sid,eid=await pending(h)
        gateway=ScriptedGateway(); gateway.submit_error=TimeoutError()
        d=EffectDispatcher(h,gateway,Gate())
        await d.drain_pending()
        assert h.store.effect(eid)['state']=='needs_reconciliation'
        assert h.store.effect(eid)['outcome']=='unknown'
        await d.drain_pending()
        assert h.store.effect(eid)['state']=='delivered'
        assert h.store.effect(eid)['outcome']=='accepted'
        assert len(gateway.submissions)==1
        assert len(gateway.lookups)==1
        h.store.close()
    asyncio.run(check())


def test_receipt_revisions_and_terminals_cannot_be_overwritten(tmp_path):
    async def check():
        h=harness(tmp_path); sid,eid=await pending(h)
        gateway=ScriptedGateway(); gateway.outcome='succeeded'
        await EffectDispatcher(h,gateway,Gate()).drain_pending()
        receipt=next(iter(gateway.receipts.values()))
        count=len(h.store.events(sid))
        assert h.store.record_receipt(receipt) is False
        assert h.store.record_receipt(replace(receipt,revision=0,outcome='accepted')) is False
        with pytest.raises(CareError,match='revision_conflict'):
            h.store.record_receipt(replace(receipt,outcome='rejected'))
        with pytest.raises(CareError,match='terminal_conflict'):
            h.store.record_receipt(replace(receipt,revision=2,outcome='rejected'))
        assert h.store.effect(eid)['outcome']=='succeeded'
        assert len(h.store.events(sid))==count
        h.store.close()
    asyncio.run(check())


def test_lookup_budget_survives_repeated_drains(tmp_path):
    async def check():
        h=harness(tmp_path); sid,eid=await pending(h)
        gateway=ScriptedGateway(); gateway.submit_error=TimeoutError(); gateway.lookup_error=TimeoutError()
        d=EffectDispatcher(h,gateway,Gate()); await d.drain_pending()
        for advance in (0,1,5,100):
            h.clock.advance(advance); await d.drain_pending()
        assert len(gateway.lookups)==3
        assert h.store.effect(eid)['manual']==1
        assert h.store.effect(eid)['outcome']=='unknown'
        assert len(gateway.submissions)==1
        h.store.close()
    asyncio.run(check())


def test_submission_budget_keeps_key_and_payload(tmp_path):
    async def check():
        h=harness(tmp_path); sid,eid=await pending(h)
        gateway=ScriptedGateway(); gateway.submit_error=TimeoutError()
        async def absent(key,*,deadline):
            gateway.lookups.append(key); return None
        gateway.lookup=absent
        d=EffectDispatcher(h,gateway,Gate()); await d.drain_pending()
        for _ in range(8):
            h.clock.advance(5); await d.drain_pending()
        assert len(gateway.submissions)==3
        assert len({p.key for p in gateway.submissions})==1
        assert len({p.payload for p in gateway.submissions})==1
        assert h.store.effect(eid)['state']=='needs_reconciliation'
        h.store.close()
    asyncio.run(check())


def test_handoff_ack_is_not_money_success(tmp_path):
    async def check():
        h=harness(tmp_path); sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        await h.request_handoff(sid,'h',CUSTOMER)
        await EffectDispatcher(h,ScriptedGateway(),Gate()).drain_pending()
        assert h.store.load_session(sid).status=='transferred'
        h.store.close()
    asyncio.run(check())
