"""HTTP presenter authorization against the real integrated runtime."""
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json

from platform_huy.serve_ui import create_server


def test_presenter_key_protects_http_state_and_next(tmp_path, monkeypatch):
    monkeypatch.setenv('LIVE_PRESENTER_KEY', 'test-only-presenter-key')
    core = Path(__file__).resolve().parents[1] / 'data/release_main/core_14d.sqlite'
    server = create_server(core_path=core, state_path=tmp_path / 'state.sqlite',
                           integrated=True, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, *, key=None, post=False):
        headers = {} if key is None else {'X-Presenter-Key': key}
        req = Request(base + path, headers=headers, data=b'{}' if post else None)
        try:
            with urlopen(req, timeout=30) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    try:
        assert request('/')[0] == 200
        assert request('/api/demo/state')[0] == 401
        assert request('/api/demo/state', key='wrong')[0] == 401
        assert request('/api/next', post=True)[0] == 401
        code, payload = request('/api/demo/state', key='test-only-presenter-key')
        assert code == 200
        state = json.loads(payload)
        assert state['now'] == '2026-10-24T14:00:00+07:00'
        assert state['contacts'] == []
        assert state['ledger'] == []
        assert request('/api/records?table=ledger_new')[0] == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
