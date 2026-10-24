"""The socket inventory of a contained run (STG-05 CB-03; designer rulings D-CS2-2 and D-CS2-3): which socket a
contained process can reach, what it is, and whether that fails the launch.

A read-only mount refuses writes to files, directories and links, not a socket's ``connect``, so every filesystem
socket a contained process can reach by its path is a door out of the sandbox. Masks close the doors somebody listed
(``/run`` whole, the secret directories); the inventory finds the ones nobody did. It comes from the kernel's own table
of Unix sockets (``/proc/net/unix``), read by the launcher in its network namespace: every bound socket, by path or by
abstract name, in O(sockets), with no walk of the filesystem. Before reading it, the launcher binds a socket of its
own: a table that does not list it is not this namespace's, and the launch fails closed.

* **A path socket** is reachable when the same socket file (device and inode) is at a path inside the sandbox: its
  own, or any other the sandbox's mount table exposes it at (``probe._PAYLOAD``). A socket bound under a temporary name
  and then linked into place in the same directory is listed under the name it was bound at, which is gone (OpenSSH's
  ControlMaster does this, in mux.c's ``muxserver_listen``): then every socket file in that directory is checked, each
  taking the worse of its own class and the listed one's.
* **An abstract socket** has no file. It is listed with its class as a fact of the network, which is shared until CS-3
  gives runs their own namespace (D-CS2-5).
* **What it cannot see** is named on the label (D-CS2-3): a socket bound in another network namespace, one bound in
  another mount namespace (its path does not resolve here), one bound by a relative path (reported and counted), and
  one moved or linked into another directory.

This module is the one owner of the classes, by name and by the listening process's executable:

* a socket that reaches the display, G3, an AEW service other than the run's own, a credential, or an escape route
  (something that runs commands as the operator outside the sandbox) fails the launch;
* the run's own bridge socket is listed as its own;
* any other socket (a site's ordinary services, such as SSSD's pipes under ``/var/lib/sss/pipes``) is reported, never
  refused.
"""

from __future__ import annotations

import os
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
# and the designer's D-CS2-2 for the abstract names.
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
    (CREDENTIAL, "gnome-keyring-daemon"),
    (CREDENTIAL, "dbus-daemon"), (CREDENTIAL, "dbus-broker*"),  # the launching user's own bus: the session bus
    (ESCAPE, "tmux*"), (ESCAPE, "screen*"), (ESCAPE, "emacs*"), (ESCAPE, "code"), (ESCAPE, "podman"),
    (ESCAPE, "systemd"),                                  # the user's service manager
)
# What the inventory cannot see, named on every label (D-CS2-3); each is accepted there, with why.
NOT_COVERED = ("a socket bound in another network namespace", "a socket moved or linked into another directory")

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


def table(path: str = TABLE) -> list[Entry]:
    """Every named socket in the kernel's table of Unix sockets (``/proc/net/unix``) of this network namespace:
    listening, bound or connected. Raises ``OSError`` when it cannot be read."""
    out = []
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        next(f, None)  # the header
        for line in f:
            fields = line.rstrip("\n").split(None, 7)  # Num RefCount Protocol Flags Type St Inode Path
            if len(fields) == 8:
                out.append(Entry(int(fields[6]), fields[7], bool(int(fields[3], 16) & _ACCEPTCON)))
    return out


def listeners(inodes: set[int]) -> dict[int, str]:
    """{socket inode: its holder's executable name} for those of ``inodes`` that the launching user's own processes
    hold (``/proc/<pid>/fd``). Another user's processes are not readable here."""
    if sys.platform == "win32":
        return {}
    wanted = {f"socket:[{i}]": i for i in inodes}
    uid, out = os.getuid(), {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            exe = os.path.basename(os.readlink(f"/proc/{pid}/exe")).removesuffix(" (deleted)")
            for fd in os.listdir(f"/proc/{pid}/fd"):
                held = wanted.get(os.readlink(f"/proc/{pid}/fd/{fd}"))
                if held is not None:
                    out[held] = exe
        except OSError:  # gone, or not ours to read
            continue
    return out


def mounts(path: str = MOUNTINFO) -> list[tuple[str, str, str]]:
    """(major:minor, root within its filesystem, mount point) of every mount in ``path``'s table, in mount order."""
    out = []
    with open(path, "rb") as f:
        for line in f:
            fields = line.partition(b" - ")[0].split()
            if len(fields) >= 5:
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
    held = listeners({e.inode for e in entries})
    classes: dict[str, str] = {}
    for e in entries:  # an accepted connection is listed under its listener's name: one class per name
        named = classes.get(e.name) or classify(e.name, own=own, env=env)
        classes[e.name] = worse(named, by_executable(held.get(e.inode)))
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
            prior = candidates.get(p)
            candidates[p] = {"path": p, "listed": name, "class": worse(prior["class"], mine) if prior else mine,
                             "dev": fst.st_dev, "ino": fst.st_ino, **_on_filesystem(p, fst.st_dev, host)}
    return {"control": control in classes, "table": len(entries), "candidates": list(candidates.values()),
            "abstract": abstract, "relative": relative, "unresolved": unresolved, "unchecked": unchecked}


def _stat(path: str) -> os.stat_result:
    return os.lstat(path)


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
