import asyncio
from dataclasses import replace

import pytest

from care_truc.dispatcher import EffectDispatcher
from care_truc.runtime_types import (CareError, CustomerEvent, EffectProposal,
    PolicyOutcome, TurnResult, canonical, fingerprint)
from .helpers import CUSTOMER, Gate, ScriptedGateway
from .test_dispatch_races import pending
from .test_memory import setup_turn
from .test_turn_loop import harness


@pytest.mark.parametrize('capability', [None, False, 1, 'true'])
def test_atomic_final_validation_must_be_explicit_true(tmp_path, capability):
    async def check():
        h = harness(tmp_path)
        _, eid = await pending(h)
        gateway = ScriptedGateway()
        if capability is None:
            from types import SimpleNamespace
            gateway = SimpleNamespace(supports_deadlines=True, submissions=gateway.submissions,
                                      submit=gateway.submit, lookup=gateway.lookup)
        else:
            gateway.atomic_final_validation = capability
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        assert gateway.submissions == []
        assert h.store.effect(eid)['state'] == 'blocked'
        assert h.store.effect(eid)['attempts'] == 0
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('change', ['key', 'session_id', 'order_id', 'kind', 'effect_id', 'evidence_ref', 'payload_order'])
def test_unsent_revision_cannot_change_envelope_binding(tmp_path, change):
    store, request, outcome = setup_turn(tmp_path / 'care.sqlite')
    proposal = EffectProposal('e', 'run:handoff:s', 's', 'o1', 'handoff_request',
                              canonical({'order_id': 'o1', 'reason': 'human'}), request['id'])
    store.commit_turn(request['id'], 0, replace(outcome, proposals=(proposal,)),
                      TurnResult('pending_delivery', 's'), '{}', '{}')
    store.set_effect('e', state='blocked')
    event = CustomerEvent('message', 'new', 'help')
    source = store.begin_request('s', 'customer', event, fingerprint(event))
    changed = replace(proposal, **({change: 'other'} if change != 'payload_order' else
                                  {'payload': canonical({'order_id': 'other'})}))
    with pytest.raises(CareError, match='effect_binding_conflict'):
        store.revise_proposal(proposal.key, source['id'], changed)
    assert store.effect('e')['revision'] == 1
    assert store.effect('e')['proposal'] == canonical(proposal)
    store.close()


@pytest.mark.parametrize("route", ["lookup", "submit"])
def test_receipt_must_belong_to_requested_effect(tmp_path, route):
    async def check():
        h = harness(tmp_path)
        gateway = ScriptedGateway()
        sid = (await h.open_chat('o1', 'open-one', CUSTOMER)).session_id
        first = await h.request_handoff(sid, 'human-one', CUSTOMER)
        dispatcher = EffectDispatcher(h, gateway, Gate())
        await dispatcher.drain_pending(limit=1)
        sid2 = (await h.open_chat('o2', 'open-two', CUSTOMER)).session_id
        second = await h.request_handoff(sid2, 'human-two', CUSTOMER)
        eid = second.effect_ids[0]
        wrong = gateway.receipts[h.store.effect(first.effect_ids[0])['effect_key']]
        async def lookup(key, *, deadline):
            return wrong
        if route == "lookup":
            assert h.store.claim_effect(eid, h.session(sid2).version, 1, 0) is not None
            gateway.lookup = lookup
            await dispatcher.reconcile(eid)
            assert h.store.effect(eid)['lookups'] == 1
        else:
            async def submit(proposal, *, deadline):
                return wrong
            gateway.submit = submit
            await dispatcher.drain_pending()
            assert h.store.effect(eid)['state'] == 'needs_reconciliation'
        assert h.store.effect(eid)['outcome'] == 'unknown'
        assert h.session(sid2).status == 'handoff_pending'
        h.store.close()
    asyncio.run(check())


def test_nonfinancial_revision_preserves_binding_and_appends_history(tmp_path):
    store, request, outcome = setup_turn(tmp_path / 'care.sqlite')
    proposal = EffectProposal('e', 'run:handoff:s', 's', 'o1', 'handoff_request',
                              canonical({'order_id': 'o1', 'reason': 'human'}), request['id'])
    store.commit_turn(request['id'], 0, replace(outcome, proposals=(proposal,)),
                      TurnResult('pending_delivery', 's'), '{}', '{}')
    store.set_effect('e', state='blocked')
    event = CustomerEvent('message', 'new', 'help')
    source = store.begin_request('s', 'customer', event, fingerprint(event))
    changed = replace(proposal, payload=canonical({'order_id': 'o1', 'reason': 'updated'}))
    assert store.revise_proposal(proposal.key, source['id'], changed) == 2
    assert store.effect('e')['proposal'] == canonical(changed)
    assert store.db.execute('SELECT count(*) FROM effect_proposals').fetchone()[0] == 2
    store.close()


@pytest.mark.parametrize('point', ['committed', 'accepted', 'receipt'])
def test_restart_delivery_uses_original_key_and_immutable_response(tmp_path, point):
    from care_truc.lifecycle import CareRuntime
    from .test_recovery import adapters

    async def check():
        ports = adapters()
        runtime = await CareRuntime.start('run', ports, root=tmp_path, background=False)
        sid = (await runtime.harness.open_chat('o1', 'open', CUSTOMER)).session_id
        result = await runtime.harness.request_handoff(sid, 'human', CUSTOMER)
        row = runtime.store.effect(result.effect_ids[0])
        if point in ('accepted', 'receipt'):
            proposal = runtime.store.claim_effect(row['id'], 1, 1, 0)
            receipt = await ports['gateway'].submit(proposal, deadline=2)
            if point == 'receipt':
                runtime.store.record_receipt(receipt)
        await runtime.shutdown()
        again = await CareRuntime.start('run', ports, root=tmp_path, background=False)
        await again.harness.drain_pending()
        assert len(ports['gateway'].submissions) == 1
        assert ports['gateway'].submissions[0].key == row['effect_key']
        assert again.store.effect(row['id'])['outcome'] == 'accepted'
        assert again.harness.session(sid).status == 'transferred'
        assert await again.harness.request_handoff(sid, 'human', CUSTOMER) == result
        assert sum(e['kind'] == 'receipt' for e in again.store.events(sid)) == 1
        await again.shutdown()
    asyncio.run(check())


def test_later_handoff_receipt_cannot_reopen_completed_session(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        result = await h.request_handoff(sid, 'human', CUSTOMER)
        gateway = ScriptedGateway()
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        state = replace(h.session(sid), status='completed')
        h.store.db.execute('UPDATE sessions SET data=? WHERE id=?', (canonical(state), sid))
        receipt = gateway.receipts[h.store.effect(result.effect_ids[0])['effect_key']]
        assert h.store.record_receipt(replace(receipt, revision=2, outcome='succeeded'))
        assert h.session(sid).status == 'completed'
        assert h.session(sid).version == state.version
        h.store.close()
    asyncio.run(check())
