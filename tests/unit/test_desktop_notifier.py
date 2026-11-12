"""`aew notify desktop`, the default notifier `aew init` writes (register E104, minimal). It shows a notify event as one
desktop notification on Linux (notify-send) and Windows (a toast: A-44 BOY-B5, which the operator pulled into V-01 on
2026-11-10). It refuses with its fix when no desktop session is present, never shows an event's reason, and its toast
gets no console window. Run's gate refuses the shipped default while it cannot deliver, and the endpoint runs the
default as its own engine. Every test here fakes the process it would start, and conftest's ``no_desktop_notification``
keeps every other test from showing one.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from aew import errors
from aew.cli.main import main
from aew.engine import steering
from aew.harness import desktop_notifier as D
from aew.harness import notify, procs
from aew.harness.agentenv import POSIX_KEEP

LINUX_SESSION = {"PATH": "/usr/bin", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
EVENT = {"schema": "aew/notify-event/v1", "event": "hard_deadline", "project_id": "demo", "subject": "R-INV-0001-1",
         "reason": "an agent wrote this", "ref": None, "revision": 1, "at": "2026-11-10T00:00:00Z",
         "source": "spool:run-R-INV-0001-1", "authenticated": False}


@pytest.fixture
def which(monkeypatch):
    """`shutil.which` as the test says: the programs found, by name."""
    found: set[str] = set()
    monkeypatch.setattr(D.shutil, "which", lambda name, path=None: f"/bin/{name}" if name in found else None)
    return found


class Runs:
    """A recording `subprocess.run`: nothing is started."""

    def __init__(self, returncode: int = 0, stdout: bytes = b"") -> None:
        self.calls: list[dict[str, Any]] = []
        self.returncode, self.stdout = returncode, stdout

    def __call__(self, argv: list[str], **kw: Any) -> Any:
        self.calls.append({"argv": argv, **kw})
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout)


# ---------------------------------------------------------------------------------------------- the session check


def test_linux_needs_the_session_bus_and_notify_send_and_no_display(which, real_desktop_notifier):
    """A-44 BOY-12.a: notify-send talks only to the session bus, so the check asks for the bus, never a display."""
    which.add("notify-send")
    assert D.problem(LINUX_SESSION, platform="linux") is None  # no DISPLAY, no WAYLAND_DISPLAY
    no_bus = {"PATH": "/usr/bin", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}
    assert D.problem(no_bus, platform="linux") == (
        "no desktop session: DBUS_SESSION_BUS_ADDRESS is not set and XDG_RUNTIME_DIR has no session bus")
    with_runtime = {"PATH": "/usr/bin", "XDG_RUNTIME_DIR": "/run/user/1000"}
    assert D.problem(with_runtime, platform="linux", bus_socket=lambda p: p.replace("\\", "/") ==
                     "/run/user/1000/bus") is None
    assert "no desktop session" in D.problem(with_runtime, platform="linux", bus_socket=lambda p: False)
    which.clear()
    assert D.problem(LINUX_SESSION, platform="linux") == (
        "notify-send is not installed (libnotify; `libnotify-bin` on Debian and Ubuntu)")


def test_windows_needs_an_interactive_session_and_powershell(which, real_desktop_notifier):
    """The toast (A-44 BOY-B5, in V-01 by the operator's ruling of 2026-11-10): available, so Run's gate accepts the
    default, only in an interactive session with Windows PowerShell."""
    which.add("powershell.exe")
    assert D.problem({"PATH": "C:\\Windows"}, platform="win32", session_id=lambda: 1) is None
    for service in (0, None):  # session 0, where services run; or a session that cannot be read
        found = D.problem({}, platform="win32", session_id=lambda s=service: s)
        assert found is not None and "outside an interactive Windows session" in found
    which.clear()
    assert "powershell.exe" in D.problem({}, platform="win32", session_id=lambda: 1)


def test_another_platform_has_no_desktop_notifier(real_desktop_notifier):
    assert D.problem(LINUX_SESSION, platform="darwin") == "no desktop notifier on this platform (darwin)"


def test_the_notifier_gets_the_session_bus_and_never_a_display(monkeypatch):
    """A-44 BOY-12.a's keep-list: beyond the keep-list, the notifier's child gets exactly the session bus's two
    variables, never `DISPLAY`, `WAYLAND_DISPLAY` or `XAUTHORITY`; and every variable the session check reads
    survives, so `notifier_problem` in the endpoint answers as the notifier would."""
    assert D.SESSION_VARS == ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR")
    monkeypatch.setattr(notify.sys, "platform", "linux")
    base = {**LINUX_SESSION, "XDG_RUNTIME_DIR": "/run/user/1000", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0",
            "XAUTHORITY": "/home/u/.Xauthority", "OPENAI_API_KEY": "sk-synthetic", "AEW_LEAD_TOKEN": "synthetic"}
    kept = notify.sanitized_env(base)
    assert {k: kept.get(k) for k in (*D.SESSION_VARS, "PATH")} == {k: base.get(k) for k in (*D.SESSION_VARS, "PATH")}
    assert set(kept) - POSIX_KEEP - {"PATH"} == set(D.SESSION_VARS)
    for absent in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "OPENAI_API_KEY", "AEW_LEAD_TOKEN"):
        assert absent not in kept, absent


# ---------------------------------------------------------------------------------------------- showing one


def test_linux_shows_kind_subject_and_project_never_the_reason(monkeypatch):
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    runs = Runs()
    out = D.show(EVENT, env=LINUX_SESSION, platform="linux", run=runs)
    (call,) = runs.calls
    assert call["argv"] == ["notify-send", "--app-name=AEW", "--", "AEW: hard deadline",
                            "R-INV-0001-1 (project demo)"]
    assert call["creationflags"] == 0 and call["stdin"] == subprocess.DEVNULL and call["timeout"] == D.TIMEOUT_S
    assert out == {"ok": True, "shown": {"title": "AEW: hard deadline", "body": "R-INV-0001-1 (project demo)"}}
    assert "agent wrote" not in json.dumps(call, default=str)


def test_a_raise_toast_names_the_mode_asked_for_and_never_the_rationale():
    """The designer's ruling of 2026-11-11 on SYS-04, part 4(b): a raise's toast names the requested mode, an enum,
    and never the Lead's rationale (its ``reason``)."""
    raise_ = {**EVENT, "event": "raise_requested", "subject": "SR-1", "reason": "the Lead's own words", "ref": "run"}
    assert D.text(raise_) == ("AEW: raise requested to run", "SR-1 (project demo)")
    assert all("the Lead's own words" not in part for part in D.text(raise_))


@pytest.mark.parametrize("event", [
    {"event": "raise_requested", "ref": "run now, said the agent"},  # not one of steering's modes
    {"event": "raise_requested", "ref": None},
    {"event": "confirmation_requested", "ref": "run"},  # only a raise's ref is a mode
    {"event": "hard_deadline", "ref": "walk"},
])
def test_a_toast_names_no_ref_that_is_not_a_raise_s_mode(event):
    title, body = D.text({**EVENT, **event})
    assert title == "AEW: " + event["event"].replace("_", " ")
    assert str(event["ref"]) not in body


def test_windows_passes_the_text_as_data_and_opens_no_console(monkeypatch):
    """The title and body reach the toast as environment values that the script escapes, never as script text; the
    child gets CREATE_NO_WINDOW."""
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    runs = Runs()
    hostile = {**EVENT, "subject": "'); Remove-Item C:\\ <x>"}
    D.show(hostile, env={"PATH": "C:\\Windows"}, platform="win32", run=runs)
    (call,) = runs.calls
    assert call["argv"][-1] == D.TOAST and "Remove-Item" not in " ".join(call["argv"])
    assert call["env"][D.BODY_VAR].startswith("'); Remove-Item") and call["env"][D.TITLE_VAR] == "AEW: hard deadline"
    assert call["creationflags"] & procs.CREATE_NO_WINDOW
    assert "[Security.SecurityElement]::Escape" in D.TOAST


def test_with_no_desktop_session_it_refuses_with_the_fix_and_starts_nothing(monkeypatch):
    monkeypatch.setattr(D, "problem", lambda env, platform=None: "no desktop session: neither DISPLAY nor ...")
    runs = Runs()
    with pytest.raises(errors.CapabilityUnavailable) as exc:
        D.show(EVENT, env={}, platform="linux", run=runs)
    assert runs.calls == [] and exc.value.details == {"reason": "no_desktop_session"}
    assert "neither DISPLAY" in exc.value.message and D.FIX in exc.value.message


def test_a_failed_notifier_is_an_error_with_its_output(monkeypatch):
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    with pytest.raises(errors.AEWError, match="exited 1: GDBus.Error: no notification daemon"):
        D.show(EVENT, env=LINUX_SESSION, platform="linux", run=Runs(1, b"GDBus.Error: no notification daemon\n"))


def test_text_is_capped_and_printable():
    title, body = D.text({"event": "x\x1b[2J" * 100, "subject": None, "project_id": ""})
    assert "\x1b" not in title and len(title) <= len("AEW: ") + D.MAX_TEXT
    assert body == "the operator endpoint has news for you"


@pytest.mark.parametrize("data", [b"", b"[]", b"{\"event\": 3}", b"\xff", b"x" * (D.MAX_EVENT_BYTES + 1)],
                         ids=["empty", "not-an-object", "no-event-string", "not-utf8", "oversize"])
def test_stdin_must_hold_one_bounded_event(data):
    with pytest.raises(errors.UsageError):
        D.read_event(io.BytesIO(data))


# ---------------------------------------------------------------------------------------------- the command


def test_the_command_reads_the_event_on_stdin(monkeypatch, capsys):
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    runs = Runs()
    monkeypatch.setattr(D.subprocess, "run", runs)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(EVENT).encode())))
    assert main(["notify", "desktop"]) == 0
    assert json.loads(capsys.readouterr().out)["shown"]["title"] == "AEW: hard deadline" and len(runs.calls) == 1


def test_the_command_refuses_with_no_desktop_session(monkeypatch, capsys):
    monkeypatch.setattr(D, "problem", lambda env, platform=None: "no desktop session: test")
    runs = Runs()
    monkeypatch.setattr(D.subprocess, "run", runs)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(EVENT).encode())))
    assert main(["notify", "desktop"]) == errors.CapabilityUnavailable.exit_code
    err = json.loads(capsys.readouterr().err)["error"]
    assert err["code"] == "CAPABILITY_UNAVAILABLE" and "no desktop session: test" in err["message"]
    assert err["details"] == {"reason": "no_desktop_session"} and runs.calls == []


def test_check_says_why_it_is_unavailable_and_shows_nothing(monkeypatch, capsys):
    monkeypatch.setattr(D, "problem", lambda env, platform=None: "no desktop session: test")
    runs = Runs()
    monkeypatch.setattr(D.subprocess, "run", runs)
    assert main(["notify", "desktop", "--check"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "available": False, "why": "no desktop session: test",
                                                   "fix": D.FIX}
    assert runs.calls == []
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    assert main(["notify", "desktop", "--check"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "available": True} and runs.calls == []


# ---------------------------------------------------------------------------------------------- Run's gate


@pytest.mark.parametrize("command", [["aew", "notify", "desktop"], ["/opt/venv/bin/aew", "notify", "desktop"],
                                     ["C:\\venv\\Scripts\\aew.exe", "notify", "desktop"]])
def test_the_default_is_recognised_by_name_or_path(command):
    assert D.is_default(command)


@pytest.mark.parametrize("command", [["aew", "notify"], ["aew", "notify", "desktop", "--check"],
                                     ["notify-send", "notify", "desktop"], "aew notify desktop"])
def test_anything_else_is_the_operator_s_own_notifier(command):
    assert not D.is_default(command)


def test_run_refuses_the_default_while_it_cannot_deliver(monkeypatch, tmp_path):
    """BOY-12.d: the shipped default is refused at the raise and at each Run activation while no desktop session is
    present, with the fix naming both ways back; a command the operator wrote keeps the executable check alone."""
    exe = tmp_path / ("notifier.exe" if sys.platform == "win32" else "notifier")
    exe.write_bytes(b"")
    exe.chmod(0o755)
    default = {"notify": {"command": ["aew", "notify", "desktop"]}}
    monkeypatch.setattr(D, "problem", lambda env, platform=None: "no desktop session: test")
    refused = steering.notifier_problem(default)
    assert refused is not None and "no desktop session: test" in refused and D.FIX in refused
    own = {"notify": {"command": [str(exe), "--my-notifier"]}}
    assert steering.notifier_problem(own) is None
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    assert steering.notifier_problem(default) is None


def test_the_default_runs_the_endpoints_own_engine_whatever_is_on_path(monkeypatch):
    """Review of E228's third PR, F7: the default needs no `aew` on PATH, and an older one there never runs: the
    endpoint runs its own interpreter's `-m aew`, as its autostart starts the endpoint, and the gate checks that."""
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    assert steering.notifier_problem({"notify": {"command": ["aew", "notify", "desktop"]}}) is None
    for default in (["aew", "notify", "desktop"], ["/opt/old/bin/aew", "notify", "desktop"]):
        assert D.runnable(default) == [sys.executable, *procs.ENGINE_PYTHON_FLAGS, "-m", "aew", "notify", "desktop"]
    assert D.runnable(["/usr/local/bin/my-notifier", "--x"]) == ["/usr/local/bin/my-notifier", "--x"]


def test_the_endpoints_watcher_delivers_the_default_as_its_own_engine(project, tmp_path, monkeypatch):
    """Quick check of E228's third PR, M3: the watcher hands `deliver` the default as ``runnable`` makes it, so the
    endpoint's own interpreter runs it, never the `aew` on PATH. `deliver` is replaced, so nothing is shown."""
    from notifier import adopt, until

    from aew.harness import event_spool

    adopt(project, command=list(D.COMMAND))
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)  # a desktop that could show it
    argvs: list[list[str]] = []

    def deliver(command: list[str], event: dict[str, Any], **kw: Any) -> dict[str, Any]:
        argvs.append(list(command))
        return {"outcome": "delivered", "reason": None, "exit_code": 0, "timed_out": False, "output_bytes": 0,
                "discarded_bytes": 0}

    monkeypatch.setattr(notify, "deliver", deliver)
    watcher = notify.Watcher(project.root, project.root / ".aew")
    watcher.pass_once()
    watcher.start()
    try:
        event_spool.append(project.root / ".aew", event_spool.BROKER, "loop_stopped", subject="T-0001",
                           reason="REPETITION: the test's stop", ref="LA-1-1")
        until(lambda: argvs, what="the delivery")
    finally:
        watcher.close()
    assert argvs[0] == [sys.executable, *procs.ENGINE_PYTHON_FLAGS, "-m", "aew", "notify", "desktop"], argvs


def test_no_test_shows_the_shipped_default():
    """The positive control of conftest's `no_desktop_notification`: in any test that does not ask for the real check,
    the shipped default is unavailable, so it shows nothing and Run's gate refuses it."""
    from conftest import NO_DESKTOP_IN_TESTS

    assert D.problem(LINUX_SESSION, platform="linux") == NO_DESKTOP_IN_TESTS
    refused = steering.notifier_problem({"notify": {"command": ["aew", "notify", "desktop"]}})
    assert refused is not None and NO_DESKTOP_IN_TESTS in refused
    runs = Runs()
    with pytest.raises(errors.CapabilityUnavailable):
        D.show(EVENT, env=LINUX_SESSION, platform="linux", run=runs)
    assert runs.calls == []
