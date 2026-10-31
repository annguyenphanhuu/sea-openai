"""Real HTTP integration of Nguyen's unchanged UI and the A2 handoff."""
import json
from pathlib import Path
import sqlite3
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from platform_huy.serve_ui import create_server


@pytest.fixture(scope='module')
def orders_server(tmp_path_factory):
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / 'data/release_main/core_14d.sqlite').is_file())
    server = create_server(core_path=root / 'data/release_main/core_14d.sqlite',
                           ops_path=root / 'data/release_main/ops_14d.sqlite',
                           state_path=tmp_path_factory.mktemp('orders-http') / 'state.sqlite',
                           integrated=True, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def get(base, path):
    return urlopen(base + path, timeout=120)


def test_orders_serves_original_ui_in_api_mode_and_assets(orders_server):
    base, _ = orders_server
    ui = Path(__file__).resolve().parents[1] / 'logistics_an_nguyen/ui'
    with get(base, '/orders') as response:
        assert response.status == 200
        assert response.url == base + '/orders/?source=api'
        assert response.read() == (ui / 'index.html').read_bytes()
    for name in ('styles.css', 'app.js', 'data.mjs'):
        with get(base, '/orders/' + name) as response:
            assert response.status == 200
            assert response.read() == (ui / name).read_bytes()
            if name == 'data.mjs':
                assert response.headers.get_content_type() == 'text/javascript'
    with get(base, '/') as response:
        html = response.read().decode('utf-8')
        assert 'Danh sách đơn' in html
        assert 'href="/orders"' in html
    for path in ('/orders/__main__.py', '/orders/README.md', '/orders/../demo_flow.py'):
        with pytest.raises(HTTPError) as error:
            get(base, path)
        assert error.value.code == 404


def test_orders_api_reads_actual_a2_handoff_and_state_has_display_keys(orders_server):
    base, server = orders_server
    with urlopen(Request(base + '/api/next', data=b'{}',
                         headers={'Content-Type': 'application/json'}), timeout=120) as response:
        assert response.status == 200
    with get(base, '/api/orders') as response:
        payload = json.load(response)
    assert payload['payload_version'] == 'a2_order_list_v1'
    assert payload['tick_at'] == '2026-10-24T07:30:00.000000Z'
    assert len(payload['orders']) > 20
    with sqlite3.connect(f'{server.coordinator.state_path.as_uri()}?mode=ro', uri=True) as db:
        saved = json.loads(db.execute('SELECT payload FROM demo_a2_handoff WHERE singleton=1').fetchone()[0])
    assert payload == saved
    by_id = {row['order_id']: row for row in payload['orders']}
    assert '261021ZS7E76FW' in by_id
    with get(base, '/api/demo/state') as response:
        state = json.load(response)
    assert state['orders']
    required = {'order_id', 'status', 'cause', 'fault_party', 'late_days', 'payment',
                'cod_refusal_risk', 'guaranteed_date', 'revised_eta', 'evidence_ref'}
    for index, row in enumerate(state['orders']):
        assert required <= row.keys()
        original = by_id[row['order_id']]
        for field in required - {'evidence_ref', 'cod_refusal_risk'}:
            assert row[field] == original[field]
        assert row['evidence_ref'] == f'#/orders/{index}/evidence'
        assert row['evidence'] == original['evidence']
        assert row['cod_refusal_risk'] in (None, 'medium', 'high')
        if row['cod_refusal_risk'] is not None:
            assert 'cod_refusal_risk:' + row['cod_refusal_risk'] in original['reason_codes']


def test_orders_cookie_is_read_only_and_requires_presenter_key(tmp_path, monkeypatch):
    monkeypatch.setenv('LIVE_PRESENTER_KEY', 'orders-test-presenter-only')
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / 'data/release_main/core_14d.sqlite').is_file())
    server = create_server(core_path=root / 'data/release_main/core_14d.sqlite',
                           ops_path=root / 'data/release_main/ops_14d.sqlite',
                           state_path=tmp_path / 'state.sqlite', integrated=True, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with pytest.raises(HTTPError) as error:
            get(base, '/api/orders')
        assert error.value.code == 401
        with urlopen(Request(base + '/api/demo/state',
                             headers={'X-Presenter-Key': 'orders-test-presenter-only'})) as response:
            cookie = response.headers['Set-Cookie']
        assert 'HttpOnly' in cookie
        assert 'SameSite=Strict' in cookie
        assert 'Path=/api/orders' in cookie
        credential = cookie.split(';', 1)[0]
        with urlopen(Request(base + '/api/orders', headers={'Cookie': credential})) as response:
            payload = json.load(response)
        assert payload['orders'] == []
        assert payload['payload_version'] == 'a2_order_list_v1'
        for path, data in (('/api/demo/state', None), ('/api/next', b'{}')):
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + path, data=data, headers={'Cookie': credential}))
            assert error.value.code == 401
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/orders', headers={'Cookie': 'orders_presenter=invalid'}))
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
