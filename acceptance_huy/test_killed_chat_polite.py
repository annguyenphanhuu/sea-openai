"""Actual HTTP: a killed guard pauses benefits without breaking existing chat."""
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from platform_huy.serve_ui import create_server
from platform_huy.a3_demo import release_dir


def test_killed_existing_chat_is_polite_and_creates_no_effect(tmp_path):
    release = release_dir()
    server = create_server(core_path=release / 'core_14d.sqlite',
                           ops_path=release / 'ops_14d.sqlite',
                           state_path=tmp_path / 'runtime.sqlite', integrated=True, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def post(path, body=None):
        request = Request(base + path, data=json.dumps(body or {}).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=120) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    try:
        assert post('/api/next')[0] == 200
        status, opened = post('/api/chat/open', {'order_id': '261021ZS7E76FW'})
        assert status == 200
        session = opened['chat']['session_id']
        assert post('/api/orders/verify', {
            'order_id': '261021ZS7E76FW',
            'reason': 'TEST ONLY: simulated staff review for killed-chat integration',
            'responsibility': 'carrier', 'force_majeure': 'absent',
            'evidence_refs': opened['pending_verification']['evidence_refs']})[0] == 200
        status, stopped = post('/api/a3/kill')
        assert status == 200
        status, paused = post('/api/chat/say', {
            'session_id': session, 'text': 'Tôi xin xu', 'request_id': 'paused-coins'})
        assert status == 200
        assert 'đang tạm dừng ưu đãi' in paused['reply']
        assert paused['turn_result']['text'] == paused['reply']
        assert paused['chat']['messages'][-1]['text'] == paused['reply']
        assert paused['inside']['gate'] == 'blocked'
        assert paused['turn_result']['effect_ids'] == []
        assert paused['ledger_total'] == 0
        assert paused['outbox_total'] == 0
        assert paused['contacts'] == stopped['contacts']
        assert paused['inbox'] == stopped['inbox']
        status, replayed = post('/api/chat/say', {
            'session_id': session, 'text': 'Tôi xin xu', 'request_id': 'paused-coins'})
        assert status == 200
        assert replayed['turn_result'] == paused['turn_result']
        assert replayed['chat']['messages'] == paused['chat']['messages']
        status, blocked = post('/api/chat/open', {'order_id': '261021ZS7E76FW'})
        assert status == 409
        assert blocked['error'] == 'proactive_blocked'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
