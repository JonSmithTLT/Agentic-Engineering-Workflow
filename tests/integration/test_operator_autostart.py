"""`aew opencode` starts the project's operator endpoint itself: one per project, in the background, for the session's
life, reused if one is live. A challenge that needs the code opens a window when asked; where none can open, the reply
says to run `aew operator serve --dev`, and the endpoint gives up its lock so that can start. Nothing here opens a
window: the one real endpoint started below is never challenged, and on Windows its console stays hidden."""

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
from aew.harness import operator_client, operator_endpoint, operator_window, procs

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
        if not IS_WINDOWS:
            stat = Path(f"/proc/{pid}/stat").read_bytes().decode("latin-1")
            assert int(stat.rsplit(")", 1)[1].split()[1]) != session.pid, "not reparented"
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


def test_where_no_window_can_open_the_reply_says_to_run_serve_and_the_endpoint_gives_up_its_lock(project, monkeypatch):
    """Planted: no display. The challenge never reaches a window, the requester's reply names the command, and the
    command can then start, because the endpoint has stopped and released the lock."""
    project_engine = Engine.discover(project.root)
    (project.root / ".aew/policy/execution.yaml").open("a", encoding="utf-8").write("\nsteering:\n  mode: crawl\n")
    project.adopt_policy()
    window = operator_window.WindowConsole()
    monkeypatch.setattr(operator_window.WindowConsole, "_write_windows", lambda self, text: "no display")
    monkeypatch.setattr(operator_window.WindowConsole, "_write_posix", lambda self, text: "no display")
    ep = operator_endpoint.OperatorEndpoint(project_engine, console=window, dev=True, background=True,
                                            console_done=window.done)
    window.on_unavailable = ep.retire
    holder = _holder(project_engine.aew_root, os.getpid())
    ep.start()
    out = threading.Thread(target=ep.serve_forever, daemon=True)
    out.start()
    asked: list[str] = []
    try:
        with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
            operator_client.request_raise(project_engine.aew_root, "walk", ask=lambda p: asked.append(p) or "x",
                                          requester="test")
        assert "aew operator serve --dev" in refused.value.message and "no display" in refused.value.message
        assert asked == [], "nothing to type: no code was shown"
        out.join(HANG_GUARD_S)
        assert not out.is_alive()
        again = operator_endpoint.OperatorEndpoint(project_engine, console=print, dev=True)
        again.start()  # the lock is free
        again.close()
    finally:
        holder.unlink(missing_ok=True)
        ep.close()
        window.close()


def test_the_steering_raise_still_takes_the_code_through_a_window_console(project, monkeypatch):
    """The window is only the console: the code shown there, typed back at the requesting terminal, raises the mode."""
    engine = Engine.discover(project.root)
    (project.root / ".aew/policy/execution.yaml").open("a", encoding="utf-8").write("\nsteering:\n  mode: crawl\n")
    project.adopt_policy()
    shown: list[str] = []

    def show(self, text: str) -> None:
        shown.append(text)

    monkeypatch.setattr(operator_window.WindowConsole, "_write_windows", show)
    monkeypatch.setattr(operator_window.WindowConsole, "_write_posix", show)
    window = operator_window.WindowConsole()
    done: list[bool] = []
    ep = operator_endpoint.OperatorEndpoint(engine, console=window, dev=True, background=True,
                                            console_done=lambda: done.append(True), timeout=30)
    ep.start()
    try:
        def code(prompt: str) -> str:
            assert "window" in prompt
            return re.findall(r"confirmation code ([0-9A-F]{6})", "".join(shown))[-1]

        out = operator_client.request_raise(engine.aew_root, "walk", ask=code, requester="test")
        assert out["mode"] == "walk" and done == [True]
    finally:
        ep.close()


def test_a_lead_session_starts_no_endpoint(project, monkeypatch):
    """The refusal stands, and it is applied before the reparenting that would hide the ancestor."""
    engine = Engine.discover(project.root)
    monkeypatch.setattr(A, "_start", lambda *a: pytest.fail("started"))
    line = A.ensure(engine, provider_env=[], base={"AEW_LEAD_BROKER": "somewhere"})
    assert line is not None and "Lead session" in line


def test_a_failed_start_never_fails_the_session_and_says_what_to_run(project, monkeypatch):
    def refuses(*_):
        raise OSError("no such file")

    monkeypatch.setattr(A, "_start", refuses)
    line = A.ensure(Engine.discover(project.root), provider_env=[], base={})
    assert line is not None and "aew operator serve --dev" in line


def test_the_off_switch_starts_nothing_and_holds_nothing(project, monkeypatch):
    monkeypatch.setenv(A.OFF_ENV, "off")
    monkeypatch.setattr(A, "_start", lambda *a: pytest.fail("started"))
    engine = Engine.discover(project.root)
    with A.for_session(engine, provider_env=[]):
        assert not (engine.aew_root / operator_client.SESSIONS_REL).exists()
