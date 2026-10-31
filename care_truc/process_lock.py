"""An OS-owned advisory lock, automatically released on process death."""

import os
from pathlib import Path


class RunLock:
    def __init__(self, handle):
        self.handle = handle

    @classmethod
    def acquire(cls, run_dir: Path) -> "RunLock":
        run_dir.mkdir(parents=True, exist_ok=True)
        handle = (run_dir / "care.lock").open("a+b")
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeError("care_run_already_owned") from None
        return cls(handle)

    def release(self) -> None:
        if self.handle.closed:
            return
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
