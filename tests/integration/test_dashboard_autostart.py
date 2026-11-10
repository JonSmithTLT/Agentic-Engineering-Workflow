"""The no-code first session and its lifetime. All openers are fake; no browser or console window is launched."""

from __future__ import annotations

import argparse
import contextlib
import http.client
import logging
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from conftest import clean_env

from aew import errors, operator
from aew.cli import dashboard_commands
from aew.dashboard import control, service
from aew.dashboard import session as S
from aew.engine.api import Engine
from aew.harness import dashboard_autostart as A
from aew.harness import lead_broker, procs
from aew.harness.opencode import lead


@pytest.fixture
def desktop(monkeypatch):
    """Opt in explicitly, but never give any test the real opener or a shared port."""
    monkeypatch.delenv(A.OFF_ENV, raising=False)
    monkeypatch.setattr(operator, "has_terminal", lambda: True)
    monkeypatch.setattr(A, "has_display", lambda: True)
    opened = []
    monkeypatch.setattr(A, "open_browser", lambda url: opened.append(url) or True)
    original = service.Service
    built = []

    def make(engine, **kwargs):
        svc = original(engine, port=kwargs.pop("port", 0), **kwargs)
        built.append(svc)
        return svc

    monkeypatch.setattr(service, "Service", make)
    return opened, built


def request(url, *, cookie=None):
    parts = urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
    try:
        conn.request("GET", parts.path, headers={"Cookie": cookie} if cookie else {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_the_first_session_opens_once_without_a_code_and_discloses_nothing(project, desktop, capsys, caplog,
                                                                          monkeypatch):
    opened, built = desktop
    monkeypatch.setattr(operator, "authorize", lambda *a, **k: pytest.fail("asked for a code"))
    caplog.set_level(logging.INFO, logger="aew.dashboard")
    engine = Engine.discover(project.root)
    with A.for_session(engine):
        assert len(opened) == 1 and len(built) == 1
        svc = built[0]
        assert svc.engine is not engine, "dashboard readers do not share the broker's caches"
        assert svc.port and svc.control.console is None
        assert svc.server._thread.is_alive() and svc.control._thread.is_alive()
        assert len(svc.table.live()) == 1
        assert svc.table.newest()["scope"]["authorized_by"] == A.FIRST_AUTHORIZED_BY
        url = opened[0]
        code = url.rsplit("/", 1)[1]
        status, headers, _ = request(url)
        assert status == 303 and headers["Location"] == "/"
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        credential = cookie.split("=", 1)[1]
        assert request(url)[0] == 410, "the bootstrap is single-use"
        assert request(f"{svc.url}/api/v1/project", cookie=cookie)[0] == 200
        assert svc.table.pending_codes == 0
        stdout, stderr = capsys.readouterr()
        assert stdout == "" and "for this session's lifetime" in stderr
        for text in (stdout, stderr, caplog.text):
            assert not any(secret in text for secret in (url, code, credential))
        # Entire project, including logs under .aew and any new file, not just the locator.
        for path in project.root.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                assert not any(secret.encode() in data for secret in (url, code, credential)), path
    assert svc.table.live() == [] and svc.table.pending_codes == 0
    assert not svc.server._thread.is_alive() and not svc.control._thread.is_alive()
    assert service.locate(engine.aew_root) is None
    assert not (engine.aew_root / service.KEY_REL).exists()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", svc.port), timeout=1)


def test_an_unspent_first_url_expires_in_ten_minutes(project, desktop):
    opened, built = desktop
    with A.for_session(Engine.discover(project.root)):
        svc = built[0]
        tick = svc.table.monotonic()
        assert S.CODE_TTL_S == 600
        svc.table.monotonic = lambda: tick + S.CODE_TTL_S + 1
        assert request(opened[0])[0] == 410
        assert svc.table.pending_codes == 0


def test_the_auto_started_session_records_operator_start(project, desktop):
    _, built = desktop
    with A.for_session(Engine.discover(project.root)):
        assert built[0].table.newest()["scope"]["authorized_by"] == "operator-start"
        found = service.locate(built[0].engine.aew_root)
        status = control.request_status(found["endpoint"], found["key"])
        assert status["sessions"][0]["authorized_by"] == "operator-start"


def test_serve_and_open_still_record_operator_tty(project, desktop, monkeypatch, capsys):
    _, built = desktop
    engine = Engine.discover(project.root)
    monkeypatch.setattr(dashboard_commands, "_engine", lambda a: engine)
    confirmations = []
    monkeypatch.setattr(operator, "authorize", lambda action: confirmations.append(action))
    monkeypatch.setattr(dashboard_commands.credentials, "write_to_terminal", lambda *a: None)

    def wait(svc):
        assert confirmations and len(svc.table.live()) == 1
        assert svc.table.newest()["scope"]["authorized_by"] == "operator-tty"
        shown = []
        svc.control.console = shown.append

        def answer(prompt):
            return re.findall(r"confirmation code ([0-9A-F]{6})", "".join(shown))[-1]

        control.request_session(svc.control.address, svc.control.key_hex, ask=answer)
        assert len(svc.table.live()) == 2 and svc.control.opened == 1
        assert all(s["authorized_by"] == "operator-tty" for s in svc.table.live())

    # The fixture's constructor is a wrapper; the class itself still owns wait and the real issue implementation.
    original_make = service.Service

    def make(engine, **kwargs):
        svc = original_make(engine, **kwargs)
        monkeypatch.setattr(svc, "wait", lambda: wait(svc))
        return svc

    monkeypatch.setattr(service, "Service", make)
    dashboard_commands._serve(argparse.Namespace(session_hours=2, port=0, static=None, print_credential=False))
    assert len(confirmations) == 1 and len(built) == 1 and built[0].table.live() == []
    assert capsys.readouterr().out


@pytest.mark.parametrize("reason", ["lead", "off", "display", "terminal"])
def test_a_refused_start_starts_nothing_and_gives_one_line(project, desktop, monkeypatch, capsys, reason):
    opened, built = desktop
    if reason == "lead":
        monkeypatch.setenv("AEW_LEAD_BROKER", "somewhere")
    elif reason == "off":
        monkeypatch.setenv(A.OFF_ENV, "off")
    elif reason == "display":
        monkeypatch.setattr(A, "has_display", lambda: False)
    else:
        monkeypatch.setattr(operator, "has_terminal", lambda: False)
    with A.for_session(Engine.discover(project.root)):
        assert opened == [] and built == []
    stdout, stderr = capsys.readouterr()
    assert stdout == "" and len(stderr.splitlines()) == 1
    assert (A.OFF_ENV if reason == "off" else "aew dashboard serve") in stderr
    assert not (project.root / ".aew" / service.SERVER_JSON_REL).exists()


def test_a_running_dashboard_is_reused_without_minting_or_stopping_it(project, desktop, monkeypatch, capsys):
    opened, built = desktop
    engine = Engine.discover(project.root)
    svc = service.Service(engine, console=lambda text: None)
    svc.start()
    first = svc.issue(authorized_by=S.OPERATOR_TTY)  # standalone serve, after its operator's authorization
    before = (list(svc.table.live()), svc.table.pending_codes)
    monkeypatch.setattr(svc, "issue", lambda: pytest.fail("reuse minted a URL"))
    try:
        with A.for_session(engine):
            assert len(built) == 1 and opened == []
        assert (svc.table.live(), svc.table.pending_codes) == before
        assert request(first)[0] == 303 and service.locate(engine.aew_root) is not None
        assert "already running" in capsys.readouterr().err
    finally:
        svc.stop()


def test_a_concurrent_start_is_reused_before_minting(project, desktop, monkeypatch, capsys):
    opened, built = desktop
    engine = Engine.discover(project.root)
    svc = service.Service(engine, console=None)
    original = service.Service

    def overtaken(engine, **kwargs):
        new = original(engine, **kwargs)
        svc.start()  # after the loser's construction check, before its locked start check
        return new

    monkeypatch.setattr(service, "Service", overtaken)
    try:
        with A.for_session(engine):
            assert opened == [] and svc.table.live() == []
        assert "already running" in capsys.readouterr().err
        assert len(built) == 2 and not built[1].server._thread.is_alive()
        assert service.locate(engine.aew_root)["instance"] == svc.instance
    finally:
        svc.stop()


def test_an_occupied_port_is_named_and_never_fails_the_session(project, desktop, monkeypatch, capsys):
    opened, _ = desktop
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen(1)
    port = taken.getsockname()[1]
    original = service.Service
    # The test owns an ephemeral port; production's default is asserted separately.
    monkeypatch.setattr(service, "Service", lambda *a, **k: original(*a, port=port, **k))
    monkeypatch.setattr(A, "DEFAULT_PORT", port)
    try:
        with A.for_session(Engine.discover(project.root)):
            assert opened == []
        line = capsys.readouterr().err
        assert str(port) in line and "is in use" in line and "aew dashboard serve --port 0" in line
        assert len(line.splitlines()) == 1
        # Follow the printed command, choosing an ephemeral free port while the original remains occupied.
        monkeypatch.setattr(service, "Service", original)
        engine = Engine.discover(project.root)
        monkeypatch.setattr(dashboard_commands, "_engine", lambda a: engine)
        confirmed = []
        monkeypatch.setattr(operator, "authorize", lambda action: confirmed.append(action))
        monkeypatch.setattr(dashboard_commands.credentials, "write_to_terminal", lambda *a: None)

        def make(engine, **kwargs):
            svc = original(engine, **kwargs)
            monkeypatch.setattr(svc, "wait", lambda: None)
            return svc

        monkeypatch.setattr(service, "Service", make)
        dashboard_commands._serve(argparse.Namespace(session_hours=2, port=0, static=None))
        assert len(confirmed) == 1
    finally:
        taken.close()


@pytest.mark.parametrize("failure", ["opener_false", "opener_exception", "publish", "interrupt"])
def test_failures_release_the_listeners_and_never_echo_the_url(project, desktop, monkeypatch, capsys, failure):
    opened, built = desktop
    engine = Engine.discover(project.root)

    def opener(url):
        opened.append(url)
        if failure == "opener_false":
            return False
        raise (KeyboardInterrupt() if failure == "interrupt" else OSError(url))

    monkeypatch.setattr(A, "open_browser", opener)
    if failure == "publish":
        monkeypatch.setattr(service, "atomic_write", lambda *a, **k: (_ for _ in ()).throw(OSError("publish")))
    cm = pytest.raises(KeyboardInterrupt) if failure == "interrupt" else contextlib.nullcontext()
    with cm, A.for_session(engine):
        pass
    assert len(built) == 1
    svc = built[0]
    assert svc.table.tokens == {} and svc.table.pending_codes == 0
    assert not svc.server._thread.is_alive() and not svc.control._thread.is_alive()
    assert service.locate(engine.aew_root) is None
    text = str(capsys.readouterr())
    assert not any(url in text or url.rsplit("/", 1)[1] in text for url in opened)


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_later_open_refuses_without_a_code_then_standalone_serve_still_requires_one(project, desktop, monkeypatch,
                                                                                  platform):
    opened, built = desktop
    engine = Engine.discover(project.root)
    with A.for_session(engine):
        svc = built[0]
        monkeypatch.setattr(operator, "new_code", lambda: pytest.fail("made a later-open code"))
        # The refusal is platform-independent; platform selection must not show/hide the TUI console.
        with monkeypatch.context() as m:
            m.setattr(A.sys, "platform", platform)
            with pytest.raises(errors.OperatorAuthorizationRequired, match="aew dashboard serve"):
                svc.control._open(object(), {})  # refusal must precede any use of the requesting connection
        # Exercise the real transport on the native platform: multiprocessing's family validation reads sys.platform.
        with pytest.raises(errors.OperatorAuthorizationRequired, match="aew dashboard serve"):
            control.request_session(svc.control.address, svc.control.key_hex,
                                    ask=lambda p: pytest.fail("asked for a code"))
        assert len(opened) == 1 and len(svc.table.live()) == 1 and svc.control.opened == 0
    # Follow the refusal's next step: when the session ends, serve can bind and asks for its code before issuing.
    monkeypatch.setattr(dashboard_commands, "_engine", lambda a: engine)
    asked = []

    def refuse(action):
        asked.append(action)
        raise errors.OperatorAuthorizationRequired("typed-back code still required")

    monkeypatch.setattr(operator, "authorize", refuse)
    with pytest.raises(errors.OperatorAuthorizationRequired, match="typed-back code"):
        dashboard_commands._serve(argparse.Namespace(session_hours=2, port=0, static=None))
    assert len(asked) == 1 and "ISSUE" in asked[0] and len(built) == 2
    assert built[1].table.tokens == {} and not built[1].server._thread.is_alive()


@pytest.mark.parametrize("contained", [False, True])
def test_both_start_paths_enter_both_services_before_the_tui_and_unwind_them(monkeypatch, contained):
    events = []

    @contextlib.contextmanager
    def endpoint(engine, *, provider_env):
        events.append("endpoint")
        try:
            yield
        finally:
            events.append("endpoint stopped")

    @contextlib.contextmanager
    def dashboard(engine):
        events.append("dashboard")
        try:
            yield
        finally:
            events.append("dashboard stopped")

    class FakeLead:
        def __init__(self, *a, **kw):
            pass

        def announce(self, out):
            pass

        def require_provider(self):
            pass

        def precheck(self):
            pass

    monkeypatch.setattr(lead, "contained_here", lambda: contained)
    monkeypatch.setattr(lead, "ContainedLead", FakeLead)
    monkeypatch.setattr(lead, "WeakerOpenCode", FakeLead)
    monkeypatch.setattr(lead, "check_version", lambda: "test")
    monkeypatch.setattr(lead, "guide_of", lambda e: "")
    monkeypatch.setattr(lead, "command", lambda e, a: ["fake-opencode"])
    monkeypatch.setattr(lead, "tui_env", lambda *a, **k: {})
    monkeypatch.setattr(lead, "pushes_wakes", lambda e: False)
    monkeypatch.setattr(lead, "no_provider_line", lambda *a: None)
    monkeypatch.setattr(lead, "_unrelayed", lambda e: None)
    monkeypatch.setattr(lead, "_readiness", lambda *a: None)
    monkeypatch.setattr(lead, "_tools_before_the_tui", lambda **k: None)
    monkeypatch.setattr(lead, "_switch_offers", lambda e: argparse.Namespace(apply=lambda t: None))
    monkeypatch.setattr(lead_broker, "require_credential", lambda acquire: None)
    monkeypatch.setattr(lead.operator_autostart, "for_session", endpoint)
    monkeypatch.setattr(A, "for_session", dashboard)

    def tui(*a, **kw):
        kw["on_ready"]()  # the broker calls this only after validating its seat and preparing the harness
        events.append("tui")
        raise errors.UsageError("fake TUI refused")

    monkeypatch.setattr(lead_broker, "run_session", tui)
    with pytest.raises(errors.UsageError, match="fake TUI"):
        lead.run(object(), acquire=True, session_label=None, keep_seat=False, provider_env=[], extra_args=[],
                 print_config=False)
    assert events == ["endpoint", "dashboard", "tui", "dashboard stopped", "endpoint stopped"]


def test_a_lead_process_starts_nothing_even_with_a_display(project):
    """A real process refusal; a fake opener must never be called. CREATE_NO_WINDOW on Windows."""
    script = """
import os
from pathlib import Path
from aew.engine.api import Engine
from aew.harness import dashboard_autostart as A
A.operator.has_terminal = lambda: True
A.has_display = lambda: True
def forbidden(*a, **k):
    raise AssertionError('started')
A.open_browser = forbidden
A.service.Service = forbidden
with A.for_session(Engine.discover(Path(os.environ['TEST_PROJECT']))):
    print('session continued')
"""
    env = clean_env({"TEST_PROJECT": str(project.root), "AEW_LEAD_BROKER": "somewhere"})
    env.pop(A.OFF_ENV, None)
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30,
                            creationflags=procs.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                            start_new_session=sys.platform != "win32")
    assert result.returncode == 0 and result.stdout.strip() == "session continued"
    assert "Lead session" in result.stderr and "did not open" not in result.stderr
    assert not (project.root / ".aew" / service.SERVER_JSON_REL).exists()


@pytest.mark.parametrize("platform,env,expected", [
    ("linux", {}, False), ("linux", {"DISPLAY": ":0"}, True),
    ("linux", {"WAYLAND_DISPLAY": "wayland-0"}, True),
    ("win32", {}, True), ("win32", {"SSH_CONNECTION": "test"}, False),
    ("darwin", {"SSH_TTY": "test"}, False),
])
def test_display_detection_never_chooses_a_text_browser(monkeypatch, platform, env, expected):
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(A.sys, "platform", platform)
    assert A.has_display() is expected


def test_the_default_port_and_off_switch_are_registered():
    import yaml

    from aew.dashboard.defaults import DEFAULT_PORT

    assert A.DEFAULT_PORT == DEFAULT_PORT == 4280
    root = Path(__file__).resolve().parents[2]
    surface = yaml.safe_load((root / "docs/implementation/surface-map.yaml").read_text(encoding="utf-8"))
    entry = next(e for e in surface["commands"] if e["name"] == "opencode")
    assert entry["environment"][A.OFF_ENV]["off"] == "disable dashboard auto-start"


@pytest.mark.parametrize("exit_code", [0, 1, None])
def test_the_unix_opener_detaches_and_discards_output_without_waiting_for_the_browser(monkeypatch, exit_code):
    called = []
    monkeypatch.setattr(A.sys, "platform", "linux")
    monkeypatch.setenv("BROWSER", "a-text-browser")

    def wait(timeout):
        assert timeout == 0.1
        if exit_code is None:
            raise subprocess.TimeoutExpired("fake-opener", timeout)
        return exit_code

    monkeypatch.setattr(A.subprocess, "Popen", lambda argv, **kw: called.append((argv, kw)) or
                        argparse.Namespace(wait=wait))
    assert A.open_browser("http://127.0.0.1:1/session/fake") is (exit_code != 1)
    [(argv, kwargs)] = called
    assert argv == ["xdg-open", "http://127.0.0.1:1/session/fake"]
    assert kwargs == {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                      "start_new_session": True, "close_fds": True}


def test_the_windows_opener_uses_the_desktop_shell_without_an_aew_child_argv(monkeypatch):
    called = []
    monkeypatch.setattr(A.sys, "platform", "win32")
    monkeypatch.setattr(A.os, "startfile", called.append, raising=False)
    monkeypatch.setattr(A.subprocess, "Popen", lambda *a, **kw: pytest.fail("launched a process"))
    assert A.open_browser("http://127.0.0.1:1/session/fake")
    assert called == ["http://127.0.0.1:1/session/fake"]


def test_dashboard_errors_never_reach_the_tui_even_without_a_root_log_handler(project, desktop, monkeypatch, capsys):
    from aew.dashboard import projections

    opened, _ = desktop
    root_log, dashboard_log = logging.getLogger(), logging.getLogger("aew.dashboard")
    handlers, propagate = dashboard_log.handlers, dashboard_log.propagate
    monkeypatch.setattr(root_log, "handlers", [])  # pytest's logging handlers otherwise hide lastResort

    def broken(self):
        raise errors.AEWError("synthetic projection failure")

    monkeypatch.setattr(projections.Projector, "project", broken)
    with A.for_session(Engine.discover(project.root)):
        capsys.readouterr()  # only the start line is allowed
        assert root_log.handlers == [] and not dashboard_log.propagate
        assert any(isinstance(h, logging.NullHandler) for h in dashboard_log.handlers)
        _, headers, _ = request(opened[0])
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        base = opened[0].rsplit("/session/", 1)[0]
        assert request(f"{base}/api/v1/project", cookie=cookie)[0] == 500
        dashboard_log.error("synthetic dashboard error")
        stdout, stderr = capsys.readouterr()
        assert stdout == stderr == ""
    assert dashboard_log.handlers is handlers and dashboard_log.propagate is propagate


@pytest.mark.parametrize("acquire", [True, False], ids=["seat-held", "bad-credential"])
def test_a_refused_seat_or_credential_never_starts_or_opens_the_dashboard(project, desktop, monkeypatch, acquire):
    opened, built = desktop
    monkeypatch.setenv("AEW_OPERATOR_AUTOSTART", "off")
    monkeypatch.setenv("AEW_LEAD_TOKEN", "synthetic-invalid-credential")
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    engine = Engine.discover(project.root)  # the real project fixture already has a held seat
    with lead.session_services(engine, provider_env=[]) as on_ready:
        with pytest.raises(errors.AEWError):
            lead_broker.run_session(engine, ["fake-tui"], acquire=acquire, session_label=None, keep_seat=False,
                                    contained=lambda *a: pytest.fail("prepared a refused harness"), on_ready=on_ready)
    assert opened == [] and built == []
    assert service.locate(engine.aew_root) is None


def test_serve_beside_an_auto_started_dashboard_gives_a_step_that_works(project, desktop, monkeypatch):
    _, built = desktop
    engine = Engine.discover(project.root)
    with A.for_session(engine):
        found = service.locate(engine.aew_root)
        assert found["opens"] is False
        published = (engine.aew_root / service.SERVER_JSON_REL).read_text(encoding="utf-8")
        assert '"opens": false' in published
        with pytest.raises(errors.UsageError) as refused:
            service.Service(engine, console=lambda text: None)
        assert "end the `aew opencode` session" in refused.value.message
        assert "then run `aew dashboard serve`" in refused.value.message
        assert "aew dashboard open" not in refused.value.message
    # End that session, then run serve as directed: the port is free and the typed-code path is still used.
    monkeypatch.setattr(dashboard_commands, "_engine", lambda a: engine)
    confirmed = []
    monkeypatch.setattr(operator, "authorize", lambda action: confirmed.append(action))
    monkeypatch.setattr(dashboard_commands.credentials, "write_to_terminal", lambda *a: None)
    original = service.Service

    def make(engine, **kwargs):
        svc = original(engine, **kwargs)

        def wait():
            assert service.locate(engine.aew_root)["opens"] is True
            assert svc.table.newest()["scope"]["authorized_by"] == S.OPERATOR_TTY

        monkeypatch.setattr(svc, "wait", wait)
        return svc

    monkeypatch.setattr(service, "Service", make)
    dashboard_commands._serve(argparse.Namespace(session_hours=2, port=0, static=None))
    assert len(confirmed) == 1 and len(built) == 2


def test_the_real_broker_starts_the_dashboard_after_the_seat_and_before_the_tui(project, desktop, monkeypatch):
    opened, built = desktop
    monkeypatch.setenv("AEW_OPERATOR_AUTOSTART", "off")
    monkeypatch.setenv("AEW_LEAD_TOKEN", project.token)
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    engine = Engine.discover(project.root)
    events = []

    def prepared(bridge_dir, env):
        assert opened == [] and built == []
        events.append("prepared")
        return lead_broker.Harness(argv=["fake-tui"], env=env, relay=False, label={},
                                   close=lambda: events.append("closed"))

    def tui(*args, **kwargs):
        assert len(opened) == len(built) == 1
        assert built[0].table.newest()["scope"]["authorized_by"] == S.OPERATOR_START
        events.append("tui")
        return 0, "clean"

    monkeypatch.setattr(procs, "run_session_tree", tui)
    with lead.session_services(engine, provider_env=[]) as on_ready:
        result = lead_broker.run_session(engine, ["fake-tui"], acquire=False, session_label=None, keep_seat=False,
                                         contained=prepared, on_ready=on_ready)
    assert result["ok"] and events == ["prepared", "tui", "closed"]
    assert service.locate(engine.aew_root) is None
