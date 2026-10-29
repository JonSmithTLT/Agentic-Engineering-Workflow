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
  binds into that tree, such as a project under ``/run`` or ``/tmp`` (:func:`_hidden_with_its_tree`).

The claim is filesystem integrity, not confidentiality: apart from the masks, a contained process can read what
the operator's account can read.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from aew.errors import ContainmentUnavailable

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


def host_masks() -> tuple[str, ...]:
    """The host's trees masked whole (CB-03): ``/run``; ``/var/run`` where it is a directory of its own rather than
    the usual link to ``/run``; and the GSS-API proxy's directory where there is one (:data:`GSSPROXY`). Host facts,
    read when the layout is made."""
    out = [RUN]
    if os.path.isdir(VAR_RUN) and not os.path.islink(VAR_RUN):
        out.append(VAR_RUN)
    if os.path.isdir(GSSPROXY) and not os.path.islink(GSSPROXY):
        out.append(GSSPROXY)
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

    def describe(self) -> dict[str, Any]:
        return {"role": self.role, "workspace_access": self.access, "writable": list(self.writable),
                "readonly": list(self.readonly),
                "hidden": [*self.hide_host, *self.hide_runs, *self.hide_dirs, *self.hide_files, *self.left_out],
                "left_out_of": list(self.left_out_of),
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


def bwrap_argv(layout: Layout, argv: list[str], *, cwd: str | os.PathLike[str] | None = None) -> list[str]:
    """The bubblewrap command that runs ``argv`` inside ``layout``. Only flags bubblewrap 0.4.0 (EL8) has."""
    # --new-session: no controlling terminal, so TIOCSTI has no terminal it would accept (CB-05; bubblewrap's answer to
    # CVE-2017-5226). bubblewrap's own processes stay in the caller's process group, so killing it still ends the run.
    out = [layout.bwrap, "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
           *(["--unshare-net"] if layout.private_network else []),  # F28 §3.2: its own loopback only
           "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", SANDBOX_TMP]
    for name in DISPLAY_ENV:
        out += ["--unsetenv", name]
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
    out = [*out, "--", *argv]
    _refuse_too_many_arguments(layout, out)  # counted before bubblewrap starts (CS-4 addendum 9)
    return out


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
    step = (f"move entries out of {held[0][0]} into a subdirectory, so it has fewer to put back" if held else
            "list fewer secret paths or writable roots")
    raise ContainmentUnavailable(
        f"this launch needs {count} arguments for bubblewrap, more than the {BWRAP_MAX_ARGS} bubblewrap 0.4.0 takes: "
        "each entry of a directory a secret is left out of is put back on its own, with three, and the directories "
        f"whose entries are put back are {listed}; the launch is refused before bubblewrap starts. To launch, {step}. "
        "This applies to every contained launch, workers included",
        arguments=count, limit=BWRAP_MAX_ARGS, put_back=dict(held), reason="bwrap_argument_limit")


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
    own = {*layout.visible, *writable, *readonly, *hidden, *layout.hide_dirs}

    def back(path: str) -> bool:
        return os.path.dirname(path) in masked and path not in own

    return bind_order(writable, readonly, hidden, visible=layout.visible,
                      put_back=[p for p in layout.put_back if back(p)],
                      links=[p for p, _ in layout.put_back_links if back(p)])


def for_check(layout: Layout, requested: str | None = None) -> Layout:
    """The layout a check of a contained run starts in (F28 §3.8, network containment design decision 3): the run's
    own, with no network unless the check's definition asks for the host's and the run's own policy gives the host's
    (equal to or stricter than the run, never wider). It never binds the run's network directory, so a check has no
    route to the relay or the egress proxy either."""
    network = SHARED if requested == SHARED and layout.network == SHARED else ISOLATED
    return replace(layout, network=network, net_dir=None)


# Within one depth: an entry put back into a directory a secret is left out of first, so a bind of the layout's own
# there wins; then the project's visible bind, so a role's writable bind of the same path wins (the Lead's R-2 shape,
# CS-4); then writable binds; then read-only re-binds; then masks.
_RANK = {"put_back": -3, "--symlink": -3, "visible": -1, "--bind": 0, "--ro-bind": 1, "--tmpfs": 2}


def bind_order(writable: tuple[str, ...] | list[str], readonly: tuple[str, ...] | list[str],
               hidden: tuple[str, ...] | list[str] = (), *,
               visible: tuple[str, ...] | list[str] = (), put_back: tuple[str, ...] | list[str] = (),
               links: tuple[str, ...] | list[str] = ()) -> list[tuple[str, str]]:
    """The project's visible binds and read-only re-binds (``--ro-bind``), the writable binds (``--bind``) and the masks
    of ``hide_host`` and ``hide_runs`` (``--tmpfs``) in the order bubblewrap applies them: by depth, ancestors first, so
    each holds for its subtree except where a deeper one says otherwise. On one path the mask comes last, after a
    re-bind, after a writable bind, after the visible bind. So no bind ever lands on a masked path after its mask
    (review of #231, m2): only deeper bind-backs come after it. A project under a masked tree (``/run/media/...``)
    stays visible for the same reason (CS-2; the Lead's approval, 2026-10-23). Otherwise the order within a depth is
    the layout's. An entry put back into a directory a secret is left out of (``put_back``, ``links``) comes a level
    below that directory's mask, as ``--ro-bind-try`` (it may have gone since the layout was made) or ``--symlink``;
    never as ``--ro-bind``, which the store check counts. The one owner of the order: ``bwrap_argv`` emits it and the
    store check (:func:`_refuse_store_binds`) reasons about it."""
    tagged = ([("put_back", p) for p in put_back] + [("--symlink", p) for p in links]
              + [("visible", p) for p in visible] + [("--bind", p) for p in writable]
              + [("--ro-bind", p) for p in readonly] + [("--tmpfs", p) for p in hidden])
    ranked = sorted(tagged, key=lambda t: (len(Path(t[1]).parts), _RANK[t[0]]))
    flags = {"visible": "--ro-bind", "put_back": "--ro-bind-try"}
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


HOME_LIST = "the home directory's secret paths"  # what names a path of SECRET_DIRS, SECRET_FILES or DISPLAY_FILES
POLICY_HIDE = "containment.hide"


def _mask_plan(home: str | None, extra: list[str], env: Mapping[str, str] | None, needed: list[tuple[str, str]],
               written: tuple[str, ...] | list[str] = ()) -> MaskPlan:
    """Every secret path, masked by its type (STG-05 CS-4, addenda 6 and 7), for every role: the secrets and the
    display's credentials in ``home``, those the launching environment ``env`` names (default: this process's), the
    policy's ``extra`` (:func:`_named`), and what the links in the directories masked whole point at (:func:`_linked`).

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
        if os.path.isdir(path):
            real = _real(path)
            by.setdefault(real, f"the link {path}" if os.path.islink(path) else source)
            what.setdefault(real, f"what {path} links to" if os.path.islink(path) else secret)
            dirs.append(real)
            return
        entries = _left_out(path)
        for i, entry in enumerate(entries):  # the first as named, each other through the link before it
            by.setdefault(entry, source if i == 0 else f"the link {entries[i - 1]}")
            what.setdefault(entry, secret if i == 0 else f"what {entries[i - 1]} links to")
        leave.extend(entries)

    for raw, source, secret in _named(home, extra, launching):
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


def _named(home: str | None, extra: list[str], env: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """Every named secret path, absolute and as named, with what names it and what it is: :data:`SECRET_DIRS`,
    :data:`SECRET_FILES` and :data:`DISPLAY_FILES` in ``home`` (:data:`SECRET_WHAT`) and the copies beside a secret file
    there (:func:`_prefixed_files`), the paths the launching environment ``env`` names (:func:`_env_masks`), and the
    policy's ``extra``."""
    out = [(os.path.join(home, p), HOME_LIST, SECRET_WHAT[p]) for p in (*SECRET_DIRS, *SECRET_FILES, *DISPLAY_FILES)] \
        if home else []
    out += [(p, HOME_LIST, f"a copy of {SECRET_WHAT['.claude.json']}") for p in _prefixed_files(home)]
    out += [*_env_masks(env), *((os.path.expanduser(p), POLICY_HIDE, "a containment.hide entry") for p in extra)]
    seen: dict[str, tuple[str, str]] = {}
    for path, source, secret in out:
        seen.setdefault(os.path.abspath(path), (source, secret))
    return [(path, source, secret) for path, (source, secret) in seen.items()]


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
    (CB-04), git's credential cache and store-helper file under a custom ``XDG_CACHE_HOME`` or ``XDG_CONFIG_HOME``,
    and every place AEW's host side reads the operator's OpenCode from (``opencode.login.operator_masks`` and
    ``operator_files``, their one owner: STG-05 CS-4, outcome 2, the Lead's view holds no operator credential). Read in
    the process that makes the layout: a run's supervisor, whose environment is the launching CLI's without AEW's own
    credentials (``harness_ops.supervisor_env``), or the CLI itself."""
    from aew.harness.opencode import login

    out = [(env["XAUTHORITY"], "XAUTHORITY", SECRET_WHAT[".Xauthority"])] if env.get("XAUTHORITY") else []
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


def for_run(*, role: str, scope: str, workspace: str | os.PathLike[str], run_dir: str | os.PathLike[str],
            scratch: str | os.PathLike[str], bridge_dir: str | None, policy: dict[str, Any] | None,
            project: str | os.PathLike[str], home: str | None = None,
            runs: str | os.PathLike[str] | None = None, env: Mapping[str, str] | None = None,
            network: str = SHARED, net_dir: str | None = None,
            state_dir: str | os.PathLike[str] | None = None) -> Layout:
    """The layout of a run of ``role`` in ``scope``. Creates the run's private directories (and, for a writing
    role, its private git state). Raises ``ContainmentUnavailable`` when the role has no layout, bubblewrap is
    missing, or a bind would reach the store's path. ``project`` is the authoritative project root (bound read-only
    so it stays visible; its ``.aew/local`` is hidden, and its store checked against every writable bind); ``runs``
    is the directory holding every run's directory (hidden too, with only this run's own directories bound back).
    ``env`` is the launching environment, for the credential paths it names (default: this process's). ``network``
    is the run's network mode (:data:`NETWORK_MODES`) and ``net_dir`` the directory of its network sockets
    (``aew.harness.containment.netns``), with its :data:`NET_SHIM` subdirectory made here. ``state_dir`` is the role's
    own harness state that outlives one run (the Lead's OpenCode state, kept per project: STG-05 CS-4 addendum 1),
    made here and bound back writable like the run's own directories."""
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
    for raw in cfg.get("writable") or []:
        path = _real(os.path.expanduser(raw))
        if not os.path.isdir(path):
            raise ContainmentUnavailable(f"policy containment.writable path {raw!r} is not an existing directory")
        roots.append((raw, path))
    # the run's own tree, where a secret cannot be left out of its directory (a policy root that holds a mask is
    # refused below: CS-4 addendum 7, ruling 2)
    plan = _mask_plan(home, list(cfg.get("hide") or []), env, needed, tuple(writable))
    _refuse_masks(plan.refused, home)
    hide_host = host_masks()
    secret = dict(plan.what)
    guarded = _guarded(ws, project=project, runs=runs, bridge_dir=bridge_dir,
                       masks=tuple((p, secret[p]) for p in (*plan.dirs, *plan.files)), host=hide_host, net_dir=net_dir,
                       left_out=tuple((p, secret[p]) for p in plan.left_out))
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
    for prefix in {sys.prefix, sys.base_prefix}:  # the interpreter behind `aew`, wherever it lives
        if prefix and os.path.isdir(prefix) and _real(prefix) not in readonly:
            readonly.append(_real(prefix))
    visible = [_real(project)] if os.path.isdir(project) else []
    local = Path(project) / ".aew" / "local"
    if local.parent.is_dir():  # made now, so a lock a host writer creates there later is hidden too (#231, m4)
        local.mkdir(exist_ok=True)
    hide_runs = [_real(local)] if local.is_dir() else []  # no .aew: not an AEW root, so no lock to hide
    if runs is not None and os.path.isdir(runs) and not any(_within(_real(runs), h) for h in hide_runs):
        hide_runs.append(_real(runs))
    layout = Layout(role=role, access=access, bwrap=bwrap, writable=tuple(writable), readonly=tuple(readonly),
                    visible=tuple(visible), hide_runs=tuple(hide_runs), **plan.fields(), mask_file=str(mask),
                    operator_writable=tuple(operator),
                    protected=tuple(protected), env=contained, hide_host=hide_host,
                    run_exceptions=run_exceptions(network), display_files=display_files(home, env), network=network,
                    net_dir=net_dir)
    _refuse_store_binds(role, project, order(layout))
    _refuse_run_bind_backs(layout, project=_real(project), workspace=str(ws))
    bwrap_argv(layout, [], cwd=ws)  # the layout's own arguments, counted before any bubblewrap starts (addendum 9)
    return layout
