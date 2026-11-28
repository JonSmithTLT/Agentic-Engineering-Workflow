"""One run's sandbox, described as data (F2; ADR-0009 amendment, M4-B).

A :class:`Layout` says what a contained process may write. Everything else is the host as read-only:

* the host root is bound read-only; ``/dev``, ``/proc`` and ``/tmp`` are private to the sandbox; the project is bound
  read-only too, at its depth in the one bind order, so it stays visible wherever it lives (even under ``/tmp``);
* ``/run`` is masked whole (STG-05 CB-03, ruling R-1): an empty tmpfs at its depth, remounted read-only once what
  the layout binds back into it is there. ``/var/run`` is the usual link to it (or masked too, where it is a
  directory of its own). Every service socket there (G3's, the work-item fact issuer's, the session and system buses,
  the operator's runtime directory) is gone; the one host-derived exception is :func:`run_exceptions`, and a project
  on removable media under ``/run`` is bound back with its workspace, on the conditions the operator's ruling sets
  (:data:`RUN_BIND_BACK`, :func:`_refuse_run_bind_backs`). The GSS-API proxy's directory is masked the same way, where
  there is one (:data:`GSSPROXY`, D-CS2-6);
* every contained process starts in a new session, so it has no controlling terminal (CB-05, ruling R-7), and
  without the display's and the operator's session variables (:data:`DISPLAY_ENV`, CB-04);
* the project's ``.aew/local`` (and the runs directory, wherever it lives) is hidden behind an empty tmpfs, and only
  this run's own directories are bound back: one run never reads another's harness state (its bridge key, its
  transcript), and the engine's control lock is not in the sandbox at all, so no contained process can hold it
  (STG-05 CBF-1). The mask takes its place in the one bind order (no bind above it can bring the lock back), and is
  remounted read-only once the run's own directories are bound back into it, so nothing makes a lock of its own
  there. The store itself (``.aew/state``) stays visible, read-only, for lock-free reads;
* PID, IPC and UTS namespaces are private, and so is the network namespace unless the layout's ``network`` is
  :data:`SHARED` (F28, STG-05 CS-3b): a private one has only its own loopback, so the host's loopback ports and abstract
  sockets are not there. The run's network sockets (the shim's, the provider relay's and the egress proxy's) are files
  in a private directory of the host's ``/tmp``, bound in at their depth: read-only, with the shim's own subdirectory
  writable (:data:`NET_SHIM`). A check runs with no network at all unless its definition and the policy allow the host's
  (:func:`for_check`);
* the writable roots come from the role (:data:`WORKSPACE_ACCESS`, exhaustive: a role without an entry has no
  layout and its launch is refused), plus the run's own scratch, harness state and private git state, plus any
  path the operator's execution policy adds (recorded on the run's label);
* writable binds and read-only re-binds are applied ancestors first (:func:`bind_order`): a later bind wins its
  subtree, so a read-only re-bind under a broad writable root closes what it protects (the repository's git metadata,
  the workspace's ``.git`` pointer, the bridge directory), and a writable bind under a read-only re-bind stays
  writable. A reader's workspace stays read-only whole: an operator root inside it is not bound;
* no writable bind may change the store's path (STG-05 CB-07, ruling R-3; :func:`_refuse_store_binds`);
* secret masks, the display's credentials among them, depend on the path's type (:func:`_mask_plan`): a directory is
  replaced by an empty tmpfs after every bind; anything else is left out of its directory, whether or not it exists
  yet, which is an empty tmpfs at its depth in the one bind order with every other entry it holds put back, then
  read-only, so a replacement or a creation on the host is not seen inside. In a tree the run writes, where that
  would make a level read-only, a file is replaced by an empty read-only file instead (``/dev/null`` would do, but
  SELinux refuses a device node bound over a home file), and the launch names it. One in a tree that is masked whole
  (``/tmp``, ``/run``, a runs mask) is hidden with its tree and not emitted, unless it lies in one of the layout's
  binds into that tree, such as a project under ``/run`` or ``/tmp`` (:func:`_hidden_with_its_tree`);
* the capability register is bound read-only, and the context's own directory of entries is read-only and first on
  every process's ``PATH`` (:meth:`Layout.contained_path`, ``aew.capability.bind``), so OpenCode's ripgrep lookup never
  misses and its download is never reached (CAPR-04; the designer's CAP-1 ruling 1);
* the project's `.env` files present at the launch, at any depth, are masked in place by the empty read-only file in
  every layout, since every layout shows the project (:func:`project_env_masks`), so containment hides them from every
  tool; `.env.example` stays.

The claim is filesystem integrity, not confidentiality: apart from the masks, a contained process can read what
the operator's account can read.
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, NamedTuple

from aew import hoststate
from aew.errors import AEWError, ContainmentUnavailable
from aew.harness.containment import client_cert

# What each archetype may do to the workspace (or observation) it was dispatched for. Exhaustive by design: an
# archetype without an entry (a new archetype nobody classified) cannot be contained, so it is refused. The Lead's
# workspace is its project's working tree (STG-05 CS-4, CB-01).
WORKSPACE_ACCESS: dict[str, str] = {
    "implementer": "write", "lead": "write",
    "reviewer": "read", "verifier": "read",
    "investigator": "read", "researcher": "read", "planner": "read",
    "frontier_advisor": "read",
}
# The scopes in which each writing archetype may hold write access (A-33 §3.1: per role): an implementer writes only
# its Ticket's workspace, and the Lead only its project. Anything else fails closed.
WRITE_SCOPES: dict[str, frozenset[str]] = {"implementer": frozenset({"ticket"}), "lead": frozenset({"project"})}

# Credentials commonly kept in a home directory. Masked when present; a policy may add more.
SECRET_DIRS = (".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store", ".config/gh",
               ".config/gcloud",
               # agent tools' own sign-ins and session stores (AEW gives a run's harness private XDG directories)
               ".local/share/opencode", ".config/opencode", ".codex", ".claude",
               ".config/anthropic",  # provider credential/config location
               # git's credential-cache daemon and its socket (STG-05 CB-03; the Lead, 2026-10-23): masked, so a host
               # that uses the cache still launches, where the socket inventory would refuse a visible one
               ".cache/git/credential", ".git-credential-cache")
SECRET_FILES = (".netrc", ".git-credentials", ".pgpass", ".pypirc", ".npmrc",
                ".claude.json",  # provider credential/config location
                ".config/git/credentials")  # git's store helper reads it too (the Lead, 2026-10-23)
# The display's credential files (STG-05 CB-04): masked like the secret files, plus the file the launching XAUTHORITY
# names (:func:`_env_masks`). The launch self-test's row 3 finds each unreadable from inside.
DISPLAY_FILES = (".Xauthority", ".ICEauthority")
# Shell and REPL history files (CS-4 addendum 12, ruling 1): a credential once typed on a command line stays there, so
# each is masked like the secret files, plus the file the launching HISTFILE names (:func:`_env_masks`). The host's own
# shell writes its history outside the sandbox. Windows masks nothing yet: PSReadLine's history under %APPDATA% is a
# known gap there, under the workdir_separation_only label, until a Windows backend masks home secrets.
HISTORY_FILES = (".bash_history", ".zsh_history", ".zhistory", ".sh_history", ".local/share/fish/fish_history",
                 ".python_history", ".node_repl_history", ".psql_history", ".mysql_history", ".sqlite_history",
                 ".rediscli_history", ".lesshst", ".local/share/powershell/PSReadLine/ConsoleHost_history.txt")
# What each of them is, for a refusal that names one (CS-4 addendum 8, ruling 1): exhaustive, a test holds it so.
SECRET_WHAT = {
    ".ssh": "ssh's keys", ".gnupg": "GnuPG's keys", ".aws": "the AWS CLI's credentials",
    ".azure": "the Azure CLI's credentials", ".kube": "kubectl's credentials", ".docker": "Docker's registry logins",
    ".password-store": "pass's password store", ".config/gh": "the GitHub CLI's login",
    ".config/gcloud": "the Google Cloud CLI's credentials", ".local/share/opencode": "OpenCode's logins and data",
    ".config/opencode": "OpenCode's configuration", ".codex": "Codex's login", ".claude": "Claude Code's sessions",
    ".config/anthropic": "an Anthropic credential", ".cache/git/credential": "git's credential cache",
    ".git-credential-cache": "git's credential cache", ".netrc": "netrc's logins",
    ".git-credentials": "git's stored credentials", ".pgpass": "PostgreSQL's passwords",
    ".pypirc": "PyPI's upload credentials", ".npmrc": "npm's tokens", ".claude.json": "Claude Code's configuration",
    ".config/git/credentials": "git's stored credentials", ".Xauthority": "the X display's cookie",
    ".ICEauthority": "the ICE session's cookie",
    ".bash_history": "bash's history", ".zsh_history": "zsh's history", ".zhistory": "zsh's history",
    ".sh_history": "the shell's history", ".local/share/fish/fish_history": "fish's history",
    ".python_history": "Python's REPL history", ".node_repl_history": "Node's REPL history",
    ".psql_history": "psql's history", ".mysql_history": "the MySQL client's history",
    ".sqlite_history": "the SQLite shell's history", ".rediscli_history": "redis-cli's history",
    ".lesshst": "less's search history",
    ".local/share/powershell/PSReadLine/ConsoleHost_history.txt": "PowerShell's history",
}
# What no contained process gets (CB-04): the display, and the operator's session bus and ssh agent. bubblewrap unsets
# them on every sandbox's argv, whichever allow-list built its environment; agentenv.POSIX_KEEP keeps none of them.
DISPLAY_ENV = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "SSH_AUTH_SOCK")

RUN = "/run"
VAR_RUN = "/var/run"
# Exceptions to the /run mask a harness needs (CB-03, ruling R-1: measured, never guessed; each a path bound back
# read-only by name, with why). None is measured: the host-derived one is :func:`_resolv_exception`'s.
RUN_EXCEPTIONS: tuple[tuple[str, str], ...] = ()
# A project under /run (removable media) is bound back into the mask, its workspace with it, on the designer's five
# conditions (:func:`_refuse_run_bind_backs`); the label records each bind-back with this reason.
RUN_BIND_BACK = "operator ruling 2026-10-23: a project under /run is bound back, on five conditions (R-1)"
# What under a host mask nothing is bound back into, whatever the ruling above lets in (condition 2): shell patterns
# for the first name below the mask. A bind-back that is the mask itself, or lies under one of these, is refused.
# Adding a pattern only tightens. aew-*: G3's aew-g3, the fact issuer's aew-wis, and any later AEW service.
RUN_PROTECTED = ("aew-*", "user", "dbus", "systemd")
# The GSS-API credential proxy's socket directory (gssproxy; the designer's D-CS2-6): masked whole where it exists, as
# /run is. A site configuration that serves users makes its socket a Kerberos credential route, and nothing inside
# needs it (GSS_USE_PROXY is off by default; the kernel's NFS client does not use the sandbox's view).
GSSPROXY = "/var/lib/gssproxy"
# WSLg's directory on a WSL host: its display and audio sockets, whose servers run in WSL's system distro. Masked whole
# where it exists, as /run is: nothing inside needs them, and the launching user owns them while /proc shows no holder,
# so row 2 refuses every launch where they are reachable (a default WSL install with bubblewrap). It holds more than
# those sockets, which is why it stays masked whole: nothing in it is to be bound back.
WSLG = "/mnt/wslg"
RESOLV_CONF = "/etc/resolv.conf"
RESOLV_WHY = "name resolution on the shared network (the operator, 2026-10-24); a private one resolves none"
MAXSYMLINKS = 40  # the links the kernel follows in one lookup before ELOOP (Linux include/linux/namei.h)
# Copies kept beside a secret file under a suffixed name (backups and the like): every regular file directly in the
# home directory whose name starts with one of these is masked too. Only the home directory itself is listed.
SECRET_FILE_PREFIXES = (".claude.json.",)  # provider credential/config location

# The network a layout gives its processes (F28 §3.1, network containment design v0.2): a private namespace whose only
# routes out are the run's relay and egress proxy, a private one with none, or the host's own (topology, not a claim).
PROXY_ONLY, ISOLATED, SHARED = "proxy_only", "isolated", "shared"
NETWORK_MODES = (PROXY_ONLY, ISOLATED, SHARED)
NET_SHIM = "shim"  # <net dir>/shim: the one place in a run's network directory the sandbox may write (the shim binds)

PRIVATE_GIT = "git"  # <run dir>/git: the run's private index and object store
MASK_FILE = ".aew-mask"
# Inside the sandbox /tmp is a fresh, private tmpfs: nothing else shares it, so the usual shared-/tmp risks (S108)
# do not apply. The bridge socket lives under the host's /tmp for the same reason (bridge.private_address).
SANDBOX_TMP = "/tmp"  # noqa: S108  # <run dir>/.aew-mask: the empty file bound over file secrets
SANDBOX_OWN = ("/dev", "/proc")  # the sandbox's own (bubblewrap's --dev and --proc): nothing of the host's is there


def host_masks() -> tuple[str, ...]:
    """The host's trees masked whole (CB-03): ``/run``; ``/var/run`` where it is a directory of its own rather than
    the usual link to ``/run``; and, where there is one, the GSS-API proxy's directory (:data:`GSSPROXY`) and WSLg's
    (:data:`WSLG`). Host facts, read when the layout is made."""
    out = [RUN]
    for tree in (VAR_RUN, GSSPROXY, WSLG):
        if os.path.isdir(tree) and not os.path.islink(tree):
            out.append(tree)
    return tuple(out)


def run_exceptions(network: str = SHARED) -> tuple[tuple[str, str], ...]:
    """What is bound back into the ``/run`` mask, read-only, each with why: :data:`RUN_EXCEPTIONS`, and on the host's
    network the host's name-resolution file (:func:`_resolv_exception`). A network of the run's own resolves no names
    inside, its routes out being the relay and the egress proxy, which resolve on the host; so it binds none back
    (STG-05 CS-4, ST-27 fact 3: CS-2's bind-back was "until CS-3")."""
    return RUN_EXCEPTIONS + (_resolv_exception() if network == SHARED else ())


def _resolv_exception(resolv: str = RESOLV_CONF, run: str = RUN) -> tuple[tuple[str, str], ...]:
    """The operator's ruling (2026-10-24, on CS-2's plan): on a systemd-resolved host ``/etc/resolv.conf`` links into
    ``/run`` (``/run/systemd/resolve/stub-resolv.conf``), and with ``/run`` masked a contained harness could not
    resolve its provider's name on the host's network. So the first path on the link chain that lies under ``/run`` is
    bound back read-only, by that name, when the chain ends at a regular file; otherwise there is no exception (a
    missing source would fail the launch). Followed as the kernel follows it, at most :data:`MAXSYMLINKS` links. Only
    the host's network needs it (:func:`run_exceptions`)."""
    path = resolv
    for _ in range(MAXSYMLINKS + 1):
        if _within(path, run):
            break
        if not os.path.islink(path):
            return ()
        path = os.path.normpath(os.path.join(os.path.realpath(os.path.dirname(path)), os.readlink(path)))
    else:
        return ()
    return ((path, RESOLV_WHY),) if os.path.isfile(path) else ()


@dataclass(frozen=True)
class Layout:
    """The sandbox of one run (and of the checks it runs). Pure data: :func:`bwrap_argv` turns it into argv."""

    role: str
    access: str                              # "write" or "read": the role's access to its workspace
    bwrap: str                               # absolute path of the bubblewrap binary
    writable: tuple[str, ...]                # read-write binds, applied by depth with `readonly` (bind_order)
    readonly: tuple[str, ...]                # read-only re-binds; a writable bind under one comes after it
    visible: tuple[str, ...] = ()            # read-only binds at their depth, first there: the project, anywhere
    hide_runs: tuple[str, ...] = ()          # empty tmpfs at its depth, then read-only: .aew/local, the runs dir
    hide_dirs: tuple[str, ...] = ()          # replaced by an empty tmpfs
    hide_files: tuple[str, ...] = ()         # replaced by ``mask_file``: a secret file in a tree the run writes
    env_masks: tuple[str, ...] = ()          # the project's `.env` files among them, in every layout
    env_dirs: tuple[str, ...] = ()           # the project's directories its .env scan could not read, in hide_dirs
    env_bulk: tuple[str, ...] = ()           # those holding more .env files than can be masked one by one, in hide_dirs
    env_links: tuple[tuple[str, str], ...] = ()  # (link, why): `.env`-named links not followed, so masking nothing
    project: str | None = None               # the project whose .env scan each sandbox of this layout repeats
    env_keep: tuple[str, ...] = ()           # what a run needs: a `.env` link's target there is never masked
    env_home: str | None = None              # the operator's home: a link's target there may be masked (EnvRules)
    env_needs: tuple[str, ...] = ()          # the run's own directories and harness binary: a target there never is
    env_outside: tuple[tuple[str, str], ...] = ()  # (link, target): a target outside the project, masked, named
    env_read_through: tuple[str, ...] = ()   # directories this account cannot read, read through a user namespace
    env_fallback: str | None = None          # why the scan could not read ``env_dirs`` through one, where it could not
    left_out: tuple[str, ...] = ()           # absent inside: left out of their directories, ``left_out_of``
    left_out_of: tuple[str, ...] = ()        # empty tmpfs at its depth, its other entries put back, then read-only
    put_back: tuple[str, ...] = ()           # those other entries, bound back read-only at their depth
    put_back_links: tuple[tuple[str, str], ...] = ()  # (path, target): the links among them, made again as links
    # (path, what put it there): masks in the run's own tree, read-only (the launch line names each), and paths there
    # not masked as absent at the launch
    tree_masks: tuple[tuple[str, str], ...] = ()
    tree_absent: tuple[tuple[str, str], ...] = ()
    # (path, what put it there): the same where a secret's directory is / or cannot be listed, so the secret cannot be
    # left out of it (CS-4 addendum 8, ruling 2.1); the launch line names these as their own case
    fixed_masks: tuple[tuple[str, str], ...] = ()
    fixed_absent: tuple[tuple[str, str], ...] = ()
    mask_file: str = "/dev/null"             # an empty read-only file
    operator_writable: tuple[str, ...] = ()  # the policy's extra writable roots (also in ``writable``)
    protected: tuple[str, ...] = ()          # paths the launch self-test must find unwritable
    env: dict[str, str] = field(default_factory=dict)  # what contained processes need set (private git, caches)
    # empty tmpfs at its depth, then read-only, like ``hide_runs``: /run (CB-03), in every layout, eval's included
    hide_host: tuple[str, ...] = field(default_factory=host_masks)
    # (path, why): bound back read-only into ``hide_host`` after its mask
    run_exceptions: tuple[tuple[str, str], ...] = field(default_factory=run_exceptions)
    display_files: tuple[str, ...] = ()      # the display's credential files found (in ``hide_files``), for row 3
    network: str = SHARED                    # NETWORK_MODES: --unshare-net unless SHARED (F28 §3.2)
    net_dir: str | None = None               # the run's network sockets, bound in read-only (its NET_SHIM writable)
    # The register's providers in this context (CAPR-04; aew.capability.bind): the tools' plan, the context's directory
    # of entries first on PATH, the one last on it (None: no record is there), and what they lead to, bound read-only
    # (the register): each with --ro-bind-try, as a payload may go during a run, which only fails a tool's use.
    tools: tuple[Any, ...] = ()
    tools_first: str | None = None
    tools_last: str | None = None
    tool_binds: tuple[str, ...] = ()
    # The run's copy of its skills (aew.skills.deliver), bound read-only, and protected so the self-test covers it: a
    # copy the run could edit would make its record state a false hash (the designer's ruling of 2026-11-03, §3)
    skills_binds: tuple[str, ...] = ()

    def contained_path(self, path: str | None = None) -> str | None:
        """The ``PATH`` every process of this context gets: its entries first, ``path`` (default: this process's), and
        its own-name entries last. None for a layout with no entries, which leaves ``PATH`` as its caller set it."""
        if self.tools_first is None:
            return None
        base = os.environ.get("PATH", "") if path is None else path
        ours = {self.tools_first, self.tools_last}
        rest = [p for p in base.split(os.pathsep) if p and p not in ours]
        return os.pathsep.join([self.tools_first, *rest, *([self.tools_last] if self.tools_last else [])])

    def describe(self) -> dict[str, Any]:
        return {"role": self.role, "workspace_access": self.access, "writable": list(self.writable),
                "readonly": list(self.readonly), "tool_binds": list(self.tool_binds),
                "skills_binds": list(self.skills_binds),
                "tools_first": self.tools_first, "tools_last": self.tools_last,
                "hidden": [*self.hide_host, *self.hide_runs, *self.hide_dirs, *self.hide_files, *self.left_out],
                "left_out_of": list(self.left_out_of), "env_masks": list(self.env_masks),
                "env_dirs": list(self.env_dirs), "env_bulk": list(self.env_bulk),
                "env_links": [{"path": p, "why": why} for p, why in self.env_links],
                "env_outside": [{"path": p, "target": t} for p, t in self.env_outside],
                "env_read_through": list(self.env_read_through), "env_fallback": self.env_fallback,
                "tree_masks": [{"path": p, "by": by} for p, by in self.tree_masks],
                "tree_absent": [{"path": p, "by": by} for p, by in self.tree_absent],
                "bound_back": [{"path": p, "why": why} for p, why in self.bind_backs()],
                "display_files": list(self.display_files), "unset_env": list(DISPLAY_ENV), "session": "new",
                "operator_writable": list(self.operator_writable), "network": self.network, "net_dir": self.net_dir}

    @property
    def private_network(self) -> bool:
        """Whether this layout's processes get a network namespace of their own (``--unshare-net``)."""
        return self.network != SHARED

    def net_binds(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """``(writable, read-only)`` binds of the run's network directory: none without one."""
        if not self.net_dir:
            return (), ()
        return (os.path.join(self.net_dir, NET_SHIM),), (self.net_dir,)

    def bind_backs(self) -> tuple[tuple[str, str], ...]:
        """(path, why) for every path this layout itself puts inside a ``hide_host`` mask: the exceptions, then any
        bind or runs mask under one, which is a project under ``/run`` (removable media) and its workspace, bound
        back by the operator's ruling (:data:`RUN_BIND_BACK`; :func:`_refuse_run_bind_backs` holds its conditions for
        a layout :func:`for_run` makes). Nothing else may be there (the self-test's row 2)."""
        out = dict(self.run_exceptions)
        for p in (*self.visible, *self.writable, *self.readonly, *self.hide_runs):
            if p not in out and any(_within(p, h) and p != h for h in self.hide_host):
                out[p] = RUN_BIND_BACK
        return tuple(out.items())

    def inside_host_masks(self) -> tuple[str, ...]:
        """The paths of :meth:`bind_backs`."""
        return tuple(p for p, _ in self.bind_backs())


def bwrap_argv(layout: Layout, argv: list[str], *, cwd: str | os.PathLike[str] | None = None,
               path: str | None = None) -> list[str]:
    """The bubblewrap command that runs ``argv`` inside ``layout``. Only flags bubblewrap 0.4.0 (EL8) has. ``path`` is
    the ``PATH`` the caller's environment gives this process (default: this process's own). What it runs gets
    :meth:`Layout.contained_path` of it: set here, the one way into a sandbox, so a context cannot miss the register's
    tools whichever allow-list built its environment (CAPR-04; the designer's CAP-1 ruling 1)."""
    out = _bwrap_args(layout, argv, cwd=cwd, path=path)
    _refuse_too_many_arguments(layout, out)  # counted before bubblewrap starts (CS-4 addendum 9)
    return out


def _bwrap_args(layout: Layout, argv: list[str], *, cwd: str | os.PathLike[str] | None = None,
                path: str | None = None) -> list[str]:
    """:func:`bwrap_argv`, not yet counted against bubblewrap's limit."""
    # --new-session: no controlling terminal, so TIOCSTI has no terminal it would accept (CB-05; bubblewrap's answer to
    # CVE-2017-5226). bubblewrap's own processes stay in the caller's process group, so killing it still ends the run.
    out = [layout.bwrap, "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
           *(["--unshare-net"] if layout.private_network else []),  # F28 §3.2: its own loopback only
           "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", SANDBOX_TMP]
    for name in DISPLAY_ENV:
        out += ["--unsetenv", name]
    contained = layout.contained_path(path)
    if contained is not None:
        out += ["--setenv", "PATH", contained]
    links = dict(layout.put_back_links)
    for flag, path in order(layout):
        out += ([flag, path] if flag == "--tmpfs" else [flag, links[path], path] if flag == "--symlink"
                else [flag, path, path])
    for path in layout.hide_dirs:  # after every bind; before the remounts, as a mask inside a bind-back may be there
        if not _hidden_with_its_tree(layout, path):
            out += ["--tmpfs", path]
    for path in layout.hide_files:
        if not _hidden_with_its_tree(layout, path):
            out += ["--ro-bind", layout.mask_file, path]
    # after the bind-backs and masks into them, which keep their own flags; each one, as --remount-ro does not recurse.
    # A directory masked whole in the run's own tree is read-only too, so a write there fails instead of vanishing.
    tree_dirs = [p for p, _ in layout.tree_masks if p in layout.hide_dirs and not _hidden_with_its_tree(layout, p)]
    for path in (*layout.hide_host, *layout.hide_runs, *_left_out_of(layout), *tree_dirs):
        out += ["--remount-ro", path]
    if cwd is not None:
        out += ["--chdir", os.fspath(cwd)]
    return [*out, "--", *argv]


# bubblewrap 0.4.0 (EL8) takes at most this many arguments after its own name: one more and it exits with "bwrap:
# Exceeded maximum number of arguments 9000" (its maximum; measured on 0.4.0, 9,000 start and 9,001 are refused). Each
# entry put back in a directory a secret is left out of takes three (CS-4 addendum 9).
BWRAP_MAX_ARGS = 9000


def _refuse_too_many_arguments(layout: Layout, argv: list[str]) -> None:
    """CS-4 addendum 9: a bubblewrap command ``argv`` over :data:`BWRAP_MAX_ARGS` is refused before bubblewrap
    starts, naming each directory whose entries are put back, with how many, and the step: move entries out of the
    largest into a subdirectory."""
    count = len(argv) - 1
    if count <= BWRAP_MAX_ARGS:
        return
    masked = set(_left_out_of(layout))
    held = Counter(os.path.dirname(p) for p in (*layout.put_back, *(p for p, _ in layout.put_back_links))
                   if os.path.dirname(p) in masked).most_common()
    listed = ", ".join(f"{d} ({n} entries)" for d, n in held) or "none"
    envs = len(layout.env_masks) + len(layout.env_dirs) + len(layout.env_bulk)
    # where most of them are: what is left after the directories holding many are masked whole (_bounded_env)
    most = ", ".join(f"{d} ({n})" for d, n in Counter(os.path.dirname(p) for p in layout.env_masks).most_common(3))
    # the step for whichever takes more of the arguments: the entries put back, or the project's .env files
    step = (f"keep fewer .env files in the project (it has {envs}, each masked on its own, most in {most or 'none'})"
            if envs and envs >= sum(n for _, n in held) else
            f"move entries out of {held[0][0]} into a subdirectory, so it has fewer to put back" if held else
            "list fewer secret paths or writable roots")
    raise ContainmentUnavailable(
        f"this launch needs {count} arguments for bubblewrap, more than the {BWRAP_MAX_ARGS} bubblewrap 0.4.0 takes: "
        "each entry of a directory a secret is left out of is put back on its own, with three, and so is each of the "
        f"project's .env files masked in place ({envs} here); the directories whose entries are put back are "
        f"{listed}; the launch is refused before bubblewrap starts. To launch, {step}. "
        "This applies to every contained launch, workers included",
        arguments=count, limit=BWRAP_MAX_ARGS, put_back=dict(held), env_masks=envs, reason="bwrap_argument_limit")


def _hidden_with_its_tree(layout: Layout, path: str) -> bool:
    """Whether a secret at ``path`` is hidden already, with a tree masked whole (the sandbox's ``/tmp``, a host mask, a
    runs mask), so its own mask is not emitted: making its path in a read-only mask would fail. It is when it lies in
    such a tree and in none of the layout's binds inside that tree, which bring their part of the host back (a project
    under ``/run`` or ``/tmp``, its workspace, the run's own directories): there the secret is the host's file, and its
    mask is emitted like any other (review of #244, m1)."""
    binds = (*layout.visible, *layout.writable, *layout.readonly, *(p for p, _ in layout.run_exceptions))
    return any(_within(path, m) and not any(_within(path, b) and _within(b, m) and b != m for b in binds)
               for m in (SANDBOX_TMP, *layout.hide_host, *layout.hide_runs))


def _left_out_of(layout: Layout) -> tuple[str, ...]:
    """The directories of ``left_out_of`` that are masked: not one hidden with its tree already, whose entries put back
    would bring the host's ``/tmp`` or ``/run`` back (:func:`_hidden_with_its_tree`), nor one in a directory masked
    whole."""
    return tuple(d for d in layout.left_out_of
                 if not _hidden_with_its_tree(layout, d) and not any(_within(d, h) for h in layout.hide_dirs))


def order(layout: Layout) -> list[tuple[str, str]]:
    """:func:`bind_order` of everything ``layout`` binds and masks at a depth: the project, the writable binds, the
    read-only re-binds with the ``/run`` exceptions, the run's network directory, the ``/run`` and runs masks, and each
    directory a secret is left out of, with its other entries put back (but one the layout binds or masks itself,
    which takes its place)."""
    net_writable, net_readonly = layout.net_binds()
    writable = (*layout.writable, *net_writable)
    readonly = (*layout.readonly, *(p for p, _ in layout.run_exceptions), *net_readonly)
    masked = _left_out_of(layout)
    hidden = (*layout.hide_host, *layout.hide_runs, *masked)
    own = {*layout.visible, *writable, *readonly, *hidden, *layout.hide_dirs, *layout.tool_binds}

    def back(path: str) -> bool:
        return os.path.dirname(path) in masked and path not in own

    return bind_order(writable, readonly, hidden, visible=layout.visible,
                      put_back=[p for p in layout.put_back if back(p)],
                      links=[p for p, _ in layout.put_back_links if back(p)], tools=layout.tool_binds)


def for_check(layout: Layout, requested: str | None = None) -> Layout:
    """The layout a check of a contained run starts in (F28 §3.8, network containment design decision 3): the run's
    own, with no network unless the check's definition asks for the host's and the run's own policy gives the host's
    (equal to or stricter than the run, never wider). It never binds the run's network directory, so a check has no
    route to the relay or the egress proxy either.

    The project's `.env` files are scanned again for each check (:func:`project_env_masks`, at its cost), so a check
    finds the tree's `.env` files as they are when it starts, wherever a session that writes the project (the Lead's)
    has moved them since the run's layout was made, never the paths of an earlier scan (the quick check of #592). A
    containment.writable root that now holds one of them, or lies in a directory now masked whole, refuses the check."""
    network = SHARED if requested == SHARED and layout.network == SHARED else ISOLATED
    out = replace(layout, network=network, net_dir=None)
    if layout.project is None:
        return out
    out = replace(out, **_env_fields(_without_env(out), project_env_masks(layout.project, layout.env_keep,
                                                                                home=layout.env_home,
                                                                                needs=layout.env_needs),
                                     out.writable))
    out = _bounded_env(out)
    _refuse_env_roots([(p, p) for p in out.operator_writable], _env_secrets(out))
    bwrap_argv(out, [])  # counted before any check starts, as for_run counts the run's own
    return out


# Within one depth: an entry put back into a directory a secret is left out of first, so a bind of the layout's own
# there wins; then the project's visible bind, so a role's writable bind of the same path wins (the Lead's R-2 shape,
# CS-4); then writable binds; then read-only re-binds (the register's among them); then masks.
_RANK = {"put_back": -3, "--symlink": -3, "visible": -1, "--bind": 0, "--ro-bind": 1, "tool": 1, "--tmpfs": 2}


def bind_order(writable: tuple[str, ...] | list[str], readonly: tuple[str, ...] | list[str],
               hidden: tuple[str, ...] | list[str] = (), *,
               visible: tuple[str, ...] | list[str] = (), put_back: tuple[str, ...] | list[str] = (),
               links: tuple[str, ...] | list[str] = (),
               tools: tuple[str, ...] | list[str] = ()) -> list[tuple[str, str]]:
    """The project's visible binds and read-only re-binds (``--ro-bind``), the writable binds (``--bind``) and the masks
    of ``hide_host`` and ``hide_runs`` (``--tmpfs``) in the order bubblewrap applies them: by depth, ancestors first, so
    each holds for its subtree except where a deeper one says otherwise. On one path the mask comes last, after a
    re-bind, after a writable bind, after the visible bind. So no bind ever lands on a masked path after its mask
    (review of #231, m2): only deeper bind-backs come after it. A project under a masked tree (``/run/media/...``)
    stays visible for the same reason (CS-2; the Lead's approval, 2026-10-23). Otherwise the order within a depth is
    the layout's. An entry put back into a directory a secret is left out of (``put_back``, ``links``) comes a level
    below that directory's mask, as ``--ro-bind-try`` (it may have gone since the layout was made) or ``--symlink``;
    never as ``--ro-bind``, which the store check counts. The register (``tools``) is bound the same way: it is a host
    state that may change during a run. The one owner of the order: ``bwrap_argv`` emits it and the store check
    (:func:`_refuse_store_binds`) reasons about it."""
    tagged = ([("put_back", p) for p in put_back] + [("--symlink", p) for p in links]
              + [("visible", p) for p in visible] + [("--bind", p) for p in writable]
              + [("--ro-bind", p) for p in readonly] + [("tool", p) for p in tools]
              + [("--tmpfs", p) for p in hidden])
    ranked = sorted(tagged, key=lambda t: (len(Path(t[1]).parts), _RANK[t[0]]))
    flags = {"visible": "--ro-bind", "put_back": "--ro-bind-try", "tool": "--ro-bind-try"}
    return [(flags.get(f, f), p) for f, p in ranked]


def find_bwrap() -> str | None:
    found = shutil.which("bwrap")
    return os.path.realpath(found) if found else None


def _real(path: str | os.PathLike[str]) -> str:
    return os.path.realpath(os.fspath(path))


def _masks(home: str | None, extra: list[str], env: Mapping[str, str] | None = None, *,
           written: tuple[str, ...] | list[str] = ()) -> MaskPlan:
    """:func:`_mask_plan` for a sandbox that needs nothing of the host but ``home`` and writes only ``written`` (eval's
    two layouts, which take its fields as :func:`for_run` does: :meth:`MaskPlan.fields`): a linked directory that is or
    holds ``home`` is left unmasked there, where :func:`for_run` refuses the launch."""
    needed = [("the home directory", _real(home))] if home else []
    return _mask_plan(home, extra, env, needed, written)


@dataclass(frozen=True)
class MaskPlan:
    """What :func:`_mask_plan` masks, in :class:`Layout`'s fields (:meth:`fields`), and what refuses a launch
    (:func:`_refuse_masks`)."""

    dirs: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    left_out: tuple[str, ...] = ()
    left_out_of: tuple[str, ...] = ()
    put_back: tuple[str, ...] = ()
    put_back_links: tuple[tuple[str, str], ...] = ()
    tree_masks: tuple[tuple[str, str], ...] = ()
    tree_absent: tuple[tuple[str, str], ...] = ()
    fixed_masks: tuple[tuple[str, str], ...] = ()
    fixed_absent: tuple[tuple[str, str], ...] = ()
    refused: tuple[dict[str, Any], ...] = ()
    what: tuple[tuple[str, str], ...] = ()  # (each path above, what the secret there is): for a refusal that names it

    def fields(self) -> dict[str, Any]:
        """The :class:`Layout` fields of these masks."""
        return {"hide_dirs": self.dirs, "hide_files": self.files, "left_out": self.left_out,
                "left_out_of": self.left_out_of, "put_back": self.put_back, "put_back_links": self.put_back_links,
                "tree_masks": self.tree_masks, "tree_absent": self.tree_absent, "fixed_masks": self.fixed_masks,
                "fixed_absent": self.fixed_absent}


HOME_LIST = "the home directory's secret paths"  # what names a path of the home directory's lists (_named)
POLICY_HIDE = "containment.hide"
# The project's `.env` files, masked in place in every layout (:func:`project_env_masks`), since every layout shows
# the project. The one owner of the names: the OpenCode projection's read rules derive from these
# (``opencode.projection.ENV_READ_RULES``; the designer, 2026-11-06), so both layers name the same files. A name
# ``ENV_FILES`` matches is a `.env` file unless ``ENV_DOCS`` matches it too: `.env.example` is documentation by
# convention (V2's own default reads it), so it stays.
ENV_FILES = ("*.env", "*.env.*")
ENV_DOCS = ("*.env.example",)
PROJECT_ENV = "the project's .env files"  # what puts each there, on the launch line
ENV_WHAT = "a project .env file"  # what each is, for a refusal that names one
PROJECT_ENV_DIR = "a project directory the .env scan cannot read"  # one masked whole, on the launch line
ENV_DIR_WHAT = "a project directory that may hold a .env file"
PROJECT_ENV_BULK = "a project directory with more .env files than can be masked one by one"  # one masked whole
ENV_BULK_WHAT = "a project directory holding many .env files"


def _mask_plan(home: str | None, extra: list[str], env: Mapping[str, str] | None, needed: list[tuple[str, str]],
               written: tuple[str, ...] | list[str] = (), *,
               named_extra: list[tuple[str, str, str]] | tuple[tuple[str, str, str], ...] = ()) -> MaskPlan:
    """Every secret path, masked by its type (STG-05 CS-4, addenda 6 and 7), for every role: the secrets and the
    display's credentials in ``home``, those the launching environment ``env`` names (default: this process's), the
    policy's ``extra`` (:func:`_named`), each ``named_extra`` (path, what names it, what it is: a provider's client
    certificate and key, ``client_cert.mask_entries``), and what the links in the directories masked whole point at
    (:func:`_linked`).

    * A directory is masked whole, at its real path; one that is or holds something in ``needed`` refuses the launch.
    * Anything else is left out of its directory (:func:`_left_out`), whether or not it exists now: that directory is
      an empty tmpfs, every other entry it holds now is put back (a link made again as a link), and it is then
      read-only. So a replacement or a creation on the host is not seen inside.
    * In the run's own tree (``written``: the Lead's project, a worker's workspace, the run's own directories) a tmpfs
      would make that level read-only, so a file there is masked by an empty file bound over it, as it is at the
      launch, and a directory masked whole there is read-only too; a path absent at the launch is not masked, as a mask
      would make it on the host. The launch names each, with what put it there (``tree_masks``, ``tree_absent``;
      :func:`tree_masks_line`; the operator's decisions of 2026-10-28). The same where the directory is ``/`` or cannot
      be listed, named as its own case (``fixed_masks``, ``fixed_absent``; CS-4 addendum 8, ruling 2.1): a write there
      by the operator's own tools needs root, or a directory the operator cannot read. The operator's OpenCode login
      database in the run's own tree refuses the launch: OpenCode makes its sidecars beside
      it as it runs, which hold login rows, and no mask covers them.

    Its limits: an entry made during the session in a directory a secret is left out of is not seen inside until the
    next launch; an entry put back that the host replaces shows what it held at the launch, until the next launch; in
    the run's own tree, a file the host replaces by rename, or first creates there, during the session is seen inside
    until the next launch; links are resolved at the launch, and hard links are out of scope."""
    from aew.harness.opencode import login

    launching = _launching(home, env)
    by: dict[str, str] = {}  # each masked path -> what put it there
    what: dict[str, str] = {}  # each masked path -> what the secret there is
    dirs: list[str] = []
    leave: list[str] = []

    def named(path: str, source: str, secret: str) -> None:
        if os.path.isdir(path) and not _sandbox_own(_real(path)):
            real = _real(path)
            by.setdefault(real, f"the link {path}" if os.path.islink(path) else source)
            what.setdefault(real, f"what {path} links to" if os.path.islink(path) else secret)
            dirs.append(real)
            return
        # A link into the sandbox's own /dev or /proc (`~/.bash_history -> /dev/null`, how a shell keeps no history)
        # is left out of its directory itself; what it points at is not the host's, so nothing there is masked.
        entries = [e for e in _left_out(path) if not _sandbox_own(e)]
        for i, entry in enumerate(entries):  # the first as named, each other through the link before it
            by.setdefault(entry, source if i == 0 else f"the link {entries[i - 1]}")
            what.setdefault(entry, secret if i == 0 else f"what {entries[i - 1]} links to")
        leave.extend(entries)

    for raw, source, secret in _named(home, extra, launching, named_extra):
        named(raw, source, secret)
    dirs = list(dict.fromkeys(dirs))
    opencode: dict[str, list[str]] = {}  # the operator's OpenCode directories, real, with what puts each there
    for directory, variables in login.operator_masks(launching).items():
        if os.path.isdir(directory):
            names = opencode.setdefault(_real(directory), [])
            names += [v for v in variables if v not in names]
    refused: list[dict[str, Any]] = []
    for directory in dirs:
        held = _held(directory, needed)
        if held:
            refused.append({"directory": directory, "variables": opencode.get(directory, []),
                            "opencode": directory in opencode, "holds": held})
    linked, targets, refused_links = _linked(dirs, needed, skip={r["directory"] for r in refused})
    for link, target in linked:
        by.setdefault(target, f"the link {link}")
        what.setdefault(target, f"what {link} links to")
        dirs.append(target)
    for link, target in targets:
        named(target, f"the link {link}", f"what {link} links to")
    refused += refused_links

    def within(path: str, roots: list[str] | tuple[str, ...]) -> bool:
        return any(_within(path, r) for r in roots)

    leave = [p for p in dict.fromkeys(leave) if not within(p, dirs)]
    for store in (*login.store_files(launching), *login.store_files(launching, real=True)):
        tree = next((w for p in _left_out(str(store)) if not within(p, dirs) for w in written
                     if _within(os.path.dirname(p), w)), None)
        if tree is not None:
            variable = "OPENCODE_DB" if launching.get("OPENCODE_DB") else "XDG_DATA_HOME"
            refused.append({"file": str(login.db_path(launching)), "variables": [variable], "tree": tree})
            break
    left: dict[str, list[str]] = {}  # directory -> the names left out of it
    in_place: list[str] = []  # where a secret cannot be left out of its directory
    for path in leave:
        parent, name = os.path.split(path)
        if parent == os.path.dirname(parent) or within(parent, written):
            in_place.append(path)
        else:
            left.setdefault(parent, []).append(name)
    listed: dict[str, list[os.DirEntry[str]]] = {}
    for parent, names in left.items():
        try:
            with os.scandir(parent) as it:
                listed[parent] = sorted(it, key=lambda e: e.name)
        except OSError:  # not listed: its other entries could not be put back
            in_place += [os.path.join(parent, n) for n in names]
    put_back: list[str] = []
    links: list[tuple[str, str]] = []
    for parent, entries in listed.items():
        for entry in entries:
            if entry.name in left[parent] or entry.path in dirs or entry.path in listed:
                continue  # left out; or masked in place by its own tmpfs, whose mount point bubblewrap makes
            try:
                if entry.is_symlink():
                    links.append((entry.path, os.readlink(entry.path)))
                else:
                    put_back.append(entry.path)
            except OSError:
                continue  # gone since it was listed
    in_place = [p for p in dict.fromkeys(in_place) if not os.path.islink(p)]  # a link's target is named itself
    # Fail closed in the run's own tree (the quick check of #592): a secret there that cannot be checked (its directory
    # cannot be searched, so it reads as absent) is masked by its directory whole, unless that holds what the run needs
    for path in [p for p in in_place if within(os.path.dirname(p), written) and _unchecked(p)]:
        parent = os.path.dirname(path)
        if not _held(parent, needed) and parent not in dirs:
            by.setdefault(parent, by[path])
            what.setdefault(parent, f"the directory of {what[path]}")
            dirs.append(parent)
            in_place.remove(path)
    in_tree = [p for p in in_place if within(os.path.dirname(p), written)]  # the rest: under / or unlistable
    files = [p for p in in_place if os.path.lexists(p) and not os.path.isdir(p)]
    tree_dirs = [d for d in dirs if within(d, written)]
    listed_out = tuple(os.path.join(p, n) for p in listed for n in dict.fromkeys(left[p]))
    return MaskPlan(dirs=tuple(dirs), files=tuple(files), left_out=listed_out,
                    left_out_of=tuple(listed), put_back=tuple(put_back), put_back_links=tuple(links),
                    tree_masks=tuple((p, by[p]) for p in (*tree_dirs, *(f for f in files if f in in_tree))),
                    tree_absent=tuple((p, by[p]) for p in in_tree if not os.path.lexists(p)),
                    fixed_masks=tuple((p, by[p]) for p in files if p not in in_tree),
                    fixed_absent=tuple((p, by[p]) for p in in_place if p not in in_tree and not os.path.lexists(p)),
                    refused=tuple(refused), what=tuple((p, what[p]) for p in (*dirs, *files, *listed_out)))


Named = tuple[str, str, str]  # a secret path, what names it, and what it is


def _named(home: str | None, extra: list[str], env: Mapping[str, str],
           named_extra: list[Named] | tuple[Named, ...] = ()) -> list[Named]:
    """Every named secret path, absolute and as named, with what names it and what it is: :data:`SECRET_DIRS`,
    :data:`SECRET_FILES`, :data:`DISPLAY_FILES` and :data:`HISTORY_FILES` in ``home`` (:data:`SECRET_WHAT`) and the
    copies beside a secret file there (:func:`_prefixed_files`), the paths the launching environment ``env`` names
    (:func:`_env_masks`), the policy's ``extra``, and ``named_extra`` as given."""
    out = [(os.path.join(home, p), HOME_LIST, SECRET_WHAT[p])
           for p in (*SECRET_DIRS, *SECRET_FILES, *DISPLAY_FILES, *HISTORY_FILES)] if home else []
    out += [(p, HOME_LIST, f"a copy of {SECRET_WHAT['.claude.json']}") for p in _prefixed_files(home)]
    out += [*_env_masks(env), *((os.path.expanduser(p), POLICY_HIDE, "a containment.hide entry") for p in extra)]
    out += list(named_extra)
    seen: dict[str, tuple[str, str]] = {}
    for path, source, secret in out:
        seen.setdefault(os.path.abspath(path), (source, secret))
    return [(path, source, secret) for path, (source, secret) in seen.items()]


def _unlistable(root: str, exc: OSError) -> ContainmentUnavailable:
    """The refusal of a project the `.env` scan cannot list or check, naming the entry that failed and the fix for its
    cause (the quick check of #592, m1): AEW reads its store there, so it is never masked whole."""
    entry = os.fspath(exc.filename) if exc.filename else root
    what = f"the project {root}" if entry == root else f"{entry}, at the top of the project {root},"
    step = (f"give this account read and search permission on {root} (for example chmod u+rx {root})"
            if exc.errno in (errno.EACCES, errno.EPERM) else f"remove or repair {entry}")
    return ContainmentUnavailable(f"{what} cannot be listed or checked ({exc.strerror}), so the project's .env files "
                                  f"cannot be found and every contained launch of it is refused. To launch, {step}",
                                  project=root, entry=entry, reason="project_unlistable")


class EnvScan(NamedTuple):
    """What :func:`project_env_masks` finds: the `.env` files to mask in place, the directories to mask whole, the
    `.env`-named links it does not follow, each with why (named on the launch line, masking nothing), the links whose
    target outside the project it masks (``(link, target)``, named on the launch line), the directories this account
    cannot read that it read through a user namespace (:func:`_walk_in_namespace`), and why it could not do that where
    it fell back to masking them whole."""

    files: list[str]
    dirs: list[str]
    links: tuple[tuple[str, str], ...] = ()
    outside: tuple[tuple[str, str], ...] = ()
    read_through: tuple[str, ...] = ()
    fallback: str | None = None


# Left out of the walk, at the project's top only, each where it is a read-only mount of its own, so nothing in the
# tree can be moved under it: `.aew`, which has masks of its own, and `.git` where the layout binds it so as the git
# metadata (the quick check of #592, m2: a checked-out branch named like a `.env` file keeps a working git inside).
ENV_LEFT_OUT = (".aew", ".git")
# The host's own system trees: a link's target there is never masked, whatever the home directory is
SYSTEM_TREES = ("/etc", "/usr", "/proc", "/sys", "/dev")


class EnvRules(NamedTuple):
    """Where a `.env`-named link's target is masked (:func:`_env_link`). ``keep``: what a run needs (the interpreter,
    AEW's package, the git metadata), never masked, and the project's own ``.git`` is left out of the walk where it is
    here. ``home``: the operator's home directory, where a target outside the project under another name is masked.
    ``needs``: the run's own directories and the harness binary it starts, where such a target never is."""

    keep: tuple[str, ...] = ()
    home: str | None = None
    needs: tuple[str, ...] = ()


def _env_named(name: str) -> bool:
    """``name`` is a `.env` file's (:data:`ENV_FILES`, but none of :data:`ENV_DOCS`)."""
    return any(fnmatchcase(name, p) for p in ENV_FILES) and not any(fnmatchcase(name, p) for p in ENV_DOCS)


def _env_link(link: str, root: str, rules: EnvRules) -> tuple[str | None, str | None]:
    """``(target to mask, why not)`` for a `.env`-named link (:func:`project_env_masks`): its target where that is a
    file it masks, else None, with why where the link is named. Never raises, so no link refuses a launch or has its
    directory masked whole (the operator's rulings of 2026-11-27)."""
    try:
        mode = os.stat(link).st_mode
    except FileNotFoundError:  # a link to nothing: nothing to read there
        return None, None
    except OSError as exc:  # a loop, or a path through a file: nothing can be read through it, inside either
        return None, f"its target cannot be followed ({exc.strerror}), so nothing is read through it"
    if not stat.S_ISREG(mode):  # a link to a directory, or to anything that is not a file
        return None, None
    target = _real(link)
    if _sandbox_own(target):
        return None, None
    if any(_within(target, k) for k in rules.keep):
        return None, f"its target {target} is what a run needs, which is never masked"
    if _within(target, root):
        if any(_within(target, os.path.join(root, d)) for d in ENV_LEFT_OUT):
            return None, f"its target {target} is in the project's own {os.path.relpath(target, root).split(os.sep)[0]}"
        return target, None
    if _env_named(os.path.basename(target)):
        return target, None
    # Outside the project under another name: masked where it is a plain file of the operator's own home, as a
    # credentials file kept there is, never a system file or one of the run's own (the operator, 2026-11-27: "Yes agree
    # with your recommendations on 592")
    home = _real(rules.home) if rules.home else None
    if (home and home != os.path.abspath(os.sep) and _within(target, home)
            and not any(_within(target, n) for n in rules.needs) and not any(_within(target, t) for t in SYSTEM_TREES)):
        return target, None
    return None, (f"its target {target} lies outside the project and the home directory, or is one of the run's own, "
                  "and is not named like a .env file")


def _walk(starts: list[str], root: str, rules: EnvRules, left_out: set[str]) -> dict[str, Any]:
    """The walk of :func:`project_env_masks` from ``starts`` (each a directory in the project ``root``): ``files``,
    ``dirs`` (those it cannot read), ``links`` (``[link, why]``) and ``outside`` (``[link, target]``), as JSON. It
    raises ``project_unlistable`` for ``root`` alone, as only the project is never masked whole."""
    files: set[str] = set()
    dirs: set[str] = set()
    links: dict[str, str] = {}
    outside: dict[str, str] = {}
    stack = list(starts)
    while stack:
        top = stack.pop()
        try:
            with os.scandir(top) as it:
                entries = list(it)
        except FileNotFoundError:  # gone during the walk
            continue
        except OSError as exc:
            if top == root:
                raise _unlistable(root, exc) from exc
            dirs.add(os.path.dirname(top) if exc.errno == errno.ENAMETOOLONG and top not in starts else top)
            continue
        below: list[str] = []
        found: list[str] = []
        named: dict[str, str] = {}
        away: dict[str, str] = {}
        try:
            for entry in entries:
                # every entry's type by its own lstat, never the listing's: a directory that can be listed but not
                # searched lists its names, and only a stat of one finds that nothing in it can be checked
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                except FileNotFoundError:  # gone during the walk
                    continue
                if stat.S_ISDIR(mode):
                    if not (top == root and entry.path in left_out):
                        below.append(entry.path)
                    continue
                if not _env_named(entry.name):
                    continue
                if stat.S_ISREG(mode):
                    found.append(_real(entry.path))
                elif stat.S_ISLNK(mode):
                    target, why = _env_link(entry.path, root, rules)
                    found += [target] if target is not None else []
                    named.update({entry.path: why} if why is not None else {})
                    away.update({entry.path: target} if target is not None and not _within(target, root) else {})
        except OSError as exc:  # an entry this scan cannot check: its directory whole
            if top == root:
                raise _unlistable(root, exc) from exc
            dirs.add(top)
            continue
        files.update(f for f in found if not _sandbox_own(f))
        links.update(named)
        outside.update(away)
        stack += below
    return {"files": sorted(files), "dirs": sorted(dirs), "links": sorted(links.items()),
            "outside": sorted(outside.items())}


# The child that walks the directories this account cannot read, in a user namespace that maps it to root, so it
# holds CAP_DAC_READ_SEARCH over the inodes it owns: those a session of its own can take the permissions of (the
# quick check of #592, m3; the operator, 2026-11-27). It imports this module from the path this process does.
_NS_CHILD = ("import json, sys; a = json.loads(sys.argv[1]); sys.path.insert(0, a['path']); "
             "from aew.harness.containment import layout as L; "
             "print(json.dumps(L._walk(a['starts'], a['root'], L.EnvRules(*a['rules']), set())))")
NS_SCAN_TIMEOUT_S = 300


def _walk_in_namespace(starts: list[str], root: str, rules: EnvRules) -> tuple[dict[str, Any] | None, str | None]:
    """``(the walk of starts, None)`` from a child in a user namespace of this account (bubblewrap, which containment
    needs anyway), or ``(None, why)`` where it cannot run: not Linux, no bubblewrap, or one that may not make the
    namespace or keep the capability in it (a host that restricts unprivileged user namespaces, a setuid bubblewrap).
    One more process per scan, only where the walk met a directory it cannot read."""
    if not sys.platform.startswith("linux"):
        return None, "user namespaces are Linux's"
    bwrap = find_bwrap()
    if bwrap is None:
        return None, "bubblewrap is not installed"
    package = os.path.dirname(_aew_package())
    argv = [bwrap, "--die-with-parent", "--unshare-user", "--uid", "0", "--gid", "0", "--cap-add",
            "CAP_DAC_READ_SEARCH", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--",
            sys.executable, "-I", "-B", "-c", _NS_CHILD,
            json.dumps({"path": package, "starts": starts, "root": root, "rules": list(rules)})]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=NS_SCAN_TIMEOUT_S, check=False,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"the namespace scan did not finish ({type(exc).__name__})"
    if done.returncode != 0:
        last = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1][-200:]
        return None, f"the namespace scan failed ({last})"
    try:
        walked = json.loads(done.stdout)
    except ValueError:
        return None, "the namespace scan's result could not be read"
    return walked, None


def project_env_masks(project: str | os.PathLike[str], keep: tuple[str, ...] = (), *, home: str | None = None,
                      needs: tuple[str, ...] = (), namespace: bool = True) -> EnvScan:
    """Every `.env` file in ``project``, at any depth (:data:`ENV_FILES`, but none of :data:`ENV_DOCS`), at its real
    path, sorted: what :func:`for_run` masks in place by the empty read-only file in every layout, so containment hides
    the project's `.env` files from every tool. A directory is not one: `.env` is also a virtual environment's usual
    name, and masking that whole would hide the interpreter a run may need.

    A `.env`-named link to a file is masked by its target, which the mask hides at both paths, where that target is in
    the project, or is itself named like a `.env` file, or is a plain file in the operator's ``home`` that is not one
    of the run's own directories nor the harness binary it starts (``needs``) nor in a system tree
    (:data:`SYSTEM_TREES`); never where it is in ``keep``
    (what a run needs: the interpreter, AEW's package, the git metadata), or in the project's own ``.aew`` or ``.git``.
    A target outside the project that is masked is named (``outside``). Any other such link masks nothing and is named
    with why (``links``), as its target reads the same by its own path, and so is one whose target cannot be followed
    (a loop, or a path through a file), as nothing can be read through it. A link to nothing, or to a directory, is not
    a `.env` file.

    The scan, at each launch and for each check's sandbox (:func:`for_check`), is a walk of the whole tree, whatever
    git makes of it: tracked, untracked and ignored files alike, and a nested repository's or a submodule's own, as
    each is in the tree a run sees. It leaves out only the project's own ``.aew`` (the store, and the runs' own
    directories, which have masks of their own) and its own ``.git`` directory where ``keep`` holds it, as the git
    metadata every layout binds read-only (:data:`ENV_LEFT_OUT`): each is a read-only mount of its own, so nothing in
    the tree is moved under it. No directory is left out by its name alone: a ``.git`` directory below the top is
    walked as any other. It follows no link to a directory, so it ends: a directory outside the project that a link
    inside it points at is not walked. Its cost is the tree's size, one stat for each entry: 1 to 3 s for 200,000
    entries in ignored vendored directories, measured on loaded hosts, two to three times the walk without the stats.

    It fails closed, and refuses for no directory below the project (the quick checks of #592): every entry is
    checked by its own stat, never by the listing alone. A directory the walk cannot list, or one holding an entry it
    cannot stat (a directory that can be listed but not searched), is walked again where ``namespace`` allows, by a
    child in a user namespace that maps this account to root (:func:`_walk_in_namespace`), which can read the
    directories this account owns whatever their mode, so the `.env` files there are masked one by one
    (``read_through``). What that cannot read (a directory another account owns), or all of them where the child
    cannot run (``fallback`` says why), is in ``dirs``, masked whole by an empty directory as a containment.hide
    directory is, as a `.env` file in it may still be read by name; one whose path is too long to list, its deepest
    directory the walk reached. One gone during the walk is not there to hide. The project itself is never masked
    whole, as AEW reads its store there: one that cannot be listed, or searched, is refused (``project_unlistable``),
    naming the entry and the fix.

    Its limits: a directory masked whole hides all it holds, what a run needs there included (a containment.writable
    root in it is refused), so where the namespace cannot read it, taking such a directory's permissions away stops
    the project's contained launches, the workers' included, until they are given back; that hides, and shows nothing.
    The masks are those of the tree as each scan found it: a file first created, moved or replaced by rename during the
    session, or while a scan walks the tree, is masked from the next scan that finds it (the next launch, or the next
    check's sandbox), as a containment.hide entry in the run's own tree is from the next launch. A `.env` file in the
    project's own git directory is not masked: that is git's."""
    root = _real(project)
    try:
        if not stat.S_ISDIR(os.stat(root).st_mode):
            return EnvScan([], [])
    except FileNotFoundError:  # no project directory to show, so nothing in it to hide
        return EnvScan([], [])
    except OSError as exc:
        raise _unlistable(root, exc) from exc
    rules = EnvRules(keep, home, needs)
    git = os.path.join(root, ".git")
    walked = _walk([root], root, rules, {os.path.join(root, ".aew"), *((git,) if git in keep else ())})
    through: tuple[str, ...] = ()
    fallback = None
    if walked["dirs"] and namespace:
        again, fallback = _walk_in_namespace(walked["dirs"], root, rules)
        if again is not None:
            through = tuple(d for d in walked["dirs"] if d not in again["dirs"])
            walked = {key: sorted({*map(_hashable, walked[key]), *map(_hashable, again[key])})
                      for key in ("files", "links", "outside")} | {"dirs": again["dirs"]}
    hidden = walked["dirs"]

    def shown(path: str) -> bool:
        return not any(_within(path, d) for d in hidden)

    return EnvScan([f for f in walked["files"] if shown(f)], hidden,
                   tuple((p, why) for p, why in walked["links"] if shown(p)),
                   tuple((p, t) for p, t in walked["outside"] if shown(p)), through, fallback if hidden else None)


def _hashable(item: Any) -> Any:
    """A walk's JSON item, a path or a ``[path, text]`` pair, as a set can hold it."""
    return tuple(item) if isinstance(item, list) else item


def _unmasked(files: tuple[str, ...], covered: tuple[str, ...], paths: list[str]) -> tuple[str, ...]:
    """Those of ``paths`` no other mask hides already: one of ``files``, or under one of ``covered``, is left to it."""
    return tuple(p for p in paths if p not in files and not any(_within(p, c) for c in covered))


# What each of the project's `.env` masks is, by its Layout field: what names it on the launch line, and what it is
# for a refusal that names it.
_ENV_LABELS = {"env_dirs": (PROJECT_ENV_DIR, ENV_DIR_WHAT), "env_bulk": (PROJECT_ENV_BULK, ENV_BULK_WHAT),
               "env_masks": (PROJECT_ENV, ENV_WHAT)}


def _env_fields(base: Mapping[str, Any], scan: EnvScan, writable: tuple[str, ...] | list[str],
                bulk: tuple[str, ...] = ()) -> dict[str, Any]:
    """The :class:`Layout` fields of ``base`` (the other masks' fields) with the project's `.env` files of ``scan``
    (:func:`project_env_masks`) masked in place among ``hide_files``, the directories its walk could not read, and
    ``bulk`` (:func:`_bounded_env`), masked whole among ``hide_dirs``, and each named on the launch line
    (``tree_masks``) where it lies in a tree the run writes: the Lead's project. A path another mask of ``base`` covers
    is left to it."""
    covered = (*base["hide_dirs"], *base["left_out"])
    env = {"env_dirs": _unmasked(base["hide_files"], covered, scan.dirs), "env_bulk": bulk,
           "env_masks": _unmasked(base["hide_files"], covered, scan.files)}
    env["env_masks"] = tuple(f for f in env["env_masks"] if not any(_within(f, d) for d in bulk))
    fields = dict(base)
    fields.update(env)
    fields["hide_files"] = (*base["hide_files"], *env["env_masks"])
    fields["hide_dirs"] = (*base["hide_dirs"], *env["env_dirs"], *bulk)
    fields["env_links"] = tuple((p, why) for p, why in scan.links if not any(_within(p, c) for c in (*covered, *bulk)))
    fields["env_outside"] = tuple((p, t) for p, t in scan.outside if t in env["env_masks"])
    fields["env_read_through"] = scan.read_through
    fields["env_fallback"] = scan.fallback if env["env_dirs"] else None
    fields["tree_masks"] = (*base["tree_masks"], *((p, _ENV_LABELS[key][0]) for key in _ENV_LABELS for p in env[key]
                                                   if any(_within(p, w) for w in writable)))
    return fields


def _without_env(layout: Layout) -> dict[str, Any]:
    """The mask fields of ``layout`` with none of the project's `.env` masks: the base :func:`_env_fields` adds them
    to."""
    files, dirs = set(layout.env_masks), {*layout.env_dirs, *layout.env_bulk}
    labels = {by for by, _ in _ENV_LABELS.values()}
    return {"hide_files": tuple(p for p in layout.hide_files if p not in files),
            "hide_dirs": tuple(p for p in layout.hide_dirs if p not in dirs), "left_out": layout.left_out,
            "tree_masks": tuple((p, by) for p, by in layout.tree_masks if by not in labels)}


def _env_secrets(layout: Layout) -> tuple[tuple[str, str], ...]:
    """(path, what it is) for each of the project's `.env` masks in ``layout``: what a writable root must not reach."""
    return tuple((p, _ENV_LABELS[key][1]) for key in _ENV_LABELS for p in getattr(layout, key))


def _bounded_env(layout: Layout) -> Layout:
    """``layout`` within bubblewrap's argument limit where the project's `.env` files are what takes it over (the
    operator's ruling of 2026-11-27): each file takes three arguments, so the directories holding the most of them are
    masked whole instead (``env_bulk``), each with two to four, the deepest that saves enough first. A directory that
    is or holds anything else the layout binds, writes, protects or keeps, or lies in what it binds read-only (the
    interpreter's prefix among them), is never one, nor the project itself. Where that is not enough the launch is
    refused as before (``bwrap_argument_limit``)."""
    over = len(_bwrap_args(layout, [])) - BWRAP_MAX_ARGS
    if over <= 0 or not layout.env_masks or layout.project is None:
        return layout
    root = layout.project
    bound = (*layout.readonly, *layout.protected, *layout.tool_binds, *layout.skills_binds, *layout.env_keep)
    held = (*layout.writable, *bound, *layout.hide_runs, layout.mask_file,
            *((layout.net_dir,) if layout.net_dir else ()))
    files = set(layout.env_masks)
    bulk = list(layout.env_bulk)
    while over > 0:
        counts: Counter[str] = Counter()
        for f in files:
            up = os.path.dirname(f)
            while up != root and _within(up, root):
                counts[up] += 1
                up = os.path.dirname(up)
        options = [(n, d) for d, n in counts.items()
                   if n >= 2 and not any(_within(h, d) for h in held) and not any(_within(d, b) for b in bound)]
        if not options:
            break
        enough = [o for o in options if 3 * o[0] - 4 >= over]
        n, chosen = (max(enough, key=lambda o: (len(Path(o[1]).parts), -o[0])) if enough
                     else max(options, key=lambda o: (o[0], len(Path(o[1]).parts))))
        bulk = [b for b in bulk if not _within(b, chosen)] + [chosen]
        files = {f for f in files if not _within(f, chosen)}
        over -= 3 * n - 4
    scan = EnvScan(sorted(files), list(layout.env_dirs), layout.env_links,
                   tuple((p, t) for p, t in layout.env_outside if t in files), layout.env_read_through,
                   layout.env_fallback)
    return replace(layout, **_env_fields(_without_env(layout), scan, layout.writable, bulk=tuple(sorted(bulk))))


def _refuse_env_roots(roots: list[tuple[str, str]], secrets: tuple[tuple[str, str], ...]) -> None:
    """A containment.writable root that holds one of the project's `.env` masks, or lies in a directory masked whole,
    is refused, as a root that holds any mask is (CS-4 addendum 7, ruling 2), with the step that lifts it (the quick
    check of #592, m1): for a directory the scan could not read, giving it its permissions back."""
    for raw, root in roots:
        hit = [(what, p) for p, what in secrets if _within(p, root) or _within(root, p)]
        if not hit:
            continue
        what, path = hit[0]
        if what == ENV_DIR_WHAT:
            why = (f"{path} is masked whole, as the project's .env scan could not read it (this account cannot list "
                   "it, or check an entry in it), and a writable root is never bound over a mask")
            step = (f"give {path} back its read and search permission for this account at your own terminal (for "
                    f"example chmod u+rx {path}), or repair the entry in it that cannot be checked; the next launch "
                    "scans it again")
        elif what == ENV_BULK_WHAT:
            why = f"{path} is masked whole, as it holds more of the project's .env files than can be masked one by one"
            step = f"keep fewer .env files under {path}"
        else:
            why = f"it holds {path}, one of the project's .env files, which every contained run finds masked"
            step = f"move {path} out of it, or list a narrower directory that holds no .env file"
        raise ContainmentUnavailable(
            f"policy containment.writable root {raw!r} ({root}) is refused and runs cannot launch: {why}. To launch, "
            f"{step}. This applies to every contained launch, workers included.",
            root=raw, resolved=root, exposes=[{"what": w, "path": p} for w, p in hit], reason="writable_root_env_mask")


def _sandbox_own(path: str) -> bool:
    """``path`` is under the sandbox's own ``/dev`` or ``/proc`` (:data:`SANDBOX_OWN`): the layout never masks, leaves
    out or puts back anything there, whatever names it."""
    return any(_within(path, d) for d in SANDBOX_OWN)


def _left_out(raw: str) -> list[str]:
    """What a named path that is not a directory leaves out of its directory, each at its directory's real path: the
    path itself where it exists, else its first component that does not exist yet (so ``~/.config/git/credentials``
    leaves ``git`` out of ``~/.config`` when there is no ``~/.config/git``), and, where that is a link, the same for
    what it points at. Nothing where the deepest existing ancestor is not a directory, as nothing can be made there."""
    out: list[str] = []
    path = os.path.abspath(raw)
    for _ in range(MAXSYMLINKS + 1):
        entry = _first_absent(path)
        if entry is None:
            break
        entry = os.path.join(_real(os.path.dirname(entry)), os.path.basename(entry))
        if entry in out:
            break
        out.append(entry)
        if not os.path.islink(entry) or os.path.isdir(entry):
            break
        path = _real(entry)
    return out


def _unchecked(path: str) -> bool:
    """Whether ``path`` cannot be checked: ``lstat`` fails for another reason than its absence."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return False


def _first_absent(path: str) -> str | None:
    """``path`` where it exists; else its first component that does not, below its deepest existing ancestor, or None
    when that ancestor is not a directory."""
    below = path
    while not os.path.lexists(below):
        up = os.path.dirname(below)
        if up == below:
            return None
        if os.path.lexists(up):
            return below if os.path.isdir(up) else None
        below = up
    return below


def _held(directory: str, needed: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """What in ``needed`` is ``directory`` or lies in it."""
    return [(what, path) for what, path in needed if _within(path, directory)]


def _linked(dirs: list[str], needed: list[tuple[str, str]], *, skip: set[str]) -> tuple[
        list[tuple[str, str]], list[tuple[str, str]], list[dict[str, Any]]]:
    """What the symlinks in a directory masked whole point at, for every role, as every secret mask is: ``(dirs,
    targets, refused)``, each with its link. A linked directory is masked whole (``dirs``), and the links in it are
    followed the same way; one that is or holds something in ``needed`` is ``refused``, named by its link. Anything
    else a link points at is a named path (``targets``, left out by the caller), so a target made after the launch is
    not seen either. Each directory is walked once, so a cycle ends; one in ``skip`` (refused already) is not walked,
    nor its links named. Its limits: links are resolved at the launch; a directory the operator's account cannot list
    is not walked; hard links are out of scope."""
    linked: list[tuple[str, str]] = []
    targets: list[tuple[str, str]] = []
    refused: dict[str, dict[str, Any]] = {}

    masked = [d for d in dirs if d not in skip]  # a directory refused already covers nothing: a link into it is named
    queue = list(masked)

    def covered(path: str) -> bool:
        return any(_within(path, d) for d in (*masked, *(t for _, t in linked)))

    while queue:
        for link in _links_in(queue.pop(0)):
            target = _real(link)
            if _sandbox_own(target):  # the sandbox's own /dev or /proc: nothing of the host's is there
                continue
            if not os.path.isdir(target):
                targets.append((link, target))
            elif not covered(target) and target not in refused:
                held = _held(target, needed)
                if held:
                    refused[target] = {"directory": target, "link": link, "holds": held}
                else:
                    linked.append((link, target))
                    queue.append(target)
    return linked, targets, list(refused.values())


def tree_masks_line(layout: Layout) -> str | None:
    """The launch's one line when a secret path lies in the run's own tree (:func:`_mask_plan`; CS-4 addendum 7 and the
    operator's decisions of 2026-10-28), or in a directory it cannot be left out of, ``/`` or one this account cannot
    list (addendum 8, ruling 2.1): each mask there and each path not masked as absent, with what put it there, what to
    do instead, and the limits. None when there is none."""
    def listed(entries: tuple[tuple[str, str], ...]) -> str:
        return ", ".join(f"{p} ({by})" for p, by in entries)

    # the operator's words for a path absent at the launch
    absent = ("not there at launch, so not masked; if it appears during the session, the run sees it until the next "
              "launch")
    out = []
    parts = [f"masked in place, read-only, in the tree this run writes: {listed(layout.tree_masks)}"] \
        if layout.tree_masks else []
    parts += [f"{absent}: {listed(layout.tree_absent)}"] if layout.tree_absent else []
    if parts:
        out.append(f"{'; '.join(parts)}. A file the host replaces by rename, or first creates there, during the "
                   "session is seen inside until the next launch. To change one, edit it at your own terminal, or keep "
                   "the real file outside that tree (for ssh, an Include from your real ~/.ssh/config)")
    fixed = [f"masked in place, read-only, as it cannot be left out of its directory (/, or one this account cannot "
             f"list): {listed(layout.fixed_masks)}"] if layout.fixed_masks else []
    fixed += [f"{absent}, as it cannot be left out of its directory (/, or one this account cannot list): "
              f"{listed(layout.fixed_absent)}"] if layout.fixed_absent else []
    if fixed:
        out.append(f"{'; '.join(fixed)}. A file replaced or first created there during the session is seen inside "
                   "until the next launch; a write there by your own tools needs root, or a directory you cannot read")

    def mine(path: str) -> bool:
        return any(_within(path, w) for w in layout.writable)

    links = [(p, why) for p, why in layout.env_links if mine(p)]
    if links:
        out.append(f"named like a .env file but not followed, so masking nothing: {listed(tuple(links))}. To have one "
                   "masked, make it the file itself, or a link to a file in the project, in your home directory, or "
                   "named like a .env file")
    away = [(p, f"its target {t}") for p, t in layout.env_outside if mine(p)]
    if away:
        out.append(f"named like a .env file and masked at its target outside the project, which reads as empty there "
                   f"too in contained runs: {listed(tuple(away))}")
    through = [d for d in layout.env_read_through if mine(d)]
    if through:
        out.append("not readable by this account, so read through a user namespace of its own, and their .env files "
                   f"masked one by one: {', '.join(through)}")
    if layout.env_fallback and any(mine(d) for d in layout.env_dirs):
        out.append(f"the directories masked whole as the .env scan cannot read them could not be read through a user "
                   f"namespace either: {layout.env_fallback}")
    return ". ".join(out) or None


def _links_in(top: str) -> list[str]:
    """Every symlink at any depth in directory ``top``, without following one (each is resolved by the caller)."""
    out: list[str] = []
    stack = [top]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    if entry.is_symlink():
                        out.append(entry.path)
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
        except OSError:
            continue
    return sorted(out)


def _launching(home: str | None, env: Mapping[str, str] | None) -> Mapping[str, str]:
    """The launching environment ``env`` (default: this process's), with ``home`` as its home directory where it
    names none."""
    env = os.environ if env is None else env
    return {"HOME": home, **env} if home else env


def _env_masks(env: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """Credential paths the launching environment names rather than the home directory, each with the variable that
    names it and what it is: the file ``XAUTHORITY`` names
    (CB-04), the history file ``HISTFILE`` names (CS-4 addendum 12; never one under ``/dev`` or ``/proc``, which the
    sandbox has its own of: ``HISTFILE=/dev/null`` is how a shell keeps none), git's credential cache and store-helper
    file under a custom ``XDG_CACHE_HOME`` or ``XDG_CONFIG_HOME``, and every place AEW's host side reads the operator's
    OpenCode from (``opencode.login.operator_masks`` and ``operator_files``, their one owner: STG-05 CS-4, outcome 2,
    the Lead's view holds no operator credential). Read in the process that makes the layout: a run's supervisor, whose
    environment is the launching CLI's without AEW's own credentials (``harness_ops.supervisor_env``), or the CLI
    itself."""
    from aew.harness.opencode import login

    out = [(env["XAUTHORITY"], "XAUTHORITY", SECRET_WHAT[".Xauthority"])] if env.get("XAUTHORITY") else []
    histfile = os.path.expanduser(env.get("HISTFILE") or "")
    if histfile and not any(_within(p, d) for p in (histfile, os.path.realpath(histfile)) for d in SANDBOX_OWN):
        out.append((histfile, "HISTFILE", "the shell's history"))
    if env.get("XDG_CACHE_HOME"):
        out.append((os.path.join(env["XDG_CACHE_HOME"], "git", "credential"), "XDG_CACHE_HOME",
                    SECRET_WHAT[".cache/git/credential"]))
    if env.get("XDG_CONFIG_HOME"):
        out.append((os.path.join(env["XDG_CONFIG_HOME"], "git", "credentials"), "XDG_CONFIG_HOME",
                    SECRET_WHAT[".config/git/credentials"]))
    for path, variables in login.operator_masks(env).items():
        out.append((str(path), " and ".join(variables) or "the operator's OpenCode", "OpenCode's own directory"))
    for path, variables in login.operator_files(env).items():
        out.append((str(path), " and ".join(variables) or "the operator's OpenCode",
                    "OpenCode's configuration file" if variables == ("OPENCODE_CONFIG",) else
                    "OpenCode's login database"))
    return [(os.path.expanduser(p), source, secret) for p, source, secret in out]


def _refuse_masks(refused: tuple[dict[str, Any], ...], home: str | None) -> None:
    """A mask that would hide what the run needs, or that cannot cover what it should, refuses the launch, once, naming
    each such path with what puts it there and its one step (the quick check of #283 at c307481a, m4; STG-05 CS-4,
    addendum 6, ruling 5):

    * a directory masked whole that is or holds something the run needs (its workspace, the project, the home
      directory, AEW's own directories, the Python environment), named by the variable that puts the operator's
      OpenCode there, or by the link in a masked directory whose target it is;
    * the operator's OpenCode login database in a tree the run writes (``file``): OpenCode makes its sidecars beside it
      as it runs, which hold login rows, and no mask covers a file made in such a tree (the operator's decision of
      2026-10-28)."""
    from aew.harness.opencode import login

    clauses, steps = [], []
    for entry in refused:
        if "file" in entry:
            db, variable, tree = entry["file"], entry["variables"][0], entry["tree"]
            dest = login.operator_dir({"HOME": home or os.path.expanduser("~")}, "data")
            clauses.append(f"{variable} puts the operator's OpenCode login database at {db}, in a tree the run writes "
                           f"({tree}), where OpenCode makes its -wal and -shm files as it runs and no mask covers them")
            steps.append(f"close OpenCode, move {db} with its -wal, -shm and -journal files to {dest}, and set "
                         f"OPENCODE_DB={dest / os.path.basename(db)}")
            continue
        directory, (what, path) = entry["directory"], entry["holds"][0]
        holds = f"that directory is or holds {what} ({path}), which the run needs"
        if "link" in entry:
            clauses.append(f"{entry['link']} links to {directory}, which a contained run masks whole (it masks what a "
                           f"link in a masked directory points at), and {holds}")
            steps.append(f"point {entry['link']} at a directory that holds nothing the run needs, or remove it")
            continue
        named = entry["variables"]
        if named:
            where = f"{' and '.join(named)} put{'s' if len(named) == 1 else ''} the operator's OpenCode files in"
        else:
            where = "by default, OpenCode keeps the operator's OpenCode files in" if entry["opencode"] else (
                "a credential directory is")
        clauses.append(f"{where} {directory}, which a contained run masks whole, and {holds}")
        moved = [(v, str(login.operator_dir({"HOME": home or os.path.expanduser("~")}, v[4:-5].lower())))
                 for v in named]  # where OpenCode keeps that kind of directory with the variable unset
        if moved and not any(_held(d, entry["holds"]) or _real(d) == directory for _, d in moved):
            steps += [f"move the operator's OpenCode files from {directory} to {d}, and unset {v}" for v, d in moved]
        else:
            steps.append(f"move {what} ({path}) out of {directory}" if path != directory else
                         f"keep {what} in a directory that is not masked, instead of {directory}")
    if not clauses:
        return
    raise ContainmentUnavailable(
        f"{'; '.join(clauses)}; the launch is refused. To launch, {'; and '.join(dict.fromkeys(steps))}. This applies "
        "to every contained launch, workers included",
        refused=[{k: [{"what": w, "path": p} for w, p in v] if k == "holds" else v for k, v in e.items()
                  if k != "opencode"} for e in refused],
        variables=list(dict.fromkeys(v for e in refused for v in e.get("variables", []))),
        links=[e["link"] for e in refused if "link" in e], reason="mask_holds_the_run")


def display_files(home: str | None, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The display's credential files present on this host (CB-04), resolved: the ones row 3 of the launch self-test
    must find unreadable from inside. Masked by :func:`_masks` with the other secrets."""
    env = os.environ if env is None else env
    candidates = [os.path.join(home, p) for p in DISPLAY_FILES] if home else []
    candidates += [env["XAUTHORITY"]] if env.get("XAUTHORITY") else []
    return tuple(dict.fromkeys(_real(p) for p in candidates if os.path.isfile(p)))


def _prefixed_files(home: str | None) -> list[str]:
    """Regular files directly in ``home`` named after a :data:`SECRET_FILE_PREFIXES` entry, as named (not recursive; a
    directory with such a name is not a file and is left alone). One made after the launch is not seen inside either:
    ``home`` is a directory secrets are left out of, so only what it held at the launch is put back."""
    if not home:
        return []
    try:
        with os.scandir(home) as it:
            names = sorted(e.name for e in it if e.name.startswith(SECRET_FILE_PREFIXES))
    except OSError:
        return []
    return [os.path.join(home, n) for n in names if os.path.isfile(os.path.join(home, n))]


def private_git(run_dir: Path, workspace: Path) -> tuple[Path, dict[str, str]]:
    """Create the run's private index (seeded from the worktree's real index) and object store, and the
    environment that points git at them. The real index, ``HEAD`` and refs stay read-only to the agent."""
    from aew.workspace import git

    gitdir = git.git_dir(workspace)
    common = git.common_dir(workspace)
    root = run_dir / PRIVATE_GIT
    (root / "objects").mkdir(parents=True, exist_ok=True)
    real_index = gitdir / "index"
    if real_index.exists():
        shutil.copy2(real_index, root / "index")
    env = {"GIT_INDEX_FILE": str(root / "index"), "GIT_OBJECT_DIRECTORY": str(root / "objects"),
           "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(common / "objects")}
    return root, env


def retire_private_git(run_dir: Path) -> None:
    """The private index and objects are scratch: nothing real refers to them, so they end with the run."""
    shutil.rmtree(run_dir / PRIVATE_GIT, ignore_errors=True)


def _git_metadata(workspace: Path) -> tuple[list[str], list[str]]:
    """(read-only binds, protected paths) for the git metadata a workspace's processes must never change."""
    from aew.errors import AEWError
    from aew.workspace import git

    try:
        gitdir = git.git_dir(workspace)
        common = git.common_dir(workspace)
    except AEWError as exc:  # never an empty protected list: the self-test would have nothing to check
        raise ContainmentUnavailable(f"the git metadata of workspace {workspace} cannot be resolved: {exc.message}",
                                     workspace=str(workspace)) from exc
    binds = [_real(common)]
    if _real(gitdir) != _real(common) and not _real(gitdir).startswith(_real(common) + os.sep):
        binds.append(_real(gitdir))
    protected = [str(gitdir / name) for name in ("HEAD", "index", "commondir", "gitdir")
                 if (gitdir / name).exists()]
    protected += [str(common / "HEAD"), str(common / "config"), str(common / "refs" / "heads"),
                  str(common / "objects")]
    pointer = workspace / ".git"
    if pointer.is_file():
        binds.append(_real(pointer))
        protected.append(str(pointer))
    return binds, [p for p in protected if os.path.exists(p)]


def _guarded(ws: Path, *, project: str | os.PathLike[str] | None, runs: str | os.PathLike[str] | None,
             bridge_dir: str | None, masks: tuple[tuple[str, str], ...],
             host: tuple[str, ...] = (RUN,), net_dir: str | None = None,
             left_out: tuple[tuple[str, str], ...] = ()) -> list[tuple[str, str]]:
    """(what, path) for every location an operator's writable root must neither equal, contain nor lie under. The
    shared temporary directory is listed separately (``_SHARED_TMP``): only containing it, or reaching one of AEW's
    own directories in it, exposes other runs."""
    import tempfile

    from aew.workspace import git

    out = [("the git repository metadata", _real(git.common_dir(ws))),
           ("the workspace's git directory", _real(git.git_dir(ws)))]
    for tmp in {_real(SANDBOX_TMP), _real(tempfile.gettempdir())}:
        out.append((_SHARED_TMP, tmp))
    if project is not None:
        out.append(("AEW's control state, evidence and records (.aew)", _real(Path(project) / ".aew")))
    if runs is not None:
        out.append(("every run's harness state and bridge credentials (the runs directory)", _real(runs)))
    if bridge_dir:
        out.append(("this run's bridge socket", _real(bridge_dir)))
    if net_dir:
        out.append(("this run's network sockets (its relay and egress proxy)", _real(net_dir)))
    for prefix in {sys.prefix, sys.base_prefix}:
        if prefix:
            out.append(("the Python environment AEW runs from", _real(prefix)))
    # ruling 2 (G3 addendum 7): the register lives outside every sandbox's writable binds (#321 review, F7)
    out.append(("AEW's host state (the capability register and the register of weaker contexts)",
                _real(hoststate.root())))
    # the G3 clients' approval records stay outside every sandbox's writable binds too (A-44 BOY-05.a; #660 review)
    from aew.g3client import approval_records_dir

    out.append(("the G3 clients' approval records", _real(approval_records_dir())))
    # each secret named by what it is, so the refusal says why (CS-4 addendum 8, ruling 1)
    out += [(f"{secret}, a masked secret", p) for p, secret in masks]
    out += [(f"{secret}, a secret path left out of the sandbox whether or not it exists", p) for p, secret in left_out]
    # R-1 binds nothing back into /run but measured exceptions: an operator root there would be one (the Lead,
    # 2026-10-23, on CS-2's plan, Q6), and one containing it would show it all again.
    out += [("the host's runtime directory, masked whole (STG-05 CB-03, ruling R-1)", _real(h)) for h in host]
    return out


_SHARED_TMP = "the shared temporary directory, where every run's bridge socket lives"


def _within(path: str, root: str) -> bool:
    """``path`` is ``root`` or under it. A sandbox's paths are POSIX (``/run``) on every platform its layout is built
    on, so ``/`` separates as well as this platform's own separator."""
    base = root.rstrip("/" + os.sep)
    return path == root or path.startswith((base + os.sep, base + "/"))


def _refuse_unsafe_root(raw: str, root: str, guarded: list[tuple[str, str]], *, workspaces: str) -> None:
    """An operator root that reaches anything containment protects would make the sandbox a label only: refused,
    naming what it would expose and what to list instead."""
    exposed = []
    for what, path in guarded:
        if what == _SHARED_TMP:
            below = os.path.relpath(root, path).split(os.sep)[0] if _within(root, path) and root != path else ""
            if _within(path, root) or below.startswith("aew-"):  # it, or AEW's own directories in it
                exposed.append((what if not below else "another run's AEW directory in the shared temporary "
                                "directory", path if not below else os.path.join(path, below)))
        elif _within(path, root) or _within(root, path):
            exposed.append((what, path))
    if _within(workspaces, root):
        exposed.append(("every other workspace (the workspaces root)", workspaces))
    if exposed:
        listed = "; ".join(f"{what} ({path})" for what, path in exposed[:4])
        instead = _narrower(raw, root, guarded)
        exact = f": here, {instead!r} in place of {raw!r}, or take {raw!r} out" if instead else ""
        raise ContainmentUnavailable(
            f"policy containment.writable root {raw!r} ({root}) would let every contained run write {listed}. "
            "Containment protects these, so this root is refused and runs cannot launch. List a narrower directory "
            "that holds none of them instead, such as a build output or cache directory (for example "
            f"<project>/build, or ~/.cache/<tool>), in containment.writable in the execution policy{exact}. This "
            "applies to every contained launch, workers included.",
            root=raw, resolved=root, exposes=[{"what": w, "path": p} for w, p in exposed], instead=instead)


def _narrower(raw: str, root: str, guarded: list[tuple[str, str]]) -> str | None:
    """The exact entry to list in place of a refused writable root (quick check 4 of #283, m11): the first directory
    in it, in the operator's own spelling, that is not, holds no and lies under no path containment protects. None
    where it has none."""
    try:
        with os.scandir(root) as it:
            names = sorted(e.name for e in it if e.is_dir(follow_symlinks=False))
    except OSError:
        return None
    for name in names:
        path = os.path.join(root, name)
        if not any(_within(p, path) or _within(path, p) for what, p in guarded if what != _SHARED_TMP):
            return f"{raw.rstrip('/')}/{name}"
    return None


STORE = (".aew", "state")  # the store, relative to the project root (aew.engine.store.STORE_REL under the AEW root)


def _refuse_store_binds(role: str, project: str | os.PathLike[str], order: list[tuple[str, str]]) -> None:
    """STG-05 CB-07 (ruling R-3): no writable bind ``W`` may change the store's path. ``W`` is not the store and not
    under it; and if ``W`` contains the store, the first component below ``W`` on the path to it is re-bound read-only
    after ``W`` (``order`` is :func:`bind_order`'s), which makes it a mount point that cannot be renamed, replaced or
    removed. This is not the operator-root guard (``_refuse_unsafe_root``): run directories live under ``.aew/local``,
    so a role's own binds need only stay off the store's path.

    The path is checked twice: as the engine walks it (the project's own ``.aew/state``, which ``Kernel.locate`` finds
    by name) and where it leads. A symlink on the walked path cannot be protected by a re-bind (a mount lands on its
    target and leaves the link renamable), so a writable bind over one is refused (review of #231, m1)."""
    walked = os.path.join(_real(project), *STORE)
    links = [p for p in (os.path.dirname(walked), walked) if os.path.islink(p)]
    for i, (flag, w) in enumerate(order):
        if flag != "--bind":
            continue
        reached = [p for p in links if _within(p, w)]
        if reached:
            raise ContainmentUnavailable(
                f"the {role} layout's writable bind {w} contains {reached[0]}, a symlink on the path to AEW's store, "
                "and a read-only re-bind cannot keep a contained process from renaming or replacing a symlink; the "
                "launch is refused. Keep the writable bind outside the project, or make the project's .aew and "
                ".aew/state real directories", role=role, bind=w, store=walked, symlink=reached[0],
                reason="store_path_symlink")
        for store in dict.fromkeys((walked, _real(walked))):
            _refuse_store_bind(role, store, w, order[i + 1:])


def _refuse_store_bind(role: str, store: str, w: str, after: list[tuple[str, str]]) -> None:
    """:func:`_refuse_store_binds` for one writable bind ``w`` and one spelling of the store's path; ``after`` is what
    the order applies after ``w``."""
    if _within(w, store):
        raise ContainmentUnavailable(
            f"the {role} layout's writable bind {w} is AEW's store ({store}) or lies under it, so a contained "
            "process could change the store; the launch is refused. Keep the workspace, scratch and every "
            "writable root outside the project's .aew/state", role=role, bind=w, store=store,
            reason="writable_bind_in_store")
    if _within(store, w):
        below = os.path.join(w, os.path.relpath(store, w).split(os.sep)[0])
        if not any(f == "--ro-bind" and p == below for f, p in after):
            raise ContainmentUnavailable(
                f"the {role} layout's writable bind {w} contains AEW's store ({store}), and {below} is not "
                "re-bound read-only after it, so a contained process could rename or replace the directories "
                f"on the store's path; the launch is refused. Re-bind {below} read-only in the same layout, or "
                "keep the writable bind outside the project", role=role, bind=w, store=store, needs=below,
                reason="store_path_writable")


# AEW's own code must lie outside every writable bind (register STG-05; the relay handoff's RLY-05): it is trusted code,
# since every supervisor and relay is a host process that imports it afresh, outside any sandbox. The interpreter's
# prefix is re-bound read-only (:func:`interpreter_binds`); the rest of AEW's import path, an editable install's source
# tree among it, is checked here.
TRUSTED_CODE_WRITABLE, TRUSTED_CODE_SYMLINK = "trusted_code_writable", "trusted_code_symlink"
HELD_TRUSTED = 5  # how many exposed pieces a refusal names: enough to see the shape, bounded
# What each piece of AEW's code is (:func:`trusted_code`), and what the operator does where a writable bind reaches it
# (review of #539, m2): each kind is cleared its own way.
PACKAGE, IMPORT_ROOT, PACKAGE_LINK = ("AEW's own package", "the import path of AEW's supervisors and relays",
                                      "a link in AEW's package")
SCRIPT_DIR = "the launching command's own directory, first on AEW's import path"
FROM_PYTHONPATH, IMPORT_DIR = "a directory PYTHONPATH puts on AEW's import path", "a directory on AEW's import path"
_REINSTALL = ("run AEW from an installation outside every directory a contained run writes: a regular install, or an "
              "editable install of a checkout no run writes")
TRUSTED_CODE_REMEDIES = {
    PACKAGE: _REINSTALL, IMPORT_ROOT: _REINSTALL, PACKAGE_LINK: _REINSTALL,
    SCRIPT_DIR: "start AEW with the `aew` command, or with `python -P -m aew`, so the launching directory is not on "
                "its import path",
    FROM_PYTHONPATH: "remove that directory from PYTHONPATH in the environment AEW is started from",
    IMPORT_DIR: "keep that directory outside every directory a contained run writes, or remove the .pth file or site "
                "setting that puts it on the import path",
}


def trusted_code_remedy(what: str) -> str:
    """What clears an exposed piece of AEW's code of kind ``what`` (:data:`TRUSTED_CODE_REMEDIES`)."""
    return TRUSTED_CODE_REMEDIES.get(what, _REINSTALL)


def _aew_package() -> str:
    """The directory of the ``aew`` package this process runs, as it imports it."""
    import aew

    return os.path.dirname(os.path.abspath(aew.__file__))


def trusted_code() -> list[tuple[str, str]]:
    """(what, path) for AEW's own code, in the spelling this process imports it by:

    * its package, and the package's parent, which is the import path of every Python process the engine starts with a
      credential (``procs.engine_imports``);
    * every symbolic link in the package's tree (an editable install's tree of links, a linked module), whose target is
      what is imported;
    * every directory on this process's import path, named by where it comes from (PYTHONPATH, or a .pth file or the
      site configuration). That includes the first entry, the script's directory or the working directory under
      ``python -m``, when ``-P`` did not remove it: the contained Lead's relays run in the launching process
      (review of #539, m1). An installed ``aew`` command's directory needs no exception of its own: it lies outside
      every writable bind (``pip install --user`` puts it in the home directory's own), or under the interpreter's
      prefix, which every layout re-binds read-only.

    Read from the filesystem at each launch: never a list of modules to keep in step. What it does not cover is listed
    as the known limits in ADR-0009's amendment of 2026-11-24."""
    package = _aew_package()
    out = [(PACKAGE, package), (IMPORT_ROOT, os.path.dirname(package))]
    stack = [package]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    if entry.is_symlink():
                        out.append((PACKAGE_LINK, entry.path))
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
        except OSError:
            continue  # an unreadable directory imports nothing either
    from_env = {os.path.abspath(p) for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p}
    entries = list(sys.path)
    if entries and not sys.flags.safe_path:
        first = os.path.abspath(entries.pop(0) or os.curdir)  # "" is the working directory
        if os.path.exists(first):
            out.append((SCRIPT_DIR, first))
    for entry in entries:
        path = os.path.abspath(entry or os.curdir)
        if os.path.exists(path):
            out.append((FROM_PYTHONPATH if path in from_env else IMPORT_DIR, path))
    return list(dict.fromkeys(out))


# The most symbolic links a resolution follows, as the kernel's own limit on Linux (MAXSYMLINKS): a path that needs
# more does not resolve, so nothing is imported through it.
MAX_HOPS = 40


def _resolution(path: str) -> tuple[list[tuple[str, bool]], str]:
    """Every path the kernel looks up to resolve ``path``, one component and one link at a time, with whether it is a
    symbolic link, and where it leads. Each is what a write could replace to change what ``path`` imports: the links on
    its spelling, the links their targets pass through, and the directories in between (#539 quick check: a link met
    during the resolution counts as much as one on the spelling). Stops after :data:`MAX_HOPS` links."""
    parts = list(Path(os.path.abspath(path)).parts)
    current, queue = parts[0], parts[1:]
    seen: list[tuple[str, bool]] = []
    hops = 0
    while queue:
        name = queue.pop(0)
        if name in ("", os.curdir):
            continue
        if name == os.pardir:
            current = os.path.dirname(current)
            continue
        candidate = os.path.join(current, name)
        if not os.path.islink(candidate):
            seen.append((candidate, False))
            current = candidate
            continue
        seen.append((candidate, True))
        hops += 1
        try:
            target = os.readlink(candidate)
        except OSError:
            break
        if hops > MAX_HOPS:
            break
        more = list(Path(target).parts)
        if os.path.isabs(target):
            current, more = more[0], more[1:]
        queue = more + queue
    return list(dict.fromkeys(seen)), current


def _held_read_only(path: str, w: str, after: set[str]) -> bool:
    """CB-07's rule for ``path`` under the writable bind ``w``: the first directory below ``w`` on its path is re-bound
    read-only after ``w`` (``after``), so nothing on the path from there down can be renamed, replaced or removed."""
    if path == w:
        return False
    return os.path.join(w, os.path.relpath(path, w).split(os.sep)[0]) in after


def trusted_code_exposed(steps: list[tuple[str, str]],
                         trusted: list[tuple[str, str]] | None = None) -> list[dict[str, str]]:
    """Every piece of ``trusted`` code (default :func:`trusted_code`) that a writable bind in ``steps``
    (:func:`bind_order`'s) could change, with the bind and the reason. As for the store (``_refuse_store_binds``), a
    path under a writable bind ``W`` is safe only when the first directory below ``W`` on its path is re-bound read-only
    after ``W`` (the prefix of a virtual environment in the project, for one). The rule applies to every path the
    piece's resolution looks up (:func:`_resolution`), its target included, and not only to its spelling. A symbolic
    link inside ``W`` is safe on the same rule only when it lies strictly below that re-bound directory (a virtual
    environment's ``lib64`` link: review of #539, M1); the re-bound directory itself, or a link above it, could be
    replaced. ``W`` itself, passed through on the way, is a mount point: only a piece that resolves to it is exposed."""
    trusted = trusted_code() if trusted is None else trusted
    resolved = {walked: _resolution(walked) for _, walked in trusted}
    found: list[dict[str, str]] = []
    for i, (flag, w) in enumerate(steps):
        if flag != "--bind":
            continue
        after = {p for f, p in steps[i + 1:] if f == "--ro-bind"}
        for what, walked in trusted:
            seen, final = resolved[walked]
            shown = walked if _within(walked, w) else final
            for p, link in seen:
                if not _within(p, w) or p == w:
                    continue
                if link and (p in after or not _held_read_only(p, w, after)):
                    found.append({"what": what, "path": shown, "bind": w, "symlink": p,
                                  "reason": TRUSTED_CODE_SYMLINK})
                    break
                if not link and not _held_read_only(p, w, after):
                    found.append({"what": what, "path": shown, "bind": w, "reason": TRUSTED_CODE_WRITABLE})
                    break
            else:
                if final == w:
                    found.append({"what": what, "path": shown, "bind": w, "reason": TRUSTED_CODE_WRITABLE})
    return found


def _refuse_trusted_code(role: str, steps: list[tuple[str, str]]) -> None:
    """A layout that could change AEW's own code (:func:`trusted_code_exposed`) is refused, naming the first piece, the
    bind and what clears it: under ``required`` the launch is refused, and under ``allow_weaker`` it runs labelled
    weaker (``containment.establish``) and enters the register of weaker contexts like every other."""
    found = trusted_code_exposed(steps)
    if not found:
        return
    first = found[0]
    how = (f"through {first['symlink']}, a symbolic link inside it that is not re-bound read-only"
           if first["reason"] == TRUSTED_CODE_SYMLINK else "and it is not re-bound read-only")
    raise ContainmentUnavailable(
        f"AEW's own code must lie outside every writable bind: the {role} layout's writable bind {first['bind']} "
        f"reaches {first['what']} ({first['path']}) {how}, and AEW's supervisors and relays import it; the launch is "
        f"refused. To launch, {trusted_code_remedy(first['what'])}", role=role, bind=first["bind"],
        path=first["path"], exposes=[{k: v for k, v in f.items() if k != "reason"} for f in found[:HELD_TRUSTED]],
        reason=first["reason"])


def interpreter_binds() -> list[str]:
    """The interpreter's prefixes behind ``aew``, wherever they live: re-bound read-only in every layout
    (:func:`for_run`), which is what keeps a virtual environment in a writable tree out of reach."""
    return list(dict.fromkeys(_real(p) for p in (sys.prefix, sys.base_prefix) if p and os.path.isdir(p)))


def operator_roots(cfg: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """``(as written, real path)`` for each writable root the policy's ``containment.writable`` adds; :func:`for_run`
    refuses one that is not an existing directory."""
    return [(raw, _real(os.path.expanduser(raw))) for raw in (cfg or {}).get("writable") or []]


def lead_trusted_code_exposed(project: str | os.PathLike[str],
                              cfg: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """:func:`trusted_code_exposed` for what decides it in the Lead's layout of ``project`` (``aew opencode``'s, whose
    workspace is the project: ``opencode.lead.establish_layout``), without building it: the project and the policy's
    writable roots, with the interpreter's prefixes re-bound read-only as :func:`for_run` re-binds them. For
    ``aew doctor``, which writes nothing into the project."""
    writable = [_real(project), *(p for _, p in operator_roots(cfg) if os.path.isdir(p))]
    return trusted_code_exposed(bind_order(writable, interpreter_binds()))


def _refuse_run_bind_backs(layout: Layout, *, project: str, workspace: str) -> None:
    """The operator's ruling of 2026-10-23 on R-1 (:data:`RUN_BIND_BACK`): a project under ``/run`` is bound back into
    the mask on the designer's five conditions, and a layout that would bind anything else back is refused. This
    holds the two that bound what comes back:

    1. only the layout's own binds of the project and this run's workspace (each at or under one of them), at their
       resolved real paths, with the modes they have anywhere else (the same entries of the one bind order); never an
       ancestor, such as ``/run/media/<user>``;
    2. none is a host mask itself or lies under :data:`RUN_PROTECTED`.

    Condition 3 is the operator-root guard (:func:`_guarded`); 4 and 5 are the self-test's row 2, which checks the
    socket inventory in the finished sandbox, after every bind-back, and allows exactly :meth:`Layout.bind_backs`.
    The name-resolution exception (:func:`run_exceptions`) is the operator's ruling of its own, and is not one of
    these."""
    exceptions = {p for p, _ in layout.run_exceptions}
    for p in (*layout.visible, *layout.writable, *layout.readonly, *layout.hide_runs):
        mask = next((h for h in layout.hide_host if _within(p, h)), None)
        if mask is None or p in exceptions:
            continue
        first = "" if p == mask else os.path.relpath(p, mask).replace(os.sep, "/").split("/")[0]
        where = f"the {layout.role} layout would bind {p} back into {mask}, which is masked whole"
        if not first or any(fnmatchcase(first, pattern) for pattern in RUN_PROTECTED):
            raise ContainmentUnavailable(
                f"{where}, and {p} is {'the mask itself' if not first else 'under ' + os.path.join(mask, first)}, "
                f"where nothing is bound back (G3's and AEW's services, the operator's runtime directory, the "
                "buses, systemd's); the launch is refused. Keep the project and its workspaces elsewhere, such as "
                "removable media under /run/media", role=layout.role, path=p, mask=mask,
                protected=[os.path.join(mask, n) for n in RUN_PROTECTED], reason="run_bind_back_protected")
        if not (_within(p, project) or _within(p, workspace)):
            raise ContainmentUnavailable(
                f"{where}, and only the project ({project}) and this run's workspace ({workspace}) are bound back "
                "there (the operator's ruling of 2026-10-23 on R-1); the launch is refused. Keep it outside "
                f"{mask}, or inside the project", role=layout.role, path=p, mask=mask, project=project,
                workspace=workspace, reason="run_bind_back_outside_project")
        if _real(p) != p:
            raise ContainmentUnavailable(
                f"{where}, by a path that is not its real one ({_real(p)}): a bind-back is made at its resolved "
                "path only; the launch is refused", role=layout.role, path=p, mask=mask, real=_real(p),
                reason="run_bind_back_not_real")


def _tool_fields(run: Path, tools: tuple[Any, ...] | None, hide_host: tuple[str, ...], readonly: list[str],
                 protected: list[str]) -> dict[str, Any]:
    """The capability register in this layout (CAPR-04, CAPR-Q02; ``aew.capability.bind``): the context's own directory
    of entries, read-only, and what its entries lead to, the register, read-only, each also a path the self-test must
    find unwritable. Each is one for any number of records. Nothing here refuses a launch (CAPR-12). A register under a
    host mask is not bound in: a bind there would re-open part of a tree the layout masks whole, and
    :func:`_refuse_run_bind_backs` reads no tool bind, so this filter is what keeps the mask whole. Its copies' checks
    then fail inside, each entry becomes the stub, and the status says why."""
    from aew.capability import bind, status, store

    if sys.platform == "win32":  # pragma: windows-only  # no contained context there, and links need a privilege
        return {}
    plan = bind.safe_plan() if tools is None else tools
    first, last = bind.place(run, plan)
    root = first.parent
    readonly.append(_real(root))
    protected.append(str(first))
    binds = [_real(store.root())] if os.path.isdir(store.root()) else []
    for tool in plan:
        binds += [_real(os.path.dirname(p)) for kind, p in tool.candidates if kind == status.AEW_COPY]
    binds = [b for b in dict.fromkeys(binds) if not any(_within(b, h) for h in hide_host)]
    binds = [b for b in binds if not any(_within(b, o) and b != o for o in binds)]  # the register holds its payloads
    protected += [b for b in binds if b not in protected]
    return {"tools": tuple(plan), "tools_first": str(first), "tools_last": str(last) if any(
        t.where == bind.OWN_NAME for t in plan) else None, "tool_binds": tuple(binds)}


def _harness_binary() -> tuple[str, ...]:
    """The harness binary a run starts, at its real path, from its owner (``opencode.adapter.binary_command``), so a
    `.env` link's target is never that binary; none where there is none, as the launch then refuses on its own."""
    from aew.harness.opencode.adapter import binary_command

    try:
        return (_real(binary_command()[-1]),)
    except (AEWError, OSError):
        return ()


def for_run(*, role: str, scope: str, workspace: str | os.PathLike[str], run_dir: str | os.PathLike[str],
            scratch: str | os.PathLike[str], bridge_dir: str | None, policy: dict[str, Any] | None,
            project: str | os.PathLike[str], home: str | None = None,
            runs: str | os.PathLike[str] | None = None, env: Mapping[str, str] | None = None,
            network: str = SHARED, net_dir: str | None = None,
            state_dir: str | os.PathLike[str] | None = None, tools: tuple[Any, ...] | None = None,
            skills_dir: str | os.PathLike[str] | None = None,
            pack: str | os.PathLike[str] | None = None) -> Layout:
    """The layout of a run of ``role`` in ``scope``. Creates the run's private directories (and, for a writing
    role, its private git state). Raises ``ContainmentUnavailable`` when the role has no layout, bubblewrap is
    missing, or a bind would reach the store's path. ``project`` is the authoritative project root (bound read-only
    so it stays visible; its ``.aew/local`` is hidden, and its store checked against every writable bind); ``runs``
    is the directory holding every run's directory (hidden too, with only this run's own directories bound back).
    ``env`` is the launching environment, for the credential paths it names (default: this process's). ``network``
    is the run's network mode (:data:`NETWORK_MODES`) and ``net_dir`` the directory of its network sockets
    (``aew.harness.containment.netns``), with its :data:`NET_SHIM` subdirectory made here. ``state_dir`` is the role's
    own harness state that outlives one run (the Lead's OpenCode state, kept per project: STG-05 CS-4 addendum 1),
    made here and bound back writable like the run's own directories. ``tools`` is what the context gets of the
    capability register (``aew.capability.bind.plan``; default: this host's, as every launch's). ``skills_dir`` is the
    run's copy of its skills, made before the layout (``aew.skills.deliver``): bound read-only and protected when it
    exists, and not bound at all when it does not, so a missing skill never refuses a launch. ``pack`` is the run's own
    pinned pack, its launch contract, under the project's `.aew/local`: bound read-only, alone, over that mask, and
    protected, so the run reads its own contract again (`aew context show`) and no other invocation's (register
    E368)."""
    access = WORKSPACE_ACCESS.get(role)
    if access is None:
        raise ContainmentUnavailable(f"role {role!r} has no containment layout; its runs are refused", role=role)
    if network not in NETWORK_MODES:
        raise ContainmentUnavailable(f"network mode {network!r} is not one of {', '.join(NETWORK_MODES)}",
                                     network=network)
    scopes = WRITE_SCOPES.get(role, frozenset())
    if access == "write" and scope not in scopes:
        allowed = " or ".join(f"a {s} scope" for s in sorted(scopes)) or "no scope"
        raise ContainmentUnavailable(f"the {role} role may write only {allowed}, not a {scope!r} scope", role=role,
                                     scope=scope, allowed=sorted(scopes))
    bwrap = find_bwrap()
    if bwrap is None:
        raise ContainmentUnavailable("bubblewrap (bwrap) is not installed or not on PATH")
    cfg = policy or {}
    ws = Path(_real(workspace))
    run = Path(run_dir)
    harness = run / "harness"
    cache = Path(scratch) / ".cache"
    for d in (harness, Path(scratch), cache):
        d.mkdir(parents=True, exist_ok=True)
    mask = run / MASK_FILE
    if not mask.exists():
        mask.write_bytes(b"")
    mask.chmod(0o444)
    contained = {"TMPDIR": SANDBOX_TMP, "XDG_CACHE_HOME": str(cache)}
    writable = [_real(scratch), _real(harness)]
    if state_dir is not None:
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        writable.append(_real(state_dir))
    if access == "write":
        git_root, git_env = private_git(run, ws)
        writable.insert(0, str(ws))
        writable.append(_real(git_root))
        contained.update(git_env)
    else:
        contained.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(cache / "pycache")})
    readonly, protected = _git_metadata(ws)
    home = home if home is not None else os.path.expanduser("~")
    if net_dir:
        net_dir = _real(net_dir)
        os.makedirs(os.path.join(net_dir, NET_SHIM), mode=0o700, exist_ok=True)
    needed = [("the workspace", str(ws)), ("the project", _real(project)), ("the home directory", _real(home)),
              ("this run's directory", _real(run)), ("this run's scratch directory", _real(scratch))]
    needed += [("the role's harness state", _real(state_dir))] if state_dir is not None else []
    needed += [(w, p) for w, p in _guarded(ws, project=project, runs=runs, bridge_dir=bridge_dir, masks=(), host=(),
                                           net_dir=net_dir) if w != _SHARED_TMP]
    roots = []
    for raw, path in operator_roots(cfg):
        if not os.path.isdir(path):
            raise ContainmentUnavailable(f"policy containment.writable path {raw!r} is not an existing directory")
        roots.append((raw, path))
    # the run's own tree, where a secret cannot be left out of its directory (a policy root that holds a mask is
    # refused below: CS-4 addendum 7, ruling 2)
    plan = _mask_plan(home, list(cfg.get("hide") or []), env, needed, tuple(writable),
                      named_extra=client_cert.mask_entries(cfg.get("network")))
    _refuse_masks(plan.refused, home)
    # The project's `.env` files, in place in every layout, as every layout shows the project: one bind of the empty
    # file each, no directory emptied and refilled (the review of #592).
    # A `.env` link's target is never masked where it is what a run needs (the operator's ruling of 2026-11-27).
    env_keep = tuple(dict.fromkeys((*readonly, *interpreter_binds(), _real(_aew_package()))))
    # the run's own directories, and the harness binary it starts: a `.env` link's target in the home directory is
    # never masked there (the quick check of #592 at 99082b59, m1)
    own: list[str] = [*env_keep, str(ws), *writable, _real(run), *((_real(runs),) if runs else ()), *_harness_binary()]
    env_needs = tuple(dict.fromkeys(own))
    scan = project_env_masks(project, env_keep, home=_real(home), needs=env_needs)
    covered = (*plan.dirs, *plan.left_out)
    env_dirs = _unmasked(plan.files, covered, scan.dirs)
    env_files = _unmasked(plan.files, covered, scan.files)
    hide_host = host_masks()
    secret = {**dict(plan.what), **dict.fromkeys(env_files, ENV_WHAT), **dict.fromkeys(env_dirs, ENV_DIR_WHAT)}
    guarded = _guarded(ws, project=project, runs=runs, bridge_dir=bridge_dir,
                       masks=tuple((p, secret[p]) for p in (*plan.dirs, *plan.files, *env_dirs, *env_files)),
                       host=hide_host, net_dir=net_dir, left_out=tuple((p, secret[p]) for p in plan.left_out))
    _refuse_env_roots(roots, (*((p, ENV_DIR_WHAT) for p in env_dirs), *((p, ENV_WHAT) for p in env_files)))
    operator = []
    for raw, path in roots:
        _refuse_unsafe_root(raw, path, guarded, workspaces=str(ws.parent))
        if access == "read" and _within(path, str(ws)):
            continue  # a reader's workspace is read-only whole: a root inside it is not bound (review of #231, m3)
        operator.append(path)
    writable += [p for p in operator if p not in writable]
    if access == "read":
        readonly.insert(0, str(ws))       # the workspace itself, re-bound read-only over any broader writable root
        protected.append(str(ws))
    aew_dir = os.path.join(_real(project), ".aew")
    if scope == "project" and access == "write" and os.path.isdir(aew_dir) and _within(aew_dir, str(ws)):
        # Ruling R-2, the Lead's alone (only the Lead writes a project scope): its writable tree holds the project, and
        # .aew is a read-only mount point in it, so the store's path cannot be renamed, replaced or removed (CB-07's
        # second clause), and .aew stays unwritable. Any other writable bind that reaches the store stays refused.
        readonly.append(aew_dir)
        protected.append(aew_dir)
    if bridge_dir:
        readonly.append(_real(bridge_dir))
    readonly += [p for p in interpreter_binds() if p not in readonly]  # the interpreter behind `aew`
    # AEW's own package and its import path: unwritable wherever they live, and the self-test checks it (the layout is
    # refused below where a writable bind reaches them)
    package = _aew_package()
    protected += [p for p in dict.fromkeys((_real(package), _real(os.path.dirname(package)))) if p not in protected]
    tool_fields = _tool_fields(run, tools, hide_host, readonly, protected)
    # a directory of its own, never a link to one: the copy's own path is what is bound (E161)
    skills_binds = ((_real(skills_dir),) if skills_dir is not None and os.path.isdir(skills_dir)
                    and not os.path.islink(skills_dir) else ())
    readonly += [p for p in skills_binds if p not in readonly]
    protected += [p for p in skills_binds if p not in protected]
    visible = [_real(project)] if os.path.isdir(project) else []
    local = Path(project) / ".aew" / "local"
    if local.parent.is_dir():  # made now, so a lock a host writer creates there later is hidden too (#231, m4)
        local.mkdir(exist_ok=True)
    hide_runs = [_real(local)] if local.is_dir() else []  # no .aew: not an AEW root, so no lock to hide
    if runs is not None and os.path.isdir(runs) and not any(_within(_real(runs), h) for h in hide_runs):
        hide_runs.append(_real(runs))
    if pack is not None and os.path.isfile(pack) and not os.path.islink(pack):  # its own path, never a link's target
        own_pack = _real(pack)
        readonly += [own_pack] if own_pack not in readonly else []
        protected += [own_pack] if own_pack not in protected else []
    layout = Layout(role=role, access=access, bwrap=bwrap, writable=tuple(writable), readonly=tuple(readonly),
                    visible=tuple(visible), hide_runs=tuple(hide_runs),
                    **_env_fields(plan.fields(), scan, writable), mask_file=str(mask),
                    project=_real(project) if os.path.isdir(project) else None, env_keep=env_keep,
                    env_home=_real(home), env_needs=env_needs,
                    operator_writable=tuple(operator),
                    protected=tuple(protected), env=contained, hide_host=hide_host,
                    run_exceptions=run_exceptions(network), display_files=display_files(home, env), network=network,
                    net_dir=net_dir, skills_binds=skills_binds, **tool_fields)
    layout = _bounded_env(layout)
    steps = order(layout)
    _refuse_store_binds(role, project, steps)
    _refuse_trusted_code(role, steps)
    _refuse_run_bind_backs(layout, project=_real(project), workspace=str(ws))
    bwrap_argv(layout, [], cwd=ws)  # the layout's own arguments, counted before any bubblewrap starts (addendum 9)
    return layout
