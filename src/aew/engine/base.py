"""The Engine's kernel: project discovery, the manifest and policies, and Lead-guarded transactions.

Every collaborator of the Engine (register E5) receives the ``Kernel`` explicitly; nothing reaches the Engine facade."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.engine.authority import require_lead
from aew.engine.seams import TxnFinalizers
from aew.engine.store import CONTROL_REL, ControlStore, Session, Transition
from aew.errors import (
    AEWError,
    IntegrityError,
    MigrationRequired,
    ProjectNotFound,
    StaleRevision,
    WorkspaceNotAuthority,
)
from aew.knowledge import render
from aew.knowledge.manifest import AEW_DIR, MANIFEST, load_manifest
from aew.knowledge.records import decision_record, format_id
from aew.policy import execution as X
from aew.schemas import validate
from aew.util import load_yaml, read_yaml, sha256_bytes, sha256_file, utc_now
from aew.workspace import git

WORKSPACE_MARKER = "aew-workspace.yaml"  # stored in a linked worktree's private git dir
V1, V2 = "aew/control/v1", "aew/control/v2"
# The top-level control-state keys only a v2 document may carry: the one definition of the set (register E36). The
# control schema's v1 rule refuses exactly these (a unit test checks the two agree), and a test or tool that fakes a v1
# project from `aew init`'s v2 output goes through `as_v1`. A key added for v2 (M4-D's `queue`) is added here.
V2_ONLY_KEYS = ("cold", "recent", "archived_refs", "retained_workspaces", "retired_observations", "queue")


# Control state's pins of the policy files (``{path under .aew: sha256 or None}``); absent in a project initialized
# before them, which `aew manifest adopt` pins.
POLICY_PINS = "policy_sha256"
_NOT_IN_TXN = object()  # Kernel._txn_pins outside a Lead transaction


def policy_files(manifest: dict[str, Any]) -> list[str]:
    """The policy files a manifest puts in force, as paths under ``.aew``: every ``policy`` entry, and the execution
    policy at its conventional path when the manifest names none (``aew.policy.execution.policy_path``)."""
    named = manifest.get("policy") or {}
    return sorted({*named.values(), named.get("execution") or X.REL_PATH})


def as_v1(state: dict[str, Any]) -> dict[str, Any]:
    """A v1 view of a control state: the schema says v1 and every v2-only key is gone. For fixtures and tools that
    build a v1 project from `aew init`, never for migration (v1 to v2 only). The policy pins go too: a v1 project
    predates them (a v1 project may gain them later, through `aew manifest adopt`)."""
    return {k: v for k, v in state.items() if k not in (*V2_ONLY_KEYS, POLICY_PINS)} | {"schema": V1}
# What a Lead may still do on a v1 project (ADR-0011; implementation plan §3): change the seat, end work in flight (a
# live run blocks the migration), and adopt a changed manifest (the migration checks the pin). Everything else waits
# for `aew migrate`, so a v1 project is never refused before the command that clears the refusal exists.
V1_OPS = frozenset({"lead.handoff.offer", "lead.handoff.cancel", "lead.release", "invoke.cancel", "manifest.adopt"})


@dataclass
class TxnContext:
    session: Session
    actor: dict[str, Any]
    summary: str | None = None
    refs: list[str] = field(default_factory=list)
    op: str | None = None  # overrides the transaction's op when the outcome differs (e.g. integrate.stale)
    # The Lead's execution selection (--profile/--model/--effort) for the invocation this dispatch creates;
    # None selects from policy (ADR-0010).
    execution_request: dict[str, Any] | None = None
    # --launch: the invocation this dispatch creates is recorded with harness run 1 (ADR-0009).
    launch_request: bool = False
    # The state to serialize, when a finalizer projected one (ADR-0011 plan R6: archival changes what is committed,
    # never the working state the operation's own code still reads after its commit). None commits ``state``.
    commit_state: dict[str, Any] | None = None
    # Side effects that must wait until the commit landed (removing a worktree the committed state no longer names).
    after_commit: list[Callable[[], None]] = field(default_factory=list)
    # History annotations this transition adds about archived units (a move), appended by the archival finalizer.
    annotations: list[dict[str, Any]] = field(default_factory=list)
    # Facts this transition declares that its state change cannot show (ADR-0012 D2: a decision recorded, evidence
    # ingested, a handoff or an audit written). Only the operation itself appends them.
    events: list[dict[str, Any]] = field(default_factory=list)
    # Other history entries this transition adds (an audit record, already staged), appended by the archival
    # finalizer first and in one append with everything else: a transaction appends to the history exactly once.
    entries: list[dict[str, Any]] = field(default_factory=list)
    # History records are written before the commit and referenced by hash (``Session.prewritten``), never staged in
    # the redo record: a migration archives the whole history in one transaction (implementation plan R8).
    prewrite: bool = False
    # The dispatch decisions this transaction computed (M4-A): the dispatch finalizer admits a new invocation or run
    # only with one of them.
    dispatch_decisions: list[Any] = field(default_factory=list)

    @property
    def state(self) -> dict[str, Any]:
        return self.session.state


class Kernel:
    def __init__(self, repo_root: Path, aew_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.aew_root = aew_root.resolve()
        self._manifest: dict[str, Any] | None = None
        self._manifest_error: Exception | None = None
        self._manifest_seen: tuple[Any, ...] | None = None  # file identities the cached manifest reflects
        self.store = ControlStore(self.aew_root, renderer=self._render, after_apply=self._refresh_manifest)
        self.finalizers = TxnFinalizers()  # run inside every Lead transaction before it commits
        # Credentials archived with finished work (ADR-0011 R7), set by the composition root; None before archival.
        self.archived_credential: Any = None
        # Lead mutations on a v1 project are refused until `aew migrate`. Only the perf tool sets this, in process, to
        # build the M3 (v1) layout its baselines were measured on (tools/perf/control_plane.py).
        self.legacy_v1_writes = False
        # The policy pins a Lead transaction checked on entry, so every policy read inside it is held to the same pins
        # (PR #118 review, finding 2: an edit after the entry check must not be used by the transaction).
        self._txn_pins: Any = _NOT_IN_TXN

    # ------------------------------------------------------------------ manifest (review 2026-09-26 M8)

    def _refresh_manifest(self, state: dict[str, Any]) -> None:
        """Load project.yaml inside the control lock, after recovery replayed any committed rewrite of it.

        Called on every session, so a long-lived engine never serves a manifest older than the control
        state it just read. An unreadable manifest is remembered and raised on use (``doctor`` reports it).
        """
        try:
            self._manifest, self._manifest_error = load_manifest(self.aew_root), None
        except Exception as exc:  # surfaced by the ``manifest`` property
            self._manifest, self._manifest_error = None, exc
        self._manifest_seen = self._authority_files_identity()
        git.trust_drivers(self.trusted_git_drivers(state.get(POLICY_PINS)))

    def trusted_git_drivers(self, pins: dict[str, str | None] | None) -> list[str]:
        """The git drivers the execution policy trusts. Nothing is trusted when it cannot be read, or when it differs
        from its pin (fail safe: AEW's git then runs no configured program at all; an unadopted edit must never add a
        driver AEW's own git would run)."""
        try:
            policy = self._execution_policy(self._manifest, pins)[0] if self._manifest else None
        except Exception:  # an invalid or unpinned policy is reported where it is used; it trusts nothing here
            policy = None
        return list(((policy or {}).get("containment") or {}).get("trusted_git_drivers") or [])

    def _authority_files_identity(self) -> tuple[Any, ...]:
        """Cheap identity of control.yaml and project.yaml (mtime, size, inode). Both are only ever
        replaced atomically, so any committed change — or a pending recovery — changes it."""
        out: list[Any] = []
        for path in (self.aew_root / CONTROL_REL, self.aew_root / MANIFEST):
            try:
                st = path.stat()
                out.append((st.st_mtime_ns, st.st_size, st.st_ino))
            except FileNotFoundError:
                out.append(None)
        return tuple(out)

    @property
    def manifest(self) -> dict[str, Any]:
        """The manifest of the latest recovered control state — for every read path (re-review M8).

        Inside a store session it was loaded under the lock when the session began (after recovery).
        Outside one, it is revalidated against the files' identity on each use and, if anything changed
        since it was loaded, reloaded through a recovered read — never by re-entering the lock.
        """
        if not self.store.held and self._manifest_seen != self._authority_files_identity():
            self.store.read()  # recovery first; the manifest is (re)loaded under the lock
        if self._manifest_error is not None:
            raise self._manifest_error
        assert self._manifest is not None
        return self._manifest

    # ------------------------------------------------------------------ discovery

    @staticmethod
    def locate(start: Path) -> tuple[Path, Path]:
        """Locate the authoritative project for ``start``.

        A linked worktree (Ticket workspace) resolves to the authoritative root
        recorded in its private marker. A worktree *copy* of ``.aew/`` without a
        marker is refused: copies are contextual snapshots, never authorities
        (WC §5 crash-safe control-authority rule, KC §12.3).
        """
        start = start.resolve()
        top = git.toplevel(start)
        if top is not None and git.is_linked_worktree(top):
            marker = git.git_dir(top) / WORKSPACE_MARKER
            if marker.exists():
                data = read_yaml(marker)
                return Path(data["authoritative_repo_root"]), Path(data["authoritative_aew_root"])
            if (top / AEW_DIR / MANIFEST).exists():
                raise WorkspaceNotAuthority(
                    f"{top / AEW_DIR} is a worktree copy of AEW state, not the authoritative project; "
                    "run aew from the authoritative repository",
                    worktree=str(top),
                )
        for directory in (start, *start.parents):
            if (directory / AEW_DIR / MANIFEST).exists():
                return directory, directory / AEW_DIR
            if top is not None and directory == top:
                break
        raise ProjectNotFound(f"no AEW project ({AEW_DIR}/{MANIFEST}) found at or above {start}")

    # ------------------------------------------------------------------ helpers

    @property
    def project_id(self) -> str:
        return self.manifest["project"]["id"]

    @property
    def authoritative_branch(self) -> str:
        return self.manifest["repository"]["authoritative_branch"]

    def authoritative_commit(self) -> str | None:
        return git.rev_parse(f"refs/heads/{self.authoritative_branch}", cwd=self.repo_root)

    def _render(self, state: dict[str, Any]) -> dict[str, str]:
        # Runs inside the lock during recovery: never re-enter the manifest property from here.
        name = ((self._manifest or {}).get("project") or {}).get("name") or state["project_id"]
        return render.views(state, name, self.aew_root)

    def policy(self, name: str) -> dict[str, Any]:
        rel = self.manifest["policy"][name]
        path = self.aew_root / rel
        raw = self._pinned_bytes(rel, self._pins_in_force())
        if raw is None:
            raise FileNotFoundError(str(path))
        data = load_yaml(raw.decode("utf-8"), source=str(path))
        validate(name, data, source=str(path))
        return data

    def execution_policy(self) -> tuple[dict[str, Any] | None, str | None]:
        """The execution policy and its file hash; ``(None, None)`` when the project has none (ADR-0010)."""
        return self._execution_policy(self.manifest, self._pins_in_force())

    def _execution_policy(self, manifest: dict[str, Any],
                          pins: dict[str, str | None] | None) -> tuple[dict[str, Any] | None, str | None]:
        path = X.policy_path(self.aew_root, manifest)
        raw = self._pinned_bytes(path.relative_to(self.aew_root).as_posix(), pins)
        if raw is None:
            return None, None
        return X.parse(raw, source=str(path)), sha256_bytes(raw)

    def _pins_in_force(self) -> dict[str, str | None] | None:
        """The policy pins a read is held to: the open Lead transaction's, else the committed state's (lock-free, the
        reader's view). ``None`` for a project whose policy was never pinned (doctor warns; adopt pins it)."""
        if self._txn_pins is not _NOT_IN_TXN:
            return self._txn_pins
        return self.store.read_committed().get(POLICY_PINS)

    def _pinned_bytes(self, rel: str, pins: dict[str, str | None] | None) -> bytes | None:
        """A policy file's bytes, read once and checked against its pin, so what is used is what was adopted: the
        caller parses these same bytes (no re-read between check and use). ``None`` when the file is absent."""
        path = self.aew_root / rel
        raw = path.read_bytes() if path.is_file() else None
        if pins is not None and (sha256_bytes(raw) if raw is not None else None) != pins.get(rel, "<not pinned>"):
            raise IntegrityError(
                f"policy file {AEW_DIR}/{rel} modified outside AEW; the operator reviews the change and runs "
                "`aew manifest adopt` at their own terminal to accept it", files=[rel])
        return raw

    def manifest_pin_ok(self, state: dict[str, Any]) -> bool:
        return sha256_file(self.aew_root / MANIFEST) == state["manifest_sha256"]

    def policy_pins(self, manifest: dict[str, Any] | None = None) -> dict[str, str | None]:
        """The sha256 of every policy file ``project.yaml`` names, and of the execution policy at its conventional path
        when the manifest names none; ``None`` for a file that does not exist (the execution policy is optional)."""
        return {rel: sha256_file(self.aew_root / rel) if (self.aew_root / rel).is_file() else None
                for rel in policy_files(self.manifest if manifest is None else manifest)}

    def policy_pin_drift(self, state: dict[str, Any], manifest: dict[str, Any] | None = None) -> list[str] | None:
        """The policy files that differ from their pins in control state, or ``None`` for a project whose policy files
        were never pinned (initialized before the pin; ``aew manifest adopt`` pins them). The manifest pin alone left
        gates, guardrails, checks and execution policy editable outside AEW, unrecorded (M4 area-5 review, note 6).
        A lock-free reader passes the manifest it read with ``state``, so this never takes the control lock."""
        pinned = state.get(POLICY_PINS)
        if pinned is None:
            return None
        current = self.policy_pins(manifest)
        return sorted(rel for rel in pinned.keys() | current.keys() if pinned.get(rel) != current.get(rel))

    def check_manifest_pin(self, state: dict[str, Any]) -> None:
        if not self.manifest_pin_ok(state):
            raise IntegrityError(
                f"{AEW_DIR}/{MANIFEST} was modified outside AEW; review the change and run "
                "`aew manifest adopt` at the operator's own terminal to accept it (a Lead session is refused it)",
            )
        drift = self.policy_pin_drift(state)
        if drift:
            raise IntegrityError(
                f"policy file(s) {', '.join(f'{AEW_DIR}/{rel}' for rel in drift)} modified outside AEW; the operator "
                "reviews the change and runs `aew manifest adopt` at their own terminal to accept it", files=drift)

    def workspaces_root(self) -> Path:
        raw = Path(self.manifest.get("workspaces", {}).get("root", f"../.aew-workspaces/{self.project_id}"))
        return raw if raw.is_absolute() else (self.repo_root / raw).resolve()

    # ------------------------------------------------------------------ transactions

    @contextmanager
    def lead_txn(
        self,
        token: str,
        expect_rev: int | None,
        op: str,
        *,
        reason: str | None = None,
        allow_pending: bool = False,
        _adopting_manifest: bool = False,
    ) -> Iterator[TxnContext]:
        """A control transition: current Lead credential + expected revision, atomic commit.

        Authority is checked before the revision so a superseded Lead is told it
        is superseded (STALE_AUTHORITY) rather than merely out of date.
        """
        with self.store.session() as s:
            actor = require_lead(s.state, token, allow_pending=allow_pending, archived=self.archived_credential)
            if expect_rev is None:
                raise StaleRevision("control mutations must state the expected revision (--expect-rev)",
                                    current=s.revision)
            if expect_rev != s.revision:
                raise StaleRevision(
                    f"expected control revision {expect_rev}, current is {s.revision}",
                    expected=expect_rev, current=s.revision,
                )
            if s.state.get("schema") != V2 and op not in V1_OPS and not self.legacy_v1_writes:
                raise MigrationRequired(
                    "this project's control state is v1: migrate it first (the operator runs `aew migrate "
                    "--expect-rev N` at their own terminal); until then the Lead can change the seat and cancel "
                    "invocations, and the operator can adopt the manifest",
                    schema=s.state.get("schema"), next_action="aew migrate --expect-rev N")
            if not _adopting_manifest:
                self.check_manifest_pin(s.state)
            # Adoption validates and pins the files itself; every other transaction reads policy held to its pins.
            self._txn_pins = None if _adopting_manifest else s.state.get(POLICY_PINS)
            try:
                ctx = TxnContext(session=s, actor=actor)
                yield ctx
                self.finalizers.run(ctx)
                s.commit(Transition(op=ctx.op or op, actor=actor, summary=ctx.summary, reason=reason, refs=ctx.refs,
                                    events=ctx.events),
                         expect_rev=expect_rev, state=ctx.commit_state)
            finally:
                self._txn_pins = _NOT_IN_TXN
            for effect in ctx.after_commit:  # best effort, like observation pruning: the commit stands regardless
                try:
                    effect()
                except (AEWError, OSError):
                    pass

    def new_decision(
        self,
        ctx: TxnContext,
        decision_type: str,
        summary: str,
        *,
        work_unit: str | None = None,
        classification: str | None = None,
        evidence_refs: list[str] | None = None,
        resulting_transition: dict[str, Any] | None = None,
        reason: str | None = None,
        decided_by: dict[str, Any] | None = None,
        body: str = "",
        reclassification: dict[str, Any] | None = None,
    ) -> str:
        state = ctx.state
        state["counters"]["decision"] = state["counters"].get("decision", 0) + 1
        decision_id = format_id("D", state["counters"]["decision"])
        record = decision_record(
            decision_id=decision_id,
            decision_type=decision_type,
            decided_by=decided_by or ctx.actor,
            at=utc_now(),
            summary=summary,
            work_unit=work_unit,
            classification=classification,
            evidence_refs=evidence_refs,
            resulting_transition=resulting_transition,
            reason=reason,
            body=body,
            reclassification=reclassification,
        )
        path = f"decisions/{decision_id}.md"
        ctx.session.write(path, record.render())
        ctx.refs.append(path)
        ctx.events.append({"kind": "decision.recorded", "id": decision_id, "type": decision_type})
        return decision_id
