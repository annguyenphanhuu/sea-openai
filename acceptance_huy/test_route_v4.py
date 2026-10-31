"""V4 route behavior against actual release inputs and local execution receipts."""
import asyncio
import json
from pathlib import Path
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import httpx

from platform_huy.serve_ui import create_server

ROOT = Path(__file__).resolve().parents[1]
while not (ROOT / 'data/release_main/core_14d.sqlite').exists() and ROOT.parent != ROOT:
    ROOT = ROOT.parent


@pytest.fixture
def running(tmp_path, monkeypatch, request):
    monkeypatch.setenv('LIVE_PRESENTER_KEY', 'route-v4-test-key')
    server = create_server(core_path=ROOT / 'data/release_main/core_14d.sqlite',
        state_path=tmp_path / 'original/platform.sqlite', integrated=True, port=0,
        selector=getattr(request, 'param', None))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(path, payload=None, *, key='route-v4-test-key'):
        headers = {'Content-Type': 'application/json'}
        if key is not None:
            headers['X-Presenter-Key'] = key
        req = Request(f'http://127.0.0.1:{server.server_port}' + path,
            data=json.dumps(payload or {}).encode(), headers=headers)
        try:
            with urlopen(req, timeout=120) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    try:
        yield server, post
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def opened(post, *, verify=False):
    code, tick = post('/api/next')
    assert code == 200
    assert tick['selected_order_id'] == '261021ZS7E76FW'
    if verify:
        code, review = post('/api/orders/verify', {
            'order_id': '261021ZS7E76FW', 'responsibility': 'carrier', 'force_majeure': 'absent',
            'reason': 'TEST ONLY: simulated staff review for route V4',
            'evidence_refs': tick['pending_verification']['evidence_refs']})
        assert code == 200 and review['pending_verification']['evidence_ready'] is True
    return tick['chat']['session_id']


def test_den_di_reports_actual_same_turn_receipt_and_not_old_grant(running):
    server, post = running
    session = opened(post, verify=True)
    payload = {'session_id': session, 'text': 'đền đi', 'request_id': 'grant'}
    code, result = post('/api/chat/say', payload)
    assert code == 200
    assert result['ledger_total'] == 1
    assert result['ledger'][0]['amount_xu'] == 26000
    assert result['reply'].endswith('Mình đã tặng bạn 26.000 xu vào ví để xin lỗi')
    assert result['chat']['messages'][-1]['text'] == result['reply']
    assert result['turn_result']['text'] == result['reply']
    assert post('/api/chat/say', payload)[1]['reply'] == result['reply']
    code, repeated = post('/api/chat/say', {
        'session_id': session, 'text': 'đền thêm', 'request_id': 'more'})
    assert code == 200 and repeated['ledger_total'] == 1
    assert 'Mình đã tặng' not in repeated['reply']


@pytest.mark.parametrize('confirmation', ['chắc', 'ok', 'đồng ý'])
def test_typed_confirmation_binds_current_pending_and_retries(running, confirmation):
    _, post = running
    session = opened(post)
    code, pending = post('/api/chat/say', {
        'session_id': session, 'text': 'tôi muốn hủy đơn', 'request_id': 'cancel'})
    assert code == 200 and pending['chat']['pending'] is not None
    payload = {'session_id': session, 'text': confirmation, 'request_id': 'confirm'}
    code, confirmed = post('/api/chat/say', payload)
    assert code == 200
    assert len(confirmed['cancellations']) == 1
    assert confirmed['cancellations'][0]['status'] == 'awaiting_review'
    assert confirmed['chat']['pending'] is None
    code, retry = post('/api/chat/say', payload)
    assert code == 200 and retry['turn_result'] == confirmed['turn_result']


def test_unverified_den_them_has_actual_lateness_and_no_success(running):
    _, post = running
    session = opened(post)
    code, reply = post('/api/chat/say', {
        'session_id': session, 'text': 'đền thêm', 'request_id': 'unverified'})
    assert code == 200
    assert reply['reply'] == 'Đơn trễ 2 ngày , mình đang kiểm tra lại để đền bù , vài phút nữa bạn hỏi lại giúp'
    assert reply['ledger_total'] == 0 and reply['outbox_total'] == 0


def test_handoff_reports_transfer_after_dispatch(running):
    _, post = running
    session = opened(post)
    code, reply = post('/api/chat/say', {
        'session_id': session, 'text': 'cho gặp nhân viên', 'request_id': 'human'})
    assert code == 200 and len(reply['handoffs']) == 1
    assert reply['reply'] == 'Mình đã chuyển cho nhân viên , bạn sẽ được liên hệ sớm'


def test_killed_chat_is_http200_exact_pause_and_keeps_information(running):
    _, post = running
    session = opened(post, verify=True)
    assert post('/api/a3/kill')[0] == 200
    code, paused = post('/api/chat/say', {
        'session_id': session, 'text': 'đền đi', 'request_id': 'paused'})
    assert code == 200
    assert paused['reply'] == 'Hệ thống đang tạm dừng ưu đãi để kiểm tra , mình vẫn hỗ trợ thông tin đơn'
    assert paused['ledger_total'] == 0 and paused['outbox_total'] == 0
    assert paused['turn_result']['effect_ids'] == []
    code, info = post('/api/chat/say', {
        'session_id': session, 'text': 'tại sao trễ', 'request_id': 'info'})
    assert code == 200 and 'Ngày giao cam kết' in info['reply']


def test_reset_requires_key_creates_separate_fresh_runtime_preserves_old(running):
    server, post = running
    opened(post, verify=True)
    old_path = server.coordinator.state_path
    old_run = server.coordinator.run_id
    class Selector:
        supports_deadlines = True

        async def select(self, context, *, deadline):
            raise AssertionError('Reset must not request phrase selection')

    selector = Selector()
    server.coordinator.selector = selector
    assert post('/api/reset', key=None)[0] == 401
    assert post('/api/reset', key='wrong')[0] == 401
    code, fresh = post('/api/reset')
    assert code == 200
    assert fresh['now'] == '2026-10-24T14:00:00+07:00'
    assert fresh['contacts_total'] == 0 and fresh['ledger_total'] == 0
    assert fresh['active_chats'] == [] and fresh['orders_total'] == 0
    assert fresh['busy'] is False and fresh['phase_trace'] == []
    assert server.coordinator.state_path != old_path
    assert server.coordinator.run_id != old_run
    assert server.coordinator.selector is selector
    with sqlite3.connect(old_path) as db:
        assert db.execute('SELECT count(*) FROM contact_log').fetchone()[0] == 30
    code, restarted = post('/api/next')
    assert code == 200 and restarted['now'] == '2026-10-24T14:30:00+07:00'
    assert restarted['contacts_total'] == 30
    assert restarted['ledger_total'] == 0


def test_reset_rejects_running_next(running):
    server, post = running
    flow = server.coordinator
    entered, release = threading.Event(), threading.Event()
    original = flow._next

    async def delayed_next():
        entered.set()
        await asyncio.to_thread(release.wait, 30)
        await original()

    flow._next = delayed_next
    result = []
    thread = threading.Thread(target=lambda: result.append(post('/api/next')))
    thread.start()
    try:
        assert entered.wait(5)
        code, rejected = post('/api/reset')
        assert code == 409 and rejected['error'] == 'next_in_progress'
    finally:
        release.set()
        thread.join(timeout=120)
    assert result[0][0] == 200


def test_affirmative_without_current_confirmation_never_queues_cancel(running):
    _, post = running
    session = opened(post)
    code, ordinary = post('/api/chat/say', {
        'session_id': session, 'text': 'ok', 'request_id': 'no-pending'})
    assert code == 200 and ordinary['cancellations'] == []
    assert post('/api/chat/say', {
        'session_id': session, 'text': 'tôi muốn hủy đơn', 'request_id': 'cancel'})[0] == 200
    assert post('/api/chat/say', {
        'session_id': session, 'text': 'tại sao trễ', 'request_id': 'intervening'})[0] == 200
    code, stale = post('/api/chat/say', {
        'session_id': session, 'text': 'chắc', 'request_id': 'stale-confirm'})
    assert code == 200 and stale['cancellations'] == []
    assert 'cancel_confirmation_invalid' in stale['turn_result']['codes']


def test_failed_reset_keeps_existing_runtime_usable(running, monkeypatch):
    server, post = running
    flow = server.coordinator
    old_path = flow.state_path
    old_run = flow.run_id

    async def cannot_initialize():
        raise OSError('TEST ONLY: new runtime initialization unavailable')

    monkeypatch.setattr(flow, '_start', cannot_initialize)
    assert post('/api/reset')[0] == 503
    assert flow.state_path == old_path and flow.run_id == old_run
    code, killed = post('/api/a3/kill')
    assert code == 200 and killed['guard_alive'] is False


class UnavailableSelector:
    supports_deadlines = True
    natural_replies = True

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    async def select(self, context, *, deadline):
        self.calls += 1
        if self.outcome == 'timeout':
            raise TimeoutError('TEST ONLY: model deadline exceeded')
        return b'' if self.outcome == 'empty' else b'{"template":"invented unapproved claim"}'


@pytest.mark.parametrize('running', [UnavailableSelector('empty'), UnavailableSelector('timeout'),
                                    UnavailableSelector('rejected')], indirect=True)
def test_model_failure_nonseed_want_more_verify_and_actual_grant(running):
    server, post = running
    code, tick = post('/api/next')
    assert code == 200
    session = next(row['session_id'] for row in tick['active_chats']
                   if row['order_id'] == '2610197T6ZKT73')
    code, fallback = post('/api/chat/say', {
        'session_id': session, 'text': 'tại sao trễ', 'request_id': 'model-failure'})
    assert code == 200 and fallback['inside']['intent'] == 'ask_why'
    assert server.coordinator.selector.calls == 1
    assert any(code in fallback['turn_result']['codes'] for code in ('model_timeout', 'model_output_rejected'))
    code, pending = post('/api/chat/say', {
        'session_id': session, 'text': 'đền thêm', 'request_id': 'pending-evidence'})
    assert code == 200 and pending['inside']['intent'] == 'want_more'
    assert pending['reply'] == 'Đơn trễ 2 ngày , mình đang kiểm tra lại để đền bù , vài phút nữa bạn hỏi lại giúp'
    assert pending['pending_verification']['order']['order_id'] == '2610197T6ZKT73'
    assert pending['pending_verification']['requires_verification'] is True
    assert pending['pending_verification']['evidence_ready'] is False
    assert pending['ledger_total'] == 0 and pending['outbox_total'] == 0
    assert server.coordinator.selector.calls == 1
    code, verified = post('/api/orders/verify', {
        'order_id': '2610197T6ZKT73', 'responsibility': 'carrier', 'force_majeure': 'absent',
        'reason': 'TEST ONLY: simulated staff review after model failure on non-seed order',
        'evidence_refs': pending['pending_verification']['evidence_refs']})
    assert code == 200 and verified['pending_verification']['evidence_ready'] is True
    code, granted = post('/api/chat/say', {
        'session_id': session, 'text': 'đền đi', 'request_id': 'actual-grant'})
    assert code == 200 and granted['ledger_total'] == 1
    assert granted['ledger'][0]['order_id'] == '2610197T6ZKT73'
    assert granted['ledger'][0]['amount_xu'] == 34000
    assert granted['ledger'][0]['idempotency_key'] == 'xu:2610197T6ZKT73'
    assert granted['reply'].endswith('Mình đã tặng bạn 34.000 xu vào ví để xin lỗi')


@pytest.mark.parametrize('natural', [False, True])
def test_selector_uses_approved_low_reasoning_and_300_token_budget(natural):
    from care_truc.openai_selector import OpenAIPhraseSelector
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        assert request.url.path == '/v1/chat/completions'
        content = {'segments': ['Chào bạn!']} if natural else {'phrase_id': 'clarify'}
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(content)}}]})

    selector = OpenAIPhraseSelector('test-only-key', transport=httpx.MockTransport(respond))
    context = {'mode': 'grounded_reply', 'topic': 'greeting', 'slots': {}} if natural else {'allowed_ids': ['clarify']}
    asyncio.run(selector.select(json.dumps(context).encode(), deadline=time.monotonic() + 10))
    assert captured[0]['max_completion_tokens'] == 300
    assert captured[0]['reasoning_effort'] == 'low'


def test_nonreasoning_fallback_omits_unsupported_reasoning_parameter():
    from care_truc.openai_selector import OpenAIPhraseSelector
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': '{"phrase_id":"clarify"}'}}]})

    selector = OpenAIPhraseSelector('test-only-key', model='gpt-4.1-mini',
                                  transport=httpx.MockTransport(respond))
    asyncio.run(selector.select(b'{"allowed_ids":["clarify"]}', deadline=time.monotonic() + 10))
    assert captured[0]['model'] == 'gpt-4.1-mini'
    assert captured[0]['max_completion_tokens'] == 300
    assert 'reasoning_effort' not in captured[0]
