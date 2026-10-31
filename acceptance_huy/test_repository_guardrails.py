"""Exercise guardrails against a real Git index isolated from this checkout."""

from pathlib import Path
import subprocess
import sys

import pytest


CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "guardrails.py"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    return tmp_path


def check(repo: Path, mode: str = "--staged") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), mode], cwd=repo,
        capture_output=True, text=True,
    )


@pytest.mark.parametrize("name", [".env", "app/.env.local", "data/source.txt", "runs/state.json", "truth/facts.txt", "source.sqlite", "backup.sqlite.gz", "app/cache.db-wal"])
def test_private_paths_are_rejected(repo: Path, name: str) -> None:
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("private\n")
    git(repo, "add", "--", name)
    result = check(repo)
    assert result.returncode == 1
    assert name in result.stdout


def test_example_env_is_allowed(repo: Path) -> None:
    (repo / ".env.example").write_text("API_KEY=\n")
    git(repo, "add", ".env.example")
    assert check(repo).returncode == 0


def test_checks_index_instead_of_working_copy(repo: Path) -> None:
    target = repo / "app.py"
    target.write_text("<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> topic\n")
    git(repo, "add", "app.py")
    target.write_text("clean\n")
    result = check(repo)
    assert result.returncode == 1
    assert "conflict marker" in result.stdout


def test_whitespace_is_rejected(repo: Path) -> None:
    (repo / "app.py").write_text("value = 1  \n")
    git(repo, "add", "app.py")
    assert check(repo).returncode == 1


def test_all_mode_checks_previously_committed_private_files(repo: Path) -> None:
    (repo / ".env").write_text("private\n")
    git(repo, "add", ".env")
    git(repo, "commit", "-m", "Fixture")
    assert check(repo).returncode == 0
    assert check(repo, "--all").returncode == 1


def test_private_file_removal_is_allowed(repo: Path) -> None:
    (repo / ".env").write_text("private\n")
    git(repo, "add", ".env")
    git(repo, "commit", "-m", "Fixture")
    git(repo, "rm", ".env")
    assert check(repo).returncode == 0
