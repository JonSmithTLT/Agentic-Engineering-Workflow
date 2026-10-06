"""A case's fixture: its content, hash and scratch repository (evaluation component design v0.2, §2).

A case's public manifest (``aew/eval-case/v1``, ``case.yaml``) names its fixture directories relative to itself: a
``base`` tree, an optional ``overlay`` copied over it (the case's starting point), and an optional ``seeded`` tree
copied over both for an arm that starts from a first implementation.

The fixture is read **once**, into a :class:`Snapshot`: the case hash a preregistration freezes is computed from it,
and the scratch repository is built from it, so the content a run starts from is always the content that was hashed
(a file changed on disk in between changes neither). The hash covers the manifest and every tree's paths and bytes.

Text is hashed and built with LF line ends, as the M3 driver built its repositories, so a CRLF and an LF checkout of
a case hash and build the same; a file holding a NUL byte is binary and kept as it is. A case whose paths could build
differently on another platform is refused: two paths that differ only in case, a name Windows reserves, a name ending
in a dot or a space. A fixture never contains a ``.git`` component, a symbolic link or a junction, or a tree that is
the case directory itself or lies inside another tree.

Every git call here runs in a scrubbed environment (no inherited ``GIT_*`` variable, no system or global
configuration, no template, hooks or signing), and only while the repository is the runner's own: nothing reads a
scratch repository through git after a model-controlled arm has run in it (:func:`files_of`).
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aew_eval.canonical import sha256_of
from aew_eval.schemas import Invalid, validate

CASE = "aew/eval-case/v1"
TREES = ("base", "overlay", "seeded")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
GIT_SHORT_NAME = re.compile(r"^git~\d+$", re.IGNORECASE)  # the 8.3 name of .git on an NTFS volume (git refuses it too)
LINK, SPECIAL = "link", "special"  # what a work tree holds besides regular files
GIT_CONFIG = ("-c", "core.hooksPath=", "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false",
              "-c", "core.autocrlf=false", "-c", "user.name=Fixture Developer", "-c", "user.email=dev@fixture.invalid")


@dataclass(frozen=True)
class Case:
    manifest: dict[str, Any]
    root: Path  # the directory holding case.yaml: fixture paths are relative to it

    @property
    def id(self) -> str:
        return self.manifest["id"]

    def tree(self, which: str) -> Path | None:
        rel = self.manifest["fixture"].get(which)
        return None if rel is None else (self.root / rel).resolve()


@dataclass(frozen=True)
class Snapshot:
    """A case's fixture as read once: every tree's files (relative path to normalized bytes) and their hash."""

    case: Case
    trees: dict[str, dict[str, bytes] | None]
    sha256: str


def load(path: Path) -> Case:
    """A case from its ``case.yaml``, validated, with every fixture tree it names a distinct directory inside its
    root (never the root itself, never inside another of its trees)."""
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate(CASE, manifest, what=f"case {path}")
    case = Case(manifest, path.parent.resolve())
    trees = {w: t for w in TREES if (t := case.tree(w)) is not None}
    for which, tree in trees.items():
        if not tree.is_dir():
            raise Invalid(f"case {case.id}: its {which} tree {manifest['fixture'][which]} is not a directory")
        if case.root not in tree.parents:
            raise Invalid(f"case {case.id}: its {which} tree must be a directory inside the case directory")
        for other, t in trees.items():
            if other != which and (t == tree or t in tree.parents):
                raise Invalid(f"case {case.id}: its {which} tree lies inside (or is) its {other} tree")
    return case


def normalized(data: bytes) -> bytes:
    """A file's content as fixtures are hashed and built: LF line ends for text, binary unchanged."""
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def safe_relative(rel: str, what: str) -> str:
    """``rel`` as a fixture or arm path: relative, inside its root, and the same file on every platform."""
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel) or "\\" in rel:
        raise Invalid(f"{what}: {rel!r} is not a relative path with / separators")
    parts = rel.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise Invalid(f"{what}: {rel!r} has an empty, . or .. component")
        if part.casefold() == ".git" or GIT_SHORT_NAME.match(part):
            raise Invalid(f"{what}: {rel!r} names a .git component: repository metadata is never a fixture or an "
                          "arm's work product")
        if WINDOWS_RESERVED.match(part) or part.endswith((".", " ")) or any(c in part for c in '<>:"|?*') \
                or any(ord(c) < 0x20 or ord(c) == 0x7F for c in part):
            raise Invalid(f"{what}: {rel!r} has a component Windows cannot hold ({part!r})")
    return rel


def is_link(p: Path) -> bool:
    """A symbolic link, or a Windows junction or other reparse point (``Path.is_junction`` only exists from 3.12)."""
    st = os.lstat(p)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(st.st_mode) or bool(reparse and (getattr(st, "st_file_attributes", 0) or 0) & reparse)


def _read_tree(root: Path, what: str) -> dict[str, bytes]:
    """Every regular file under ``root``, by relative path; refuses a link, a junction or a path leaving ``root``."""
    files: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        for name in dirnames + filenames:
            p = here / name
            if is_link(p):
                raise Invalid(f"{what}: {p.relative_to(root).as_posix()} is a link; a fixture holds regular files")
            if root not in p.resolve().parents:
                raise Invalid(f"{what}: {p.relative_to(root).as_posix()} resolves outside the tree")
        for name in filenames:
            p = here / name
            rel = safe_relative(p.relative_to(root).as_posix(), what)
            if not stat.S_ISREG(os.lstat(p).st_mode):
                raise Invalid(f"{what}: {rel} is not a regular file")
            files[rel] = normalized(p.read_bytes())
    if not files:
        raise Invalid(f"{what}: no files")
    return files


def _digest(files: dict[str, bytes]) -> str:
    return sha256_of(sorted([rel, hashlib.sha256(data).hexdigest()] for rel, data in files.items()))


def snapshot(case: Case) -> Snapshot:
    """Read the case's fixture once. Refuses, within a tree or across trees, paths whose files or directories would
    collide on a case-insensitive file system, and a name that is a file in one tree and a directory in another (an
    overlay may replace a file only under exactly the same name)."""
    trees: dict[str, dict[str, bytes] | None] = {}
    seen: dict[str, tuple[str, str]] = {}  # case-folded path -> (as spelled, "file" or "dir")
    for which in TREES:
        tree = case.tree(which)
        trees[which] = None if tree is None else _read_tree(tree, f"case {case.id} {which}")
        for rel in trees[which] or {}:
            parts = rel.split("/")
            for n in range(1, len(parts) + 1):
                path, kind = "/".join(parts[:n]), "file" if n == len(parts) else "dir"
                prior = seen.setdefault(path.casefold(), (path, kind))
                if prior[0] != path:
                    raise Invalid(f"case {case.id}: {path!r} and {prior[0]!r} differ only in case; they would build "
                                  "differently on Windows and Linux")
                if prior[1] != kind:
                    raise Invalid(f"case {case.id}: {path!r} is a file in one tree and a directory in another")
    digests = {which: None if files is None else _digest(files) for which, files in trees.items()}
    return Snapshot(case, trees, sha256_of({"manifest": case.manifest, "trees": digests}))


def case_sha256(case: Case) -> str:
    """The hash a preregistration freezes for the case: its manifest and the content of each fixture tree."""
    return snapshot(case).sha256


def git_env() -> dict[str, str]:
    """The environment for the runner's git: nothing a caller set for some other repository, and no configuration
    beyond the command line's."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return env


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *GIT_CONFIG, *args], cwd=repo, check=True, capture_output=True, encoding="utf-8",
                          env=git_env(), stdin=subprocess.DEVNULL, creationflags=NO_WINDOW).stdout.strip()


def starting_files(snap: Snapshot, *, seeded: bool) -> dict[str, bytes]:
    """The starting point's files: base, then overlay, then (when ``seeded``) the seeded tree, each over the last."""
    if seeded and snap.trees["seeded"] is None:
        raise Invalid(f"case {snap.case.id} has no seeded tree")
    files: dict[str, bytes] = {}
    for which in ("base", "overlay", "seeded") if seeded else ("base", "overlay"):
        files.update(snap.trees[which] or {})
    return files


def build(snap: Snapshot, repo: Path, *, seeded: bool = False) -> dict[str, bytes]:
    """The starting point as a fresh one-commit git repository at ``repo``, written from the snapshot (never from
    disk again). Returns the files it holds, by relative path, for :func:`changed_paths`."""
    files = starting_files(snap, seeded=seeded)
    if repo.exists():
        raise Invalid(f"{repo} exists: a fixture is built into a fresh directory")
    repo.mkdir(parents=True)
    for rel, data in files.items():
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    git(repo, "init", "-q", "--template=", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", f"{snap.case.id}: starting point" + (" (seeded)" if seeded else ""))
    return files


@dataclass(frozen=True)
class WorkTree:
    """A work tree as found, without git: its regular files' exact bytes, and everything else it holds (a link,
    with its target text; a FIFO, socket or device, as special), kept apart so no content is mistaken for either."""

    files: dict[str, bytes]
    other: dict[str, str]


def files_of(repo: Path) -> WorkTree:
    """A work tree read as plain files, without git (whose configuration an arm may have rewritten), never following a
    link out of it and never opening anything but a regular file (a FIFO would block): ``.git`` is skipped."""
    files: dict[str, bytes] = {}
    other: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(repo, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not (here == repo and d == ".git")]
        for name in list(dirnames) + filenames:
            p = here / name
            rel = p.relative_to(repo).as_posix()
            if is_link(p):
                try:
                    other[rel] = f"{LINK} -> {os.readlink(p)}"
                except (OSError, ValueError):  # a reparse point that is not a link (an app alias, a socket)
                    other[rel] = SPECIAL
                if name in dirnames:
                    dirnames.remove(name)
            elif name in filenames:
                if stat.S_ISREG(os.lstat(p).st_mode):
                    files[rel] = p.read_bytes()
                else:
                    other[rel] = SPECIAL
    return WorkTree(files, other)


def changed_paths(start: dict[str, bytes], now: WorkTree) -> list[str]:
    """Every path added, removed or changed since the starting point (built with exactly ``start``'s bytes, so a
    line-end-only rewrite is a change), and every link or special file now present."""
    changed = {rel for rel in start.keys() | now.files.keys() if start.get(rel) != now.files.get(rel)}
    return sorted(changed | now.other.keys())
