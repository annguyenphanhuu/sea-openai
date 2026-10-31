"""Opt-in real-browser rehearsal; all mutations use an isolated release-fed runtime."""

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

import pytest

from platform_huy.serve_ui import create_server


ROOT = Path(__file__).resolve().parents[1]
VN = timezone(timedelta(hours=7))


def read_json(url: str) -> dict:
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def presenter_summary(url: str) -> dict:
    state = read_json(url + '/api/runtime')
    return {key: state[key] for key in (
        'now', 'guard_alive', 'proactive_allowed', 'orders_total',
        'ledger_total', 'outbox_total', 'active_chats', 'cancellations', 'handoffs',
    )}


def hashes() -> dict[str, str]:
    return {name: sha256((ROOT / 'data/release_main' / name).read_bytes()).hexdigest()
            for name in ('core_14d.sqlite', 'ops_14d.sqlite')}


@pytest.mark.skipif(os.environ.get('SEA_DEMO_3000') != '1',
                    reason='Opt in with SEA_DEMO_3000=1; requires installed frontend/browser and live A1 key')
def test_demo_3000_browser_rehearsal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replay all three scripts through UI and verify committed platform effects."""
    from care_truc.openai_selector import selector_from_env
    from platform_huy.llm import load_openai_env

    stamp = datetime.now(VN).strftime('%Y%m%d-%H%M%S-%f')
    output = ROOT / 'runs' / f'demo-3000-{stamp}'
    output.mkdir(parents=True)
    print(f'Artifacts: {output}', flush=True)
    presenter_url = os.environ.get('SEA_PRESENTER_URL', 'http://127.0.0.1:3000')
    before = presenter_summary(presenter_url)
    source_before = hashes()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    metadata = {'checked_at': datetime.now(VN).isoformat(), 'revision': revision,
                'python': sys.version.split()[0], 'presenter_url': presenter_url,
                'presenter_before': before, 'source_hashes_before': source_before}
    server = None
    thread = None
    process = None
    log = None
    try:
        load_openai_env(ROOT / '.env')
        selector = selector_from_env()
        assert selector is not None, 'A live A1 key is required; do not label fallback-only testing as LLM proof'
        monkeypatch.delenv('LIVE_PRESENTER_KEY', raising=False)
        server = create_server(core_path=ROOT / 'data/release_main/core_14d.sqlite',
                               ops_path=ROOT / 'data/release_main/ops_14d.sqlite',
                               state_path=output / 'state.sqlite', integrated=True,
                               port=0, selector=selector)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        backend = f'http://127.0.0.1:{server.server_port}'
        # An ignored descendant resolves existing node_modules through ancestors,
        # including on Windows filesystems that do not support junctions.
        app = ROOT / 'frontend/runs' / output.name
        app.mkdir(parents=True)
        tracked = subprocess.check_output(['git', 'ls-files', '-z', 'frontend'], cwd=ROOT)
        for raw in tracked.split(b'\0'):
            if not raw:
                continue
            relative = Path(os.fsdecode(raw))
            target = app / relative.relative_to('frontend')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        node = shutil.which('node')
        assert node, 'Node.js is required'
        modules = ROOT / 'frontend/node_modules'
        assert (modules / 'next/dist/bin/next').is_file(), 'Install existing frontend dependencies first'
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = os.environ.copy()
        for key in ('OPENAI_API_KEY', 'OPENAI_MODEL', 'OPENAI_REVIEW_MODEL',
                    'LIVE_PRESENTER_KEY', 'FRONTEND_HOST', 'PORT'):
            env.pop(key, None)
        env.update(PIPELINE_URL=backend, NEXT_TELEMETRY_DISABLED='1')
        log = (output / 'frontend.log').open('w', encoding='utf-8')
        process = subprocess.Popen([node, str(modules / 'next/dist/bin/next'), 'dev',
                                    str(app), '--webpack', '--hostname', '127.0.0.1',
                                    '--port', str(port)], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 120
        while True:
            assert process.poll() is None, f'Frontend exited; inspect {output / "frontend.log"}'
            try:
                read_json(base + '/api/runtime')
                break
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    raise AssertionError(f'Frontend startup timed out; inspect {output / "frontend.log"}')
                time.sleep(0.5)
        metadata.update(test_url=base, backend_url=backend, model=selector.model,
                        isolated_frontend=str(app.relative_to(ROOT)))
        browser_env = env | {'DEMO_TEST_URL': base, 'DEMO_OUTPUT': str(output),
                             'DEMO_PLAYWRIGHT': str(modules / '@playwright/test')}
        result = subprocess.run([node, str(ROOT / 'acceptance_huy/demo_3000_browser.cjs')],
                                cwd=ROOT, env=browser_env, timeout=480, check=False,
                                capture_output=True, text=True, encoding='utf-8')
        (output / 'browser.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        print(result.stdout, flush=True)
        assert result.returncode == 0, f'Browser checks failed; inspect {output / "browser.log"}'
    finally:
        if process is not None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
        if log is not None:
            log.close()
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        metadata['source_hashes_after'] = hashes()
        metadata['source_unchanged'] = metadata['source_hashes_after'] == source_before
        metadata['presenter_after'] = presenter_summary(presenter_url)
        metadata['presenter_unchanged'] = metadata['presenter_after'] == before
        (output / 'environment.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert metadata['source_unchanged'], 'Source database hashes changed'
    assert metadata['presenter_unchanged'], 'Presenter operational state changed during rehearsal'
