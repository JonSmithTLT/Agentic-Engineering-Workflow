"""The capability register's host state (STG-15, A-38: CAPR-03, CAPR-04, CAPR-13).

Per host, outside every project and every sandbox's writable binds: ``$XDG_DATA_HOME/aew/capability`` (by default
``~/.local/share/aew/capability``), or ``%LOCALAPPDATA%\\aew\\capability`` on Windows. It holds:

* ``register.json``: the operator's records and settings, the health checks' results and the refused payloads, one
  document replaced whole under ``register.lock``;
* ``payloads/<provider>/<sha256 prefix>/<command>``: each pinned executable, in a directory of its own that holds
  nothing else, so a later PATH entry can name it (CAPR-04);
* ``changes.jsonl``: one line per operator change, with its time, its author and its authorization (CAPR-13).

Only operator commands write the records and settings; the health checks write their results (the stage's parts
table).
"""

from __future__ import annotations

import contextlib
import errno
import getpass
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aew.errors import IntegrityError, PermissionDenied
from aew.util import atomic_write, utc_now

FORMAT = 1
REGISTER, LOCK, CHANGES, PAYLOADS = "register.json", "register.lock", "changes.jsonl", "payloads"
# How long a second register command waits for the lock before it is refused (LOCK_TIMEOUT), as the control store's
# lock waits. A holder may be fetching payloads and running their health checks, each bounded by its own timeout
# (payload.FETCH_TIMEOUT_S, status.HEALTH_TIMEOUT_S) but not, all together, by this one (review N3).
LOCK_TIMEOUT_S = 60.0
NOT_WRITABLE = "register_not_writable"

# Tests point the register at a directory of their own, in process; the product never sets it. (An environment
# variable would let any process that launches AEW choose another register.)
ROOT_OVERRIDE: Path | None = None


def base_variable() -> str:
    """The environment variable that names the directory the register lives under on this platform."""
    return "LOCALAPPDATA" if sys.platform == "win32" else "XDG_DATA_HOME"


def root() -> Path:
    """This host's register directory."""
    if ROOT_OVERRIDE is not None:
        return ROOT_OVERRIDE
    if sys.platform == "win32":
        base = os.environ.get(base_variable()) or str(Path.home() / "AppData" / "Local")
    else:  # the XDG base directory rule: a relative XDG_DATA_HOME is ignored
        xdg = os.environ.get(base_variable()) or ""
        base = xdg if os.path.isabs(xdg) else str(Path.home() / ".local" / "share")
    return Path(base) / "aew" / "capability"


def empty() -> dict[str, Any]:
    return {"format": FORMAT, "host_copies": True, "operator_records": {}, "checks": {}, "refused": {},
            "fetch_failures": {}}


def read(directory: Path | None = None) -> dict[str, Any]:
    """The register's state; an empty one where none was written yet. An unreadable one raises ``IntegrityError``,
    which every reader reports as the cause of every capability's REFUSED (never a crash, never a silent default)."""
    path = (directory or root()) / REGISTER
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return empty()
    except OSError as exc:
        raise IntegrityError(f"the capability register {path} cannot be read: {exc}", path=str(path),
                             reason="register_unreadable") from None
    try:
        state = json.loads(raw)
    except ValueError as exc:
        raise IntegrityError(f"the capability register {path} is not JSON ({exc}); move it aside and run `aew "
                             "capability check` to start a new one", path=str(path),
                             reason="register_unreadable") from None
    if not isinstance(state, dict) or state.get("format") != FORMAT:
        raise IntegrityError(f"the capability register {path} has an unknown format; this AEW reads format {FORMAT}",
                             path=str(path), reason="register_format")
    out = empty()
    out.update({k: v for k, v in state.items() if k in out})
    return out


@contextlib.contextmanager
def writing(target: Path) -> Iterator[None]:
    """Every write under the register at ``target`` goes through here: its state, its lock's own file, its change log
    and its payloads. Where the register cannot be written, as in a contained run, whose sandbox sees it read-only
    (CAPR-Q02), the write is refused with its own reason, never a crash (CAP-1 review F1)."""
    try:
        yield
    except OSError as exc:
        # The OS's own words stay out of the message: errno's name says it (a contained run's checks read its output)
        name = errno.errorcode.get(exc.errno or 0, type(exc).__name__)
        raise PermissionDenied(f"the capability register at {target} cannot be written by this process ({name}); a "
                               "contained run sees it read-only: run `aew capability check` at the operator's own "
                               "terminal, and `aew capability list` reads the register here", path=str(target),
                               errno=name, reason=NOT_WRITABLE) from None


def write(state: dict[str, Any], directory: Path | None = None) -> None:
    """Replace the register's state. Callers hold :func:`locked`."""
    target = directory or root()
    with writing(target):
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write(target / REGISTER, json.dumps(state, indent=1, sort_keys=True) + "\n")


@contextlib.contextmanager
def locked(directory: Path | None = None) -> Iterator[Path]:
    """The register's lock, held for a read-change-write of its state."""
    from aew.engine.lock import FileLock

    target = directory or root()
    with writing(target):
        target.mkdir(mode=0o700, parents=True, exist_ok=True)  # the register is the operator's own, as AEW's store is
        lock = FileLock(target / LOCK, timeout=LOCK_TIMEOUT_S)
        lock.__enter__()
    try:
        yield target
    finally:
        with writing(target):
            lock.__exit__(None, None, None)


def payload_dir(name: str, sha256: str, directory: Path | None = None) -> Path:
    """The directory of one pinned executable: a new pin is a new directory, so a check never reads a half-replaced
    payload."""
    return (directory or root()) / PAYLOADS / name / sha256[:16]


def executable_name(command: str) -> str:
    return f"{command}.exe" if sys.platform == "win32" else command


def record_change(command: str, what: dict[str, Any], authorization: dict[str, str] | None,
                  directory: Path | None = None) -> dict[str, Any]:
    """Append one operator change to the change log: its time, its author (this host's account) and how the operator
    authorized it (CAPR-13). Never the confirmation code itself."""
    try:
        author = getpass.getuser()
    except (OSError, KeyError):  # no account name (a container without a passwd entry)
        getuid = getattr(os, "getuid", None)
        author = f"uid {getuid()}" if getuid is not None else "unknown"
    entry = {"at": utc_now(), "by": author, "command": command, **what,
             "authorized_by": (authorization or {}).get("authorized_by")}
    target = directory or root()
    with writing(target):
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(target / CHANGES, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry
