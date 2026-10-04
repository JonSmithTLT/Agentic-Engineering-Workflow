"""Git mechanics for controlled integration (WC §8.1, §13; ADR-0004, D-op-2).

validate, then publish:

1. commit the gated Ticket workspace (its tree must equal the gated fingerprint);
2. build candidate M from authoritative commit H in a detached integration worktree;
3. (post-integration verification runs against M — engine/roles, not here);
4. publish with an atomic compare-and-swap on the authoritative ref
   (``git update-ref <ref> M H``): it succeeds only if the ref is still H;
5. sync the authoritative worktree: force exactly the paths changed between H
   and M to M. Other paths — including dirty ``.aew/`` control files — are
   untouched.

Synchronization compares *complete* Git entries (mode + object id) of the
index and of the working copy against H and M — never only blob content, and
never through ``git diff`` (which honours assume-unchanged/skip-worktree flags
and could hide a local edit). Every path is classified before anything is
written: a path whose index entry or working copy is neither H's nor M's
belongs to someone else and the whole sync is refused (review 2026-09-26 B2,
M6). Sync is idempotent from every intermediate {H, M} state a crash can leave.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.errors import GitError, IntegrityError, StaleCandidate
from aew.snapshot import fingerprint
from aew.workspace import git

AEW_EXCLUDE = ":(exclude).aew"
LITERAL = {"GIT_LITERAL_PATHSPECS": "1"}

# (mode, object id). A directory is represented by TREE so file <-> directory
# transitions classify cleanly; ``None`` means "absent".
Entry = tuple[str, str]
TREE: Entry = ("040000", "tree")
GITLINK_MODE = "160000"
SYMLINK_MODE = "120000"


def commit_workspace(workspace: Path, message: str) -> str:
    """Commit all non-AEW working changes in a Ticket workspace; return HEAD.

    Refuses, before touching the index, when committing would lose work:

    * paths flagged assume-unchanged/skip-worktree — `git add` would silently leave their edits out of
      the Ticket commit (re-review B1); the flags are reported, never cleared on the user's behalf;
    * staged content that matches neither HEAD nor the working copy — `git add` would overwrite it, and
      it exists nowhere else (foundation review).
    """
    flagged = [p for p, f in index_flags(workspace, None).items() if not p.startswith(".aew/")]
    if flagged:
        raise IntegrityError(
            "the Ticket workspace index marks paths assume-unchanged/skip-worktree, so their edits would be left "
            "out of the Ticket commit; clear the flags (git update-index --no-assume-unchanged / "
            "--no-skip-worktree) and prepare again", workspace=str(workspace), paths=flagged[:50])
    index_only = [p for p in fingerprint.index_only_paths(workspace) if not p.startswith(".aew/")]
    if index_only:
        raise IntegrityError(
            "the Ticket workspace index holds staged content that matches neither HEAD nor the working copy; "
            "committing the evaluated working state would overwrite it. Put the intended content in the working "
            "copy (and re-verify) or drop the staged version (git restore --staged), then prepare again",
            workspace=str(workspace), paths=index_only[:50])
    status = git.out("status", "--porcelain", "--untracked-files=normal", "--", ".", AEW_EXCLUDE, cwd=workspace)
    if status:
        git.git("add", "-A", "--", ".", AEW_EXCLUDE, cwd=workspace)
        git.git("commit", "-q", "--no-verify", "-m", message, cwd=workspace, env=git.identity_env(workspace))
    head = git.rev_parse("HEAD", cwd=workspace)
    assert head
    return head


def merge_candidate(repo_root: Path, int_path: Path, ticket_commit: str, message: str) -> dict[str, Any]:
    """Merge the Ticket commit into the detached integration worktree (at H). Returns M or a conflict."""
    proc = git.git("merge", "--no-ff", "--no-edit", "-m", message, ticket_commit, cwd=int_path, check=False,
                   env=git.identity_env(repo_root))
    if proc.returncode != 0:
        conflicts = git.out("diff", "--name-only", "--diff-filter=U", cwd=int_path)
        git.git("merge", "--abort", cwd=int_path, check=False)
        return {"conflict": True, "paths": [p for p in conflicts.splitlines() if p],
                "stderr": proc.stderr.decode("utf-8", "replace")[-2000:]}
    return {"conflict": False, "commit": git.rev_parse("HEAD", cwd=int_path)}


def changed_between(repo_root: Path, a: str, b: str) -> list[str]:
    raw = git.out("diff", "--name-only", "--no-renames", "-z", a, b, cwd=repo_root)
    return [p for p in raw.split("\x00") if p]


def _chunks(items: list[str], n: int = 200) -> list[list[str]]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def authoritative_worktree_applies(repo_root: Path, branch: str) -> bool:
    return git.current_branch(repo_root) == branch


def cas_publish(repo_root: Path, ref: str, new: str, expected_old: str, message: str) -> None:
    proc = git.git("update-ref", "-m", message, ref, new, expected_old, cwd=repo_root, check=False)
    if proc.returncode != 0:
        current = git.rev_parse(ref, cwd=repo_root)
        raise StaleCandidate(
            "the authoritative ref moved since the candidate was built; rebuild and revalidate",
            ref=ref, expected=expected_old, current=current, stderr=proc.stderr.decode("utf-8", "replace").strip())


# ---------------------------------------------------------------------- entry-level state


def _config_bool(repo_root: Path, key: str, default: bool) -> bool:
    proc = git.git("config", "--type=bool", "--get", key, cwd=repo_root, check=False)
    value = proc.stdout.decode().strip()
    return default if proc.returncode != 0 or not value else value == "true"


def tree_entries(repo_root: Path, commit: str, paths: list[str]) -> dict[str, Entry | None]:
    """Entries of ``paths`` in ``commit`` (``None`` if absent, ``TREE`` for a directory)."""
    found: dict[str, Entry | None] = {p: None for p in paths}
    for chunk in _chunks(paths):
        raw = git.git("ls-tree", "-z", commit, "--", *chunk, cwd=repo_root, env=LITERAL).stdout.decode("utf-8")
        for rec in raw.split("\x00"):
            if not rec:
                continue
            meta, _, path = rec.partition("\t")
            mode, kind, oid = meta.split()
            if path in found:
                found[path] = TREE if kind == "tree" else (mode, oid)
    return found


def index_entries(repo_root: Path, paths: list[str]) -> tuple[dict[str, Entry | None], list[str]]:
    """Stage-0 index entries of ``paths``; also returns the paths with unmerged (stage > 0) entries."""
    found: dict[str, Entry | None] = {p: None for p in paths}
    wanted = set(paths)
    unmerged: set[str] = set()
    for chunk in _chunks(paths):
        raw = git.git("ls-files", "-s", "-z", "--", *chunk, cwd=repo_root, env=LITERAL).stdout.decode("utf-8")
        for rec in raw.split("\x00"):
            if not rec:
                continue
            meta, _, path = rec.partition("\t")
            mode, oid, stage = meta.split()
            if path in wanted:
                if stage != "0":
                    unmerged.add(path)
                else:
                    found[path] = (mode, oid)
            else:  # an entry *under* a requested path: that path is a directory in the index
                for p in chunk:
                    if path.startswith(p + "/") and found[p] is None:
                        found[p] = TREE
    return found, sorted(unmerged)


def index_flags(repo_root: Path, paths: list[str] | None) -> dict[str, list[str]]:
    """Index flags that suppress Git's reading of the working copy (assume-unchanged, skip-worktree).

    ``paths=None`` inspects the whole index.
    """
    flagged: dict[str, list[str]] = {}
    wanted = set(paths or [])
    for chunk in (_chunks(paths) if paths is not None else [[]]):
        raw = git.git("ls-files", "-v", "-z", "--", *chunk, cwd=repo_root, env=LITERAL).stdout.decode("utf-8")
        for rec in raw.split("\x00"):
            if len(rec) < 3 or (paths is not None and rec[2:] not in wanted):
                continue
            tag, path = rec[0], rec[2:]
            flags = []
            if tag.islower():
                flags.append("assume-unchanged")
            if tag.upper() == "S":
                flags.append("skip-worktree")
            if flags:
                flagged[path] = flags
    return flagged


def worktree_entries(repo_root: Path, paths: list[str]) -> dict[str, Entry | None]:
    """What the working copy holds at each path, hashed the way ``git add`` would (clean filters apply)."""
    found: dict[str, Entry | None] = {}
    regular: list[str] = []
    modes: dict[str, str] = {}
    for p in paths:
        target = repo_root / p
        if target.is_symlink():
            link = os.readlink(target)
            oid = git.git("hash-object", "--stdin", cwd=repo_root,
                          input=os.fsencode(link)).stdout.decode().strip()
            found[p] = (SYMLINK_MODE, oid)
        elif target.is_dir():
            found[p] = TREE
        elif target.is_file():
            if "\n" in p:
                raise IntegrityError("paths containing newlines are not supported by worktree sync", path=p)
            regular.append(p)
            modes[p] = "100755" if target.stat().st_mode & 0o100 else "100644"
        else:
            found[p] = None
    for chunk in _chunks(regular):
        oids = git.git("hash-object", "--stdin-paths", cwd=repo_root,
                       input=("\n".join(chunk) + "\n").encode("utf-8")).stdout.decode().split()
        for p, oid in zip(chunk, oids, strict=True):
            found[p] = (modes[p], oid)
    return found


@dataclass(frozen=True)
class _Filesystem:
    filemode: bool  # core.fileMode: is the executable bit meaningful in this checkout?
    symlinks: bool  # core.symlinks: are symlinks real, or plain files holding the target?

    def matches(self, have: Entry | None, want: Entry | None) -> bool:
        """Does the working copy ``have`` represent the Git entry ``want`` on this filesystem?"""
        if have is None or want is None:
            return have == want
        if have == TREE or want == TREE:
            return have == want
        (hmode, hoid), (wmode, woid) = have, want
        if hoid != woid:
            return False
        if wmode == SYMLINK_MODE or hmode == SYMLINK_MODE:
            # Without core.symlinks a symlink is checked out as a plain file holding its target.
            return hmode == wmode or (not self.symlinks and {hmode, wmode} <= {SYMLINK_MODE, "100644", "100755"})
        return hmode == wmode or not self.filemode


@dataclass
class _PathStates:
    base: dict[str, Entry | None]
    new: dict[str, Entry | None]
    index: dict[str, Entry | None]
    worktree: dict[str, Entry | None]
    unmerged: list[str]
    flags: dict[str, list[str]]
    fs: _Filesystem

    def unsupported(self, paths: list[str]) -> dict[str, str]:
        out: dict[str, str] = {p: "unmerged index entry" for p in self.unmerged}
        for p, flags in self.flags.items():
            out[p] = f"index flag {'+'.join(flags)} (clear it so Git reads the working copy)"
        for p in paths:
            if any(e is not None and e != TREE and e[0] == GITLINK_MODE
                   for e in (self.base[p], self.new[p], self.index[p])):
                out[p] = "submodule (gitlink) paths are not synced in M1"
        return out


def _states(repo_root: Path, base: str, new: str | None, paths: list[str]) -> _PathStates:
    index, unmerged = index_entries(repo_root, paths)
    return _PathStates(
        base=tree_entries(repo_root, base, paths),
        new=tree_entries(repo_root, new, paths) if new else {p: None for p in paths},
        index=index,
        worktree=worktree_entries(repo_root, paths),
        unmerged=unmerged,
        flags=index_flags(repo_root, paths),
        fs=_Filesystem(filemode=_config_bool(repo_root, "core.fileMode", True),
                       symlinks=_config_bool(repo_root, "core.symlinks", True)),
    )


def precheck_sync(repo_root: Path, base: str, paths: list[str]) -> None:
    """Before publishing: every path the integration changes must be exactly H in both index and working copy."""
    st = _states(repo_root, base, None, paths)
    problems = st.unsupported(paths)
    for p in paths:
        if p not in problems and (st.index[p] != st.base[p] or not st.fs.matches(st.worktree[p], st.base[p])):
            problems[p] = "local change (staged or unstaged) on a path this integration changes"
    if problems:
        raise IntegrityError(
            "the authoritative worktree has local changes on paths this integration changes; "
            "commit/stash them (and clear index flags), then publish again — or, if a publish was interrupted, "
            "run `aew integrate reconcile`",
            paths=dict(sorted(problems.items())[:50]))


def _is_file(e: Entry | None) -> bool:
    return e is not None and e != TREE


def _allowed(st: _PathStates, p: str) -> tuple[Entry | None, ...]:
    """Entries a crash-interrupted sync may leave at ``p``: H's, M's, and — around a
    file <-> directory transition — the empty state between removing one and creating the other."""
    ends = (st.base[p], st.new[p])
    return ends + ((None,) if TREE in ends else ())


def _classify_for_sync(st: _PathStates, paths: list[str]) -> dict[str, str]:
    problems = st.unsupported(paths)
    for p in paths:
        if p in problems:
            continue
        allowed = _allowed(st, p)
        if st.index[p] not in allowed:
            problems[p] = "staged content matches neither the pre-integration nor the integrated commit"
        elif not any(st.fs.matches(st.worktree[p], e) for e in allowed):
            problems[p] = "working copy matches neither the pre-integration nor the integrated commit"
    return problems


def _converged(st: _PathStates, p: str) -> bool:
    want = st.new[p]
    if _is_file(want):
        return st.index[p] == want and st.fs.matches(st.worktree[p], want)
    # Absent (or a directory) in M: no file entry may remain at p itself.
    return not _is_file(st.index[p]) and not _is_file(st.worktree[p])


def _prune_empty_parents(repo_root: Path, path: Path) -> None:
    parent = path.parent
    root = repo_root.resolve()
    while parent.resolve() != root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def sync_worktree(repo_root: Path, base: str, new: str, paths: list[str], *, on_first=None) -> dict[str, Any]:
    """Force exactly ``paths`` to ``new`` in the authoritative index and working copy (idempotent).

    Every path is classified first; if any index entry or working copy belongs to neither ``base``
    nor ``new``, nothing is written and :class:`IntegrityError` names the paths.
    """
    st = _states(repo_root, base, new, paths)
    problems = _classify_for_sync(st, paths)
    if problems:
        raise IntegrityError(
            "refusing to overwrite local work in the authoritative worktree on paths this integration changes; "
            "commit/stash it (and clear index flags), then run `aew integrate reconcile`",
            paths=dict(sorted(problems.items())[:50]))
    removals = [p for p in paths if not _is_file(st.new[p])
                and (_is_file(st.index[p]) or _is_file(st.worktree[p]))]
    updates = [p for p in paths if _is_file(st.new[p])
               and (st.index[p] != st.new[p] or not st.fs.matches(st.worktree[p], st.new[p]))]
    # Removals first, so a file -> directory transition has room for the new tree.
    for chunk in _chunks([p for p in removals if _is_file(st.index[p])]):
        git.git("rm", "-q", "--cached", "--ignore-unmatch", "--", *chunk, cwd=repo_root, env=LITERAL)
    for p in removals:
        if _is_file(st.worktree[p]):
            target = repo_root / p
            target.unlink(missing_ok=True)
            _prune_empty_parents(repo_root, target)
    for i, chunk in enumerate(_chunks(updates)):
        # `checkout <commit> -- <paths>` writes the index entry *and* the working copy, including mode.
        git.git("checkout", new, "--", *chunk, cwd=repo_root, env=LITERAL)
        if i == 0 and on_first:
            on_first()
    if st.fs.filemode:  # belt and braces: materialize an executable-bit change checkout left behind
        after = worktree_entries(repo_root, updates)
        for p in updates:
            want, have = st.new[p], after[p]
            if want is None or have is None or not _is_file(have):
                continue
            if want[0] in {"100644", "100755"} and have[0] != want[0]:
                mode = (repo_root / p).stat().st_mode
                os.chmod(repo_root / p, mode | 0o111 if want[0] == "100755" else mode & ~0o111)
    final = _states(repo_root, base, new, paths)
    stuck = [p for p in paths if not _converged(final, p)]
    if stuck:
        raise GitError("authoritative worktree did not converge to the integrated commit", paths=stuck[:50])
    return {"synced": len(removals) + len(updates), "paths": len(paths)}
