"""Real release -> A3 -> A2 -> A1 coordinator acceptance checks."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime
from pathlib import Path

from platform_huy.demo_flow import DemoFlow
from platform_huy import sysguard


CORE = Path(__file__).resolve().parents[1]
while not (CORE / 'data/release_main/core_14d.sqlite').exists() and CORE.parent != CORE:
    CORE = CORE.parent
CORE = CORE / 'data/release_main/core_14d.sqlite'


def test_actual_release_next_real_a1_four_customer_turns(tmp_path):
    flow = DemoFlow(CORE, tmp_path / 'runtime/platform.sqlite',
                    datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    try:
        initial = flow.request('status')
        assert initial['now'] == '2026-10-24T14:00:00+07:00'
        assert initial['guard_alive'] is False
        tick = flow.request('next')
        assert tick['now'] == '2026-10-24T14:30:00+07:00'
        assert tick['phase_trace'] == ['A3', 'A2', 'A1']
        assert tick['proactive_allowed'] is True
        assert '261021ZS7E76FW' in [row['order_id'] for row in tick['contact_queue']]
        opened = flow.request('chat-open', {'order_id': '261021ZS7E76FW'})
        session = opened['chat']['session_id']
        assert opened['chat']['opened_by'] == 'a1'
        assert opened['chat']['effects'][0]['outcome'] == 'succeeded'
        assert opened['pending_verification']['order']['items_value_vnd'] == 525000
        assert opened['pending_verification']['order']['delivered_at'] is None
        assert opened['pending_verification']['coin_quote'] == 26000
        first = flow.request('chat-say', {'session_id': session, 'text': 'Tại sao đơn hàng trễ?', 'request_id': 'turn-1'})
        assert first['turn_result']['intent'] == 'ask_why'
        # No audit review has happened. Real A1 and the financial gate fail closed.
        second = flow.request('chat-say', {'session_id': session, 'text': 'Tôi xin xu', 'request_id': 'turn-2'})
        assert second['ledger'] == []
        assert second['turn_result']['codes'] == ['coins_ineligible']
        third = flow.request('chat-say', {'session_id': session, 'text': 'Tôi muốn hủy đơn', 'request_id': 'turn-3'})
        assert third['turn_result']['confirmation_id']
        assert third['outbox'] == []
        fourth = flow.request('chat-say', {'session_id': session, 'text': 'đồng ý', 'request_id': 'turn-4',
                                         'reply_to': third['chat']['pending']['reply_to']})
        assert len(fourth['cancellations']) == 1, fourth['gateway_errors']
        assert fourth['cancellations'][0]['status'] == 'awaiting_review'
        assert fourth['ledger'] == []
        assert fourth['now'] == '2026-10-24T14:30:00+07:00'
        assert len([m for m in fourth['chat']['messages'] if m['kind'] == 'customer']) == 4
    finally:
        flow.close()


def test_explicit_simulated_staff_review_real_money_and_four_turns(tmp_path):
    """Staff input exercises review handling; it is not a source FM finding."""
    flow = DemoFlow(CORE, tmp_path / 'runtime/platform.sqlite',
                    datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    try:
        flow.request('next')
        opened = flow.request('chat-open', {'order_id': '261021ZS7E76FW'})
        session = opened['chat']['session_id']
        reviewed = flow.request('verify-order', {
            'order_id': '261021ZS7E76FW',
            'reason': 'TEST ONLY: simulated authorized staff decision for executor integration',
            'responsibility': 'carrier', 'force_majeure': 'absent',
            'evidence_refs': opened['pending_verification']['evidence_refs']})
        assert reviewed['pending_verification']['evidence_ready'] is True
        assert reviewed['orders'][0]['fault_party'] == 'unknown'
        first = flow.request('chat-say', {'session_id': session, 'text': 'Tại sao đơn hàng trễ?', 'request_id': 'why'})
        assert first['turn_result']['intent'] == 'ask_why'
        second = flow.request('chat-say', {'session_id': session, 'text': 'Tôi xin xu', 'request_id': 'coins'})
        assert len(second['ledger']) == 1, second['gateway_errors']
        assert second['ledger'][0]['amount_xu'] == 26000
        assert second['ledger'][0]['idempotency_key'] == 'xu:261021ZS7E76FW'
        repeated = flow.request('chat-say', {'session_id': session, 'text': 'Tôi xin xu', 'request_id': 'coins'})
        assert len(repeated['ledger']) == 1
        third = flow.request('chat-say', {'session_id': session, 'text': 'Tôi muốn hủy đơn', 'request_id': 'cancel'})
        assert third['cancellations'] == []
        fourth = flow.request('chat-say', {'session_id': session, 'text': 'đồng ý', 'request_id': 'confirm',
                                         'reply_to': third['chat']['pending']['reply_to']})
        assert len(fourth['cancellations']) == 1, fourth['gateway_errors']
        assert fourth['cancellations'][0]['status'] == 'awaiting_review'
        assert len(fourth['ledger']) == 1
        assert len(fourth['outbox']) == 2
        assert fourth['chat']['effects'][-1]['outcome'] == 'awaiting_approval'
        assert fourth['now'] == '2026-10-24T14:30:00+07:00'
        assert len([m for m in fourth['chat']['messages'] if m['kind'] == 'customer']) == 4
    finally:
        flow.close()


def test_threaded_requests_share_one_business_clock(tmp_path):
    flow = DemoFlow(CORE, tmp_path / 'runtime/platform.sqlite',
                    datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: flow.request('next'), range(2)))
        assert sorted(row['now'] for row in results) == [
            '2026-10-24T14:30:00+07:00', '2026-10-24T15:00:00+07:00']
        stopped = flow.request('kill')
        assert stopped['guard_alive'] is False
        assert stopped['proactive_allowed'] is False
        assert flow.request('revive')['guard_alive'] is False
        assert flow.request('next')['guard_alive'] is True
    finally:
        flow.close()


def test_kill_after_async_gate_prevents_actual_web_inbox_delivery(tmp_path):
    flow = DemoFlow(CORE, tmp_path / 'runtime/platform.sqlite',
                    datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    try:
        async def install_guard_race():
            gate = flow.care.dispatcher.gate
            original = gate.check

            async def kill_after_check(proposal, ctx, *, deadline):
                decision = await original(proposal, ctx, deadline=deadline)
                assert decision.allowed is True
                sysguard.kill(flow.conn)
                return decision

            gate.check = kill_after_check

        asyncio.run_coroutine_threadsafe(install_guard_race(), flow.loop).result()
        opened = flow.request('next')
        assert opened['guard_alive'] is False
        assert opened['inbox'] == []
        assert opened['contacts'] == []
        assert opened['chat']['effects'][0]['outcome'] == 'unknown'
        assert opened['gateway_errors'][0]['code'] == 'proactive_blocked'
    finally:
        flow.close()
