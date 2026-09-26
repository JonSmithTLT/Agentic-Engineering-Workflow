"""Engine core: project discovery, policy loading, and Lead-guarded transactions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.engine.authority import require_lead
from aew.engine.store import ControlStore, Session, Transition
from aew.errors import IntegrityError, ProjectNotFound, StaleRevision, WorkspaceNotAuthority
from aew.knowledge import render
from aew.knowledge.manifest import AEW_DIR, MANIFEST, load_manifest
from aew.knowledge.records import decision_record, format_id
from aew.schemas import validate
from aew.util import read_yaml, sha256_file, utc_now
from aew.workspace import git

WORKSPACE_MARKER = "aew-workspace.yaml"  # stored in a linked worktree's private git dir


@dataclass
class TxnContext:
    session: Session
    actor: dict[str, Any]
    summary: str | None = None
    refs: list[str] = field(default_factory=list)

    @property
    def state(self) -> dict[str, Any]:
        return self.session.state


class EngineBase:
    def __init__(self, repo_root: Path, aew_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.aew_root = aew_root.resolve()
        self.manifest = load_manifest(self.aew_root)
        self.store = ControlStore(self.aew_root, renderer=self._render)

    # ------------------------------------------------------------------ discovery

    @classmethod
    def discover(cls, start: Path) -> "EngineBase":
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
                return cls(Path(data["authoritative_repo_root"]), Path(data["authoritative_aew_root"]))
            if (top / AEW_DIR / MANIFEST).exists():
                raise WorkspaceNotAuthority(
                    f"{top / AEW_DIR} is a worktree copy of AEW state, not the authoritative project; "
                    "run aew from the authoritative repository",
                    worktree=str(top),
                )
        for directory in (start, *start.parents):
            if (directory / AEW_DIR / MANIFEST).exists():
                return cls(directory, directory / AEW_DIR)
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

    def _render(self, state: dict[str, Any]) -> dict[str, str]:
        return render.views(state, self.manifest["project"]["name"], self.aew_root)

    def reload_manifest(self) -> None:
        self.manifest = load_manifest(self.aew_root)

    def policy(self, name: str) -> dict[str, Any]:
        path = self.aew_root / self.manifest["policy"][name]
        data = read_yaml(path)
        validate(name, data, source=str(path))
        return data

    def manifest_pin_ok(self, state: dict[str, Any]) -> bool:
        return sha256_file(self.aew_root / MANIFEST) == state["manifest_sha256"]

    def check_manifest_pin(self, state: dict[str, Any]) -> None:
        if not self.manifest_pin_ok(state):
            raise IntegrityError(
                f"{AEW_DIR}/{MANIFEST} was modified outside AEW; review the change and run "
                "`aew manifest adopt` (Lead) to accept it",
            )

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
            actor = require_lead(s.state, token, allow_pending=allow_pending)
            if expect_rev is None:
                raise StaleRevision("control mutations must state the expected revision (--expect-rev)",
                                    current=s.revision)
            if expect_rev != s.revision:
                raise StaleRevision(
                    f"expected control revision {expect_rev}, current is {s.revision}",
                    expected=expect_rev, current=s.revision,
                )
            if not _adopting_manifest:
                self.check_manifest_pin(s.state)
            ctx = TxnContext(session=s, actor=actor)
            yield ctx
            s.commit(Transition(op=op, actor=actor, summary=ctx.summary, reason=reason, refs=ctx.refs),
                     expect_rev=expect_rev)

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
        )
        path = f"decisions/{decision_id}.md"
        ctx.session.write(path, record.render())
        ctx.refs.append(path)
        return decision_id
