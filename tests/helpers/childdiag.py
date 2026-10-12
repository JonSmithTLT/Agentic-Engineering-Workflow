"""Diagnostics inside every Python helper subprocess (the hang-and-flake diagnosis plan, G3 H1, "each Python child's
stacks").

In #213 the listener that died ran inside the fake TUI **subprocess**: the test process's thread dump never saw it,
its uncaught exception went to a stderr nobody kept, and its directory was deleted. A helper child started through
this module (:func:`spawn`, or :func:`install` called first thing by a helper the product starts, such as the fake
OpenCode launcher) leaves, in its private diagnostics directory:

- ``stacks-<pid>.a.txt`` / ``.b.txt``: every thread's stack, every ``interval`` seconds (at least 30), from
  ``faulthandler.dump_traceback_later(repeat=True)``. That runs on faulthandler's own C thread, so it still records
  during a hang inside a C call holding the GIL, and needs no signal (Windows has none to send). faulthandler appends
  to its descriptor, so a small watcher thread bounds the file: past :data:`FILE_CAP` it cancels the timer (which is
  synchronous), reopens the **other** file truncated, re-arms on it, and only then closes the old one. Two
  generations are kept; nothing is renamed (Windows refuses to rename an open file), and a file faulthandler may still
  write to is never closed. If the GIL is held so the watcher cannot run, the file grows by one dump per interval
  until the session deadline: at most ``remaining_s / interval`` dumps.
- ``events-<pid>.jsonl``: every uncaught exception, in any thread (``threading.excepthook``) or the main one
  (``sys.excepthook``), with its stack, written at once. A dying thread is never silent.
- ``out-<pid>.log`` / ``err-<pid>.log``: its stdout and stderr. ``capture="redirect"`` replaces the descriptors
  themselves (so C-level output and output before an ``os._exit`` are kept); ``capture="tee"``, for a child whose
  output a test or the product reads, copies what Python writes and leaves the descriptors alone.
- ``recorder-<pid>.jsonl``: its flight recorder, at exit and on an uncaught exception.

The directory is the test's private one (``autopsy.child_dir``), outside the report directory; the autopsy copies it
from there through ``harness_diagnostics`` (redacted, capped, never ``.json``). The test process itself never arms
faulthandler here: its single timer belongs to the hang watchdog.

Run as a script, ``python childdiag.py <script.py | -m module | -c code> [args]`` installs and then runs the target
as ``__main__`` (what :func:`spawn` starts). This module imports nothing from AEW.
"""

from __future__ import annotations

import atexit
import faulthandler
import io
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import IO, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flight_recorder  # noqa: E402

ENV_DIR = "AEW_CHILDDIAG_DIR"
ENV_CAPTURE = "AEW_CHILDDIAG_CAPTURE"
ENV_INTERVAL = "AEW_CHILDDIAG_INTERVAL"
DIR_FILE = "childdiag-dir.txt"  # beside a helper's own files, for a helper the product starts with a curated env
MIN_INTERVAL_S = 30.0
FILE_CAP = 256 * 1024
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_installed: Diag | None = None


class _Tee(io.TextIOBase):
    def __init__(self, first: IO[str], second: IO[str]) -> None:
        self.first, self.second = first, second

    def write(self, s: str) -> int:
        n = self.first.write(s)
        self.first.flush()
        try:
            self.second.write(s)
            self.second.flush()
        except (OSError, ValueError):
            pass
        return n

    def flush(self) -> None:
        self.first.flush()

    def fileno(self) -> int:
        return self.first.fileno()

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self.first, "encoding", "utf-8")

    @property
    def buffer(self) -> Any:
        return self.first.buffer  # binary writes go to the real stream only


class Diag:
    def __init__(self, directory: Path, interval: float, cap: int) -> None:
        self.dir = directory
        self.interval = float(interval)
        self.cap = cap
        self.pid = os.getpid()
        self.paths = [directory / f"stacks-{self.pid}.a.txt", directory / f"stacks-{self.pid}.b.txt"]
        self.events = directory / f"events-{self.pid}.jsonl"
        self._gen = 0
        self._lock = threading.Lock()
        self._file: IO[str] | None = None
        self._stop = threading.Event()
        self.rotations = 0

    # ------------------------------------------------------------------ the repeating dump, bounded

    def arm(self) -> None:
        self._file = open(self.paths[0], "w", encoding="utf-8")  # noqa: SIM115  (faulthandler holds it)
        self._file.write(f"childdiag: pid {self.pid}, every thread's stack every {self.interval:g}s\n")
        self._file.flush()
        faulthandler.dump_traceback_later(self.interval, repeat=True, file=self._file)
        threading.Thread(target=self._watch, name="childdiag-rotate", daemon=True).start()

    def rotate(self) -> None:
        """Cancel (synchronous: faulthandler's thread stops writing), reopen the other generation truncated, re-arm on
        it, then close the old file: faulthandler never writes to a closed or truncated descriptor."""
        with self._lock:
            old = self._file
            faulthandler.cancel_dump_traceback_later()
            self._gen = 1 - self._gen
            self._file = open(self.paths[self._gen], "w", encoding="utf-8")  # noqa: SIM115
            self._file.write(f"childdiag: pid {self.pid}, generation {self.rotations + 1}\n")
            self._file.flush()
            faulthandler.dump_traceback_later(self.interval, repeat=True, file=self._file)
            self.rotations += 1
            if old is not None:
                old.close()

    def _watch(self) -> None:
        poll = min(self.interval, 5.0)
        while not self._stop.wait(poll):
            try:
                if self._file is not None and os.fstat(self._file.fileno()).st_size > self.cap:
                    self.rotate()
            except (OSError, ValueError):
                return

    # ------------------------------------------------------------------ uncaught exceptions

    def event(self, kind: str, **facts: Any) -> None:
        line = json.dumps({"kind": kind, "t": round(time.time(), 3), "pid": self.pid, **facts}, default=str) + "\n"
        try:
            with self.events.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def _excepthook(self, args: threading.ExceptHookArgs) -> None:
        stack = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        name = args.thread.name if args.thread is not None else "?"
        self.event("thread_exception", thread=name, error=args.exc_type.__name__, message=str(args.exc_value),
                   stack=stack)
        flight_recorder.record("thread_died", thread=name, error=args.exc_type.__name__, message=str(args.exc_value))
        flight_recorder.flush_raw(self.dir)
        self._previous_thread_hook(args)

    def _sys_excepthook(self, exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        stack = "".join(traceback.format_exception(exc_type, exc, tb))
        self.event("uncaught_exception", thread="MainThread", error=exc_type.__name__, message=str(exc), stack=stack)
        flight_recorder.record("uncaught", error=exc_type.__name__, message=str(exc))
        flight_recorder.flush_raw(self.dir)
        self._previous_sys_hook(exc_type, exc, tb)

    def hooks(self) -> None:
        self._previous_thread_hook = threading.excepthook
        self._previous_sys_hook = sys.excepthook
        threading.excepthook = self._excepthook
        sys.excepthook = self._sys_excepthook
        atexit.register(lambda: flight_recorder.flush_raw(self.dir))

    # ------------------------------------------------------------------ output

    def capture(self, how: str) -> None:
        if how == "none":
            return
        out = self.dir / f"out-{self.pid}.log"
        err = self.dir / f"err-{self.pid}.log"
        if how == "redirect":
            for stream, path, fd in ((sys.stdout, out, 1), (sys.stderr, err, 2)):
                try:
                    if stream is not None:
                        stream.flush()
                    target = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    os.dup2(target, fd)
                    os.close(target)
                except OSError:
                    continue
            # A fresh text stream over each descriptor: on Windows the inherited one may be a console stream, which
            # writes to the console handle rather than through the descriptor just replaced.
            sys.stdout = open(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)  # noqa: SIM115
            sys.stderr = open(2, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)  # noqa: SIM115
            return
        if how == "tee":
            if sys.stdout is not None:
                sys.stdout = _Tee(sys.stdout, open(out, "a", encoding="utf-8"))  # noqa: SIM115
            if sys.stderr is not None:
                sys.stderr = _Tee(sys.stderr, open(err, "a", encoding="utf-8"))  # noqa: SIM115
            return
        raise ValueError(f"capture must be redirect, tee or none, not {how!r}")


def install(directory: str | os.PathLike[str] | None = None, *, capture: str | None = None,
            interval: float | None = None, cap: int = FILE_CAP) -> Diag | None:
    """Install the child's diagnostics into ``directory`` (else ``$AEW_CHILDDIAG_DIR``). Without either it does
    nothing at all: a helper run outside a test session is unchanged. Idempotent."""
    global _installed
    if _installed is not None:
        return _installed
    where = directory or os.environ.get(ENV_DIR)
    if not where:
        return None
    path = Path(where)
    path.mkdir(parents=True, exist_ok=True)
    explicit = interval or os.environ.get(ENV_INTERVAL)
    # At least 30 s, which bounds the file's growth; only a test of this module asks for less (never below 1 s).
    diag = Diag(path, max(float(explicit), 1.0) if explicit else MIN_INTERVAL_S, cap)
    diag.hooks()
    diag.capture(capture or os.environ.get(ENV_CAPTURE) or "redirect")
    diag.arm()
    flight_recorder.record("childdiag", dir=str(path), interval=diag.interval, argv=" ".join(sys.argv[:6]))
    _installed = diag
    return diag


def install_beside(directory: Path, *, capture: str = "tee") -> Diag | None:
    """For a helper the product starts (whose environment the product curates): the diagnostics directory named in
    ``<directory>/childdiag-dir.txt``, written there by the test (``autopsy.child_dir``), else the environment."""
    marker = Path(directory) / DIR_FILE
    try:
        where = marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        where = None
    return install(where, capture=capture)


def child_env(directory: Path, env: dict[str, str] | None = None, *, capture: str = "redirect",
              interval: float | None = None) -> dict[str, str]:
    """The environment for a helper child: its diagnostics directory and capture mode. Set per spawn only, never in
    the test process's own environment (``process_isolation`` checks ``AEW_*``)."""
    out = dict(os.environ if env is None else env)
    out[ENV_DIR] = str(directory)
    out[ENV_CAPTURE] = capture
    if interval is not None:
        out[ENV_INTERVAL] = str(interval)
    return out


def spawn(argv: list[str], directory: Path, *, capture: str = "redirect", interval: float | None = None,
          env: dict[str, str] | None = None, **popen: Any) -> subprocess.Popen[Any]:
    """Start a Python helper (``[python, script, ...]``, ``[python, -m, module, ...]`` or ``[python, -c, code]``)
    under this module: it installs first, then runs the target as ``__main__``. ``capture="tee"`` when the caller reads
    the child's output itself. On Windows the child never has a window. The spawn and its pid go to the recorder."""
    if len(argv) < 2:
        raise ValueError("spawn expects [python, target, ...]")
    wrapped = [argv[0], str(Path(__file__).resolve()), *argv[1:]]
    if sys.platform == "win32":  # pragma: windows-only
        popen["creationflags"] = popen.get("creationflags", 0) | NO_WINDOW
    started = time.monotonic()
    proc = subprocess.Popen(wrapped, env=child_env(directory, env, capture=capture, interval=interval), **popen)
    flight_recorder.spawned(argv, proc.pid, via="childdiag", capture=capture, at=round(started, 3))
    return proc


def _main(argv: list[str]) -> None:
    import runpy

    sys.modules.setdefault("childdiag", sys.modules[__name__])  # the target's own `import childdiag` finds this one
    install()
    if not argv:
        raise SystemExit("usage: childdiag.py <script.py | -m module | -c code> [args]")
    if argv[0] == "-m":
        sys.argv = [argv[1], *argv[2:]]
        runpy.run_module(argv[1], run_name="__main__", alter_sys=True)
    elif argv[0] == "-c":
        sys.argv = ["-c", *argv[2:]]
        exec(compile(argv[1], "<string>", "exec"), {"__name__": "__main__"})  # noqa: S102  (the helper's own code)
    else:
        sys.argv = list(argv)
        sys.path.insert(0, str(Path(argv[0]).resolve().parent))
        runpy.run_path(argv[0], run_name="__main__")


if __name__ == "__main__":
    _main(sys.argv[1:])
