"""Crash-safe, stale-writer-resistant persistence for authoritative control state.

Implements WC §5 (crash-safe control-authority rule), WC §8.2 and KC §12.3.

Model (ADR-0001):

* ``state/control.yaml`` is the single atomic **commit point**. It ends with a
  ``# aew-checksum sha256:<hex>`` trailer so external truncation/damage is
  detected instead of silently parsed.
* A transition may also create or replace other files (records, decisions,
  the manifest). Those writes are first **staged** in a redo record
  ``state/txn/<rev>.yaml`` (fsynced) that the new control state references by
  hash. Only after the control file is atomically replaced are the writes
  **applied**. Recovery rolls a committed-but-unapplied transaction forward
  and discards staged transactions that never committed. A crash therefore
  exposes either the previous valid state or the complete new state.
* Roll-forward is idempotent and conservative: a target is written only if it
  still has its pre-transaction content (or is at the post content already);
  anything else is an out-of-band modification and fails closed.
* Every operation (read or write) runs under an OS advisory lock and first
  performs recovery. Revision checks happen inside the lock (compare-and-swap).
* The transition log ``state/log/<rev>.yaml`` and derived views (for example
  ``state/CURRENT.md``) are rebuilt from committed state; they are never
  authoritative.
* ``after_apply(state)`` runs inside the lock once a state's writes are known to
  be on disk — after redo recovery and after each commit's apply, before the
  post-commit render — so callers can load files a transition may have
  replaced (the project manifest) from the same coherent snapshot (review
  2026-09-26 M8).
* A process keeps its last parse of ``control.yaml`` together with the SHA-256
  of the bytes it parsed. Every read still reads the file; only bytes identical
  to the ones already parsed and verified reuse that parse (parsing is
  deterministic, so this is exactly a re-parse), and any other bytes get a full
  parse with checksum and schema validation. Long-lived processes (a run's
  supervisor, the Lead broker) poll the state, and several commands read it more
  than once (M3 step 7, ``m3-performance.md``).
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew import profile
from aew.engine import faults
from aew.engine.lock import FileLock
from aew.errors import AEWError, IntegrityError, ProjectNotFound, StaleRevision
from aew.schemas import validate
from aew.util import (
    atomic_write,
    create_exclusive,
    dump_yaml,
    fsync_dir,
    load_yaml,
    replace_with_retry,
    sha256_bytes,
    sha256_file,
    utc_now,
    write_temp,
)

CHECKSUM_PREFIX = "# aew-checksum sha256:"
CONTROL_REL = "state/control.yaml"
TXN_DIR = "state/txn"
LOG_DIR = "state/log"
LOCK_REL = "local/control.lock"

Renderer = Callable[[dict[str, Any]], dict[str, str]]
AfterApply = Callable[[dict[str, Any]], None]


@dataclass
class PendingWrite:
    path: str  # POSIX path relative to the AEW root
    content: str
    immutable: bool


@dataclass
class Transition:
    """What a committed control transition records about itself."""

    op: str
    actor: dict[str, Any]
    summary: str | None = None
    reason: str | None = None
    refs: list[str] = field(default_factory=list)


def serialize_control(state: dict[str, Any]) -> bytes:
    body = dump_yaml(state)
    return (body + f"{CHECKSUM_PREFIX}{sha256_bytes(body.encode('utf-8'))}\n").encode("utf-8")


def deserialize_control(raw: bytes, *, source: str) -> dict[str, Any]:
    text = raw.decode("utf-8")
    body, sep, trailer = text.rstrip("\n").rpartition("\n")
    if not sep or not trailer.startswith(CHECKSUM_PREFIX):
        raise IntegrityError(f"{source}: missing checksum trailer (damaged or edited outside AEW)")
    body += "\n"
    expected = trailer[len(CHECKSUM_PREFIX):].strip()
    if sha256_bytes(body.encode("utf-8")) != expected:
        raise IntegrityError(f"{source}: checksum mismatch (damaged or edited outside AEW)")
    state = load_yaml(body, source=source)
    validate("control", state, source=source)
    return state


class Session:
    """A locked, recovered view of control state that may commit at most once."""

    def __init__(self, store: "ControlStore", state: dict[str, Any]) -> None:
        self._store = store
        self._committed_state = state  # the store's parse: never changed (``state`` is this session's copy)
        self.state = copy.deepcopy(state)
        self._writes: list[PendingWrite] = []
        self.committed_revision: int | None = None

    @property
    def revision(self) -> int:
        return self._committed_state["revision"]

    def base_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._committed_state)

    def write(self, path: str, content: str, *, immutable: bool = True) -> None:
        self._writes.append(PendingWrite(path, content, immutable))

    def commit(self, transition: Transition, *, expect_rev: int | None = None) -> int:
        if self.committed_revision is not None:
            raise AEWError("session already committed")
        if expect_rev is not None and expect_rev != self.revision:
            raise StaleRevision(
                f"expected control revision {expect_rev}, current is {self.revision}",
                expected=expect_rev,
                current=self.revision,
            )
        self.committed_revision = self._store._commit(self._committed_state, self.state, self._writes, transition)
        return self.committed_revision


class ControlStore:
    def __init__(self, aew_root: Path, *, renderer: Renderer | None = None, lock_timeout: float = 60.0,
                 after_apply: AfterApply | None = None) -> None:
        self.root = aew_root
        self.renderer = renderer
        self.lock_timeout = lock_timeout
        self.after_apply = after_apply
        self.held = 0  # > 0 while this process holds the control lock through this store
        self._parsed: tuple[str, dict[str, Any]] | None = None  # (sha256 of the bytes, their parse): read-only

    # ------------------------------------------------------------------ paths

    @property
    def control_path(self) -> Path:
        return self.root / CONTROL_REL

    def _abs(self, rel: str) -> Path:
        path = (self.root / rel).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise IntegrityError(f"write outside AEW root refused: {rel}")
        return path

    def exists(self) -> bool:
        return self.control_path.exists()

    # ------------------------------------------------------------------ public API

    @contextmanager
    def session(self) -> Iterator[Session]:
        with FileLock(self.root / LOCK_REL, timeout=self.lock_timeout):
            self.held += 1
            try:
                state = self._recover()
                yield Session(self, state)
            finally:
                self.held -= 1

    def read(self) -> dict[str, Any]:
        with FileLock(self.root / LOCK_REL, timeout=self.lock_timeout):
            self.held += 1
            try:
                return copy.deepcopy(self._recover())
            finally:
                self.held -= 1

    def create(self, state: dict[str, Any], files: dict[str, str]) -> None:
        """Initialize a project: write skeleton files, then publish revision 0.

        The exclusive creation of ``control.yaml`` is the commit point; an
        interrupted initialization leaves no control state and can be re-run.
        """
        with FileLock(self.root / LOCK_REL, timeout=self.lock_timeout):
            if self.control_path.exists():
                raise IntegrityError(f"{self.control_path} already exists; project is initialized")
            for rel, content in files.items():
                atomic_write(self._abs(rel), content)
            state = copy.deepcopy(state)
            state["revision"] = 0
            validate("control", state, source="initial control state")
            self.control_path.parent.mkdir(parents=True, exist_ok=True)
            create_exclusive(self.control_path, serialize_control(state))
            self._post_commit(state)

    # ------------------------------------------------------------------ commit

    def _commit(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        writes: list[PendingWrite],
        transition: Transition,
    ) -> int:
        profile.count("commit")
        with profile.phase("commit"):
            return self._commit_unprofiled(before, after, writes, transition)

    def _commit_unprofiled(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        writes: list[PendingWrite],
        transition: Transition,
    ) -> int:
        revision = before["revision"] + 1
        after["revision"] = revision
        staged = []
        for w in writes:
            target = self._abs(w.path)
            current = sha256_file(target)
            new_hash = sha256_bytes(w.content.encode("utf-8"))
            if w.immutable and current is not None and current != new_hash:
                raise IntegrityError(f"refusing to overwrite immutable record {w.path}")
            staged.append(
                {"path": w.path, "before": current, "after": new_hash, "immutable": w.immutable, "content": w.content}
            )

        txn_ref = None
        txn_bytes = b""
        if staged:
            txn_bytes = dump_yaml({"revision": revision, "writes": staged}).encode("utf-8")
            txn_ref = {
                "path": f"{TXN_DIR}/{revision:06d}.yaml",
                "sha256": sha256_bytes(txn_bytes),
                "writes": [{k: s[k] for k in ("path", "before", "after")} for s in staged],
            }
        after["last_transition"] = {
            "revision": revision,
            "at": utc_now(),
            "actor": transition.actor,
            "op": transition.op,
            "summary": transition.summary,
            "reason": transition.reason,
            "refs": list(transition.refs),
            "txn": txn_ref,
        }
        # Validate before anything touches disk so a rejected transition leaves no trace.
        validate("control", after, source=f"control state revision {revision}")
        control_bytes = serialize_control(after)

        faults.hit("txn.before_stage")
        if txn_ref:
            atomic_write(self._abs(txn_ref["path"]), txn_bytes)
        faults.hit("txn.after_stage")

        # The commit point: temp + fsync, then atomic replace of control.yaml.
        tmp = write_temp(self.control_path.parent, control_bytes, prefix=".control.yaml.")
        try:
            faults.hit("txn.before_replace")
            replace_with_retry(tmp, self.control_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        fsync_dir(self.control_path.parent)
        faults.hit("txn.after_replace")

        self._apply(staged, inject=True)
        faults.hit("txn.after_apply")
        if self.after_apply:
            self.after_apply(after)
        self._post_commit(after, inject=True)
        return revision

    # ------------------------------------------------------------------ recovery

    def _load(self) -> dict[str, Any]:
        """The committed state: this process's last parse when the file holds the very bytes it parsed, else a verified
        parse. The result is shared with the cache and must not be changed (a session changes its own copy)."""
        with profile.phase("parse"):
            try:
                raw = self.control_path.read_bytes()
            except FileNotFoundError:
                raise ProjectNotFound(f"no control state at {self.control_path}") from None
            digest = sha256_bytes(raw)
            if self._parsed is not None and self._parsed[0] == digest:
                profile.count("parse_cached")
                return self._parsed[1]
            profile.count("parse")
            profile.count("parse_bytes", len(raw))
            state = deserialize_control(raw, source=str(self.control_path))
            self._parsed = (digest, state)
            return state

    def _recover(self) -> dict[str, Any]:
        with profile.phase("recover"):
            return self._recover_unprofiled()

    def _recover_unprofiled(self) -> dict[str, Any]:
        self._remove_temp_files()
        state = self._load()
        revision = state["revision"]
        txn_dir = self._abs(TXN_DIR)
        # Discard staged transactions that never committed.
        if txn_dir.exists():
            for f in txn_dir.glob("*.yaml"):
                if f.stem.isdigit() and int(f.stem) > revision:
                    f.unlink()
        txn_ref = (state.get("last_transition") or {}).get("txn")
        if txn_ref:
            self._apply(self._load_txn(txn_ref))
        if self.after_apply:
            self.after_apply(state)
        self._post_commit(state)
        # The last committed transaction is fully applied; older redo records are spent.
        if txn_dir.exists():
            for f in txn_dir.glob("*.yaml"):
                if f.stem.isdigit() and int(f.stem) < revision:
                    f.unlink()
        return state

    def _load_txn(self, txn_ref: dict[str, Any]) -> list[dict[str, Any]]:
        path = self._abs(txn_ref["path"])
        pending = [w for w in txn_ref["writes"] if sha256_file(self._abs(w["path"])) != w["after"]]
        if not pending:
            return []
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise IntegrityError(
                "committed transaction has unapplied writes but its redo record is missing",
                txn=txn_ref["path"],
                pending=[w["path"] for w in pending],
            ) from None
        if sha256_bytes(raw) != txn_ref["sha256"]:
            raise IntegrityError(f"redo record {txn_ref['path']} is damaged")
        return load_yaml(raw.decode("utf-8"), source=txn_ref["path"])["writes"]

    def _apply(self, staged: list[dict[str, Any]], *, inject: bool = False) -> None:
        for i, w in enumerate(staged):
            target = self._abs(w["path"])
            current = sha256_file(target)
            if current == w["after"]:
                continue
            if current != w["before"]:
                raise IntegrityError(
                    f"{w['path']} was modified outside AEW while a transition was being applied",
                    path=w["path"],
                    expected_one_of=[w["before"], w["after"]],
                    found=current,
                )
            atomic_write(target, w["content"])
            if inject and i == 0:
                faults.hit("txn.mid_apply")

    def _post_commit(self, state: dict[str, Any], *, inject: bool = False) -> None:
        last = state.get("last_transition")
        if last:
            log_path = self._abs(f"{LOG_DIR}/{state['revision']:06d}.yaml")
            if not log_path.exists():
                atomic_write(log_path, dump_yaml(last))
        if inject:
            faults.hit("txn.after_log")
        if self.renderer:
            profile.count("render")
            with profile.phase("render"):
                for rel, content in self.renderer(state).items():
                    target = self._abs(rel)
                    data = content.encode("utf-8")
                    if sha256_file(target) != sha256_bytes(data):
                        atomic_write(target, data)
        if inject:
            faults.hit("txn.after_render")

    def _remove_temp_files(self) -> None:
        for directory in (self.root, self.root / "state", self.root / TXN_DIR, self.root / LOG_DIR):
            if not directory.is_dir():
                continue
            for f in directory.iterdir():
                if f.name.startswith(".") and f.name.endswith(".tmp") and f.is_file():
                    try:
                        f.unlink()
                    except OSError:
                        pass

    # ------------------------------------------------------------------ helpers for tests/doctor

    def verify(self) -> list[str]:
        """Return integrity problems without modifying anything."""
        problems = []
        try:
            self._load()
        except AEWError as exc:
            problems.append(f"{exc.code}: {exc.message}")
        return problems
