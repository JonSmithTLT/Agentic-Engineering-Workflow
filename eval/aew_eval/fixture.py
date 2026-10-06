"""A case's fixture: its content hash, and a scratch repository built from it (evaluation component design v0.2, §2).

A case's public manifest (``aew/eval-case/v1``, ``case.yaml``) names its fixture directories relative to itself: a
``base`` tree, an optional ``overlay`` copied over it (the case's starting point), and an optional ``seeded`` tree
copied over both for an arm that starts from a first implementation. The case hash a preregistration freezes covers
the manifest and the bytes of every one of those trees, so a changed fixture refuses to run under the old
preregistration (:func:`aew_eval.prereg.require_inputs`).

Text is hashed and built with LF line ends, as the M3 driver built its repositories: a Windows checkout with CRLF and a
Linux one hash and build the same. A file holding a NUL byte is binary and kept as it is.
"""

from __future__ import annotations

import hashlib
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
GIT_IDENTITY = (("user.name", "Fixture Developer"), ("user.email", "dev@fixture.invalid"), ("core.autocrlf", "false"))


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


def load(path: Path) -> Case:
    """A case from its ``case.yaml``, validated, with every fixture tree it names present and inside its root."""
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate(CASE, manifest, what=f"case {path}")
    case = Case(manifest, path.parent.resolve())
    for which in TREES:
        tree = case.tree(which)
        if tree is None:
            continue
        if not tree.is_dir():
            raise Invalid(f"case {case.id}: its {which} tree {manifest['fixture'][which]} is not a directory")
        if case.root not in tree.parents and tree != case.root:
            raise Invalid(f"case {case.id}: its {which} tree is outside the case directory")
    return case


def normalized(data: bytes) -> bytes:
    """A file's content as fixtures are hashed and built: LF line ends for text, binary unchanged."""
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def _files(root: Path) -> list[tuple[str, Path]]:
    out = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise Invalid(f"{path} is a symbolic link; a fixture holds regular files only")
        if path.is_file():
            out.append((path.relative_to(root).as_posix(), path))
    return out


def tree_digest(root: Path) -> str:
    """The content hash of one fixture tree: each file's path and normalized bytes."""
    entries = [[rel, hashlib.sha256(normalized(p.read_bytes())).hexdigest()] for rel, p in _files(root)]
    if not entries:
        raise Invalid(f"{root} holds no files")
    return sha256_of(entries)


def case_sha256(case: Case) -> str:
    """The hash a preregistration freezes for the case: its manifest and the content of each fixture tree."""
    trees = {which: (None if case.tree(which) is None else tree_digest(case.tree(which)))  # type: ignore[arg-type]
             for which in TREES}
    return sha256_of({"manifest": case.manifest, "trees": trees})


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, creationflags=NO_WINDOW).stdout.strip()


def build(case: Case, repo: Path, *, seeded: bool = False) -> str:
    """The case's starting point as a fresh git repository at ``repo``; returns its one commit. ``seeded`` copies the
    seeded tree over the base and overlay (refused for a case that has none)."""
    if seeded and case.tree("seeded") is None:
        raise Invalid(f"case {case.id} has no seeded tree")
    if repo.exists():
        raise Invalid(f"{repo} exists: a fixture is built into a fresh directory")
    repo.mkdir(parents=True)
    for which in ("base", "overlay", "seeded") if seeded else ("base", "overlay"):
        tree = case.tree(which)
        if tree is None:
            continue
        for rel, src in _files(tree):
            dest = repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(normalized(src.read_bytes()))
    _git(repo, "init", "-q", "-b", "main")
    for key, value in GIT_IDENTITY:
        _git(repo, "config", key, value)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"{case.id}: starting point" + (" (seeded)" if seeded else ""))
    return _git(repo, "rev-parse", "HEAD")


def changed_paths(repo: Path, base: str) -> list[str]:
    """Every path that differs from ``base`` in the work tree, committed or not, untracked files included."""
    _git(repo, "add", "-A", "--intent-to-add")
    out = _git(repo, "diff", "--no-renames", "--name-only", base)
    return sorted(line for line in out.splitlines() if line)
