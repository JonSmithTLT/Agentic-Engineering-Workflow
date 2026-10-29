"""A hang or a deadline explains itself the first time, from the kept files alone (the hang-and-flake diagnosis plan,
G3 H1-H4, its G3a acceptance).

Each test runs an inner pytest session in a scratch project (as the hang watchdog's own tests do) with the
real helpers, and judges only by what the session left under its hang directory: the autopsy, the session deadline's
markers and the sentinel's records. Every process any of them starts has no window (``CREATE_NO_WINDOW``), and every
wait is bounded and ends on an event (a file, a process's end), never on a sleep.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import bounds
import lanes
import proctree
import pytest
from conftest import IS_WINDOWS
from racing_read import read_text_or_none

HELPERS = Path(lanes.__file__).resolve().parent
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
DEADLINE_EXIT = 70
# The margin the lanes run their session deadline with. Where the controller's own exit is what a test checks, the
# sentinel acts only two of these after the deadline, so a runner slow to collect is not ended for it (a Windows run
# of 2026-10-24, under 3 s margins). A test of the sentinel acting sets its own small margin.
MARGIN = f"{bounds.DEADLINE_MARGIN_S:g}"

CONFTEST = f'''
import sys
sys.path.insert(0, {str(HELPERS)!r})
import pytest
import autopsy, harness_diagnostics, lanes, session_deadline, watchdog


def pytest_addoption(parser):
    lanes.addoption(parser)
    watchdog.addoption(parser)
    session_deadline.addoption(parser)
    harness_diagnostics.addoption(parser)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    session_deadline.configure(config)
    lanes.configure(config)
    watchdog.configure(config)
    autopsy.configure(config)
'''


def project(tmp_path: Path, tests: str, files: dict[str, str] | None = None, conftest_extra: str = "") -> Path:
    root = tmp_path / "proj"
    (root / "tests" / "integration").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "tests" / "conftest.py").write_text(CONFTEST + conftest_extra, encoding="utf-8")
    (root / "tests" / "integration" / "test_x.py").write_text(tests, encoding="utf-8")
    for name, text in (files or {}).items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_"))}


def inner(proj: Path, hangs: Path, *args: str, timeout: float = 240,
          extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--hang-dir", str(hangs),
                           *args, "tests"], cwd=proj, env={**env(), **(extra_env or {})}, capture_output=True,
                          text=True, timeout=timeout, **NO_WINDOW)


def start_inner(proj: Path, hangs: Path, *args: str) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--hang-dir", str(hangs),
                             *args, "tests"], cwd=proj, env=env(), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, text=True, **NO_WINDOW)


def texts(directory: Path, pattern: str = "*") -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(directory.rglob(pattern))
                     if p.is_file())


def autopsy_of(hangs: Path, test: str) -> Path:
    prefix = f"tests_integration_test_x.py_{test}-"
    found = [d for d in (hangs / "autopsy").iterdir() if d.is_dir() and d.name.startswith(prefix)]
    assert len(found) == 1, sorted(p.name for p in (hangs / "autopsy").iterdir())
    return found[0]


def session_dir(hangs: Path) -> Path:
    found = sorted((hangs / "autopsy").glob("session-*"))
    assert len(found) == 1, found
    return found[0]


def sentinel_ends(session: Path) -> None:
    """The sentinel has gone (by its pid and start time), so nothing holds the scratch directory open."""
    started = (session / "session-started.txt").read_text(encoding="utf-8")
    pid = int(re.search(r"sentinel pid (\d+)", started).group(1))  # type: ignore[union-attr]
    ident = proctree.identity(pid)
    if ident is not None:
        bounds.bounded_wait("test.sentinel_exits", lambda: not proctree.same(ident), seconds=60)


def unrelated() -> subprocess.Popen[bytes]:
    """A process started outside the inner session: nothing the session does may end it."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], **NO_WINDOW)


# ---------------------------------------------------------------------------------------------- a hung test (H1)

CHILD = '''import os, threading


def listen():
    raise RuntimeError("the listener died: synthetic, before its first message")


def block_on_pipe():
    r, w = os.pipe()
    print("child ready", flush=True)
    os.read(r, 1)  # a C-level call nobody will answer


threading.Thread(target=listen, name="listener").start()
block_on_pipe()
'''

HUNG = '''import sys, threading
from pathlib import Path

import autopsy, bounds, childdiag, pytest


@pytest.mark.autopsy
def test_waits_for_an_event_that_never_comes(tmp_path):
    where = autopsy.child_dir()
    child = childdiag.spawn([sys.executable, str(Path(__file__).parent.parent.parent / "child_helper.py")], where,
                            interval=1)
    try:
        # by event: the child has dumped its stacks once, blocked, and its listener's death is on record
        bounds.bounded_wait("inner.child_dumped", lambda: any(
            "block_on_pipe" in p.read_text(encoding="utf-8", errors="replace") for p in where.glob("stacks-*.txt"))
            and any(where.glob("events-*.jsonl")), seconds=60, gone=lambda: child.poll() is not None)
        never = threading.Event()
        assert never.wait(12), "the event never came"
    finally:
        child.kill()
        child.wait(30)
'''


def test_a_hung_test_names_its_blocked_frame_the_childs_blocked_frame_and_the_dead_thread(tmp_path):
    """The deliberately hung test: the test process waits on an event that never comes, a child Python helper is
    blocked in a C call (``os.read`` on a pipe), and a child thread died of an uncaught exception. The autopsy names all
    three from its files alone."""
    hangs = tmp_path / "hangs"
    proc = inner(project(tmp_path, HUNG, {"child_helper.py": CHILD}), hangs, "--test-timeout", "4", "-p", "no:xdist")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "aew autopsy" in out, out  # the failure names its autopsy directory
    kept = autopsy_of(hangs, "test_waits_for_an_event_that_never_comes")
    stacks = texts(kept, "stacks.*")
    assert "test_waits_for_an_event_that_never_comes" in stacks and "never.wait(12)" in stacks, stacks
    child_stacks = texts(kept / "children", "stacks-*")
    assert "block_on_pipe" in child_stacks, child_stacks  # faulthandler's C thread dumped it during the block
    events = texts(kept / "children", "events-*")
    assert "thread_exception" in events and '"listener"' in events, events
    assert "the listener died: synthetic" in events and "in listen" in events, events
    assert "child ready" in texts(kept / "children", "out-*")  # its output was kept
    assert not list(hangs.rglob("*.json"))  # nothing an assurance tool would read as a lane report


# ---------------------------------------------------------------------------------------------- the file holder

HOLDER = '''import os, subprocess, sys

import bounds, flight_recorder, pytest

NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


@pytest.fixture
def holder(tmp_path):
    """Another process holding the state file open, until after the failure is reported (teardown)."""
    target, ready = tmp_path / "state.txt", tmp_path / "ready"
    target.write_text("old", encoding="utf-8")
    code = (f"import pathlib, time; f = open({str(target)!r}, 'a'); pathlib.Path({str(ready)!r}).write_text('1'); "
            "time.sleep(120)")
    proc = subprocess.Popen([sys.executable, "-c", code], **NO_WINDOW)
    bounds.bounded_wait("inner.holder_ready", ready.exists, seconds=60, gone=lambda: proc.poll() is not None)
    yield target
    proc.kill()
    proc.wait(30)


@pytest.mark.autopsy
def test_cannot_replace_a_file_another_process_holds(tmp_path, holder):
    new = tmp_path / "state.tmp"
    new.write_text("new", encoding="utf-8")
    try:
        os.replace(new, holder)
        # POSIX lets a replace through an open file: the failure is simulated there, the holder lookup is real
        flight_recorder.io("replace", holder, PermissionError(13, "simulated: POSIX replaced an open file"))
    except PermissionError as exc:
        flight_recorder.io("replace", holder, exc)
    pytest.fail("the state file could not be replaced")
'''


def test_a_file_another_process_holds_is_named_with_its_holder(tmp_path):
    hangs = tmp_path / "hangs"
    root = project(tmp_path, HOLDER)
    proc = inner(root, hangs, "-p", "no:xdist")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    kept = autopsy_of(hangs, "test_cannot_replace_a_file_another_process_holds")
    holders = texts(kept, "file-holders.*")
    assert "state.txt" in holders and "held by pid" in holders, holders
    pids = {int(p) for p in re.findall(r"held by pid (\d+)", holders)}
    tree = texts(kept, "processes.*")
    assert any(re.search(rf"^\s*{pid}\s", tree, re.M) for pid in pids), (holders, tree)  # a process of the test's


# ---------------------------------------------------------------------------------------------- the session deadline

OUTLIVES = '''import threading

import pytest


@pytest.mark.autopsy
def test_outlives_the_session():
    threading.Event().wait(120)
'''


def test_a_test_that_outlives_the_session_deadline_leaves_its_autopsy_and_the_controller_exits_by_itself(tmp_path):
    hangs = tmp_path / "hangs"
    proc = inner(project(tmp_path, OUTLIVES), hangs, "--session-deadline", "5", "--session-deadline-margin", MARGIN,
                 "-p", "no:xdist")
    assert proc.returncode == DEADLINE_EXIT, proc.stdout + proc.stderr
    session = session_dir(hangs)
    sentinel_ends(session)
    names = {p.name for p in session.iterdir()}
    assert {"session-started.txt", "session-deadline.txt", "session-finished.txt"} <= names, names
    assert not any(n.startswith("sentinel-processes") for n in names), names  # the controller was not ended
    assert "abnormal-exit.txt" not in names
    kept = autopsy_of(hangs, "test_outlives_the_session")
    assert "the session deadline (5s) passed" in texts(kept, "reason*")
    assert "test_outlives_the_session" in texts(kept, "stacks.*")
    # pytest prints no summary after the deadline's exit: the session says why itself (review of #217)
    said = proc.stdout + proc.stderr
    assert "aew session deadline: the session reached its --session-deadline (5s)" in said, said
    assert "before pytest could print its summary" in said, said


def test_the_ci_jobs_deadline_caps_the_session_and_the_exit_names_it(tmp_path):
    """Review of #217 (the `core` job's serial step ended with exit 70 and no summary): ``AEW_JOB_DEADLINE``, the job's
    own deadline, caps a session whose ``--session-deadline`` is later, and the exit names that cause on stderr."""
    import time

    hangs = tmp_path / "hangs"
    proc = inner(project(tmp_path, OUTLIVES), hangs, "--session-deadline", "600", "--session-deadline-margin", "3",
                 "-p", "no:xdist", extra_env={"AEW_JOB_DEADLINE": str(int(time.time()) + 6)})
    assert proc.returncode == DEADLINE_EXIT, proc.stdout + proc.stderr
    assert "the session reached the CI job's deadline (AEW_JOB_DEADLINE" in proc.stdout + proc.stderr, proc.stdout
    session = session_dir(hangs)
    sentinel_ends(session)
    assert "capped by the CI job's deadline" in texts(session, "session-started*")


SESSION_SET = '''import os, subprocess, sys, threading
from pathlib import Path

import bounds

OUT = Path(os.environ["G3_OUT"])
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
SLEEP = [sys.executable, "-c", "import time; time.sleep(300)"]
DETACH = ("import os, sys, pathlib; from aew.harness.procs import spawn_detached; "
          "p = spawn_detached(sys.argv[2:], env=dict(os.environ)); pathlib.Path(sys.argv[1]).write_text(str(p.pid))")


def test_records_its_worker():
    (OUT / f"worker-{os.getpid()}").write_text("1", encoding="utf-8")


def test_spawns_a_detached_supervisor_and_hangs():
    (OUT / f"worker-{os.getpid()}").write_text("1", encoding="utf-8")
    # the supervisor's own launcher exits at once: only containment (the job, the subreaper) still holds it
    subprocess.run([sys.executable, "-c", DETACH, str(OUT / "supervisor.pid"), *SLEEP], check=True, timeout=60,
                   **NO_WINDOW)
    child = subprocess.Popen(SLEEP, **NO_WINDOW)
    (OUT / "child.pid").write_text(str(child.pid), encoding="utf-8")
    threading.Event().wait(120)
'''


def alive_identity(path: Path) -> tuple[int, int]:
    ident = proctree.identity(int(path.read_text(encoding="utf-8")))
    assert ident is not None, f"{path.name}: already gone"
    return ident


@pytest.mark.parametrize("mode", [("-p", "no:xdist"), ("-n", "2", "--max-worker-restart", "0")],
                         ids=["one_process", "xdist"])
def test_the_deadline_ends_only_the_sessions_own_processes(tmp_path, monkeypatch, mode):
    """A session with a detached supervisor (``spawn_detached``, whose launcher already exited) and an unrelated
    process started outside it hits its deadline: the supervisor is listed and ended, the unrelated process lives.
    Under xdist, every worker was in the session's set from its start (Windows: the job's list)."""
    hangs, out = tmp_path / "hangs", tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("G3_OUT", str(out))
    other = unrelated()
    try:
        other_id = proctree.identity(other.pid)
        assert other_id is not None
        # The deadline counts from the session's start, so it leaves room for xdist's workers to start cold; the
        # margin leaves the controller time to finish after its workers exit, before the sentinel would act (an
        # earlier 3 s margin let a slow controller be ended by the sentinel, which is that path working, not this).
        deadline = "20" if "-n" in mode else "8"
        proc = inner(project(tmp_path, SESSION_SET), hangs, "--session-deadline", deadline,
                     "--session-deadline-margin", MARGIN, *mode)
        session = session_dir(hangs)
        why = f"{proc.stdout}{proc.stderr}\n--- kept files:\n{texts(session)}"
        assert proc.returncode == DEADLINE_EXIT, why
        sentinel_ends(session)
        assert (out / "supervisor.pid").exists(), why
        supervisor = int((out / "supervisor.pid").read_text(encoding="utf-8"))
        listed = texts(session, "controller-processes*")
        assert re.search(rf"^\s*{supervisor}\s", listed, re.M), why  # the detached supervisor was in the set
        assert proctree.identity(supervisor) is None, why  # and was ended
        assert proctree.identity(int((out / "child.pid").read_text(encoding="utf-8"))) is None, why
        assert proctree.same(other_id)  # the unrelated process survives
        assert "session-finished.txt" in {p.name for p in session.iterdir()}, why
        if "-n" in mode:
            workers = texts(session, "workers*")
            assert workers.count(" in the session") == 2 and "NOT in" not in workers, why
    finally:
        other.kill()
        other.wait(30)


CRASH = '''import os


def test_a_worker_dies():
    os._exit(3)


def test_later():
    pass
'''


def test_a_worker_crash_ends_the_run_and_leaves_the_crashed_tests_autopsy(tmp_path):
    hangs = tmp_path / "hangs"
    proc = inner(project(tmp_path, CRASH), hangs, "-n", "1", "--max-worker-restart", "0", "--session-deadline", "120")
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "crashed while running 'tests/integration/test_x.py::test_a_worker_dies'" in out, out
    assert "1 failed" in out and "passed" not in out, out  # no replacement worker ran test_later: the run ended
    kept = autopsy_of(hangs, "test_a_worker_dies")
    assert "its xdist worker crashed" in texts(kept, "reason*")
    assert "went down" in texts(hangs / "autopsy", "worker-*-down*")
    sentinel_ends(session_dir(hangs))


ABNORMAL = '''import os, subprocess, sys, threading
from pathlib import Path

OUT = Path(os.environ["G3_OUT"])
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def test_waits_while_its_controller_is_killed():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], **NO_WINDOW)
    (OUT / "child.pid").write_text(str(child.pid), encoding="utf-8")
    (OUT / "controller.pid.part").write_text(str(os.getpid()), encoding="utf-8")
    os.replace(OUT / "controller.pid.part", OUT / "controller.pid")  # last, and whole: the outer test waits on it
    threading.Event().wait(200)
'''


def test_a_controller_killed_abruptly_leaves_no_session_process_alive(tmp_path, monkeypatch):
    """Q1: the controller dies before the deadline without ``session-finished`` (killed from outside). The sentinel
    writes ``abnormal-exit`` and ends the set; an unrelated process still survives."""
    hangs, out = tmp_path / "hangs", tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("G3_OUT", str(out))
    other = unrelated()
    session = start_inner(project(tmp_path, ABNORMAL), hangs, "--session-deadline", "150", "-p", "no:xdist")
    try:
        other_id = proctree.identity(other.pid)
        assert other_id is not None
        # controller.pid is the inner test's last file, so both are there (a CI run of 2026-10-24 waited for
        # child.pid alone and read controller.pid before it was written)
        bounds.bounded_wait("test.inner_started", lambda: (out / "controller.pid").exists(), seconds=120,
                            gone=lambda: session.poll() is not None)
        child = alive_identity(out / "child.pid")
        controller = alive_identity(out / "controller.pid")
        sdir = session_dir(hangs)
        if not IS_WINDOWS:  # by event: the sentinel's snapshot (its view of the set on Linux) includes the child
            snapshot = sdir / "sentinel-snapshot.txt"
            bounds.bounded_wait("test.snapshot_has_child", lambda: re.search(
                rf"^\s*{child[0]}\s", read_text_or_none(snapshot) or "", re.M), seconds=60)
        assert proctree.end(controller)  # abrupt: no hook runs
        bounds.bounded_wait("test.abnormal_exit", lambda: (sdir / "abnormal-exit.txt").exists(), seconds=60)
        sentinel_ends(sdir)
        assert not proctree.same(child)  # the session's process was ended
        assert proctree.same(other_id)  # the unrelated one was not
        assert "session-finished.txt" not in {p.name for p in sdir.iterdir()}
        assert any(p.name.startswith("sentinel-processes-abnormal-exit") for p in sdir.iterdir())
    finally:
        session.kill()
        session.wait(60)
        other.kill()
        other.wait(30)


def test_without_a_session_deadline_nothing_is_created(tmp_path):
    hangs = tmp_path / "hangs"
    proc = inner(project(tmp_path, "def test_ok():\n    pass\n"), hangs, "-p", "no:xdist")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not list(hangs.glob("autopsy/session-*"))
    assert "aew session deadline" not in proc.stdout


HELD_OPEN = '''import threading
from pathlib import Path

RELEASED = Path(__file__).with_name("released")


def hold():
    threading.Event().wait(40)
    RELEASED.write_text("1")  # only a worker that was not killed gets here


def test_leaves_a_thread_that_holds_its_worker_open():
    # Non-daemon, so the worker cannot exit when its session ends: past xdist's 10 s exit wait, teardown kills it.
    threading.Thread(target=hold, name="holder").start()
'''

SAVE_WORKER_COVERAGE = '''
from worker_coverage import pytest_sessionfinish  # the suite's own hook, as tests/conftest.py imports it
'''

# Another session-finish implementation that raises, in the worker only: pluggy then skips the plain implementations
# after it, which a save among them would be (review of #232, F2).
RAISES_AT_FINISH = '''
def pytest_sessionfinish(session):
    if getattr(session.config, "workerinput", None) is not None:
        raise RuntimeError("synthetic: a session-finish hook failed")
'''


@pytest.mark.parametrize("finish", ["clean", "a_hook_raises"])
def test_a_worker_killed_at_teardown_keeps_its_coverage_and_names_what_held_it(tmp_path, finish):
    """The 2026-10-22 gate drop: a worker that has not exited 10 s after teardown starts is killed, and its coverage
    (saved at exit) was lost. Saved at the end of its session (``worker_coverage``), it is kept, even when another
    session-finish hook raises; and the worker's exit note names the non-daemon thread that held it open."""
    files = {".coveragerc": "[run]\nparallel = true\npatch = subprocess\n"}
    if finish == "a_hook_raises":
        files["tests/integration/conftest.py"] = RAISES_AT_FINISH
    proj = project(tmp_path, HELD_OPEN, files=files, conftest_extra=SAVE_WORKER_COVERAGE)
    hangs, data = tmp_path / "hangs", tmp_path / "cov"
    data.mkdir()
    clean = {k: v for k, v in env().items() if not k.startswith("COVERAGE_")}  # this session's own coverage, if any
    proc = subprocess.run([sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "--hang-dir", str(hangs), "-n", "1", "--max-worker-restart", "0", "--session-deadline",
                           "120", "tests"], cwd=proj, env={**clean, "COVERAGE_FILE": str(data / ".coverage")},
                          capture_output=True, text=True, timeout=240, **NO_WINDOW)
    why = proc.stdout + proc.stderr
    assert "1 passed" in proc.stdout, why
    assert not (proj / "tests" / "integration" / "released").exists(), "the worker was not killed: nothing was tested"
    session = session_dir(hangs)
    pid = (session / "worker-gw0-pid.txt").read_text(encoding="utf-8").strip()
    assert "holder" in (session / "worker-gw0-exit.txt").read_text(encoding="utf-8"), why
    assert [p.name for p in data.iterdir() if f".pid{pid}." in p.name], sorted(p.name for p in data.iterdir())
    sentinel_ends(session)


ORPHAN = '''import os, subprocess, sys, time
from pathlib import Path

NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
OUT = Path(os.environ["G3_OUT"])
# The orphan waits for its exit file (bounded); its launcher ends at once, so it is adopted before anyone sees it.
ORPHAN = ("import pathlib, sys, time; p = pathlib.Path(sys.argv[1]); d = time.monotonic() + 60\\n"
          "while not p.exists() and time.monotonic() < d:\\n    time.sleep(0.02)\\n")
LAUNCH = ("import subprocess, sys; d = subprocess.DEVNULL; p = subprocess.Popen([sys.executable, '-c', sys.argv[1], "
          "sys.argv[2]], start_new_session=True, stdin=d, stdout=d, stderr=d); print(p.pid, flush=True)")
ALIVE = "import sys; from aew.harness.procs import pid_alive; print(pid_alive(int(sys.argv[1])))"


def alive_elsewhere(pid):
    """As another process (an `aew` command, a worker) sees it: never this one, which would reap its own zombie."""
    out = subprocess.run([sys.executable, "-c", ALIVE, str(pid)], capture_output=True, text=True, check=True,
                         timeout=60, **NO_WINDOW)
    return out.stdout.strip() == "True"


def test_an_orphan_adopted_at_once_that_exits_is_seen_gone():
    exit_file = OUT / "orphan-exit"
    pid = int(subprocess.run([sys.executable, "-c", LAUNCH, ORPHAN, str(exit_file)], capture_output=True, text=True,
                             check=True, timeout=60, **NO_WINDOW).stdout)  # the launcher has ended: adopted already
    gate = os.environ.get("G3_TEST_REAP_GATE")
    if gate:
        Path(gate).write_text("1", encoding="utf-8")  # only now does the reaper look: it never saw another parent
    exit_file.write_text("1", encoding="utf-8")  # by event: the orphan ends now
    deadline = time.monotonic() + 30
    while alive_elsewhere(pid) and time.monotonic() < deadline:
        time.sleep(0.2)  # bounded: the deadline above
    assert not alive_elsewhere(pid)
'''


@pytest.mark.parametrize("mode", [("-p", "no:xdist"), ("-n", "1")], ids=["one_process", "xdist"])
def test_an_orphan_adopted_at_once_and_ended_is_seen_gone_by_every_process(tmp_path, monkeypatch, mode):
    """Linux: the controller is a subreaper, so a detached process whose launcher already ended is re-parented to it.
    When that orphan exits, the controller must reap it, or it stays a zombie that ``procs.pid_alive`` in any other
    process (a worker, an ``aew`` command) reports as alive. Liveness is judged from a separate process.

    The case CI met (review of #217: a launcher that crashed at once): the orphan is adopted before the reaper ever
    sees it, which the test makes certain by events (the reaper's start waits for a gate the test opens after the
    launcher ended). The earlier rule, which reaped only a zombie it had seen with another parent, fails this test;
    the controller now knows every child it created (``OwnChildren``) and reaps any other. The same test holds on
    Windows, where nothing is re-parented."""
    hangs, out = tmp_path / "hangs", tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("G3_OUT", str(out))
    monkeypatch.setenv("G3_TEST_REAP_GATE", str(out / "reap-gate"))
    proc = inner(project(tmp_path, ORPHAN), hangs, "--session-deadline", "120", *mode)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    sentinel_ends(session_dir(hangs))


OWN_CHILD = '''

import os, subprocess, sys


def pytest_sessionstart(session):
    if not hasattr(session.config, "workerinput"):  # the controller's own child, which it waits for later
        session.config.g3_child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])


def pytest_sessionfinish(session):
    if not hasattr(session.config, "workerinput"):
        rc = session.config.g3_child.wait(timeout=60)
        with open(os.path.join(os.environ["G3_OUT"], "rc"), "w", encoding="utf-8") as fh:
            fh.write(str(rc))
'''


@pytest.mark.parametrize("mode", [("-p", "no:xdist"), ("-n", "1")], ids=["one_process", "xdist"])
def test_the_reaper_never_takes_the_status_of_a_child_the_controller_started(tmp_path, monkeypatch, mode):
    """Review of #217, m1: a child the controller started itself, and waits for after it exited, keeps its exit
    status: the reaper takes only orphans it saw adopted, never the controller's own children (before the fix, under
    xdist, ``wait()`` returned 0 for a child that exited 3)."""
    hangs, out = tmp_path / "hangs", tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("G3_OUT", str(out))
    tests = "import time\n\n\ndef test_lets_the_reaper_poll():\n    time.sleep(1)  # several reaper polls\n"
    proc = inner(project(tmp_path, tests, conftest_extra=OWN_CHILD), hangs, "--session-deadline", "120", *mode)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "rc").read_text(encoding="utf-8") == "3"
    sentinel_ends(session_dir(hangs))


LEAKS = '''import os, subprocess, sys
from pathlib import Path

import pytest

NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def test_leaves_a_process(tmp_path):
    script = tmp_path / "sleeper.py"
    script.write_text("import time\\ntime.sleep(120)\\n", encoding="utf-8")
    child = subprocess.Popen([sys.executable, str(script)], cwd=tmp_path, **NO_WINDOW)  # never ended: the leak
    (Path(os.environ["G3_OUT"]) / "leaked.pid").write_text(str(child.pid), encoding="utf-8")


@pytest.fixture
def managed(tmp_path):
    """A process a fixture starts and ends in its teardown, as HarnessLab does: never a leak."""
    script = tmp_path / "managed.py"
    script.write_text("import time\\ntime.sleep(120)\\n", encoding="utf-8")
    # the base interpreter, not a venv's launcher: ending it ends the one process
    proc = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), str(script)], cwd=tmp_path,
                            **NO_WINDOW)
    (Path(os.environ["G3_OUT"]) / "managed.pid").write_text(str(proc.pid), encoding="utf-8")
    yield proc
    proc.kill()
    proc.wait(30)


def test_uses_a_process_its_fixture_ends(managed):  # the module's last test: its teardown precedes the scan
    assert managed.poll() is None
'''


def test_a_process_a_test_leaves_running_is_reported_by_its_test_directory(tmp_path, monkeypatch):
    """Review of #217, (a), report-only: a process still running after its test, whose command line or working
    directory is in the session's base temporary directory, is listed at its module's end with the test directory
    it is in (pytest's numbered name). A process a fixture ends in its teardown is not listed: the scan runs after the
    module's last teardown (N1). Nothing fails for a leak yet (G3b enforces)."""
    hangs, out = tmp_path / "hangs", tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("G3_OUT", str(out))
    proc = inner(project(tmp_path, LEAKS), hangs, "-p", "no:xdist", "--basetemp", str(tmp_path / "base"))
    try:
        assert proc.returncode == 0, proc.stdout + proc.stderr  # report-only: the run stays green
        pid = int((out / "leaked.pid").read_text(encoding="utf-8"))
        report = texts(hangs / "autopsy", "leaked-processes.*")
        assert re.search(rf"test_leaves_a_process\d*: pid {pid} .*sleeper\.py", report), report
        assert "managed.py" not in report, report  # ended by its fixture's teardown: not a leak (review, N1)
    finally:
        ident = proctree.identity(int((out / "leaked.pid").read_text(encoding="utf-8")))
        if ident is not None:
            proctree.end(ident)


def test_a_controller_slower_than_its_margins_is_ended_by_the_sentinel_and_says_so(tmp_path, monkeypatch):
    """Review of #217, (b): the suspected cause of the one unexplained session-set failure, made deterministic. The
    controller's collect outlasts both margins, so the sentinel acts: it writes ``session-deadline`` itself (saying
    so), records the set it ended, and the controller never writes ``session-finished``."""
    hangs = tmp_path / "hangs"
    monkeypatch.setenv("G3_TEST_SLOW_COLLECT_S", "60")
    proc = inner(project(tmp_path, OUTLIVES), hangs, "--session-deadline", "4", "--session-deadline-margin", "1",
                 "-p", "no:xdist")
    session = session_dir(hangs)
    sentinel_ends(session)
    names = {p.name for p in session.iterdir()}
    why = f"{proc.returncode}\n{proc.stdout}{proc.stderr}\n--- kept files:\n{texts(session)}"
    assert proc.returncode in (DEADLINE_EXIT, -9, 137), why  # ended by the sentinel: its job code, or SIGKILL
    assert "session-finished.txt" not in names and "abnormal-exit.txt" not in names, why
    assert "written by the sentinel" in (session / "session-deadline.txt").read_text(encoding="utf-8"), why
    assert any(n.startswith("sentinel-processes-deadline") for n in names), why
    assert "(deadline)" in (session / "sentinel-log.txt").read_text(encoding="utf-8"), why


TREE = '''import os, subprocess, sys
from pathlib import Path

from aew.harness.procs import ProcessTree

GRANDCHILD = ("import subprocess, sys; d = subprocess.DEVNULL; subprocess.Popen([sys.executable, '-c', "
              "'import time; time.sleep(60)'], stdin=d, stdout=d, stderr=d, "
              "creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))")


def test_a_process_tree_whose_member_was_orphaned_closes_completely():
    tree = ProcessTree()
    tree.spawn([sys.executable, "-c", GRANDCHILD]).wait(60)  # it has ended: its child is an orphan, adopted
    gate = os.environ.get("G3_TEST_REAP_GATE")
    if gate:
        Path(gate).write_text("1", encoding="utf-8")  # only now does the reaper look
    tree.close()  # ends the orphan, and waits (at most 10 s) until its process group is gone
    if sys.platform != "win32":  # Windows re-parents nothing, and a closed tree's job is gone
        assert tree.active() == 0  # a zombie still in the group would read as a live member
'''


@pytest.mark.parametrize("mode", [("-p", "no:xdist"), ("-n", "1")], ids=["one_process", "xdist"])
def test_a_process_tree_whose_member_was_orphaned_closes_under_the_session(tmp_path, monkeypatch, mode):
    """The second shape the CI met (review of #217): ``ProcessTree.close`` waits until its process group is gone, and
    a killed member that the subreaper adopted stayed a zombie in that group, so every close ran out its 10 s (the
    fast lane's eval-scoring tests, about 3 minutes in all). The controller now reaps every child it did not create;
    the earlier first-seen rule fails this test."""
    hangs, out = tmp_path / "hangs", tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("G3_TEST_REAP_GATE", str(out / "reap-gate"))
    proc = inner(project(tmp_path, TREE), hangs, "--session-deadline", "120", *mode)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    sentinel_ends(session_dir(hangs))
