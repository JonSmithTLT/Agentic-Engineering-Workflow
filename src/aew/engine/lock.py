"""Exclusive inter-process lock on the control state.

Uses OS advisory locks (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows),
which the OS releases automatically when a process dies, so a crash can never
leave a stale lock behind. Leadership is *not* this lock: Lead authority is the
generation-bound token checked inside each locked transition.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import TracebackType

from aew import profile
from aew.errors import LockTimeout


class FileLock:
    def __init__(self, path: Path, timeout: float = 60.0) -> None:
        self.path = path
        self.timeout = timeout
        self._fh = None

    def __enter__(self) -> FileLock:
        with profile.phase("lock"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(self.path, "a+b")
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    self._try_lock(fh)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        fh.close()
                        raise LockTimeout(f"could not lock {self.path} within {self.timeout}s") from None
                    time.sleep(0.01)
        self._fh = fh
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            self._unlock(fh)
        finally:
            fh.close()

    if sys.platform == "win32":  # pragma: windows-only

        @staticmethod
        def _try_lock(fh) -> None:
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

        @staticmethod
        def _unlock(fh) -> None:
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

    else:  # pragma: posix-only

        @staticmethod
        def _try_lock(fh) -> None:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        @staticmethod
        def _unlock(fh) -> None:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
