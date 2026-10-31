"""Unified dashboard contract over real HTTP, replay data and runtime audits."""
import hashlib
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from platform_huy.serve_ui import create_server
from platform_huy.a3_demo import release_dir


@pytest.fixture(scope='module')
def dashboard(tmp_path_factory):
    release = release_dir()
    sources = [release / 'core_14d.sqlite', release / 'ops_14d.sqlite']
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in sources]
    server = create_server(core_path=sources[0], ops_path=sources[1],
        state_path=tmp_path_factory.mktemp('dashboard') / 'platform.sqlite',
        integrated=True, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in sources] == before


def call(server, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(f'http://127.0.0.1:{server.server_port}{path}', data=body,
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=120) as response:
        return response.status, response.read()


def test_dashboard_real_state_candidates_routes_and_named_review(dashboard):
    _, body = call(dashboard, '/api/demo/state')
    initial = json.loads(body)
    for name in ('orders', 'tasks', 'chats', 'outbox', 'ledger', 'handoffs', 'timings'):
        assert initial[name] == []
    assert [row['available'] for row in initial['demo_scenarios']] == [False, False, False]
    assert initial['demo_candidates'] == []
    for route in ('/overview', '/contacts', '/chat', '/money'):
        status, page = call(dashboard, route)
        assert status == 200
        assert b'<!doctype html>' in page.lower()
    status, orders_page = call(dashboard, '/orders/?source=api')
    assert status == 200
    assert b'app.js' in orders_page

    _, body = call(dashboard, '/api/next', {})
    state = json.loads(body)
    assert state['now'] == '2026-10-24T14:30:00+07:00'
    assert state['tasks'] == state['contact_queue']
    assert state['chats'] == state['active_chats']
    assert state['timings'] == state['tick_timings']
    assert [row['agent'] for row in state['timings']] == ['A3', 'A2', 'A1']
    assert [row['order_id'] for row in state['demo_scenarios']] == [
        '261021ZS7E76FW', '261019QY8UDYNZ', '2610181FZM7I7I']
    assert [row['order_id'] for row in state['demo_candidates']] == [
        '261021ZS7E76FW', '261019QY8UDYNZ']
    assert state['demo_scenarios'][2]['status'] == 'customer_fault'
    assert state['demo_scenarios'][2]['contact_available'] is False
    assert state['orders'][0]['lsr_exempt'] is True
    assert state['orders'][0]['lsr_exemption']

    _, body = call(dashboard, '/api/demo/state?order_id=2610181FZM7I7I')
    selected = json.loads(body)
    actual = next(row for row in selected['orders'] if row['order_id'] == '2610181FZM7I7I')
    assert actual['status'] == 'customer_fault'
    assert actual['lsr_exempt'] is False
    assert selected['pending_verification']['responsibility'] == 'customer'
    assert selected['chat'] is None
    with pytest.raises(HTTPError) as failure:
        call(dashboard, '/api/chat/open', {'order_id': '2610181FZM7I7I'})
    assert failure.value.code == 409
    assert json.loads(failure.value.read())['error'] == 'order_not_in_contact_queue'

    _, body = call(dashboard, '/api/orders/verify', {
        'order_id': '261021ZS7E76FW', 'staff_name': ' Huy Dashboard Test ',
        'reason': 'TEST ONLY simulated staff verification for audit contract',
        'responsibility': 'carrier', 'force_majeure': 'absent',
        'evidence_refs': state['pending_verification']['evidence_refs']})
    assert json.loads(body)['pending_verification']['evidence_ready'] is True
    _, body = call(dashboard, '/api/records?table=eligibility_reviews')
    reviews = json.loads(body)['rows']
    assert len(reviews) == 1
    assert reviews[0]['reviewed_by'] == 'Huy Dashboard Test'


@pytest.mark.parametrize('staff_name', ['', '   ', 7, None])
def test_dashboard_rejects_invalid_explicit_staff_identity(dashboard, staff_name):
    with pytest.raises(HTTPError) as failure:
        call(dashboard, '/api/orders/verify', {
            'order_id': '261021ZS7E76FW', 'staff_name': staff_name,
            'reason': 'TEST ONLY invalid identity', 'responsibility': 'carrier',
            'force_majeure': 'absent', 'evidence_refs': ['core:orders:261021ZS7E76FW']})
    assert failure.value.code == 400
    assert json.loads(failure.value.read())['error'] == 'staff_name_required'
