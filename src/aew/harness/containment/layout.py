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
* secret masks, the display's credentials among them, come after every bind and depend on the path's type: a
  directory is replaced by an empty tmpfs, a file by an empty read-only file (``/dev/null`` would do, but SELinux
  refuses a device node bound over a home file). One in a tree that is masked whole (``/tmp``, ``/run``, a runs mask)
  is hidden with its tree and not emitted, unless it lies in one of the layout's binds into that tree, such as a
  project under ``/run`` or ``/tmp`` (:func:`_hidden_with_its_tree`).

The claim is filesystem integrity, not confidentiality: apart from the masks, a contained process can read what
the operator's account can read.
"""

from __future__ import annotations

import os
import shutil
import sys
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
    hide_files: tuple[str, ...] = ()         # replaced by ``mask_file``
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
                "hidden": [*self.hide_host, *self.hide_runs, *self.hide_dirs, *self.hide_files],
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
    for flag, path in order(layout):
        out += [flag, path] if flag == "--tmpfs" else [flag, path, path]
    for path in layout.hide_dirs:  # after every bind; before the remounts, as a mask inside a bind-back may be there
        if not _hidden_with_its_tree(layout, path):
            out += ["--tmpfs", path]
    for path in layout.hide_files:
        if not _hidden_with_its_tree(layout, path):
            out += ["--ro-bind", layout.mask_file, path]
    for path in (*layout.hide_host, *layout.hide_runs):  # after the bind-backs into them, which keep their own flags
        out += ["--remount-ro", path]
    if cwd is not None:
        out += ["--chdir", os.fspath(cwd)]
    return [*out, "--", *argv]


def _hidden_with_its_tree(layout: Layout, path: str) -> bool:
    """Whether a secret at ``path`` is hidden already, with a tree masked whole (the sandbox's ``/tmp``, a host mask, a
    runs mask), so its own mask is not emitted: making its path in a read-only mask would fail. It is when it lies in
    such a tree and in none of the layout's binds inside that tree, which bring their part of the host back (a project
    under ``/run`` or ``/tmp``, its workspace, the run's own directories): there the secret is the host's file, and its
    mask is emitted like any other (review of #244, m1)."""
    binds = (*layout.visible, *layout.writable, *layout.readonly, *(p for p, _ in layout.run_exceptions))
    return any(_within(path, m) and not any(_within(path, b) and _within(b, m) and b != m for b in binds)
               for m in (SANDBOX_TMP, *layout.hide_host, *layout.hide_runs))


def order(layout: Layout) -> list[tuple[str, str]]:
    """:func:`bind_order` of everything ``layout`` binds and masks at a depth: the project, the writable binds, the
    read-only re-binds with the ``/run`` exceptions, the run's network directory, and the ``/run`` and runs masks."""
    net_writable, net_readonly = layout.net_binds()
    return bind_order((*layout.writable, *net_writable),
                      (*layout.readonly, *(p for p, _ in layout.run_exceptions), *net_readonly),
                      (*layout.hide_host, *layout.hide_runs), visible=layout.visible)


def for_check(layout: Layout, requested: str | None = None) -> Layout:
    """The layout a check of a contained run starts in (F28 §3.8, network containment design decision 3): the run's
    own, with no network unless the check's definition asks for the host's and the run's own policy gives the host's
    (equal to or stricter than the run, never wider). It never binds the run's network directory, so a check has no
    route to the relay or the egress proxy either."""
    network = SHARED if requested == SHARED and layout.network == SHARED else ISOLATED
    return replace(layout, network=network, net_dir=None)


# Within one depth: the project's visible bind first, so a role's writable bind of the same path wins (the Lead's R-2
# shape, CS-4); then writable binds; then read-only re-binds; then masks.
_RANK = {"visible": -1, "--bind": 0, "--ro-bind": 1, "--tmpfs": 2}


def bind_order(writable: tuple[str, ...] | list[str], readonly: tuple[str, ...] | list[str],
               hidden: tuple[str, ...] | list[str] = (), *,
               visible: tuple[str, ...] | list[str] = ()) -> list[tuple[str, str]]:
    """The project's visible binds and read-only re-binds (``--ro-bind``), the writable binds (``--bind``) and the masks
    of ``hide_host`` and ``hide_runs`` (``--tmpfs``) in the order bubblewrap applies them: by depth, ancestors first, so
    each holds for its subtree except where a deeper one says otherwise. On one path the mask comes last, after a
    re-bind, after a writable bind, after the visible bind. So no bind ever lands on a masked path after its mask
    (review of #231, m2): only deeper bind-backs come after it. A project under a masked tree (``/run/media/...``)
    stays visible for the same reason (CS-2; the Lead's approval, 2026-10-23). Otherwise the order within a depth is
    the layout's. The one owner of the order: ``bwrap_argv`` emits it and the store check
    (:func:`_refuse_store_binds`) reasons about it."""
    tagged = ([("visible", p) for p in visible] + [("--bind", p) for p in writable]
              + [("--ro-bind", p) for p in readonly] + [("--tmpfs", p) for p in hidden])
    ranked = sorted(tagged, key=lambda t: (len(Path(t[1]).parts), _RANK[t[0]]))
    return [("--ro-bind" if f == "visible" else f, p) for f, p in ranked]


def find_bwrap() -> str | None:
    found = shutil.which("bwrap")
    return os.path.realpath(found) if found else None


def _real(path: str | os.PathLike[str]) -> str:
    return os.path.realpath(os.fspath(path))


def _masks(home: str | None, extra: list[str],
           env: Mapping[str, str] | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Existing secret paths, split by type (a file cannot be masked by a tmpfs, nor a directory by /dev/null): the
    secrets and the display's credentials in ``home``, those the launching environment ``env`` names
    (:func:`_env_masks`; default: this process's), and the policy's ``extra``."""
    candidates = [os.path.join(home, p) for p in (*SECRET_DIRS, *SECRET_FILES, *DISPLAY_FILES)] if home else []
    candidates += _env_masks(_launching(home, env))
    candidates += [os.path.expanduser(p) for p in extra]
    dirs: list[str] = []
    files: list[str] = []
    for path in _prefixed_files(home):
        if path not in files:
            files.append(path)
    for raw in candidates:
        if not os.path.lexists(raw):
            continue
        path = _real(raw)
        target = dirs if os.path.isdir(path) else files if os.path.isfile(path) else None
        if target is not None and path not in target:
            target.append(path)
    return tuple(dirs), tuple(files)


def _launching(home: str | None, env: Mapping[str, str] | None) -> Mapping[str, str]:
    """The launching environment ``env`` (default: this process's), with ``home`` as its home directory where it
    names none."""
    env = os.environ if env is None else env
    return {"HOME": home, **env} if home else env


def _env_masks(env: Mapping[str, str]) -> list[str]:
    """Credential paths the launching environment names rather than the home directory: the file ``XAUTHORITY`` names
    (CB-04), git's credential cache and store-helper file under a custom ``XDG_CACHE_HOME`` or ``XDG_CONFIG_HOME``,
    and every place AEW's host side reads the operator's OpenCode from (``opencode.login.operator_masks``, their one
    owner: STG-05 CS-4, outcome 2, the Lead's view holds no operator credential). Read in the process that makes the
    layout: a run's supervisor, whose environment is the launching CLI's without AEW's own credentials
    (``harness_ops.supervisor_env``), or the CLI itself."""
    from aew.harness.opencode import login

    out = [env["XAUTHORITY"]] if env.get("XAUTHORITY") else []
    if env.get("XDG_CACHE_HOME"):
        out.append(os.path.join(env["XDG_CACHE_HOME"], "git", "credential"))
    if env.get("XDG_CONFIG_HOME"):
        out.append(os.path.join(env["XDG_CONFIG_HOME"], "git", "credentials"))
    out += [str(p) for p in login.operator_masks(env)]
    return [os.path.expanduser(p) for p in out]


def _refuse_masks_over_the_run(env: Mapping[str, str], needed: list[tuple[str, str]]) -> None:
    """A directory masked whole for the operator's OpenCode (:func:`_env_masks`) that is, or holds, something the
    run needs (``needed``: its workspace, the project, the home directory, AEW's own directories, the Python
    environment) would hide it: refused, naming what puts the directory there and the fix. Masking only the files in
    it would not do: the login database's sidecars appear beside it after the launch."""
    from aew.harness.opencode import login

    for directory, variable in login.operator_masks(env).items():
        if not os.path.isdir(directory):
            continue
        masked = _real(directory)
        held = [(what, path) for what, path in needed if _within(path, masked)]
        if held:
            what, path = held[0]
            where = f"{variable} puts" if variable else "by default, OpenCode keeps"
            fix = (f"point {variable} at a directory of its own, which holds nothing else, or unset it" if variable
                   else "keep the project and AEW outside it")
            raise ContainmentUnavailable(
                f"{where} the operator's OpenCode files in {masked}, which a contained run masks whole, and that "
                f"directory is or holds {what} ({path}), which the run needs; the launch is refused. To launch, "
                f"{fix}", directory=masked, variable=variable, holds=[{"what": w, "path": p} for w, p in held],
                reason="opencode_mask_holds_the_run")


def display_files(home: str | None, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The display's credential files present on this host (CB-04), resolved: the ones row 3 of the launch self-test
    must find unreadable from inside. Masked by :func:`_masks` with the other secrets."""
    env = os.environ if env is None else env
    candidates = [os.path.join(home, p) for p in DISPLAY_FILES] if home else []
    candidates += [env["XAUTHORITY"]] if env.get("XAUTHORITY") else []
    return tuple(dict.fromkeys(_real(p) for p in candidates if os.path.isfile(p)))


def _prefixed_files(home: str | None) -> list[str]:
    """Regular files directly in ``home`` named after a :data:`SECRET_FILE_PREFIXES` entry (not recursive; a
    directory with such a name is not a file and is left alone)."""
    if not home:
        return []
    try:
        with os.scandir(home) as it:
            names = sorted(e.name for e in it if e.name.startswith(SECRET_FILE_PREFIXES))
    except OSError:
        return []
    out = []
    for name in names:
        path = _real(os.path.join(home, name))
        if os.path.isfile(path):
            out.append(path)
    return out


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
             bridge_dir: str | None, masks: tuple[str, ...],
             host: tuple[str, ...] = (RUN,), net_dir: str | None = None) -> list[tuple[str, str]]:
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
    out += [("a masked secret", m) for m in masks]
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
        raise ContainmentUnavailable(
            f"policy containment.writable root {raw!r} ({root}) would let every contained run write {listed}. "
            "Containment protects these, so this root is refused and runs cannot launch. List a narrower directory "
            "that holds none of them instead, such as a build output or cache directory (for example "
            "<project>/build, or ~/.cache/<tool>), in containment.writable in the execution policy.",
            root=raw, resolved=root, exposes=[{"what": w, "path": p} for w, p in exposed])


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
    hide_dirs, hide_files = _masks(home, list(cfg.get("hide") or []), env)
    hide_host = host_masks()
    if net_dir:
        net_dir = _real(net_dir)
        os.makedirs(os.path.join(net_dir, NET_SHIM), mode=0o700, exist_ok=True)
    guarded = _guarded(ws, project=project, runs=runs, bridge_dir=bridge_dir, masks=(*hide_dirs, *hide_files),
                       host=hide_host, net_dir=net_dir)
    needed = [("the workspace", str(ws)), ("the project", _real(project)), ("the home directory", _real(home)),
              ("this run's directory", _real(run)), ("this run's scratch directory", _real(scratch))]
    needed += [("the role's harness state", _real(state_dir))] if state_dir is not None else []
    _refuse_masks_over_the_run(_launching(home, env), needed + [(w, p) for w, p in _guarded(
        ws, project=project, runs=runs, bridge_dir=bridge_dir, masks=(), host=(), net_dir=net_dir)
        if w != _SHARED_TMP])
    operator = []
    for raw in cfg.get("writable") or []:
        path = _real(os.path.expanduser(raw))
        if not os.path.isdir(path):
            raise ContainmentUnavailable(f"policy containment.writable path {raw!r} is not an existing directory")
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
                    visible=tuple(visible), hide_runs=tuple(hide_runs), hide_dirs=hide_dirs, hide_files=hide_files,
                    mask_file=str(mask), operator_writable=tuple(operator), protected=tuple(protected),
                    env=contained, hide_host=hide_host, run_exceptions=run_exceptions(network),
                    display_files=display_files(home, env), network=network, net_dir=net_dir)
    _refuse_store_binds(role, project, order(layout))
    _refuse_run_bind_backs(layout, project=_real(project), workspace=str(ws))
    return layout
