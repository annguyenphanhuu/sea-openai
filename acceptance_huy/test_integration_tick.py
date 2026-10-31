"""Actual release integration: automatic contacts, timings and five A1 turns."""
from datetime import datetime
import asyncio
from pathlib import Path

from platform_huy.demo_flow import DemoFlow
from platform_huy.tick import run_tick


ROOT = Path(__file__).resolve().parents[1]
while not (ROOT / 'data/release_main/core_14d.sqlite').exists() and ROOT.parent != ROOT:
    ROOT = ROOT.parent
CORE = ROOT / 'data/release_main/core_14d.sqlite'


def test_actual_tick_automatic_contacts_timings_and_five_customer_turns(tmp_path):
    flow = DemoFlow(CORE, tmp_path / 'runtime/platform.sqlite',
                    datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    try:
        tick = flow.request('next')
        assert tick['now'] == '2026-10-24T14:30:00+07:00'
        assert tick['phase_trace'] == ['A3', 'A2', 'A1']
        assert [row['agent'] for row in tick['tick_timings']] == ['A3', 'A2', 'A1']
        for row in tick['tick_timings']:
            assert row['duration_ms'] >= 0
            assert row['started_at'] <= row['finished_at']
        assert tick['tick_timings'][0]['finished_at'] <= tick['tick_timings'][1]['started_at']
        assert tick['tick_timings'][1]['finished_at'] <= tick['tick_timings'][2]['started_at']
        assert len(tick['contact_queue']) == 30
        assert tick['auto_contact']['opened'] == 30
        assert len(tick['active_chats']) == 30
        assert len(tick['active_chats']) == len({row['principal_id'] for row in tick['active_chats']})
        assert tick['selected_order_id'] == '261021ZS7E76FW'
        assert [row['order_id'] for row in tick['demo_candidates']] == ['261021ZS7E76FW', '261019QY8UDYNZ']
        assert sum(tick['label_counts'].values()) == tick['orders_total']
        assert tick['contact_queue'][0]['payment'] == 'COD'
        assert tick['contact_queue'][0]['cause']['fault_party'] == 'unknown'
        assert tick['chat']['opened_by'] == 'a1'
        session = tick['chat']['session_id']
        reviewed = flow.request('verify-order', {
            'order_id': '261021ZS7E76FW',
            'reason': 'TEST ONLY simulated staff decision; not a finding about source force majeure',
            'responsibility': 'carrier', 'force_majeure': 'absent',
            'evidence_refs': tick['pending_verification']['evidence_refs']})
        assert reviewed['pending_verification']['evidence_ready'] is True
        why = flow.request('chat-say', {'session_id': session, 'text': 'Tại sao đơn hàng trễ?', 'request_id': 'why'})
        assert why['inside']['intent'] == 'ask_why'
        assert why['inside']['used_llm'] is False
        coins = flow.request('chat-say', {'session_id': session, 'text': 'Tôi xin xu', 'request_id': 'coins'})
        assert len(coins['ledger']) == 1, coins['gateway_errors']
        assert coins['ledger'][0]['amount_xu'] == 26000
        cancel = flow.request('chat-say', {'session_id': session, 'text': 'Tôi muốn hủy đơn', 'request_id': 'cancel'})
        assert cancel['cancellations'] == []
        confirm = flow.request('chat-say', {'session_id': session, 'text': 'đồng ý', 'request_id': 'confirm',
                                          'reply_to': cancel['chat']['pending']['reply_to']})
        assert confirm['cancellations'][0]['status'] == 'awaiting_review'
        human = flow.request('chat-say', {'session_id': session, 'text': 'Tôi muốn gặp nhân viên', 'request_id': 'human'})
        assert human['inside']['intent'] == 'ask_human'
        assert len(human['handoffs']) == 1
        assert len(human['ledger']) == 1
        assert len([m for m in human['chat']['messages'] if m['kind'] == 'customer']) == 5
        contacts = len(human['contacts'])
        flow.request('kill')
        stopped = flow.request('next')
        assert stopped['auto_contact']['opened'] == 0
        assert len(stopped['contacts']) == contacts
        assert stopped['guard_alive'] is False
        answered = flow.request('chat-say', {'session_id': session, 'text': 'Tại sao đơn hàng trễ?', 'request_id': 'while-killed'})
        assert answered['reply']
        assert len(answered['ledger']) == 1
        assert len(answered['contacts']) == contacts
    finally:
        flow.close()


def test_actual_lost_contact_never_queues_cancellation(tmp_path):
    flow = DemoFlow(CORE, tmp_path / 'runtime/platform.sqlite',
                    datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    try:
        tick = flow.request('next')
        lost = flow.request('chat-open', {'order_id': '261019QY8UDYNZ'})
        session = lost['chat']['session_id']
        result = flow.request('chat-say', {'session_id': session, 'text': 'Tôi muốn hủy đơn', 'request_id': 'cancel-lost'})
        if result['chat']['pending']:
            result = flow.request('chat-say', {'session_id': session, 'text': 'đồng ý', 'request_id': 'confirm-lost',
                'reply_to': result['chat']['pending']['reply_to']})
        assert result['cancellations'] == []
        assert not any(row['kind'] == 'cancel_request' for row in result['outbox'])
        assert result['inside']['gate'] == 'blocked'
    finally:
        flow.close()


def test_previous_day_active_sessions_do_not_consume_new_contact_budget(tmp_path):
    flow = DemoFlow(CORE, tmp_path / 'runtime/platform.sqlite',
                    datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    try:
        first = flow.request('next')
        assert first['auto_contact']['opened'] == 30
        assert len(first['contacts']) == 30

        async def age_runtime_contacts_only():
            # Simulate persisted contacts from the previous Vietnamese day.
            # Keep every original Care session, effect and successful receipt.
            flow.conn.execute("UPDATE contact_log SET requested_at='2026-10-23T07:30:00.000000Z',"
                              "opened_at='2026-10-23T07:30:00.000000Z',"
                              "guard_checked_at='2026-10-23T07:30:00.000000Z'")

        asyncio.run_coroutine_threadsafe(age_runtime_contacts_only(), flow.loop).result()
        second = flow.request('next')
        assert second['now'] == '2026-10-24T15:00:00+07:00'
        assert second['auto_contact']['reused_sessions'] == 30
        assert second['auto_contact']['opened'] == 30
        assert len(second['contacts']) == 60
        assert len(second['active_chats']) == 60
        assert len({row['principal_id'] for row in second['active_chats']}) == 60
    finally:
        flow.close()


def test_restart_trace_uses_completed_phase_audit_not_a2_snapshot(tmp_path):
    state_path = tmp_path / 'runtime/platform.sqlite'
    start = datetime.fromisoformat('2026-10-24T14:00:00+07:00')
    flow = DemoFlow(CORE, state_path, start)
    try:
        assert flow.request('next')['phase_trace'] == ['A3', 'A2', 'A1']

        async def mark_interrupted_a1_phase():
            # The durable A2 snapshot remains, but A1 did not finish this tick.
            flow.conn.execute("UPDATE demo_tick_timings SET status='failed' WHERE agent='A1'")

        asyncio.run_coroutine_threadsafe(mark_interrupted_a1_phase(), flow.loop).result()
    finally:
        flow.close()
    restarted = DemoFlow(CORE, state_path, start)
    try:
        status = restarted.request('status')
        assert status['now'] == '2026-10-24T14:30:00+07:00'
        assert status['orders_total'] > 0
        assert status['phase_trace'] == ['A3', 'A2']
        assert [row['status'] for row in status['tick_timings']] == ['completed', 'completed', 'failed']
    finally:
        restarted.close()
