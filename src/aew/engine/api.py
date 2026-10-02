"""The AEW engine facade: the single state authority used by every adapter.

The CLI (and a future MCP adapter) call these methods; neither implements
workflow semantics of its own (WC §15.6, invariant 21).

``Engine`` is the composition root (register E5): it builds the Kernel and the collaborators, each given
exactly the collaborators it uses, fills the seams between them (``seams``) in a fixed order, and delegates
every public operation to the one collaborator that owns it. No collaborator holds a reference to the Engine.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aew import SPEC_SET, roles
from aew.engine.archive_ops import Archive
from aew.engine.base import Kernel, TxnContext
from aew.engine.context_ops import ContextPacks
from aew.engine.evidence_ops import EvidenceCommands, Gates
from aew.engine.harness_ops import Harness
from aew.engine.hierarchy_ops import Hierarchy
from aew.engine.integration_ops import Integration
from aew.engine.lead_ops import Lead
from aew.engine.nonmutating_ops import Inputs, NonMutating
from aew.engine.ports import RolesPort
from aew.engine.resume_ops import Resume
from aew.engine.role_ops import Roles
from aew.engine.seams import GuardTable, KindRegistry, StateHooks
from aew.engine.status_ops import StatusViews
from aew.engine.store import ControlStore
from aew.engine.work_ops import WorkCommands, WorkUnits
from aew.engine.workspace_ops import Assignment, Invocations
from aew.errors import IllegalTransition, IntegrityError, NotFound, UsageError
from aew.harness import contract as K
from aew.history import manifest as history_manifest
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
    roles_readme,
)
from aew.policy import execution as X
from aew.schemas import validate
from aew.util import dump_yaml, load_yaml, sha256_bytes, sha256_text, utc_now
from aew.workspace import git

AEW_GITIGNORE = "# Rebuildable/runtime data (KC §5.3) and spent redo records.\nlocal/\nstate/txn/\n"
AUTHORITY_CLASSES = ("contracts", "decisions", "schemas", "source", "orientation")


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-._")
    return slug or "project"


class ProjectAdmin:
    """The project's authority registry, manifest adoption and `aew doctor`."""

    def __init__(self, k: Kernel, *, roles: RolesPort) -> None:
        self.k = k
        self.roles = roles

    def authority_list(self) -> dict[str, Any]:
        self.k.store.read()  # recovery + integrity
        return {"accepted": self.k.manifest["authority"]["accepted"],
                "candidates": self.k.manifest["authority"]["candidates"]}

    def _rewrite_manifest(self, ctx, manifest: dict[str, Any]) -> None:
        validate("project", manifest, source="updated manifest")
        text = render_manifest(manifest)
        ctx.session.write(MANIFEST, text, immutable=False)
        ctx.state["manifest_sha256"] = sha256_text(text)

    def authority_accept(self, *, token: str, expect_rev: int, candidate_id: str, klass: str,
                         decided_by: str = "lead", reason: str | None = None) -> dict[str, Any]:
        if klass not in AUTHORITY_CLASSES:
            raise UsageError(f"class must be one of {AUTHORITY_CLASSES}")
        with self.k.lead_txn(token, expect_rev, "authority.accept", reason=reason) as ctx:
            manifest = self._fresh_manifest()
            candidate = self._candidate(manifest, candidate_id)
            if candidate["status"] != "proposed":
                raise IllegalTransition(f"{candidate_id} is already {candidate['status']}")
            by = dict(ctx.actor, kind="operator" if decided_by == "operator" else "lead",
                      recorded_by_lead=True)
            decision = self.k.new_decision(
                ctx, "authority_acceptance",
                f"Accepted {candidate['path']} as {klass} authority",
                decided_by=by, reason=reason, evidence_refs=[candidate["path"]],
            )
            candidate["status"] = "accepted"
            manifest["authority"]["accepted"].append(
                {"id": candidate_id, "path": candidate["path"], "class": klass, "decision": decision})
            self._rewrite_manifest(ctx, manifest)
            ctx.summary = f"authority accepted: {candidate['path']} ({klass})"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def authority_reject(self, *, token: str, expect_rev: int, candidate_id: str,
                         reason: str | None = None) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "authority.reject", reason=reason) as ctx:
            manifest = self._fresh_manifest()
            candidate = self._candidate(manifest, candidate_id)
            if candidate["status"] != "proposed":
                raise IllegalTransition(f"{candidate_id} is already {candidate['status']}")
            decision = self.k.new_decision(ctx, "authority_rejection",
                                         f"Rejected {candidate['path']} as project authority", reason=reason)
            candidate["status"] = "rejected"
            self._rewrite_manifest(ctx, manifest)
            ctx.summary = f"authority candidate rejected: {candidate['path']}"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def manifest_adopt(self, *, token: str, expect_rev: int, reason: str) -> dict[str, Any]:
        """Accept a reviewed manual edit of project.yaml by re-pinning it (recorded decision)."""
        manifest_path = self.k.aew_root / MANIFEST
        # Credential and revision are checked by lead_txn before any state-dependent answer.
        with self.k.lead_txn(token, expect_rev, "manifest.adopt", reason=reason, _adopting_manifest=True) as ctx:
            if self.k.manifest_pin_ok(ctx.state):
                raise IllegalTransition("project.yaml matches its pin; nothing to adopt")
            raw = manifest_path.read_bytes()  # pin the exact bytes on disk, not a newline-normalized view
            validate("project", load_yaml(raw.decode("utf-8"), source=str(manifest_path)),
                     source=str(manifest_path))
            decision = self.k.new_decision(ctx, "manifest_adoption",
                                         "Adopted a reviewed manual edit of project.yaml", reason=reason)
            ctx.state["manifest_sha256"] = sha256_bytes(raw)
            ctx.summary = "manifest re-pinned"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def _fresh_manifest(self) -> dict[str, Any]:
        return load_manifest(self.k.aew_root)

    @staticmethod
    def _candidate(manifest: dict[str, Any], candidate_id: str) -> dict[str, Any]:
        for c in manifest["authority"]["candidates"]:
            if c["id"] == candidate_id:
                return c
        raise NotFound(f"no authority candidate {candidate_id}")

    def doctor_checks(self) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []

        def add(name: str, status: str, detail: str) -> None:
            checks.append({"check": name, "status": status, "detail": detail})

        try:
            state = self.k.store.read()
            add("control-state", "PASS", f"revision {state['revision']}, checksum and schema valid")
        except Exception as exc:  # report, never crash
            add("control-state", "FAIL", f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")
            return checks
        try:
            _ = self.k.manifest
            add("manifest", "PASS", "project.yaml parses and matches its schema")
        except Exception as exc:
            add("manifest", "FAIL", f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")
            return checks
        add("manifest-pin", "PASS" if self.k.manifest_pin_ok(state) else "FAIL",
            "project.yaml matches its pinned hash" if self.k.manifest_pin_ok(state)
            else "project.yaml modified outside AEW; review then `aew manifest adopt`")
        for name in ("guardrails", "checks", "gates"):
            try:
                self.k.policy(name)
                add(f"policy:{name}", "PASS", "valid")
            except Exception as exc:
                add(f"policy:{name}", "FAIL", str(exc))
        found = self.roles.policy_problems()
        add("policy:consistency", "FAIL" if found else "PASS",
            " ".join(found) if found else "gates, checks and role cards agree")
        try:
            execution, _ = self.k.execution_policy()
            if execution is None or not execution["configured"]:
                add("policy:execution", "WARN", "execution policy unconfigured: harness launch is refused until "
                    f"{X.REL_PATH} is configured (or the Lead pins --profile/--model on dispatch)")
            else:
                add("policy:execution", "PASS", f"configured; default profile {execution['routing']['default']}")
        except Exception as exc:
            add("policy:execution", "FAIL", str(exc))
        from aew.harness import contract as K
        add("containment", "WARN", K.CONTAINMENT_NOTE)  # the actual guarantee, never implied (AEW-INV-ISO-001)
        try:
            checks_policy = self.k.policy("checks")
            unconfigured = [k for k, v in checks_policy["checks"].items() if not v.get("configured")]
            if unconfigured:
                add("checks-configured", "WARN",
                    f"unconfigured checks {unconfigured}: gates requiring them stay blocked")
            else:
                add("checks-configured", "PASS", "all declared checks configured")
            gates = self.k.policy("gates")
            if gates.get("mutating_concurrency", 1) > 1:
                add("mutating-concurrency", "WARN",
                    "isolation/integration for concurrency > 1 is not implemented; effective value is 1")
        except Exception:
            pass
        lead = state["lead"]
        add("lead", "PASS" if lead["status"] == "active" else "WARN",
            f"{lead['status']} (generation {lead['generation']})")
        proposed = [c["id"] for c in self.k.manifest["authority"]["candidates"] if c["status"] == "proposed"]
        if proposed:
            add("authority", "WARN", f"unclassified authority candidates: {proposed}")
        return checks


class Engine:
    """The facade over the Engine's collaborators; see the module docstring."""

    def __init__(self, repo_root: Path, aew_root: Path) -> None:
        k = self._k = Kernel(repo_root, aew_root)
        hooks, guards, kinds = StateHooks(), GuardTable(), KindRegistry()
        self._archive = archive = Archive(k)
        self._units = units = WorkUnits(k, hooks=hooks, guards=guards, archive=archive)
        self._roles = roles = Roles(k, units=units)
        self._invocations = invocations = Invocations(k, roles=roles)
        self._inputs = inputs = Inputs(k)
        self._packs = packs = ContextPacks(k, units=units, archive=archive)
        self._gates = gates = Gates(k, units=units, roles=roles, invocations=invocations, kinds=kinds, archive=archive)
        self._work = work = WorkCommands(k, units=units, roles=roles, invocations=invocations, archive=archive)
        self._assignment = Assignment(k, units=units, roles=roles, invocations=invocations, inputs=inputs,
                                      packs=packs)
        self._nm = nm = NonMutating(k, units=units, roles=roles, invocations=invocations, inputs=inputs, packs=packs,
                                    gates=gates, work=work, archive=archive)
        self._hierarchy = hierarchy = Hierarchy(k, units=units, roles=roles, invocations=invocations, inputs=inputs,
                                                gates=gates, nm=nm, archive=archive)
        self._evidence = evidence = EvidenceCommands(k, units=units, roles=roles, invocations=invocations,
                                                     inputs=inputs, packs=packs, gates=gates, nm=nm, kinds=kinds,
                                                     archive=archive)
        self._integration = integration = Integration(k, units=units, invocations=invocations, gates=gates)
        self._harness = harness = Harness(k, invocations=invocations, packs=packs, gates=gates, archive=archive)
        self._lead = lead = Lead(k, archive=archive)
        self._views = views = StatusViews(k)
        self._resume = resume = Resume(k, units=units, roles=roles, inputs=inputs, gates=gates, hierarchy=hierarchy,
                                       lead=lead, views=views, harness=harness, kinds=kinds)
        self._project = ProjectAdmin(k, roles=roles)
        # The seams, in their documented order (tests/unit/test_engine_composition.py pins them).
        hooks.before.append(integration.before_state_change)
        hooks.after.extend([invocations.on_state_change, integration.on_state_change])
        guards.register_all(units.guard_registrations())
        guards.register_all(gates.guard_registrations())
        guards.register_all(nm.guard_registrations())
        for owner in (gates, evidence, nm, hierarchy, resume):
            kinds.register_all(owner.kind_registrations())
        kinds.require_complete()
        k.finalizers.steps.append(archive.finalize)  # ADR-0011: finished work leaves the hot state (plan R6)
        k.archived_credential = archive.archived_credential  # an archived credential stays stale authority (R7)

    @classmethod
    def discover(cls, start: Path) -> "Engine":
        """The Engine of the authoritative project for ``start`` (``Kernel.locate``)."""
        return cls(*Kernel.locate(start))

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
            X.REL_PATH: X.TEMPLATE,
            "roles/README.md": roles_readme(),
        }
        state = {
            "schema": "aew/control/v2",
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
            "cold": {"root": history_manifest.empty_root()},  # ADR-0011: finished work is archived here
            "last_transition": {
                "revision": 0, "at": utc_now(), "actor": {"kind": "operator", "command": "aew init"},
                "op": "init", "summary": f"AEW project '{project_id}' initialized", "reason": None,
                "refs": [], "txn": None,
            },
        }
        ControlStore(aew_root).create(state, files)
        return cls(repo_root, aew_root)

    # ------------------------------------------------------------------ delegation (one owner per operation)

    @property
    def repo_root(self) -> Path:
        return self._k.repo_root

    @property
    def aew_root(self) -> Path:
        return self._k.aew_root

    @property
    def store(self) -> ControlStore:
        return self._k.store

    @property
    def NM_PRE_REVIEW(self) -> Any:
        return self._nm.NM_PRE_REVIEW

    @property
    def PRE_REVIEW(self) -> Any:
        return self._gates.PRE_REVIEW

    def accepted_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._gates.accepted_gate_context(state, work_id)

    def accepted_plan_ref(self, unit: dict[str, Any]) -> dict[str, Any] | None:
        return self._units.accepted_plan_ref(unit)

    def ancestor_plan_snapshot(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._units.ancestor_plan_snapshot(state, work_id)

    @property
    def authoritative_branch(self) -> Any:
        return self._k.authoritative_branch

    def authoritative_commit(self) -> str | None:
        return self._k.authoritative_commit()

    def authority_accept(self, *, token: str, expect_rev: int, candidate_id: str, klass: str, decided_by: str = "lead",
                         reason: str | None = None) -> dict[str, Any]:
        return self._project.authority_accept(token=token, expect_rev=expect_rev, candidate_id=candidate_id,
                                              klass=klass, decided_by=decided_by, reason=reason)

    def authority_list(self) -> dict[str, Any]:
        return self._project.authority_list()

    def authority_reject(self, *, token: str, expect_rev: int, candidate_id: str,
                         reason: str | None = None) -> dict[str, Any]:
        return self._project.authority_reject(token=token, expect_rev=expect_rev, candidate_id=candidate_id,
                                              reason=reason)

    def before_commit(self, ctx: TxnContext) -> None:
        return self._units.before_commit(ctx)

    def bind_plan_assurance(self, unit: dict[str, Any], revision: int, assurance: dict[str, list[str]] | None) -> None:
        return self._roles.bind_plan_assurance(unit, revision, assurance)

    def binding_problem(self, unit: dict[str, Any]) -> dict[str, Any] | None:
        return self._gates.binding_problem(unit)

    def build_pack(self, ctx: TxnContext, inv_id: str) -> None:
        return self._packs.build_pack(ctx, inv_id)

    def check_manifest_pin(self, state: dict[str, Any]) -> None:
        return self._k.check_manifest_pin(state)

    def check_run(self, *, invocation_token: str, check_id: str, env: dict[str, str] | None = None) -> dict[str, Any]:
        return self._evidence.check_run(invocation_token=invocation_token, check_id=check_id, env=env)

    def checkpoint(self, *, token: str, expect_rev: int, note: str = "", next_action: str | None = None) -> dict[str,
                   Any]:
        return self._resume.checkpoint(token=token, expect_rev=expect_rev, note=note, next_action=next_action)

    def children_digest(self, state: dict[str, Any], work_id: str) -> str:
        return self._hierarchy.children_digest(state, work_id)

    def classify_parent_verification(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                                     reason: str) -> dict[str, Any]:
        return self._hierarchy.classify_parent_verification(token=token, expect_rev=expect_rev, work_id=work_id,
                                                            classification=classification, reason=reason)

    def completion_sha(self, state: dict[str, Any], work_id: str) -> str | None:
        return self._units.completion_sha(state, work_id)

    def consumed_inputs(self, state: dict[str, Any], work_id: str) -> list[dict[str, Any]]:
        return self._inputs.consumed_inputs(state, work_id)

    def context_pack(self, inv_id: str) -> dict[str, Any]:
        return self._packs.context_pack(inv_id)

    def context_show(self, inv_id: str) -> str:
        return self._packs.context_show(inv_id)

    def contradictions(self, state: dict[str, Any]) -> list[str]:
        return self._views.contradictions(state)

    def current_snapshot(self, unit: dict[str, Any]) -> dict[str, Any] | None:
        return self._invocations.current_snapshot(unit)

    def dispatch_binding_problem(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        return self._units.dispatch_binding_problem(state, work_id)

    def dispatch_commit(self, unit: dict[str, Any]) -> str | None:
        return self._inputs.dispatch_commit(unit)

    def dispatch_inputs(self, state: dict[str, Any], work_id: str, commit: str | None) -> list[dict[str, Any]]:
        return self._inputs.dispatch_inputs(state, work_id, commit)

    def doctor_checks(self) -> list[dict[str, str]]:
        return self._project.doctor_checks()

    def effective_role_plan(self, state: dict[str, Any], work_id: str, gc: dict[str, Any] | None = None) -> dict[str,
                            Any]:
        return self._roles.effective_role_plan(state, work_id, gc)

    def evidence_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._gates.evidence_gate_context(state, work_id)

    def evidence_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._nm.evidence_ingest(token=token, expect_rev=expect_rev, work_id=work_id, evidence_id=evidence_id)

    def execute_record_binding(self, state: dict[str, Any], inv_id: str, inv: dict[str, Any], kind: str,
                               submitted: dict[str, Any]) -> dict[str, Any]:
        return self._nm.execute_record_binding(state, inv_id, inv, kind, submitted)

    def execute_record_status(self, state: dict[str, Any], work_id: str, records: dict[str, dict[str, Any]],
                              commit: str | None) -> dict[str, Any]:
        return self._nm.execute_record_status(state, work_id, records, commit)

    def execution_policy(self) -> tuple[dict[str, Any] | None, str | None]:
        return self._k.execution_policy()

    def expected_kinds(self, state: dict[str, Any], inv: dict[str, Any]) -> list[str]:
        return self._harness.expected_kinds(state, inv)

    def gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._gates.gate_context(state, work_id)

    def gate_show(self, work_id: str) -> dict[str, Any]:
        return self._gates.gate_show(work_id)

    def harness_config(self, harness: str, *, invocation: str | None = None, lead: bool = False) -> dict[str, Any]:
        from aew.harness.opencode import lead as oclead

        return self._harness.harness_config(harness, invocation=invocation, lead=lead,
                                            lead_projection=lambda: oclead.describe(self, provider_env=[]))

    def harness_contract(self, state: dict[str, Any], inv_id: str, run: str) -> K.LaunchContract:
        return self._harness.harness_contract(state, inv_id, run)

    def harness_interrupt(self, *, token: str, run: str) -> dict[str, Any]:
        return self._harness.harness_interrupt(token=token, run=run)

    def harness_launch(self, *, token: str, expect_rev: int, invocation: str, replace: bool = False) -> dict[str, Any]:
        return self._harness.harness_launch(token=token, expect_rev=expect_rev, invocation=invocation, replace=replace)

    def harness_resume(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return self._harness.harness_resume(state)

    def harness_send(self, *, token: str, run: str, text: str) -> dict[str, Any]:
        return self._harness.harness_send(token=token, run=run, text=text)

    def harness_status(self, invocation: str | None = None) -> dict[str, Any]:
        return self._harness.harness_status(invocation)

    def harness_stop(self, *, token: str, run: str, reason: str) -> dict[str, Any]:
        return self._harness.harness_stop(token=token, run=run, reason=reason)

    def harness_wait(self, run: str, *, timeout: float = 600.0) -> dict[str, Any]:
        return self._harness.harness_wait(run, timeout=timeout)

    def ingest_evidence_unit_report(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str,
                                    kind: str) -> dict[str, Any]:
        return self._evidence.ingest_evidence_unit_report(token=token, expect_rev=expect_rev, work_id=work_id,
                                                          evidence_id=evidence_id, kind=kind)

    def input_status(self, state: dict[str, Any], work_id: str) -> list[dict[str, Any]]:
        return self._inputs.input_status(state, work_id)

    def inspect_workspace(self, unit: dict[str, Any]) -> dict[str, Any]:
        return self._invocations.inspect_workspace(unit)

    def integrate_prepare(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        return self._integration.integrate_prepare(token=token, expect_rev=expect_rev, work_id=work_id)

    def integrate_publish(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        return self._integration.integrate_publish(token=token, expect_rev=expect_rev, work_id=work_id)

    def integrate_reconcile(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        return self._integration.integrate_reconcile(token=token, expect_rev=expect_rev, work_id=work_id)

    def integration_binding(self, unit: dict[str, Any]) -> dict[str, Any]:
        return self._gates.integration_binding(unit)

    def invocation_whoami(self, *, invocation_token: str) -> dict[str, Any]:
        return self._harness.invocation_whoami(invocation_token=invocation_token)

    def invoke_cancel(self, *, token: str, expect_rev: int, invocation: str, reason: str) -> dict[str, Any]:
        return self._evidence.invoke_cancel(token=token, expect_rev=expect_rev, invocation=invocation, reason=reason)

    def invoke_create(self, *, token: str, expect_rev: int, work_id: str, role: str | None = None,
                      card: str | None = None, scope: str = "ticket", execution_profile: dict[str, Any] | None = None,
                      launch: bool = False) -> dict[str, Any]:
        return self._evidence.invoke_create(token=token, expect_rev=expect_rev, work_id=work_id, role=role, card=card,
                                            scope=scope, execution_profile=execution_profile, launch=launch)

    def invoke_evidence_unit(self, *, token: str, expect_rev: int, work_id: str, role: str | None, card: str | None,
                             scope: str, execution_profile: dict[str, Any] | None = None,
                             launch: bool = False) -> dict[str, Any]:
        return self._evidence.invoke_evidence_unit(token=token, expect_rev=expect_rev, work_id=work_id, role=role,
                                                   card=card, scope=scope, execution_profile=execution_profile,
                                                   launch=launch)

    def invoke_show(self, invocation: str) -> dict[str, Any]:
        return self._evidence.invoke_show(invocation)

    def launch_dispatched(self, result: dict[str, Any]) -> dict[str, Any]:
        return self._harness.launch_dispatched(result)

    def lead_acquire(self, *, expect_rev: int, session_label: str | None = None) -> dict[str, Any]:
        return self._lead.lead_acquire(expect_rev=expect_rev, session_label=session_label)

    def lead_guide(self) -> str:
        return self._resume.lead_guide()

    def lead_handoff_accept(self, *, offer: str, expect_rev: int, session_label: str | None = None) -> dict[str, Any]:
        return self._lead.lead_handoff_accept(offer=offer, expect_rev=expect_rev, session_label=session_label)

    def lead_handoff_cancel(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        return self._lead.lead_handoff_cancel(token=token, expect_rev=expect_rev)

    def lead_handoff_offer(self, *, token: str, expect_rev: int, note: str = "",
                           carry_invocations: list[str] | None = None) -> dict[str, Any]:
        return self._lead.lead_handoff_offer(token=token, expect_rev=expect_rev, note=note,
                                             carry_invocations=carry_invocations)

    def lead_release(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        return self._lead.lead_release(token=token, expect_rev=expect_rev)

    def lead_show(self) -> dict[str, Any]:
        return self._lead.lead_show()

    def lead_takeover(self, *, expect_rev: int, reason: str, session_label: str | None = None) -> dict[str, Any]:
        return self._lead.lead_takeover(expect_rev=expect_rev, reason=reason, session_label=session_label)

    def lead_txn(self, token: str, expect_rev: int | None, op: str, *, reason: str | None = None,
                 allow_pending: bool = False, _adopting_manifest: bool = False) -> Iterator[TxnContext]:
        return self._k.lead_txn(token, expect_rev, op, reason=reason, allow_pending=allow_pending,
                                _adopting_manifest=_adopting_manifest)

    @property
    def manifest(self) -> Any:
        return self._k.manifest

    def manifest_adopt(self, *, token: str, expect_rev: int, reason: str) -> dict[str, Any]:
        return self._project.manifest_adopt(token=token, expect_rev=expect_rev, reason=reason)

    def manifest_pin_ok(self, state: dict[str, Any]) -> bool:
        return self._k.manifest_pin_ok(state)

    def new_decision(self, ctx: TxnContext, decision_type: str, summary: str, *, work_unit: str | None = None,
                     classification: str | None = None, evidence_refs: list[str] | None = None,
                     resulting_transition: dict[str, Any] | None = None, reason: str | None = None,
                     decided_by: dict[str, Any] | None = None, body: str = "") -> str:
        return self._k.new_decision(ctx, decision_type, summary, work_unit=work_unit, classification=classification,
                                    evidence_refs=evidence_refs, resulting_transition=resulting_transition,
                                    reason=reason, decided_by=decided_by, body=body)

    def next_actions(self, state: dict[str, Any]) -> list[str]:
        return self._resume.next_actions(state)

    def operations_of(self, inv: dict[str, Any]) -> list[str]:
        return self._harness.operations_of(inv)

    def plan_accept(self, *, token: str, expect_rev: int, work_id: str, revision: int) -> dict[str, Any]:
        return self._work.plan_accept(token=token, expect_rev=expect_rev, work_id=work_id, revision=revision)

    def plan_adopt(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str, source: str,
                   reason: str | None = None, review: list[str] | None = None, verify: list[str] | None = None,
                   no_assurance: bool = False) -> dict[str, Any]:
        return self._nm.plan_adopt(token=token, expect_rev=expect_rev, work_id=work_id, evidence_id=evidence_id,
                                   source=source, reason=reason, review=review, verify=verify,
                                   no_assurance=no_assurance)

    def plan_binding_problem(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        return self._units.plan_binding_problem(state, work_id)

    def plan_gate_status(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._gates.plan_gate_status(state, work_id)

    def plan_gates(self, unit: dict[str, Any]) -> dict[str, str]:
        return self._roles.plan_gates(unit)

    def plan_propose(self, *, token: str, expect_rev: int, work_id: str, body: str, reason: str | None = None,
                     affected_paths: list[str] | None = None, review: list[str] | None = None,
                     verify: list[str] | None = None, no_assurance: bool = False) -> dict[str, Any]:
        return self._work.plan_propose(token=token, expect_rev=expect_rev, work_id=work_id, body=body, reason=reason,
                                       affected_paths=affected_paths, review=review, verify=verify,
                                       no_assurance=no_assurance)

    def plan_reconfirm(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        return self._nm.plan_reconfirm(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def policy(self, name: str) -> dict[str, Any]:
        return self._k.policy(name)

    def policy_problems(self) -> list[str]:
        return self._roles.policy_problems()

    @property
    def project_id(self) -> Any:
        return self._k.project_id

    def prune_observations(self, state: dict[str, Any] | None = None) -> list[str]:
        return self._nm.prune_observations(state)

    def render_resume(self, r: dict[str, Any]) -> str:
        return self._resume.render_resume(r)

    def render_status(self, report: dict[str, Any]) -> str:
        return self._views.render_status(report)

    def require_dispatch_binding(self, state: dict[str, Any], work_id: str) -> None:
        return self._units.require_dispatch_binding(state, work_id)

    def require_observation_intact(self, inv_id: str, inv: dict[str, Any]) -> None:
        return self._nm.require_observation_intact(inv_id, inv)

    def require_plan_binding(self, state: dict[str, Any], work_id: str) -> None:
        return self._units.require_plan_binding(state, work_id)

    def require_reported_workspace(self, work_id: str, unit: dict[str, Any], gc: dict[str, Any]) -> None:
        return self._gates.require_reported_workspace(work_id, unit, gc)

    def require_workspace_intact(self, inv_id: str, inv: dict[str, Any], workspace: Path, ws_id: str) -> None:
        return self._gates.require_workspace_intact(inv_id, inv, workspace, ws_id)

    def resolve_card(self, state: dict[str, Any], work_id: str, slot: str, *, card_id: str | None, role: str | None,
                     gc: dict[str, Any] | None = None) -> roles.Card:
        return self._roles.resolve_card(state, work_id, slot, card_id=card_id, role=role, gc=gc)

    def resolve_plan_assurance(self, unit: dict[str, Any], *, review: list[str] | None, verify: list[str] | None,
                               none: bool) -> dict[str, list[str]]:
        return self._roles.resolve_plan_assurance(unit, review=review, verify=verify, none=none)

    def resume(self, session: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._resume.resume(session)

    def review_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._evidence.review_ingest(token=token, expect_rev=expect_rev, work_id=work_id,
                                            evidence_id=evidence_id)

    def role_catalog(self) -> roles.Catalog:
        return self._roles.role_catalog()

    def role_list(self) -> dict[str, Any]:
        return self._roles.role_list()

    def role_show(self, card_id: str) -> dict[str, Any]:
        return self._roles.role_show(card_id)

    def role_validate(self, path: str | None = None) -> dict[str, Any]:
        return self._roles.role_validate(path)

    def rollup(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._units.rollup(state, work_id)

    def run_authority_problem(self, state: dict[str, Any], inv_id: str, run: str, token_id: str) -> str | None:
        return self._harness.run_authority_problem(state, inv_id, run, token_id)

    def run_evidence(self, work_unit: str, run: str,
                     _cache: dict[str, list[dict[str, Any]]] | None = None) -> list[str]:
        return self._harness.run_evidence(work_unit, run, _cache)

    def run_results(self, work_unit: str, run: str, _cache: dict[str, list[dict[str, Any]]] | None = None) -> dict[str,
                    str]:
        return self._harness.run_results(work_unit, run, _cache)

    def snapshot_of(self, path: str | Path, workspace_id: str) -> dict[str, Any]:
        return self._invocations.snapshot_of(path, workspace_id)

    def status(self, work_id: str | None = None) -> dict[str, Any]:
        return self._resume.status(work_id)

    def submit(self, *, invocation_token: str, kind: str, text: str) -> dict[str, Any]:
        return self._evidence.submit(invocation_token=invocation_token, kind=kind, text=text)

    def tree_lines(self, tree: list[dict[str, Any]]) -> list[str]:
        return self._hierarchy.tree_lines(tree)

    def archived_credential(self, state: dict[str, Any], token_id: str) -> dict[str, Any] | None:
        """A credential archived with finished work (ADR-0011 R7), for checks outside the engine (the Lead broker, a
        run's supervisor): presenting it again is stale authority, never an unknown credential."""
        return self._archive.archived_credential(state, token_id)

    def unit(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._units.unit(state, work_id)

    def verify_classify(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                        reason: str) -> dict[str, Any]:
        return self._evidence.verify_classify(token=token, expect_rev=expect_rev, work_id=work_id,
                                              classification=classification, reason=reason)

    def verify_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._evidence.verify_ingest(token=token, expect_rev=expect_rev, work_id=work_id,
                                            evidence_id=evidence_id)

    def waive(self, *, token: str, expect_rev: int, work_id: str, reason: str, gate: str | None = None,
              finding: str | None = None) -> dict[str, Any]:
        return self._evidence.waive(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason, gate=gate,
                                    finding=finding)

    def work_accept(self, *, token: str, expect_rev: int, work_id: str, reason: str | None = None) -> dict[str, Any]:
        return self._nm.work_accept(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def work_acknowledge_input(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str, source: str,
                               reason: str) -> dict[str, Any]:
        return self._nm.work_acknowledge_input(token=token, expect_rev=expect_rev, work_id=work_id,
                                               evidence_id=evidence_id, source=source, reason=reason)

    def work_assign(self, *, token: str, expect_rev: int, work_id: str, execution_profile: dict[str, Any] | None = None,
                    launch: bool = False) -> dict[str, Any]:
        return self._assignment.work_assign(token=token, expect_rev=expect_rev, work_id=work_id,
                                            execution_profile=execution_profile, launch=launch)

    def work_cancel(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        return self._hierarchy.work_cancel(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def work_close(self, *, token: str, expect_rev: int, work_id: str, reason: str | None = None) -> dict[str, Any]:
        return self._hierarchy.work_close(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def work_create(self, *, token: str, expect_rev: int, kind: str, title: str, risk_class: int,
                    mutating: bool | None = None, parent: str | None = None, depends_on: list[str] | None = None,
                    scope_paths: list[str] | None = None, goal_backwards: list[str] | None = None,
                    contract: list[str] | None = None, mandatory_gates: list[str] | None = None,
                    min_descendant_class: int | None = None, rationale: str | None = None,
                    external_refs: list[str] | None = None, body: str = "", card: str | None = None,
                    promoted_from: str | None = None) -> dict[str, Any]:
        return self._work.work_create(token=token, expect_rev=expect_rev, kind=kind, title=title, risk_class=risk_class,
                                      mutating=mutating, parent=parent, depends_on=depends_on, scope_paths=scope_paths,
                                      goal_backwards=goal_backwards, contract=contract, mandatory_gates=mandatory_gates,
                                      min_descendant_class=min_descendant_class, rationale=rationale,
                                      external_refs=external_refs, body=body, card=card, promoted_from=promoted_from)

    def work_depend(self, *, token: str, expect_rev: int, work_id: str, add: list[str] | None = None,
                    remove: list[str] | None = None, reason: str) -> dict[str, Any]:
        return self._hierarchy.work_depend(token=token, expect_rev=expect_rev, work_id=work_id, add=add, remove=remove,
                                           reason=reason)

    def work_dispatch(self, *, token: str, expect_rev: int, work_id: str, card: str | None = None,
                      execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        return self._nm.work_dispatch(token=token, expect_rev=expect_rev, work_id=work_id, card=card,
                                      execution_profile=execution_profile, launch=launch)

    def work_list(self, *, state_filter: str | None = None) -> dict[str, Any]:
        return self._work.work_list(state_filter=state_filter)

    def work_move(self, *, token: str, expect_rev: int, work_id: str, parent: str | None, reason: str) -> dict[str,
                  Any]:
        return self._hierarchy.work_move(token=token, expect_rev=expect_rev, work_id=work_id, parent=parent,
                                         reason=reason)

    def work_promote(self, *, token: str, expect_rev: int, work_id: str, to: str, title: str, reason: str,
                     risk_class: int | None = None) -> dict[str, Any]:
        return self._hierarchy.work_promote(token=token, expect_rev=expect_rev, work_id=work_id, to=to, title=title,
                                            reason=reason, risk_class=risk_class)

    def work_reconcile(self, *, token: str, expect_rev: int, work_id: str, to: str, reason: str,
                       inspection: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._nm.work_reconcile(token=token, expect_rev=expect_rev, work_id=work_id, to=to, reason=reason,
                                       inspection=inspection)

    def work_redispatch(self, *, token: str, expect_rev: int, work_id: str, reason: str, card: str | None = None,
                        execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        return self._nm.work_redispatch(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason, card=card,
                                        execution_profile=execution_profile, launch=launch)

    def work_roles(self, work_id: str) -> dict[str, Any]:
        return self._gates.work_roles(work_id)

    def work_show(self, work_id: str) -> dict[str, Any]:
        return self._work.work_show(work_id)

    def work_staff(self, *, token: str, expect_rev: int, work_id: str, execute: list[str] | None = None,
                   review: list[str] | None = None, verify: list[str] | None = None, forbid: list[str] | None = None,
                   remove: list[str] | None = None, selected_by: str = "lead", pin: bool = False,
                   reason: str | None = None) -> dict[str, Any]:
        return self._roles.work_staff(token=token, expect_rev=expect_rev, work_id=work_id, execute=execute,
                                      review=review, verify=verify, forbid=forbid, remove=remove,
                                      selected_by=selected_by, pin=pin, reason=reason)

    def work_transition(self, *, token: str, expect_rev: int, work_id: str, to: str,
                        reason: str | None = None) -> dict[str, Any]:
        return self._work.work_transition(token=token, expect_rev=expect_rev, work_id=work_id, to=to, reason=reason)

    def work_tree(self, root: str | None = None) -> dict[str, Any]:
        return self._hierarchy.work_tree(root)

    def workspaces_root(self) -> Path:
        return self._k.workspaces_root()

    def _require_gates(self, gc: dict[str, Any], names: list[str], *, what: str) -> None:
        return self._gates.require_gates(gc, names, what=what)
