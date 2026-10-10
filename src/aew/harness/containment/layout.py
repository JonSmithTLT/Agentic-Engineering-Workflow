"""One run's sandbox, described as data (F2; ADR-0009 amendment, M4-B).

A :class:`Layout` says what a contained process may write. Everything else is the host as read-only:

* the host root is bound read-only; ``/dev``, ``/proc`` and ``/tmp`` are private to the sandbox; the project is bound
  read-only too, so it stays visible wherever it lives (even under ``/tmp``);
* every harness run's directory is hidden behind an empty tmpfs, and only this run's own directories are bound back:
  one run never reads another's harness state (its bridge key, its transcript);
* PID, IPC and UTS namespaces are private; the network namespace is shared (the harness server listens on
  ``127.0.0.1`` and the provider is remote), so nothing here claims network isolation;
* the writable roots come from the role (:data:`WORKSPACE_ACCESS`, exhaustive: a role without an entry has no
  layout and its launch is refused), plus the run's own scratch, harness state and private git state, plus any
  path the operator's execution policy adds (recorded on the run's label);
* read-only re-binds come after every writable bind, so a broad writable root can never reopen what they protect:
  the repository's git metadata, the workspace's ``.git`` pointer, the bridge directory;
* secret masks come last and depend on the path's type: a directory is replaced by an empty tmpfs, a file by an
  empty read-only file (``/dev/null`` would do, but SELinux refuses a device node bound over a home file).

The claim is filesystem integrity, not confidentiality: apart from the masks, a contained process can read what
the operator's account can read.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.errors import ContainmentUnavailable

# What each archetype may do to the workspace (or observation) it was dispatched for. Exhaustive by design: an
# archetype without an entry (the Lead, or a new archetype nobody classified) cannot be contained, so it is refused.
WORKSPACE_ACCESS: dict[str, str] = {
    "implementer": "write",
    "reviewer": "read", "verifier": "read",
    "investigator": "read", "researcher": "read", "planner": "read",
    "frontier_advisor": "read",
}
# The scopes in which an archetype may hold write access. Anything else fails closed.
WRITE_SCOPES = frozenset({"ticket"})

# Credentials commonly kept in a home directory. Masked when present; a policy may add more.
SECRET_DIRS = (".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store", ".config/gh",
               ".config/gcloud",
               # agent tools' own sign-ins and session stores (AEW gives a run's harness private XDG directories)
               ".local/share/opencode", ".config/opencode", ".codex", ".claude",
               ".config/anthropic")  # provider credential/config location
SECRET_FILES = (".netrc", ".git-credentials", ".pgpass", ".pypirc", ".npmrc",
                ".claude.json")  # provider credential/config location
# Copies kept beside a secret file under a suffixed name (backups and the like): every regular file directly in the
# home directory whose name starts with one of these is masked too. Only the home directory itself is listed.
SECRET_FILE_PREFIXES = (".claude.json.",)  # provider credential/config location

PRIVATE_GIT = "git"  # <run dir>/git: the run's private index and object store
MASK_FILE = ".aew-mask"
# Inside the sandbox /tmp is a fresh, private tmpfs: nothing else shares it, so the usual shared-/tmp risks (S108)
# do not apply. The bridge socket lives under the host's /tmp for the same reason (bridge.private_address).
SANDBOX_TMP = "/tmp"  # noqa: S108  # <run dir>/.aew-mask: the empty file bound over file secrets


@dataclass(frozen=True)
class Layout:
    """The sandbox of one run (and of the checks it runs). Pure data: :func:`bwrap_argv` turns it into argv."""

    role: str
    access: str                              # "write" or "read": the role's access to its workspace
    bwrap: str                               # absolute path of the bubblewrap binary
    writable: tuple[str, ...]                # read-write binds, in order
    readonly: tuple[str, ...]                # read-only re-binds, after every writable bind
    visible: tuple[str, ...] = ()            # read-only binds first: the project, wherever it lives
    hide_runs: tuple[str, ...] = ()          # empty tmpfs before the writable binds: every run's directory
    hide_dirs: tuple[str, ...] = ()          # replaced by an empty tmpfs
    hide_files: tuple[str, ...] = ()         # replaced by ``mask_file``
    mask_file: str = "/dev/null"             # an empty read-only file
    operator_writable: tuple[str, ...] = ()  # the policy's extra writable roots (also in ``writable``)
    protected: tuple[str, ...] = ()          # paths the launch self-test must find unwritable
    env: dict[str, str] = field(default_factory=dict)  # what contained processes need set (private git, caches)

    def describe(self) -> dict[str, Any]:
        return {"role": self.role, "workspace_access": self.access, "writable": list(self.writable),
                "readonly": list(self.readonly), "hidden": [*self.hide_runs, *self.hide_dirs, *self.hide_files],
                "operator_writable": list(self.operator_writable)}


def bwrap_argv(layout: Layout, argv: list[str], *, cwd: str | os.PathLike[str] | None = None) -> list[str]:
    """The bubblewrap command that runs ``argv`` inside ``layout``. Only flags bubblewrap 0.4.0 (EL8) has."""
    out = [layout.bwrap, "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
           "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", SANDBOX_TMP]
    for path in layout.visible:
        out += ["--ro-bind", path, path]
    for path in layout.hide_runs:
        out += ["--tmpfs", path]
    for path in layout.writable:
        out += ["--bind", path, path]
    for path in layout.readonly:
        out += ["--ro-bind", path, path]
    for path in layout.hide_dirs:
        out += ["--tmpfs", path]
    for path in layout.hide_files:
        out += ["--ro-bind", layout.mask_file, path]
    if cwd is not None:
        out += ["--chdir", os.fspath(cwd)]
    return [*out, "--", *argv]


def find_bwrap() -> str | None:
    found = shutil.which("bwrap")
    return os.path.realpath(found) if found else None


def _real(path: str | os.PathLike[str]) -> str:
    return os.path.realpath(os.fspath(path))


def _masks(home: str | None, extra: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Existing secret paths, split by type (a file cannot be masked by a tmpfs, nor a directory by /dev/null)."""
    candidates = [os.path.join(home, p) for p in (*SECRET_DIRS, *SECRET_FILES)] if home else []
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
             bridge_dir: str | None, masks: tuple[str, ...]) -> list[tuple[str, str]]:
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
    for prefix in {sys.prefix, sys.base_prefix}:
        if prefix:
            out.append(("the Python environment AEW runs from", _real(prefix)))
    out += [("a masked secret", m) for m in masks]
    return out


_SHARED_TMP = "the shared temporary directory, where every run's bridge socket lives"


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


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


def for_run(*, role: str, scope: str, workspace: str | os.PathLike[str], run_dir: str | os.PathLike[str],
            scratch: str | os.PathLike[str], bridge_dir: str | None, policy: dict[str, Any] | None,
            home: str | None = None, project: str | os.PathLike[str] | None = None,
            runs: str | os.PathLike[str] | None = None) -> Layout:
    """The layout of a run of ``role`` in ``scope``. Creates the run's private directories (and, for a writing
    role, its private git state). Raises ``ContainmentUnavailable`` when the role has no layout or bubblewrap is
    missing. ``project`` is the authoritative project root (bound read-only so it stays visible); ``runs`` is the
    directory holding every run's directory (hidden, with only this run's own directories bound back)."""
    access = WORKSPACE_ACCESS.get(role)
    if access is None:
        raise ContainmentUnavailable(f"role {role!r} has no containment layout; its runs are refused", role=role)
    if access == "write" and scope not in WRITE_SCOPES:
        raise ContainmentUnavailable(f"a {role} may write only a Ticket workspace, not a {scope!r} scope",
                                     role=role, scope=scope)
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
    env = {"TMPDIR": SANDBOX_TMP, "XDG_CACHE_HOME": str(cache)}
    writable = [_real(scratch), _real(harness)]
    if access == "write":
        git_root, git_env = private_git(run, ws)
        writable.insert(0, str(ws))
        writable.append(_real(git_root))
        env.update(git_env)
    else:
        env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(cache / "pycache")})
    readonly, protected = _git_metadata(ws)
    hide_dirs, hide_files = _masks(home if home is not None else os.path.expanduser("~"),
                                   list(cfg.get("hide") or []))
    guarded = _guarded(ws, project=project, runs=runs, bridge_dir=bridge_dir, masks=(*hide_dirs, *hide_files))
    operator = []
    for raw in cfg.get("writable") or []:
        path = _real(os.path.expanduser(raw))
        if not os.path.isdir(path):
            raise ContainmentUnavailable(f"policy containment.writable path {raw!r} is not an existing directory")
        _refuse_unsafe_root(raw, path, guarded, workspaces=str(ws.parent))
        operator.append(path)
    writable += [p for p in operator if p not in writable]
    if access == "read":
        readonly.insert(0, str(ws))       # the workspace itself, re-bound read-only over any broad writable root
        protected.append(str(ws))
    if bridge_dir:
        readonly.append(_real(bridge_dir))
    for prefix in {sys.prefix, sys.base_prefix}:  # the interpreter behind `aew`, wherever it lives
        if prefix and os.path.isdir(prefix) and _real(prefix) not in readonly:
            readonly.append(_real(prefix))
    visible = [_real(project)] if project is not None and os.path.isdir(project) else []
    hide_runs = [_real(runs)] if runs is not None and os.path.isdir(runs) else []
    return Layout(role=role, access=access, bwrap=bwrap, writable=tuple(writable), readonly=tuple(readonly),
                  visible=tuple(visible), hide_runs=tuple(hide_runs), hide_dirs=hide_dirs, hide_files=hide_files,
                  mask_file=str(mask), operator_writable=tuple(operator), protected=tuple(protected), env=env)
