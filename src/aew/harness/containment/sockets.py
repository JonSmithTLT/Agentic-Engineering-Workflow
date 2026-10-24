"""The socket inventory of a contained run (STG-05 CB-03; designer rulings D-CS2-2 and D-CS2-3): which socket a
contained process can reach, what it is, and whether that fails the launch.

A read-only mount refuses writes to files, directories and links, not a socket's ``connect``, so every filesystem
socket a contained process can reach by its path is a door out of the sandbox. Masks close the doors somebody listed
(``/run`` whole, the secret directories); the inventory finds the ones nobody did. It comes from the kernel's own table
of Unix sockets (``/proc/net/unix``), read by the launcher in its network namespace: every bound socket, by path or by
abstract name, in O(sockets), with no walk of the filesystem. Before reading it, the launcher binds a socket of its
own: a table that does not list it is not this namespace's, and the launch fails closed.

* **A path socket** is reachable when the same socket file (device and inode) is at a path inside the sandbox: its
  own, or any other the sandbox's mount table exposes it at (``probe._PAYLOAD``), at its listed path and at that path
  with its directory resolved on the host. A socket bound under a temporary name and then linked into place in the
  same directory is listed under the name it was bound at, which is gone (OpenSSH's ControlMaster does this, in mux.c's
  ``muxserver_listen``): then every socket file in that directory is checked, each taking the worse of its own class
  and the listed one's.
* **An abstract socket** has no file. It is listed with its class as a fact of the network, which is shared until CS-3
  gives runs their own namespace (D-CS2-5).
* **What it cannot see** is named on the label (:data:`NOT_COVERED`; D-CS2-3), with the instances the table shows: a
  path that does not resolve here (bound in another mount namespace), a relative bind (reported and counted), a path
  the launcher could not check, a socket no mount of whose filesystem is known (checked at its own paths only), and the
  launching user's processes that ``/proc`` does not let it read.
* **The kernel's tables** (``/proc/net/unix``, ``/proc/self/mountinfo``) are read as bytes and split where the kernel
  delimits a record; a record that does not parse fails the launch closed, never dropped.

This module is the one owner of the classes, by name and by the listening process's executable, a known list never
complete (D-CS2-6):

* a socket that reaches the display, G3, an AEW service other than the run's own, a credential, or an escape route
  (something that runs commands as the operator outside the sandbox) fails the launch. A listening socket the
  launching user owns, whose holder the launcher cannot identify, is a credential (:data:`UNIDENTIFIED`, D-CS2-6);
* the run's own bridge socket is listed as its own;
* any other socket (a site's ordinary services, such as SSSD's pipes under ``/var/lib/sss/pipes``) is reported, never
  refused.
"""

from __future__ import annotations

import contextlib
import os
import posixpath
import re
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

OWN, REPORTED = "own", "reported"
DISPLAY, APPROVAL, AEW_SERVICE, CREDENTIAL, ESCAPE = "display", "approval", "aew_service", "credential", "escape"
FAILING = frozenset({DISPLAY, APPROVAL, AEW_SERVICE, CREDENTIAL, ESCAPE})

TABLE = "/proc/net/unix"
MOUNTINFO = "/proc/self/mountinfo"
_ACCEPTCON = 0x10000  # __SO_ACCEPTCON in the table's Flags: a listening socket
# One record of the table as the kernel writes it (net/unix/af_unix.c, unix_seq_show): "%pK: %08X %08X %08X %04X %02X
# %5lu" (Num RefCount Protocol Flags Type St Inode), then " " and the name when the socket has one.
_RECORD = re.compile(rb"[0-9A-Fa-f]+: [0-9A-Fa-f]{8} [0-9A-Fa-f]{8} ([0-9A-Fa-f]{8}) [0-9A-Fa-f]{4} [0-9A-Fa-f]{2} +"
                     rb"([0-9]+)(?: (.+))?", re.DOTALL)
_MAJMIN = re.compile(rb"[0-9]+:[0-9]+")

# AEW's own runtime directories are named aew-<service>, directly in a runtime root (/run/aew-g3/, /run/aew-wis/,
# /tmp/aew-bridge-*/, or the launching environment's XDG_RUNTIME_DIR): a socket anywhere under one is that service's.
# A directory elsewhere that is named aew-* (a checkout, a reviewer's tree) is no service's: on the Rocky VM a
# reviewer's ~/aew-review held stale sockets of an old study, which refused every launch. The first match is the
# class; the run's own bridge is OWN before either.
RUNTIME_ROOTS = ("/run", "/var/run", "/tmp")  # noqa: S108 (paths it classifies, never a file it makes)
ANCESTORS: tuple[tuple[str, str], ...] = (
    (APPROVAL, "aew-g3*"),                                # G3, the approval service
    (AEW_SERVICE, "aew-*"),                               # any other AEW service
)
# (class, the socket's name, its parent directory, its grandparent), each a shell pattern ("*": anything). The first
# row that matches is the class; a socket nothing matches is reported. An abstract socket is matched by its name
# without the "@" (X11's is "/tmp/.X11-unix/X0"). The table is the CS-2 hand-off's list and the Lead's rulings on
# CS-2's plan (2026-10-23): the system bus, terminal multiplexers, editor servers, container engines and the user
# service manager, each an escape route, since each runs commands as the operator, outside the sandbox (or as root);
# the designer's D-CS2-2 for the abstract names, and D-CS2-6 for the agents' names. The names here and the
# executables below are a known list, never complete (D-CS2-6): what neither names is caught, if at all, by
# UNIDENTIFIED's rule.
CLASSES: tuple[tuple[str, str, str, str], ...] = (
    (DISPLAY, "X*", ".X11-unix", "*"),                    # X11
    (DISPLAY, "wayland-*", "*", "*"),                     # Wayland compositors
    (CREDENTIAL, "agent.*", "ssh-*", "*"),                # ssh-agent
    (CREDENTIAL, "S.gpg-agent*", "*", "*"),               # gpg-agent, its ssh and extra sockets
    (CREDENTIAL, "S.scdaemon", "*", "*"),
    (CREDENTIAL, "S.keyboxd", "*", "*"),
    (CREDENTIAL, "socket", "credential", "git"),          # git's credential-cache: $XDG_CACHE_HOME/git/credential
    (CREDENTIAL, "socket", ".git-credential-cache", "*"),
    (CREDENTIAL, "*", "keyring", "*"),                    # gnome-keyring
    (CREDENTIAL, "bus", "*", "user"),                     # the session bus, /run/user/<uid>/bus (the Secret Service)
    (CREDENTIAL, "dbus-*", "tmp", "*"),                   # a session bus at /tmp/dbus-* (abstract, or a file)
    (CREDENTIAL, "agent.sock", "*", "*"),                 # an agent by its common names (D-CS2-6): 1Password's
    (CREDENTIAL, "*-agent.sock", "*", "*"),               # ~/.1password/agent.sock, Bitwarden's
    (CREDENTIAL, "*-agent.socket", "*", "*"),             # ~/.bitwarden-ssh-agent.sock, and the like
    (CREDENTIAL, "ssh", "gcr", "*"),                      # gcr's ssh agent, $XDG_RUNTIME_DIR/gcr/ssh
    (ESCAPE, "system_bus_socket", "dbus", "*"),           # the system bus: polkit can prompt the operator
    (ESCAPE, "*", "tmux-*", "*"),                         # tmux
    (ESCAPE, "*", "S-*", "screen*"),                      # GNU screen
    (ESCAPE, "*", "emacs*", "*"),                         # an emacs server
    (ESCAPE, "vscode-*.sock", "*", "*"),                  # VS Code's IPC and git sockets
    (ESCAPE, "docker.sock", "*", "*"),                    # container engines: root-equivalent
    (ESCAPE, "podman.sock", "*", "*"),
    (ESCAPE, "containerd.sock", "*", "*"),
    (ESCAPE, "*", "containerd-shim", "*"),                # containerd's shims, abstract
    (ESCAPE, "private", "systemd", "*"),                  # a service manager: systemd --user runs any command
)
# (class, the listening process's executable name), for a listener that is the launching user's own process (the
# designer, D-CS2-2 and its addendum): it catches what a name cannot, such as a ControlMaster's hashed ControlPath.
# Another user's processes are not readable, and their sockets are classified by name only.
EXECUTABLES: tuple[tuple[str, str], ...] = (
    (DISPLAY, "Xorg"), (DISPLAY, "Xwayland"), (DISPLAY, "Xvfb"), (DISPLAY, "Xvnc"),
    (CREDENTIAL, "ssh"),                                  # a ControlMaster, or a forward to a remote socket
    (CREDENTIAL, "ssh-agent"), (CREDENTIAL, "gpg-agent"), (CREDENTIAL, "scdaemon"), (CREDENTIAL, "keyboxd"),
    (CREDENTIAL, "gnome-keyring-daemon"), (CREDENTIAL, "1password"), (CREDENTIAL, "bitwarden"),
    (CREDENTIAL, "keepassxc"),                            # password managers' agents (D-CS2-6)
    (CREDENTIAL, "dbus-daemon"), (CREDENTIAL, "dbus-broker*"),  # the launching user's own bus: the session bus
    (ESCAPE, "tmux*"), (ESCAPE, "screen*"), (ESCAPE, "emacs*"), (ESCAPE, "code"), (ESCAPE, "podman"),
    (ESCAPE, "systemd"),                                  # the user's service manager
)
# The designer's D-CS2-6: a listening socket the launching user owns, whose holder the launcher cannot identify (no
# process of the launching user's that it can read holds it), is a credential, and fails the launch where it is
# reachable. Its candidate says so, for row 2 and doctor to name the socket and the remedy.
UNIDENTIFIED = "unidentified"
# What the inventory cannot see, named on every label (D-CS2-3, and the review of #244); each is accepted there, with
# why. The lists the label carries (unresolved, relative, unchecked, untranslated) are the instances the table shows.
NOT_COVERED = (
    "a socket bound in another network namespace",
    "a socket moved or linked into another directory",
    "a socket bound in another mount namespace at a path that names a different socket here",
    "a socket bound after the launch's check: the inventory is as of the launch",
    "a socket bound through a file descriptor's path (/proc/self/fd/<n>/...): unresolved or unchecked here",
    "a socket whose path the launcher could not check: recorded under unchecked, not failed",
)

_X_DISPLAY = re.compile(r"^(?:unix)?:(\d+)(?:\.\d+)?$")


def classify(path: str, *, own: tuple[str, ...] = (), env: Mapping[str, str] | None = None) -> str:
    """The class of the socket at ``path`` (an abstract one as ``@<name>``): :data:`OWN` (under one of ``own``, the
    run's bridge directory), a failing class (:data:`FAILING`), or :data:`REPORTED`. Sockets the launching environment
    ``env`` names (its display, ssh agent and session bus) are failing wherever they live."""
    env = os.environ if env is None else env
    named = _named(env)
    if path.startswith("@"):
        return named.get(path) or _by_name(os.path.normpath(path[1:]) if path[1:2] == "/" else path[1:], env)
    path = os.path.normpath(path)
    if any(path == os.path.normpath(d) or path.startswith(os.path.normpath(d) + os.sep) for d in own):
        return OWN
    return named.get(path) or _by_name(path, env)


def _by_name(path: str, env: Mapping[str, str]) -> str:
    for root in (*RUNTIME_ROOTS, *([env["XDG_RUNTIME_DIR"]] if env.get("XDG_RUNTIME_DIR") else [])):
        root = os.path.normpath(root)
        below = path[len(root) + 1:].split(os.sep) if path.startswith(root + os.sep) else []
        for cls, pattern in ANCESTORS:
            if len(below) > 1 and fnmatchcase(below[0], pattern):
                return cls
    parts = path.split(os.sep)
    name, parent, grand = parts[-1], (parts[-2] if len(parts) > 1 else ""), (parts[-3] if len(parts) > 2 else "")
    for cls, n, p, g in CLASSES:
        if fnmatchcase(name, n) and fnmatchcase(parent, p) and fnmatchcase(grand, g):
            return cls
    return REPORTED


def by_executable(exe: str | None) -> str | None:
    """The class :data:`EXECUTABLES` gives a listener's executable name, or None."""
    return next((cls for cls, pattern in EXECUTABLES if exe and fnmatchcase(exe, pattern)), None)


def worse(cls: str, other: str | None) -> str:
    """The worse of two classes: a failing one over any other, ``cls`` first. The run's own stays its own."""
    if other is None or cls in FAILING or cls == OWN:
        return cls
    return other if other in FAILING else cls


def _named(env: Mapping[str, str]) -> dict[str, str]:
    """{socket path or @abstract name: class} for the sockets the launching environment names (CB-04's variables)."""
    out: dict[str, str] = {}
    x = _X_DISPLAY.match(env.get("DISPLAY") or "")
    if x:
        out["/tmp/.X11-unix/X" + x.group(1)] = DISPLAY  # noqa: S108 (X11's fixed socket directory)
        out["@/tmp/.X11-unix/X" + x.group(1)] = DISPLAY
    wayland = env.get("WAYLAND_DISPLAY") or ""
    if wayland:
        out[os.path.normpath(os.path.join(env.get("XDG_RUNTIME_DIR") or "", wayland))] = DISPLAY
    if env.get("SSH_AUTH_SOCK"):
        out[os.path.normpath(env["SSH_AUTH_SOCK"])] = CREDENTIAL
    for address in (env.get("DBUS_SESSION_BUS_ADDRESS") or "").split(";"):
        if address.startswith("unix:"):
            for key, _, value in (kv.partition("=") for kv in address[5:].split(",")):
                if key == "path" and value:
                    out[os.path.normpath(value)] = CREDENTIAL
                elif key == "abstract" and value:
                    out["@" + value] = CREDENTIAL
    return out


@dataclass(frozen=True)
class Entry:
    """One named socket in the kernel's table."""

    inode: int        # the socket's own inode (sockfs), as /proc/<pid>/fd shows it
    name: str         # an absolute path, "@" and an abstract name, or a relative path as it was bound
    listening: bool


def _lines(path: str) -> list[bytes]:
    """The records of a ``/proc`` table, read as bytes and split at the newline only, where the kernel ends each
    (review of #244)."""
    with open(path, "rb") as f:
        lines = f.read().split(b"\n")
    if lines[-1] != b"":
        raise ValueError(f"{path} does not end with a newline")
    return lines[:-1]


def table(path: str = TABLE) -> list[Entry]:
    """Every named socket in the kernel's table of Unix sockets (``/proc/net/unix``) of this network namespace:
    listening, bound or connected. Raises ``OSError`` when it cannot be read, and ``ValueError`` on a record that does
    not match the kernel's fixed format (:data:`_RECORD`), which the row then fails on: a record is never dropped."""
    lines = _lines(path)
    if not lines or not lines[0].startswith(b"Num "):
        raise ValueError(f"{path} has no header")
    out = []
    for n, line in enumerate(lines[1:], start=2):
        record = _RECORD.fullmatch(line)
        if record is None:
            raise ValueError(f"line {n} of {path} is not a socket's record: {line[:80]!r}")
        flags, inode, name = record.groups()
        if name is not None:
            out.append(Entry(int(inode), name.decode("utf-8", "surrogateescape"), bool(int(flags, 16) & _ACCEPTCON)))
    return out


def listeners(inodes: set[int]) -> tuple[dict[int, str], list[dict[str, Any]]]:
    """``({socket inode: its holder's executable name}, unreadable)`` for those of ``inodes`` that the launching
    user's own processes hold (``/proc/<pid>/fd``). Another user's processes are not readable here. A process of the
    launching user's whose ``/proc`` entries it cannot read (one ``/proc`` shows as root's while its real uid is the
    launching user's, among them) is ``unreadable``, by pid and name, for the label (review of #244)."""
    wanted = {f"socket:[{i}]": i for i in inodes}
    uid, out, unreadable = _uid(), {}, []
    for pid in _pids():
        try:
            owner = _owner(pid)
            if owner != uid and not (owner == 0 and uid != 0 and _real_uid(pid) == uid):
                continue
            exe = os.path.basename(_exe(pid)).removesuffix(" (deleted)")
            for target in _fds(pid):
                held = wanted.get(target)
                if held is not None:
                    out[held] = exe
        except PermissionError:
            unreadable.append({"pid": int(pid), "name": _comm(pid)})
        except OSError:  # gone
            continue
    return out, unreadable


def _uid() -> int:
    if sys.platform == "win32":
        return -1
    return os.getuid()


def _pids() -> list[str]:
    return [] if sys.platform == "win32" else [p for p in os.listdir("/proc") if p.isdigit()]


def _owner(pid: str) -> int:
    return os.stat(f"/proc/{pid}").st_uid


def _real_uid(pid: str) -> int | None:
    return _status_uid(f"/proc/{pid}/status")


def _status_uid(path: str) -> int | None:
    """The real uid in a ``/proc/<pid>/status``, read as bytes (its last ``Uid:`` line: the name comes first)."""
    uids = [line.split(b"\t")[1] for line in _lines(path) if line.startswith(b"Uid:\t")]
    return int(uids[-1]) if uids and uids[-1].isdigit() else None


def _exe(pid: str) -> str:
    return os.readlink(f"/proc/{pid}/exe")


def _fds(pid: str) -> list[str]:
    """What each of a process's descriptors is; one closed while they are read is skipped, not the process."""
    out = []
    for fd in os.listdir(f"/proc/{pid}/fd"):
        with contextlib.suppress(FileNotFoundError):
            out.append(os.readlink(f"/proc/{pid}/fd/{fd}"))
    return out


def _comm(pid: str) -> str | None:
    try:
        with open(f"/proc/{pid}/comm", "rb") as f:
            return f.read().removesuffix(b"\n").decode("utf-8", "surrogateescape")
    except OSError:
        return None


def mounts(path: str = MOUNTINFO) -> list[tuple[str, str, str]]:
    """(major:minor, root within its filesystem, mount point) of every mount in ``path``'s table, in mount order. Its
    fields are split at single spaces, as the kernel writes them: a path escapes a space, a tab, a newline and a
    backslash in octal, and holds any other byte raw. Raises ``ValueError`` on a line that does not parse."""
    out = []
    for line in _lines(path):
        left, sep, right = line.partition(b" - ")
        fields = left.split(b" ")
        if not sep or len(fields) < 6 or not _MAJMIN.fullmatch(fields[2]) or not right.split(b" ")[0]:
            raise ValueError(f"a line of {path} is not a mount's: {line[:80]!r}")
        out.append((fields[2].decode(), _unescape(fields[3]), _unescape(fields[4])))
    return out


def _unescape(raw: bytes) -> str:
    return os.fsdecode(re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m.group(1), 8)]), raw))


def inventory(*, control: str, own: tuple[str, ...] = (), env: Mapping[str, str] | None = None,
              path: str = TABLE) -> dict[str, Any]:
    """What the launcher's network namespace holds, for the launch self-test: every path socket to check inside the
    sandbox (``candidates``, with the class each takes), the abstract sockets and the relative binds with theirs, the
    paths that do not resolve here, and whether ``control`` (the probe's own listener) is in the table. Raises
    ``OSError`` when the table cannot be read."""
    entries = table(path)
    held, unreadable = listeners({e.inode for e in entries})
    classes: dict[str, str] = {}
    unheld: set[str] = set()  # names with a listening socket whose own inode no readable process holds (D-CS2-6)
    for e in entries:  # an accepted connection is listed under its listener's name: one class per name
        named = classes.get(e.name) or classify(e.name, own=own, env=env)
        classes[e.name] = worse(named, by_executable(held.get(e.inode)))
        if e.listening and e.inode not in held:
            unheld.add(e.name)
    uid = _uid()
    host = mounts()
    candidates: dict[str, dict[str, Any]] = {}
    abstract, relative, unresolved, unchecked = [], [], [], []
    for name, cls in classes.items():
        if name.startswith("@"):
            abstract.append({"name": name, "class": cls})
            continue
        if not name.startswith("/"):
            relative.append({"name": name, "class": cls})
            continue
        try:
            st = _stat(name)
        except (FileNotFoundError, NotADirectoryError):
            st = None
        except OSError as exc:
            unchecked.append({"path": name, "class": cls, "error": exc.strerror})
            continue
        if st is not None and stat.S_ISSOCK(st.st_mode):
            found = [(name, st)]
        else:  # bound under another name and moved or linked in its directory (D-CS2-3): every socket file there
            try:
                found = _socket_files(os.path.dirname(name))
            except FileNotFoundError:  # bound in another mount namespace: its path does not resolve here
                unresolved.append({"path": name, "class": cls})
                continue
            except OSError as exc:
                unchecked.append({"path": name, "class": cls, "error": exc.strerror})
                continue
        for p, fst in found:
            mine = worse(classify(p, own=own, env=env), cls) if p != name else cls
            real = posixpath.join(_realdir(posixpath.dirname(p)), posixpath.basename(p))  # a sandbox's paths: POSIX
            if real != p:  # each spelling is checked inside, and takes its class (review of #244)
                mine = worse(mine, classify(real, own=own, env=env))
            unknown = name in unheld and fst.st_uid == uid
            if unknown:
                mine = worse(mine, CREDENTIAL)
            prior = candidates.get(p)
            candidates[p] = {"path": p, "listed": name, "class": worse(prior["class"], mine) if prior else mine,
                             **({"holder": UNIDENTIFIED} if unknown or (prior or {}).get("holder") else {}),
                             "dev": fst.st_dev, "ino": fst.st_ino, **_on_filesystem(p, fst.st_dev, host),
                             "real": None if real == p else
                             {"path": real, "fspath": _on_filesystem(real, fst.st_dev, host)["fspath"]}}
    return {"control": control in classes, "table": len(entries), "candidates": list(candidates.values()),
            "abstract": abstract, "relative": relative, "unresolved": unresolved, "unchecked": unchecked,
            "unreadable": unreadable}


def _stat(path: str) -> os.stat_result:
    return os.lstat(path)


def _realdir(directory: str) -> str:
    """``directory`` with every link on it resolved, as the host sees it: each socket is checked inside at its listed
    path and at this one."""
    return os.path.realpath(directory)


def _socket_files(directory: str) -> list[tuple[str, os.stat_result]]:
    """(path, stat) of every socket file directly in ``directory``."""
    with os.scandir(directory) as it:
        return [(f.path, st) for f in it if stat.S_ISSOCK((st := f.stat(follow_symlinks=False)).st_mode)]


def _majmin(dev: int) -> str | None:
    """``major:minor`` of a device number, as the mount table writes it (None where there is no mount table)."""
    if sys.platform == "win32":
        return None
    return f"{os.major(dev)}:{os.minor(dev)}"


def _on_filesystem(path: str, dev: int, host: list[tuple[str, str, str]]) -> dict[str, str | None]:
    """``majmin`` and ``fspath``: the socket's filesystem and its path within it, from the deepest of the host's mounts
    of that filesystem above it, so the sandbox can find it at any mount of the same filesystem. ``fspath`` is None
    when no mount of its device is above it (the sandbox then checks its own path only)."""
    majmin = _majmin(dev)
    best: tuple[str, str] | None = None
    for mm, root, point in host:
        if mm == majmin and (path == point or path.startswith(point.rstrip("/") + "/")):
            if best is None or len(point) >= len(best[1]):
                best = (root, point)
    if best is None:
        return {"majmin": majmin, "fspath": None}
    root, point = best
    return {"majmin": majmin, "fspath": root.rstrip("/") + path[len(point.rstrip("/")):] or "/"}
