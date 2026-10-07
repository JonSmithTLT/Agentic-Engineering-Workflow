"""``TrackedTree``: the structural generator's only way to read a repository (design v0.5 §2.2, §2.4; plan §2).

For commit ``H`` it resolves the commit and its tree, lists the tree once (``ls-tree -r -z --full-tree -l``: mode,
type, object id, size and path) and serves blobs through one ``cat-file --batch`` process, all reading Git objects
with replace refs and lazy fetching switched off (``aew.workspace.git.OBJECT_ENV``). Never the checkout, the index or
the working tree: ``--commit H`` means exactly ``H``.

Every blob the generator considers is logged through the same tracker: a blob it reads as ``{path, git_oid, size,
read: true, sha256}``, a blob it skipped for its size or because the total cap was reached as ``{path, git_oid, size,
read: false, reason}``. That log is the record's ``inputs.metadata``; it is never written by hand (PMP-27).

A record is never produced from incomplete source (PMP-67, T5-INV-08): a needed object that is missing refuses
generation (``MAP_CURRENTNESS_UNPROVEN``, ``missing_object``), and a partial clone on a git too old to be told not to
fetch lazily is refused outright (``partial_clone``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aew.errors import MapCurrentnessUnproven
from aew.maps.canonical import Entry, listing_sha256, render_bytes, sha256
from aew.workspace import git

CAPPED_SIZE, CAPPED_TOTAL = "capped_size", "capped_total"
MISSING_SHOWN = 20


class TrackedTree:
    """One commit's listing, and its blobs through a tracked read. ``fetch`` returns a blob's bytes by object id, or
    None when the object is missing; tests give an in-memory one, ``open_tree`` gives the batch process."""

    def __init__(self, *, commit: str, tree: str, object_format: str, entries: list[Entry],
                 fetch: Callable[[str], bytes | None]) -> None:
        self.commit = commit
        self.tree = tree
        self.object_format = object_format
        self.entries: tuple[Entry, ...] = tuple(sorted(entries, key=lambda e: e.path))
        self._by_path = {e.path: e for e in self.entries}
        self._fetch = fetch
        self._log: dict[str, dict[str, Any]] = {}

    def entry(self, path: str) -> Entry:
        return self._by_path[path]

    def require(self, paths: list[str]) -> None:
        """Refuse, naming every one of them, when any of the blobs the generator needs is missing (PR #126 review, F3:
        one refusal per missing input made the operator fetch them one round at a time). ``ls-tree -l`` reads each
        blob's header for its size, so a listed size proves the object is here; a missing one has none (``BAD``)."""
        missing = sorted(p for p in paths if self._by_path[p].size is None)
        if missing:
            raise MapCurrentnessUnproven(
                f"{len(missing)} blob(s) the map needs are missing from this repository (a partial clone?), "
                f"including {missing[0]}: a map is never generated from incomplete source; fetch them, or generate in "
                "a full clone", reason="missing_object", paths=missing[:MISSING_SHOWN], missing=len(missing))

    def read(self, path: str) -> bytes:
        """A regular blob's bytes, logged as an input. The only read API (PMP-27)."""
        e = self._by_path[path]
        if not e.regular:
            raise ValueError(f"{path}: only a regular blob is read (mode {e.mode}, type {e.type})")
        data = self._fetch(e.oid)
        if data is None:
            raise MapCurrentnessUnproven(
                f"the blob of {path} ({e.oid}) is missing from this repository (a partial clone?): a map is never "
                "generated from incomplete source; fetch the object, or generate in a full clone",
                reason="missing_object", paths=[path], object=e.oid)
        self._log[path] = {"path": path, "git_oid": e.oid, "size": len(data), "read": True, "sha256": sha256(data)}
        return data

    def skip(self, path: str, reason: str) -> None:
        """A blob the generator considered and did not read: still an input, since the decision depended on it."""
        if reason not in (CAPPED_SIZE, CAPPED_TOTAL):
            raise ValueError(f"unknown reason {reason!r}")
        e = self._by_path[path]
        if e.size is None:  # its size is an input, and a missing object has none: never logged as a guess
            raise MapCurrentnessUnproven(
                f"the blob of {path} ({e.oid}) is missing from this repository (a partial clone?): a map is never "
                "generated from incomplete source; fetch the object, or generate in a full clone",
                reason="missing_object", paths=[path], object=e.oid)
        self._log[path] = {"path": path, "git_oid": e.oid, "size": e.size, "read": False, "reason": reason}

    def inputs(self) -> list[dict[str, Any]]:
        return [dict(self._log[p]) for p in sorted(self._log)]

    def listing_sha256(self) -> str:
        return listing_sha256(list(self.entries))


def parse_listing(raw: bytes, *, sizes: bool = True) -> list[Entry]:
    """``ls-tree -r -z -l`` output: ``<mode> SP <type> SP <oid> SP <size>\\t<path>\\0`` per entry (no size field
    without ``-l``)."""
    out: list[Entry] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, _, name = item.partition(b"\t")
        fields = meta.split(None, 3)
        mode, kind, oid = fields[:3]
        size = fields[3].strip() if sizes and len(fields) == 4 else b"-"
        path, utf8 = render_bytes(name)
        # "-" for a gitlink; "BAD" when the object is missing (a partial clone): unknown, never guessed
        out.append(Entry(mode=mode.decode("ascii"), type=kind.decode("ascii"), oid=oid.decode("ascii"),
                         size=int(size) if size.isdigit() else None, path=path, utf8=utf8))
    return out


def _refuse_option(rev: str) -> None:
    if not rev or rev.startswith("-") or "\0" in rev or "\n" in rev:
        raise MapCurrentnessUnproven(f"{rev!r} is not a commit name", reason="unknown_commit", commit=rev)


def resolve(repo: Path, rev: str) -> tuple[str, str, str]:
    """``(commit, tree, object_format)`` for ``rev``; ``MAP_CURRENTNESS_UNPROVEN`` (``unknown_commit``) when it does not
    resolve to a commit."""
    _refuse_option(rev)
    proc = git.object_git("rev-parse", "--show-object-format", f"{rev}^{{commit}}", f"{rev}^{{tree}}", cwd=repo,
                          check=False)
    lines = proc.stdout.decode("ascii", "replace").split()
    if proc.returncode != 0 or len(lines) != 3:
        raise MapCurrentnessUnproven(f"{rev!r} does not resolve to a commit in this repository",
                                     reason="unknown_commit", commit=rev)
    object_format, commit, tree = lines
    return commit, tree, object_format


def list_tree(repo: Path, tree: str, *, sizes: bool = True) -> list[Entry]:
    """The recursive listing of ``tree``. With ``sizes`` (``-l``) git reads every blob's header, so in a partial clone
    a missing blob fails the listing: the refusal then names the paths whose objects are missing."""
    args = ["ls-tree", "-r", "-z", "--full-tree", *(["-l"] if sizes else []), tree]
    proc = git.object_git(*args, cwd=repo, check=False)
    if proc.returncode == 0:
        return parse_listing(proc.stdout, sizes=sizes)
    missing: list[str] = []
    if sizes:
        names = git.object_git("ls-tree", "-r", "-z", "--full-tree", tree, cwd=repo, check=False)
        if names.returncode == 0:
            missing = missing_blobs(repo, parse_listing(names.stdout, sizes=False))
    raise MapCurrentnessUnproven(
        f"the tree {tree} cannot be read completely (a partial clone?): a map is never generated from incomplete "
        "source; fetch the missing objects, or generate in a full clone", reason="missing_object", object=tree,
        paths=missing[:MISSING_SHOWN], missing=len(missing),
        stderr=proc.stderr.decode("utf-8", "replace").strip()[-400:])


def missing_blobs(repo: Path, entries: list[Entry]) -> list[str]:
    """The paths whose blobs are not in the object database (one ``cat-file --batch-check``)."""
    blobs = [e for e in entries if e.type == "blob"]
    if not blobs:
        return []
    proc = git.object_git("cat-file", "--batch-check", cwd=repo, check=False,
                          input="".join(e.oid + "\n" for e in blobs).encode("ascii"))
    lines = proc.stdout.decode("ascii", "replace").splitlines()
    return sorted(e.path for e, line in zip(blobs, lines, strict=False) if line.endswith(" missing"))


def refuse_lazy_fetch(repo: Path) -> None:
    """A partial clone on git older than 2.44 could fetch a missing object lazily whatever AEW asks: refused."""
    if git.is_partial_clone(repo) and git.version(repo) < git.NO_LAZY_FETCH_FROM:
        raise MapCurrentnessUnproven(
            "this repository is a partial clone and this git (older than 2.44) cannot be stopped from fetching "
            "missing objects lazily: generate the map in a full clone, or upgrade git", reason="partial_clone")


@contextmanager
def open_tree(repo: Path, rev: str) -> Iterator[TrackedTree]:
    """The tracked tree of commit ``rev``: a constant number of git processes, whatever the repository's size."""
    commit, tree, object_format = resolve(repo, rev)
    refuse_lazy_fetch(repo)
    entries = list_tree(repo, tree)
    with git.CatFileBatch(repo) as batch:
        yield TrackedTree(commit=commit, tree=tree, object_format=object_format, entries=entries, fetch=batch.read)
