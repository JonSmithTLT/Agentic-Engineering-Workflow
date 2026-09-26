"""The AEW engine facade: the single state authority used by every adapter.

The CLI (and a future MCP adapter) call these methods; neither implements
workflow semantics of its own (WC §15.6, invariant 21).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aew import SPEC_SET
from aew.engine.base import EngineBase
from aew.engine.lead_ops import LeadOps
from aew.engine.status_ops import StatusOps
from aew.engine.evidence_ops import EvidenceOps
from aew.engine.store import ControlStore
from aew.errors import IllegalTransition, IntegrityError, NotFound, UsageError
from aew.knowledge import discovery
from aew.knowledge.manifest import (
    AEW_DIR,
    DEFAULT_CHECKS,
    DEFAULT_GATES,
    DEFAULT_GUARDRAILS,
    MANIFEST,
    default_manifest,
    load_manifest,
    open_questions_template,
    project_overview_template,
    render_manifest,
)
from aew.schemas import validate
from aew.util import dump_yaml, load_yaml, sha256_bytes, sha256_text, utc_now
from aew.workspace import git

AEW_GITIGNORE = "# Rebuildable/runtime data (KC §5.3) and spent redo records.\nlocal/\nstate/txn/\n"
AUTHORITY_CLASSES = ("contracts", "decisions", "schemas", "source", "orientation")


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-._")
    return slug or "project"


class Engine(EvidenceOps, LeadOps, StatusOps):
    # ------------------------------------------------------------------ init

    @classmethod
    def initialize(
        cls,
        repo_root: Path,
        *,
        project_id: str | None = None,
        name: str | None = None,
        branch: str | None = None,
        workspaces_root: str | None = None,
    ) -> "Engine":
        repo_root = repo_root.resolve()
        top = git.toplevel(repo_root)
        if top is None or top.resolve() != repo_root:
            raise UsageError(f"{repo_root} is not the top level of a git repository")
        if git.is_linked_worktree(repo_root):
            raise UsageError("initialize AEW in the main worktree, not a linked worktree")
        aew_root = repo_root / AEW_DIR
        if (aew_root / "state" / "control.yaml").exists():
            raise IntegrityError(f"{aew_root} is already an initialized AEW project")
        branch = branch or git.current_branch(repo_root)
        if not branch:
            raise UsageError("HEAD is detached; pass --branch to name the authoritative branch")
        project_id = project_id or _slug(repo_root.name)
        name = name or repo_root.name
        workspaces_root = workspaces_root or f"../.aew-workspaces/{project_id}"

        manifest = default_manifest(project_id, name, branch, workspaces_root)
        candidates = discovery.discover_candidates(repo_root)
        manifest["authority"]["candidates"] = candidates
        validate("project", manifest, source="new manifest")
        manifest_text = render_manifest(manifest)
        files = {
            MANIFEST: manifest_text,
            ".gitignore": AEW_GITIGNORE,
            "knowledge/PROJECT.md": project_overview_template(name),
            "knowledge/OPEN-QUESTIONS.md": open_questions_template() + discovery.open_questions_for(candidates),
            "policy/guardrails.yaml": dump_yaml(DEFAULT_GUARDRAILS),
            "policy/checks.yaml": dump_yaml(DEFAULT_CHECKS),
            "policy/gates.yaml": dump_yaml(DEFAULT_GATES),
        }
        state = {
            "schema": "aew/control/v1",
            "project_id": project_id,
            "spec_set": SPEC_SET,
            "revision": 0,
            "manifest_sha256": sha256_text(manifest_text),
            "lead": {"schema": "aew/lead/v1", "status": "vacant", "generation": 0, "session_label": None,
                     "token_id": None, "acquired_at": None, "handoff": None},
            "tokens": {},
            "counters": {"ticket": 0, "story": 0, "epic": 0, "invocation": 0, "decision": 0, "handoff": 0},
            "latest_handoff": None,
            "next_action": None,
            "work": {},
            "invocations": {},
            "last_transition": {
                "revision": 0, "at": utc_now(), "actor": {"kind": "operator", "command": "aew init"},
                "op": "init", "summary": f"AEW project '{project_id}' initialized", "reason": None,
                "refs": [], "txn": None,
            },
        }
        ControlStore(aew_root).create(state, files)
        return cls(repo_root, aew_root)

    # ------------------------------------------------------------------ authority registry

    def authority_list(self) -> dict[str, Any]:
        self.store.read()  # recovery + integrity
        return {"accepted": self.manifest["authority"]["accepted"],
                "candidates": self.manifest["authority"]["candidates"]}

    def _rewrite_manifest(self, ctx, manifest: dict[str, Any]) -> None:
        validate("project", manifest, source="updated manifest")
        text = render_manifest(manifest)
        ctx.session.write(MANIFEST, text, immutable=False)
        ctx.state["manifest_sha256"] = sha256_text(text)

    def authority_accept(self, *, token: str, expect_rev: int, candidate_id: str, klass: str,
                         decided_by: str = "lead", reason: str | None = None) -> dict[str, Any]:
        if klass not in AUTHORITY_CLASSES:
            raise UsageError(f"class must be one of {AUTHORITY_CLASSES}")
        with self.lead_txn(token, expect_rev, "authority.accept", reason=reason) as ctx:
            manifest = self._fresh_manifest()
            candidate = self._candidate(manifest, candidate_id)
            if candidate["status"] != "proposed":
                raise IllegalTransition(f"{candidate_id} is already {candidate['status']}")
            by = dict(ctx.actor, kind="operator" if decided_by == "operator" else "lead",
                      recorded_by_lead=True)
            decision = self.new_decision(
                ctx, "authority_acceptance",
                f"Accepted {candidate['path']} as {klass} authority",
                decided_by=by, reason=reason, evidence_refs=[candidate["path"]],
            )
            candidate["status"] = "accepted"
            manifest["authority"]["accepted"].append(
                {"id": candidate_id, "path": candidate["path"], "class": klass, "decision": decision})
            self._rewrite_manifest(ctx, manifest)
            ctx.summary = f"authority accepted: {candidate['path']} ({klass})"
        self.reload_manifest()
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def authority_reject(self, *, token: str, expect_rev: int, candidate_id: str,
                         reason: str | None = None) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "authority.reject", reason=reason) as ctx:
            manifest = self._fresh_manifest()
            candidate = self._candidate(manifest, candidate_id)
            if candidate["status"] != "proposed":
                raise IllegalTransition(f"{candidate_id} is already {candidate['status']}")
            decision = self.new_decision(ctx, "authority_rejection",
                                         f"Rejected {candidate['path']} as project authority", reason=reason)
            candidate["status"] = "rejected"
            self._rewrite_manifest(ctx, manifest)
            ctx.summary = f"authority candidate rejected: {candidate['path']}"
        self.reload_manifest()
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def manifest_adopt(self, *, token: str, expect_rev: int, reason: str) -> dict[str, Any]:
        """Accept a reviewed manual edit of project.yaml by re-pinning it (recorded decision)."""
        manifest_path = self.aew_root / MANIFEST
        # Credential and revision are checked by lead_txn before any state-dependent answer.
        with self.lead_txn(token, expect_rev, "manifest.adopt", reason=reason, _adopting_manifest=True) as ctx:
            if self.manifest_pin_ok(ctx.state):
                raise IllegalTransition("project.yaml matches its pin; nothing to adopt")
            raw = manifest_path.read_bytes()  # pin the exact bytes on disk, not a newline-normalized view
            validate("project", load_yaml(raw.decode("utf-8"), source=str(manifest_path)),
                     source=str(manifest_path))
            decision = self.new_decision(ctx, "manifest_adoption",
                                         "Adopted a reviewed manual edit of project.yaml", reason=reason)
            ctx.state["manifest_sha256"] = sha256_bytes(raw)
            ctx.summary = "manifest re-pinned"
        self.reload_manifest()
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def _fresh_manifest(self) -> dict[str, Any]:
        return load_manifest(self.aew_root)

    @staticmethod
    def _candidate(manifest: dict[str, Any], candidate_id: str) -> dict[str, Any]:
        for c in manifest["authority"]["candidates"]:
            if c["id"] == candidate_id:
                return c
        raise NotFound(f"no authority candidate {candidate_id}")

    # ------------------------------------------------------------------ doctor

    def doctor_checks(self) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []

        def add(name: str, status: str, detail: str) -> None:
            checks.append({"check": name, "status": status, "detail": detail})

        try:
            state = self.store.read()
            add("control-state", "PASS", f"revision {state['revision']}, checksum and schema valid")
        except Exception as exc:  # report, never crash
            add("control-state", "FAIL", f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")
            return checks
        add("manifest-pin", "PASS" if self.manifest_pin_ok(state) else "FAIL",
            "project.yaml matches its pinned hash" if self.manifest_pin_ok(state)
            else "project.yaml modified outside AEW; review then `aew manifest adopt`")
        for name in ("guardrails", "checks", "gates"):
            try:
                self.policy(name)
                add(f"policy:{name}", "PASS", "valid")
            except Exception as exc:
                add(f"policy:{name}", "FAIL", str(exc))
        try:
            checks_policy = self.policy("checks")
            unconfigured = [k for k, v in checks_policy["checks"].items() if not v.get("configured")]
            if unconfigured:
                add("checks-configured", "WARN",
                    f"unconfigured checks {unconfigured}: gates requiring them stay blocked")
            else:
                add("checks-configured", "PASS", "all declared checks configured")
            gates = self.policy("gates")
            if gates.get("mutating_concurrency", 1) > 1:
                add("mutating-concurrency", "WARN",
                    "isolation/integration for concurrency > 1 is not implemented; effective value is 1")
        except Exception:
            pass
        lead = state["lead"]
        add("lead", "PASS" if lead["status"] == "active" else "WARN",
            f"{lead['status']} (generation {lead['generation']})")
        proposed = [c["id"] for c in self.manifest["authority"]["candidates"] if c["status"] == "proposed"]
        if proposed:
            add("authority", "WARN", f"unclassified authority candidates: {proposed}")
        return checks
