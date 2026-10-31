"""Deployment checks use real SQLite; only Hub transport is replaced."""

from hashlib import sha256
import importlib
import os
from pathlib import Path
import sqlite3
import sys
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


def release_fixture(path: Path, *, manifest: bool = False) -> Path:
    path.mkdir(parents=True)
    for name in ("core_14d.sqlite", "ops_14d.sqlite"):
        with sqlite3.connect(path / name) as connection:
            connection.execute("CREATE TABLE sample(value TEXT)")
            connection.execute("INSERT INTO sample VALUES ('synthetic')")
        connection.close()
    if manifest:
        lines = [sha256((path / name).read_bytes()).hexdigest() + "  " + name
                 for name in ("core_14d.sqlite", "ops_14d.sqlite")]
        (path / "manifest.sha256").write_text("\n".join(lines), encoding="utf-8")
    return path


def fetch_module():
    return importlib.import_module("deploy.fetch_data")


def test_offline_release_needs_no_hub_import(tmp_path, monkeypatch):
    path = release_fixture(tmp_path / "release_main", manifest=True)
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    monkeypatch.delenv("SEA_DATASET_REPO", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert fetch_module().ensure_release(path) == path.resolve()


def test_missing_release_requires_explicit_dataset_id(tmp_path, monkeypatch):
    monkeypatch.delenv("SEA_DATASET_REPO", raising=False)
    with pytest.raises(fetch_module().ReleaseError, match="SEA_DATASET_REPO"):
        fetch_module().ensure_release(tmp_path / "release_main")


def test_download_requires_runtime_token(tmp_path, monkeypatch):
    monkeypatch.setenv("SEA_DATASET_REPO", "test/private-release")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(fetch_module().ReleaseError, match="HF_TOKEN"):
        fetch_module().ensure_release(tmp_path / "release_main")


def test_download_only_allowlisted_files_and_atomic_publication(tmp_path, monkeypatch):
    target = tmp_path / "release_main"
    monkeypatch.setenv("SEA_DATASET_REPO", "test/private-release")
    monkeypatch.setenv("HF_TOKEN", "test-placeholder-secret")
    monkeypatch.setenv("SEA_DATASET_REVISION", "demo-release")
    calls = []

    def download(**kwargs):
        assert not target.exists()
        calls.append(kwargs)
        release_fixture(Path(kwargs["local_dir"]) / "release_main", manifest=True)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    assert fetch_module().ensure_release(target) == target.resolve()
    assert len(calls) == 1
    assert calls[0]["repo_id"] == "test/private-release"
    assert calls[0]["repo_type"] == "dataset"
    assert calls[0]["revision"] == "demo-release"
    assert calls[0]["token"] == "test-placeholder-secret"
    assert calls[0]["allow_patterns"] == ["release_main/core_14d.sqlite",
                                          "release_main/ops_14d.sqlite",
                                          "release_main/manifest.sha256"]
    assert sorted(path.name for path in target.iterdir()) == ["core_14d.sqlite", "manifest.sha256", "ops_14d.sqlite"]


def test_failed_download_cannot_publish_partial_or_leak_token(tmp_path, monkeypatch):
    target = tmp_path / "release_main"
    monkeypatch.setenv("SEA_DATASET_REPO", "test/private-release")
    monkeypatch.setenv("HF_TOKEN", "test-placeholder-secret")

    def download(**kwargs):
        folder = Path(kwargs["local_dir"]) / "release_main"
        folder.mkdir()
        (folder / "core_14d.sqlite").write_bytes(b"partial")
        raise OSError("transport test-placeholder-secret")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    with pytest.raises(fetch_module().ReleaseError) as error:
        fetch_module().ensure_release(target)
    assert "test-placeholder-secret" not in str(error.value)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("damage", ["missing", "corrupt", "hash", "manifest"])
def test_existing_invalid_release_is_never_accepted(tmp_path, damage):
    path = release_fixture(tmp_path / "release_main", manifest=True)
    if damage == "missing":
        (path / "ops_14d.sqlite").unlink()
    elif damage == "corrupt":
        (path / "ops_14d.sqlite").write_bytes(b"not sqlite")
    elif damage == "hash":
        with sqlite3.connect(path / "ops_14d.sqlite") as connection:
            connection.execute("INSERT INTO sample VALUES ('changed')")
        connection.close()
    else:
        (path / "manifest.sha256").write_text("invalid checksum", encoding="utf-8")
    with pytest.raises(fetch_module().ReleaseError):
        fetch_module().ensure_release(path)


def test_download_missing_ops_is_never_published(tmp_path, monkeypatch):
    target = tmp_path / "release_main"
    monkeypatch.setenv("SEA_DATASET_REPO", "test/private-release")
    monkeypatch.setenv("HF_TOKEN", "test-placeholder-secret")

    def download(**kwargs):
        folder = release_fixture(Path(kwargs["local_dir"]) / "release_main")
        (folder / "ops_14d.sqlite").unlink()

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    with pytest.raises(fetch_module().ReleaseError):
        fetch_module().ensure_release(target)
    assert not target.exists()


def test_release_environment_overrides_only_release_path(tmp_path, monkeypatch):
    from platform_huy.a3_demo import release_dir
    monkeypatch.setenv("SEA_RELEASE_DIR", str(tmp_path / "custom-release"))
    assert release_dir() == tmp_path / "custom-release"


def test_docker_metadata_and_copy_allowlist():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "deploy/Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.11-slim" in dockerfile
    assert 'CMD ["python", "-m", "deploy.start_space"]' in dockerfile
    assert "EXPOSE 7860" in dockerfile
    assert "care_truc/*.py care_truc/schema.sql ./care_truc/" in dockerfile
    assert "platform_huy/migrations/*.sql ./platform_huy/migrations/" in dockerfile
    assert "COPY ." not in dockerfile
    assert "HF_TOKEN" not in dockerfile
    readme = (root / "deploy/README.md").read_text(encoding="utf-8")
    assert len(readme.splitlines()) == 5
    assert "az acr build" in readme
    assert "az containerapp update" in readme
    assert "7860" in readme
    ignored = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("**/.env*", "**/data", "**/truth", "**/runs", "**/.git", "**/.worktrees", "**/.scratch"):
        assert pattern in ignored


def test_space_https_origin_and_public_bind_with_real_http(tmp_path):
    from platform_huy.serve_ui import create_server
    core = tmp_path / "core.sqlite"
    with sqlite3.connect(core) as connection:
        connection.executescript("""
            CREATE TABLE sim_clock(id INTEGER PRIMARY KEY, now TEXT);
            INSERT INTO sim_clock VALUES (1,'2026-10-24T16:00:00+07:00');
            CREATE TABLE orders(order_id TEXT,created_at TEXT,guaranteed_date TEXT,
                carrier_id TEXT,service_level TEXT,cancelled_at TEXT);
            CREATE TABLE scan_events(event_id TEXT,order_id TEXT,status TEXT,location_type TEXT,
                location_id TEXT,event_at TEXT,ingested_at TEXT,carrier_event_id TEXT);
            CREATE TABLE delivery_attempts(attempt_id TEXT,order_id TEXT,attempt_no INTEGER,
                attempt_at TEXT,outcome TEXT,reason_code TEXT,call_attempts INTEGER);
            CREATE TABLE linehaul_reports(report_id TEXT,trip_id TEXT,reported_at TEXT,
                reported_by TEXT,reason_code TEXT,driver_note TEXT);
        """)
    connection.close()
    server = create_server(core_path=core, state_path=tmp_path / "runtime/state.sqlite",
                           port=0, host="0.0.0.0")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.server_address[0] == "0.0.0.0"
        url = "http://127.0.0.1:" + str(server.server_port) + "/api/next"
        request = Request(url, data=b"{}", headers={"Host": "synthetic.hf.space",
                                                   "Origin": "https://synthetic.hf.space"})
        with urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert b'"now": "2026-10-24T16:30:00+07:00"' in response.read()
        request = Request(url, data=b"{}", headers={"Host": "synthetic.hf.space",
                                                   "Origin": "https://other.hf.space"})
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=5)
        assert error.value.code == 403
        error.value.close()
        with sqlite3.connect(tmp_path / "runtime/state.sqlite") as connection:
            assert connection.execute("SELECT current_at FROM a3_demo_clock").fetchone() == (
                "2026-10-24T16:30:00+07:00",)
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize('target', ['ops', 'nested', 'hardlink'])
def test_startup_rejects_source_runtime_alias_before_server(tmp_path, monkeypatch, target):
    from deploy import start_space
    release = release_fixture(tmp_path / 'inputs')
    original = sha256((release / 'ops_14d.sqlite').read_bytes()).hexdigest()
    state = release / 'ops_14d.sqlite' if target == 'ops' else release / 'runtime.sqlite'
    if target == 'hardlink':
        state = tmp_path / 'runtime.sqlite'
        os.link(release / 'ops_14d.sqlite', state)
    monkeypatch.setenv('SEA_RELEASE_DIR', str(release))
    monkeypatch.setenv('SEA_STATE_PATH', str(state))
    started = []
    monkeypatch.setattr(start_space.runpy, 'run_module', lambda *args, **kwargs: started.append(args))
    with pytest.raises(SystemExit, match='runtime'):
        start_space.main()
    assert started == []
    assert sha256((release / 'ops_14d.sqlite').read_bytes()).hexdigest() == original


def test_direct_demo_rejects_ops_alias_before_writing(tmp_path):
    from datetime import datetime, timezone
    from platform_huy.a3_demo import A3Demo
    release = release_fixture(tmp_path / 'inputs')
    ops = release / 'ops_14d.sqlite'
    original = sha256(ops.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='source'):
        A3Demo(release / 'core_14d.sqlite', ops, datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert sha256(ops.read_bytes()).hexdigest() == original
