"""`aew notify file PATH`: a headless notifier AEW ships, for an endpoint with no desktop session (an ssh login on a
Linux host). The operator approved it on 2026-11-11 ("right if its small sure"), from the RUN readiness walk's
finding 5.

The operator endpoint runs it as it runs ``aew notify desktop``: as its own engine (``desktop_notifier.runnable``),
with one ``aew/notify-event/v1`` object on stdin. It appends one JSON line per event to ``PATH``: the time, the
event's kind, subject, project, revision and source, and the title and body the desktop notifier would show
(``desktop_notifier.text``, so a raise names its mode). Never the event's ``reason``, which can be the Lead's
rationale or a run's spool text: the toast's rule (A-44: the operator's notifications carry no agent text).

The file is bounded as the endpoint's own delivery log is (``notify.LOG_MAX_BYTES``, ``notify.LOG_KEEP`` rotated
copies, ``PATH.1`` newest). The endpoint delivers one event at a time, so nothing else appends while one runs.

``PATH`` must be absolute: the raise checks it in the operator's process and the endpoint runs it from the project's
root, so a relative path would name two places.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PREFIX = ("aew", "notify", "file")  # the argv `notify.command` names it by, with the path as its one argument
FIX = ("set the execution policy's `notify.command` to `[aew, notify, file, <an absolute path you can write>]`, or "
       "fix the path it names")


def matches(command: Any) -> bool:
    """Whether ``command`` is ``aew notify file PATH``, with ``aew`` by name or by path."""
    if not isinstance(command, (list, tuple)) or len(command) != len(PREFIX) + 1:
        return False
    program = str(command[0]).replace("\\", "/").rsplit("/", 1)[-1].lower()  # either separator, on any platform
    return program in ("aew", "aew.exe") and tuple(command[1:3]) == PREFIX[1:]


def problem(path: str) -> str | None:
    """Why ``path`` cannot take the events, or ``None``: it must be absolute, and be a regular file this process can
    write or a path whose nearest existing directory it can write (the parents are created at the first event).
    Writes nothing."""
    target = Path(path)
    if not target.is_absolute():
        return f"the file notifier's path `{path}` is not absolute"
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        info = None
    except OSError as exc:
        return f"the file notifier's path `{path}` cannot be read: {exc.strerror or exc}"
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            return f"the file notifier's path `{path}` is not a regular file"
        return None if os.access(target, os.W_OK) else f"the file notifier's path `{path}` is not writable"
    parent = target.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
        return f"the file notifier cannot create `{path}`: `{parent}` is not a directory it can write"
    return None


def availability(path: str) -> dict[str, Any]:
    """`aew notify file PATH --check`: whether events can be appended to ``PATH``, and if not why and the fix."""
    missing = problem(path)
    if missing:
        return {"ok": True, "available": False, "why": missing, "fix": FIX}
    return {"ok": True, "available": True, "path": str(Path(path))}


def line(event: Mapping[str, Any], at: str) -> dict[str, Any]:
    """The record appended for ``event``: what the toast shows, and the event's identifying fields; never its
    ``reason``."""
    from aew.harness import desktop_notifier

    title, body = desktop_notifier.text(event)
    clean = desktop_notifier._clean  # the toast's own cleaning: printable, bounded
    return {"at": at, "title": title, "body": body, "event": clean(event.get("event")),
            "subject": clean(event.get("subject")), "project_id": clean(event.get("project_id")),
            "revision": event.get("revision") if isinstance(event.get("revision"), int) else None,
            "source": clean(event.get("source")), "authenticated": event.get("authenticated") is True}


def append(event: Mapping[str, Any], path: str) -> dict[str, Any]:
    """Append ``event``'s line to ``path``, rotating first when it would pass the bound; refuses, with the fix, when
    the path cannot take it."""
    from aew.errors import CapabilityUnavailable
    from aew.harness import notify
    from aew.util import utc_now

    missing = problem(path)
    if missing:
        raise CapabilityUnavailable(f"the file notifier cannot write: {missing}. Fix: {FIX}", reason="not_writable")
    target = Path(path)
    text = json.dumps(line(event, utc_now()), sort_keys=True, separators=(",", ":")) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        full = target.stat().st_size + len(text.encode("utf-8")) > notify.LOG_MAX_BYTES
    except FileNotFoundError:
        full = False
    if full:
        for n in range(notify.LOG_KEEP - 1, 0, -1):
            older = target.with_name(f"{target.name}.{n}")
            if older.exists():
                os.replace(older, target.with_name(f"{target.name}.{n + 1}"))
        os.replace(target, target.with_name(f"{target.name}.1"))
    with target.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return {"ok": True, "appended": str(target)}
