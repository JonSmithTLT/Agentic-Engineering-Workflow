"""The socket inventory of a contained run (STG-05 CB-03): what a filesystem socket it can reach is, and whether that
fails the launch.

A read-only mount refuses writes to files, directories and links, not a socket's ``connect``, so every filesystem
socket a contained process can reach by its path is a door out of the sandbox. Masks close the doors somebody listed
(``/run`` whole, the secret directories); the inventory finds the ones nobody did. The launch self-test walks every
mount the sandbox sees, the read-only root included (``probe._PAYLOAD``), and this module, the one owner of the
classes, judges what it found:

* a socket that reaches the display, G3, an AEW service other than the run's own, a credential, or an escape route
  (something that runs commands as the operator outside the sandbox) fails the launch;
* the run's own bridge socket is listed as its own;
* any other socket (a site's ordinary services, such as SSSD's pipes under ``/var/lib/sss/pipes``) is reported, never
  refused.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from fnmatch import fnmatchcase

OWN, REPORTED = "own", "reported"
DISPLAY, APPROVAL, AEW_SERVICE, CREDENTIAL, ESCAPE = "display", "approval", "aew_service", "credential", "escape"
FAILING = frozenset({DISPLAY, APPROVAL, AEW_SERVICE, CREDENTIAL, ESCAPE})

# AEW's own runtime directories are named aew-<service> (/run/aew-g3/, /run/aew-wis/, /tmp/aew-bridge-*/): a socket
# anywhere under one is that service's. The first match is the class; the run's own bridge is OWN before either.
ANCESTORS: tuple[tuple[str, str], ...] = (
    (APPROVAL, "aew-g3*"),                                # G3, the approval service
    (AEW_SERVICE, "aew-*"),                               # any other AEW service
)
# (class, the socket's name, its parent directory, its grandparent), each a shell pattern ("*": anything). The first
# row that matches is the class; a socket nothing matches is reported. The table is the CS-2 hand-off's list and the
# Lead's rulings on CS-2's plan (2026-10-23): the system bus, terminal multiplexers, editor servers, container
# engines and the user service manager, each an escape route, since each runs commands as the operator, outside the
# sandbox (or as root).
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
    (ESCAPE, "system_bus_socket", "dbus", "*"),           # the system bus: polkit can prompt the operator
    (ESCAPE, "*", "tmux-*", "*"),                         # tmux
    (ESCAPE, "*", "S-*", "screen*"),                      # GNU screen
    (ESCAPE, "*", "emacs*", "*"),                         # an emacs server
    (ESCAPE, "vscode-*.sock", "*", "*"),                  # VS Code's IPC and git sockets
    (ESCAPE, "docker.sock", "*", "*"),                    # container engines: root-equivalent
    (ESCAPE, "podman.sock", "*", "*"),
    (ESCAPE, "containerd.sock", "*", "*"),
    (ESCAPE, "private", "systemd", "*"),                  # a service manager: systemd --user runs any command
)

_X_DISPLAY = re.compile(r"^(?:unix)?:(\d+)(?:\.\d+)?$")


def classify(path: str, *, own: tuple[str, ...] = (), env: Mapping[str, str] | None = None) -> str:
    """The class of the filesystem socket at ``path``: :data:`OWN` (under one of ``own``, the run's bridge
    directory), a failing class (:data:`FAILING`), or :data:`REPORTED`. Sockets the launching environment ``env``
    names (its display, ssh agent and session bus) are failing wherever they live."""
    path = os.path.normpath(path)
    if any(path == os.path.normpath(d) or path.startswith(os.path.normpath(d) + os.sep) for d in own):
        return OWN
    named = _named(os.environ if env is None else env)
    if path in named:
        return named[path]
    parts = path.split(os.sep)
    for cls, pattern in ANCESTORS:
        if any(fnmatchcase(d, pattern) for d in parts[:-1]):
            return cls
    name, parent, grand = parts[-1], (parts[-2] if len(parts) > 1 else ""), (parts[-3] if len(parts) > 2 else "")
    for cls, n, p, g in CLASSES:
        if fnmatchcase(name, n) and fnmatchcase(parent, p) and fnmatchcase(grand, g):
            return cls
    return REPORTED


def _named(env: Mapping[str, str]) -> dict[str, str]:
    """{socket path: class} for the sockets the launching environment names (CB-04's variables)."""
    out: dict[str, str] = {}
    x = _X_DISPLAY.match(env.get("DISPLAY") or "")
    if x:
        out["/tmp/.X11-unix/X" + x.group(1)] = DISPLAY  # noqa: S108 (X11's fixed socket directory)
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
    return out


# Filesystem types the walk does not enter (by their type in /proc/self/mountinfo). Kernel interfaces hold no socket
# file a process could bind; an autofs mount point mounts what it serves when it is walked, so only the mounts it has
# already made (listed in mountinfo of their own) are walked; read-only image filesystems (snaps, discs, images) are
# made before they are mounted, with no socket in them (the Lead, 2026-10-23, on CS-2's plan, Q3). Every mount not
# walked is listed on the label.
UNWALKED_FS = frozenset({
    "proc", "sysfs", "devpts", "cgroup", "cgroup2", "mqueue", "debugfs", "tracefs", "securityfs", "pstore", "bpf",
    "configfs", "fusectl", "hugetlbfs", "binfmt_misc", "efivarfs", "selinuxfs", "nsfs", "rpc_pipefs", "autofs",
    "squashfs", "iso9660", "erofs",
})
