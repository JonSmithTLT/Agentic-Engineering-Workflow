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
* A transition may also reference **pre-written immutable objects**
  (``Session.prewritten``): files a caller already wrote, create-if-absent and
  deterministic, before the commit (ADR-0011 migration, implementation plan
  R8). The commit verifies each one's hash and records them in the redo record
  by path and hash only, never by content, so a large batch keeps both the
  redo record and ``last_transition`` bounded. If the commit never happens they
  stay behind unreferenced, which is benign (ADR-0011): a retry rewrites the
  same bytes.
* Roll-forward is idempotent and conservative: a target is written only if it
  still has its pre-transaction content (or is at the post content already);
  anything else is an out-of-band modification and fails closed.
* Every operation (read or write) runs under an OS advisory lock and first
  performs recovery. Revision checks happen inside the lock (compare-and-swap).
  A process declared a non-writer (``aew.process_kind``, STG-05 CB-09) is refused
  all three before the lock is opened: it reads lock-free (``read_committed``).
* The store (``state/`` and everything under it) has one **target** group and modes at a time, whatever the umask,
  the process's effective group or a set-group-ID parent (STG-05 CB-08; D-CS1-10 and D-CS1-11 as A-36 amends them):
  the store's group with :data:`STORE_FILE_MODE` and :data:`STORE_DIR_MODE` (group-readable, so the work-item fact
  issuer can read it) where WIS-01a's group is private to the operator and every running store writer holds it, and
  otherwise owner-only under the operator's primary group (``aew.engine.store_group``, ``aew.engine.store_writers``).
  Every other file AEW writes keeps ``0600``. The target is computed under the control lock, at every open and before
  every commit, and compared with the record, the control file's group **and** mode (D-CS1-1 as extended); where they
  differ the whole store is walked to the target first, the control file last (``_walk``). Every write into the store
  goes through :func:`write_file`, which refuses one made without the control lock, so no publication escapes the
  comparison.
* The transition log ``state/log/<rev>.yaml`` is derived from committed state and
  never authoritative, but it is complete and consumable (ADR-0012, amending
  ADR-0001): every revision has exactly one record, carrying the typed events the
  commit implies (bounded hot; an oversized set goes to an immutable sidecar staged
  in the redo record) and a hash chaining it to the previous one. See
  ``aew.engine.outbox``. Derived views (for example ``state/CURRENT.md``) are
  rebuilt from committed state.
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
import os
import stat
import sys
import time
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar

from aew import process_kind, profile
from aew.coordination import layout as coordination
from aew.engine import faults, outbox, store_group, store_writers
from aew.engine.lock import FileLock
from aew.errors import AEWError, DispatchUndecided, IntegrityError, ProjectNotFound, StaleRevision, ThreadUnsealed
from aew.schemas import validate
from aew.util import (
    GroupRefused,
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
STORE_REL = "state"
# The store's group-readable modes (STG-05 CB-08; WIS-00 WISD-2), which are also WIS-00's upper bound, and its
# owner-only ones; ``store_group`` owns both pairs. Every write into the store goes through ``write_file`` (and
# ``store_dirs``) at the target the holder of the control lock computed, except the control file's temp, which
# ``_commit_unprofiled`` writes at the same target before it replaces the control file.
STORE_FILE_MODE, STORE_DIR_MODE = store_group.GROUP_READ
OWNER_FILE_MODE, OWNER_DIR_MODE = store_group.OWNER_ONLY
CONTROL_REL = "state/control.yaml"
TXN_DIR = "state/txn"
LOG_DIR = "state/log"
LOCK_REL = "local/control.lock"
READ_RETRIES = 8  # a lock-free read colliding with a replace on Windows
_T = TypeVar("_T")
# What an open reports for a present file in the middle of a replace, besides a sharing violation: only Windows.
MISSING_MID_REPLACE: tuple[type[OSError], ...] = (FileNotFoundError,) if os.name == "nt" else ()


def retry_lock_free(read: Callable[[], _T], *, also: tuple[type[OSError], ...] = ()) -> _T:
    """``read()``, retried briefly on ``PermissionError`` (and on ``also``): on Windows a lock-free reader's open can
    collide with a writer's atomic replace for a moment (a sharing violation), as the writer's own
    ``replace_with_retry`` does on its side. The one owner of that retry, for every lock-free read of a file that may
    be replaced. The last attempt's error is raised."""
    for attempt in range(READ_RETRIES):
        try:
            return read()
        except (PermissionError, *also):
            if attempt == READ_RETRIES - 1:
                raise
            time.sleep(0.01 * (attempt + 1))
    raise AssertionError("unreachable")


def read_lock_free(path: Path) -> bytes | None:
    """A file's bytes without the control lock, or None when it does not exist. No ``is_file()`` pre-check. On
    Windows a missing file is absent only after the retries: in the middle of a replace, a stat can fail and an open can
    even report the file missing, so a present file would look absent (F1a review, R4). That costs a truly absent file
    the retries' backoff (about 0.3 s) there. On POSIX ``rename`` replaces a name atomically, so a missing file is
    absent at once (F1a re-review, R8; as ``aew.dashboard.reader`` gates its own retry). A directory reads as absent."""
    try:
        return retry_lock_free(path.read_bytes, also=MISSING_MID_REPLACE)
    except (FileNotFoundError, IsADirectoryError):
        return None
    except PermissionError:
        if path.is_dir():  # Windows refuses to open a directory with a PermissionError
            return None
        raise


def store_dirs(store: Path, directory: Path, target: store_group.Target | None) -> None:
    """Create ``directory`` (the store directory or one under it) and every missing directory between, each at the
    target. ``mkdir`` makes it ``0700`` or narrower (the umask only removes bits), so it grants nothing until it has the
    target's group, set on its descriptor, and then the target's mode, which ``fchmod`` sets exactly (clearing a
    set-group-ID parent's bit too). So no new directory is ever above WIS-00's bound, even for a moment. An existing
    directory is left: the walk brings it to the target. ``target`` is None on Windows."""
    missing = []
    d = directory
    while not d.is_dir():
        missing.append(d)
        if d == store:
            break
        d = d.parent
    for d in reversed(missing):
        try:
            d.mkdir(mode=OWNER_DIR_MODE, parents=d == store)
        except FileExistsError:
            continue  # another writer made it: the walk owns existing directories
        if sys.platform != "win32" and target is not None:  # pragma: posix-only
            fd = os.open(d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                try:
                    os.fchown(fd, -1, target.gid)
                except PermissionError as exc:
                    if target.group_readable:
                        raise GroupRefused(exc.errno, f"group {target.gid} refused for {d}") from exc
                os.fchmod(fd, target.dir_mode)
            finally:
                os.close(fd)


def operator_gid() -> int | None:
    """The operator's primary group, or this process's own group when the uid has no account entry: the group an
    owner-only store has where the host's listing failed. None where there are no POSIX groups (Windows)."""
    if sys.platform == "win32":  # pragma: windows-only
        return None
    try:  # pragma: posix-only
        import pwd
    except ImportError:  # a test that claims a POSIX platform on Windows: there are still no groups
        return None
    try:
        return pwd.getpwuid(os.getuid()).pw_gid
    except KeyError:  # a container's or a user namespace's uid
        return os.getgid()


# The store directory -> the ControlStore that holds its control lock in this process and has compared the store with
# its target (D-CS1-1). ``write_file`` publishes into the store only through it.
_HOLDERS: dict[Path, ControlStore] = {}


class _ControlLock(FileLock):
    """The control lock as a store writer holds it: once taken, the store is compared with WIS-01a's current answer,
    and walked to it first where they differ (D-CS1-1 as extended), before anything else runs under it. So the walk
    always holds the lock throughout, and so does every publication (``write_file``)."""

    def __init__(self, store: ControlStore, path: Path, timeout: float) -> None:
        super().__init__(path, timeout=timeout)
        self._store = store
        self._outer: ControlStore | None = None

    def __enter__(self) -> _ControlLock:
        super().__enter__()
        self._outer = _HOLDERS.get(self._store.store_dir)
        _HOLDERS[self._store.store_dir] = self._store
        try:
            self._store._compare()
        except BaseException:
            self._release_holder()
            super().__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        try:
            self._release_holder()
        finally:
            super().__exit__(exc_type, exc, tb)

    def _release_holder(self) -> None:
        if self._outer is None:
            _HOLDERS.pop(self._store.store_dir, None)
        else:
            _HOLDERS[self._store.store_dir] = self._outer
        self._store._target = None


def store_of(aew_root: Path) -> Path:
    """The store directory of ``aew_root``, resolved itself (a ``state`` that is a link resolves to its target): what
    :func:`write_file` compares its resolved paths with, and what the migration and `aew doctor` walk."""
    return (aew_root / STORE_REL).resolve()


def write_file(store: Path, path: Path, data: bytes | str, *, exclusive: bool = False) -> None:
    """Write ``path`` atomically (``create_exclusive`` when ``exclusive``): at the store's target when it is in
    ``store`` (from :func:`store_of`), and AEW's ``0600`` otherwise. Both are resolved paths, so a path that reaches
    the store through ``..`` or a link is in the store. A write into the store is made only through the
    ``ControlStore`` that holds its control lock in this process, which has compared the store with its target
    (D-CS1-1); without one it is refused, so no writer publishes a store file the comparison has not covered."""
    if store not in path.parents:
        (create_exclusive if exclusive else atomic_write)(path, data, mode=0o600)
        return
    holder = _HOLDERS.get(store)
    if holder is None:
        raise IntegrityError(f"refusing to write {path} into the store without holding its control lock",
                             path=str(path), reason="store_write_unlocked")
    holder.publish(path, data, exclusive=exclusive)


def _temp_args(target: store_group.Target | None) -> dict[str, Any]:
    """``write_temp``'s group and mode for a store file at ``target`` (None on Windows: the mode is ignored there)."""
    if target is None:
        return {"mode": STORE_FILE_MODE}
    return {"mode": target.file_mode, "group": target.gid, "require_group": target.group_readable}


@dataclass(frozen=True)
class GroupView:
    """What a store writer sees of the store's group now (:meth:`ControlStore.group_view`)."""

    host: store_group.HostGroups | None  # None where the listing failed (``error``)
    answer: store_group.Answer
    me: store_group.Credentials
    others: list[store_writers.Writer]
    problems: list[str]
    target: store_group.Target
    error: str | None
    register_problem: str | None

    def lacking(self) -> list[str]:
        """Each running store writer that lacks the private group, this process first: the ones to restart."""
        gid = self.answer.gid
        if gid is None:
            return []
        out = [] if self.me.holds(gid) else [f"this process (pid {os.getpid()})"]
        return out + [w.name() + (f": {w.note}" if w.note else "") for w in self.others if not w.holds(gid)]


Renderer = Callable[[dict[str, Any]], dict[str, str]]
AfterApply = Callable[[dict[str, Any]], None]
# Seals the coordination threads of the invocations a session ends (F9-A plan D-16): the kernel's
# ``Coordination.seal_ending``, injected by the composition root. The store calls it only as the commit check's
# fallback, for an ending whose path missed its explicit call.
Seal = Callable[["Session", list[str]], list[str]]


@dataclass
class PendingWrite:
    path: str  # POSIX path relative to the AEW root
    content: str
    immutable: bool
    fault: str | None = None  # a fault point hit right after this write is applied (crash-safety tests)


@dataclass
class Transition:
    """What a committed control transition records about itself."""

    op: str
    actor: dict[str, Any]
    summary: str | None = None
    reason: str | None = None
    refs: list[str] = field(default_factory=list)
    # Facts the state difference cannot recover, declared by the authoritative operation (ADR-0012 D2).
    events: list[dict[str, Any]] = field(default_factory=list)


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


def _applied_marker(revision: int) -> str:
    """Written once a committed transaction's staged writes are all in place: recovery then has nothing to redo."""
    return f"{TXN_DIR}/{revision:06d}.applied"


def _require_dispatched(before: dict[str, Any], after: dict[str, Any]) -> None:
    """No commit creates an invocation or a harness run without the dispatch decision that admitted it (M4-A).

    The dispatch commit check (``Dispatch.finalize``) admits each new one and records its decision on it; it runs as a
    Lead transaction finalizer. This makes the rule structural: whatever path commits, a new invocation or run with
    no recorded decision is refused here (area 3 note 1)."""
    old_invs = before.get("invocations") or {}
    for inv_id, inv in (after.get("invocations") or {}).items():
        old = old_invs.get(inv_id)
        if old is None and "dispatch" not in inv:
            raise DispatchUndecided(f"{inv_id} would be committed without a dispatch decision", invocation=inv_id)
        for run in (inv.get("runs") or [])[len((old or {}).get("runs") or []):]:
            if "dispatch" not in run:
                raise DispatchUndecided(f"run {run.get('run')} of {inv_id} would be committed without a dispatch "
                                        "decision", invocation=inv_id, run=run.get("run"))


class Session:
    """A locked, recovered view of control state that may commit at most once."""

    def __init__(self, store: ControlStore, state: dict[str, Any]) -> None:
        self._store = store
        self._committed_state = state  # the store's parse: never changed (``state`` is this session's copy)
        self.state = copy.deepcopy(state)
        self._writes: list[PendingWrite] = []
        self._prewritten: dict[str, str] = {}  # path -> sha256 of an immutable object written before the commit
        self.committed_revision: int | None = None

    @property
    def revision(self) -> int:
        return self._committed_state["revision"]

    def committed_view(self) -> dict[str, Any]:
        """The committed state this session started from, without a copy: read it, never change it."""
        return self._committed_state

    def base_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._committed_state)

    def write(self, path: str, content: str, *, immutable: bool = True, fault: str | None = None) -> None:
        """Stage ``content`` at ``path``; a later write of the same path in this session replaces the earlier one (an
        append-only record file gains several lines in one transaction: M4-E's steering records)."""
        self._writes = [w for w in self._writes if w.path != path]
        self._writes.append(PendingWrite(path, content, immutable, fault))

    def prewritten(self, path: str, sha256: str) -> None:
        """Reference an immutable object the caller already wrote at ``path``; the commit refuses unless the file
        holds exactly ``sha256``."""
        if self._prewritten.get(path, sha256) != sha256:
            raise IntegrityError(f"{path} is referenced with two different hashes")
        self._prewritten[path] = sha256

    def commit(self, transition: Transition, *, expect_rev: int | None = None,
               state: dict[str, Any] | None = None) -> int:
        """Commit this session's state, or ``state`` when a finalizer projected the one to serialize (ADR-0011 R6).
        """
        if self.committed_revision is not None:
            raise AEWError("session already committed")
        if expect_rev is not None and expect_rev != self.revision:
            raise StaleRevision(
                f"expected control revision {expect_rev}, current is {self.revision}",
                expected=expect_rev,
                current=self.revision,
            )
        after = self.state if state is None else state
        _require_dispatched(self._committed_state, after)
        self._require_sealed(transition, after)
        self.committed_revision = self._store._commit(self._committed_state, after, self._writes, transition,
                                                      self._prewritten, working=self.state)
        return self.committed_revision

    # ------------------------------------------------------------------ the seal check (F9-A plan D-16, R3)

    def _unsealed_endings(self) -> list[tuple[str, str]]:
        """``(invocation, work unit)`` for each invocation this session ends (``active`` in the committed state, not in
        the working state) whose coordination thread exists, and whose unit in the working state carries no pointer to
        a seal prewritten in this session with the pointer's hash. The working state, not the projection: archival
        changes only what is serialized (ADR-0011 R6). One stat per ending invocation; nothing when none ends."""
        working = self.state.get("invocations") or {}
        out = []
        for inv_id, inv in (self._committed_state.get("invocations") or {}).items():
            if inv.get("status") != "active" or (working.get(inv_id) or {}).get("status") == "active":
                continue
            work_id = inv.get("work_unit")
            if not work_id or not (self._store.root / coordination.thread_rel(work_id, inv_id)).is_file():
                continue
            unit = (self.state.get("work") or {}).get(work_id) or {}
            if not any(p.get("invocation") == inv_id and self._prewritten.get(p.get("seal")) == p.get("sha256")
                       for p in unit.get(coordination.UNIT_KEY) or []):
                out.append((inv_id, work_id))
        return out

    def _require_sealed(self, transition: Transition, after: dict[str, Any]) -> None:
        """No commit ends an invocation and leaves its thread unsealed (F9-A plan D-16): the structural half of the
        seal, as ``_require_dispatched`` is of dispatch. The work is ``Coordination.seal_ending``, run as a Lead
        transaction finalizer before archival and called explicitly on the direct paths. An ending that missed its call
        is a defect: on a unit that stays in the serialized state the check seals it here, through the injected
        function, and records a ``coordination.seal_fallback`` event naming the operation (R3), so a missed call site
        never wedges an authority path; on a unit this commit archives it refuses (``ThreadUnsealed``), because the
        unit's bundle is already written. A store without the injected function refuses rather than seal."""
        missed = self._unsealed_endings()
        if not missed:
            return
        archived = sorted(inv for inv, work in missed if work not in (after.get("work") or {}))
        if archived:
            raise ThreadUnsealed(f"this commit ends {', '.join(archived)} and archives its unit without sealing its "
                                 "coordination thread; nothing was committed", invocations=archived, op=transition.op,
                                 reason="archived_unsealed")
        if self._store.seal is None:
            raise ThreadUnsealed(f"this commit ends {', '.join(inv for inv, _ in missed)} without sealing its "
                                 "coordination thread, and this store cannot seal; nothing was committed",
                                 invocations=[inv for inv, _ in missed], op=transition.op, reason="no_seal_function")
        self._store.seal(self, transition.refs)
        if after is not self.state:  # a projection is a shallow copy: its top-level keys are its own
            if coordination.UNSEEN_KEY in self.state:
                after[coordination.UNSEEN_KEY] = self.state[coordination.UNSEEN_KEY]
            else:
                after.pop(coordination.UNSEEN_KEY, None)
            for _, work_id in missed:
                unit = after["work"][work_id]
                if unit is not self.state["work"][work_id]:
                    unit[coordination.UNIT_KEY] = self.state["work"][work_id][coordination.UNIT_KEY]
        left = self._unsealed_endings()
        if left:
            raise ThreadUnsealed(f"the commit check could not seal {', '.join(inv for inv, _ in left)}; nothing was "
                                 "committed", invocations=[inv for inv, _ in left], op=transition.op,
                                 reason="seal_failed")
        transition.events.extend({"kind": coordination.SEAL_FALLBACK, "invocation": inv, "op": transition.op}
                                 for inv, _ in missed)


class ControlStore:
    def __init__(self, aew_root: Path, *, renderer: Renderer | None = None, lock_timeout: float = 60.0,
                 after_apply: AfterApply | None = None, seal: Seal | None = None) -> None:
        self.root = aew_root
        self.renderer = renderer
        self.lock_timeout = lock_timeout
        self.after_apply = after_apply
        self.seal = seal  # F9-A plan D-16: the commit check's fallback; the composition root sets it
        self.held = 0  # > 0 while this process holds the control lock through this store
        self._parsed: tuple[str, dict[str, Any]] | None = None  # (sha256 of the bytes, their parse): read-only
        self._lock: FileLock | None = None  # the control lock this process holds for the open session
        self.store_dir = store_of(aew_root)  # resolved, for ``write_file``
        self._target: store_group.Target | None = None  # set under the control lock only (``_compare``)
        self._registered = False
        self._registration: store_writers.Registration | None = None
        self._register_problem: str | None = None

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

    def control_lock(self, operation: str) -> FileLock:
        """The engine's control lock, not yet taken: the one place AEW opens it (STG-05 CB-09). ``operation`` is refused
        here in a non-writer, before anything opens the lock (``process_kind.require_writer``); a test refuses a
        ``FileLock`` on :data:`LOCK_REL` anywhere else (review of #231, MJ1). This is also where a process becomes a
        running store writer (``store_writers.register``), so every one of them is counted (STG-05 CB-08)."""
        process_kind.require_writer(operation)
        self._register()
        return _ControlLock(self, self.root / LOCK_REL, timeout=self.lock_timeout)

    def _register(self) -> None:
        """Record this process as a running store writer of this project, once per ``ControlStore``; the entry goes
        when the last ``ControlStore`` of the project in this process does. A process that cannot record itself is
        unseen by the others, so it never widens the store (``group_view``)."""
        if self._registered or sys.platform == "win32":
            return
        self._registered = True
        try:  # pragma: posix-only
            self._registration = store_writers.register(self.root, process_kind.declared())
        except OSError as exc:
            self._register_problem = (f"this process could not record itself as a running store writer "
                                      f"({exc.strerror or exc}), so it writes the store owner-only")
            return
        weakref.finalize(self, store_writers.release, self.root)

    # ------------------------------------------------------------------ the store's group and modes (STG-05 CB-08)

    def group_view(self) -> GroupView:
        """WIS-01a's answer now (``store_group.HOST``), the running store writers, and the target they give every store
        publication. Changes nothing; ``aew doctor`` reads it too. A listing that fails makes nothing private: the
        store is then owner-only, and AEW keeps working."""
        host: store_group.HostGroups | None = None
        error = None
        try:
            host = store_group.HOST(self.store_dir)
            found = store_group.answer(host)
            primary = host.primary
        except Exception as exc:  # report and fail closed, never stop a command
            error = f"{type(exc).__name__}: {exc}"
            found = store_group.Answer(None, None, store_group.HOST_UNREADABLE)
            primary = operator_gid() or 0
        me = store_writers.CREDENTIALS()
        reg = self._registration
        if process_kind.kind() == process_kind.NON_WRITER:  # it publishes nothing, so it is no writer to count
            me = store_group.Credentials(-1, frozenset() if found.gid is None else frozenset({found.gid}))
        elif reg is None:  # unseen by the others, so it must not be the one that widens
            me = store_group.Credentials(-1, frozenset())
        elif reg.refused is not None:  # the file system refused it the group: it lacks it, whatever its credentials
            me = store_group.Credentials(-1 if me.egid == reg.refused else me.egid, me.groups - {reg.refused})
        others, problems = store_writers.running(self.root, exclude=reg)
        return GroupView(host, found, me, others, problems, store_group.target(found, primary, me, others), error,
                         self._register_problem)

    def _compare(self) -> None:
        """D-CS1-1 as extended (A-36): under the control lock, compare the record (the control file's group and mode)
        with the target WIS-01a gives now, and walk the store to the target first where they differ. Run when the
        lock is taken (every open) and again before every commit, so a change that lands while a writer is open is
        walked before its next publication (C2-1), and a walk interrupted before the control file runs again (C2-2).
        A store with no control file yet is walked too, so an interrupted ``create`` leaves nothing behind."""
        if sys.platform == "win32":  # pragma: windows-only
            self._target = None
            return
        want = self.group_view().target  # pragma: posix-only
        if self._record() != (want.gid, want.file_mode) and self.store_dir.is_dir():
            want = self._walk(want)
        self._target = want

    def _record(self) -> tuple[int, int] | None:  # pragma: posix-only
        try:
            st = os.stat(self.store_dir / Path(CONTROL_REL).name)
        except FileNotFoundError:
            return None
        return st.st_gid, stat.S_IMODE(st.st_mode)

    def _walk(self, want: store_group.Target) -> store_group.Target:  # pragma: posix-only
        """Bring every store path to ``want`` (``store_group.steps``), the control file last, under the control lock.
        A path pruned meanwhile (the compactor prunes without the lock) is skipped, and so is one this process may not
        change (another account's), which `aew doctor` names. If the file system refuses this process the store's
        group on a path of its own, the process lacks it: it says so in its entry, and walks to the owner-only target
        instead. Returns the target the store was walked to."""
        control = self.store_dir / Path(CONTROL_REL).name
        try:
            first = True
            for path, gid, mode, is_dir, uid in self._store_paths():
                if path != control:
                    self._step(path, gid, mode, is_dir, uid, want)
                    if first:
                        first = False
                        faults.pause("store.walk.mid")  # tests hold a walk here while a second writer tries to open
            faults.hit("store.walk.before_control")
            try:
                st = os.lstat(control)
            except FileNotFoundError:
                return want
            self._step(control, st.st_gid, stat.S_IMODE(st.st_mode), False, st.st_uid, want)
        except GroupRefused:
            self._refuse(want.gid)
            return self._walk(self.group_view().target)  # owner-only now, which needs no group but the primary
        return want

    @staticmethod
    def _step(path: Path, gid: int, mode: int, is_dir: bool, uid: int,
              want: store_group.Target) -> None:
        if sys.platform == "win32":  # pragma: windows-only (no groups or modes to walk)
            return
        for op, value in store_group.steps(gid, mode, want, is_dir):  # pragma: posix-only
            try:
                if op == "mode":
                    os.chmod(path, value)
                else:
                    os.chown(path, -1, value, follow_symlinks=False)
            except FileNotFoundError:
                return
            except PermissionError as exc:
                if op == "group" and want.group_readable and uid == os.geteuid():
                    raise GroupRefused(exc.errno, f"group {value} refused for {path}") from exc
                return  # another account's path, or a primary group this process does not hold: left, and reported

    def _refuse(self, gid: int) -> None:
        if self._registration is not None:
            self._registration.refuse(gid)

    def publish(self, path: Path, data: bytes | str, *, exclusive: bool = False) -> None:
        """Publish ``path`` (resolved, in the store) at the target: only for the holder of the control lock, which
        ``write_file`` routes to. If the file system refuses the store's group, this process lacks it: the store
        goes owner-only (``_refuse``, ``_compare``) and the file is published owner-only."""
        while True:
            target = self._target
            try:
                store_dirs(self.store_dir, path.parent, target)
                (create_exclusive if exclusive else atomic_write)(path, data, **_temp_args(target))
                return
            except GroupRefused:
                if target is None or not target.group_readable:
                    raise
                self._refuse(target.gid)
                self._compare()

    def _publish_temp(self, data: bytes, prefix: str) -> Path:
        """The control file's temp, at the target, as :meth:`publish` makes every other store file."""
        while True:
            target = self._target
            try:
                return write_temp(self.store_dir, data, prefix=prefix, **_temp_args(target))
            except GroupRefused:
                if target is None or not target.group_readable:
                    raise
                self._refuse(target.gid)
                self._compare()

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.control_lock("ControlStore.session") as lock:
            self.held += 1
            outer, self._lock = self._lock, lock
            try:
                state = self._recover()
                yield Session(self, state)
            finally:
                self._lock = outer
                self.held -= 1

    def require_lock_intact(self) -> None:
        """Refuse to write when the control lock this process holds was removed or replaced while held (``local/``
        deleted under a running process): another process can then lock a new file at the same path, so this lock no
        longer excludes it. Every writer under the lock checks this just before it writes: the commit, and the append
        to a coordination thread (F9-A, ADR-0017 D1), whose chain two unexcluded writers would fork."""
        if self._lock is not None and not self._lock.intact():
            raise IntegrityError(f"the control lock {LOCK_REL} was removed or replaced while this process held it, so "
                                 "another process may hold it too; nothing was written. Retry the command (and do "
                                 "not delete .aew/local while AEW is running)", path=LOCK_REL, reason="lock_lost")

    def read(self) -> dict[str, Any]:
        with self.control_lock("ControlStore.read"):
            self.held += 1
            try:
                return copy.deepcopy(self._recover())
            finally:
                self.held -= 1

    def current(self) -> dict[str, Any]:
        """The committed state, as this process may read it (STG-05 CB-09). A store writer reads under the control lock,
        after recovery (``read``). A non-writer (``aew.process_kind``) reads lock-free (``read_committed``): no lock,
        no recovery and no render, so it works on a read-only store, and may see a committed revision whose staged
        records are not applied yet (``read_committed`` says how a reader treats that). The one place that chooses:
        every read of the engine's goes through here, never through ``read`` (a test enforces it)."""
        if process_kind.kind() == process_kind.NON_WRITER:
            return self.read_committed()
        return self.read()

    def control_identity(self) -> tuple[int, int, int] | None:
        """A cheap identity of the committed control file (mtime, size, inode), or None when there is none. The file
        is only ever replaced atomically, so every committed change changes it: a long-lived reader stats it and reads
        only on a change (ADR-0012 D3, invariant 4)."""
        try:
            st = os.stat(self.control_path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def read_committed(self) -> dict[str, Any]:
        """The committed state as the control file holds it, **without the control lock and without recovery**: a
        reader's view (ADR-0012 D3 and invariant 4; the dashboard, register F20.2). Under ADR-0001 the file is only
        ever replaced atomically, so this is always one complete committed state, verified and schema-checked like
        every parse. What a lock-free reader may observe is a committed revision whose staged record files are not
        applied yet (the window recovery closes under the lock); such a reader treats a record that is missing or does
        not match its pin as a stale view to report, never as something to repair. Writers and every engine command
        keep using ``read`` and ``session``.

        On Windows the writer's atomic replace and a reader's open can collide for a moment (a sharing violation,
        ``PermissionError``); the reader retries briefly, as the writer does on its side (``replace_with_retry``)."""
        return retry_lock_free(lambda: copy.deepcopy(self._load()))

    def create(self, state: dict[str, Any], files: dict[str, str]) -> None:
        """Initialize a project: write skeleton files, then publish revision 0.

        The exclusive creation of ``control.yaml`` is the commit point; an
        interrupted initialization leaves no control state and can be re-run.
        """
        with self.control_lock("ControlStore.create"):
            if self.control_path.exists():
                raise IntegrityError(f"{self.control_path} already exists; project is initialized")
            for rel, content in files.items():
                write_file(self.store_dir, self._abs(rel), content)
            state = copy.deepcopy(state)
            state["revision"] = 0
            if state.get("last_transition"):  # revision 0 starts the transition chain (ADR-0012)
                state["outbox"] = outbox.marker({}, 0)
                state["last_transition"] = outbox.seal(
                    {"schema": outbox.TRANSITION_SCHEMA, **state["last_transition"], "revision": 0, "events": [],
                     "event_overflow": None}, outbox.GENESIS_H)
            validate("control", state, source="initial control state")
            write_file(self.store_dir, self._abs(CONTROL_REL), serialize_control(state), exclusive=True)
            self._post_commit(state)

    # ------------------------------------------------------------------ commit

    def _commit(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        writes: list[PendingWrite],
        transition: Transition,
        prewritten: dict[str, str] | None = None,
        *,
        working: dict[str, Any] | None = None,
    ) -> int:
        profile.count("commit")
        with profile.phase("commit"):
            return self._commit_unprofiled(before, after, writes, transition, prewritten or {},
                                           after if working is None else working)

    def _commit_unprofiled(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        writes: list[PendingWrite],
        transition: Transition,
        prewritten: dict[str, str],
        working: dict[str, Any],
    ) -> int:
        revision = before["revision"] + 1
        after["revision"] = revision
        # ADR-0012: the transition's typed events, derived here so that every commit site is covered.
        with profile.phase("outbox"):
            events = outbox.derive_events(before, working, after) + list(transition.events)
            hot, overflow, overflow_text = outbox.bound(revision, events)
        if overflow is not None and overflow_text is not None:  # the complete set, staged like any other write
            # Validated before anything touches disk, as the hot list is with control.yaml: a malformed event fails
            # the commit wherever it falls in the list, not only within the first 64 (D1 review F1).
            validate("transition-events", {"schema": outbox.EVENTS_SCHEMA, "revision": revision, "events": events},
                     source=f"revision {revision}'s overflow events {overflow['path']}")
            writes = [*writes, PendingWrite(overflow["path"], overflow_text, True)]
        for rel, digest in sorted(prewritten.items()):
            if sha256_file(self._abs(rel)) != digest:
                raise IntegrityError(f"pre-written object {rel} is missing or does not hold its declared content",
                                     path=rel, expected=digest)
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
        fault_after = [w.fault for w in writes]

        txn_ref = None
        txn_bytes = b""
        if staged or prewritten:
            record: dict[str, Any] = {"revision": revision, "writes": staged}
            listing = [{"path": rel, "sha256": digest} for rel, digest in sorted(prewritten.items())]
            if listing:
                record["prewritten"] = listing
            txn_bytes = dump_yaml(record).encode("utf-8")
            txn_ref = {
                "path": f"{TXN_DIR}/{revision:06d}.yaml",
                "sha256": sha256_bytes(txn_bytes),
                "writes": [{k: s[k] for k in ("path", "before", "after")} for s in staged],
            }
            if listing:  # bounded: the listing itself is in the hash-pinned redo record
                txn_ref["prewritten"] = {"count": len(listing), "sha256": sha256_bytes(dump_yaml(listing).encode())}
        after["outbox"] = outbox.marker(before, revision)
        after["last_transition"] = outbox.seal({
            "schema": outbox.TRANSITION_SCHEMA,
            "revision": revision,
            "at": utc_now(),
            "actor": transition.actor,
            "op": transition.op,
            "summary": transition.summary,
            "reason": transition.reason,
            "refs": list(transition.refs),
            "txn": txn_ref,
            "events": hot,
            "event_overflow": overflow,
        }, outbox.previous_h(before))
        # Validate before anything touches disk so a rejected transition leaves no trace.
        validate("control", after, source=f"control state revision {revision}")
        control_bytes = serialize_control(after)

        # D-CS1-1 as extended (C2-1): compared before every commit, not only at the open, so this commit publishes
        # nothing at a group or mode the rest of the store does not carry.
        self._compare()
        self.require_lock_intact()
        faults.hit("txn.before_stage")
        if txn_ref:
            write_file(self.store_dir, self._abs(txn_ref["path"]), txn_bytes)
        faults.hit("txn.after_stage")

        # The commit point: temp + fsync, then atomic replace of control.yaml.
        tmp = self._publish_temp(control_bytes, ".control.yaml.")
        try:
            faults.hit("txn.before_replace")
            replace_with_retry(tmp, self.control_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        fsync_dir(self.control_path.parent)
        faults.hit("txn.after_replace")
        if overflow is not None:
            faults.hit("log.overflow_unpublished")  # committed, its sidecar not yet written: recovery publishes it

        self._apply(staged, inject=True, fault_after=fault_after)
        if txn_ref:
            self._mark_applied(revision)
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
        self._remove_temp_files()  # the store was compared, and walked, when the lock was taken (``_ControlLock``)
        state = self._load()
        revision = state["revision"]
        txn_dir = self._abs(TXN_DIR)
        # Discard staged transactions that never committed (and any marker beyond the committed revision).
        if txn_dir.exists():
            for f in [*txn_dir.glob("*.yaml"), *txn_dir.glob("*.applied")]:
                if f.stem.isdigit() and int(f.stem) > revision:
                    f.unlink()
        txn_ref = (state.get("last_transition") or {}).get("txn")
        # Roll forward only a transaction whose apply did not finish. Once it finished, a staged file that differs
        # is a later out-of-band edit, which the pin checks report, not an interrupted transition (area 5 F1).
        if txn_ref and not self._abs(_applied_marker(revision)).exists():
            self._apply(self._load_txn(txn_ref))
            self._mark_applied(revision)
        if self.after_apply:
            self.after_apply(state)
        self._post_commit(state)
        # The last committed transaction is fully applied; older redo records and their markers are spent.
        if txn_dir.exists():
            for f in [*txn_dir.glob("*.yaml"), *txn_dir.glob("*.applied")]:
                if f.stem.isdigit() and int(f.stem) < revision:
                    f.unlink()
        return state

    def _store_paths(self) -> Iterator[tuple[Path, int, int, bool, int]]:  # pragma: posix-only
        """(path, its group, its mode, whether it is a directory, its owner) for the store directory and every directory
        and regular file under it. Symbolic links are skipped (``chmod`` would follow them out of the store), and so
        is a path that vanished after it was listed: the compactor prunes log records without the control lock
        (``log_compact``)."""
        for d, dirs, files in os.walk(self.store_dir):
            names = [("", True)] if Path(d) == self.store_dir else []
            names += [*((n, True) for n in dirs), *((n, False) for n in files)]
            for name, is_dir in names:
                path = Path(d) / name if name else Path(d)
                try:
                    st = os.lstat(path)
                except FileNotFoundError:
                    continue
                if not stat.S_ISLNK(st.st_mode):
                    yield path, st.st_gid, stat.S_IMODE(st.st_mode), is_dir, st.st_uid

    def applied(self, revision: int) -> bool:
        """Whether committed ``revision``'s staged writes are all in place (its marker exists): one stat, no lock. While
        it is absent the apply is pending, or the committer died in it and recovery will roll it forward."""
        return self._abs(_applied_marker(revision)).exists()

    def _mark_applied(self, revision: int) -> None:
        write_file(self.store_dir, self._abs(_applied_marker(revision)), "")

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

    def _apply(self, staged: list[dict[str, Any]], *, inject: bool = False,
               fault_after: list[str | None] | None = None) -> None:
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
            write_file(self.store_dir, target, w["content"])
            if inject and i == 0:
                faults.hit("txn.mid_apply")
            point = fault_after[i] if inject and fault_after else None
            if point:
                faults.hit(point)

    def _post_commit(self, state: dict[str, Any], *, inject: bool = False) -> None:
        last = state.get("last_transition")
        wrote = False
        if last:
            log_path = self._abs(f"{LOG_DIR}/{state['revision']:06d}.yaml")
            if not log_path.exists():
                write_file(self.store_dir, log_path, dump_yaml(last))
                wrote = True
        if inject:
            faults.hit("txn.after_log")
        if wrote:  # a new record, committed now or repaired: wake waiters (advisory, ADR-0012 D4)
            outbox.bump_wake(self.root, state["revision"])
        if self.renderer:
            profile.count("render")
            with profile.phase("render"):
                for rel, content in self.renderer(state).items():
                    target = self._abs(rel)
                    data = content.encode("utf-8")
                    if sha256_file(target) != sha256_bytes(data):
                        write_file(self.store_dir, target, data)
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

    def path_problems(self, want: store_group.Target) -> list[tuple[str, int, int]] | None:
        """``(path, group, mode)`` for each store path (``state/...``; a directory ends in ``/``) that is not exactly at
        ``want``, without modifying anything: a path the walk could not change (another account's), or one changed
        after the record was written, which the walk does not revisit while the control file is at the target. None on
        Windows, which has no such modes or groups."""
        if sys.platform == "win32":  # pragma: windows-only
            return None
        return sorted((self._rel(path, is_dir), gid, mode)  # pragma: posix-only
                      for path, gid, mode, is_dir, _uid in self._store_paths()
                      if (gid, mode) != (want.gid, want.mode(is_dir)))

    def _rel(self, path: Path, is_dir: bool) -> str:  # pragma: posix-only
        rel = (Path(STORE_REL) / path.relative_to(self.store_dir)).as_posix()
        return rel + "/" if is_dir else rel

    def verify(self) -> list[str]:
        """Return integrity problems without modifying anything."""
        problems = []
        try:
            self._load()
        except AEWError as exc:
            problems.append(f"{exc.code}: {exc.message}")
        return problems
