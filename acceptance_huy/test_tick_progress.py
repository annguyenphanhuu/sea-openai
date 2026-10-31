"""Concurrent HTTP polling observes real tick boundaries without SQLite threads."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
from threading import Event, Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from platform_huy import tick
from platform_huy.serve_ui import create_server


ROOT = Path(__file__).resolve().parents[1]
while not (ROOT / 'data/release_main/core_14d.sqlite').exists() and ROOT.parent != ROOT:
    ROOT = ROOT.parent


@pytest.mark.parametrize('disconnect', [False, True])
def test_http_polling_reports_real_phase_boundaries_and_rejects_overlapping_next(tmp_path, monkeypatch, disconnect):
    monkeypatch.setenv('LIVE_PRESENTER_KEY', 'progress-test-key')
    server = create_server(core_path=ROOT / 'data/release_main/core_14d.sqlite',
        state_path=tmp_path / 'state.sqlite', integrated=True, port=0,
        start_at=datetime.fromisoformat('2026-10-24T14:00:00+07:00'))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    entered = {phase: Event() for phase in ('A3', 'A2', 'A1')}
    release = {phase: Event() for phase in ('A3', 'A2', 'A1')}
    flow = server.coordinator
    real_snapshot, real_evaluate, real_contact = flow.reader.snapshot, tick.evaluate_tick, flow._auto_contact

    def hold(phase):
        entered[phase].set()
        assert release[phase].wait(30), phase

    def snapshot(*args, **kwargs):
        hold('A3')
        return real_snapshot(*args, **kwargs)

    def evaluate(*args, **kwargs):
        hold('A2')
        return real_evaluate(*args, **kwargs)

    async def contact(*args, **kwargs):
        hold('A1')
        return await real_contact(*args, **kwargs)

    monkeypatch.setattr(flow.reader, 'snapshot', snapshot)
    monkeypatch.setattr(tick, 'evaluate_tick', evaluate)
    monkeypatch.setattr(flow, '_auto_contact', contact)

    def request(path='/api/demo/state', *, post=False, authorized=True, timeout=2):
        headers = {'X-Presenter-Key': 'progress-test-key'} if authorized else {}
        req = Request(base + path, headers=headers, data=b'{}' if post else None)
        try:
            with urlopen(req, timeout=timeout) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        initial = request()[1]
        future = pool.submit(request, '/api/next', post=True, timeout=0.2 if disconnect else 120)
        if disconnect:
            assert entered['A3'].wait(30)
            with pytest.raises(TimeoutError):
                future.result(timeout=5)
        for phase, trace, committed in [('A3', [], []), ('A2', ['A3'], []),
                                       ('A1', ['A3', 'A2'], ['A3', 'A2'])]:
            assert entered[phase].wait(30)
            started = time.perf_counter()
            code, status = request()
            assert time.perf_counter() - started < 1
            assert code == 200
            assert status['busy'] is True
            assert status['current_phase'] == phase
            assert status['phase_trace'] == trace
            assert status['progress']['committed_phases'] == committed
            assert status['now'] == '2026-10-24T14:00:00+07:00'
            assert status['orders_total'] == 0
            assert status['contacts'] == initial['contacts'] == []
            assert status['progress']['from_at'] == '2026-10-24T14:00:00+07:00'
            assert status['progress']['to_at'] == '2026-10-24T14:30:00+07:00'
            if phase in ('A2', 'A1'):
                assert status['progress']['orders_to_assess'] == 6259
            assert [row['agent'] for row in status['timings']] == trace
            assert request(authorized=False)[0] == 401
            assert request('/api/next', post=True) == (409, {'error': 'next_in_progress'})
            release[phase].set()
        if disconnect:
            deadline = time.monotonic() + 120
            while True:
                code, final = request()
                if not final['busy'] or time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        else:
            code, final = future.result(timeout=120)
        assert code == 200
        assert final['busy'] is False
        assert final['phase_trace'] == ['A3', 'A2', 'A1']
        assert final['progress']['status'] == 'completed'
        assert final['now'] == '2026-10-24T14:30:00+07:00'
        assert final['orders_total'] == 6259
        assert final['contact_queue_total'] > 30
        assert final['auto_contact']['opened'] == 30
        assert final['contacts_total'] == 30
        assert [row['agent'] for row in final['timings']] == ['A3', 'A2', 'A1']
        assert all(row['duration_ms'] > 0 for row in final['timings'])
        if disconnect:
            assert final['timings'][0]['duration_ms'] >= 200
        assert sum(row['duration_ms'] for row in final['timings']) <= final['progress']['elapsed_seconds'] * 1000
        assert request()[1]['progress']['run_id'] == final['progress']['run_id']
    finally:
        for gate in release.values():
            gate.set()
        pool.shutdown(wait=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
