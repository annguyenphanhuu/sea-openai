from pathlib import Path
from threading import Thread
import time
import json
import sqlite3
import uuid
import httpx
import pytest

from platform_huy.serve_ui import create_server


def test_voice_http_binds_web_voice_session_and_blocks_coins(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'data/release_main/core_14d.sqlite'
    if not source.is_file():
        pytest.skip('Release input required')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('LIVE_PRESENTER_KEY', 'test-presenter')
    def provider(payload):
        assert payload['session']['model'] == 'gpt-realtime'
        assert payload['session']['tools'][0]['name'] == 'send_to_a1'
        return {'value': 'ek_test', 'expires_at': time.time() + 60}
    server = create_server(core_path=source, state_path=tmp_path/'state.sqlite', integrated=True,
                           port=0, voice_provider=provider)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', headers={'X-Presenter-Key': 'test-presenter'}, timeout=120) as client:
            denied = httpx.post(f'http://127.0.0.1:{server.server_port}/api/voice/state', json={})
            assert denied.status_code == 401
            assert client.post('/api/voice/state', json={}).json()['available'] is True
            state = client.post('/api/next', json={}).json()
            parent = next(chat for chat in state['active_chats'] if chat['status'] == 'active')
            created = client.post('/api/voice/create', json={'session_id': parent['session_id'], 'request_id': uuid.uuid4().hex})
            assert created.status_code == 200, created.text
            token = created.json()
            assert token['client_secret'] == 'ek_test' and 'test-key' not in created.text
            assert token['care_session_id'] != parent['session_id']
            care_path = tmp_path / 'care' / server.coordinator.run_id / 'care.sqlite'
            def session(sid):
                with sqlite3.connect(care_path.as_uri() + '?mode=ro', uri=True) as db:
                    return json.loads(db.execute('SELECT data FROM sessions WHERE id=?', (sid,)).fetchone()[0])
            child = session(token['care_session_id'])
            assert child['channel'] == 'web_voice' and child['opened_by'] == 'customer'
            payload = {'voice_session_id': token['voice_session_id'], 'session_id': token['care_session_id'], 'text': 'Tôi xin xu', 'request_id': 'voice-test-turn'}
            reply = client.post('/api/voice/turn', json=payload)
            assert reply.status_code == 200, reply.text
            assert reply.json()['inside']['channel'] == 'voice'
            assert session(child['session_id'])['turn_count'] == 1
            with sqlite3.connect(care_path.as_uri() + '?mode=ro', uri=True) as db:
                assert db.execute('SELECT count(*) FROM pending_effects WHERE session_id=?', (child['session_id'],)).fetchone()[0] == 0
            retry = client.post('/api/voice/turn', json=payload)
            assert retry.json() == reply.json()
            assert session(child['session_id'])['turn_count'] == 1
            mismatch = client.post('/api/voice/turn', json=dict(payload, session_id=parent['session_id']))
            assert mismatch.status_code == 403
            ordinary = client.get('/api/demo/state', params={'order_id': parent['order_id']}).json()
            assert ordinary['chat']['session_id'] == parent['session_id']
            assert all(chat['session_id'] != child['session_id'] for chat in ordinary['active_chats'])
            client.post('/api/chat/say', json={'session_id': parent['session_id'], 'request_id': 'parent-handoff', 'text': 'Tôi muốn gặp nhân viên'})
            assert client.post('/api/voice/turn', json=dict(payload, request_id='after-handoff')).status_code == 403
            assert client.post('/api/voice/end', json={'voice_session_id': token['voice_session_id']}).status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
