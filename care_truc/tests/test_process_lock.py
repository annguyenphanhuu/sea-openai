import subprocess
import sys

import pytest

from care_truc.process_lock import RunLock


def child(path):
    return subprocess.run([sys.executable, "-c",
        "from pathlib import Path; from care_truc.process_lock import RunLock; "
        "import sys; lock=RunLock.acquire(Path(sys.argv[1]))", str(path)],
        capture_output=True, timeout=10)


def test_second_process_same_run_fails(tmp_path):
    lock = RunLock.acquire(tmp_path)
    try:
        assert child(tmp_path).returncode != 0
        assert child(tmp_path / "other").returncode == 0
    finally:
        lock.release()


def test_process_death_releases_lock(tmp_path):
    assert child(tmp_path).returncode == 0
    lock = RunLock.acquire(tmp_path)
    lock.release()
