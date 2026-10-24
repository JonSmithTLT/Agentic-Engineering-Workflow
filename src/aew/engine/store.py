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
* The store (``state/`` and everything under it) is owner-only whatever the umask (operator, 2026-10-24: the work-item
  fact issuer that was to read it as the operator's group is cut): its files are :data:`STORE_FILE_MODE`, its
  directories :data:`STORE_DIR_MODE`. Every write the store makes goes through :func:`write_file`; a store written
  group-readable (STG-05 CS-1's CB-08 modes) is narrowed once, in recovery (``_migrate_modes``).
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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from aew import process_kind, profile
from aew.coordination import layout as coordination
from aew.engine import faults, outbox
from aew.engine.lock import FileLock
from aew.errors import (
    AEWError,
    DispatchUndecided,
    IntegrityError,
    ProjectNotFound,
    StaleRevision,
    ThreadUnsealed,
    ValidationFailed,
)
from aew.schemas import validate
from aew.util import (
    IS_WINDOWS,
    YAML_TOO_DEEP,
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
# The store's modes: owner-only. Files come from ``write_temp`` (``mkstemp``, 0600 whatever the umask), directories from
# ``store_dirs``; every write into the store goes through ``write_file``, except the control file's temp, which
# ``_commit_unprofiled`` writes with ``write_temp`` before it replaces the control file.
STORE_FILE_MODE = 0o600
STORE_DIR_MODE = 0o700
_GROUP_OTHER = 0o077  # the permission bits of anyone but the owner, which no store path has
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


def store_dirs(store: Path, directory: Path) -> None:
    """Create ``directory`` (the store directory or one under it) and every missing directory between, each
    :data:`STORE_DIR_MODE`: ``mkdir`` is filtered by the umask, ``chmod`` is not. An existing directory keeps its mode
    (``_migrate_modes`` narrows a store written group-readable)."""
    missing = []
    d = directory
    while not d.is_dir():
        missing.append(d)
        if d == store:
            break
        d = d.parent
    for d in reversed(missing):
        d.mkdir(parents=d == store, exist_ok=True)
        if not IS_WINDOWS:  # pragma: posix-only
            os.chmod(d, STORE_DIR_MODE)


def _chmod_if_allowed(path: Path, mode: int) -> None:  # pragma: posix-only
    """``chmod``, except where this process may not change the path (another account's file), it has gone, or the file
    system refuses (read-only, or no ``chmod`` at all): the narrowing is best-effort, so it then leaves the path, and
    `aew doctor` names it (review of #256, F4)."""
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def store_of(aew_root: Path) -> Path:
    """The store directory of ``aew_root``, resolved itself (a ``state`` that is a link resolves to its target): what
    :func:`write_file` compares its resolved paths with, and what the migration and `aew doctor` walk."""
    return (aew_root / STORE_REL).resolve()


def write_file(store: Path, path: Path, data: bytes | str, *, exclusive: bool = False) -> None:
    """Write ``path`` atomically (``create_exclusive`` when ``exclusive``), owner-only like every file AEW writes.
    When it is in ``store`` (from :func:`store_of`), its missing directories are made with the store's mode
    (:func:`store_dirs`). Both are resolved paths, so a path that reaches the store through ``..`` or a link is in the
    store."""
    if store in path.parents:
        store_dirs(store, path.parent)
    (create_exclusive if exclusive else atomic_write)(path, data)


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
    body = dump_yaml(state, source="control state")
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
    # Bounded too: the checksum keeps out damage, not a writer. AEW never writes control state past the bound, so a deep
    # one was written outside AEW, and flattening it by hand would break its checksum (review of #236, R2-F3).
    state = load_yaml(body, source=source, remedy="AEW never writes control state that deep, so this file was written "
                      "outside AEW: restore it from git or a backup")
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
        # False once the narrowing found that the file system holding the store keeps no permission bits (``chmod``
        # changes nothing there), for `aew doctor` to say so; None until then (``_migrate_modes``).
        self.modes_kept: bool | None = None

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
        ``FileLock`` on :data:`LOCK_REL` anywhere else (review of #231, MJ1)."""
        process_kind.require_writer(operation)
        return FileLock(self.root / LOCK_REL, timeout=self.lock_timeout)

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
            txn_bytes = dump_yaml(record, source="the transaction's redo record").encode("utf-8")
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

        self.require_lock_intact()
        faults.hit("txn.before_stage")
        if txn_ref:
            write_file(self.store_dir, self._abs(txn_ref["path"]), txn_bytes)
        faults.hit("txn.after_stage")

        # The commit point: temp + fsync, then atomic replace of control.yaml.
        tmp = write_temp(self.store_dir, control_bytes, prefix=".control.yaml.")
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
        self._remove_temp_files()
        self._migrate_modes()
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

    def _store_modes(self) -> Iterator[tuple[Path, int, bool]]:  # pragma: posix-only
        """(path, its mode, whether it is a directory) for the store directory and every directory and regular file
        under it. Symbolic links are skipped (``chmod`` would follow them out of the store), and so is a path that
        vanished after it was listed: the compactor prunes log records without the control lock (``log_compact``)."""
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
                    yield path, stat.S_IMODE(st.st_mode), is_dir

    def _migrate_modes(self) -> None:
        """Narrow a store written group-readable (STG-05 CS-1's CB-08 modes, ``0640``/``0750``), or one from before
        CS-1 whose directories the umask left wider, to owner-only, once, under the control lock: every path loses its
        group and other permission bits. The store directory's and the control file's own modes are the record that it
        ran: both are owner-only from the start (``store_dirs``, ``write_temp``). The control file is narrowed first and
        the store directory last, so a store whose two are owner-only was narrowed (or written owner-only), and a
        narrowing interrupted part-way runs again. A path this process may not change (another account's file) is left
        as it is and the narrowing still finishes, so it never stops a command; `aew doctor` (``store-modes``) names it.
        If the store directory is such a path, the record is never written and every recovery walks the store again
        (review of #230, N4).

        Neither record path is followed if it is a link: a control file that is one is left for `aew doctor` to name,
        and the next commit replaces it with a file (review of #256, F3). If the control file is still wide after it is
        narrowed, whether or not ``chmod`` raised, walking the store would change nothing either, at every open: the
        file system keeps no permission bits (drvfs without ``metadata``, vfat, CIFS without Unix extensions), and
        `aew doctor` says so once (:attr:`modes_kept`), or the control file is another account's, and doctor names it
        (review of #256, F1)."""
        # sys.platform, not IS_WINDOWS: Pyright narrows a platform branch only on sys.platform, and os.geteuid is
        # POSIX-only (review of #230, m8)
        if sys.platform == "win32":  # pragma: windows-only
            return
        control = self.store_dir / Path(CONTROL_REL).name  # pragma: posix-only
        try:
            top, ctl = os.lstat(self.store_dir), os.lstat(control)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(ctl.st_mode):
            return
        top_mode, ctl_mode = stat.S_IMODE(top.st_mode), stat.S_IMODE(ctl.st_mode)
        if not (top_mode | ctl_mode) & _GROUP_OTHER:
            return
        if ctl_mode & _GROUP_OTHER:
            _chmod_if_allowed(control, ctl_mode & ~_GROUP_OTHER)
            after = os.lstat(control)
            if stat.S_IMODE(after.st_mode) & _GROUP_OTHER:
                if after.st_uid == os.geteuid():
                    self.modes_kept = False
                return
        for path, mode, _is_dir in self._store_modes():
            if path not in (self.store_dir, control) and mode & _GROUP_OTHER:
                _chmod_if_allowed(path, mode & ~_GROUP_OTHER)
        if top_mode & _GROUP_OTHER:
            _chmod_if_allowed(self.store_dir, top_mode & ~_GROUP_OTHER)

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
        try:
            return load_yaml(raw.decode("utf-8"), source=txn_ref["path"])["writes"]  # its pinned sha256 matched
        except ValidationFailed as exc:
            # AEW never writes a redo record that deep, and git cannot restore one (state/txn/ is ignored): it is the
            # damaged record its checksum refusal names (review of #236, R2-F3)
            if exc.details.get("reason") != YAML_TOO_DEEP:
                raise
            raise IntegrityError(f"redo record {txn_ref['path']} is damaged", **exc.details) from None

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

    def mode_problems(self) -> list[str] | None:
        """The store's paths (``state/...``; a directory ends in ``/``) that are not owner-only, without modifying
        anything: those with a group or other permission bit, and a control file that is a link, which the narrowing
        never follows (``_migrate_modes``). None on Windows, which has no such modes: there is nothing to report either
        way."""
        if IS_WINDOWS:  # pragma: windows-only
            return None
        out = []  # pragma: posix-only
        for path, mode, is_dir in self._store_modes():
            if mode & _GROUP_OTHER:
                out.append(self._rel(path, is_dir))
        if (self.store_dir / Path(CONTROL_REL).name).is_symlink():
            out.append(f"{CONTROL_REL} (a symbolic link, which AEW never follows: the next commit replaces it with a "
                       "file)")
        return sorted(out)

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
