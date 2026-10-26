"""Every wait a Lead broker's watchdog iteration reaches is one its bound counts, or is excused with its reason.

The class (CI on PR #281, the Windows serial lane): a wait inside a watchdog iteration that the iteration's bound does
not count. The bound is ``broker_liveness.wedge_threshold_s(lock_timeout, POLL_S)``, the ``wedge_after_s`` the broker
records and ``judge`` holds to: an iteration waits ``POLL_S`` on its stop event and up to the control store's lock
timeout for its read, and has one ``POLL_S`` left for its work. A superseded broker's watchdog also waited on the
history index (its authority check looked the archived credential up there), whose SQLite busy timeout, 30 s, the
bound does not count, so the broker closed late.

Two detectors, which must agree:
- **The census** (run time): each blocking call the watchdog thread makes, with the bound it was given, attributed to
  the AEW function that made it, while the watchdog iterates as the current Lead and then as a superseded one. A
  blocking call is ``sqlite3.connect`` or ``time.sleep`` (wrapped for the run), or one of ``PROFILED`` (Python-level
  waits, seen through a profiler on the watchdog thread alone). A call made inside another (the sleeps of a
  ``FileLock`` within its deadline) is the enclosing call's.
- **The scan** (source): each call of a name in ``BLOCKING``, and each ``with`` over one, in every AEW function the
  watchdog thread ran.

``WAITS`` holds every function the scan finds, and the table must be exact. Each is ``COUNTED`` (a term of the bound:
the census checks its bound against the term, derived), ``INSIDE`` (its waits sit within a counted wait's deadline),
``EXCUSED`` (why it does not count; ``after_outcome`` when it waits only once the iteration's outcome is recorded) or
``NO_WAIT`` (it names a blocking call without making one). It fails on a function the scan finds that ``WAITS`` does not
hold, an entry for one it does not find, a census wait whose function the scan does not find, a wait whose function
``WAITS`` holds as anything but ``COUNTED`` or ``EXCUSED``, a counted wait whose bound is not its term, and the total of
an iteration's counted bounds past the bound less one ``POLL_S`` of work.

What it does not see, each a defect the reviewer reads for:
- a ``with lock:`` over a lock that is no call (``with self._mu:``): a C lock's acquire is no call the profiler reports,
  nor one the scan names (``Beat.close``'s ``with self._mu`` waits for the beat thread's write);
- a stall inside a plain file read or write, and any wait in C code that ``WRAPPED`` does not wrap;
- the functions of an iteration this module does not run: a pending handoff, a store read that times out (the held-lock
  test's, ``test_notifier.py``), a non-writer's lock-free read;
- a name not in ``BLOCKING``, and a call made through a variable the scan cannot name.
"""

from __future__ import annotations

import ast
import functools
import inspect
import sqlite3
import sys
import textwrap
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import CodeType, FrameType
from typing import Any

import pytest
from notifier import takeover, until

import aew
from aew.engine.api import Engine
from aew.engine.authority import require_lead
from aew.engine.lock import FileLock
from aew.harness import broker_liveness, lead_broker

AEW_DIR = Path(aew.__file__).resolve().parent
COUNTED, INSIDE, EXCUSED, NO_WAIT = "counted", "inside", "excused", "no_wait"

# The names whose call blocks, as the scan reads them: a callee's last name (``self._stop.wait`` is ``wait``).
BLOCKING = frozenset({"FileLock", "Popen", "accept", "acquire", "communicate", "connect", "control_lock", "join",
                      "recv", "select", "session", "sleep", "start", "wait"})

# Every AEW function a watchdog iteration runs that the scan finds a blocking call in. The bound's terms carry the
# function that derives their value from the broker: the stop wait is ``POLL_S``, the store's read its lock timeout.
WAITS: dict[str, tuple[str, str]] = {
    "aew.harness.lead_broker:LeadBroker._watchdog": (COUNTED, "the stop wait between iterations: POLL_S"),
    "aew.engine.store:ControlStore.read": (COUNTED, "the read's control lock: the store's lock timeout"),
    "aew.engine.store:ControlStore.control_lock": (NO_WAIT, "makes the FileLock, untaken: its caller's with waits"),
    "aew.engine.lock:FileLock._wait": (INSIDE, "polls for the turnstile and the lock until FileLock.__enter__'s one "
                                               "deadline"),
    "aew.engine.faults:pause": (EXCUSED, "a test's fault point: it waits only while a test parks it (AEW_PAUSE)"),
    "aew.harness.bridge:BridgeServer.close": (EXCUSED, "starts the listener's wake thread: Thread.start returns once "
                                                       "that thread runs, after the bridge is marked closed"),
    "aew.harness.broker_liveness:Beat.close": (EXCUSED, "after_outcome: joins the beat thread once closed_at is "
                                                        "written"),
    "aew.util:replace_with_retry": (EXCUSED, "writes closed_at, once the bridge is closed: it sleeps only while "
                                             "Windows refuses the replace (a reader holds the record open for one "
                                             "read), up to its own 5 s, which the bound does not count"),
}
BOUNDS: dict[str, Callable[[Any], float]] = {
    "aew.harness.lead_broker:LeadBroker._watchdog": lambda broker: lead_broker.POLL_S,
    "aew.engine.store:ControlStore.read": lambda broker: broker.engine.store.lock_timeout,
}


@functools.cache
def _module(filename: str) -> str | None:
    """The AEW module ``filename`` holds, or None for any other file (cached: the profiler asks on every call)."""
    try:
        rel = Path(filename).resolve().relative_to(AEW_DIR)
    except (OSError, ValueError):
        return None
    parts = rel.with_suffix("").parts
    return ".".join(("aew", *parts[:-1])) if parts[-1] == "__init__" else ".".join(("aew", *parts))


def _aew_function(code: CodeType) -> str | None:
    """``module:qualname`` of AEW code, or None for any other."""
    module = _module(code.co_filename)
    return None if module is None else f"{module}:{code.co_qualname}"


def _caller(frame: FrameType | None) -> str | None:
    """The innermost AEW function at or above ``frame``."""
    while frame is not None:
        name = _aew_function(frame.f_code)
        if name is not None:
            return name
        frame = frame.f_back
    return None


@dataclass
class Wait:
    function: str | None  # the AEW function that made the call
    primitive: str
    bound: float | None  # None: unbounded
    iteration: int


# Python-level waits: the code that blocks, and the bound it was given (None: unbounded).
PROFILED: dict[CodeType, tuple[str, Callable[[FrameType], float | None]]] = {
    threading.Event.wait.__code__: ("Event.wait", lambda f: f.f_locals.get("timeout")),
    threading.Condition.wait.__code__: ("Condition.wait", lambda f: f.f_locals.get("timeout")),
    threading.Thread.join.__code__: ("Thread.join", lambda f: f.f_locals.get("timeout")),
    threading.Thread.start.__code__: ("Thread.start", lambda f: None),
    FileLock.__enter__.__code__: ("FileLock", lambda f: f.f_locals["self"].timeout),
}


@dataclass
class Census:
    ran: dict[str, CodeType] = field(default_factory=dict)
    waits: list[Wait] = field(default_factory=list)
    iteration: int = 0
    watch: int | None = None  # the watchdog thread's identifier
    broker: Any = None  # the bound's terms derive from it
    _depth: int = 0  # > 0 while a recorded wait is in progress: what it calls is inside it
    _codes: set[CodeType] = field(default_factory=set)

    def profile(self, frame: FrameType, event: str, arg: Any) -> None:
        if event == "call":
            code = frame.f_code
            if code not in self._codes:  # each function once: the profiler runs on every call
                self._codes.add(code)
                name = _aew_function(code)
                if name is not None:
                    self.ran[name] = code
            seen = PROFILED.get(code)
            if seen is not None:
                if self._depth == 0:
                    caller = _caller(frame.f_back)
                    if caller == "aew.harness.lead_broker:LeadBroker._watchdog" and seen[0] == "Event.wait":
                        self.iteration += 1  # an iteration starts with its stop wait
                    self.waits.append(Wait(caller, seen[0], seen[1](frame), self.iteration))
                self._depth += 1
        elif event == "return" and frame.f_code in PROFILED:
            self._depth -= 1

    def wrap(self, primitive: str, real: Callable[..., Any], bound: Callable[..., float | None]) -> Callable[..., Any]:
        @functools.wraps(real)
        def recorded(*args: Any, **kwargs: Any) -> Any:
            if threading.get_ident() == self.watch and self._depth == 0:
                self.waits.append(Wait(_caller(sys._getframe(1)), primitive, bound(*args, **kwargs), self.iteration))
            return real(*args, **kwargs)
        return recorded


def _text_join(callee: ast.expr) -> bool:
    """``"sep".join(...)`` or ``os.path.join(...)``: a ``join`` that joins text, not a thread."""
    if not (isinstance(callee, ast.Attribute) and callee.attr == "join"):
        return False
    receiver = callee.value
    return (isinstance(receiver, (ast.Constant, ast.JoinedStr))
            or (isinstance(receiver, ast.Attribute) and receiver.attr == "path"))


def scan(code: CodeType) -> set[str]:
    """The ``BLOCKING`` names the function of ``code`` calls, or enters a ``with`` over: its own body, not the
    functions nested in it (each is its own function, scanned when it runs)."""
    found: set[str] = set()
    if code.co_name.startswith("<"):  # a lambda's or a generator expression's source is only a fragment of a line
        return found
    fn = ast.parse(textwrap.dedent(inspect.getsource(code))).body[0]

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(child, ast.Call):
                callee = child.func
                name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", None)
                if name in BLOCKING and not _text_join(callee):
                    found.add(name)
            visit(child)

    visit(fn)
    return found


def run_census(project: Any, monkeypatch: pytest.MonkeyPatch, *, check: Callable[..., Any] | None = None) -> Census:
    """Watchdog iterations as the current Lead, then the superseded one after a takeover, with every wait recorded.
    ``check``: the watchdog's authority check in place of the broker's own (a planted control)."""
    census = Census()
    monkeypatch.setattr(lead_broker, "POLL_S", 0.25)  # the profiled thread idles between iterations
    if check is not None:
        monkeypatch.setattr(lead_broker, "require_held_lead", check)
    real = lead_broker.LeadBroker._watchdog

    def watched(self: lead_broker.LeadBroker) -> None:
        census.watch = threading.get_ident()
        sys.setprofile(census.profile)  # this thread's profiler alone
        try:
            real(self)
        finally:
            sys.setprofile(None)

    monkeypatch.setattr(lead_broker.LeadBroker, "_watchdog", watched)
    monkeypatch.setattr(sqlite3, "connect", census.wrap("sqlite3.connect", sqlite3.connect,
                                                         lambda *a, timeout=5.0, **k: timeout))
    monkeypatch.setattr(time, "sleep", census.wrap("time.sleep", time.sleep, lambda seconds: seconds))
    root = project.root / ".aew"
    broker = lead_broker.LeadBroker(Engine.discover(project.root), project.token)
    broker.start()
    try:
        # A generous window: the profiler slows each iteration's read, and this is no timing claim
        until(lambda: census.iteration >= 3, 60, "three watchdog iterations as the current Lead")
        current = census.iteration
        takeover(project, monkeypatch)
        until(lambda: (broker_liveness.read(root) or {}).get("closed_at"), 60, "the superseded broker's closed_at")
        assert broker.superseded and census.iteration > current
    finally:
        broker.close()
    census.broker = broker
    return census


def problems(census: Census) -> list[str]:
    """Everything the census and the scan disagree on, or find past the bound."""
    out: list[str] = []
    found = {name: names for name, code in census.ran.items() if (names := scan(code))}
    out += [f"{name} makes a blocking call ({', '.join(sorted(names))}) that WAITS does not hold"
            for name, names in sorted(found.items()) if name not in WAITS]
    out += [f"WAITS holds {name}, which no watchdog iteration ran or which makes no blocking call"
            for name in sorted(WAITS) if name not in found]
    broker = census.broker
    counted: dict[int, float] = {}
    for wait in census.waits:
        where = f"{wait.primitive} (bound {wait.bound}) from {wait.function}, iteration {wait.iteration}"
        if wait.function not in found:
            out.append(f"{where}: the scan finds no blocking call there (BLOCKING misses a name)")
            continue
        kind, _ = WAITS.get(wait.function, (None, ""))
        if kind == COUNTED:
            term = BOUNDS[wait.function](broker)
            if wait.bound is None or wait.bound != pytest.approx(term):
                out.append(f"{where}: a counted wait whose bound is not its term, {term}")
            counted[wait.iteration] = counted.get(wait.iteration, 0.0) + (wait.bound or 0.0)
        elif kind != EXCUSED:
            out.append(f"{where}: not a wait the bound counts, nor one WAITS excuses")
    bound = broker_liveness.wedge_threshold_s(broker.engine.store.lock_timeout, lead_broker.POLL_S)
    out += [f"iteration {i} waits {total} s in counted waits, past the bound less one POLL_S of work"
            for i, total in sorted(counted.items()) if total > bound - lead_broker.POLL_S + 1e-9]
    return out


def test_every_wait_a_watchdog_iteration_reaches_is_counted_by_its_bound_or_excused(project, monkeypatch):
    census = run_census(project, monkeypatch)
    assert {w.primitive for w in census.waits} >= {"Event.wait", "FileLock"}, census.waits  # the census sees waits
    assert not problems(census), "\n".join(problems(census))


def test_an_authority_check_that_reads_the_archive_is_found_waiting_on_the_history_index(project, monkeypatch):
    """The planted control, main's defect: the watchdog's check looking a superseded credential up in the archive."""
    engine = Engine.discover(project.root)
    found = problems(run_census(project, monkeypatch, check=lambda state, token: require_lead(
        state, token, archived=engine.archived_credential)))
    assert any("aew.history.index:HistoryIndex._db makes a blocking call (connect)" in p for p in found), found
    waited = "sqlite3.connect (bound 30.0) from aew.history.index:HistoryIndex._db"
    assert any(p.startswith(waited) for p in found), found


@pytest.mark.parametrize(("body", "names"), [
    ("def f(p):\n    return sqlite3.connect(p, timeout=30.0)\n", {"connect"}),
    ("def f(self):\n    with self.k.store.control_lock('x'):\n        pass\n", {"control_lock"}),
    ("def f(self):\n    while not self._stop.wait(1.0):\n        pass\n", {"wait"}),
    ("def f():\n    def g():\n        time.sleep(1)\n    return g\n", set()),  # g is its own function
])
def test_the_scan_names_each_blocking_call_in_a_function_body(tmp_path, body, names):
    path = tmp_path / "planted.py"
    path.write_bytes(body.encode())
    namespace: dict[str, Any] = {}
    exec(compile(body, str(path), "exec"), namespace)  # noqa: S102  a planted function, compiled from its file
    assert scan(namespace["f"].__code__) == names


def test_a_with_over_a_lock_that_is_no_call_is_not_seen(tmp_path):
    """Pinned (the module docstring): ``with self._mu:`` waits, and neither detector sees it."""
    body = "def f(self):\n    with self._mu:\n        pass\n"
    path = tmp_path / "planted.py"
    path.write_bytes(body.encode())
    namespace: dict[str, Any] = {}
    exec(compile(body, str(path), "exec"), namespace)  # noqa: S102  a planted function, compiled from its file
    assert scan(namespace["f"].__code__) == set()
