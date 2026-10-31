"""Deployment startup forwards explicit port and LLM settings to the UI."""

import sqlite3
import sys

import pytest

from deploy import start_space


@pytest.fixture
def startup(monkeypatch, tmp_path):
    release = tmp_path / "release_main"
    release.mkdir()
    for name in ("core_14d.sqlite", "ops_14d.sqlite"):
        with sqlite3.connect(release / name) as connection:
            connection.execute("CREATE TABLE startup_fixture (id INTEGER)")
    monkeypatch.setattr(start_space, "release_dir", lambda: release)
    monkeypatch.setattr(start_space, "project_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["startup-test"])
    for name in ("PORT", "SEA_INTEGRATED", "SEA_LLM", "SEA_STATE_PATH"):
        monkeypatch.delenv(name, raising=False)
    launches = []

    def record_launch(module, *, run_name):
        launches.append((module, run_name, sys.argv.copy()))

    monkeypatch.setattr(start_space.runpy, "run_module", record_launch)
    return launches, release, tmp_path


@pytest.mark.parametrize("port, expected", [(None, "7860"), ("8000", "8000"), ("9123", "9123")])
def test_startup_uses_port_environment_or_space_default(startup, monkeypatch, port, expected):
    launches, release, root = startup
    if port is not None:
        monkeypatch.setenv("PORT", port)

    start_space.main()

    assert launches == [(
        "platform_huy.serve_ui", "__main__",
        ["platform_huy.serve_ui", "--host", "0.0.0.0", "--port", expected,
         "--core-path", str(release / "core_14d.sqlite"),
         "--state-path", str(root / "runs/a3-demo/state.sqlite")],
    )]


@pytest.mark.parametrize("integrated, llm, expected_flags", [
    (None, None, []),
    ("1", None, ["--integrated"]),
    ("true", "1", ["--integrated", "--llm"]),
    ("1", "true", ["--integrated", "--llm"]),
    ("TRUE", "TRUE", ["--integrated", "--llm"]),
    ("1", "false", ["--integrated"]),
    ("1", "0", ["--integrated"]),
    ("false", "yes", []),
    (None, "1", ["--llm"]),
])
def test_startup_preserves_integrated_and_explicit_llm_flags(
    startup, monkeypatch, integrated, llm, expected_flags,
):
    launches, _, _ = startup
    if integrated is not None:
        monkeypatch.setenv("SEA_INTEGRATED", integrated)
    if llm is not None:
        monkeypatch.setenv("SEA_LLM", llm)

    start_space.main()

    assert len(launches) == 1
    assert launches[0][2][9:] == expected_flags


def test_llm_without_integrated_fails_before_server_or_secret_loading(
    startup, monkeypatch, capsys,
):
    from platform_huy import serve_ui

    monkeypatch.setenv("SEA_LLM", "1")

    def forbidden(*args, **kwargs):
        pytest.fail("Nonintegrated LLM startup must reject before server or secret loading")

    monkeypatch.setattr(serve_ui, "project_root", forbidden)
    monkeypatch.setattr(serve_ui, "create_server", forbidden)

    def launch_ui(module, *, run_name):
        assert (module, run_name) == ("platform_huy.serve_ui", "__main__")
        serve_ui.main()

    monkeypatch.setattr(start_space.runpy, "run_module", launch_ui)
    with pytest.raises(SystemExit) as error:
        start_space.main()

    assert error.value.code == 2
    assert "--llm requires --integrated" in capsys.readouterr().err
