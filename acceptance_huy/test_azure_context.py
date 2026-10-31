"""Exercise the exact ACR context boundary with real files."""
from pathlib import Path
import os

import pytest


def fixture_source(tmp_path):
    source = tmp_path / "source"
    files = {
        ".dockerignore": b"**\n", "deploy/Dockerfile": b"FROM python:3.11-slim\n",
        "deploy/requirements.txt": b"", "deploy/start_space.py": b"print('start')\n",
        "contracts/types.py": b"VALUE = 42\n", "contracts/schema.sql": b"SELECT 1;",
        "care_truc/api.py": b"# care", "care_truc/schema.sql": b"SELECT 2;",
        "platform_huy/a3_demo.py": b"# a3", "platform_huy/migrations/001.sql": b"SELECT 3;",
        "platform_huy/ui_prototype/live.html": b"<html>demo</html>",
        "platform_huy/ui_prototype/assets/icon.svg": b"<svg/>",
        "logistics_an_nguyen/replay.py": b"# replay",
        "logistics_an_nguyen/ui/index.html": b"orders", "logistics_an_nguyen/ui/app.js": b"app",
        "logistics_an_nguyen/ui/data.mjs": b"data", "logistics_an_nguyen/ui/styles.css": b"css",
        "data/release_main/core_14d.sqlite": b"literal core bytes",
        "data/release_main/ops_14d.sqlite": b"literal ops bytes",
    }
    for name, content in files.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return source


def test_context_preserves_bytes_and_excludes_unlisted_data_and_secrets(tmp_path, monkeypatch):
    from deploy.prepare_context import prepare_context
    source = fixture_source(tmp_path)
    for name in (".env", "truth/labels.csv", "data/release_main/third.sqlite",
                 "data/release_main/manifest.sha256", "platform_huy/ui_prototype/.env",
                 "platform_huy/ui_prototype/assets/private.token", "deploy/extra.txt",
                 "platform_huy/ui_prototype/node_modules/hidden.js",
                 "platform_huy/ui_prototype/heldout/leak.png", ".pytest_cache/secret"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"excluded sentinel")
    original_scandir = os.scandir
    def guarded_scandir(path):
        if Path(path) == source or Path(path).name in (".pytest_cache", "node_modules", "heldout"):
            raise PermissionError("must never enumerate unrelated directory")
        return original_scandir(path)
    monkeypatch.setattr(os, "scandir", guarded_scandir)
    output = tmp_path / "context"
    assert prepare_context(source, output) == output
    assert (output / "data/release_main/core_14d.sqlite").read_bytes() == b"literal core bytes"
    assert (output / "data/release_main/ops_14d.sqlite").read_bytes() == b"literal ops bytes"
    assert (output / "contracts/types.py").read_bytes() == b"VALUE = 42\n"
    assert (output / "logistics_an_nguyen/ui/data.mjs").read_bytes() == b"data"
    assert sorted(p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()) == [
        ".dockerignore", "care_truc/api.py", "care_truc/schema.sql", "contracts/schema.sql", "contracts/types.py",
        "data/release_main/core_14d.sqlite", "data/release_main/ops_14d.sqlite", "deploy/Dockerfile",
        "deploy/requirements.txt", "deploy/start_space.py", "logistics_an_nguyen/replay.py",
        "logistics_an_nguyen/ui/app.js", "logistics_an_nguyen/ui/data.mjs",
        "logistics_an_nguyen/ui/index.html", "logistics_an_nguyen/ui/styles.css",
        "platform_huy/a3_demo.py", "platform_huy/migrations/001.sql",
        "platform_huy/ui_prototype/assets/icon.svg", "platform_huy/ui_prototype/live.html",
    ]


def test_existing_output_refused_without_overwriting(tmp_path):
    from deploy.prepare_context import prepare_context
    source = fixture_source(tmp_path)
    output = tmp_path / "context"
    output.mkdir()
    (output / "keep.txt").write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        prepare_context(source, output)
    assert (output / "keep.txt").read_bytes() == b"keep me"


def test_source_data_output_refused_but_scratch_run_allowed(tmp_path):
    from deploy.prepare_context import prepare_context
    source = fixture_source(tmp_path)
    for relative in ("data/context", "truth/context", "contracts/context"):
        with pytest.raises(ValueError):
            prepare_context(source, source / relative)
        assert not (source / relative).exists()
    output = source / ".scratch/runs/fresh-context"
    assert prepare_context(source, output) == output
