"""`aew opencode` starts the project's operator endpoint itself: one per project, in the background, for the session's
life, reused if one is live. Where a challenge needs a code and it has nowhere to show one, the reply says to run
`aew operator serve --dev`, and the endpoint gives up its lock so that can start. Nothing here shows a window: the real
endpoints started below are never challenged, and on Windows their console stays hidden."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import IS_WINDOWS, clean_env
from notifier import adopt, hidden, raise_to, received, recorder, script, until

from aew import errors
from aew.engine.api import Engine
from aew.harness import broker_liveness, notify, operator_client, operator_endpoint, procs
from aew.harness import operator_autostart as A

SRC = Path(__file__).resolve().parents[2] / "src"
# A process whose command line reads as `python -m aew opencode`, as the endpoint's ancestor check sees it
SESSION = """
from pathlib import Path
import sys
from aew.engine.api import Engine
from aew.harness import operator_autostart
with operator_autostart.for_session(Engine.discover(Path(sys.argv[1])), provider_env=[]):
    print("session", flush=True)
    sys.stdin.readline()
"""
# The same session, one process below an `aew opencode` that has no broker in its environment
UNDER_A_SESSION = ("import subprocess,sys;"
                   "sys.exit(subprocess.run([sys.executable,'-c',sys.argv[1],sys.argv[2]]).returncode)")
HANG_GUARD_S = 60.0  # only for a failure: each wait below ends on the event it waits for


def _until(what: str, done) -> None:
    deadline = time.monotonic() + HANG_GUARD_S
    while not done():
        assert time.monotonic() < deadline, what
        time.sleep(0.05)


def _holder(aew_root: Path, pid: int) -> Path:
    path = aew_root / operator_client.SESSIONS_REL / f"{pid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "start_id": procs.start_id(pid),
                                "process_started": procs.started_at(pid)}), encoding="utf-8")
    return path


def _leave(aew_root: Path, holder: Path) -> None:
    """A session leaving, as its own end removes its file: under the lock the endpoint's looks read the files under,
    so the removal never meets the look's open file (Windows refuses that with WinError 32; CI, 2026-11-11)."""
    operator_client.unname_session(aew_root, holder)


def _still_serving(aew_root: Path, out: threading.Thread, why: str) -> None:
    """Over two looks of its loop. Its thread alone says nothing: it is alive for all of `close`, too."""
    out.join(1.0)
    assert out.is_alive() and operator_client.status(aew_root)["running"], why


def _cmdline(pid: int) -> list[str]:
    return [a.decode("utf-8", "replace") for a in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if a]


def _ancestors(pid: int) -> list[int]:
    found = []
    while pid > 1:
        pid = int(Path(f"/proc/{pid}/stat").read_bytes().decode("latin-1").rsplit(")", 1)[1].split()[1])
        found.append(pid)
    return found


def test_a_session_starts_the_endpoint_outside_its_ancestry_and_the_endpoint_ends_with_it(project):
    """The whole route, with the real process chain: the session's command line is one the endpoint refuses as an
    ancestor, so an endpoint that was not reparented would refuse to start here."""
    env = clean_env({"PYTHONPATH": str(SRC)})
    env.pop(A.OFF_ENV, None)
    aew_root = project.root / ".aew"
    session = subprocess.Popen([sys.executable, "-c", SESSION, str(project.root), "-m", "aew", "opencode"], env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               creationflags=procs.CREATE_NO_WINDOW if IS_WINDOWS else 0)
    pid = None
    try:
        assert session.stdout is not None
        line = session.stdout.readline().strip()
        if line != "session":
            pytest.fail(session.communicate(timeout=HANG_GUARD_S)[1])
        found = operator_client.wait_for_locator(aew_root, timeout=HANG_GUARD_S)
        log = operator_client.locator_path(aew_root).with_name(A.LOG_NAME)
        assert found, log.read_text(encoding="utf-8", errors="replace")
        pid = found["pid"]
        ping = operator_client.ping(aew_root)
        assert ping["alive"] and ping["pid"] == pid and ping["guarantee"] == "dev"
        assert pid != session.pid
        assert operator_client.session_holders_live(aew_root), "named, so it stays"
        if not IS_WINDOWS:  # what the endpoint's own check walks: no `aew opencode` above it, because none is
            assert operator_client._is_lead_session(_cmdline(session.pid)), "this test's session must read as one"
            above = _ancestors(pid)
            assert session.pid not in above, "not reparented"
            assert not any(operator_client._is_lead_session(_cmdline(a)) for a in above if a > 1)
        _, told = session.communicate("\n", timeout=HANG_GUARD_S)
        assert session.returncode == 0
        assert "no Lead session is left" in told and f"{A.OFF_ENV}=off" in told, "what it did, and how to turn it off"
        _until("the endpoint outlived its session", lambda: not operator_client.status(aew_root)["running"])
        assert not list((aew_root / operator_client.SESSIONS_REL).glob("*.json"))
    finally:
        if session.poll() is None:
            session.kill()
            session.communicate()
        if pid is not None and procs.pid_alive(pid):  # its session has gone: it stops itself within a poll
            _until("the endpoint outlived its session", lambda: not procs.pid_alive(pid))


def test_a_second_session_reuses_a_live_endpoint_and_starts_nothing(project, monkeypatch):
    engine = Engine.discover(project.root)
    ep = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
    ep.start()
    started: list[list[str]] = []
    monkeypatch.setattr(A, "_start", lambda argv, env, log: started.append(argv))
    try:
        assert A.ensure(engine, provider_env=[], base={}) is None
    finally:
        ep.close()
    assert started == []


def test_an_endpoint_started_at_a_terminal_is_not_stopped_when_a_session_ends(project):
    """It is the operator's: only a background endpoint looks at the sessions."""
    engine = Engine.discover(project.root)
    ep = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
    ep.start()
    out = threading.Thread(target=ep.serve_forever, daemon=True)
    out.start()
    try:
        assert not operator_client.session_holders_live(engine.aew_root)
        _still_serving(engine.aew_root, out, "no session is live, and it does not look")
    finally:
        ep.close()
        out.join(HANG_GUARD_S)


def test_a_background_endpoint_stays_while_any_session_it_serves_lives(project):
    engine = Engine.discover(project.root)
    holder = _holder(engine.aew_root, os.getpid())
    ep = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True, background=True)
    ep.start()
    out = threading.Thread(target=ep.serve_forever, daemon=True)
    out.start()
    try:
        _still_serving(engine.aew_root, out, "a session is live")
        _leave(engine.aew_root, holder)
        out.join(HANG_GUARD_S)
        assert not out.is_alive(), "no session is live"
        assert operator_client.read_locator(operator_client.locator_path(engine.aew_root)) is None
    finally:
        ep.close()


def test_a_session_that_died_never_keeps_the_endpoint_up(project):
    aew_root = project.root / ".aew"
    child = subprocess.Popen([sys.executable, "-c", "pass"], creationflags=procs.CREATE_NO_WINDOW if IS_WINDOWS else 0)
    child.wait()
    gone = aew_root / operator_client.SESSIONS_REL / f"{child.pid}.json"
    gone.parent.mkdir(parents=True, exist_ok=True)
    gone.write_text(json.dumps({"pid": child.pid, "start_id": "not-this-process"}), encoding="utf-8")
    junk = gone.with_name("junk.json")
    junk.write_text("not json", encoding="utf-8")
    assert not operator_client.session_holders_live(aew_root)
    assert not gone.exists() and not junk.exists()


def _background(engine, **kw):
    ep = operator_endpoint.OperatorEndpoint(engine, console=kw.pop("console", print), dev=True, background=True, **kw)
    ep.start()
    out = threading.Thread(target=ep.serve_forever, daemon=True)
    out.start()
    return ep, out


def _steered(project) -> Engine:
    (project.root / ".aew/policy/execution.yaml").open("a", encoding="utf-8").write("\nsteering:\n  mode: crawl\n")
    project.adopt_policy()
    return Engine.discover(project.root)


def test_a_background_endpoint_with_no_terminal_says_run_serve_and_gives_up_its_lock(project):
    """No code is made, so none can reach its log; the reply arrives before it stops; and the command it names can
    then start, because the lock is free."""
    engine = _steered(project)
    holder = _holder(engine.aew_root, os.getpid())
    lines: list[str] = []
    ep, out = _background(engine, console=lines.append, code_problem=lambda: "it has no terminal")
    asked: list[str] = []
    try:
        with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
            operator_client.request_raise(engine.aew_root, "walk", ask=lambda p: asked.append(p) or "x",
                                          requester="test")
        assert "aew operator serve --dev" in refused.value.message and "no terminal" in refused.value.message
        assert "is stopping" in refused.value.message
        assert operator_client.read_locator(operator_client.locator_path(engine.aew_root)) is None, "not to be reused"
        assert asked == [] and lines == [], "no code was made, shown or asked for"
        out.join(HANG_GUARD_S)
        assert not out.is_alive()
        again = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
        again.start()
        again.close()
    finally:
        _leave(engine.aew_root, holder)
        ep.close()


def test_a_capability_change_with_no_terminal_says_the_same_and_shows_nothing(project):
    engine = Engine.discover(project.root)
    holder = _holder(engine.aew_root, os.getpid())
    lines: list[str] = []
    ep, out = _background(engine, console=lines.append, code_problem=lambda: "it has no terminal")
    try:
        with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
            operator_client.request_capability_change(engine.aew_root, "host_copies", {"on": False},
                                                      ask=lambda p: pytest.fail("asked"), requester="test")
        assert "aew operator serve --dev" in refused.value.message and lines == []
        out.join(HANG_GUARD_S)
        assert not out.is_alive()
    finally:
        _leave(engine.aew_root, holder)
        ep.close()


def test_where_a_code_can_be_shown_the_raise_still_takes_it(project):
    """Windows' case: the background console is only where the code goes, typed back at the requesting terminal."""
    engine = _steered(project)
    shown: list[str] = []
    done: list[bool] = []
    ep = operator_endpoint.OperatorEndpoint(engine, console=shown.append, dev=True, background=True,
                                            console_done=lambda: done.append(True), code_problem=lambda: None,
                                            timeout=30)
    ep.start()
    try:
        def code(prompt: str) -> str:
            assert "on Windows the window" in prompt
            return re.findall(r"confirmation code ([0-9A-F]{6})", "".join(shown))[-1]

        out = operator_client.request_raise(engine.aew_root, "walk", ask=code, requester="test")
        assert out["mode"] == "walk" and done == [True]
    finally:
        ep.close()


def test_a_challenge_in_hand_finishes_before_the_endpoint_stops(project):
    engine = _steered(project)
    holder = _holder(engine.aew_root, os.getpid())
    shown: list[str] = []
    ep, out = _background(engine, console=shown.append)
    try:
        def code(prompt: str) -> str:
            _leave(engine.aew_root, holder)
            _still_serving(engine.aew_root, out, "a challenge is in hand")
            return re.findall(r"confirmation code ([0-9A-F]{6})", "".join(shown))[-1]

        assert operator_client.request_raise(engine.aew_root, "walk", ask=code, requester="test")["mode"] == "walk"
        out.join(HANG_GUARD_S)
        assert not out.is_alive(), "then no session is live"
    finally:
        _leave(engine.aew_root, holder)
        ep.close()


@pytest.mark.parametrize("background", [True, False], ids=["a_session", "the_operator_at_a_terminal"])
def test_a_session_starting_while_the_endpoint_stops_ends_with_one_live_endpoint(project, monkeypatch, background):
    """The endpoint has decided to stop and still holds the lock. The session finds no locator and starts another, which
    waits the old one out instead of failing its claim. So does the command a refusal has just named."""
    engine = Engine.discover(project.root)
    holder = _holder(engine.aew_root, os.getpid())
    old, out = _background(engine)
    let_go = threading.Event()
    assert old.watcher is not None
    close_watcher = old.watcher.close
    monkeypatch.setattr(old.watcher, "close", lambda bound: (let_go.wait(HANG_GUARD_S), close_watcher(bound)))
    _leave(engine.aew_root, holder)
    locator = operator_client.locator_path(engine.aew_root)
    _until("the endpoint decided to stop", lambda: operator_client.read_locator(locator) is None)

    started: list[list[str]] = []
    monkeypatch.setattr(A, "_start", lambda argv, env, log: started.append(argv))
    assert operator_client.name_session(engine.aew_root) is not None
    assert A.ensure(engine, provider_env=[], base={}) is not None
    assert started, "it found no endpoint, so it started one"
    new = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True, background=background)
    failed: list[BaseException] = []

    def start() -> None:
        try:
            new.start()
        except BaseException as exc:  # noqa: BLE001 (reported by the assert below)
            failed.append(exc)

    starting = threading.Thread(target=start, daemon=True)
    starting.start()
    try:
        starting.join(2 * operator_endpoint.CLAIM_TIMEOUT_S)  # an ordinary claim would have failed by now
        assert starting.is_alive() and not failed
        let_go.set()
        out.join(HANG_GUARD_S)
        starting.join(HANG_GUARD_S)
        assert not failed and not out.is_alive()
        assert operator_client.ping(engine.aew_root)["alive"]
        third = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
        with pytest.raises(errors.PermissionDenied):
            third.start()
    finally:
        let_go.set()
        new.close()
        old.close()
        _leave(engine.aew_root, engine.aew_root / operator_client.SESSIONS_REL / f"{os.getpid()}.json")


def test_a_session_naming_itself_during_the_endpoints_last_look_is_seen(project):
    """The look and the naming take one lock. Without it, the look finds nobody and stops, and this session has reused
    an endpoint that is going away."""
    engine = Engine.discover(project.root)
    leaving = _holder(engine.aew_root, os.getpid())
    ep, out = _background(engine)
    try:
        with operator_client.sessions_lock(engine.aew_root):
            leaving.unlink()
            _still_serving(engine.aew_root, out, "its look waits for the session")
            arriving = _holder(engine.aew_root, os.getpid())
        _still_serving(engine.aew_root, out, "the session is seen")
        assert A.ensure(engine, provider_env=[], base={}) is None
        assert operator_client.ping(engine.aew_root)["alive"]
        _leave(engine.aew_root, arriving)
        out.join(HANG_GUARD_S)
        assert not out.is_alive()
    finally:
        ep.close()


def test_a_lead_session_starts_no_endpoint(project, monkeypatch):
    """The refusal stands, and it is applied before the reparenting that would hide the ancestor."""
    engine = Engine.discover(project.root)
    monkeypatch.setattr(A, "_start", lambda *a: pytest.fail("started"))
    line = A.ensure(engine, provider_env=[], base={"AEW_LEAD_BROKER": "somewhere"})
    assert line is not None and "Lead session" in line and "aew operator serve --dev" in line, "and what to do instead"


@pytest.mark.skipif(IS_WINDOWS, reason="the check's walk of the process chain reads /proc")
def test_aew_opencode_under_a_lead_session_starts_nothing_and_says_why(project):
    """The real chain, on Linux: no broker in the environment, only an `aew opencode` above it. It names no session
    either, so nothing keeps an endpoint up for it."""
    env = clean_env({"PYTHONPATH": str(SRC)})
    env.pop(A.OFF_ENV, None)
    env.pop("AEW_LEAD_BROKER", None)
    aew_root = project.root / ".aew"
    done = subprocess.run([sys.executable, "-c", UNDER_A_SESSION, SESSION, str(project.root), "-m", "aew", "opencode"],
                          env=env, input="\n", capture_output=True, text=True, timeout=HANG_GUARD_S)
    assert done.returncode == 0, done.stderr
    assert "the operator endpoint was not started" in done.stderr and "Lead session" in done.stderr
    assert not operator_client.status(aew_root)["running"]
    assert not operator_client.locator_path(aew_root).with_name(A.LOG_NAME).exists()
    assert not (aew_root / operator_client.SESSIONS_REL).exists()


def test_a_failed_start_never_fails_the_session_and_says_what_to_run(project, monkeypatch):
    def refuses(*_):
        raise OSError("no such file")

    monkeypatch.setattr(A, "_start", refuses)
    line = A.ensure(Engine.discover(project.root), provider_env=[], base={})
    assert line is not None and "aew operator serve --dev" in line


def test_a_session_that_cannot_be_named_starts_nothing_and_still_runs(project, monkeypatch):
    monkeypatch.delenv(A.OFF_ENV, raising=False)
    monkeypatch.setattr(operator_client, "name_session", lambda aew_root: None)
    monkeypatch.setattr(A, "_start", lambda *a: pytest.fail("it would stop at once, with nobody named"))
    ran = []
    with A.for_session(Engine.discover(project.root), provider_env=[]):
        ran.append(True)
    assert ran == [True]


def test_the_off_switch_starts_nothing_and_holds_nothing(project, monkeypatch):
    monkeypatch.setenv(A.OFF_ENV, "off")
    monkeypatch.setattr(A, "_start", lambda *a: pytest.fail("started"))
    engine = Engine.discover(project.root)
    with A.for_session(engine, provider_env=[]):
        assert not (engine.aew_root / operator_client.SESSIONS_REL).exists()


# ------------------------------------------------------------- a session's end reaches the operator (plan v3 §2.8)

BROKER = """\
import sys, time
from pathlib import Path
from aew.engine.api import Engine
from aew.harness.lead_broker import LeadBroker
token = sys.stdin.readline().strip()
broker = LeadBroker(Engine.discover(Path(sys.argv[1])), token)
broker.start()
open(sys.argv[2], "w").close()
if sys.argv[3] == "close":
    sys.stdin.readline()
    broker.close()
else:
    time.sleep(300)
"""
# As `aew opencode`: the session holds the endpoint, and its broker runs in the session's own process
BROKER_SESSION = """\
import sys
from pathlib import Path
from aew.engine.api import Engine
from aew.harness import operator_autostart
from aew.harness.lead_broker import LeadBroker
token = sys.stdin.readline().strip()
engine = Engine.discover(Path(sys.argv[1]))
with operator_autostart.for_session(engine, provider_env=[]):
    broker = LeadBroker(engine, token)
    broker.start()
    print("session", flush=True)
    sys.stdin.readline()
    broker.close()
"""


def _broker_gone(out: Path) -> list[dict]:
    return [e for e in received(out) if e["event"] == "broker_gone"]


@pytest.mark.parametrize("background", [False, True], ids=["terminal_endpoint", "background_endpoint"])
@pytest.mark.parametrize("ending", ["crash", "close"])
def test_a_session_ending_in_run_is_told_to_the_operator(project, tmp_path, background, ending):
    """The event that exists for an away operator, from either endpoint. A background one stops within a look of the
    session's end, and its watcher's next pass would come after that."""
    command, out = recorder(tmp_path)
    engine = adopt(project, command=command)
    raise_to(engine, "run")
    root = project.root / ".aew"
    ready = tmp_path / "broker-ready"
    child = subprocess.Popen([sys.executable, script(tmp_path, "broker", BROKER), str(project.root), str(ready),
                              ending],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **hidden())
    assert child.stdin is not None
    child.stdin.write((project.token + "\n").encode("utf-8"))
    child.stdin.flush()
    until(ready.exists, HANG_GUARD_S, "the broker to start")
    record = until(lambda: broker_liveness.read(root), what="the broker's liveness record")
    _holder(root, record["pid"])
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=lambda s: None, dev=True,
                                            background=background)
    ep.start()
    until(lambda: notify.summary(root) is not None, what="the watcher's first pass")
    loop = threading.Thread(target=ep.serve_forever, daemon=True)
    loop.start()
    try:
        _still_serving(root, loop, "it is serving, over more than one look")
        if ending == "crash":
            procs.kill_pid(record["pid"])
            if child.pid != record["pid"]:  # a venv's launcher on Windows
                procs.kill_pid(child.pid)
        else:
            child.stdin.write(b"\n")
            child.stdin.flush()
        child.wait(HANG_GUARD_S)
        until(lambda: _broker_gone(out), HANG_GUARD_S, "broker_gone",
              describe=lambda: f"stopped: {not loop.is_alive()}")
        if background:
            loop.join(HANG_GUARD_S)
            assert not loop.is_alive(), "and then it stops"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(HANG_GUARD_S)
        ep.close()


@pytest.mark.parametrize("ending", ["crash", "close"])
def test_the_whole_route_tells_the_operator_a_session_ended_and_then_the_endpoint_stops(project, tmp_path, ending):
    """Nothing in-process: the session names itself and starts the real endpoint, whose real notifier gets the event."""
    command, out = recorder(tmp_path)
    engine = adopt(project, command=command)
    raise_to(engine, "run")
    root = project.root / ".aew"
    env = clean_env({"PYTHONPATH": str(SRC)})
    env.pop(A.OFF_ENV, None)
    session = subprocess.Popen([sys.executable, script(tmp_path, "session", BROKER_SESSION), str(project.root)],
                               env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, **hidden())
    pid = None
    try:
        assert session.stdin is not None and session.stdout is not None
        session.stdin.write(project.token + "\n")
        session.stdin.flush()
        assert session.stdout.readline().strip() == "session"
        found = operator_client.wait_for_locator(root, timeout=HANG_GUARD_S)
        assert found
        pid = found["pid"]
        record = until(lambda: broker_liveness.read(root), what="the broker's liveness record")
        until(lambda: notify.summary(root) is not None, HANG_GUARD_S, "the watcher's first pass")
        if ending == "crash":
            procs.kill_pid(record["pid"])
            if session.pid != record["pid"]:  # a venv's launcher on Windows
                procs.kill_pid(session.pid)
        else:
            session.stdin.write("\n")
            session.stdin.flush()
        session.wait(HANG_GUARD_S)
        until(lambda: _broker_gone(out), HANG_GUARD_S, "broker_gone",
              describe=lambda: f"endpoint alive: {procs.pid_alive(pid)}; {received(out)}")
        until(lambda: not procs.pid_alive(pid), HANG_GUARD_S, "the endpoint to stop")
    finally:
        if session.poll() is None:
            session.kill()
            session.wait(HANG_GUARD_S)
        if pid is not None and procs.pid_alive(pid):
            procs.kill_pid(pid)


def test_a_hung_notifier_never_keeps_the_endpoint_up(project, tmp_path, monkeypatch):
    """The flush is bounded by the notifier's own timeout, and what is left stays outstanding. The notifier hangs until
    the test lets it go, so the delivery is in flight for the whole flush by construction: with a real 1 s timeout,
    a flush whose own pass took longer than that found the delivery already recorded (CI, Windows, 2026-11-10 and
    2026-11-11)."""
    command = [sys.executable, "-I", script(tmp_path, "hang", "import time\ntime.sleep(300)\n")]
    engine = adopt(project, command=command, timeout_s=1)
    in_flight, let_go = threading.Event(), threading.Event()

    def hung(*_args, **_kw) -> dict:  # the notifier that never answers, until the test ends
        in_flight.set()
        let_go.wait(HANG_GUARD_S)
        return {"outcome": "failed", "reason": "timeout", "exit_code": None, "timed_out": True, "output_bytes": 0,
                "discarded_bytes": 0}

    monkeypatch.setattr(notify, "deliver", hung)
    ep = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True, background=True)
    ep.start()
    try:
        assert ep.watcher is not None
        monkeypatch.setattr(notify, "FLUSH_DELIVERIES", 0)
        ep.watcher._offer("test:one", {"event": "test", "source": "test"}, lane="urgent")
        assert in_flight.wait(HANG_GUARD_S), "the delivery to begin"
        started = time.monotonic()
        assert ep.watcher.flush() is False, "nothing waits past the bound"
        assert time.monotonic() - started < HANG_GUARD_S
        assert "test:one" in ep.watcher._outstanding, "what is left stays outstanding"
    finally:
        let_go.set()
        ep.close()


def test_a_hand_over_ends_a_flush_so_the_command_it_names_can_start(project, tmp_path):
    """The named command waits `STOPPING_S` for the lock, and a slow notifier's flush may be far longer than that."""
    command = [sys.executable, "-I", script(tmp_path, "hang", "import time\ntime.sleep(300)\n")]
    engine = adopt(project, command=command, timeout_s=30)
    holder = _holder(engine.aew_root, os.getpid())
    ep, out = _background(engine)
    try:
        assert ep.watcher is not None
        ep.watcher._offer("test:one", {"event": "test", "source": "test"}, lane="urgent")
        until(lambda: ep.watcher._busy, HANG_GUARD_S, "the delivery to begin")
        _leave(engine.aew_root, holder)
        time.sleep(1.0)  # its look has found nobody, and it is flushing
        ep._retired.set()
        out.join(operator_endpoint.STOPPING_S)
        assert not out.is_alive(), "still flushing"
    finally:
        _leave(engine.aew_root, holder)
        ep.close()


# ----------------------------------------------------------------------- what the real command and its console do


@pytest.mark.skipif(IS_WINDOWS, reason="a real challenge on Windows would show the window, and no test shows one")
def test_the_real_background_command_makes_no_code_and_the_command_it_names_starts_at_once(project, tmp_path):
    """Through the real command line, with nothing injected: the raise is refused, no code reaches the log, and the
    command the reply names, run at once, rides out the stopping endpoint."""
    engine = _steered(project)
    root = engine.aew_root
    holder = _holder(root, os.getpid())
    log = tmp_path / "endpoint.log"
    env = clean_env({"PYTHONPATH": str(SRC)})
    with open(log, "wb") as fh:
        proc = subprocess.Popen([sys.executable, "-m", "aew", "-C", str(project.root), "operator", "serve", "--dev",
                                 "--background"], env=env, stdin=subprocess.DEVNULL, stdout=fh, stderr=fh)
    try:
        assert operator_client.wait_for_locator(root, timeout=HANG_GUARD_S), log.read_text()
        with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
            operator_client.request_raise(root, "walk", ask=lambda p: pytest.fail("asked"), requester="test")
        assert "aew operator serve --dev" in refused.value.message
        again = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
        again.start()
        again.close()
        proc.wait(HANG_GUARD_S)
        text = log.read_text()
        assert not re.search(r"confirmation code", text, re.I) and "RAISE" not in text
        assert "Ctrl-C" not in text and "Lead sessions it serves" in text
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(HANG_GUARD_S)
        _leave(engine.aew_root, holder)


@pytest.mark.skipif(IS_WINDOWS, reason="a hardened session is Linux's")
def test_a_hardened_session_keeps_its_background_endpoint(project):
    """The real session hardens itself after naming itself. The endpoint's look must still see it live."""
    body = SESSION.replace('    print("session"', '    procs.harden_current_process()\n    print("session"').replace(
        "from aew.harness import operator_autostart", "from aew.harness import operator_autostart, procs")
    env = clean_env({"PYTHONPATH": str(SRC)})
    env.pop(A.OFF_ENV, None)
    root = project.root / ".aew"
    session = subprocess.Popen([sys.executable, "-c", body, str(project.root)], env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert session.stdout is not None and session.stdout.readline().strip() == "session"
        found = operator_client.wait_for_locator(root, timeout=HANG_GUARD_S)
        assert found
        time.sleep(2.0)  # several looks
        assert operator_client.status(root)["running"], "the endpoint stopped under a live, hardened session"
        session.communicate("\n", timeout=HANG_GUARD_S)
        _until("the endpoint to stop", lambda: not procs.pid_alive(found["pid"]))
    finally:
        if session.poll() is None:
            session.kill()
            session.communicate()


def test_the_background_command_wires_its_console_to_the_endpoint(monkeypatch):
    """Every platform, showing nothing: what `--background` gives the endpoint, which the tests above inject."""
    import argparse

    from aew.cli import operator_commands

    class Stop(Exception):
        pass

    seen = {}

    def built(engine, **kw):
        seen.update(kw)
        raise Stop

    monkeypatch.setattr(operator_endpoint, "OperatorEndpoint", built)
    monkeypatch.setattr(operator_commands, "_engine", lambda a: object())
    with pytest.raises(Stop):
        operator_commands._serve(argparse.Namespace(background=True, dev=True))
    window = seen["console"]
    assert seen["background"] is True and seen["console_done"] == window.done
    assert seen["code_problem"] == window.problem and seen["show_challenge"] == window.challenge


def test_a_code_is_made_in_one_place_which_holds_the_check():
    source = Path(operator_endpoint.__file__).read_text(encoding="utf-8")
    assert source.count("operator.new_code(") == 1
    assert source.index("self.code_problem()") < source.index("operator.new_code(")


def test_a_challenge_that_cannot_be_written_refuses_and_hands_over(project):
    """Never "shown": the requester would wait out the timeout for a code nobody saw."""
    engine = _steered(project)
    holder = _holder(engine.aew_root, os.getpid())

    def fails(text: str) -> None:
        raise OSError("gone")

    ep, out = _background(engine, show_challenge=fails, code_problem=lambda: None)
    try:
        with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
            operator_client.request_raise(engine.aew_root, "walk", ask=lambda p: pytest.fail("asked"), requester="test")
        assert "cannot be written" in refused.value.message and "aew operator serve --dev" in refused.value.message
        out.join(HANG_GUARD_S)
        assert not out.is_alive()
    finally:
        _leave(engine.aew_root, holder)
        ep.close()


def test_a_terminal_endpoints_console_failure_stays_its_own(project):
    """Only a background endpoint hands over: the operator's own endpoint keeps serving."""
    def fails(text: str) -> None:
        raise OSError("gone")

    ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=fails, dev=True)
    with pytest.raises(OSError):
        ep._show_challenge("text")
    assert ep._retiring_by is None


class _Conn:
    """One request, and what the endpoint's state was as its reply went."""

    def __init__(self, op: str, args: dict, on_reply) -> None:
        self.request, self.on_reply = json.dumps({"op": op, "args": args}).encode("utf-8"), on_reply

    def recv_bytes(self, _limit: int) -> bytes:
        return self.request

    def send_bytes(self, _data: bytes) -> None:
        self.on_reply()

    def close(self) -> None:
        pass


def test_the_reply_goes_before_the_endpoint_retires_and_only_its_own_handler_retires_it(project):
    engine = _steered(project)
    ep = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True, background=True,
                                            code_problem=lambda: "it has no terminal")
    at_reply: list[bool] = []
    ep._handle(_Conn("mode_raise", {"mode": "walk"}, lambda: at_reply.append(ep._retired.is_set())))
    assert at_reply == [False], "the reply goes first"
    assert ep._retired.is_set(), "then it retires"
    other = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True, background=True)
    other._retiring_by = threading.Thread()  # another handler's reply is on its way
    other._handle(_Conn("ping", {}, lambda: None))
    assert not other._retired.is_set(), "a ping ending says nothing of that reply"


def test_a_terminal_serve_beside_a_background_endpoint_says_what_it_is_and_what_to_do(project):
    engine = Engine.discover(project.root)
    holder = _holder(engine.aew_root, os.getpid())
    ep, out = _background(engine)
    try:
        assert operator_client.read_locator(operator_client.locator_path(engine.aew_root))["background"] is True
        with pytest.raises(errors.PermissionDenied) as refused:
            operator_endpoint.OperatorEndpoint(engine, console=print, dev=True).start()
        told = refused.value.message
        assert "aew opencode" in told and "stops when the Lead sessions" in told and "stop it first" not in told
        assert ("own window" if IS_WINDOWS else "hands over") in told
    finally:
        _leave(engine.aew_root, holder)
        ep.close()


def test_two_starts_keep_both_lines_in_the_log(project, monkeypatch):
    engine = Engine.discover(project.root)
    written = iter([b"the winner\n", b"the loser\n"])
    monkeypatch.setattr(A, "_start", lambda argv, env, log: log.write(next(written)))
    A.ensure(engine, provider_env=[], base={})
    A.ensure(engine, provider_env=[], base={})
    log = operator_client.locator_path(engine.aew_root).with_name(A.LOG_NAME)
    assert log.read_bytes() == b"the winner\nthe loser\n"


def test_a_session_file_that_cannot_be_removed_costs_the_session_nothing(project, monkeypatch):
    class Held:
        def unlink(self, missing_ok: bool = False) -> None:
            raise PermissionError("in use by the endpoint's look")

    monkeypatch.delenv(A.OFF_ENV, raising=False)
    monkeypatch.setattr(operator_client, "name_session", lambda aew_root: Held())
    monkeypatch.setattr(A, "ensure", lambda engine, provider_env: None)
    ran = []
    with A.for_session(Engine.discover(project.root), provider_env=[]):
        ran.append(True)
    assert ran == [True]


HELD_SESSION = """
import sys
from pathlib import Path
from aew.engine.api import Engine
from aew.harness import operator_autostart
operator_autostart.ensure = lambda engine, provider_env: None  # its file is what this checks, not the endpoint
with operator_autostart.for_session(Engine.discover(Path(sys.argv[1])), provider_env=[]):
    print("session", flush=True)
    sys.stdin.readline()
print("ended", flush=True)
"""


def test_a_real_sessions_file_held_open_at_its_end_costs_it_nothing_and_goes_with_it(project):
    """The product's side of the WinError 32 the tests above met (CI, 2026-11-11): a real session's own end removes
    its file while another process holds it open. On Windows the removal is refused; the session still ends cleanly,
    and the endpoint's next look removes the file once that process has gone."""
    env = clean_env({"PYTHONPATH": str(SRC)})
    env.pop(A.OFF_ENV, None)
    root = project.root / ".aew"
    session = subprocess.Popen([sys.executable, "-c", HELD_SESSION, str(project.root)], env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               creationflags=procs.CREATE_NO_WINDOW if IS_WINDOWS else 0)
    try:
        assert session.stdout is not None and session.stdout.readline().strip() == "session", session.stderr
        [named] = list((root / operator_client.SESSIONS_REL).glob("*.json"))  # by glob: a venv's launcher on Windows
        with open(named, "rb"):  # held as the endpoint's look holds it, across the session's end
            said, told = session.communicate("\n", timeout=HANG_GUARD_S)
            assert session.returncode == 0 and said.split() == ["ended"], told
            assert named.exists() == IS_WINDOWS, "Windows refuses to remove a file another process has open"
        with operator_client.sessions_lock(root):
            assert not operator_client.session_holders_live(root)
        assert not named.exists(), "its process has gone, so the look removed it"
    finally:
        if session.poll() is None:
            session.kill()
            session.communicate()


@pytest.mark.skipif(IS_WINDOWS, reason="the walk reads /proc")
def test_aew_dash_c_opencode_above_it_is_a_lead_session_too(project):
    """The same chain as `aew opencode` above, spelled as a script spells it, with no broker in any environment."""
    env = clean_env({"PYTHONPATH": str(SRC)})
    env.pop(A.OFF_ENV, None)
    env.pop("AEW_LEAD_BROKER", None)
    done = subprocess.run([sys.executable, "-c", UNDER_A_SESSION, SESSION, str(project.root), "-m", "aew", "-C", "/p",
                           "opencode"], env=env, input="\n", capture_output=True, text=True, timeout=HANG_GUARD_S)
    assert done.returncode == 0, done.stderr
    assert "the operator endpoint was not started" in done.stderr
