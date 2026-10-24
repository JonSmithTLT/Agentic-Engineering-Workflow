"""Evaluated-snapshot identity (WC §9.9; KC §11; ADR-0002).

An evaluated snapshot identifies the engineering inputs actually evaluated,
including relevant uncommitted changes:

    base_revision               HEAD commit of the workspace (may be None in an empty repo)
    workspace_id                attributable workspace identity
    relevant_inputs_fingerprint git tree id of the working state, synthesized in a
                                temporary index: tracked + untracked-not-ignored files,
                                plus policy-declared ignored inputs, minus the AEW
                                knowledge root and policy exclusions
    artifact_digests            evaluated build artifact digests (optional)

Because ``.aew/`` is removed from the synthesized tree, writing an AEW report or
control file never changes the fingerprint of the evidence it records. Any change
to a relevant source/config/generated input does.

Known limits (documented, not hidden): dirty state *inside* submodules is not
captured (gitlinks record the submodule commit); Git LFS files contribute their
pointer; content that differs only by line endings normalized by git's filters
hashes identically (it would also commit identically).

A fingerprint is a read (STG-05 D-CS2-1; ADR-0002 amendment of 2026-10-23). In a non-writer process (a worker's
``aew``, the dashboard's server: :mod:`aew.process_kind`) nothing here writes an object: the temporary index is filled
with blob ids hashed and never stored (``update-index --info-only``, from the statuses ``git add -A`` itself acts on),
and every tree id is hashed in Python from the index entries (:func:`_tree_id`) instead of written by ``write-tree``.
So a reader computes a writer's value in its sandbox, where the real object store is read-only, and outside one,
where writing it would add loose objects nobody asked for; there is nothing private to bound or clean up. A store
writer keeps storing what it hashes (``git add -A``, ``write-tree``), with the same values: the reviewer's and
verifier's packs diff the base against the snapshot's tree, and a mutated workspace's refusal names the paths
between two snapshots, both read from the store (``engine.context_ops``, ``evidence_ops._paths_between``).
:func:`working_diff` stores what it adds in any process (it reads blob content; flagged: no caller in ``src``).

Index flags (review 2026-09-26 M3; ADR-0002 amendment). The temporary index
starts as a copy of the real one (for its stat cache), so flags that make Git
*skip reading* the working copy are neutralized there — never in the user's
real index: assume-unchanged bits are cleared, and core.ignoreStat,
core.fsmonitor and core.untrackedCache are forced off. Skip-worktree entries
(sparse checkout) are refused: their content is not in the workspace, so no
honest snapshot of it exists.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.errors import GitError, IntegrityError
from aew.workspace import git

AEW_ROOT_REL = ".aew"
NUL = "\x00"
# Windows device names: a file with one of these names (any extension, any case) cannot be read
# through the ordinary path, so ``git add`` fails on it ("short read"). Usually made by a bash
# ``> nul`` redirect on Windows.
WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))])
# Settings that let Git trust cached/filesystem-monitor state instead of reading files: forced off
# for snapshot synthesis (GIT_CONFIG_COUNT needs git >= 2.31, the supported floor).
READ_ALL_CONTENT = {
    "GIT_CONFIG_COUNT": "3",
    "GIT_CONFIG_KEY_0": "core.ignoreStat", "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "core.fsmonitor", "GIT_CONFIG_VALUE_1": "false",
    "GIT_CONFIG_KEY_2": "core.untrackedCache", "GIT_CONFIG_VALUE_2": "false",
}


def _stores_objects() -> bool:
    """Whether this process stores the objects a fingerprint hashes (D-CS2-1): a store writer does, as before; a
    non-writer never writes the repository's object store. The process's declared kind is behaviour, not the
    boundary (:mod:`aew.process_kind`): in a reader's sandbox the store is read-only whatever a process declares."""
    from aew import process_kind

    return process_kind.kind() != process_kind.NON_WRITER


@dataclass(frozen=True)
class _Index:
    """A throwaway index (its git environment), and whether the objects hashed into it are stored."""

    workspace: Path
    env: dict[str, str]
    stores: bool

    def add_forced(self, path: str) -> None:
        """``git add -f -- path``: every untracked file under ``path``, ignored or not."""
        if self.stores:
            git.git("add", "-f", "--", path, cwd=self.workspace, env=self.env)
        else:
            _add(self.workspace, self.env, git.git("ls-files", "-z", "--others", "--", path, cwd=self.workspace,
                                                   env=self.env).stdout.split(b"\0"))

    def tree(self, *, intent_to_add: bool = False) -> str:
        """The tree id ``write-tree`` gives this index; stored only by a process that stores objects."""
        if self.stores:
            return git.out("write-tree", cwd=self.workspace, env=self.env)
        return _tree_id(self.workspace, self.env, intent_to_add=intent_to_add)


@contextmanager
def _working_index(workspace: Path, *, skip_aew: bool = False, stores: bool | None = None) -> Iterator[_Index]:
    """A throwaway index holding the complete working state (tracked + untracked-not-ignored). With ``skip_aew``,
    ``.aew/``'s working files are not read at all (the caller removes ``.aew/`` from the tree anyway): in the
    authoritative checkout it can hold thousands of uncommitted records (ADR-0011 investigation §8.1). Its blobs are
    stored (``git add -A``) when ``stores`` (default: :func:`_stores_objects`), and otherwise only hashed
    (:func:`_stage`)."""
    stores = _stores_objects() if stores is None else stores
    real_index = Path(git.out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=workspace))
    tmpdir = Path(tempfile.mkdtemp(prefix="aew-idx-"))
    try:
        tmp_index = tmpdir / "index"
        if real_index.exists():
            shutil.copy2(real_index, tmp_index)  # reuse stat cache: fast on large trees
        env = {"GIT_INDEX_FILE": str(tmp_index), **READ_ALL_CONTENT}
        _neutralize_index_flags(workspace, env)
        spec = ["--", ".", *([f":(exclude){AEW_ROOT_REL}"] if skip_aew else [])]
        try:
            if stores:
                git.git("add", "-A", *spec, cwd=workspace, env=env)
            else:
                _stage(workspace, env, spec)
        except GitError:
            _refuse_reserved_names(workspace, env)
            raise
        yield _Index(workspace, env, stores)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _stage(workspace: Path, env: dict[str, str], spec: list[str]) -> None:
    """What ``git add -A <spec>`` does to the index in ``env``, writing no object (D-CS2-1). The tracked paths come with
    the statuses ``add -A`` acts on (``diff-files``, which reports a file replaced by a directory as deleted): a
    deleted one is removed, any other (modified, type-changed, unmerged) re-added. Then every untracked path that is
    not ignored is added; a trailing ``/`` marks an embedded repository, recorded as its commit, as ``add -A`` does.
    ``--info-only`` hashes through the same filters and stores nothing; ``--replace`` lets a path take the place of a
    file or directory it conflicts with."""
    raw = git.git("diff-files", "-z", "--name-status", "--no-renames", *spec, cwd=workspace, env=env).stdout
    fields = raw.split(b"\0")
    status = dict(zip(fields[1::2], fields[0::2], strict=False))
    status.pop(b"", None)
    gone = [p for p, s in status.items() if s == b"D"]
    if gone:
        git.git("update-index", "--force-remove", "-z", "--stdin", cwd=workspace, env=env,
                input=b"\0".join(gone) + b"\0")
    others = git.git("ls-files", "-z", "--others", "--exclude-standard", *spec, cwd=workspace, env=env).stdout
    _add(workspace, env, [*(p for p, s in status.items() if s != b"D"), *others.split(b"\0")])


def _add(workspace: Path, env: dict[str, str], paths: list[bytes]) -> None:
    """Hash ``paths`` into the index in ``env`` without storing a blob (``git add`` without the object write). On
    Windows a file named after a device is refused by name before anything is hashed: ``update-index`` would read
    the device itself, where ``git add`` failed on it ("short read")."""
    paths = list(dict.fromkeys(p.rstrip(b"/") for p in paths if p))
    if sys.platform == "win32" and (found := reserved_device_names([p.decode("utf-8", "replace") for p in paths])):
        raise _device_named(workspace, found)
    if paths:
        git.git("update-index", "--add", "--replace", "--info-only", "-z", "--stdin", cwd=workspace, env=env,
                input=b"\0".join(paths) + b"\0")


def reserved_device_names(paths: list[str]) -> list[str]:
    """The paths whose last component is a Windows device name (``nul``, ``con.txt``, ``LPT1``, ...)."""
    def stem(path: str) -> str:
        return path.rsplit("/", 1)[-1].split(".", 1)[0].rstrip(" ").upper()
    return [p for p in paths if stem(p) in WINDOWS_RESERVED_NAMES]


def _refuse_reserved_names(workspace: Path, env: dict[str, str]) -> None:
    """After ``git add`` failed: if untracked files with device names explain it, refuse naming them."""
    proc = git.git("ls-files", "--others", "--exclude-standard", "-z", cwd=workspace, env=env, check=False)
    if proc.returncode != 0:
        return
    found = reserved_device_names([p for p in proc.stdout.decode("utf-8", "replace").split(NUL) if p])
    if found:
        raise _device_named(workspace, found)


def _device_named(workspace: Path, found: list[str]) -> IntegrityError:
    return IntegrityError(
        f"the workspace contains a file named after a Windows device ({', '.join(found[:5])}), which git "
        "cannot read, so no snapshot can be taken. It is usually left by a `> nul` redirect in bash on "
        "Windows; delete it and retry", workspace=str(workspace), paths=found[:20], count=len(found))


def _neutralize_index_flags(workspace: Path, env: dict[str, str]) -> None:
    """In the temporary index only: clear assume-unchanged; refuse skip-worktree (sparse) entries."""
    assumed, sparse = [], []
    for rec in git.out("ls-files", "-v", "-z", cwd=workspace, env=env).split(NUL):
        if len(rec) < 3:
            continue
        tag, path = rec[0], rec[2:]
        if tag.upper() == "S":
            sparse.append(path)
        elif tag.islower():
            assumed.append(path)
    if sparse:
        raise IntegrityError(
            "the workspace has skip-worktree (sparse checkout) entries; their content is not in the workspace, "
            "so an evaluated snapshot cannot include it. Use a full checkout for AEW workspaces",
            workspace=str(workspace), paths=sparse[:20], count=len(sparse))
    if assumed:
        git.git("update-index", "--no-assume-unchanged", "-z", "--stdin", cwd=workspace, env=env,
                input=(NUL.join(assumed) + NUL).encode("utf-8"))


def relevant_inputs_fingerprint(
    workspace: Path,
    *,
    exclude: list[str] | None = None,
    include_ignored: list[str] | None = None,
) -> str:
    workspace = workspace.resolve()
    with _working_index(workspace, skip_aew=True) as idx:
        for path in [AEW_ROOT_REL, *(exclude or [])]:
            git.git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", path, cwd=workspace, env=idx.env)
        for path in include_ignored or []:
            if (workspace / path).exists():
                idx.add_forced(path)
        tree = idx.tree()
    return f"git-tree:{tree}"


def working_tree_id(workspace: Path) -> str:
    """Tree id of everything Git would keep in a workspace, read from content.

    Tracked plus untracked-not-ignored files — nothing excluded, ``.aew/`` included — built in the
    same flag-neutralized temporary index as the fingerprint, so an assume-unchanged edit cannot
    hide (re-review B1). Compared with ``HEAD^{tree}`` it answers "does this workspace hold anything
    beyond its HEAD commit?". Raises :class:`IntegrityError` for sparse (skip-worktree) entries,
    whose content is absent and so cannot be compared; callers must treat that as "unknown".
    """
    workspace = workspace.resolve()
    with _working_index(workspace) as idx:
        return idx.tree()


def index_tree_id(workspace: Path) -> str:
    """Tree id of the workspace's index exactly as staged, hashed from a copy (the real index is untouched).

    The complement of :func:`working_tree_id`, which reads working-file content and therefore cannot
    see a change that exists only in the index (staged, then the working file restored) — foundation
    review. Raises :class:`GitError` for unmerged entries; callers treat that as "unknown".
    """
    workspace = workspace.resolve()
    with _staged_index(workspace) as idx:
        return idx.tree(intent_to_add=True)


@contextmanager
def _staged_index(workspace: Path) -> Iterator[_Index]:
    """A throwaway copy of the workspace's index, as staged."""
    real_index = Path(git.out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=workspace))
    tmpdir = Path(tempfile.mkdtemp(prefix="aew-idx-"))
    try:
        tmp_index = tmpdir / "index"
        if real_index.exists():
            shutil.copy2(real_index, tmp_index)
        yield _Index(workspace, {"GIT_INDEX_FILE": str(tmp_index)}, _stores_objects())
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _entries(workspace: Path, env: dict[str, str], *, intent_to_add: bool = False) -> dict[bytes, tuple[bytes, bytes]]:
    """{path: (mode, object id)} of the index in ``env``, as ``write-tree`` would take them: an entry at a stage above
    0 is refused with :class:`GitError`, as ``write-tree`` refuses it, and with ``intent_to_add`` an intent-to-add
    entry is left out, as ``write-tree`` leaves it out (``ls-files`` shows it as the empty blob). After
    :func:`_stage` none is left: a file present is added, one absent removed."""
    out: dict[bytes, tuple[bytes, bytes]] = {}
    for rec in git.git("ls-files", "-s", "-z", cwd=workspace, env=env).stdout.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, oid, stage = meta.split()
        if stage != b"0":
            raise GitError(f"the index has unmerged entries ({path.decode('utf-8', 'replace')}), so it has no tree",
                           cwd=str(workspace))
        out[path] = (mode, oid)
    if intent_to_add and out:
        for path in _intent_to_add(workspace, env):
            out.pop(path, None)
    return out


def _intent_to_add(workspace: Path, env: dict[str, str]) -> set[bytes]:
    """The intent-to-add entries of the index in ``env``: what a diff against the empty tree lists, minus what it lists
    once they are invisible (git >= 2.17; CS-2 plan, measured 2026-10-23)."""
    empty = _hash(_object_format(workspace), b"tree", b"")

    def listed(*flags: str) -> set[bytes]:
        raw = git.git("diff-index", "--cached", "--name-only", "--no-renames", "-z", *flags, empty, cwd=workspace,
                      env=env).stdout
        return {p for p in raw.split(b"\0") if p}

    return listed() - listed("--ita-invisible-in-index")


def _tree_id(workspace: Path, env: dict[str, str], *, intent_to_add: bool = False) -> str:
    """The id ``git write-tree`` would give the index in ``env``, hashed here and stored nowhere (D-CS2-1). Git's tree
    format: an entry is ``<mode> <name>\\0<raw id>``, a tree's mode ``40000``, and entries sort by name with a
    directory's compared as its name plus ``/`` (so files ``a-b`` and ``a.txt`` come before directory ``a``). A
    directory left with no entry is left out, as ``write-tree`` leaves it out."""
    fmt = _object_format(workspace)
    root: dict[bytes, Any] = {}
    for path, entry in _entries(workspace, env, intent_to_add=intent_to_add).items():
        *dirs, name = path.split(b"/")
        node = root
        for d in dirs:
            node = node.setdefault(d, {})
        node[name] = entry

    def tree(node: dict[bytes, Any]) -> bytes | None:
        rows = []
        for name, child in node.items():
            if isinstance(child, dict):
                oid = tree(child)
                if oid is not None:
                    rows.append((name + b"/", b"40000 " + name + b"\0" + oid))
            else:
                mode, oid_hex = child
                rows.append((name, mode + b" " + name + b"\0" + bytes.fromhex(oid_hex.decode())))
        if not rows and node is not root:
            return None
        return bytes.fromhex(_hash(fmt, b"tree", b"".join(row for _, row in sorted(rows))))

    return (tree(root) or b"").hex()


def _object_format(workspace: Path) -> str:
    """The repository's object format, ``sha1`` or ``sha256`` (a hashlib name)."""
    return git.out("rev-parse", "--show-object-format", cwd=workspace) or "sha1"


def _hash(fmt: str, kind: bytes, body: bytes) -> str:
    """The id of a ``kind`` object holding ``body``, in object format ``fmt``."""
    return hashlib.new(fmt, kind + b" " + str(len(body)).encode() + b"\0" + body).hexdigest()


def head_tree_id(workspace: Path) -> str:
    head = git.rev_parse("HEAD", cwd=workspace)
    return (git.out("rev-parse", f"{head}^{{tree}}", cwd=workspace) if head
            else _hash(_object_format(workspace), b"tree", b""))  # an empty repository: the empty tree


def _changed(a: dict[bytes, tuple[bytes, bytes]], b: dict[bytes, tuple[bytes, bytes]]) -> set[str]:
    """The paths whose entry (mode and object id) differs between two listings: what ``git diff --name-only
    --no-renames`` says of their trees, without needing either tree in a store."""
    return {p.decode("utf-8", "replace") for p in a.keys() | b.keys() if a.get(p) != b.get(p)}


def _head_entries(workspace: Path) -> dict[bytes, tuple[bytes, bytes]]:
    """{path: (mode, object id)} of HEAD's tree (empty in an empty repository)."""
    if git.rev_parse("HEAD", cwd=workspace) is None:
        return {}
    out = {}
    for rec in git.git("ls-tree", "-r", "-z", "--full-tree", "HEAD", cwd=workspace).stdout.split(b"\0"):
        if rec:
            meta, path = rec.split(b"\t", 1)
            mode, _, oid = meta.split()
            out[path] = (mode, oid)
    return out


def index_only_paths(workspace: Path) -> list[str]:
    """Paths whose staged index entry matches neither HEAD nor the working copy.

    That staged content exists nowhere else: ``git add`` of the working state would overwrite it and
    removing the worktree would drop it. Compared entry by entry: the trees are hashed, not stored (D-CS2-1).
    """
    workspace = workspace.resolve()
    with _staged_index(workspace) as idx:
        index = _entries(workspace, idx.env, intent_to_add=True)
    with _working_index(workspace) as idx:
        work = _entries(workspace, idx.env)
    return sorted(_changed(_head_entries(workspace), index) & _changed(index, work))


def evaluated_snapshot(
    workspace: Path,
    workspace_id: str,
    *,
    exclude: list[str] | None = None,
    include_ignored: list[str] | None = None,
    artifact_digests: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "base_revision": git.rev_parse("HEAD", cwd=workspace),
        "workspace_id": workspace_id,
        "relevant_inputs_fingerprint": relevant_inputs_fingerprint(
            workspace, exclude=exclude, include_ignored=include_ignored),
        "artifact_digests": list(artifact_digests or []),
    }


def changed_paths(workspace: Path, base: str) -> list[str]:
    """Paths differing between ``base`` and the working state, including untracked files.

    Deliberately *includes* the AEW root so guardrails can reject a Ticket that touches it.
    """
    workspace = workspace.resolve()
    with _working_index(workspace) as idx:  # the names only: the diff reads no blob, stored or not
        raw = git.out("diff", "--cached", "--name-only", "--no-renames", "-z", base, cwd=workspace, env=idx.env)
    return [p for p in raw.split(NUL) if p]


def working_diff(workspace: Path, base: str) -> str:
    """Unified diff of base..working state (incl. untracked files), excluding the AEW root.

    It stores the blobs it adds (``git add -A``) in any process: a unified diff reads their content. No reader reaches
    it, and nothing in ``src`` calls it: it is flagged under "requirements are the authority" (STG-05 CS-2), its
    keep-or-remove question with the designer and the operator."""
    workspace = workspace.resolve()
    with _working_index(workspace, stores=True) as idx:
        git.git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", AEW_ROOT_REL, cwd=workspace, env=idx.env)
        return git.git("diff", "--cached", "--no-color", "--no-renames", base, cwd=workspace,
                       env=idx.env).stdout.decode("utf-8", "replace")
