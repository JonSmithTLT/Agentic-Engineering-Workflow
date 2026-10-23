"""Exclusive inter-process lock on the control state.

Uses OS advisory locks (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows),
which the OS releases automatically when a process dies, so a crash can never
leave a stale lock behind. Leadership is *not* this lock: Lead authority is the
generation-bound token checked inside each locked transition.

The lock is fair (ADR-0001, amendment 2026-10-23): a taker first takes a turnstile, a second OS lock on
``<path>.queue``, and lets it go as soon as it holds the lock. Polling alone let a holder that released and at once
asked again win nearly every time, so a waiter waited through the holder's whole run of transactions. Now that holder
queues behind the waiter: two takers alternate, and with more the next holder is whichever queued taker polls first.
The turnstile only orders takers and excludes no one: a taker that cannot open it polls the lock without it, and it
has no removed-file check, so removing ``local/`` can cost fairness for a moment, never exclusion. A process stopped
while it waits (Ctrl+Z, a debugger) holds the turnstile, and every other taker waits behind it, as behind a stopped
holder (operator decision, 2026-10-23).
"""

from __future__ import annotations

import os
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
            deadline = time.monotonic() + self.timeout
            queue = self._join_queue(deadline)
            try:
                fh = self._open()
                while True:
                    self._wait(fh, deadline)
                    if self._is_path(fh):
                        break
                    # the file was removed or replaced after we opened it: a lock on the old file excludes no one
                    self._unlock(fh)
                    fh.close()
                    fh = self._open()
            finally:
                if queue is not None:  # the next taker queues now, behind this holder
                    try:
                        self._unlock(queue)
                    finally:
                        queue.close()
        self._fh = fh
        return self

    def _join_queue(self, deadline: float):  # type: ignore[no-untyped-def]
        """The turnstile, locked, or None when it cannot be opened. It only orders takers, so a taker that can open
        the lock but not the turnstile polls the lock without it rather than failing. It is opened here, never
        through ``_open``, which is the lock file's alone."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            queue = open(self.path.with_name(self.path.name + ".queue"), "a+b")
        except OSError:
            return None
        self._wait(queue, deadline)
        return queue

    def _wait(self, fh, deadline: float) -> None:  # type: ignore[no-untyped-def]
        """Lock ``fh``, polling until ``deadline``; past it, close ``fh`` and raise ``LockTimeout``."""
        while True:
            try:
                self._try_lock(fh)
                return
            except OSError:
                pass
            if time.monotonic() > deadline:
                fh.close()
                raise LockTimeout(f"could not lock {self.path} within {self.timeout}s") from None
            time.sleep(0.01)

    def intact(self) -> bool:
        """Whether the held lock is still on the file at the path. A holder checks this before it writes: if the
        lock file was removed while held (``local/`` deleted under a running process), another process can lock a
        new file at the same path, and this lock no longer excludes it."""
        return self._fh is not None and self._is_path(self._fh)

    def _is_path(self, fh) -> bool:  # type: ignore[no-untyped-def]
        if sys.platform == "win32":  # pragma: windows-only (an open file cannot be removed or replaced)
            return True
        try:  # pragma: posix-only
            held, now = os.fstat(fh.fileno()), os.stat(self.path)
        except OSError:
            return False
        return (held.st_ino, held.st_dev) == (now.st_ino, now.st_dev)

    def _open(self):  # type: ignore[no-untyped-def]
        """The lock file, opened for writing. Only a store writer locks it (``aew.process_kind``); a reader reads
        lock-free, and a contained run's layout hides ``.aew/local`` (STG-05 CB-09, CBF-1). So there is no read-only
        fallback: a process that cannot open the lock for writing is not one that may hold it (ADR-0009, amendment
        2026-10-21)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return open(self.path, "a+b")

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
