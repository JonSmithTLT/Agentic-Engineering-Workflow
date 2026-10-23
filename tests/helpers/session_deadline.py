"""The session deadline: CI keeps the evidence even when a job would time out (the hang-and-flake diagnosis plan,
G3 H3).

GitHub Actions gives no hook before a job's ``timeout-minutes`` kills it, so a lane sets its own limit below it:
``--session-deadline S``. Nothing at all is created without it (no job object, no subreaper, no sentinel), so a
developer running pytest normally is unaffected.

**The deadline under xdist.** The controller computes one absolute deadline (wall clock, converted by each process to
its own monotonic clock) and passes it to every worker. Each worker, at that deadline, collects the autopsy of its
running test (``autopsy.py``) and exits with :data:`DEADLINE_EXIT`. Deadline lanes run with ``--max-worker-restart 0``
(set here too), so xdist replaces no worker and the run ends; a crash is evidence, not something to route around. At
the deadline plus one margin, the controller (or, without xdist, the one process, at the deadline itself):

1. collects (its own autopsy, the session's process set, the file holders) and writes ``session-deadline``;
2. ends the **other** members of the session's process set, each re-checked by (pid, start time). It never ends its
   own job: it is a member;
3. writes ``session-finished`` last, and exits with :data:`DEADLINE_EXIT`.

If the session finishes on its own after the deadline (its workers exited), ``pytest_sessionfinish`` does the same and
sets the exit status instead. On any normal exit ``session-finished`` is the controller's last act.

**The session's process set** is defined by containment, never by walking parent pids from the controller (detached
supervisors break away or call ``setsid``; Windows reuses pids):

- **Windows:** a job object without breakaway, created and joined in ``pytest_configure`` (``tryfirst``), before xdist
  starts any worker. Every later descendant starts inside it; ``procs.spawn_detached``'s breakaway attempt fails into
  its fallback, inside the job.
- **Linux:** the controller is a child subreaper, so detached descendants re-parent to it; a member is a descendant
  identified by (pid, start time), each child started no earlier than its parent (``proctree.descendants``).

**The sentinel**, independent of the controller's GIL: one small process (``CREATE_NO_WINDOW``), started **before**
the controller joins its job, so outside it. It knows the deadline, the controller's (pid, start time) and the session
directory; on Windows it opens the job by its name. It acts when:

- the controller is gone with ``session-finished`` written: it exits;
- the controller is gone **without** it (an ``os._exit`` from the watchdog's second alarm, an xdist internal error, a
  kill): it writes ``abnormal-exit``, the set and the file holders, ends the set (``TerminateJobObject``; on Linux the
  members of its last snapshot, refreshed every few seconds while the controller lived, whose (pid, start time) still
  match, children first), and exits;
- the deadline plus two margins passes with the controller still there (wedged, for example holding the GIL): it
  writes ``session-deadline`` itself, the set and the holders, ends the set (the controller with it), and exits.

Its lifetime is bounded by the deadline plus the two margins. Everything it writes goes through
``harness_diagnostics`` (redacted, capped, never ``.json``), under ``<hang-dir>/autopsy/session-<pid>/``.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
import weakref
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bounds  # noqa: E402
import flight_recorder  # noqa: E402
import proctree  # noqa: E402

PLUGIN_NAME = "aew-session-deadline"
DEADLINE_EXIT = 70  # distinct from pytest's own exit codes (0-5)
JOB_DEADLINE_ENV = "AEW_JOB_DEADLINE"  # the CI job's absolute deadline for its sessions (its first step sets it)
SLOW_COLLECT_ENV = "G3_TEST_SLOW_COLLECT_S"  # tests only: the controller's collect takes this long (the sentinel path)
WORKER_KEY = "aew_session_deadline"
DIR_KEY = "aew_session_dir"
STARTED, DEADLINE, FINISHED, ABNORMAL = "session-started", "session-deadline", "session-finished", "abnormal-exit"
READY = "sentinel-ready"
JOB_UNAVAILABLE = "job-unavailable"
SENTINEL_POLL_S = 0.25
SNAPSHOT_EVERY_S = 2.0
SENTINEL_READY_S = 20.0  # the bound on the sentinel opening the job before the controller joins it
HOLDER_FILES = 200
REAP_POLL_S = 0.1
REAP_GATE_ENV = "G3_TEST_REAP_GATE"  # tests only: the reaper starts polling once this file exists


def _write(directory: Path, name: str, text: str, *, append: bool = False) -> None:
    import harness_diagnostics as hd  # redacts with AEW's own patterns; imported late: the sentinel loads it lazily

    hd.write_text(directory, name, text, append=append)


def marker(directory: Path, name: str) -> Path:
    return directory / f"{name}.txt"


def _stamp(what: str) -> str:
    return f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid {os.getpid()}: {what}\n"


def _holders_text(directory: Path, extra: list[str]) -> str:
    """Who holds the session's evidence files (what the upload must read) and the recorder's failed paths."""
    paths = [str(p) for p in sorted(directory.parent.parent.rglob("*")) if p.is_file()][:HOLDER_FILES]
    found = {k: v for k, v in proctree.holders(paths + extra).items() if v}
    return proctree.describe_holders(found) if found else "no process holds any of the session's files\n"


class OwnChildren:
    """Linux: every child this process creates, by (pid, start time). ``subprocess`` (``_fork_exec``, and
    ``os.posix_spawn`` where it uses that), ``multiprocessing`` (``_posixsubprocess.fork_exec``, ``os.fork``),
    ``pty.fork`` (``os.forkpty``) and direct ``os.fork`` and ``os.posix_spawn[p]`` calls go through the functions
    wrapped here. A zombie child of the controller that is not recorded is an orphan it adopted as a subreaper.

    **Creation and recording are one step for the reaper.** The wrapper holds :attr:`lock` from before the creating call
    until the child is recorded, and :class:`Reaper` holds it for each whole pass. So a child that exits at once is
    never seen unrecorded: the reaper cannot take its exit status, and ``Popen.wait()`` reports it (review of #217,
    F1: before, a child that exited between the call's return and its recording was reaped, and ``wait()`` said 0).

    **What it cannot see** (review of #217, F2): a child created by C code that calls ``fork`` itself (a C extension,
    ``ctypes``), and ``os.system`` and ``os.popen``'s shell. Nothing in AEW or its tests creates children that way
    today; such a child would be reaped if it exited before its creator waited for it. :meth:`install` refuses to run
    when this Python's ``subprocess`` path cannot be wrapped (a private name gone), rather than silently recording
    nothing."""

    seam: Any = None  # tests only: called with the pid between the creating call and its recording

    def __init__(self) -> None:
        self.ids: set[tuple[int, int]] = set()
        self.lock = threading.RLock()
        self.reset_in_child = True  # tests only: False shows what a child inherits without the reset
        # A forked child gets a fresh lock: one another thread held at the fork (the reaper mid-pass, while some
        # path this cannot wrap forks) would otherwise stay held forever in the child (review of #217 at 9dc585a).
        mine = weakref.ref(self)

        def reset() -> None:
            own = mine()
            if own is not None and own.reset_in_child:
                own.lock = threading.RLock()

        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=reset)

    def add(self, pid: int) -> None:
        start = proctree.linux_start(pid)
        if start is not None:
            with self.lock:
                self.ids.add((pid, start))

    def __contains__(self, ident: object) -> bool:
        with self.lock:
            return ident in self.ids

    def _wrap(self, owner: Any, name: str, pid_of: Any) -> bool:
        original = getattr(owner, name, None)
        if original is None:
            return False
        if getattr(original, "_aew_own_children", False):
            return True

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with self.lock:  # the reaper waits: the child is recorded before it can be reaped
                out = original(*args, **kwargs)
                pid = pid_of(out)
                if pid:  # 0 in a forked child: nothing to record there
                    if self.seam is not None:
                        self.seam(pid)
                    self.add(pid)
                return out

        wrapper._aew_own_children = True  # type: ignore[attr-defined]
        setattr(owner, name, wrapper)
        return True

    def install(self) -> None:
        """Wrap every creating function this Python has. Refuses, before wrapping anything, when ``subprocess``'s own
        path cannot be wrapped: the reaper would then take the status of every child a test starts."""
        import _posixsubprocess  # type: ignore[import-not-found]

        def first(out: Any) -> int:
            return out[0] if isinstance(out, tuple) else out

        targets = [(subprocess, "_fork_exec"), (_posixsubprocess, "fork_exec")]
        targets += [(os, name) for name in ("fork", "forkpty", "posix_spawn", "posix_spawnp")]
        needed = [(subprocess, "_fork_exec"), (_posixsubprocess, "fork_exec"), (os, "fork")]
        if getattr(subprocess, "_USE_POSIX_SPAWN", False):
            needed.append((os, "posix_spawn"))
        missing = [f"{owner.__name__}.{name}" for owner, name in needed if getattr(owner, name, None) is None]
        if missing:
            raise RuntimeError(f"the session deadline cannot record this process's own children on this Python "
                               f"({sys.version.split()[0]}): {', '.join(missing)} not found. Its reaper would take "
                               "their exit status, so it refuses to start")
        for owner, name in targets:
            self._wrap(owner, name, first)


class Reaper:
    """Linux: a subreaper must reap what it adopts, as ``procs.py``'s session reaper does. Otherwise an orphan that
    exits (a supervisor whose launching CLI has already ended) stays a zombie of the controller, and every other
    process sees it alive: ``procs.pid_alive`` from a worker or an ``aew`` process reports a zombie that is not its own
    child as alive.

    A zombie child of the controller is reaped exactly when the controller did not create it (:class:`OwnChildren`):
    an adopted orphan, however soon after its birth its parent ended (review of #217: a launcher that crashed at once
    left its supervisor a zombie under the earlier first-seen rule). A child the controller created keeps its exit
    status for whoever waits for it. Each poll reads only the controller's children (``/proc/self/task/*/children``)."""

    def __init__(self, own: OwnChildren) -> None:
        self.own = own
        self.stop = threading.Event()
        self.reaped = 0

    def start(self) -> None:
        threading.Thread(target=self._run, name="aew-session-reaper", daemon=True).start()

    def poll(self) -> None:
        with self.own.lock:  # one whole pass: a child being created is recorded before or after it, never during
            self._poll()

    def _poll(self) -> None:
        for pid in proctree.linux_children():
            state = proctree.linux_state(pid)
            if state is None or state[0] != "Z" or (pid, state[1]) in self.own:
                continue
            try:
                if os.waitpid(pid, os.WNOHANG)[0] == pid:
                    self.reaped += 1
                    flight_recorder.record("reaped", child=pid)
            except ChildProcessError:
                pass

    def _run(self) -> None:
        gate = os.environ.get(REAP_GATE_ENV)  # a test of the reaper only: it starts when this file exists
        if gate:
            bounds.bounded_wait("session.reap_gate", lambda: Path(gate).exists(), seconds=600, poll_s=0.05,
                                gone=self.stop.is_set)
        while not self.stop.wait(REAP_POLL_S):  # bounded: it stops with the session (finish); a daemon thread
            try:
                self.poll()
            except OSError:
                continue


# ---------------------------------------------------------------------------------------------- the pytest side

def addoption(parser: Any) -> None:
    group = parser.getgroup("aew-lanes")
    group.addoption("--session-deadline", dest="aew_session_deadline", type=float, default=0.0, metavar="SECONDS",
                    help="end the session SECONDS after it starts, keeping every running test's autopsy, below the "
                         "CI job's own timeout (0: off; nothing is created without it)")
    group.addoption("--session-deadline-margin", dest="aew_session_deadline_margin", type=float,
                    default=bounds.DEADLINE_MARGIN_S, metavar="SECONDS",
                    help="how long after the deadline the controller acts under xdist, and the sentinel one more")


class Controller:
    def __init__(self, config: Any, seconds: float, margin: float) -> None:
        import watchdog

        self.config = config
        self.seconds = seconds
        self.margin = margin
        # The job's own absolute deadline (``AEW_JOB_DEADLINE``, set by the job's first step) caps the session's:
        # sessions that run one after another in one job then all end before the job's timeout (review of #217, M1).
        own_wall, job_wall = time.time() + seconds, job_deadline()
        self.wall = min(own_wall, job_wall or float("inf"))
        self.cause = (f"the CI job's deadline ({JOB_DEADLINE_ENV}, {seconds:g}s of --session-deadline not reached)"
                      if job_wall is not None and job_wall < own_wall else f"its --session-deadline ({seconds:g}s)")
        self.seconds = round(self.wall - time.time(), 1)
        self.mono = time.monotonic() + (self.wall - time.time())
        self.dir = watchdog.hang_dir(config) / "autopsy" / f"session-{os.getpid()}"
        self.distributed = _xdist_requested(config)
        self.me = proctree.identity(os.getpid())
        self.job: Any = None
        self.job_note = ""
        self.sentinel: subprocess.Popen[bytes] | None = None
        self.sentinel_id: tuple[int, int] | None = None
        self._once = threading.Lock()
        self._expired = False
        self._finished = threading.Event()
        self.exit_status: int | None = None
        self.reaper: Reaper | None = None

    # ------------------------------------------------------------------ start (pytest_configure, tryfirst)

    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.distributed:
            self.config.option.maxworkerrestart = "0"  # a worker that exits ends the run (the lanes pin it as well)
        job_name = None
        if proctree.IS_WINDOWS:  # pragma: windows-only
            self.job_note = proctree.outer_job()
            job_name = f"aew-session-{os.getpid()}-{secrets.token_hex(6)}"
            self.job = proctree.Job(job_name)
        else:
            self.job_note = "subreaper set" if proctree.set_child_subreaper() else "subreaper unavailable"
            if self.job_note == "subreaper set":  # before any child: the sentinel and every worker are recorded
                own = OwnChildren()
                own.install()
                self.reaper = Reaper(own)
        self.sentinel = self._spawn_sentinel(job_name)
        if self.reaper is not None:
            self.reaper.start()
        if self.job is not None:  # pragma: windows-only
            ready = marker(self.dir, READY)
            try:
                bounds.bounded_wait("session.sentinel_ready", ready.exists, seconds=SENTINEL_READY_S,
                                    gone=lambda: self.sentinel is not None and self.sentinel.poll() is not None)
            except bounds.BoundExpired:
                self.job_note += "; the sentinel did not open the job in time"
            try:
                self.job.assign_self()
                self.job_note += "; the session job was joined"
            except OSError as exc:  # recorded, not fatal: the thread-based deadline still runs
                self.job_note += f"; the session job could not be joined (winerror {getattr(exc, 'winerror', None)})"
                self.job = None
                # the sentinel's job is empty: it falls back to the controller's descendants by start time
                _write(self.dir, JOB_UNAVAILABLE, _stamp(self.job_note))
        _write(self.dir, STARTED, _stamp(f"{self.report_header()}; at {self.wall:.3f}, margin "
                                         f"{self.margin:g}s, {'xdist' if self.distributed else 'one process'}; "
                                         f"sentinel pid "
                                         f"{self.sentinel.pid if self.sentinel else None}"))
        threading.Thread(target=self._watch, name="aew-session-deadline", daemon=True).start()

    def _spawn_sentinel(self, job_name: str | None) -> subprocess.Popen[bytes]:
        args = {"deadline_wall": self.wall, "margin": self.margin, "controller": list(self.me or (os.getpid(), 0)),
                "dir": str(self.dir), "job": job_name}
        kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                                  "stderr": subprocess.DEVNULL, "close_fds": True}
        if proctree.IS_WINDOWS:  # pragma: windows-only
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "sentinel", json.dumps(args)],
                                **kwargs)
        self.sentinel_id = proctree.identity(proc.pid)
        flight_recorder.spawned(["session_deadline.py", "sentinel"], proc.pid)
        return proc

    def report_header(self) -> str:
        capped = "; capped by the CI job's deadline" if JOB_DEADLINE_ENV in self.cause else ""
        return f"aew session deadline: {self.seconds:g}s{capped}; {self.job_note}"

    # ------------------------------------------------------------------ the deadline

    def _watch(self) -> None:
        act_at = self.mono + (self.margin if self.distributed else 0.0)
        while not self._finished.wait(max(0.0, min(act_at - time.monotonic(), 60.0))):
            if time.monotonic() >= act_at:
                self.expire(from_thread=True)
                return

    def passed(self) -> bool:
        return time.monotonic() >= self.mono

    def members(self) -> list[proctree.Proc]:
        """The session's process set as it is now, without the controller and the sentinel."""
        skip = {i for i in (self.me, self.sentinel_id) if i}
        if self.job is not None:  # pragma: windows-only
            return [p for p in self.job.members() if p.identity not in skip and p.pid != os.getpid()]
        if self.me is None:
            return []
        return proctree.descendants(self.me, proctree.table(), exclude=[i for i in skip if i != self.me])

    def expire(self, *, from_thread: bool) -> None:
        with self._once:
            if self._expired or self._finished.is_set():
                return
            self._expired = True
            notes = []
            if not self.distributed:  # the one process runs the tests: the running test's autopsy
                import autopsy

                plugin = autopsy.current()
                if plugin is not None:
                    where = plugin.collect_current(f"the session deadline ({self.seconds:g}s) passed")
                    notes.append(f"the running test's autopsy: {where}")
            slow = float(os.environ.get(SLOW_COLLECT_ENV) or 0)
            if slow > 0:  # a test of the sentinel path only: a controller whose collect outlasts its margins
                time.sleep(min(slow, 600.0))  # bounded
            try:
                set_now = self.members()
                _write(self.dir, "controller-processes", proctree.describe(
                    set_now, title=f"the session's process set at the deadline ({self.job_note}):"))
                _write(self.dir, "controller-recorder.jsonl", flight_recorder.lines())
                _write(self.dir, "controller-file-holders", _holders_text(self.dir, flight_recorder.failed_paths()))
                import autopsy

                _write(self.dir, "controller-stacks", autopsy.thread_stacks())
            except Exception as exc:  # the marker and the ending still happen
                set_now = []
                notes.append(f"collecting failed: {type(exc).__name__}: {exc}")
            _write(self.dir, DEADLINE, _stamp(f"the session deadline ({self.seconds:g}s) passed; the controller "
                                              "collected and ends the other members\n" + "".join(
                                                  f"  {n}\n" for n in notes)))
            end = self.job.end if self.job is not None else proctree.end  # Windows: on one handle, in the job
            ended = [p.pid for p in proctree.children_first(set_now) if end(p.identity)]
            _write(self.dir, "controller-ended", _stamp(f"ended {len(ended)} of {len(set_now)} members: {ended}; "
                                                        f"{self.since_deadline()}"))
            self.exit_status = DEADLINE_EXIT
            if from_thread:
                self.finish()
                say(self.config, f"aew session deadline: the session reached {self.cause} and ended with exit "
                    f"{DEADLINE_EXIT}, before pytest could print its summary; the running test's autopsy and the "
                    f"markers are in {self.dir}")
                os._exit(DEADLINE_EXIT)

    def finish(self) -> None:
        """``session-finished``: the controller's last act on any normal exit, the deadline's included."""
        if self._finished.is_set():
            return
        self._finished.set()
        if self.reaper is not None:
            self.reaper.stop.set()
        _write(self.dir, FINISHED, _stamp(f"the session finished (exit {self.exit_status}); {self.since_deadline()}"))

    def since_deadline(self) -> str:
        """Where this moment sits against the deadline and the sentinel's: margin pressure shows before it bites."""
        now = time.monotonic()
        sentinel_at = self.mono + 2 * self.margin
        if now < self.mono:
            return f"{self.mono - now:.1f}s before the deadline"
        return (f"{now - self.mono:.1f}s after the deadline, {sentinel_at - now:.1f}s before the sentinel would act"
                if now < sentinel_at else f"{now - self.mono:.1f}s after the deadline, past the sentinel's time")

    # ------------------------------------------------------------------ the pytest hooks

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node: Any) -> None:
        node.workerinput[WORKER_KEY] = self.wall
        node.workerinput[DIR_KEY] = str(self.dir)

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodeready(self, node: Any) -> None:
        """Each worker, once ready: is it in the session's set? (Windows: in the job's list; Linux: a descendant by
        start time.) Kept in ``workers.txt``, the evidence that the job was joined before any worker started."""
        workerid = node.gateway.id
        try:
            pid = int(marker(self.dir, f"worker-{workerid}-pid").read_text(encoding="utf-8").split()[-1])
        except (OSError, ValueError, IndexError):
            _write(self.dir, "workers", _stamp(f"worker {workerid}: its pid was not recorded"), append=True)
            return
        if self.job is not None:  # pragma: windows-only
            inside = pid in self.job.pids()
            where = "the session job's list"
        else:
            inside = pid in {p.pid for p in self.members()}
            where = "the session's descendants by start time"
        _write(self.dir, "workers", _stamp(f"worker {workerid} pid {pid}: {'in' if inside else 'NOT in'} {where}"),
               append=True)

    def pytest_report_header(self, config: Any) -> str:
        return self.report_header()

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        """The same line at the end, where ``-q`` still shows it: a CI log records how the session's set was made
        (on Windows, how the session job nested under the runner's job)."""
        terminalreporter.write_line(self.report_header())

    @pytest.hookimpl(tryfirst=True)  # before the lane report is written with the session's exit status
    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        if self.passed():
            self.expire(from_thread=False)
            session.exitstatus = DEADLINE_EXIT
            say(self.config, f"aew session deadline: the session reached {self.cause}: exit {DEADLINE_EXIT}; "
                f"the markers are in {self.dir}")

    def pytest_unconfigure(self, config: Any) -> None:
        self.finish()


class Worker:
    """An xdist worker: at the absolute deadline, the running test's autopsy, then exit."""

    def __init__(self, config: Any, wall: float, directory: str) -> None:
        self.config = config
        self.mono = time.monotonic() + (wall - time.time())
        self.dir = Path(directory)
        self._done = threading.Event()

    def start(self) -> None:
        worker = self.config.workerinput.get("workerid", "?")
        _write(self.dir, f"worker-{worker}-pid", f"{os.getpid()}\n")
        threading.Thread(target=self._watch, name="aew-session-deadline", daemon=True).start()

    def _watch(self) -> None:
        while not self._done.wait(max(0.0, min(self.mono - time.monotonic(), 60.0))):
            if time.monotonic() >= self.mono:
                self.expire()
                return

    def expire(self) -> None:
        import autopsy

        worker = self.config.workerinput.get("workerid", "?")
        plugin = autopsy.current()
        where = plugin.collect_current("the session deadline passed") if plugin is not None else None
        _write(self.dir, f"worker-{worker}-deadline", _stamp(f"worker {worker} reached the deadline; the running "
                                                              f"test's autopsy: {where}"))
        os._exit(DEADLINE_EXIT)

    @pytest.hookimpl(wrapper=True, trylast=True)
    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> Any:
        """``worker-gwN-exit``: what could still keep this worker from exiting once its session is over (a non-daemon
        thread, a child process). xdist kills a worker that has not exited 10 s after teardown starts, and a killed
        worker loses what it had not written (its coverage, 2026-10-22), so this names the holder in the evidence. A
        wrapper, written in a ``finally``: another session-finish hook that raises cannot skip it (#232, F2)."""
        try:
            return (yield)
        finally:
            self._exit_note(exitstatus)

    def _exit_note(self, exitstatus: int) -> None:
        worker = self.config.workerinput.get("workerid", "?")
        try:
            threads = [f"{t.name} (target {getattr(t, '_target', None)!r})" for t in threading.enumerate()
                       if t.is_alive() and not t.daemon and t is not threading.main_thread()]
            children = [f"{p.pid} {p.cmdline or p.exe}" for p in proctree.table() if p.ppid == os.getpid()]
            note = (f"worker {worker} finished its session (exit {exitstatus}); non-daemon threads: "
                    f"{threads or 'none'}; child processes: {children or 'none'}")
        except Exception as exc:  # evidence on the way out never fails the exit (review of #232, F2)
            note = f"worker {worker} finished its session (exit {exitstatus}); collecting failed: {exc!r}"
        try:
            _write(self.dir, f"worker-{worker}-exit", _stamp(note))
        except OSError:
            pass  # the hang directory cannot be written: there is nowhere to say so

    def pytest_unconfigure(self, config: Any) -> None:
        self._done.set()


def say(config: Any, line: str) -> None:
    """One line where the run's output goes, written and flushed at once: it reaches the CI log even from a thread about
    to ``os._exit``. pytest's own terminal writer, since its capture holds the process's descriptors 1 and 2 while a
    test runs (a direct write to them would land in the capture and vanish); else the descriptor of stderr."""
    tr = config.pluginmanager.get_plugin("terminalreporter") if config is not None else None
    try:
        if tr is not None:
            capman = config.pluginmanager.get_plugin("capturemanager")
            if capman is not None:  # a test is running: its capture holds descriptors 1 and 2
                capman.suspend_global_capture(in_=False)
            tr.ensure_newline()
            tr.write_line(line)
            tr._tw.flush()
            return
    except Exception:  # noqa: BLE001, S110  (fall back to the descriptor)
        pass
    try:
        os.write(2, (line + "\n").encode("utf-8", "replace"))
    except OSError:
        pass


def job_deadline() -> float | None:
    """The CI job's absolute deadline for its sessions (epoch seconds, ``AEW_JOB_DEADLINE``), when the job set one."""
    raw = os.environ.get(JOB_DEADLINE_ENV, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _xdist_requested(config: Any) -> bool:
    return bool(getattr(config.option, "numprocesses", None))


def configure(config: Any) -> None:
    """``pytest_configure`` (``tryfirst``, from conftest): before xdist starts any worker."""
    worker_input = getattr(config, "workerinput", None)
    if worker_input is not None:
        if worker_input.get(WORKER_KEY):
            plugin: Any = Worker(config, float(worker_input[WORKER_KEY]), worker_input[DIR_KEY])
            config.pluginmanager.register(plugin, PLUGIN_NAME)
            plugin.start()
        return
    seconds = float(config.getoption("aew_session_deadline") or 0.0)
    if seconds <= 0:
        return  # nothing at all is created without --session-deadline
    plugin = Controller(config, seconds, float(config.getoption("aew_session_deadline_margin")))
    config.pluginmanager.register(plugin, PLUGIN_NAME)
    plugin.start()


# ---------------------------------------------------------------------------------------------- the sentinel

class Sentinel:
    def __init__(self, args: dict[str, Any]) -> None:
        self.dir = Path(args["dir"])
        self.margin = float(args["margin"])
        self.act_mono = time.monotonic() + (float(args["deadline_wall"]) + 2 * self.margin - time.time())
        self.controller = (int(args["controller"][0]), int(args["controller"][1]))
        self.me = proctree.identity(os.getpid())
        self.job: Any = None
        self.snapshot: list[proctree.Proc] = []
        if args.get("job"):  # pragma: windows-only
            self.job = proctree.Job.open(args["job"])
            _write(self.dir, READY, _stamp("the sentinel holds the session job"))

    def log(self, what: str) -> None:
        _write(self.dir, "sentinel-log", _stamp(what), append=True)

    def joined(self) -> bool:
        """The controller joined the job (else it wrote ``job-unavailable``, and the descendants rule applies)."""
        return self.job is not None and not marker(self.dir, JOB_UNAVAILABLE).exists()

    def members(self) -> list[proctree.Proc]:
        if self.joined():  # pragma: windows-only
            return self.job.members()
        return proctree.descendants(self.controller, proctree.table(), exclude=[self.me] if self.me else [])

    def refresh(self) -> None:
        if not self.joined() and proctree.same(self.controller):
            members = self.members()
            controller = next((p for p in proctree.table() if p.identity == self.controller), None)
            snapshot = ([controller] if controller else []) + members
            if {p.identity for p in snapshot} != {p.identity for p in self.snapshot}:
                # kept whenever it changes: the set the sentinel would end if the controller died now
                _write(self.dir, "sentinel-snapshot", proctree.describe(
                    snapshot, title="the session's set as the sentinel last saw it (Linux: refreshed every "
                                    f"{SNAPSHOT_EVERY_S:g}s while the controller lives):"))
            self.snapshot = snapshot

    def end_set(self, why: str) -> None:
        if self.joined():  # pragma: windows-only
            listed = self.job.members()
            _write(self.dir, f"sentinel-processes-{why}", proctree.describe(listed, title="the session job's members:"))
            _write(self.dir, f"sentinel-file-holders-{why}", _holders_text(self.dir, []))
            ok = self.job.terminate(DEADLINE_EXIT)
            self.log(f"TerminateJobObject ({why}): {'done' if ok else 'failed'}; {len(listed)} members")
            return
        alive = [p for p in self.snapshot if proctree.same(p.identity)]
        _write(self.dir, f"sentinel-processes-{why}", proctree.describe(
            alive, title="the session's set (the last snapshot's members whose pid and start time still match):"))
        _write(self.dir, f"sentinel-file-holders-{why}", _holders_text(self.dir, []))
        ended = [p.pid for p in proctree.children_first(alive) if proctree.end(p.identity)]
        self.log(f"ended {len(ended)} of {len(alive)} matching members ({why}): {ended}")

    def run(self) -> int:
        last_snapshot = 0.0
        hard_stop = self.act_mono + 120.0  # its own lifetime is bounded, whatever happens
        while time.monotonic() < hard_stop:
            if marker(self.dir, FINISHED).exists():  # the controller's last act on a normal exit
                return 0
            if not proctree.same(self.controller):
                _write(self.dir, ABNORMAL, _stamp("the controller is gone (by pid and start time) without "
                                                  "session-finished: ending the session's process set"))
                self.end_set("abnormal-exit")
                return 0
            if time.monotonic() >= self.act_mono:
                if not marker(self.dir, DEADLINE).exists():
                    _write(self.dir, DEADLINE, _stamp("written by the sentinel: the controller had not finished by "
                                                      "the deadline plus its margins (wedged, or holding the GIL)"))
                self.refresh()
                self.end_set("deadline")
                return 0
            if time.monotonic() - last_snapshot >= SNAPSHOT_EVERY_S:
                self.refresh()
                last_snapshot = time.monotonic()
            time.sleep(SENTINEL_POLL_S)  # bounded: the loop ends at hard_stop
        self.log("the sentinel's own lifetime bound passed")
        return 0


def sentinel_main(raw: str) -> int:
    args = json.loads(raw)
    try:
        return Sentinel(args).run()
    except Exception as exc:  # its own failure is written down, never silent (its stderr goes nowhere)
        _write(Path(args["dir"]), "sentinel-log", _stamp(f"the sentinel failed: {type(exc).__name__}: {exc}"),
               append=True)
        return 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["sentinel"]:
        sys.exit(sentinel_main(sys.argv[2]))
    sys.exit("usage: session_deadline.py sentinel <json>")
