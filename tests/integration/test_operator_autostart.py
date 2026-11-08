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

from aew import errors
from aew.engine.api import Engine
from aew.harness import operator_autostart as A
from aew.harness import operator_client, operator_endpoint, procs

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
        session.communicate("\n", timeout=HANG_GUARD_S)
        assert session.returncode == 0
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
        out.join(1.0)  # two polls of the loop, with no session live
        assert out.is_alive() and operator_client.ping(engine.aew_root)["alive"]
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
        out.join(1.0)
        assert out.is_alive(), "a session is live"
        holder.unlink()
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
        assert asked == [] and lines == [], "no code was made, shown or asked for"
        out.join(HANG_GUARD_S)
        assert not out.is_alive()
        again = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
        again.start()
        again.close()
    finally:
        holder.unlink(missing_ok=True)
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
        holder.unlink(missing_ok=True)
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
            holder.unlink()
            out.join(1.0)  # two looks with no session live
            assert out.is_alive()
            return re.findall(r"confirmation code ([0-9A-F]{6})", "".join(shown))[-1]

        assert operator_client.request_raise(engine.aew_root, "walk", ask=code, requester="test")["mode"] == "walk"
        out.join(HANG_GUARD_S)
        assert not out.is_alive(), "then no session is live"
    finally:
        holder.unlink(missing_ok=True)
        ep.close()


def test_a_session_starting_while_the_endpoint_stops_ends_with_one_live_endpoint(project, monkeypatch):
    """The endpoint has decided to stop and still holds the lock. The session finds no locator and starts another, which
    waits the old one out instead of failing its claim."""
    engine = Engine.discover(project.root)
    holder = _holder(engine.aew_root, os.getpid())
    old, out = _background(engine)
    let_go = threading.Event()
    assert old.watcher is not None
    close_watcher = old.watcher.close
    monkeypatch.setattr(old.watcher, "close", lambda bound: (let_go.wait(HANG_GUARD_S), close_watcher(bound)))
    holder.unlink()
    locator = operator_client.locator_path(engine.aew_root)
    _until("the endpoint decided to stop", lambda: operator_client.read_locator(locator) is None)

    started: list[list[str]] = []
    monkeypatch.setattr(A, "_start", lambda argv, env, log: started.append(argv))
    assert operator_client.name_session(engine.aew_root) is not None
    assert A.ensure(engine, provider_env=[], base={}) is not None
    assert started, "it found no endpoint, so it started one"
    new = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True, background=True)
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
        (engine.aew_root / operator_client.SESSIONS_REL / f"{os.getpid()}.json").unlink(missing_ok=True)


def test_a_session_naming_itself_during_the_endpoints_last_look_is_seen(project):
    """The look and the naming take one lock. Without it, the look finds nobody and stops, and this session has reused
    an endpoint that is going away."""
    engine = Engine.discover(project.root)
    leaving = _holder(engine.aew_root, os.getpid())
    ep, out = _background(engine)
    try:
        with operator_client.sessions_lock(engine.aew_root):
            leaving.unlink()
            out.join(1.0)
            assert out.is_alive(), "its look waits for the session"
            arriving = _holder(engine.aew_root, os.getpid())
        out.join(1.0)
        assert out.is_alive(), "the session is seen"
        assert A.ensure(engine, provider_env=[], base={}) is None
        assert operator_client.ping(engine.aew_root)["alive"]
        arriving.unlink()
        out.join(HANG_GUARD_S)
        assert not out.is_alive()
    finally:
        ep.close()


def test_a_lead_session_starts_no_endpoint(project, monkeypatch):
    """The refusal stands, and it is applied before the reparenting that would hide the ancestor."""
    engine = Engine.discover(project.root)
    monkeypatch.setattr(A, "_start", lambda *a: pytest.fail("started"))
    line = A.ensure(engine, provider_env=[], base={"AEW_LEAD_BROKER": "somewhere"})
    assert line is not None and "Lead session" in line


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
