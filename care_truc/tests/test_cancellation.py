import asyncio
from dataclasses import replace
from datetime import timedelta
import pytest

from care_truc.runtime_types import CareError
from .helpers import CUSTOMER, NOW
from .test_turn_loop import harness


def test_explicit_consent_and_reply_are_required(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        prompt = await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        pending = (await h.session(sid)).pending
        for request, consent, reply in [('no', False, pending.reply_to), ('wrong', True, 'wrong')]:
            result = await h.confirm_cancel(pending.confirmation_id, request, CUSTOMER,
                                            reply_to=reply, confirmed=consent)
            assert not result.effect_ids
        assert not h.store.effects()
        h.store.close()
    asyncio.run(check())


def test_consumed_id_replays_original_response_after_restart_and_terminal(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        pending = (await h.session(sid)).pending
        first = await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER,
                                      reply_to=pending.reply_to, confirmed=True)
        from care_truc.dispatcher import EffectDispatcher
        from .helpers import Gate, ScriptedGateway
        gateway = ScriptedGateway()
        gateway.outcome = 'succeeded'
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        assert first == await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER,
                                               reply_to=pending.reply_to, confirmed=True)
        await h.request_handoff(sid, 'human', CUSTOMER)
        h.store.close()
        h = harness(tmp_path)
        assert first == await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER,
                                               reply_to=pending.reply_to, confirmed=True)
        assert first == await h.confirm_cancel(pending.confirmation_id, 'different', CUSTOMER,
                                               reply_to=pending.reply_to, confirmed=True)
        assert len([e for e in h.store.effects() if ':cancel:' in e['effect_key']]) == 1
        h.store.close()
    asyncio.run(check())


def test_unbound_accept_never_authorizes_cancellation(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        reply = (await h.session(sid)).pending.reply_to
        result = await h.handle_message(sid, 'yes', 'đồng ý', CUSTOMER)
        assert not result.effect_ids
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('minutes', [10, 11])
def test_expiry_is_business_time_and_never_renews(tmp_path, minutes):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        pending = (await h.session(sid)).pending
        assert pending.expires_at == NOW + timedelta(minutes=10)
        h.context_provider.snapshot = replace(h.context_provider.snapshot, cutoff=NOW + timedelta(minutes=minutes))
        result = await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER,
                                      reply_to=pending.reply_to, confirmed=True)
        assert 'cancel_confirmation_expired' in result.codes
        assert not result.effect_ids and (await h.session(sid)).pending is None
        assert h.store.db.execute('SELECT status FROM cancellations').fetchone()[0] == 'expired'
        assert 'xác nhận' in result.text
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('change', ['supersede', 'retract', 'handoff'])
def test_old_confirmation_cannot_enqueue_after_invalidation(tmp_path, change):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        old = (await h.session(sid)).pending
        if change == 'handoff':
            await h.request_handoff(sid, 'new', CUSTOMER)
            with pytest.raises(CareError, match='session_state_conflict'):
                await h.confirm_cancel(old.confirmation_id, 'yes', CUSTOMER, reply_to=old.reply_to, confirmed=True)
        else:
            await h.handle_message(sid, 'new', 'muốn hủy' if change == 'supersede' else 'tôi không muốn hủy', CUSTOMER)
            result = await h.confirm_cancel(old.confirmation_id, 'yes', CUSTOMER, reply_to=old.reply_to, confirmed=True)
            assert not result.effect_ids
        assert h.store.db.execute('SELECT status FROM cancellations WHERE id=?', (old.confirmation_id,)).fetchone()[0] == 'invalidated'
        assert not any(':cancel:' in e['effect_key'] for e in h.store.effects())
        h.store.close()
    asyncio.run(check())


def test_lost_lifecycle_fails_closed_and_requires_new_prompt(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        old = (await h.session(sid)).pending
        # Emulate an older v1 database with an embedded pending but no lifecycle table.
        h.store.db.execute('DROP TABLE cancellations')
        h.store.close()
        h = harness(tmp_path)
        result = await h.confirm_cancel(old.confirmation_id, 'yes', CUSTOMER, reply_to=old.reply_to, confirmed=True)
        assert 'cancel_confirmation_invalid' in result.codes
        assert not result.effect_ids and (await h.session(sid)).pending is None
        assert h.store.db.execute('SELECT count(*) FROM cancellations').fetchone()[0] == 0
        fresh = await h.handle_message(sid, 'again', 'muốn hủy', CUSTOMER)
        assert fresh.confirmation_id != old.confirmation_id
        h.store.close()
    asyncio.run(check())


def test_confirm_is_turn_eight_and_cannot_bypass_handoff(tmp_path):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        for i in range(6):
            await h.handle_message(sid, f'm{i}', 'xin chào', CUSTOMER)
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        pending = (await h.session(sid)).pending
        result = await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER, reply_to=pending.reply_to, confirmed=True)
        assert 'turn_limit' in result.codes
        assert (await h.session(sid)).turn_count == 8 and (await h.session(sid)).status == 'handoff_pending'
        assert all(':cancel:' not in e['effect_key'] for e in h.store.effects())
        h.store.close()
    asyncio.run(check())


def test_consumed_alias_id_conflicts_on_changed_payload_and_scope(tmp_path):
    async def check():
        from care_truc.harness import CareHarness
        from .helpers import STAFF
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        pending = (await h.session(sid)).pending
        first = await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER, reply_to=pending.reply_to, confirmed=True)
        assert first == await h.confirm_cancel(pending.confirmation_id, 'alias', CUSTOMER, reply_to=pending.reply_to, confirmed=True)
        with pytest.raises(CareError, match='request_conflict'):
            await h.confirm_cancel(pending.confirmation_id, 'alias', CUSTOMER, reply_to=pending.reply_to, confirmed=False)
        for scoped in [h, CareHarness('other-run', h.store, h.context_provider, h.clock)]:
            with pytest.raises(CareError, match='not_found'):
                await scoped.confirm_cancel(pending.confirmation_id, 'foreign', STAFF if scoped is h else CUSTOMER,
                                            reply_to=pending.reply_to, confirmed=True)
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('field,value', [('principal_id','other'), ('session_id','other'), ('order_id','o2'), ('contact_id','other'), ('version',99)])
def test_corrupt_binding_cannot_authorize_action(tmp_path, field, value):
    async def check():
        import json
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        pending = (await h.session(sid)).pending
        data = json.loads(h.store.db.execute('SELECT data FROM sessions WHERE id=?', (sid,)).fetchone()[0])
        data['pending'][field] = value
        h.store.db.execute('UPDATE sessions SET data=? WHERE id=?', (json.dumps(data), sid))
        result = await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER, reply_to=pending.reply_to, confirmed=True)
        assert not result.effect_ids and not h.store.effects()
        h.store.close()
    asyncio.run(check())


def test_cancellation_revision_is_forbidden_even_before_send(tmp_path):
    async def check():
        import json
        from care_truc.runtime_types import EffectProposal
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        pending = (await h.session(sid)).pending
        result = await h.confirm_cancel(pending.confirmation_id, 'yes', CUSTOMER, reply_to=pending.reply_to, confirmed=True)
        row = h.store.effect(result.effect_ids[0])
        proposal = EffectProposal(**json.loads(row['proposal']))
        h.store.set_effect(row['id'], state='blocked')
        source = h.store.db.execute("SELECT id FROM requests WHERE client_id='yes'").fetchone()[0]
        with pytest.raises(CareError, match='cancel_revision_not_allowed'):
            h.store.revise_proposal(proposal.key, source, proposal)
        assert h.store.effect(row['id'])['revision'] == 1
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('consent', [None, 1, 'true'])
def test_confirmation_api_rejects_non_boolean_consent(tmp_path, consent):
    async def check():
        from care_truc.api import CareApi
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        prompt = await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        result = await CareApi(h).handle('confirm_cancel', {'confirmation_id':prompt.confirmation_id,
            'request_id':'yes', 'reply_to':prompt.message_id, 'confirmed':consent}, CUSTOMER)
        assert result.status == 400 and not h.store.effects()
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('text', ['đồng ý', 'tôi đồng ý hủy đơn'])
def test_acceptance_text_bound_to_current_prompt_can_confirm(tmp_path, text):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        prompt = await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        result = await h.handle_message(sid, 'yes', text, CUSTOMER, reply_to=prompt.message_id)
        assert result.status == 'pending_delivery' and len(result.effect_ids) == 1
        assert h.store.db.execute('SELECT status FROM cancellations').fetchone()[0] == 'consumed'
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('text', ['cảm ơn', 'không đồng ý', '"đồng ý"', 'tài xế nói đồng ý', 'hôm qua tôi đồng ý', 'nếu đồng ý thì sao'])
def test_non_authorizing_text_cannot_confirm_even_with_prompt(tmp_path, text):
    async def check():
        h = harness(tmp_path)
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        prompt = await h.handle_message(sid, 'want', 'muốn hủy', CUSTOMER)
        result = await h.handle_message(sid, 'yes', text, CUSTOMER, reply_to=prompt.message_id)
        assert not result.effect_ids and not h.store.effects()
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('text,reason', [('đồ ngu', 'abuse_limit'), ('tôi muốn gặp người', 'customer_requested_human')])
def test_confirmation_still_obeys_human_and_abuse_priority(text, reason):
    from care_truc.policy import CarePolicy
    from care_truc.runtime_types import CustomerEvent, SessionState
    from .helpers import context
    policy = CarePolicy()
    state = SessionState('s', 'run', 'customer', 'o1', abusive_turn_count=2)
    first = policy.evaluate(state, CustomerEvent('prepare_cancel', 'want'), context())
    pending = first.state.pending
    current = replace(first.state, version=pending.version)
    result = policy.evaluate(current, CustomerEvent('confirm_cancel', 'yes', text=text,
        confirmation_id=pending.confirmation_id, reply_to=pending.reply_to, confirmed=True), context())
    assert reason in result.codes and result.state.status == 'handoff_pending'
    assert result.state.pending is None and [p.kind for p in result.proposals] == ['handoff_request']


@pytest.mark.parametrize('legacy_state', ['pending_delivery', 'retry_wait'])
def test_legacy_unsent_cancellation_is_quarantined_on_upgrade(tmp_path, legacy_state):
    async def check():
        import json
        from care_truc.dispatcher import EffectDispatcher
        from .helpers import Gate, ScriptedGateway
        from .test_dispatch_races import pending
        h = harness(tmp_path)
        sid, eid = await pending(h)
        # Persist the pre-Task8 schema and consent-free event, rather than using
        # the current insertion path to authorize a legacy pending effect.
        request = h.store.db.execute("SELECT * FROM requests WHERE client_id='confirm'").fetchone()
        payload = json.loads(request['payload'])
        payload.pop('confirmed')
        payload.pop('reply_to')
        h.store.db.execute('UPDATE requests SET payload=? WHERE id=?', (json.dumps(payload), request['id']))
        h.store.set_effect(eid, state=legacy_state)
        h.store.db.execute('DROP TABLE cancellations')
        h.store.close()
        h = harness(tmp_path)
        gateway = ScriptedGateway()
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        assert gateway.submissions == []
        assert h.store.effect(eid)['state'] == 'blocked'
        assert h.store.effect(eid)['attempts'] == 0
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('legacy_state', ['in_flight', 'needs_reconciliation', 'retry_wait'])
def test_legacy_attempted_cancellation_keeps_receipt_reconciliation(tmp_path, legacy_state):
    async def check():
        from care_truc.dispatcher import EffectDispatcher
        from .helpers import Gate, ScriptedGateway
        from .test_dispatch_races import pending
        h = harness(tmp_path)
        sid, eid = await pending(h)
        gateway = ScriptedGateway()
        gateway.submit_error = TimeoutError()
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        assert h.store.effect(eid)['attempts'] == 1
        h.store.set_effect(eid, state=legacy_state)
        h.store.db.execute('DROP TABLE cancellations')
        h.store.close()
        h = harness(tmp_path)
        assert h.store.effect(eid)['attempts'] == 1
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        assert len(gateway.submissions) == 1
        assert len(gateway.lookups) == 1
        assert h.store.effect(eid)['state'] == 'delivered'
        assert h.store.effect(eid)['outcome'] == 'accepted'
        h.store.close()
    asyncio.run(check())


def test_legacy_uncertain_cancellation_never_resubmits_after_absent_lookup(tmp_path):
    async def check():
        from care_truc.dispatcher import EffectDispatcher
        from .helpers import Gate, ScriptedGateway
        from .test_dispatch_races import pending
        h = harness(tmp_path)
        sid, eid = await pending(h)
        gateway = ScriptedGateway()
        gateway.submit_error = TimeoutError()
        await EffectDispatcher(h, gateway, Gate()).drain_pending()
        gateway.receipts.clear()
        h.store.db.execute('DROP TABLE cancellations')
        h.store.close()
        h = harness(tmp_path)
        dispatcher = EffectDispatcher(h, gateway, Gate())
        for seconds in (0, 1, 5, 20):
            h.clock.advance(seconds)
            await dispatcher.drain_pending()
        assert len(gateway.submissions) == 1 and len(gateway.lookups) == 3
        row = h.store.effect(eid)
        assert row['attempts'] == 1 and row['outcome'] == 'unknown'
        assert row['state'] == 'needs_reconciliation' and row['manual'] == 1
        h.store.close()
    asyncio.run(check())
