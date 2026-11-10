"""`aew notify desktop`, the default notifier `aew init` writes (register E104, minimal).

It shows a notify event as one desktop notification on Linux (notify-send) and Windows (a toast), refuses with its fix
when no desktop session is present, never shows an event's reason, and gets no console window. Run's gate refuses the
shipped default while it cannot deliver. Every test here fakes the process it would start: none shows a notification.
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

LINUX_SESSION = {"PATH": "/usr/bin", "DISPLAY": ":0", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
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


def test_linux_needs_a_display_a_session_bus_and_notify_send(which):
    which.add("notify-send")
    assert D.problem(LINUX_SESSION, platform="linux") is None
    assert D.problem({**LINUX_SESSION, "DISPLAY": ""}, platform="linux") == (
        "no desktop session: neither DISPLAY nor WAYLAND_DISPLAY is set")
    wayland = {**LINUX_SESSION, "DISPLAY": "", "WAYLAND_DISPLAY": "wayland-0"}
    assert D.problem(wayland, platform="linux") is None
    no_bus = {"PATH": "/usr/bin", "DISPLAY": ":0"}
    assert "no desktop session bus" in D.problem(no_bus, platform="linux")
    with_runtime = {**no_bus, "XDG_RUNTIME_DIR": "/run/user/1000"}
    assert D.problem(with_runtime, platform="linux", bus_socket=lambda p: p.replace("\\", "/") ==
                     "/run/user/1000/bus") is None
    assert "no desktop session bus" in D.problem(with_runtime, platform="linux", bus_socket=lambda p: False)
    which.clear()
    assert D.problem(LINUX_SESSION, platform="linux") == "notify-send is not installed (the libnotify package)"


def test_windows_needs_an_interactive_session_and_powershell(which):
    which.add("powershell.exe")
    assert D.problem({"PATH": "C:\\Windows"}, platform="win32", session_id=lambda: 1) is None
    for service in (0, None):  # session 0, where services run; or a session that cannot be read
        found = D.problem({}, platform="win32", session_id=lambda s=service: s)
        assert found is not None and "outside an interactive Windows session" in found
    which.clear()
    assert "powershell.exe" in D.problem({}, platform="win32", session_id=lambda: 1)


def test_another_platform_has_no_desktop_notifier():
    assert D.problem(LINUX_SESSION, platform="darwin") == "no desktop notifier on this platform (darwin)"


def test_the_session_check_reads_only_what_the_endpoint_passes_its_notifier(monkeypatch):
    """`notifier_problem` checks the endpoint's own environment: that answers as the notifier's would only because
    every variable the check reads survives `notify.sanitized_env`."""
    monkeypatch.setattr(notify.sys, "platform", "linux")
    base = {**LINUX_SESSION, "XDG_RUNTIME_DIR": "/run/user/1000", "WAYLAND_DISPLAY": "wayland-0",
            "OPENAI_API_KEY": "sk-synthetic", "AEW_LEAD_TOKEN": "synthetic"}
    kept = notify.sanitized_env(base)
    assert {k: kept.get(k) for k in (*D.SESSION_VARS, "PATH")} == {k: base.get(k) for k in (*D.SESSION_VARS, "PATH")}
    assert "OPENAI_API_KEY" not in kept and "AEW_LEAD_TOKEN" not in kept


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
    exe = tmp_path / ("aew.exe" if sys.platform == "win32" else "aew")
    exe.write_bytes(b"")
    exe.chmod(0o755)
    default = {"notify": {"command": [str(exe), "notify", "desktop"]}}
    monkeypatch.setattr(D, "problem", lambda env, platform=None: "no desktop session: test")
    refused = steering.notifier_problem(default)
    assert refused is not None and "no desktop session: test" in refused and D.FIX in refused
    own = {"notify": {"command": [str(exe), "--my-notifier"]}}
    assert steering.notifier_problem(own) is None
    monkeypatch.setattr(D, "problem", lambda env, platform=None: None)
    assert steering.notifier_problem(default) is None
