"""Literal financial gate expectations against an actual SQLite runtime."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from contracts.types import Action
from platform_huy.dto import ServerContext, SourceIdentity
from platform_huy.state import bootstrap, canonical, connect_state, utc
from platform_huy.money import execute_action, get_receipt
from platform_huy.state_store import SqliteStateStore


NOW = datetime(2026, 10, 31, 3, tzinfo=timezone.utc)
IDENTITY = SourceIdentity('a' * 64, 'b' * 64, NOW - timedelta(days=14), NOW)


@pytest.fixture
def case(tmp_path):
    conn = connect_state(tmp_path / 'runtime.sqlite')
    bootstrap(conn, run_id='test-run', identity=IDENTITY, start_at=NOW)
    conn.execute('UPDATE demo_clock SET current_at=? WHERE singleton=1', (utc(NOW),))
    conn.execute("INSERT INTO guard_heartbeat VALUES (?,'A3',?,1,'[]')", (utc(NOW), utc(NOW)))
    for feed in ('orders', 'scan_events', 'delivery_attempts'):
        conn.execute('INSERT INTO feed_health VALUES (?,?,?,?,?,?,?)',
                     (feed, utc(NOW), 'trusted', utc(NOW), utc(NOW), utc(NOW), '[]'))
    conn.execute("INSERT INTO contact_log(contact_id,order_id,channel,initiated_by,status,requested_at,opened_at,provider_session_id) VALUES ('chat','o','chat','A1','active',?,?, 'delivered-session')", (utc(NOW), utc(NOW)))
    conn.execute("INSERT INTO customer_messages VALUES ('msg','chat','o','c','text',?,?,?,'late_compensation','rule-v1','a1_transport')", (utc(NOW), utc(NOW), 'Please compensate my late delivery'))
    payload = {
        'schema_version': 1, 'run_id': 'test-run', 'source_identity': json.loads(canonical(IDENTITY)),
        'order': {'order_id': 'o', 'customer_id': 'c', 'seller_id': 's',
                  'guaranteed_date': '2026-10-29', 'items_value_vnd': 239999,
                  'delivered_at': None},
        'responsibility': 'carrier', 'force_majeure': 'absent',
        'history': {'coins': 'not_granted', 'voucher': 'not_granted'},
    }
    conn.execute('INSERT INTO execution_evidence VALUES (?,?,?,?,?,?,?,?,?,?)',
                 ('ev', 'o', 'chat', 'msg', utc(NOW), utc(NOW), 'huy-demo-v1',
                  canonical(payload), hashlib.sha256(canonical(payload).encode()).hexdigest(), 'platform_huy'))
    store = SqliteStateStore(conn, evidence_producers=frozenset({'platform_huy'}),
                             message_recorders=frozenset({'a1_transport'}),
                             request_rule_versions=frozenset({'rule-v1'}))
    context = ServerContext('a1-service', 'a1', 'c', None, frozenset({'actions:coins'}))
    action = Action('a', 'o', 'coins', 11000, 'a1', NOW, 'xu:o', 'ev', False, 'local')
    yield conn, store, context, action, payload
    conn.close()


def update_payload(case, **changes):
    conn, _, _, _, payload = case
    payload.update(changes)
    text = canonical(payload)
    conn.execute('UPDATE execution_evidence SET payload_json=?,sha256=?',
                 (text, hashlib.sha256(text.encode()).hexdigest()))


def run(case, **changes):
    _, store, context, action, _ = case
    return execute_action(replace(action, **changes), store=store, context=context)


def assert_no_money(conn):
    assert conn.execute('SELECT COUNT(*) FROM outbox').fetchone() == (0,)
    assert conn.execute('SELECT COUNT(*) FROM action_receipts').fetchone() == (0,)
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (0,)
    assert conn.execute('SELECT COUNT(*) FROM voucher_ledger').fetchone() == (0,)


def test_grant_and_separate_voucher(case):
    conn, store, context, action, _ = case
    coins = run(case)
    assert (coins.decision, coins.amount_xu, coins.amount_vnd, coins.replayed) == ('succeeded', 11000, None, False)
    voucher = execute_action(replace(action, action_id='v', kind='voucher', source='rule', amount_vnd=10000, idempotency_key='voucher:o'), store=store,
        context=replace(context, principal_id='rule-service', source='rule', capabilities=frozenset({'actions:voucher'})))
    assert (voucher.decision, voucher.amount_xu, voucher.amount_vnd) == ('succeeded', None, 10000)
    assert conn.execute('SELECT amount_xu FROM ledger_new').fetchall() == [(11000,)]
    assert conn.execute('SELECT face_value_vnd FROM voucher_ledger').fetchall() == [(10000,)]
    assert conn.execute('SELECT status FROM outbox ORDER BY kind').fetchall() == [('succeeded',), ('succeeded',)]


@pytest.mark.parametrize('control', ['a3_killed', 'a3_resume_pending', 'proactive_block'])
def test_guard_blocks_before_grant(case, control):
    conn, *_ = case
    conn.execute("INSERT INTO controls VALUES (?,'global','true',?,'human','test')", (control, utc(NOW)))
    result = run(case)
    assert result.decision == 'blocked'
    assert 'proactive_gate_closed' in result.reason_codes
    assert_no_money(conn)
    assert conn.execute('SELECT COUNT(*) FROM incidents').fetchone() == (1,)


@pytest.mark.parametrize('age,allowed', [(30, True), (31, False)])
def test_feed_freshness(case, age, allowed):
    conn, *_ = case
    conn.execute('UPDATE feed_health SET source_timestamp=?', (utc(NOW - timedelta(minutes=age)),))
    assert (run(case).decision == 'succeeded') is allowed


def test_success_retry_replays_even_after_guard_closes(case):
    conn, store, context, action, _ = case
    first = run(case)
    conn.execute('DELETE FROM feed_health')
    conn.execute('DELETE FROM guard_heartbeat')
    replay = execute_action(replace(action, action_id='transport-retry'), store=store, context=context)
    assert replay == replace(first, replayed=True)
    assert get_receipt('xu:o', store=store, context=context) == replay
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (1,)


def test_denial_does_not_reserve_key_and_can_retry(case):
    conn, *_ = case
    update_payload(case, force_majeure='unknown')
    assert run(case).decision == 'blocked'
    assert_no_money(conn)
    update_payload(case, force_majeure='absent')
    assert run(case).decision == 'succeeded'
    assert conn.execute('SELECT COUNT(*) FROM incidents').fetchone() == (1,)


@pytest.mark.parametrize('changes,reason', [
    ({'source': 'rule'}, 'permission_denied'), ({'amount_vnd': 10000}, 'amount_mismatch'),
    ({'amount_vnd': True}, 'validation_error'), ({'idempotency_key': 'run:coins:o'}, 'invalid_idempotency_key'),
    ({'evidence_ref': 'absent'}, 'evidence_missing'), ({'needs_approval': True}, 'approval_required'),
    ({'requested_at': NOW + timedelta(seconds=1)}, 'validation_error'),
])
def test_action_denials(case, changes, reason):
    result = run(case, **changes)
    assert (result.decision, result.reason_codes) == ('blocked', (reason,))
    assert_no_money(case[0])


@pytest.mark.parametrize('field,value', [('responsibility', 'customer'), ('responsibility', 'unknown'), ('force_majeure', 'present'), ('force_majeure', 'unknown'), ('history', {'coins': 'unknown', 'voucher': 'not_granted'}), ('history', {'coins': 'already_granted', 'voucher': 'not_granted'})])
def test_unresolved_or_ineligible_facts_fail_closed(case, field, value):
    update_payload(case, **{field: value})
    assert run(case).decision == 'blocked'
    assert_no_money(case[0])


@pytest.mark.parametrize('statement', [
    "UPDATE customer_messages SET origin='voice_transcript'",
    "UPDATE customer_messages SET request_code=NULL",
    "UPDATE customer_messages SET recorded_by='customer'",
    "UPDATE customer_messages SET request_rule_version='unconfigured'",
    "UPDATE customer_messages SET customer_id='someone-else'",
    "UPDATE contact_log SET initiated_by='customer'",
    "UPDATE contact_log SET status='pending'",
    "UPDATE contact_log SET provider_session_id=NULL",
    "UPDATE execution_evidence SET created_by='customer'",
    "UPDATE execution_evidence SET sha256='tampered'",
    "UPDATE execution_evidence SET assessment_at='2026-10-31T02:30:00.000000Z'",
])
def test_persisted_provenance_required(case, statement):
    case[0].execute(statement)
    assert run(case).decision == 'blocked'
    assert_no_money(case[0])


@pytest.mark.parametrize('date,delivery,allowed', [
    ('2026-10-29', None, True), ('2026-10-30', None, False),
    ('2026-10-29', '2026-10-29T12:00:00+07:00', False),
    ('2026-10-29', '2026-10-31T00:00:00+07:00', True),
    ('2026-10-29', '2026-11-01T00:00:00+07:00', False),
])
def test_vietnam_calendar_and_delivery_stop_lateness(case, date, delivery, allowed):
    order = {**case[4]['order'], 'guaranteed_date': date, 'delivered_at': delivery}
    update_payload(case, order=order)
    assert (run(case).decision == 'succeeded') is allowed


@pytest.mark.parametrize('value,amount', [(None,10000), (0,10000), (199999,10000), (239999,11000), (20000000,1000000), (999999999,1000000)])
def test_amount_literal_boundaries(case, value, amount):
    update_payload(case, order={**case[4]['order'], 'items_value_vnd': value})
    result = run(case, amount_vnd=amount)
    assert (result.decision, result.amount_xu) == ('succeeded', amount)


def test_changed_semantics_and_principal_cannot_replay(case):
    _, store, context, action, _ = case
    assert run(case).decision == 'succeeded'
    assert run(case, amount_vnd=10000).reason_codes == ('idempotency_conflict',)
    other = execute_action(action, store=store, context=replace(context, principal_id='other'))
    assert other.reason_codes == ('idempotency_conflict',)


def test_missing_server_authority_and_cross_customer(case):
    conn, store, context, action, _ = case
    assert execute_action(action, store=store, context=replace(context, capabilities=frozenset())).reason_codes == ('permission_denied',)
    assert execute_action(action, store=store, context=replace(context, customer_id='other')).reason_codes == ('not_found',)
    assert execute_action(action, store=SqliteStateStore(conn), context=context).decision == 'blocked'
    assert_no_money(conn)


@pytest.mark.parametrize('kind,source', [('cancel_request','a1'), ('eta_notice','a1'), ('refund','cancel_reviewer'), ('shipping_fee_refund','cancel_reviewer')])
def test_unimplemented_effects_never_report_success(case, kind, source):
    _, store, context, action, _ = case
    result = execute_action(replace(action, kind=kind, source=source), store=store, context=replace(context, source=source))
    assert result.reason_codes == ('policy_not_configured',)
    assert_no_money(case[0])


def test_failure_rolls_back_every_financial_write(case):
    conn, *_ = case
    conn.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON action_receipts BEGIN SELECT RAISE(ABORT,'receipt failure'); END")
    from platform_huy.dto import PlatformError
    with pytest.raises(PlatformError, match='Runtime state is unavailable'):
        run(case)
    assert_no_money(conn)


def test_known_voucher_history_does_not_consume_coins(case):
    update_payload(case, history={'coins':'not_granted','voucher':'already_granted'})
    assert run(case).decision == 'succeeded'


@pytest.mark.parametrize('age,allowed', [(60, True), (61, False), (90, False), (91, False)])
def test_heartbeat_contract_boundary_with_current_source_health(case, age, allowed):
    conn, *_ = case
    conn.execute('DELETE FROM feed_health')
    conn.execute('DELETE FROM guard_heartbeat')
    heartbeat = utc(NOW - timedelta(minutes=age))
    conn.execute("INSERT INTO guard_heartbeat VALUES (?,'A3',?,1,'[]')", (heartbeat, utc(NOW)))
    for feed in ('orders', 'scan_events', 'delivery_attempts'):
        conn.execute('INSERT INTO feed_health VALUES (?,?,?,?,?,?,?)',
                     (feed, heartbeat, 'trusted', utc(NOW), utc(NOW), utc(NOW), '[]'))
    assert (run(case).decision == 'succeeded') is allowed


def test_concurrent_connections_commit_only_one_grant(case):
    conn, store, context, action, _ = case
    db_path = conn.execute('PRAGMA database_list').fetchone()[2]
    barrier = Barrier(2)

    def submit(action_id):
        other = connect_state(db_path)
        try:
            own_store = SqliteStateStore(other, evidence_producers=store.evidence_producers,
                                        message_recorders=store.message_recorders,
                                        request_rule_versions=store.request_rule_versions)
            barrier.wait(timeout=5)
            return execute_action(replace(action, action_id=action_id), store=own_store, context=context)
        finally:
            other.close()

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(submit, action_id) for action_id in ('concurrent-1', 'concurrent-2')]
        results = [future.result(timeout=10) for future in futures]
    assert [result.decision for result in results] == ['succeeded', 'succeeded']
    assert sorted(result.replayed for result in results) == [False, True]
    assert results[0].ledger_id == results[1].ledger_id
    assert conn.execute('SELECT COUNT(*) FROM outbox').fetchone() == (1,)
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (1,)
    assert conn.execute('SELECT COUNT(*) FROM action_receipts').fetchone() == (1,)


def test_legacy_outbox_without_real_receipt_is_never_success(case):
    conn, *_ = case
    conn.execute("INSERT INTO outbox(action_id,idempotency_key,order_id,kind,amount_vnd,source,evidence_ref,needs_approval,queue,requested_at,available_at) VALUES ('legacy','xu:o','o','coins',11000,'a1','ev',0,'local',?,?)", (utc(NOW), utc(NOW)))
    result = run(case)
    assert (result.decision, result.reason_codes) == ('blocked', ('idempotency_conflict',))
    assert conn.execute('SELECT COUNT(*) FROM ledger_new').fetchone() == (0,)


def test_receipt_replay_does_not_need_changed_business_evidence(case):
    _, store, context, action, _ = case
    first = run(case)
    update_payload(case, force_majeure='present')
    assert execute_action(action, store=store, context=context) == replace(first, replayed=True)


@pytest.mark.parametrize('statement', [
    "UPDATE outbox SET status='pending'",
    "UPDATE action_receipts SET attested_source='rule'",
    "UPDATE action_receipts SET result_json='{}'",
    "DELETE FROM ledger_new",
])
def test_incomplete_or_tampered_success_cannot_replay(case, statement):
    assert run(case).decision == 'succeeded'
    case[0].execute(statement)
    assert run(case).reason_codes == ('idempotency_conflict',)


@pytest.mark.parametrize('changes', [
    {'source_identity': {}}, {'run_id': 'another-run'}, {'schema_version': 999},
    {'order': {'order_id':'o', 'customer_id':'c'}},
])
def test_malformed_or_cross_run_payload_fails_closed(case, changes):
    update_payload(case, **changes)
    assert run(case).decision == 'blocked'
    assert_no_money(case[0])


def test_get_receipt_requires_original_customer_and_capability(case):
    from platform_huy.dto import PlatformError
    _, store, context, _, _ = case
    assert run(case).decision == 'succeeded'
    for other in (replace(context, customer_id='other'), replace(context, capabilities=frozenset())):
        with pytest.raises(PlatformError, match='permission_denied'):
            get_receipt('xu:o', store=store, context=other)


def test_ungranted_key_has_no_recovery_receipt(case):
    _, store, context, _, _ = case
    assert get_receipt('xu:o', store=store, context=context) is None


def test_recovery_checks_original_seller_scope(case):
    from platform_huy.dto import PlatformError
    _, store, context, _, _ = case
    assert run(case).decision == 'succeeded'
    with pytest.raises(PlatformError, match='permission_denied'):
        get_receipt('xu:o', store=store, context=replace(context, seller_id='another-shop'))


def test_recovery_uses_immutable_receipt_scope_not_current_evidence(case):
    _, store, context, _, _ = case
    original = run(case)
    update_payload(case, order={**case[4]['order'], 'customer_id': 'changed-owner'})
    assert get_receipt('xu:o', store=store, context=context) == replace(original, replayed=True)


@pytest.mark.parametrize('closed_offset,message_offset,expected', [
    (-1, 0, 'blocked'), (0, 0, 'succeeded'), (-1, -2, 'succeeded'), (1, 0, 'blocked'),
])
def test_customer_request_belongs_to_contact_lifetime(case, closed_offset, message_offset, expected):
    conn, *_ = case
    opened = utc(NOW - timedelta(minutes=3))
    conn.execute("UPDATE contact_log SET requested_at=?,opened_at=?,status='completed',closed_at=?",
                 (opened, opened, utc(NOW + timedelta(minutes=closed_offset))))
    conn.execute('UPDATE customer_messages SET created_at=?', (utc(NOW + timedelta(minutes=message_offset)),))
    assert run(case).decision == expected
    if expected == 'blocked':
        assert_no_money(conn)
