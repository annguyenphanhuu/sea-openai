"""Validate the public branch checker command and actual branch detection."""

from pathlib import Path
import subprocess
import sys

import pytest


CHECKER = Path(__file__).resolve().parents[1] / "scripts/check_branch.py"


@pytest.mark.parametrize("name", ["feat/order-tracking", "fix/123-heartbeat", "chore/repository-guardrails", "ci/pr-checks", "docs/setup"])
def test_valid_names(name: str) -> None:
    assert subprocess.run([sys.executable, str(CHECKER), name], capture_output=True).returncode == 0


@pytest.mark.parametrize("name", ["main", "master", "huy", "an-nguyen", "truc", "", "feat/Uppercase", "feat/two_words", "feat/a--b", "fix/a/b", "feature/orders", "feat/-orders", "feat/orders-"])
def test_invalid_names(name: str) -> None:
    assert subprocess.run([sys.executable, str(CHECKER), name], capture_output=True).returncode == 1


def test_detects_current_branch_and_rejects_detached_head(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    def check() -> int:
        return subprocess.run([sys.executable, str(CHECKER)], cwd=tmp_path, capture_output=True).returncode

    git("init")
    git("switch", "-c", "feat/orders")
    assert check() == 0
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "Fixture")
    git("checkout", "--detach", "HEAD")
    assert check() == 1
