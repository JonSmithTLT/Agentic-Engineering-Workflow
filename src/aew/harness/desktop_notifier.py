"""`aew notify desktop`: the default notifier `aew init` writes (register E104, minimal; A-44's slice S3).

The operator endpoint runs the execution policy's ``notify.command`` with one ``aew/notify-event/v1`` object on stdin
(``aew.harness.notify``). This command turns that event into one desktop notification:

- **Linux:** ``notify-send`` (libnotify), which needs the desktop session's bus and a display. The endpoint passes
  the notifier only a sanitized environment, so ``notify.sanitized_env`` keeps the session's own variables
  (:data:`SESSION_VARS`), which carry no credential.
- **Windows:** a toast from Windows PowerShell 5.1, with the title and body passed as environment values, never as
  script text. The interactive session is any but session 0, where services run and no toast can show.

With no desktop session it refuses, naming what is missing and both ways back: run the endpoint in the desktop
session, or set ``notify.command`` to a notifier of your own. :func:`problem` is the same check: ``notifier_problem``
uses it for the shipped default, so Run's raise and each Run activation refuse the default while it cannot deliver
(BOY-12.d).

What it shows is the event's kind, its subject and the project, never its ``reason``: a reason can come from a run's
spool line, which an agent can write (A-44: the desktop shows no agent text).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from typing import Any

from aew.harness import procs

COMMAND = ("aew", "notify", "desktop")  # the shipped default's argv, as `aew init` writes it
SESSION_VARS = ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR")
MAX_EVENT_BYTES = 65536
TIMEOUT_S = 8.0  # inside the endpoint's own notifier timeout (notify.DEFAULT_TIMEOUT_S, 10 s)
MAX_TEXT = 200
TITLE_VAR, BODY_VAR = "NOTIFY_TITLE", "NOTIFY_BODY"
# Windows PowerShell's own AppUserModelID: a toast needs a registered app id, and this one ships with Windows.
POWERSHELL_APP_ID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
TOAST = (
    "$ErrorActionPreference = 'Stop';"
    "[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime];"
    "[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime];"
    f"$t = [Security.SecurityElement]::Escape($env:{TITLE_VAR});"
    f"$b = [Security.SecurityElement]::Escape($env:{BODY_VAR});"
    "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
    "$x.LoadXml(\"<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual>"
    "</toast>\");"
    f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{POWERSHELL_APP_ID}')"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
)
FIX = ("run the operator endpoint (`aew operator serve`) in your desktop session, or set the execution policy's "
       "`notify.command` to a notifier of your own")


def is_default(command: Any) -> bool:
    """Whether ``command`` is the shipped default: ``aew notify desktop``, with ``aew`` by name or by path."""
    if not isinstance(command, (list, tuple)) or len(command) != len(COMMAND):
        return False
    program = os.path.basename(str(command[0])).lower()
    return program in ("aew", "aew.exe") and tuple(command[1:]) == COMMAND[1:]


def resolve(command: Any) -> str | None:
    """The file ``command[0]`` names: looked up on ``PATH`` when it is a bare name, otherwise the path as written."""
    program = str(command[0])
    return shutil.which(program) if os.sep not in program and "/" not in program else program


def windows_session_id() -> int | None:
    """This process's Terminal Services session, or ``None`` when it cannot be read."""
    import ctypes

    sid = ctypes.c_ulong()
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    if not kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(sid)):
        return None
    return int(sid.value)


def problem(env: Mapping[str, str], *, platform: str | None = None,
            session_id: Callable[[], int | None] | None = None,
            bus_socket: Callable[[str], bool] = os.path.exists) -> str | None:
    """Why no desktop notification can be shown with ``env``, or ``None``."""
    platform = sys.platform if platform is None else platform
    path = env.get("PATH") or env.get("Path") or ""
    if platform == "win32":
        if (session_id or windows_session_id)() in (0, None):
            return "no desktop session: this process runs outside an interactive Windows session (session 0)"
        if not shutil.which("powershell.exe", path=path):
            return "Windows PowerShell (powershell.exe) is not on PATH"
        return None
    if not platform.startswith("linux"):
        return f"no desktop notifier on this platform ({platform})"
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return "no desktop session: neither DISPLAY nor WAYLAND_DISPLAY is set"
    runtime = env.get("XDG_RUNTIME_DIR")
    if not env.get("DBUS_SESSION_BUS_ADDRESS") and not (runtime and bus_socket(os.path.join(runtime, "bus"))):
        return "no desktop session bus: DBUS_SESSION_BUS_ADDRESS is not set and XDG_RUNTIME_DIR has no bus"
    if not shutil.which("notify-send", path=path):
        return "notify-send is not installed (the libnotify package)"
    return None


def _clean(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(c if c.isprintable() else " " for c in text)[:MAX_TEXT]


def text(event: Mapping[str, Any]) -> tuple[str, str]:
    """The title and body for ``event``: its kind, subject and project, never its reason."""
    kind = _clean(event.get("event")).replace("_", " ") or "event"
    subject, project = _clean(event.get("subject")), _clean(event.get("project_id"))
    body = " ".join(p for p in (subject, f"(project {project})" if project else "") if p)
    return f"AEW: {kind}", body or "the operator endpoint has news for you"


def read_event(stream: Any) -> dict[str, Any]:
    from aew.errors import UsageError

    data = stream.read(MAX_EVENT_BYTES + 1)
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) > MAX_EVENT_BYTES:
        raise UsageError(f"the event on stdin is over {MAX_EVENT_BYTES} bytes")
    try:
        event = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError(f"stdin holds no notify event (one JSON object): {exc}") from None
    if not isinstance(event, dict) or not isinstance(event.get("event"), str):
        raise UsageError("stdin holds no notify event: a JSON object with an `event` string")
    return event


def argv(title: str, body: str, *, platform: str) -> list[str]:
    if platform == "win32":
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", TOAST]
    return ["notify-send", "--app-name=AEW", "--", title, body]


def show(event: Mapping[str, Any], *, env: Mapping[str, str] | None = None, platform: str | None = None,
         run: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Show ``event`` as one desktop notification, or refuse (``CAPABILITY_UNAVAILABLE``) with the fix. The child gets
    no console window on Windows (``CREATE_NO_WINDOW``): the toast is the only thing shown."""
    from aew.errors import AEWError, CapabilityUnavailable

    platform = sys.platform if platform is None else platform
    run = subprocess.run if run is None else run
    env = dict(os.environ if env is None else env)
    missing = problem(env, platform=platform)
    if missing:
        raise CapabilityUnavailable(f"the desktop notifier cannot show a notification: {missing}. Fix: {FIX}",
                                    reason="no_desktop_session")
    title, body = text(event)
    child = {**env, TITLE_VAR: title, BODY_VAR: body}
    flags = procs.CREATE_NO_WINDOW if platform == "win32" else 0
    try:
        done = run(argv(title, body, platform=platform), env=child, stdin=subprocess.DEVNULL,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TIMEOUT_S, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise AEWError(f"the desktop notifier did not finish in {TIMEOUT_S:g} s") from None
    except OSError as exc:
        raise AEWError(f"the desktop notifier could not start: {exc}") from None
    if done.returncode != 0:
        tail = _clean((done.stdout or b"").decode("utf-8", "replace").strip()[-MAX_TEXT:])
        raise AEWError(f"the desktop notifier exited {done.returncode}: {tail or 'no output'}")
    return {"ok": True, "shown": {"title": title, "body": body}}


def availability(env: Mapping[str, str] | None = None, *, platform: str | None = None) -> dict[str, Any]:
    """`aew notify desktop --check`: whether a notification can be shown here, and if not, why and the fix. A report,
    not a refusal: the answer "unavailable" is the check working."""
    missing = problem(dict(os.environ if env is None else env), platform=platform)
    if missing:
        return {"ok": True, "available": False, "why": missing, "fix": FIX}
    return {"ok": True, "available": True}
