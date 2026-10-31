"""Task 5 service assertions ported to the single async harness."""
import asyncio
from dataclasses import replace
from datetime import timedelta, timezone
import json
import pytest
from care_truc.harness import CareHarness
from care_truc.runtime_types import CareError, TrustedRequestContext, canonical
from care_truc.store import MemoryStore
from .helpers import CUSTOMER, SYSTEM, STAFF, NOW, ContextAdapter, FakeClock, BlockingSelector
from .test_integration import contact
from .test_turn_loop import harness


def test_client_open_never_promotes_even_for_server(tmp_path):
    async def check():
        h=harness(tmp_path)
        sid=(await h.open_chat('o1','open',SYSTEM)).session_id
        assert h.store.load_session(sid).opened_by=='customer'
        assert not h.store.effects()
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('change',['missing','old','feed','future','evidence_future','naive'])
def test_invalid_contact_never_creates_session(tmp_path,change):
    async def check():
        h=harness(tmp_path)
        ctx=h.context_provider.snapshot
        if change=='missing': ctx=replace(ctx,assessment=None)
        elif change=='old': ctx=replace(ctx,assessment=replace(ctx.assessment,assessed_at=NOW-timedelta(minutes=31)))
        elif change=='feed': ctx=replace(ctx,guard=None)
        elif change=='future': ctx=replace(ctx,assessment=replace(ctx.assessment,assessed_at=NOW+timedelta(seconds=1)))
        elif change=='naive': ctx=replace(ctx,cutoff=NOW.replace(tzinfo=None))
        else: ctx=replace(ctx,assessment=replace(ctx.assessment,evidence=({'ingested_at':NOW+timedelta(seconds=1)},)))
        h.context_provider.snapshot=ctx
        with pytest.raises(CareError): await h.open_contact(contact(),SYSTEM)
        assert not h.store.db.execute('SELECT id FROM sessions').fetchall()
        assert not h.store.effects()
        h.store.close()
    asyncio.run(check())


def test_evidence_private_retry_before_context_and_scope(tmp_path):
    async def check():
        h=harness(tmp_path)
        ctx=h.context_provider.snapshot
        fact={'feed':'ops','source_table':'scan','record_id':'private','ingested_at':NOW,
              'fact_code':'driver_note','value':'secret phone 0901234567','is_structured':False}
        h.context_provider.snapshot=replace(ctx,assessment=replace(ctx.assessment,evidence=(fact,)))
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        result=await h.handle_message(sid,'m','tại sao',CUSTOMER)
        await h.handle_message(sid,'m2','tại sao',CUSTOMER)
        assert h.store.db.execute('SELECT count(*) FROM evidence_bundles').fetchone()[0]==2
        assert 'private' in h.store.db.execute('SELECT data FROM evidence_bundles').fetchone()[0]
        assert 'private' not in str(await h.get_messages(sid,CUSTOMER))
        async def offline(*args): raise AssertionError('replay loaded context')
        h.context_provider.load=offline
        assert await h.handle_message(sid,'m','tại sao',CUSTOMER)==result
        with pytest.raises(CareError): await h.handle_message(sid,'m','different',CUSTOMER)
        with pytest.raises(CareError): await h.handle_message(sid,'m','tại sao',STAFF)
        other=CareHarness('different',h.store,h.context_provider,h.clock)
        with pytest.raises(CareError): await other.handle_message(sid,'m','tại sao',CUSTOMER)
        h.store.close()
    asyncio.run(check())


def test_missing_facts_accept_human_but_authorization_failure_does_not(tmp_path):
    async def check():
        h=harness(tmp_path)
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        h.context_provider.snapshot=replace(h.context_provider.snapshot,assessment=None,guard=None)
        async def denied(*args): raise CareError('order_not_found',404)
        original=h.context_provider.authorize
        h.context_provider.authorize=denied
        with pytest.raises(CareError,match='order_not_found'):
            await h.handle_message(sid,'m','Tôi muốn gặp nhân viên',CUSTOMER)
        assert h.store.load_session(sid).turn_count==0
        h.context_provider.authorize=original
        await h.handle_message(sid,'m','Tôi muốn gặp nhân viên',CUSTOMER)
        assert h.store.load_session(sid).status=='handoff_pending'
        assert json.loads(h.store.effects()[0]['proposal'])['kind']=='handoff_request'
        h.store.close()
    asyncio.run(check())


def test_selector_outside_transaction_rejects_version_race(tmp_path):
    async def check():
        selector=BlockingSelector(); h=harness(tmp_path,selector=selector)
        sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        running=asyncio.create_task(h.handle_message(sid,'m','tại sao',CUSTOMER))
        await selector.started.wait()
        assert not h.store.db.in_transaction
        h.store.db.execute('UPDATE sessions SET version=version+1 WHERE id=?',(sid,))
        selector.release.set()
        with pytest.raises(CareError,match='stale_callback'): await running
        assert h.store.load_session(sid).turn_count==0
        assert not h.store.events(sid)
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('status',['transferred','completed'])
def test_terminal_replays_old_rejects_new(tmp_path,status):
    async def check():
        h=harness(tmp_path); sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        result=await h.handle_message(sid,'m','tại sao',CUSTOMER)
        state=replace(h.store.load_session(sid),status=status)
        h.store.db.execute('UPDATE sessions SET data=? WHERE id=?',(canonical(state),sid))
        assert await h.handle_message(sid,'m','tại sao',CUSTOMER)==result
        with pytest.raises(CareError,match='session_state_conflict'):
            await h.handle_message(sid,'new','cho tôi xu',CUSTOMER)
        assert h.store.load_session(sid)==state
        h.store.close()
    asyncio.run(check())


def test_cached_open_contact_and_turn_survive_restart(tmp_path):
    async def check():
        h=harness(tmp_path); sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        result=await h.handle_message(sid,'m','tại sao',CUSTOMER)
        opening=await h.open_contact(contact(),SYSTEM)
        h.store.close()
        h=harness(tmp_path)
        async def offline(*args): raise AssertionError('replay loaded context')
        h.context_provider.load=offline
        assert (await h.open_chat('o1','open',CUSTOMER)).session_id==sid
        assert await h.open_contact(contact(),SYSTEM)==opening
        assert await h.handle_message(sid,'m','tại sao',CUSTOMER)==result
        assert h.store.load_session(sid).turn_count==1
        h.store.close()
    asyncio.run(check())


def test_concurrent_contact_creates_one_session_and_effect(tmp_path):
    async def check():
        h=harness(tmp_path)
        results=await asyncio.gather(h.open_contact(contact(),SYSTEM),h.open_contact(contact(),SYSTEM))
        assert results[0]==results[1]
        assert h.store.db.execute('SELECT count(*) FROM sessions').fetchone()[0]==1
        assert len(h.store.effects())==1
        h.store.close()
    asyncio.run(check())


def test_server_cutoff_normalized_and_cannot_regress(tmp_path):
    async def check():
        h=harness(tmp_path); sid=(await h.open_chat('o1','open',CUSTOMER)).session_id
        h.context_provider.snapshot=replace(h.context_provider.snapshot,cutoff=NOW.astimezone(timezone(timedelta(hours=7))))
        await h.handle_message(sid,'m','tại sao',CUSTOMER)
        assert h.store.load_session(sid).last_cutoff.utcoffset()==timedelta(0)
        h.context_provider.snapshot=replace(h.context_provider.snapshot,cutoff=NOW-timedelta(seconds=1))
        with pytest.raises(CareError,match='context_cutoff_regressed'):
            await h.handle_message(sid,'new','cho tôi xu',CUSTOMER)
        assert h.store.load_session(sid).turn_count==1
        h.store.close()
    asyncio.run(check())
