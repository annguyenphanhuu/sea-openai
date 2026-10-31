"""Startup copies exact release bytes to local disk without moving source data."""
from pathlib import Path
import sqlite3
import sys

from deploy import start_space


def test_local_release_copies_only_two_databases_and_preserves_sources(tmp_path):
    source, target = tmp_path / 'wwwroot', tmp_path / 'local/release_main'
    source.mkdir()
    for name, marker in [('core_14d.sqlite', 14), ('ops_14d.sqlite', 28)]:
        with sqlite3.connect(source / name) as db:
            db.execute('CREATE TABLE example (marker INTEGER)')
            db.execute('INSERT INTO example VALUES (?)', (marker,))
    (source / 'truth.json').write_text('never copy')
    before = {name: (source / name).read_bytes() for name in ('core_14d.sqlite', 'ops_14d.sqlite')}
    result = start_space.materialize_local_release(source, target)
    assert result == target.resolve()
    assert sorted(path.name for path in target.iterdir()) == ['core_14d.sqlite', 'ops_14d.sqlite']
    for name in before:
        assert (source / name).read_bytes() == before[name]
        assert (target / name).read_bytes() == before[name]
    assert start_space.materialize_local_release(source, target) == target.resolve()


def test_startup_uses_local_sources_and_creates_state_parent(tmp_path, monkeypatch):
    source, local, state = tmp_path / 'wwwroot', tmp_path / 'local/release_main', tmp_path / 'local/v4/state.sqlite'
    source.mkdir()
    for name in ('core_14d.sqlite', 'ops_14d.sqlite'):
        with sqlite3.connect(source / name) as db:
            db.execute('CREATE TABLE example (value INTEGER)')
    monkeypatch.setattr(start_space, 'release_dir', lambda: source)
    monkeypatch.setenv('SEA_RELEASE_DIR', str(source))
    monkeypatch.setenv('SEA_LOCAL_RELEASE_DIR', str(local))
    monkeypatch.setenv('SEA_STATE_PATH', str(state))
    monkeypatch.setenv('SEA_INTEGRATED', '1')
    monkeypatch.setenv('SEA_LLM', '1')
    captured = []
    monkeypatch.setattr(start_space.runpy, 'run_module', lambda *a, **k: captured.append(sys.argv.copy()))
    start_space.main()
    assert state.parent.is_dir()
    assert captured[0][captured[0].index('--core-path') + 1] == str(local / 'core_14d.sqlite')
    assert captured[0][captured[0].index('--state-path') + 1] == str(state)
    assert captured[0][-2:] == ['--integrated', '--llm']
