"""Adapter tests use real A1 and platform SQLite, including the real executor."""
import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import time

import pytest

from care_truc.runtime_types import CareError, EffectProposal, SessionState, canonical, fingerprint
from care_truc.store import MemoryStore
from contracts.types import Action
from platform_huy.dto import ServerContext, SourceIdentity
from platform_huy.state import bootstrap, canonical as platform_json, connect_state, utc
from platform_huy.state_store import SqliteStateStore
from platform_huy.effect_gateway import SqliteEffectGateway


NOW = datetime(2026, 10, 31, 3, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path):
    conn = connect_state(tmp_path / 'platform.sqlite')
    identity = SourceIdentity('a' * 64, 'b' * 64, NOW - timedelta(days=14), NOW)
    bootstrap(conn, run_id='run', identity=identity, start_at=NOW)
    conn.execute('UPDATE demo_clock SET current_at=? WHERE singleton=1', (utc(NOW),))
    conn.execute("INSERT INTO guard_heartbeat VALUES (?,'A3',?,1,'[]')", (utc(NOW), utc(NOW)))
    for feed in ('orders', 'scan_events', 'delivery_attempts'):
        conn.execute('INSERT INTO feed_health VALUES (?,?,?,?,?,?,?)',
                     (feed, utc(NOW), 'trusted', utc(NOW), utc(NOW), utc(NOW), '[]'))
    conn.execute("INSERT INTO contact_log(contact_id,order_id,channel,initiated_by,status,requested_at,opened_at,provider_session_id) VALUES ('contact','o','chat','A1','active',?,?,'local-chat-delivered')", (utc(NOW), utc(NOW)))
    body = 'Tôi xin xu bồi thường'
    conn.execute("INSERT INTO customer_messages VALUES ('message','contact','o','customer','text',?,?,?,'late_compensation','v1','transport')", (utc(NOW), utc(NOW), body))
    facts = dict(schema_version=1, run_id='run', source_identity=json.loads(platform_json(identity)),
                 order=dict(order_id='o', customer_id='customer', seller_id='shop',
                            guaranteed_date='2026-10-29', items_value_vnd=300000, delivered_at=None),
                 responsibility='carrier', force_majeure='absent',
                 history=dict(coins='not_granted', voucher='not_granted'))
    payload = platform_json(facts)
    conn.execute('INSERT INTO execution_evidence VALUES (?,?,?,?,?,?,?,?,?,?)',
                 ('proof', 'o', 'contact', 'message', utc(NOW), utc(NOW), 'huy-demo-v1',
                  payload, hashlib.sha256(payload.encode()).hexdigest(), 'platform'))
    platform = SqliteStateStore(conn, evidence_producers=frozenset({'platform'}),
        message_recorders=frozenset({'transport'}), request_rule_versions=frozenset({'v1'}))
    care = MemoryStore.open(tmp_path / 'care.sqlite')
    state = SessionState('session', 'run', 'customer-login', 'o', 'chat', 'a1', 'contact')
    care.create_session(state, 'opening')
    event = dict(kind='message', request_id='client-request', text=body, reply_to=None, confirmation_id=None)
    action = Action('action', 'o', 'coins', 15000, 'a1', NOW, 'run:coins:o', 'care-proof', False, 'care')
    proposal = EffectProposal('effect', 'run:coins:o', 'session', 'o', 'action_request', canonical(action), 'care-proof')
    care.db.execute("INSERT INTO requests(id,run_id,session_id,principal,client_id,fingerprint,payload,phase,base_version) VALUES ('request','run','session','customer-login','client-request','fixture',?,'committed',0)", (canonical(event),))
    bundle = dict(session=asdict(state), event=event, proposals=[asdict(proposal)])
    care.db.execute("INSERT INTO evidence_bundles VALUES ('care-proof','request',?,'{}')", (canonical(bundle),))
    care.db.execute("INSERT INTO pending_effects(id,run_id,effect_key,session_id,proposal,state,attempts,session_version) VALUES ('effect','run','run:coins:o','session',?,'in_flight',1,0)", (canonical(proposal),))
    context = ServerContext('care-service', 'a1', 'customer', None, frozenset({'actions:coins'}))
    gateway = SqliteEffectGateway(platform, care, context=context,
        customer_principal='customer-login', evidence_bindings={'care-proof': 'proof'})
    yield conn, platform, care, gateway, proposal, context
    care.close()
    conn.close()


def submit(gateway, proposal):
    return asyncio.run(gateway.submit(proposal, deadline=time.monotonic() + 2))


def test_real_executor_receipt_and_retry(setup):
    conn, platform, care, gateway, proposal, context = setup
    first = submit(gateway, proposal)
    assert (first.outcome, first.key, first.effect_id) == ('succeeded', 'run:coins:o', 'effect')
    assert first.payload_hash == fingerprint(proposal.payload)
    assert conn.execute('SELECT idempotency_key,amount_xu FROM ledger_new').fetchall() == [('xu:o', 15000)]
    care.record_receipt(first)
    conn.execute('DELETE FROM feed_health')
    conn.execute('DELETE FROM guard_heartbeat')
    reopened = SqliteEffectGateway(platform, care, context=context,
        customer_principal='customer-login', evidence_bindings={'care-proof': 'proof'})
    receipt = asyncio.run(reopened.lookup(proposal.key, deadline=time.monotonic() + 2))
    assert receipt == first
    assert submit(reopened, proposal) == first
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (1,)


def test_real_guard_denies_without_reserved_key(setup):
    conn, _, _, gateway, proposal, _ = setup
    conn.execute("INSERT INTO controls VALUES ('a3_killed','global','true',?,'human','demo')", (utc(NOW),))
    receipt = submit(gateway, proposal)
    assert receipt.outcome == 'rejected'
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (0,)
    assert conn.execute('SELECT COUNT(*) FROM outbox').fetchone() == (0,)
    assert conn.execute('SELECT COUNT(*) FROM incidents').fetchone() == (1,)
    assert asyncio.run(gateway.lookup(proposal.key, deadline=time.monotonic() + 2)) is None


def test_unpersisted_tampered_proposal_is_rejected(setup):
    conn, _, _, gateway, proposal, _ = setup
    payload = json.loads(proposal.payload)
    payload['amount_vnd'] = 999999
    with pytest.raises(CareError):
        submit(gateway, replace(proposal, payload=canonical(payload)))
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (0,)


def test_platform_text_must_match_actual_a1_request(setup):
    conn, _, _, gateway, proposal, _ = setup
    conn.execute("UPDATE customer_messages SET body='other customer request'")
    with pytest.raises(CareError):
        submit(gateway, proposal)
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (0,)


def test_missing_server_evidence_binding_blocks(setup):
    conn, platform, care, _, proposal, context = setup
    gateway = SqliteEffectGateway(platform, care, context=context,
        customer_principal='customer-login', evidence_bindings={})
    with pytest.raises(CareError):
        submit(gateway, proposal)
    assert conn.execute('SELECT COUNT(*) FROM outbox').fetchone() == (0,)


def test_wrong_authenticated_customer_cannot_use_another_session(setup):
    conn, platform, care, _, proposal, context = setup
    gateway = SqliteEffectGateway(platform, care, context=context,
        customer_principal='other-login', evidence_bindings={'care-proof': 'proof'})
    with pytest.raises(CareError):
        submit(gateway, proposal)
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (0,)


def test_deadline_expired_has_no_effect(setup):
    conn, _, _, gateway, proposal, _ = setup
    with pytest.raises(TimeoutError):
        asyncio.run(gateway.submit(proposal, deadline=time.monotonic() - 1))
    assert conn.execute('SELECT COUNT(*) FROM outbox').fetchone() == (0,)


def test_lookup_without_grant_does_not_claim_success(setup):
    _, _, _, gateway, proposal, _ = setup
    assert asyncio.run(gateway.lookup(proposal.key, deadline=time.monotonic() + 2)) is None


@pytest.mark.parametrize('change', [{'needs_approval': True}, {'queue': 'changed'}, {'confirmation_id': 'other'}])
def test_lookup_rejects_changed_persisted_action_semantics(setup, change):
    _, _, care, gateway, proposal, _ = setup
    assert submit(gateway, proposal).outcome == 'succeeded'
    payload = json.loads(proposal.payload)
    payload.update(change)
    altered = replace(proposal, payload=canonical(payload))
    care.db.execute('UPDATE pending_effects SET proposal=? WHERE id=?', (canonical(altered), proposal.effect_id))
    with pytest.raises(CareError, match='receipt_binding_invalid'):
        asyncio.run(gateway.lookup(proposal.key, deadline=time.monotonic() + 2))
