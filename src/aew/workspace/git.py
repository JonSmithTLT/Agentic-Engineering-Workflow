"""Thin, explicit wrapper over the git CLI (the guaranteed provider; git >= 2.31).

Every call runs with the programs git configuration can name switched off: filter, diff and merge drivers, hooks,
fsmonitor and signing. AEW's git reads and commits files an agent wrote, and a configured command can point at a file
an agent can edit, so running it would execute agent-controlled code outside any sandbox (M4-B review). The operator
trusts a driver by name in execution policy (``containment.trusted_git_drivers``), for an installed program such as
git-lfs; a dispatch whose base needs an untrusted filter is refused (``untrusted_filters``).
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from aew import profile
from aew.errors import GitError, IllegalTransition, NotFound, UsageError
from aew.harness.contract import scrub_credentials

AEW_IDENTITY = {"name": "AEW Engine", "email": "aew-engine@invalid"}

DRIVER_KEY = re.compile(r"^(filter|diff|merge)\.(.+)\.(clean|smudge|process|required|command|textconv|driver)$")
# What each driver key becomes when its driver is not trusted: no command (git then passes content through), and a
# merge driver that always reports a conflict, so a custom merge falls back to the Lead rather than to a guess.
NEUTRAL = {"clean": "", "smudge": "", "process": "", "required": "false", "command": "", "textconv": "",
           "driver": "false"}
DIFF_COMMANDS = {"diff", "log", "show"}
# githooks(5) recommends clearing the names printed by `git rev-parse --local-env-vars`
# before running Git in a different repository. Pin the union across supported Git versions (2.31 and newer).
LOCAL_ENV_VARS = frozenset({
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS",
    "GIT_DIR", "GIT_GRAFT_FILE", "GIT_IMPLICIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_INTERNAL_SUPER_PREFIX",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_OBJECT_DIRECTORY", "GIT_PREFIX", "GIT_REPLACE_REF_BASE", "GIT_SHALLOW_FILE", "GIT_WORK_TREE",
})
COUNTED_CONFIG = re.compile(r"GIT_CONFIG_(KEY|VALUE)_\d+\Z")

_trusted: frozenset[str] = frozenset()
_drivers: dict[str, dict[str, Any]] = {}
_no_hooks: str | None = None


def trust_drivers(names: Iterable[str]) -> None:
    """The driver names the operator trusts (execution policy); every other configured driver is switched off."""
    global _trusted
    _trusted = frozenset(names)


def trusted_drivers() -> frozenset[str]:
    return _trusted


# The environment git reads configuration from: part of the cache key (a call may carry its own GIT_CONFIG_*).
_CONFIG_ENV = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "PREFIX", "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE")
INCLUDE_KEY = re.compile(r"^(include|includeif\..*)\.path$", re.IGNORECASE)


def _config_env_key(env: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, v) for k, v in env.items() if k in _CONFIG_ENV or k.startswith("GIT_CONFIG")))


def _base_files(cwd: Path, env: dict[str, str]) -> list[str]:
    """The configuration files git reads whatever they contain: system, global, repository and worktree."""
    home = Path(env.get("HOME") or Path.home())
    xdg = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    files = [env.get("GIT_CONFIG_GLOBAL") or str(home / ".gitconfig"), str(xdg / "git" / "config"),
             env.get("GIT_CONFIG_SYSTEM") or "/etc/gitconfig"]
    proc = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir", "--git-dir"], cwd=cwd,
                          capture_output=True, env=env)
    if proc.returncode == 0:
        common, gitdir = (proc.stdout.decode("utf-8", "replace").splitlines() + ["", ""])[:2]
        files += [str(Path(common) / "config"), str(Path(gitdir) / "config.worktree"), str(Path(gitdir) / "HEAD")]
    return files


def _signature(files: list[str]) -> tuple[Any, ...]:
    out: list[Any] = []
    for f in files:
        try:
            st = os.stat(f)
            out.append((f, st.st_mtime_ns, st.st_size, st.st_ino))
        except OSError:
            out.append((f, None))
    return tuple(out)


def _include_target(value: str, origin: Path, env: dict[str, str]) -> str | None:
    """Where an include points (git's rules: ``~/`` is home, a relative path is relative to the including file's
    directory). None when it cannot be resolved here (``%(prefix)/``): the caller then never caches."""
    if "%(" in value:
        return None
    if value.startswith("~/") or value == "~":
        return str(Path(env.get("HOME") or Path.home()) / value[2:])
    path = Path(value)
    return str(path if path.is_absolute() else origin.parent / path)


def configured_drivers(cwd: Path, env: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Every filter, diff and merge driver key in the effective configuration at ``cwd``, with the file defining it.

    Cached per directory and configuration environment, and re-read whenever any input of the last read changes:
    every file git read (whatever keys it holds), every include's target (even one that is empty or missing), the
    system, global, repository and worktree files, and the worktree's HEAD (an ``includeIf "onbranch:..."`` follows
    it). A read whose inputs were not all known before it ran is not cached, and neither is one with an include this
    cannot resolve: the next call reads again (M4-B review)."""
    full = _env(env)
    key = f"{cwd}\0{_config_env_key(full)}"
    cached = _drivers.get(key)
    if cached is not None and cached["signature"] is not None and _signature(cached["files"]) == cached["signature"]:
        return cached["found"]
    try:
        known = sorted(set(_base_files(cwd, full)) | set(cached["files"] if cached else []))
        before = _signature(known)  # taken before reading, so a change made during the read is seen next time
        proc = subprocess.run(["git", "config", "--list", "--show-origin", "-z"], cwd=cwd, capture_output=True,
                              env=full)
    except OSError:  # not a directory (yet): git itself reports it
        return []
    found: list[dict[str, str]] = []
    needed: set[str] = set()
    resolvable = True
    items = proc.stdout.decode("utf-8", "replace").split("\0") if proc.returncode == 0 else []
    for origin, entry in zip(items[0::2], items[1::2], strict=False):
        name, _, value = entry.partition("\n")
        raw = origin.removeprefix("file:")
        where = Path(raw) if Path(raw).is_absolute() else cwd / raw  # the repository's own config is relative
        if origin.startswith("file:"):
            needed.add(str(where))
        if INCLUDE_KEY.match(name):
            target = _include_target(value, where, full)
            if target is None:
                resolvable = False
            else:
                needed.add(target)
        m = DRIVER_KEY.match(name)
        if m:
            found.append({"kind": m.group(1), "driver": m.group(2), "key": m.group(3), "config": name,
                          "value": value, "origin": where.as_posix()})
    complete = resolvable and proc.returncode == 0 and needed <= set(known)
    _drivers[key] = {"found": found, "files": sorted(set(known) | needed),
                     "signature": before if complete else None}
    return found


def _hooks_off() -> str:
    """An empty directory private to this process, for ``core.hooksPath`` (a shared path could be planted)."""
    global _no_hooks
    if _no_hooks is None:
        _no_hooks = tempfile.mkdtemp(prefix="aew-no-hooks-")
        atexit.register(shutil.rmtree, _no_hooks, True)
    return _no_hooks


def safe_config(cwd: Path, env: dict[str, str] | None = None) -> list[str]:
    """``-c`` arguments that keep git from running any configured program but the trusted drivers."""
    pairs = [("core.fsmonitor", "false"), ("core.hooksPath", _hooks_off()), ("diff.external", ""),
             ("commit.gpgSign", "false"), ("tag.gpgSign", "false")]
    pairs += [(d["config"], NEUTRAL[d["key"]]) for d in configured_drivers(cwd, env) if d["driver"] not in _trusted]
    return [arg for k, v in pairs for arg in ("-c", f"{k}={v}")]


def _env(env: dict[str, str] | None) -> dict[str, str]:
    full_env = scrub_credentials(dict(os.environ))  # git and its hooks never see an AEW credential (ADR-0009)
    for name in tuple(full_env):
        if name in LOCAL_ENV_VARS or COUNTED_CONFIG.fullmatch(name):
            del full_env[name]
    full_env["GIT_TERMINAL_PROMPT"] = "0"
    full_env["LC_ALL"] = "C"
    if env:
        full_env.update(env)
    return full_env


def git(
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
    input: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if not Path(cwd).is_dir():  # a worktree removed outside AEW: an AEW error, not a traceback (area 4 F3)
        raise GitError(f"git {args[0] if args else ''}: the directory {cwd} does not exist (removed outside AEW?)",
                       cwd=str(cwd))
    full_env = _env(env)
    profile.count("git")
    profile.count(f"git:{args[0] if args else ''}")
    if args and args[0] in DIFF_COMMANDS:
        args = (args[0], "--no-ext-diff", "--no-textconv", *args[1:])
    with profile.phase("git"):
        proc = subprocess.run(["git", *safe_config(cwd, env), *args], cwd=cwd, env=full_env, capture_output=True,
                              input=input)
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode})",
            cwd=str(cwd),
            stderr=proc.stderr.decode("utf-8", "replace").strip(),
        )
    return proc


def out(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    return git(*args, cwd=cwd, env=env).stdout.decode("utf-8", "replace").strip()


def ok(*args: str, cwd: Path) -> bool:
    return git(*args, cwd=cwd, check=False).returncode == 0


def rev_parse(ref: str, *, cwd: Path) -> str | None:
    proc = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=cwd, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip() or None


def is_ancestor(ancestor: str, descendant: str, *, cwd: Path) -> bool:
    proc = git("merge-base", "--is-ancestor", ancestor, descendant, cwd=cwd, check=False)
    if proc.returncode not in (0, 1):
        raise GitError("merge-base --is-ancestor failed", stderr=proc.stderr.decode().strip())
    return proc.returncode == 0


def toplevel(cwd: Path) -> Path | None:
    proc = git("rev-parse", "--show-toplevel", cwd=cwd, check=False)
    return Path(proc.stdout.decode().strip()) if proc.returncode == 0 else None


def git_dir(cwd: Path) -> Path:
    return Path(out("rev-parse", "--absolute-git-dir", cwd=cwd))


def common_dir(cwd: Path) -> Path:
    raw = out("rev-parse", "--git-common-dir", cwd=cwd)
    path = Path(raw)
    return path if path.is_absolute() else (cwd / path).resolve()


def is_linked_worktree(cwd: Path) -> bool:
    return git_dir(cwd).resolve() != common_dir(cwd).resolve()


def current_branch(cwd: Path) -> str | None:
    proc = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=cwd, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip() or None


def identity_env(cwd: Path) -> dict[str, str]:
    """Commit identity for AEW-created commits: the repo's configured identity, else a fixed one."""
    env: dict[str, str] = {}
    if not ok("config", "user.name", cwd=cwd):
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = AEW_IDENTITY["name"]
    if not ok("config", "user.email", cwd=cwd):
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = AEW_IDENTITY["email"]
    return env


ATTR_FILTER = re.compile(r"(?:^|\s)filter=([^\s]+)")


def _attribute_files(cwd: Path) -> list[Path]:
    global_var = git("var", "GIT_ATTR_GLOBAL", cwd=cwd, check=False)
    if global_var.returncode == 0:
        global_path = cwd / os.fsdecode(global_var.stdout.rstrip(b"\r\n"))
    else:
        configured = git("config", "--type=path", "--null", "--get", "core.attributesFile", cwd=cwd, check=False)
        if configured.returncode == 0:
            global_path = cwd / os.fsdecode(configured.stdout.removesuffix(b"\0"))
        else:
            home = Path(os.environ.get("HOME") or Path.home())
            xdg = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
            global_path = cwd / xdg / "git" / "attributes"
    system = git("var", "GIT_ATTR_SYSTEM", cwd=cwd, check=False)
    files = [global_path]
    if system.returncode == 0:
        files.append(Path(os.fsdecode(system.stdout.rstrip(b"\r\n"))))
    elif (system.returncode == 129
          and os.environ.get("GIT_ATTR_NOSYSTEM", "").lower() in {"", "0", "false", "no", "off"}):
        # Git before 2.42 has no variable for the installation's system attributes path.
        files.append(Path("/etc/gitattributes"))
        exec_path = Path(out("--exec-path", cwd=cwd))
        files.extend(prefix / "etc" / "gitattributes" for prefix in exec_path.parents[1:4])
    return files


def untrusted_filters(cwd: Path, commit: str) -> list[dict[str, Any]]:
    """Find configured, untrusted filters assigned by committed or external attributes.

    AEW switches these filters off, so it refuses a dispatch that would read or commit files
    differently from the project's own git.
    """
    effective: dict[str, dict[str, str]] = {}
    for d in configured_drivers(cwd):  # in precedence order: the last definition of a key is the one git uses
        effective[d["config"]] = d
    defined: dict[str, list[dict[str, str]]] = {}
    for d in effective.values():
        if d["kind"] == "filter" and d["key"] in {"clean", "smudge", "process"} and d["value"]:
            defined.setdefault(d["driver"], []).append(d)
    needed = {name: entries for name, entries in defined.items() if name not in _trusted}
    if not needed:
        return []
    sources: list[tuple[str, str]] = []
    # Count case variants on every platform, even when Git would only use lowercase.
    for path in out("ls-tree", "-r", "--name-only", "-z", commit, cwd=cwd).split("\0"):
        if path.rsplit("/", 1)[-1].lower() == ".gitattributes":
            sources.append((path, out("cat-file", "-p", f"{commit}:{path}", cwd=cwd)))
    info = git_dir(cwd) / "info" / "attributes"
    common_info = common_dir(cwd) / "info" / "attributes"
    for f in dict.fromkeys([info, common_info, *_attribute_files(cwd)]):
        if f.is_file():
            sources.append((str(f), f.read_text(encoding="utf-8", errors="replace")))
    uses: dict[str, dict[str, list[str]]] = {}
    for where, text in sources:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for name in ATTR_FILTER.findall(line):
                if name in needed:
                    uses.setdefault(name, {}).setdefault(where, []).append(line.split()[0])
    return [{"driver": name, "patterns_by_file": uses[name],
             "commands": [{"config": d["config"], "value": d["value"], "origin": d["origin"]} for d in needed[name]]}
            for name in sorted(uses)]


def untrusted_filters_message(found: list[dict[str, Any]], policy_file: str, *, from_doctor: bool = False) -> str:
    """The refusal for ``untrusted_filters``: what is needed and why it is refused, then exactly how to proceed."""
    parts = []
    for f in found:
        groups = []
        for path, patterns in f["patterns_by_file"].items():
            shown = ", ".join(patterns[:5])
            if len(patterns) > 5:
                shown += f" and {len(patterns) - 5} more"
            groups.append(f"{shown} ({path})")
        origins = sorted({c["origin"] for c in f["commands"]})
        cmds = ", ".join(f"{c['config']} = `{c['value']}`" for c in f["commands"])
        where = f"defined in {origins[0]}" if len(origins) == 1 else "defined in " + ", ".join(origins)
        parts.append(f"filter '{f['driver']}' (assigned by {'; '.join(groups)}; {cmds}; {where})")
    names = ", ".join(f["driver"] for f in found)
    return (
        f"Refused: this repository's files need git {'filters' if len(found) > 1 else 'filter'} {names} and AEW "
        f"does not trust {'them' if len(found) > 1 else 'it'}. " + "; ".join(parts) + ". "
        "Why: AEW's own git handles the files agents write, outside every sandbox, so an untrusted filter command "
        "could run code an agent edited; and without the filter AEW would snapshot and commit these files wrongly. "
        "To fix, either: "
        f"1. If the command is an installed program agents cannot modify (git-lfs usually is): add "
        f"`trusted_git_drivers: [{names}]` under `containment:` in {policy_file}, then retry. "
        "2. If the command runs a script from this repository: move the script outside the repository and outside "
        "every containment.writable root, update the filter's git configuration to the new path, then trust it as "
        "in 1; or remove the filter assignment from each attributes file listed above."
        + ("" if from_doctor else " `aew doctor` lists every configured git driver and whether AEW trusts it.")
    )


# --------------------------------------------------------------------------- reading one commit's objects
#
# Project maps (register F22.1, ADR-0015) are generated from the Git objects of an exact commit, never from the
# checkout or the index (design v0.5 §2.2). Two things could still substitute bytes under that commit: replace refs
# (`refs/replace/*` swaps one object for another on every read) and, in a partial clone, a lazy fetch of a missing
# object from a promisor remote. Both are switched off; a missing object is reported, never fetched (plan §2).

OBJECT_ENV = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1"}  # the second is honoured from git 2.44
NO_LAZY_FETCH_FROM = (2, 44)
# No console window on Windows (subprocess.CREATE_NO_WINDOW, spelled out so the module type-checks on Linux; POSIX
# accepts 0).
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# Bounds on object reads: a one-shot call, and each object a batch reader serves. Generous for a real repository;
# they exist so that a stuck git fails a command instead of hanging it (PR #126, CI).
OBJECT_TIMEOUT_S = 300.0
BATCH_READ_TIMEOUT_S = 120.0
BATCH_CLOSE_TIMEOUT_S = 30.0  # the wait for a batch reader to exit once its input is closed (normally at once)


def object_git(*args: str, cwd: Path, check: bool = True, input: bytes | None = None,
               timeout: float = OBJECT_TIMEOUT_S) -> subprocess.CompletedProcess[bytes]:
    """A one-shot git call that reads objects of an exact commit: replace refs off, no lazy fetch, no window, never
    waiting on a terminal, and bounded by ``timeout`` (a stuck git fails the command, it never hangs it). Counted
    like every other git process (``profile``), so a per-file spawn shows in the scale regression."""
    if not Path(cwd).is_dir():
        raise GitError(f"git {args[0] if args else ''}: the directory {cwd} does not exist", cwd=str(cwd))
    profile.count("git")
    profile.count(f"git:{args[0] if args else ''}")
    with profile.phase("git"):
        try:
            proc = subprocess.run(["git", *safe_config(cwd, OBJECT_ENV), *args], cwd=cwd, env=_env(OBJECT_ENV),
                                  capture_output=True, input=input, timeout=timeout,
                                  stdin=subprocess.DEVNULL if input is None else None, creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise GitError(f"git {' '.join(args)} did not finish within {timeout:g}s and was stopped", cwd=str(cwd),
                           reason="timeout") from None
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode})", cwd=str(cwd),
                       stderr=proc.stderr.decode("utf-8", "replace").strip())
    return proc


def version(cwd: Path, *, timeout: float = OBJECT_TIMEOUT_S) -> tuple[int, ...]:
    """The installed git's version as numbers (``git version 2.46.0.windows.1`` -> (2, 46, 0))."""
    raw = object_git("version", cwd=cwd, timeout=timeout).stdout.decode("ascii", "replace").split()
    numbers = re.findall(r"\d+", raw[2] if len(raw) > 2 else "")
    return tuple(int(n) for n in numbers[:3])


def is_partial_clone(cwd: Path, *, timeout: float = OBJECT_TIMEOUT_S) -> bool:
    """Whether the repository is a partial clone: ``extensions.partialClone`` set, or a remote marked promisor."""
    proc = object_git("config", "-z", "--get-regexp", r"^(extensions\.partialclone|remote\..*\.promisor)$",
                      cwd=cwd, check=False, timeout=timeout)
    for item in proc.stdout.split(b"\0"):
        key, _, value = item.partition(b"\n")
        if key == b"extensions.partialclone" and value.strip():
            return True
        if key.startswith(b"remote.") and value.strip().lower() in {b"true", b"yes", b"on", b"1"}:
            return True
    return False


def lazy_fetch_possible(cwd: Path, *, timeout: float | Callable[[], float] = OBJECT_TIMEOUT_S) -> bool:
    """Whether a read of this repository's objects could fetch a missing one lazily whatever AEW asks: a partial clone
    on a git older than 2.44 (``NO_LAZY_FETCH_FROM``), which ignores ``GIT_NO_LAZY_FETCH``. The one owner of the
    predicate: the maps refuse generation on it, and a ref review's pin refuses dispatch on it (register E168).
    ``timeout`` bounds each git process; a callable is asked again for each, so a caller with one deadline gives each
    process only the time left."""
    left = timeout if callable(timeout) else (lambda: timeout)
    return is_partial_clone(cwd, timeout=left()) and version(cwd, timeout=left()) < NO_LAZY_FETCH_FROM


class CatFileBatch:
    """One ``git cat-file --batch`` process serving every blob of a generation: one process, not one per file.

    Use as a context manager; ``read(oid)`` returns the object's bytes, or None when the object is missing."""

    def __init__(self, cwd: Path, timeout: float = BATCH_READ_TIMEOUT_S) -> None:
        self.cwd = cwd
        self.timeout = timeout
        self.close_timeout = BATCH_CLOSE_TIMEOUT_S  # a caller with a deadline lowers it (maps.gitobjects.open_tree)
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> CatFileBatch:
        profile.count("git")
        profile.count("git:cat-file")
        self._proc = subprocess.Popen(["git", *safe_config(self.cwd, OBJECT_ENV), "cat-file", "--batch"],
                                      cwd=self.cwd, env=_env(OBJECT_ENV), stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return self

    def read(self, oid: str) -> bytes | None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise GitError("cat-file --batch is not running", cwd=str(self.cwd))
        # A pipe read cannot time out on Windows, so a watchdog kills a batch process that stops answering: the read
        # then ends at EOF and fails, instead of hanging the command.
        watchdog = threading.Timer(self.timeout, proc.kill)
        watchdog.daemon = True
        watchdog.start()
        try:
            with profile.phase("git"):
                proc.stdin.write(oid.encode("ascii") + b"\n")
                proc.stdin.flush()
                header = proc.stdout.readline()
                parts = header.split()
                if len(parts) == 2 and parts[1] == b"missing":
                    return None
                if len(parts) != 3:
                    raise GitError(f"cat-file --batch: no reply for {oid} ({header[:80]!r}; stopped after "
                                   f"{self.timeout:g}s?)", cwd=str(self.cwd))
                size = int(parts[2])
                data = proc.stdout.read(size)
                proc.stdout.read(1)  # the newline after the content
        except OSError as exc:  # the process died (or was stopped): a broken pipe
            raise GitError(f"cat-file --batch failed: {exc}", cwd=str(self.cwd)) from None
        finally:
            watchdog.cancel()
        if len(data) != size:
            raise GitError("cat-file --batch: short read", cwd=str(self.cwd))
        return data

    def __exit__(self, *_exc: object) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.wait(timeout=self.close_timeout)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()
        finally:
            if proc.stdout is not None:
                proc.stdout.close()


# --------------------------------------------------------------------------- a named ref to review (register E168)
#
# A non-mutating Ticket may name a local ref for review (the designer's decision of 2026-11-06, (d)). What a ref name
# means to AEW is owned here: the namespaces it accepts, how a given name becomes one full ref name at creation, and
# what that ref points at when it is pinned. Every call reads through ``object_git``: replace refs off, no lazy fetch,
# no window. AEW fetches nothing: a ref is what the operator's repository holds now.

REVIEWABLE_REF_PREFIXES = ("refs/heads/", "refs/tags/", "refs/remotes/")
# What makes a name a revision expression rather than a ref's name (gitrevisions(7)), or not a ref name at all.
_REVISION_SYNTAX = re.compile(r"[~^:\\?*\[\s]|@\{|\.\.|\A-|\A@\Z")
_HEX = re.compile(r"\A[0-9a-fA-F]{4,64}\Z")


def _refs(cwd: Path) -> list[str]:
    """Every ref the repository holds, by its full name (one ``for-each-ref``)."""
    proc = object_git("for-each-ref", "--format=%(refname)", cwd=cwd)
    return proc.stdout.decode("utf-8", "replace").splitlines()


def full_ref_name(name: str, *, cwd: Path) -> str:
    """The full name of the ref ``name`` gives, in an accepted namespace (``REVIEWABLE_REF_PREFIXES``): a full name as
    it is, a short one as the one ref it names there, and ``HEAD`` as the branch the checkout at ``cwd`` is on. Never a
    commit: what the ref points at is read when it is pinned. Refused, with ``reason`` in the details: a revision
    expression, a commit id or an invalid name (``not_a_ref``), a ref outside the namespaces (``ref_namespace``), a
    short name two refs share (``ambiguous_ref``, with the ``candidates``), ``HEAD`` detached (``detached_head``) or on
    a branch with no commit yet (``unborn_ref``), and a name no ref has (``unknown_ref``)."""
    accepted = ", ".join(f"`{p}`" for p in REVIEWABLE_REF_PREFIXES)
    if name == "HEAD":
        proc = object_git("symbolic-ref", "--quiet", "HEAD", cwd=cwd, check=False)
        branch = proc.stdout.decode("utf-8", "replace").strip()
        if proc.returncode != 0 or not branch:
            raise UsageError("HEAD is detached, so it names no branch to review: name the branch (or tag) instead",
                             reason="detached_head", ref=name)
        if branch not in _refs(cwd):
            raise IllegalTransition(f"HEAD is on {branch}, which has no commit yet: commit first, then name it",
                                    reason="unborn_ref", ref=branch)
        name = branch
    if not name or _REVISION_SYNTAX.search(name):
        raise UsageError(f"{name!r} is not the name of a ref: name a branch, tag or remote-tracking ref (in "
                         f"{accepted}); to review a bare commit, create a branch at it", reason="not_a_ref", ref=name)
    refs = _refs(cwd)
    if name.startswith("refs/"):
        if not name.startswith(REVIEWABLE_REF_PREFIXES):
            raise UsageError(f"{name} is outside the refs AEW reviews: name one in {accepted}", reason="ref_namespace",
                             ref=name, accepted=list(REVIEWABLE_REF_PREFIXES))
        if name in refs:
            return name
        raise NotFound(f"no ref {name} in this repository; AEW fetches nothing: create or fetch it yourself, then "
                       "name it again", reason="unknown_ref", ref=name)
    candidates = [prefix + name for prefix in REVIEWABLE_REF_PREFIXES if prefix + name in refs]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise UsageError(f"{name!r} names {len(candidates)} refs ({', '.join(candidates)}): give the full name",
                         reason="ambiguous_ref", ref=name, candidates=candidates)
    if f"refs/{name}" in refs:
        raise UsageError(f"refs/{name} is outside the refs AEW reviews: name one in {accepted}",
                         reason="ref_namespace", ref=f"refs/{name}", accepted=list(REVIEWABLE_REF_PREFIXES))
    if _HEX.match(name) and object_git("cat-file", "-e", f"{name}^{{commit}}", cwd=cwd, check=False).returncode == 0:
        raise UsageError(f"{name!r} is a commit, not a ref: a review names a branch, tag or remote-tracking ref; to "
                         "review a bare commit, create a branch at it", reason="not_a_ref", ref=name)
    raise NotFound(f"no branch, tag or remote-tracking ref named {name!r} in this repository; AEW fetches nothing: "
                   "create or fetch it yourself, then name it again", reason="unknown_ref", ref=name)


def ref_target(name: str, *, cwd: Path, timeout: float = OBJECT_TIMEOUT_S) -> str | None:
    """The object the full ref ``name`` holds now, or None when the repository has no such ref (it was deleted). The
    ref is read, never its object, so a missing object does not hide the ref."""
    proc = object_git("for-each-ref", "--format=%(refname)%00%(objectname)", name, cwd=cwd, timeout=timeout)
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        ref, _, oid = line.partition("\0")
        if ref == name:
            return oid
    return None


def ref_commit(name: str, *, cwd: Path, timeout: float = OBJECT_TIMEOUT_S) -> str | None:
    """The commit the full ref ``name`` points at now, a tag peeled; None when there is no such ref. Refused: a ref that
    does not peel to a commit (``USAGE``, ``not_a_commit``), and one whose objects the repository lacks (``GIT_ERROR``,
    ``object_missing``: AEW fetches nothing)."""
    oid = ref_target(name, cwd=cwd, timeout=timeout)
    if oid is None:
        return None
    proc = object_git("rev-parse", "--verify", "--quiet", f"{oid}^{{commit}}", cwd=cwd, check=False, timeout=timeout)
    commit = proc.stdout.decode("ascii", "replace").strip()
    if proc.returncode == 0 and commit:
        return commit
    if object_git("cat-file", "-e", oid, cwd=cwd, check=False, timeout=timeout).returncode != 0:
        raise GitError(f"{name} points at {oid[:12]}, which this repository does not hold; AEW fetches nothing: fetch "
                       "it yourself, then dispatch again", reason="object_missing", ref=name, object=oid)
    raise UsageError(f"{name} points at {oid[:12]}, which is not a commit: name a ref to a commit",
                     reason="not_a_commit", ref=name, object=oid)


def merge_bases(one: str, other: str, *, cwd: Path) -> list[str]:
    """Every best common ancestor of two commits, in the order ``git merge-base --all`` prints them; empty when they
    share no history. More than one is a criss-cross history."""
    proc = object_git("merge-base", "--all", one, other, cwd=cwd, check=False)
    if proc.returncode not in (0, 1):
        raise GitError(f"git merge-base {one[:12]} {other[:12]} failed: a commit's objects are missing? AEW fetches "
                       "nothing", reason="object_missing", stderr=proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout.decode("ascii", "replace").split()


def is_ancestor_object(ancestor: str, descendant: str, *, cwd: Path, timeout: float = OBJECT_TIMEOUT_S) -> bool:
    """``is_ancestor`` through ``object_git``: no lazy fetch, bounded."""
    proc = object_git("merge-base", "--is-ancestor", ancestor, descendant, cwd=cwd, check=False, timeout=timeout)
    if proc.returncode not in (0, 1):
        raise GitError("merge-base --is-ancestor failed", stderr=proc.stderr.decode("utf-8", "replace").strip())
    return proc.returncode == 0


def uncommitted_on(branch: str, *, cwd: Path) -> dict[str, Any] | None:
    """Where the full branch name ``branch`` is checked out with uncommitted changes to tracked files: the worktree
    and how many paths, or None. Read with ``--no-optional-locks``, so the worktree's index is not refreshed: nothing
    is written. A tag or a remote-tracking ref is never checked out, so it has none."""
    if not branch.startswith("refs/heads/"):
        return None
    listing = object_git("worktree", "list", "--porcelain", cwd=cwd).stdout.decode("utf-8", "replace")
    for block in listing.split("\n\n"):  # git 2.31 has no `-z` here; a path holding a newline is not matched
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if fields.get("branch") != branch or not fields.get("worktree") or not Path(fields["worktree"]).is_dir():
            continue
        proc = object_git("--no-optional-locks", "status", "--porcelain", "-z", "--no-renames",
                          "--untracked-files=no", cwd=Path(fields["worktree"]), check=False)
        paths = [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]
        return {"worktree": fields["worktree"], "paths": len(paths)} if paths else None
    return None
