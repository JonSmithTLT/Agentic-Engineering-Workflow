"""Which store writers are running, and the groups each holds (STG-05 CB-08; WIS-01a, "every running store writer
must hold the store's group", A-36). WIS-01a leaves the mechanism to the build; `aew doctor` reports the same fact.

Every process that opens the control lock (``ControlStore.control_lock``, the one opener, so every store writer)
registers in ``.aew/local/writers/``: one entry per process and project, ``<pid>-<random>.json``, with its
credentials. It holds an exclusive ``flock`` on its entry while any ``ControlStore`` for that project is alive in it.
A reader tries the same lock without waiting: if it gets it, the kernel released the owner's lock, so the owner has
exited (crashed or killed included), and the entry is removed. No process ID is trusted, so a reused one is harmless.

**What it can and cannot change.** A writer's own answer comes from its own credentials (:data:`CREDENTIALS`), never
from its entry. The directory is ``0700`` and every entry ``0600`` whatever the store's target: every writer runs as
the operator's UID, and nothing else needs them. Agent layouts hide ``.aew/local`` whole (CBF-1). A process of the
operator's UID that forges or removes entries can only make every writer publish owner-only (an entry that lacks the
group) or make the writers disagree (a hidden entry), which WIS-01a states fails closed: the store's group is used only
where WIS-01a holds by the host and root's record, so no file is readable to anyone new either way.

Nothing here reads an environment variable (a test checks it). Windows has no groups: nothing registers there.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from aew.engine.store_group import Credentials

WRITERS_REL = "local/writers"
DIR_MODE = 0o700
ENTRY_MODE = 0o600
_MAX_ENTRY = 1 << 16


@dataclass(frozen=True)
class Writer:
    """A running store writer, as its entry reports it. ``refused`` is a group the file system refused it (``EPERM``
    from ``chown``): it counts as lacking that group whatever its credentials say."""

    pid: int
    entry_point: str | None
    egid: int
    groups: frozenset[int]
    refused: int | None = None
    note: str | None = None  # why the entry could not be read (it then holds nothing)

    def holds(self, gid: int) -> bool:
        return gid != self.refused and self.note is None and (gid == self.egid or gid in self.groups)

    def name(self) -> str:
        return f"pid {self.pid} ({self.entry_point or 'an undeclared AEW process, such as the Lead broker'})"


def own() -> Credentials:
    if sys.platform == "win32":  # pragma: windows-only
        return Credentials(0, frozenset())
    return Credentials(os.getegid(), frozenset(os.getgroups()))  # pragma: posix-only


# The seam: this process's own credentials. Tests replace it in-process, or in a child through tests/helpers/host_seam.
CREDENTIALS: Callable[[], Credentials] = own


class Registration:
    """This process's entry for one project: created, locked, then published, so no reader sees an unlocked live
    entry."""

    def __init__(self, aew_root: Path, entry_point: str | None) -> None:
        self.dir = aew_root / WRITERS_REL
        self.refused: int | None = None
        self._entry_point = entry_point
        self.name = f"{os.getpid()}-{secrets.token_hex(8)}.json"
        self.path = self.dir / self.name
        self.fd: int | None = None
        self.users = 0
        self._open()

    def _open(self) -> None:
        if sys.platform == "win32":  # pragma: windows-only (register makes none there)
            raise NotImplementedError("no store-writer entries on Windows")
        import fcntl  # pragma: posix-only

        self.dir.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        os.chmod(self.dir, DIR_MODE)  # mkdir is filtered by the umask, and an existing directory keeps its mode
        tmp = self.dir / f".{self.name}.tmp"
        fd = os.open(tmp, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), ENTRY_MODE)
        try:
            os.fchmod(fd, ENTRY_MODE)
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._write(fd)
            os.rename(tmp, self.path)
        except BaseException:
            os.close(fd)
            tmp.unlink(missing_ok=True)
            raise
        self.fd = fd

    def _write(self, fd: int) -> None:
        if sys.platform == "win32":  # pragma: windows-only
            raise NotImplementedError("no store-writer entries on Windows")
        creds = CREDENTIALS()  # pragma: posix-only
        data = json.dumps({"pid": os.getpid(), "entry_point": self._entry_point, "egid": creds.egid,
                           "groups": sorted(creds.groups), "refused": self.refused}, sort_keys=True).encode()
        os.ftruncate(fd, 0)
        os.pwrite(fd, data, 0)

    def refuse(self, gid: int) -> None:
        """The file system refused this process ``gid``: say so in its entry, so every other writer counts it as
        lacking the group too."""
        self.refused = gid
        if self.fd is not None:
            self._write(self.fd)

    def close(self) -> None:
        fd, self.fd = self.fd, None
        if fd is None:
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass  # a reader removes it once the lock is gone
        os.close(fd)


_REGISTERED: dict[Path, Registration] = {}


def register(aew_root: Path, entry_point: str | None) -> Registration | None:
    """This process's entry for ``aew_root``, made at its first use and shared by every ``ControlStore`` of the project
    in this process (:func:`release` when each is gone). None on Windows."""
    if sys.platform == "win32":  # pragma: windows-only
        return None
    key = aew_root.resolve()  # pragma: posix-only
    reg = _REGISTERED.get(key)
    if reg is None or reg.fd is None:
        reg = _REGISTERED[key] = Registration(key, entry_point)
    reg.users += 1
    return reg


def release(aew_root: Path) -> None:
    """One ``ControlStore`` of ``aew_root`` is gone; the entry goes with the last."""
    reg = _REGISTERED.get(aew_root.resolve())
    if reg is None:
        return
    reg.users -= 1
    if reg.users <= 0:
        reg.close()
        _REGISTERED.pop(aew_root.resolve(), None)


def running(aew_root: Path, *, exclude: Registration | None = None) -> tuple[list[Writer], list[str]]:
    """The running store writers of ``aew_root`` other than ``exclude``, and what could not be done (an entry this view
    may not remove). An entry whose lock is free belongs to an exited process and is removed; an entry that is locked
    but cannot be read counts as a writer holding no group, so it can only make the store owner-only."""
    if sys.platform == "win32":  # pragma: windows-only
        return [], []
    import fcntl  # pragma: posix-only

    directory = aew_root / WRITERS_REL
    try:
        names = sorted(os.listdir(directory))
    except FileNotFoundError:
        return [], []
    out: list[Writer] = []
    problems: list[str] = []
    for name in names:
        if exclude is not None and name in (exclude.name, f".{exclude.name}.tmp"):
            continue
        path = directory / name
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        except FileNotFoundError:
            continue
        except OSError as exc:
            out.append(Writer(-1, None, -1, frozenset(), note=f"{name}: {exc.strerror or exc}"))
            continue
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if not name.startswith("."):  # a live entry; a locked temporary one is being made, not yet a writer
                    out.append(_read(fd, name))
                continue
            try:  # its owner has exited
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                problems.append(f"{name} belongs to an exited process but could not be removed ({exc.strerror or exc})")
        finally:
            os.close(fd)
    return out, problems


def _read(fd: int, name: str) -> Writer:
    if sys.platform == "win32":  # pragma: windows-only
        raise NotImplementedError("no store-writer entries on Windows")
    try:  # pragma: posix-only
        data = json.loads(os.pread(fd, _MAX_ENTRY, 0))
        return Writer(int(data["pid"]), data.get("entry_point"), int(data["egid"]),
                      frozenset(int(g) for g in data["groups"]),
                      refused=None if data.get("refused") is None else int(data["refused"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return Writer(-1, None, -1, frozenset(), note=f"{name} could not be read ({exc})")
