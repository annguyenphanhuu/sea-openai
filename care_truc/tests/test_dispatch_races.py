import asyncio
import json

from care_truc.dispatcher import EffectDispatcher
from .helpers import CUSTOMER, Gate, ScriptedGateway
from .test_turn_loop import harness


async def pending(h):
    sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
    await h.handle_message(sid,'want','muốn hủy',CUSTOMER)
    confirmation=h.store.load_session(sid).pending.confirmation_id
    result=await h.confirm_cancel(confirmation,'confirm',CUSTOMER)
    return sid,result.effect_ids[0]


def test_change_before_claim_prevents_network(tmp_path):
    async def check():
        h=harness(tmp_path); gateway=ScriptedGateway()
        sid,eid=await pending(h)
        await h.handle_message(sid,'mind','tôi không muốn hủy',CUSTOMER)
        d=EffectDispatcher(h,gateway,Gate())
        await d.drain_pending()
        assert gateway.submissions==[]
        assert h.store.effect(eid)['state']=='blocked'
        h.store.close()
    asyncio.run(check())


def test_change_after_claim_does_not_claim_recall_or_hold_lock(tmp_path):
    async def check():
        h=harness(tmp_path); sid,eid=await pending(h)
        gateway=ScriptedGateway(); original=gateway.submit
        entered=asyncio.Event(); release=asyncio.Event()
        async def submit(proposal,*,deadline):
            assert not h.lock(sid).locked()
            assert not h.store.db.in_transaction
            entered.set(); await release.wait()
            return await original(proposal,deadline=deadline)
        gateway.submit=submit
        task=asyncio.create_task(EffectDispatcher(h,gateway,Gate()).drain_pending())
        await entered.wait()
        changed=await h.handle_message(sid,'mind','tôi không muốn hủy',CUSTOMER)
        assert 'đang chờ kết quả' in changed.text
        assert h.store.effect(eid)['state']=='in_flight'
        release.set(); await task
        assert h.store.effect(eid)['state']=='delivered'
        h.store.close()
    asyncio.run(check())


def test_missing_or_denied_gate_blocks_submission(tmp_path):
    async def check():
        h=harness(tmp_path); sid,eid=await pending(h)
        gateway=ScriptedGateway()
        await EffectDispatcher(h,gateway,None).drain_pending()
        assert gateway.submissions==[]
        assert h.store.effect(eid)['state']=='blocked'
        h.store.close()
    asyncio.run(check())


def test_version_change_during_gate_discards_claim(tmp_path):
    async def check():
        h=harness(tmp_path); sid,eid=await pending(h)
        gateway=ScriptedGateway(); gate=Gate()
        original=gate.check
        async def change(proposal,ctx,*,deadline):
            # A separate writer changing committed version while a remote gate awaits.
            h.store.db.execute('UPDATE sessions SET version=version+1 WHERE id=?',(sid,))
            return await original(proposal,ctx,deadline=deadline)
        gate.check=change
        await EffectDispatcher(h,gateway,gate).drain_pending()
        assert gateway.submissions==[]
        assert h.store.effect(eid)['attempts']==0
        h.store.close()
    asyncio.run(check())
