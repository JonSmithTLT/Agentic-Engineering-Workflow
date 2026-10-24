"""A workspace fingerprint is a read (STG-05 D-CS2-1): a non-writer writes no object, and gets git's own value.

Every value is compared with an oracle, git itself: ``git add -A`` (and ``rm --cached``, ``add -f``) into a copy of
the index, its objects into a private directory with the real store as an alternate, then ``write-tree``. That is what
AEW computed before, and what evidence already recorded holds. Each case runs as a reader (a worker's CLI, a
non-writer) and as a store writer: the reader's read leaves the real repository's ``objects`` directory and index
unchanged by digest (names, sizes, mtimes); the writer's value is the same, and its tree is in the store, where the
reviewer's pack diffs against it. These run on every platform: Windows runs every worker's read uncontained, the
second face of the gap (#231's review). The sandbox face is in tests/integration/test_containment.py.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from aew import process_kind
from aew.errors import GitError
from aew.snapshot import fingerprint as F
from aew.workspace import worktrees

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1"}


def git(*args: str, cwd: Path, env: dict[str, str] | None = None, check: bool = True,
        input: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    done = subprocess.run(["git", *args], cwd=cwd, env={**ENV, **(env or {})}, capture_output=True, input=input,
                          creationflags=NO_WINDOW, timeout=120)
    if check and done.returncode:
        raise AssertionError(f"git {args}: {done.stderr.decode(errors='replace')}")
    return done


def out(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    return git(*args, cwd=cwd, env=env).stdout.decode("utf-8", "replace").strip()


def digest(repo: Path) -> str:
    """The real object store and index, by names, sizes and mtimes: a write, a new object and a freshened one show."""
    common = Path(out("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=repo))
    index = Path(out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=repo))
    h = hashlib.sha256()
    for d, dirs, files in os.walk(common / "objects"):
        dirs.sort()
        for name in sorted(files):
            st = os.stat(os.path.join(d, name))
            h.update(f"{os.path.relpath(os.path.join(d, name), common)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    if index.exists():
        st = index.stat()
        h.update(f"index|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()


class Oracle:
    """Git's own answer, computed with a private object directory, so it leaves the real store alone too."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.tmp = Path(tempfile.mkdtemp(prefix="oracle-"))
        common = Path(out("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=repo))
        (self.tmp / "objects").mkdir()
        self.objects = {"GIT_OBJECT_DIRECTORY": str(self.tmp / "objects"),
                        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(common / "objects")}

    def index(self, *, staged: bool = False, skip_aew: bool = False) -> dict[str, str]:
        real = Path(out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=self.repo))
        idx = self.tmp / f"index-{len(list(self.tmp.iterdir()))}"
        if real.exists():
            shutil.copy2(real, idx)
        env = {"GIT_INDEX_FILE": str(idx), **self.objects, **F.READ_ALL_CONTENT}
        if not staged:
            git("add", "-A", "--", ".", *([":(exclude).aew"] if skip_aew else []), cwd=self.repo, env=env)
        return env

    def fingerprint(self, exclude: list[str] | None = None, include_ignored: list[str] | None = None) -> str:
        env = self.index(skip_aew=True)
        for path in [".aew", *(exclude or [])]:
            git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", path, cwd=self.repo, env=env)
        for path in include_ignored or []:
            if (self.repo / path).exists():
                git("add", "-f", "--", path, cwd=self.repo, env=env)
        return "git-tree:" + out("write-tree", cwd=self.repo, env=env)

    def working_tree(self) -> str:
        return out("write-tree", cwd=self.repo, env=self.index())

    def index_tree(self) -> str:
        return out("write-tree", cwd=self.repo, env=self.index(staged=True))

    def changed(self, base: str) -> list[str]:
        raw = git("diff", "--cached", "--name-only", "--no-renames", "-z", base, cwd=self.repo, env=self.index())
        return [p for p in raw.stdout.decode("utf-8", "replace").split("\0") if p]

    def index_only(self) -> list[str]:
        head = F.head_tree_id(self.repo)
        index, work = self.index_tree(), self.working_tree()

        def diff(a: str, b: str) -> set[str]:
            raw = git("diff", "--name-only", "--no-renames", "-z", a, b, cwd=self.repo, env=self.objects).stdout
            return {p for p in raw.decode("utf-8", "replace").split("\0") if p}

        return sorted(diff(head, index) & diff(index, work))

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def new_repo(root: Path, name: str = "repo") -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=repo)
    return repo


def commit(repo: Path, message: str = "c") -> str:
    git("add", "-A", cwd=repo)
    git("commit", "-q", "--no-verify", "-m", message, cwd=repo)
    return out("rev-parse", "HEAD", cwd=repo)


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())


# Each case builds a workspace state and returns (the workspace, the base commit or None, fingerprint options).
def edits(root: Path):
    repo = new_repo(root)
    for rel in ("a.txt", "b.txt", "d/c.txt", "gone.txt", "becomes_dir", "docs/x.md", ".aew/state/s.json"):
        write(repo, rel, rel + "\n")
    write(repo, ".gitignore", "*.log\nbuild/\n")
    base = commit(repo)
    write(repo, "a.txt", "changed\n")
    write(repo, "new.txt", "brand new\n")
    (repo / "gone.txt").unlink()
    (repo / "becomes_dir").unlink()
    write(repo, "becomes_dir/inner.txt", "inner\n")  # a tracked file replaced by a directory
    write(repo, "x.log", "ignored\n")
    write(repo, "build/out.txt", "ignored, then included\n")
    write(repo, "docs/x.md", "excluded change\n")
    write(repo, ".aew/state/s.json", "{}\n")  # AEW's own records never move the fingerprint
    return repo, base, {"exclude": ["docs"], "include_ignored": ["build", "x.log"]}


def tree_order(root: Path):
    """git sorts a directory as its name plus '/': files `a-b` and `a.txt` come before directory `a`."""
    repo = new_repo(root)
    for rel in ("a/inner.txt", "a-b", "a.txt", "a0"):
        write(repo, rel, rel + "\n")
    base = commit(repo)
    write(repo, "a/inner.txt", "changed\n")
    write(repo, "a-c", "new\n")
    return repo, base, {}


def empty_repo(root: Path):
    repo = new_repo(root)
    write(repo, "first.txt", "never committed\n")
    return repo, None, {}


def crlf(root: Path):
    repo = new_repo(root)
    git("config", "core.autocrlf", "true", cwd=repo)
    write(repo, "w.txt", "one\r\ntwo\r\n")
    base = commit(repo)
    write(repo, "w.txt", "one\r\nthree\r\n")
    write(repo, "n.txt", "new\r\nfile\r\n")
    return repo, base, {}


def intent_to_add(root: Path):
    repo = new_repo(root)
    write(repo, "a.txt", "a\n")
    base = commit(repo)
    write(repo, "ita/only.txt", "intent\n")
    git("add", "-N", "ita/only.txt", cwd=repo)  # an entry with no content staged: write-tree leaves it (and ita/) out
    return repo, base, {}


def unmerged(root: Path):
    repo = new_repo(root)
    write(repo, "m.txt", "base\n")
    base = commit(repo)
    git("checkout", "-q", "-b", "side", cwd=repo)
    write(repo, "m.txt", "side\n")
    commit(repo)
    git("checkout", "-q", "main", cwd=repo)
    write(repo, "m.txt", "main\n")
    commit(repo)
    assert git("merge", "-q", "side", cwd=repo, check=False).returncode != 0  # a conflict: stages 1 to 3
    return repo, base, {}


def nested(root: Path):
    """An embedded repository (recorded as its commit, as `add -A` does) and a gitlink at another commit."""
    repo = new_repo(root)
    sub = new_repo(repo, "sub")
    write(sub, "s.txt", "one\n")
    first = commit(sub)
    write(repo, "top.txt", "top\n")
    git("add", "top.txt", cwd=repo)
    git("update-index", "--add", "--cacheinfo", f"160000,{first},sub", cwd=repo)
    git("commit", "-q", "--no-verify", "-m", "with a gitlink", cwd=repo)
    base = out("rev-parse", "HEAD", cwd=repo)
    write(sub, "s.txt", "two\n")
    commit(sub)  # the gitlink's checkout moved to another commit
    embedded = new_repo(repo, "embedded")
    write(embedded, "e.txt", "e\n")
    commit(embedded)
    return repo, base, {}


def posix_modes(root: Path):
    """A symlink and an executable bit (POSIX; on Windows the case is the plain edit)."""
    repo = new_repo(root)
    write(repo, "run.sh", "echo\n")
    write(repo, "target.txt", "t\n")
    base = commit(repo)
    if sys.platform != "win32":
        (repo / "run.sh").chmod(0o755)
        (repo / "link").symlink_to("target.txt")
    write(repo, "target.txt", "t2\n")
    return repo, base, {}


def fresh_worktree(root: Path):
    """D-CS2-1's second case: a worktree just made, whose index is racily clean, so every file is read again."""
    repo = new_repo(root)
    for i in range(20):
        write(repo, f"f{i}.txt", f"{i}\n")
    base = commit(repo)
    ws = root / "fresh"
    git("worktree", "add", "-q", "--detach", str(ws), cwd=repo)
    return ws, base, {}


CASES: dict[str, Callable] = {f.__name__: f for f in (edits, tree_order, empty_repo, crlf, intent_to_add, unmerged,
                                                         nested, posix_modes, fresh_worktree)}


READER = "aew (worker run)"  # a non-writer entry point (process_kind.ENTRY_POINTS)


def as_kind(kind: str):
    """The process kind the reads run as: a worker's CLI (a non-writer), or the default, a store writer."""
    import contextlib

    return process_kind.declared_as(READER) if kind == "reader" else contextlib.nullcontext()


@pytest.mark.parametrize("kind", ["reader", "writer"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_a_fingerprint_read_writes_no_object_and_equals_gits_own(tmp_path, case, kind):
    ws, base, opts = CASES[case](tmp_path)
    oracle = Oracle(ws)
    try:
        expected = oracle.fingerprint(**opts) if case != "unmerged" else None
        tree = oracle.working_tree()
    finally:
        oracle.close()
    before = digest(ws)
    with as_kind(kind):
        if case != "unmerged":  # unmerged: resolved in the throwaway index, as `add -A` resolves it
            assert F.relevant_inputs_fingerprint(ws, **opts) == expected
        assert F.working_tree_id(ws) == tree
    if kind == "reader":
        assert digest(ws) == before
    else:  # the reviewer's pack diffs the base against the snapshot's tree: a writer's is in the store
        assert git("cat-file", "-e", f"{tree}^{{tree}}", cwd=ws, check=False).returncode == 0


@pytest.mark.parametrize("kind", ["reader", "writer"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_every_tree_read_leaves_the_object_store_unchanged(tmp_path, case, kind):
    """Each read a worker's command can reach (``working_tree_id``, ``index_tree_id``, ``changed_paths``,
    ``index_only_paths``, ``worktrees.inspect``) gives git's answer, and as a reader writes nothing to the real
    store."""
    ws, base, _ = CASES[case](tmp_path)
    oracle = Oracle(ws)
    try:
        staged = None if case == "unmerged" else oracle.index_tree()
        changed = oracle.changed(base) if base else None
        index_only = None if case == "unmerged" else oracle.index_only()
    finally:
        oracle.close()
    before = digest(ws)
    with as_kind(kind):
        tree_reads(ws, base, staged, changed, index_only)
    if kind == "reader":
        assert digest(ws) == before


def tree_reads(ws: Path, base: str | None, staged: str | None, changed: list[str] | None,
               index_only: list[str] | None) -> None:
    if staged is None:
        with pytest.raises(GitError):  # an unmerged index has no tree: callers treat it as unknown
            F.index_tree_id(ws)
        assert worktrees.inspect(str(ws), base)["dirty"] is None
    else:
        assert F.index_tree_id(ws) == staged
        assert F.index_only_paths(ws) == index_only
        assert worktrees.inspect(str(ws), base)["exists"] is True
    if changed is not None and base is not None:
        assert sorted(F.changed_paths(ws, base)) == sorted(changed)


def test_a_recorded_fingerprint_a_non_writer_computed_is_found_with_no_tree_in_the_store(tmp_path):
    """Planted cases for ``worker_surface.unstored_fingerprints``, the check that every fingerprint the engine records
    names a stored tree (the worker-surface test runs it over a project's whole flow): a value a non-writer computed,
    recorded, is found; a writer's is not."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
    import worker_surface

    ws, _, _ = edits(tmp_path)
    with as_kind("reader"):
        reader = F.relevant_inputs_fingerprint(ws)
    write(ws, ".aew/work/T-1.yaml", f"snapshot: {reader}\n")
    recorded, unstored = worker_surface.unstored_fingerprints(ws)
    assert recorded == {reader.removeprefix("git-tree:")} and unstored == [reader.removeprefix("git-tree:")]
    writer = F.relevant_inputs_fingerprint(ws)  # the same tree, now stored by a writer
    assert writer == reader and worker_surface.unstored_fingerprints(ws)[1] == []


def test_working_diff_stores_what_it_reads_in_any_process_and_still_gives_the_diff(tmp_path):
    """Flagged (no caller in src): it reads blob content, so it stores the blobs it adds, even in a reader."""
    ws, base, _ = edits(tmp_path)
    with as_kind("reader"):
        assert "brand new" in F.working_diff(ws, base)
