"""Invocations, checks, evidence submission, gates, review/verification ingest, classification.

Authority split (WC §6, KC §16):
* bounded roles run checks and submit evidence with their invocation credential;
* the engine binds evidence to the evaluated snapshot it computes itself;
* the Lead ingests results, and the state they imply is applied mechanically;
* after VERIFICATION_FAILED only the Lead's classification selects the next path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import gates as G
from aew.engine import transitions
from aew.engine.authority import require_invocation
from aew.engine.base import TxnContext
from aew.engine.dispatch import GuardRegistration as DispatchGuard
from aew.engine.dispatch import blocker_from, checked
from aew.engine.guards import NotQueryable, require
from aew.engine.guards import checked as guard_checked
from aew.engine.seams import (
    CLASSIFY_VERIFICATION,
    GATE_CONTEXT,
    INGEST,
    INVOKE,
    MUTATING,
    NON_MUTATING,
    GuardRegistration,
    KindRegistration,
)
from aew.errors import (
    GateUnsatisfied,
    IllegalTransition,
    NotFound,
    PermissionDenied,
    StaleAuthority,
    StaleCandidate,
    UsageError,
    ValidationFailed,
    WorkspaceMutated,
)
from aew.knowledge import evidence as E
from aew.knowledge.records import read_record
from aew.policy import checks as C
from aew.policy import guardrails as GR
from aew.schemas import validate_property
from aew.snapshot.fingerprint import changed_paths
from aew.util import create_exclusive, parse_frontmatter, sha256_file, utc_now
from aew.workspace.integration import changed_between as git_changed_between

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import (
        ArchivePort,
        ContextPacksPort,
        DispatchPort,
        GatesPort,
        InputsPort,
        InvocationsPort,
        NonMutatingPort,
        QueuePort,
        RolesPort,
        WorkUnitsPort,
    )
    from aew.engine.seams import KindRegistry

REVIEW_ROLES = {"reviewer"}
# Read-only roles that work in a live workspace they share with the implementer, or in an integration candidate
# (M3-B6); in observation scope the same roles are covered by ObservationMutated (ADR-0008).
SHARED_WORKSPACE_READERS = {"reviewer", "verifier"}


class Gates:
    """Effective obligations and gate status per unit, the gate-based Lead guards of mutating Tickets, and the bindings
    a report or candidate must hold. The gate context of each unit kind comes from the ``KindRegistry``: a mutating
    Ticket's is computed here, a non-mutating Ticket's and a parent's by their own collaborators."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, roles: RolesPort, invocations: InvocationsPort,
                 kinds: KindRegistry, archive: ArchivePort) -> None:
        self.k = k
        self.units = units
        self.roles = roles
        self.invocations = invocations
        self.kinds = kinds
        self.archive = archive

    def record_meta(self, unit: dict[str, Any]) -> dict[str, Any]:
        return read_record(self.k.aew_root / unit["record"], "work-unit").meta

    @staticmethod
    def _paths_between(workspace: Path, fingerprint_a: str | None, fingerprint_b: str | None) -> list[str]:
        """Paths that differ between two evaluated-snapshot fingerprints (both are git trees)."""
        a, b = (str(f or "").removeprefix("git-tree:") for f in (fingerprint_a, fingerprint_b))
        if not a or not b:
            return []
        try:
            return sorted(git_changed_between(workspace, a, b))
        except Exception:  # a tree that is no longer in the object store: the refusal stands without paths
            return []

    def require_workspace_intact(self, inv_id: str, inv: dict[str, Any], workspace: Path, ws_id: str) -> None:
        """A reviewer or verifier evaluates exactly the snapshot it was dispatched for (M3-B6). Its workspace is
        shared with the implementer's work (or is the integration candidate), so an edit there would otherwise be
        found only later, as a stale review, and attributed to nobody."""
        pinned = (inv.get("snapshot") or {}).get("relevant_inputs_fingerprint")
        current = self.invocations.snapshot_of(workspace, ws_id)["relevant_inputs_fingerprint"]
        if pinned and current != pinned:
            raise WorkspaceMutated(
                f"{inv_id} ({inv['role']}) may not change the workspace it evaluates; it now differs from the "
                "snapshot the invocation was dispatched for. The Lead returns the Ticket to RUNNING, so that an "
                "implementer reports or restores the change", invocation=inv_id, workspace=str(workspace),
                changed=self._paths_between(workspace, pinned, current))

    def require_reported_workspace(self, work_id: str, unit: dict[str, Any], gc: dict[str, Any]) -> None:
        """A reviewer or verifier is dispatched only for the implementation that was reported: the workspace still
        holds the snapshot the implementer's checks and self-review evaluated (M3-B6)."""
        stale = {g: s for g, s in G.unmet(gc["gates"], self.PRE_REVIEW).items() if s == G.STALE}
        if not stale:
            return
        workspace = Path((unit.get("workspace") or {}).get("path") or ".")
        reports = [e for e in gc["evidence"] if e["kind"] == "implementation_report"
                   and e["producer"].get("invocation") == unit.get("implementer_invocation")]
        reported = (reports[-1]["evaluated_snapshot"] if reports else {}).get("relevant_inputs_fingerprint")
        current = (gc.get("snapshot") or {}).get("relevant_inputs_fingerprint")
        raise WorkspaceMutated(
            f"{work_id}'s workspace no longer holds the implementation that was reported ({', '.join(sorted(stale))} "
            "are stale); a reviewer or verifier would evaluate unreported changes. Return the Ticket to RUNNING so "
            "that an implementer reports or restores them", work_id=work_id, stale=sorted(stale),
            changed=self._paths_between(workspace, reported, current))

    def gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """The unit's effective obligations and gate status, from the handler registered for its kind."""
        return self.kinds.resolve(GATE_CONTEXT, self.units.unit(state, work_id))(state, work_id)

    def _ticket_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """A mutating Ticket's obligations and gate status for the workspace's *current* evaluated snapshot."""
        unit = self.units.unit(state, work_id)
        snapshot = self.invocations.current_snapshot(unit)
        ws = unit.get("workspace")
        changed = changed_paths(Path(ws["path"]), ws["base_commit"]) if snapshot and ws else None
        return self._gates_at(state, work_id, snapshot, changed)

    def accepted_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """Obligations and gates re-evaluated at the ACCEPTED (COMMIT_READY) snapshot (foundation review).

        Used at publication: obligations added after acceptance (an operator-pinned card, a new policy
        gate) must be met before DONE. Guardrail triggers come from the committed Ticket diff and the
        fingerprint from the gated snapshot, so later workspace edits cannot change the answer.
        """
        unit = self.units.unit(state, work_id)
        integ = unit.get("integration") or {}
        ws = unit.get("workspace") or {}
        changed = git_changed_between(self.k.repo_root, ws["base_commit"], integ["ticket_commit"])
        return self._gates_at(state, work_id, unit.get("commit_ready_snapshot"), changed)

    def _gates_at(self, state: dict[str, Any], work_id: str, snapshot: dict[str, Any] | None,
                  changed: list[str] | None) -> dict[str, Any]:
        unit = self.units.unit(state, work_id)
        gates_policy = self.k.policy("gates")
        guard = {"violations": [], "triggered_gates": [], "changed_paths": []}
        meta = self.record_meta(unit)
        acceptance = meta.get("acceptance") or {}
        if changed is not None:
            guard = GR.evaluate(changed, self.k.policy("guardrails"), (meta.get("scope") or {}).get("paths", []),
                                acceptance.get("inputs"))
        declared = list(acceptance.get("checks") or [])
        obligations = G.with_acceptance_checks(
            G.effective_obligations(state, work_id, gates_policy, guard["triggered_gates"],
                                    self.roles.plan_gates(unit)),
            declared)
        evidence, problems = E.scan(self.k.aew_root, work_id)
        plan = unit.get("plan") or {}
        plan_ok = bool(plan) and sha256_file(self.k.aew_root / plan["path"]) == plan["sha256"]
        fingerprint = snapshot["relevant_inputs_fingerprint"] if snapshot else None
        results = G.evaluate(state, work_id, evidence, obligations=obligations, gates_policy=gates_policy,
                             fingerprint=fingerprint, plan_ok=plan_ok,
                             check_definitions=C.current_definitions(self.k.policy("checks"),
                                                                     self.k.policy("guardrails")),
                             acceptance_checks=declared)
        binding = self.units.plan_binding_problem(state, work_id)
        if binding and results.get("accepted_plan", {}).get("status") == G.CURRENT:
            # An ancestor's accepted plan changed after this plan was accepted (ADR-0007, fail closed).
            results["accepted_plan"] = {"status": G.STALE, "detail": binding,
                                        "action": f"`aew plan reconfirm {work_id} --reason ...` or a new plan revision"}
        return {"work_id": work_id, "snapshot": snapshot, "guardrails": guard, "obligations": obligations,
                "gates": results, "evidence": evidence, "evidence_problems": problems,
                "open_required_findings": G.open_required_findings(unit), "plan_binding": binding,
                "dispatch_binding": self.units.dispatch_binding_problem(state, work_id)}

    def evidence_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """The gate context of an evidence-only unit, from the collaborator registered for its kind: a Story or Epic's
        (ADR-0007), otherwise a non-mutating Ticket's (ADR-0008)."""
        return self.kinds.resolve_evidence_only(GATE_CONTEXT, self.units.unit(state, work_id))(state, work_id)

    def gate_show(self, work_id: str) -> dict[str, Any]:
        state = self.k.store.read()
        if work_id not in state["work"]:  # an archived unit's gates, as they stood when it finished (R7)
            state = self.archive.rehydrate(state, work_id) or state
        gc = self.gate_context(state, work_id)
        gc.pop("evidence")
        gc["evidence_ids"] = [e["id"] for e in E.scan(self.k.aew_root, work_id)[0]]
        gc["unmet"] = G.unmet(gc["gates"])
        if gc.get("plan_binding"):
            gc["unmet"].setdefault("accepted_plan", G.STALE)  # blocks progress even off the risk path (B1)
        return gc

    def require_gates(self, gc: dict[str, Any], names: list[str], *, what: str) -> None:
        unmet = G.unmet(gc["gates"], [n for n in names if n in gc["obligations"]["gates"]])
        if gc["evidence_problems"]:
            raise GateUnsatisfied("evidence integrity problems", problems=gc["evidence_problems"])
        if gc["guardrails"]["violations"]:
            violations = gc["guardrails"]["violations"]
            message = f"{what}: guardrail violations: {GR.describe(violations)}"
            if any(v["rule"] == "outside_ticket_scope" for v in violations):  # M3 dogfood report §6.6 (E9)
                message += ". " + GR.scope_remedy(gc.get("work_id") or "<T>")
            raise GateUnsatisfied(message, violations=violations)
        if gc.get("plan_binding"):
            # An accepted plan stays bound to its ancestors' plans whatever the risk path lists: a class 0 path
            # has no accepted_plan gate, yet its plan is just as stale (ADR-0007, fail closed; M2 review B1).
            raise GateUnsatisfied(f"{what}: the accepted plan is stale under its ancestors' current plans; "
                                  "`aew plan reconfirm <id> --reason ...` or accept a new plan revision first",
                                  unmet={**unmet, "accepted_plan": G.STALE}, plan_binding=gc["plan_binding"])
        if gc.get("dispatch_binding"):
            # Required upstream output must be in the source the attempt works from (M1); a move that re-parents
            # started work changes its inherited edges, so the attempt no longer qualifies (M2 review B2).
            raise GateUnsatisfied(f"{what}: this attempt was dispatched with other dependencies than the Ticket now "
                                  "has; a new dispatch is required (move it to REPLAN_REQUIRED and accept a plan "
                                  "revision, or `aew work redispatch` a non-mutating Ticket)",
                                  dispatch_binding=gc["dispatch_binding"])
        if unmet:
            raise GateUnsatisfied(f"{what}: gates not satisfied for the current evaluated snapshot",
                                  unmet=unmet, fingerprint=(gc["snapshot"] or {}).get("relevant_inputs_fingerprint"))

    def ingest_ref(self, unit: dict[str, Any], ev: dict[str, Any]) -> None:
        refs = unit.setdefault("evidence", [])
        if not any(r["id"] == ev["id"] for r in refs):
            refs.append(self.evidence_ref(ev))

    @staticmethod
    def evidence_ref(ev: dict[str, Any]) -> dict[str, Any]:
        """The reference an ingest pins on the unit for a sealed report (its id and hash: what the gates count)."""
        return {"id": ev["id"], "kind": ev["kind"], "path": ev["_path"], "sha256": ev["_sha256"],
                "result": ev["result"], "fingerprint": ev["evaluated_snapshot"]["relevant_inputs_fingerprint"],
                "findings": [f["id"] for f in (ev.get("review") or {}).get("findings", [])]}

    PRE_REVIEW = ["accepted_plan", "local_checks", G.ACCEPTANCE_CHECKS, "self_review"]

    def review_gates(self, gc: dict[str, Any]) -> list[str]:
        return [g for g in gc["obligations"]["gates"] if g.startswith(G.REVIEW_GATES_PREFIX)]

    def verification_gates(self, gc: dict[str, Any]) -> list[str]:
        return [g for g in gc["obligations"]["gates"]
                if g in G.VERIFICATION_GATES or g.startswith(G.VERIFY_CARD_PREFIX)]

    @staticmethod
    def _gate_evidence_ids(gc: dict[str, Any], names: list[str]) -> set[str]:
        ids: set[str] = set()
        for name in names:
            info = gc["gates"].get(name) or {}
            if info.get("evidence"):
                ids.add(info["evidence"])
            ids.update(c["evidence"] for c in info.get("checks", {}).values() if c.get("evidence"))
        return ids

    def record_relied_on(self, ctx: TxnContext, unit: dict[str, Any], gc: dict[str, Any], names: list[str]) -> None:
        """Pin (id + sha256) the evidence a transition relied on into control state."""
        wanted = self._gate_evidence_ids(gc, names)
        for ev in gc["evidence"]:
            if ev["id"] in wanted:
                self.ingest_ref(unit, ev)
                ctx.refs.append(ev["_path"])

    def _ingest_implementation(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], gc: dict[str, Any]) -> None:
        self.record_relied_on(ctx, unit, gc, self.PRE_REVIEW)
        # Bounded subagents are retired once their artifact is accepted (WC §5). If work returns to
        # RUNNING, the Lead dispatches a fresh implementer whose pack carries the findings/failure evidence.
        if unit.get("implementer_invocation"):
            self.invocations.complete_invocation(ctx.state, unit["implementer_invocation"])

    def kind_registrations(self) -> list[KindRegistration]:
        return [KindRegistration(GATE_CONTEXT, MUTATING, self._ticket_gate_context)]

    def guard_registrations(self) -> list[GuardRegistration]:
        """The gate-based Lead guards (mutating Tickets' M1 guards; non-mutating Tickets replace them)."""
        return [GuardRegistration("ready_for_review", self._guard_ready_for_review,
                                  query=self._query_ready_for_review),
                GuardRegistration("ready_for_verification_without_review",
                                  self._guard_ready_for_verification_without_review),
                GuardRegistration("commit_ready_without_review_or_verification",
                                  self._guard_commit_ready_without_review_or_verification),
                GuardRegistration("review_current", self._guard_review_current, query=self._query_review_current),
                GuardRegistration("commit_ready_without_verification", self._guard_commit_ready_without_verification),
                GuardRegistration("all_gates_current", self._guard_all_gates_current)]

    def _query_ready_for_review(self, state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """RUNNING -> REVIEW_PENDING (M4-E E4: its query form): a review gate applies, and the pre-review gates are
        current for the workspace's snapshot. It records the gate context it evaluated (``found["gate_context"]``)."""
        def check() -> None:
            gc = self.gate_context(state, work_id)
            if not self.review_gates(gc):
                raise GateUnsatisfied("no review gate applies to this Ticket; advance to verification or commit-ready")
            self.require_gates(gc, self.PRE_REVIEW, what="RUNNING -> REVIEW_PENDING")
            args.setdefault("found", {})["gate_context"] = gc

        return guard_checked(check)

    def _guard_ready_for_review(self, ctx, work_id, unit, to) -> None:
        args: dict[str, Any] = {"to": to}
        require(self._query_ready_for_review(ctx.state, work_id, args))
        self._ingest_implementation(ctx, work_id, unit, args["found"]["gate_context"])

    def _guard_ready_for_verification_without_review(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        if self.review_gates(gc):
            raise GateUnsatisfied("independent review is required before verification", required=self.review_gates(gc))
        if not self.verification_gates(gc):
            raise GateUnsatisfied("no verification gate applies; advance to commit-ready")
        self.require_gates(gc, self.PRE_REVIEW, what="RUNNING -> VERIFY_PENDING")
        self._ingest_implementation(ctx, work_id, unit, gc)

    def _guard_commit_ready_without_review_or_verification(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        if self.review_gates(gc) or self.verification_gates(gc):
            raise GateUnsatisfied("review/verification gates apply to this Ticket",
                                  required=self.review_gates(gc) + self.verification_gates(gc))
        self._commit_ready(ctx, work_id, unit, gc)

    def _query_review_current(self, state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """REVIEW_PASSED -> VERIFY_PENDING (M4-E E4: its query form): the pre-review and review gates are current for
        the workspace's snapshot (the review was of what is there now)."""
        def check() -> None:
            gc = self.gate_context(state, work_id)
            self.require_gates(gc, self.PRE_REVIEW + self.review_gates(gc), what="REVIEW_PASSED -> VERIFY_PENDING")

        return guard_checked(check)

    def _guard_review_current(self, ctx, work_id, unit, to) -> None:
        require(self._query_review_current(ctx.state, work_id, {"to": to}))

    def _guard_commit_ready_without_verification(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        if self.verification_gates(gc):
            raise GateUnsatisfied("verification gates apply to this Ticket", required=self.verification_gates(gc))
        self._commit_ready(ctx, work_id, unit, gc)

    def _guard_all_gates_current(self, ctx, work_id, unit, to) -> None:
        self._commit_ready(ctx, work_id, unit, self.gate_context(ctx.state, work_id))

    def _commit_ready(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], gc: dict[str, Any]) -> None:
        """WC §8: VERIFIED -> COMMIT_READY needs every effective gate current and required findings resolved/waived."""
        self.require_gates(gc, gc["obligations"]["gates"], what="-> COMMIT_READY")
        if gc["open_required_findings"]:
            raise GateUnsatisfied("mandatory review findings are unresolved and not waived",
                                  findings=[f["id"] for f in gc["open_required_findings"]])
        self.record_relied_on(ctx, unit, gc, list(gc["gates"]))
        unit["commit_ready_snapshot"] = gc["snapshot"]
        unit["commit_ready_gates"] = {g: v["status"] for g, v in gc["gates"].items()}
        # Identity of this acceptance: an integration candidate is bound to it (review B1).
        unit["commit_ready_seq"] = unit.get("commit_ready_seq", 0) + 1
        if unit.get("implementer_invocation"):
            self.invocations.complete_invocation(ctx.state, unit["implementer_invocation"])

    @staticmethod
    def integration_binding(unit: dict[str, Any]) -> dict[str, Any]:
        """What an integration candidate is built from: the accepted plan and the COMMIT_READY acceptance."""
        plan = unit.get("plan") or {}
        return {"plan": {"revision": plan.get("accepted"), "sha256": plan.get("sha256")},
                "commit_ready_seq": unit.get("commit_ready_seq", 0),
                "gated_fingerprint": (unit.get("commit_ready_snapshot") or {}).get("relevant_inputs_fingerprint")}

    def binding_problem(self, unit: dict[str, Any]) -> dict[str, Any] | None:
        bound = (unit.get("integration") or {}).get("binding")
        current = self.integration_binding(unit)
        return None if bound == current else {"candidate_bound_to": bound, "current": current}

    def require_current_binding(self, unit: dict[str, Any]) -> None:
        problem = self.binding_problem(unit)
        if problem:
            raise StaleCandidate("the integration candidate was built from an earlier COMMIT_READY or plan; "
                                 "run `aew integrate prepare` again", **problem)

    def find_evidence(self, work_id: str, evidence_id: str) -> dict[str, Any]:
        records, problems = E.scan(self.k.aew_root, work_id)
        if problems:
            raise GateUnsatisfied("evidence integrity problems", problems=problems)
        for ev in records:
            if ev["id"] == evidence_id:
                return ev
        raise NotFound(f"no evidence {evidence_id} for {work_id}")

    def require_bound_report(self, state: dict[str, Any], unit: dict[str, Any], ev: dict[str, Any], *,
                             scope: str) -> None:
        """Accept a report only for the assignment it was produced for (re-review R1).

        Identical engineering content is not enough: the report must have been produced under the
        Ticket's current accepted plan (revision + sha256) by an invocation dispatched for the current
        attempt's workspace (ticket scope) or for the current integration candidate (integration scope).
        Reports from superseded plans, attempts or candidates stay durable history; current work needs
        its own.
        """
        inv = state["invocations"].get(ev["producer"]["invocation"]) or {}
        plan = unit.get("plan") or {}
        accepted = {"revision": plan.get("accepted"), "sha256": plan.get("sha256")}
        problems: dict[str, Any] = {}
        if ev.get("plan_revision") != accepted:
            problems["plan"] = {"report": ev.get("plan_revision"), "accepted": accepted}
        if scope == "integration":
            integ = unit.get("integration") or {}
            if inv.get("scope") != "integration" or inv.get("workspace") != integ.get("workspace") \
                    or inv.get("integration_attempt") != integ.get("attempt"):
                problems["candidate"] = {"report_for": inv.get("workspace_id"), "report_attempt": inv.get(
                    "integration_attempt"), "current": integ.get("workspace_id"),
                    "current_attempt": integ.get("attempt")}
        else:
            ws = unit.get("workspace") or {}
            if (inv.get("scope") or "ticket") != "ticket" or inv.get("workspace") != ws.get("path"):
                problems["workspace"] = {"report_for": inv.get("workspace_id") or inv.get("workspace"),
                                         "current": ws.get("id")}
        if problems:
            raise GateUnsatisfied(
                f"{ev['id']} was produced for a different plan, attempt or candidate than the one being accepted; "
                "it remains in history, but the current work needs its own report", **problems)

    def plan_gate_status(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        unit = state["work"][work_id]
        plan = unit.get("plan") or {}
        if not plan.get("accepted"):
            return {"status": G.MISSING}
        if sha256_file(self.k.aew_root / plan["path"]) != plan["sha256"]:
            return {"status": G.FAILED, "detail": "accepted plan modified outside AEW"}
        problem = self.units.plan_binding_problem(state, work_id)
        if problem:
            return {"status": G.STALE, "detail": problem,
                    "action": f"`aew plan reconfirm {work_id} --reason ...` or a new plan revision"}
        return {"status": G.CURRENT}

    def work_roles(self, work_id: str) -> dict[str, Any]:
        state = self.k.store.read()
        gc = self.gate_context(state, work_id)
        out = self.roles.effective_role_plan(state, work_id, gc)
        out["plan_gates"] = self.roles.plan_gates(self.units.unit(state, work_id))
        return out



class EvidenceCommands:
    """Bounded-role checks and submissions, Lead ingest of reviews and verifications, classification and waivers.
    Dispatch, ingest and classification are routed through the ``KindRegistry``: a mutating Ticket's are handled
    here, a non-mutating Ticket's and a Story or Epic's by their own collaborators."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, roles: RolesPort, invocations: InvocationsPort,
                 inputs: InputsPort, packs: ContextPacksPort, gates: GatesPort, nm: NonMutatingPort,
                 kinds: KindRegistry, archive: ArchivePort, dispatch: DispatchPort, queue: QueuePort) -> None:
        self.k = k
        self.dispatch = dispatch
        self.queue = queue
        self.units = units
        self.roles = roles
        self.invocations = invocations
        self.inputs = inputs
        self.packs = packs
        self.gates = gates
        self.nm = nm
        self.kinds = kinds
        self.archive = archive

    def kind_registrations(self) -> list[KindRegistration]:
        return [KindRegistration(INVOKE, MUTATING, self._invoke_ticket),
                KindRegistration(INGEST, MUTATING, self._ingest_ticket_report),
                KindRegistration(CLASSIFY_VERIFICATION, MUTATING, self._classify_ticket_verification),
                KindRegistration(CLASSIFY_VERIFICATION, NON_MUTATING, self._classify_ticket_verification)]

    def _handler(self, operation: str, work_id: str) -> Any:
        return self.kinds.resolve(operation, self.units.unit(self.k.store.read(), work_id))

    def invoke_evidence_unit(self, *, token: str, expect_rev: int, work_id: str, role: str | None,
                             card: str | None, scope: str, execution_profile: dict[str, Any] | None = None,
                             launch: bool = False) -> dict[str, Any]:
        handler = self.kinds.resolve_evidence_only(INVOKE, self.units.unit(self.k.store.read(), work_id))
        return handler(token=token, expect_rev=expect_rev, work_id=work_id, role=role, card=card, scope=scope,
                       execution_profile=execution_profile, launch=launch)

    def ingest_evidence_unit_report(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str,
                                    kind: str) -> dict[str, Any]:
        handler = self.kinds.resolve_evidence_only(INGEST, self.units.unit(self.k.store.read(), work_id))
        return handler(token=token, expect_rev=expect_rev, work_id=work_id, evidence_id=evidence_id, kind=kind)

    def invoke_create(self, *, token: str, expect_rev: int, work_id: str, role: str | None = None,
                      card: str | None = None, scope: str = "ticket",
                      execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        """Dispatch a bounded invocation, by the handler registered for the unit's kind."""
        return self._handler(INVOKE, work_id)(token=token, expect_rev=expect_rev, work_id=work_id, role=role,
                                              card=card, scope=scope, execution_profile=execution_profile,
                                              launch=launch)

    # ---- the dispatch guards of ``invoke create`` for a mutating Ticket (M4-A), in the order the route checked

    def dispatch_guards(self) -> list[DispatchGuard]:
        return [DispatchGuard("invoke.slot", self._g_slot),
                DispatchGuard("card.slot", self._g_card),
                DispatchGuard("workspace.live", self._g_workspace)]

    def _g_slot(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> Any:
        def check() -> None:
            unit = state["work"][work_id]
            st = unit["state"]
            if facts.get("scope", "ticket") == "integration":
                slot = "verify"
                if not (st == "COMMIT_READY" and (unit.get("integration") or {}).get("status") == "prepared"):
                    raise IllegalTransition("post-integration verification needs a prepared integration candidate")
                self.gates.require_current_binding(unit)
                lease = self.queue.require_live_lease(state, work_id, "post-integration verification")
                facts["custodian"] = lease["custodian"] if lease else None  # None: a v1 project has no queue
            elif st in {"ASSIGNED", "RUNNING"}:
                slot = "execute"
                current = state["invocations"].get(unit.get("implementer_invocation") or "")
                if current and current["status"] == "active":
                    raise IllegalTransition(f"{unit['implementer_invocation']} is still active; cancel it first")
                self.units.require_plan_binding(state, work_id)
                self.units.require_dispatch_binding(state, work_id)
            elif st == "REVIEW_PENDING":
                slot = "review"
            elif st == "VERIFY_PENDING":
                slot = "verify"
            else:
                raise IllegalTransition(f"no role is dispatched for {work_id} in state {st}")
            facts["slot"] = slot
            # A fresh implementer consumes the Ticket's inputs again: stale source-bound ones block (ADR-0008).
            facts["inputs_at"] = (unit.get("workspace") or {}).get("base_commit")
            facts["inputs_skip"] = slot != "execute"
        return checked(check)

    def _g_card(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> Any:
        def check() -> None:
            unit = state["work"][work_id]
            slot = facts["slot"]
            gc = self.gates.gate_context(state, work_id) if slot in {"review", "verify"} \
                and facts.get("scope", "ticket") == "ticket" else None
            if gc is not None and unit.get("mutating"):
                self.gates.require_reported_workspace(work_id, unit, gc)
            chosen = self.roles.resolve_card(state, work_id, slot, card_id=facts.get("card_id"),
                                             role=facts.get("role"), gc=gc)
            facts.update(card=chosen, archetype=chosen.archetype)
        return checked(check)

    @staticmethod
    def _g_workspace(state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> Any:
        unit = state["work"][work_id]
        if facts.get("scope", "ticket") == "integration":
            integ = unit["integration"]
            facts["workspace"], facts["workspace_id"] = integ["workspace"], integ["workspace_id"]
            return None
        ws = unit.get("workspace") or {}
        if ws.get("status") != "active":
            return blocker_from(IllegalTransition(f"{work_id} has no active workspace"))
        facts["workspace"], facts["workspace_id"] = ws["path"], ws["id"]
        return None

    def _invoke_ticket(self, *, token: str, expect_rev: int, work_id: str, role: str | None = None,
                       card: str | None = None, scope: str = "ticket",
                       execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        """Dispatch a bounded invocation for a mutating Ticket. The Role card (explicit, planned, or workflow
        default) determines the archetype; authority comes from the archetype only (ADR-0006). Its legality is the
        ``invoke.create.mutating`` dispatch entrypoint's guards (M4-A)."""
        with self.k.lead_txn(token, expect_rev, "invoke.create") as ctx:
            ctx.execution_request, ctx.launch_request = execution_profile, launch
            state = ctx.state
            unit = self.units.unit(state, work_id)
            decision = self.dispatch.decide_in(ctx, "invoke.create.mutating", work_id, role=role, card_id=card,
                                               scope=scope)
            facts = decision.facts
            chosen, inputs = facts["card"], facts["inputs"]
            workspace, ws_id = facts["workspace"], facts["workspace_id"]
            snapshot = self.invocations.snapshot_of(workspace, ws_id)
            archetype = chosen.archetype
            inv_id, inv_token = self.invocations.new_invocation(ctx, archetype, work_id, scope=scope,
                                                                workspace=workspace,
                                                     workspace_id=ws_id, snapshot=snapshot, card=chosen)
            if archetype == "implementer":
                unit["implementer_invocation"] = inv_id
                state["invocations"][inv_id]["inputs"] = inputs
            if scope == "integration":  # the candidate this invocation serves (re-review M2/R1), under the lease
                state["invocations"][inv_id].update(integration_attempt=unit["integration"]["attempt"],
                                                    candidate=unit["integration"]["candidate"])
                if facts.get("custodian"):
                    state["invocations"][inv_id]["custodian"] = facts["custodian"]
            self.packs.build_pack(ctx, inv_id)
            ctx.summary = f"{inv_id} ({chosen.id} / {archetype}, {scope}) dispatched for {work_id}"
        pack = ctx.state["invocations"][inv_id].get("pack") or {}
        return {"ok": True, "invocation": inv_id, "invocation_token": inv_token, "role": archetype,
                "role_card": chosen.id, "scope": scope, "evaluated_snapshot": snapshot,
                "pack": pack or None, "dispatch": decision.to_dict(), "revision": ctx.session.committed_revision}

    def invoke_cancel(self, *, token: str, expect_rev: int, invocation: str, reason: str) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "invoke.cancel", reason=reason) as ctx:
            inv = ctx.state["invocations"].get(invocation)
            if inv is None:
                raise NotFound(f"no invocation {invocation}")
            if inv["status"] != "active":
                raise IllegalTransition(f"{invocation} is {inv['status']}")
            self.invocations.complete_invocation(ctx.state, invocation, "cancelled")
            ctx.summary = f"{invocation} cancelled"
        return {"ok": True, "revision": ctx.session.committed_revision}

    def invoke_show(self, invocation: str) -> dict[str, Any]:
        state = self.k.store.read()
        inv = state["invocations"].get(invocation) or self.archive.archived_invocation(state, invocation)
        if inv is None:
            raise NotFound(f"no invocation {invocation}")
        return {"id": invocation, **{k: v for k, v in inv.items() if k != "token_id"}}

    def check_run(self, *, invocation_token: str, check_id: str, env: dict[str, str] | None = None,
                  layout: Any = None, trees: Any = None, ending: Any = None) -> dict[str, Any]:
        """Run a project check as a bounded role. ``env`` is the complete environment of the check's process
        (a harness run passes its agent environment, so a check never sees the supervisor's). ``layout`` is a
        contained run's sandbox: the check runs inside it, through the same process-tree choke point (M4-B).
        ``trees`` and ``ending`` come from a run's supervisor: the run ending kills the check, and a check the run's
        end cut short records nothing (independent review, area 2, F6)."""
        with self.k.store.session() as s:
            inv_id, inv, actor = require_invocation(s.state, invocation_token, "check.run",
                                                    archived=self.archive.archived_credential)
            work_id = inv["work_unit"]
            workspace, ws_id, base = self.invocations.invocation_workspace(s.state, inv)
            unit = s.state["work"][work_id]
            allowed_checks = inv.get("allowed_checks")
            if allowed_checks is not None and check_id not in allowed_checks:
                card_id = (inv.get("card") or {}).get("id")
                raise PermissionDenied(f"role card {card_id} does not permit check {check_id}")
            cfg = C.resolve(self.k.policy("checks"), check_id)
            definition = C.definition_digest(cfg,
                                             guardrails=self.k.policy("guardrails") if cfg.get("builtin") else None)
            meta = self.gates.record_meta(unit)
            scope_paths = (meta.get("scope") or {}).get("paths", [])
            acceptance_inputs = (meta.get("acceptance") or {}).get("inputs")
            plan = unit.get("plan") or {}
        if not workspace.exists():
            raise NotFound(f"workspace {workspace} is missing")
        if inv["role"] in SHARED_WORKSPACE_READERS and inv.get("scope") in {"ticket", "integration"}:
            self.gates.require_workspace_intact(inv_id, inv, workspace, ws_id)  # never a check on an edited workspace
        before = self.invocations.snapshot_of(workspace, ws_id)
        if cfg.get("builtin"):
            if base is None:
                raise IllegalTransition(f"{inv_id}'s workspace records no base commit, so guardrails cannot say what "
                                        "changed")
            verdict = GR.evaluate(changed_paths(workspace, base), self.k.policy("guardrails"), scope_paths,
                                  acceptance_inputs)
            run = {"exit_code": 1 if verdict["violations"] else 0, "duration_s": 0.0,
                   "log": json.dumps(verdict, indent=2), "command": ["aew-builtin", "guardrails"]}
        else:
            verdict = None
            run = C.run(cfg, workspace, env=env, layout=layout, trees=trees)
            if ending is not None and ending.is_set():
                raise StaleAuthority(f"the run ended while check {check_id} ran; nothing was recorded")
        after = self.invocations.snapshot_of(workspace, ws_id)
        mutated = before["relevant_inputs_fingerprint"] != after["relevant_inputs_fingerprint"]
        result = "inconclusive" if mutated else ("pass" if run["exit_code"] == 0 else "fail")
        with self.k.store.session() as s:
            # Re-verify: a credential revoked while the check ran must not write evidence.
            inv_id, inv, actor = require_invocation(s.state, invocation_token, "check.run",
                                                    archived=self.archive.archived_credential)
            seq = E.next_seq(self.k.aew_root, work_id)
            eid = f"{inv_id}-check-{check_id}-{seq}"
            log_rel = f"evidence/{work_id}/logs/{eid}.log"
            create_exclusive(self.k.aew_root / log_rel, run["log"])
            meta = {
                "schema": "aew/evidence/v1", "id": eid, "kind": "check_result", "work_unit": work_id,
                "producer": {"role": inv["role"], "invocation": inv_id, "role_card": self.invocations.card_ref(inv),
                             **self.invocations.execution_provenance(inv)},
                "created_at": utc_now(), "seq": seq,
                "plan_revision": {"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None,
                "evaluated_snapshot": before,
                "method": {"capability": "targeted_test_execution" if not cfg.get("builtin") else "guardrail_check",
                           "provider": "aew-check-runner", "command": run["command"],
                           "containment": "os_readonly_roots" if layout is not None else "workdir_separation_only"},
                "claim": f"check {check_id} passes on the evaluated snapshot",
                "result": result,
                "evidence": [{"path": log_rel, "sha256": sha256_file(self.k.aew_root / log_rel)}],
                "check": {"check_id": check_id, "exit_code": run["exit_code"], "duration_s": run["duration_s"],
                          "mutated_inputs": mutated, "definition_sha256": definition,
                          **({"violations": verdict["violations"], "triggered_gates": verdict["triggered_gates"]}
                             if verdict else {})},
            }
            if check_id in self.k.policy("checks").get("baseline_failures", []):
                meta["check"]["baseline_known_failure"] = True
            if inv.get("attempt") is not None:
                meta["attempt"] = inv["attempt"]  # engine-bound: the non-mutating attempt it belongs to
            create_exclusive(self.k.aew_root / f"evidence/{work_id}/{eid}.md", E.seal(meta, ""))
        return {"ok": True, "evidence": eid, "result": result, "exit_code": run["exit_code"],
                "mutated_inputs": mutated, "evaluated_snapshot": before, "log": log_rel}

    def submit(self, *, invocation_token: str, kind: str, text: str) -> dict[str, Any]:
        submitted, body = parse_frontmatter(text, source="submission")
        with self.k.store.session() as s:
            state = s.state
            inv_id, inv, actor = require_invocation(state, invocation_token, f"submit.{kind}",
                                                    archived=self.archive.archived_credential)
            E.check_submission(inv["role"], kind, submitted)
            # Any report — implementation, review or verification — is written only while the invocation's
            # own workspace/candidate is still live (review M2, re-review M2).
            workspace, ws_id, _ = self.invocations.invocation_workspace(state, inv)
            if inv.get("scope") in {"observation", "parent"}:
                self.nm.require_observation_intact(inv_id, inv)  # read-only roles: records, reviews, verifications
            elif inv["role"] in SHARED_WORKSPACE_READERS:
                self.gates.require_workspace_intact(inv_id, inv, workspace, ws_id)  # M3-B6
            work_id = inv["work_unit"]
            unit = state["work"][work_id]
            plan = unit.get("plan") or {}
            meta: dict[str, Any] = {
                "schema": "aew/evidence/v1", "kind": kind, "work_unit": work_id,
                "producer": {"role": inv["role"], "invocation": inv_id, "role_card": self.invocations.card_ref(inv),
                             **(submitted.get("producer") or {}), **self.invocations.execution_provenance(inv)},
                "created_at": utc_now(),
                "plan_revision": {"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None,
                "method": submitted.get("method") or {"capability": kind, "provider": "harness-role"},
                "claim": submitted.get("claim") or kind.replace("_", " "),
                "evidence": submitted.get("evidence") or [],
            }
            if kind == "implementation_report":
                meta["evaluated_snapshot"] = self.invocations.snapshot_of(workspace, ws_id)
                meta["implementation"] = submitted.get("implementation") or {}
                meta["result"] = submitted.get("result", "pass")
                if meta["result"] not in {"pass", "blocked"}:
                    raise ValidationFailed("an implementation report result is pass (complete) or blocked")
            elif kind == "review":
                review = submitted.get("review") or {}
                validate_property("evidence", "review", {**review, "findings": [
                    {"required": False, **f} if isinstance(f, dict) else f for f in review.get("findings") or []]}
                    if isinstance(review, dict) else review, source="submission")  # its shape, before it is read
                review = dict(review)
                if review.get("independence") == "R0":
                    raise ValidationFailed("R0 self-review is not independent review (WC §10.2)")
                review.setdefault("specialty", inv.get("specialty"))
                if (review.get("specialty") or None) != (inv.get("specialty") or None):
                    raise ValidationFailed("review specialty must match the dispatched specialty")
                for f in review.get("findings", []):
                    if f.get("severity") in {"blocker", "major"}:
                        f["required"] = True
                if review.get("disposition") == "pass" and any(f.get("required") for f in review.get("findings", [])):
                    raise ValidationFailed("disposition pass is inconsistent with required findings")
                # Checked here, while the reviewer can still correct it, not only at the Lead's ingest (M3 step 8).
                known = {f["id"]: f for f in unit.get("findings") or []}
                unknown = [r for r in review.get("resolved_findings") or [] if r not in known]
                if unknown:
                    listed = sorted(i for i, f in known.items() if f.get("status") == "open")
                    raise ValidationFailed(
                        f"review resolves unknown finding(s) {', '.join(map(str, unknown))}: name each exactly as the "
                        f"pack lists it; the open findings are {', '.join(listed) or 'none'}",
                        unknown=unknown, open_findings=listed)
                meta["review"] = review
                meta["evaluated_snapshot"] = inv["snapshot"]
                meta["result"] = "pass" if review.get("disposition") == "pass" else "fail"
            elif kind == "verification":
                meta.update(self._verification_binding(state, inv_id, inv, submitted))
            elif kind in E.EXECUTE_KINDS:
                meta.update(self.nm.execute_record_binding(state, inv_id, inv, kind, submitted))
            else:
                raise UsageError(f"unknown evidence kind {kind}")
            if kind in {"review", "verification"} and inv.get("scope") == "observation":
                meta["subject"] = inv.get("subject")  # the execute record this report evaluated (ADR-0008)
            seq = E.next_seq(self.k.aew_root, work_id)
            meta["id"] = f"{inv_id}-{E.SHORT[kind]}-{seq}"
            meta["seq"] = seq
            ordered = {k: meta[k] for k in ("schema", "id", "kind", "work_unit", "producer", "created_at", "seq",
                                             "plan_revision", "evaluated_snapshot", "method", "claim", "result",
                                             "evidence") if k in meta}
            ordered.update({k: v for k, v in meta.items() if k not in ordered})
            path = self.k.aew_root / f"evidence/{work_id}/{meta['id']}.md"
            create_exclusive(path, E.seal(ordered, body))
        return {"ok": True, "evidence": meta["id"], "result": meta["result"],
                "evaluated_snapshot": meta["evaluated_snapshot"], "path": str(path)}

    def _verification_binding(self, state: dict[str, Any], inv_id: str, inv: dict[str, Any],
                              submitted: dict[str, Any]) -> dict[str, Any]:
        v = submitted.get("verification") or {}
        dispatched = {"integration": "integration", "parent": "parent"}.get(inv.get("scope") or "ticket", "ticket")
        if isinstance(v, dict):
            v = {"scope": dispatched, **v}
        validate_property("evidence", "verification", v, source="submission")  # its shape, before it is read
        if v["scope"] != dispatched:
            raise ValidationFailed("verification scope must match the dispatched scope")
        claims = v.get("claims") or []
        types = {c.get("type") for c in claims}
        if v["scope"] in {"ticket", "parent"} and not {"goal_backwards", "contract"} <= types:
            raise ValidationFailed(f"{v['scope']} verification needs both goal_backwards and contract claims "
                                   "(WC §11.4)")
        if not claims:
            raise ValidationFailed("verification needs at least one claim")
        work_id = inv["work_unit"]
        records = {e["id"]: e for e in E.scan(self.k.aew_root, work_id)[0]}
        expected_fp = ((inv.get("observation") or {}).get("fingerprint")
                       or inv["snapshot"]["relevant_inputs_fingerprint"])
        definitions = C.current_definitions(self.k.policy("checks"), self.k.policy("guardrails"))
        for c in claims:
            for cid in c.get("checks", []):
                ev = records.get(cid)
                if ev is None or ev["kind"] != "check_result" or ev["producer"]["invocation"] != inv_id:
                    raise ValidationFailed(f"claim cites {cid}, which is not a check run by this verifier invocation")
                if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != expected_fp:
                    raise ValidationFailed(
                        f"{cid} evaluated a different snapshot than this verification package; re-run the check")
                if not C.proves_current_definition(ev, definitions):
                    raise ValidationFailed(f"{cid} ran check {ev['check']['check_id']} as it was defined before "
                                           "policy/checks.yaml changed; re-run the check (independent audit I1)")
        results = [c["result"] for c in claims]
        if "fail" in results:
            overall = "fail"
        elif "blocked" in results:
            overall = "blocked"
        elif all(r == "pass" for r in results):
            overall = "pass"
        else:
            overall = "inconclusive"
        return {"verification": v, "evaluated_snapshot": inv["snapshot"], "result": overall}

    def review_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._handler(INGEST, work_id)(token=token, expect_rev=expect_rev, work_id=work_id,
                                              evidence_id=evidence_id, kind="review")

    def verify_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._handler(INGEST, work_id)(token=token, expect_rev=expect_rev, work_id=work_id,
                                              evidence_id=evidence_id, kind="verification")

    def _ingest_ticket_report(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str,
                              kind: str) -> dict[str, Any]:
        """A mutating Ticket's review or verification report."""
        ingest = self._ingest_ticket_review if kind == "review" else self._ingest_ticket_verification
        return ingest(token=token, expect_rev=expect_rev, work_id=work_id, evidence_id=evidence_id)

    # ---- `review.ingest`'s guard as a query (M4-E E4; aew.engine.guards)

    def review_ingest_query(self, state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """``review.ingest`` of report ``args["evidence"]``: the guard of the ingest the ``KindRegistry`` selects for
        the unit, where it has a query form (a mutating Ticket's); another kind's is ``NotQueryable``."""
        found = guard_checked(lambda: self.units.unit(state, work_id))
        if found is not None:
            return found
        if self.kinds.resolve(INGEST, state["work"][work_id]) != self._ingest_ticket_report:
            return NotQueryable("review.ingest")
        return self._query_ticket_review(state, work_id, args)

    def _query_ticket_review(self, state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """Accepting a review report for a mutating Ticket: it is REVIEW_PENDING; the report is a sealed review of it by
        a reviewer independent of the implementer, of the workspace's current snapshot, bound to the current plan and
        attempt; every finding it resolves is known. It records the report, the reference the ingest pins, and the
        state the report's outcome implies (REVIEW_FAILED, else REVIEW_PASSED; a review still pending elsewhere is the
        next step's guard's to see)."""
        evidence_id = str(args.get("evidence"))

        def check() -> None:
            unit = state["work"][work_id]
            if unit["state"] != "REVIEW_PENDING":
                raise IllegalTransition(f"{work_id} is {unit['state']}, not REVIEW_PENDING. "
                                        f"{transitions.next_steps(unit['state'], work_id)}".rstrip())
            ev = self.gates.find_evidence(work_id, evidence_id)
            inv = state["invocations"][ev["producer"]["invocation"]]
            if ev["kind"] != "review" or inv["role"] not in REVIEW_ROLES or inv["work_unit"] != work_id:
                raise IllegalTransition(f"{evidence_id} is not a review of {work_id}")
            if ev["producer"]["invocation"] == unit.get("implementer_invocation"):
                raise GateUnsatisfied("a review must come from an invocation independent of the implementer")
            gc = self.gates.gate_context(state, work_id)
            current = (gc["snapshot"] or {}).get("relevant_inputs_fingerprint")
            if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != current:
                raise GateUnsatisfied("review evaluated a snapshot that is no longer current (stale)",
                                      reviewed=ev["evaluated_snapshot"]["relevant_inputs_fingerprint"], current=current)
            self.gates.require_bound_report(state, unit, ev, scope="ticket")
            findings = unit.get("findings") or []
            resolved = list(ev["review"].get("resolved_findings", []))
            for rid in resolved:
                if not any(f["id"] == rid for f in findings):
                    raise ValidationFailed(f"review resolves unknown finding {rid}")
            still_open = [f for f in G.open_required_findings(unit) if f["id"] not in resolved]
            failed = (ev["review"]["disposition"] != "pass" or bool(still_open)
                      or any(f["required"] for f in ev["review"]["findings"]))
            args.setdefault("found", {}).update(evidence=ev, ref=self.gates.evidence_ref(ev),
                                                to="REVIEW_FAILED" if failed else "REVIEW_PASSED")

        return guard_checked(check)

    def _ingest_ticket_review(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "review.ingest") as ctx:
            ctx.events.append({"kind": "evidence.ingested", "work": work_id, "evidence_kind": "review",
                               "ids": [evidence_id]})
            state = ctx.state
            args: dict[str, Any] = {"evidence": evidence_id}
            require(self.review_ingest_query(state, work_id, args))  # the guard, as `explain` and a stage ask it
            unit = state["work"][work_id]
            ev = args["found"]["evidence"]
            findings = unit.setdefault("findings", [])
            known = {f["id"] for f in findings}
            for rid in ev["review"].get("resolved_findings", []):
                target = next(f for f in findings if f["id"] == rid)  # known: the query checked every one
                target.update(status="resolved", resolved_by=evidence_id)
            for f in ev["review"]["findings"]:
                fid = f"{evidence_id}#{f['id']}"
                if fid not in known:
                    findings.append({"id": fid, "severity": f["severity"], "summary": f["summary"],
                                     "location": f.get("location"), "required": f["required"],
                                     "status": "open" if f["required"] else "noted", "source": evidence_id})
            self.gates.ingest_ref(unit, ev)
            self.invocations.complete_invocation(state, ev["producer"]["invocation"])
            open_required = G.open_required_findings(unit)
            gc = self.gates.gate_context(state, work_id)
            pending = G.unmet(gc["gates"], self.gates.review_gates(gc))
            if ev["review"]["disposition"] != "pass" or open_required:
                to = "REVIEW_FAILED"
            elif pending:
                to = None  # other required reviews (triggered/inherited) still outstanding
            else:
                to = "REVIEW_PASSED"
            change = None
            if to:
                transitions.check(unit["state"], to, "review.ingest")
                change = self.units.set_state(unit, to, f"review {evidence_id}: {ev['review']['disposition']}",
                                         state=state)
            ctx.refs.append(ev["_path"])
            ctx.summary = f"{work_id} review {evidence_id} ingested" + (f" -> {to}" if to else " (reviews pending)")
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "transition": change, "pending_reviews": pending,
                "open_required_findings": [f["id"] for f in open_required],
                "revision": ctx.session.committed_revision}

    def _ingest_ticket_verification(self, *, token: str, expect_rev: int, work_id: str,
                                    evidence_id: str) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "verify.ingest") as ctx:
            ctx.events.append({"kind": "evidence.ingested", "work": work_id, "evidence_kind": "verification",
                               "ids": [evidence_id]})
            state = ctx.state
            unit = self.units.unit(state, work_id)
            ev = self.gates.find_evidence(work_id, evidence_id)
            inv = state["invocations"][ev["producer"]["invocation"]]
            if ev["kind"] != "verification" or inv["role"] != "verifier" or inv["work_unit"] != work_id:
                raise IllegalTransition(f"{evidence_id} is not a verification of {work_id}")
            scope = ev["verification"]["scope"]
            if scope == "ticket":
                if unit["state"] != "VERIFY_PENDING":
                    raise IllegalTransition(f"{work_id} is {unit['state']}, not VERIFY_PENDING. "
                                            f"{transitions.next_steps(unit['state'], work_id)}".rstrip())
                current = (self.invocations.current_snapshot(unit) or {}).get("relevant_inputs_fingerprint")
            else:
                integ = unit.get("integration") or {}
                if unit["state"] != "COMMIT_READY" or integ.get("status") != "prepared":
                    raise IllegalTransition(f"{work_id} has no prepared integration candidate")
                self.gates.require_current_binding(unit)
                self.queue.require_live_lease(state, work_id, "ingesting post-integration verification")
                current = self.invocations.snapshot_of(integ["workspace"],
                                                       integ["workspace_id"])["relevant_inputs_fingerprint"]
            if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != current:
                raise GateUnsatisfied("verification evaluated a snapshot that is no longer current (stale)",
                                      verified=ev["evaluated_snapshot"]["relevant_inputs_fingerprint"], current=current)
            self.gates.require_bound_report(state, unit, ev, scope=scope)
            self.gates.ingest_ref(unit, ev)
            self.invocations.complete_invocation(state, ev["producer"]["invocation"])
            result = ev["result"]
            unit["last_verification"] = {"evidence": evidence_id, "result": result, "scope": scope}
            change = None
            pending: dict[str, str] = {}
            if scope == "ticket":
                # The Verifier's result determines the state mechanically (ambiguity report B1, B2).
                to = {"pass": "VERIFIED", "fail": "VERIFICATION_FAILED"}.get(result, "VERIFICATION_INCONCLUSIVE")
                if to == "VERIFIED":
                    gc = self.gates.gate_context(state, work_id)
                    pending = G.unmet(gc["gates"], self.gates.verification_gates(gc))
                    if pending:
                        to = None  # other planned verifier cards are still outstanding
                if to:
                    transitions.check(unit["state"], to, "verify.ingest")
                    change = self.units.set_state(unit, to, f"verification {evidence_id}: {result}", state=state)
            elif result == "pass":
                unit["integration"]["status"] = "validated"
                unit["integration"]["post_integration_evidence"] = evidence_id
            elif result == "fail":
                unit["integration"]["status"] = "validation_failed"
                transitions.check(unit["state"], "VERIFICATION_FAILED", "verify.ingest")
                change = self.units.set_state(unit, "VERIFICATION_FAILED",
                                         f"post-integration verification {evidence_id} failed", state=state)
            else:
                unit["integration"]["status"] = "validation_inconclusive"
                # M4-D4: an inconclusive integration validation must not hold the one lease while the Lead decides:
                # the entry waits for disposition, so independent entries behind it integrate (no head-of-line
                # blocking). A failed one moves the Ticket to VERIFICATION_FAILED, which retires the entry.
                self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="validation_inconclusive",
                                   detail={"evidence": evidence_id})
            ctx.refs.append(ev["_path"])
            ctx.summary = f"{work_id} verification {evidence_id} ({scope}) ingested: {result}"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "scope": scope, "result": result, "transition": change,
                "pending_verifications": pending, "revision": ctx.session.committed_revision}

    def verify_classify(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                        reason: str) -> dict[str, Any]:
        if classification not in transitions.VERIFICATION_CLASSIFICATIONS:
            raise UsageError(f"classification must be one of {sorted(transitions.VERIFICATION_CLASSIFICATIONS)}")
        if not (reason and reason.strip()):
            raise UsageError("a classification needs a reason")
        return self._handler(CLASSIFY_VERIFICATION, work_id)(token=token, expect_rev=expect_rev, work_id=work_id,
                                                             classification=classification, reason=reason)

    def _classify_ticket_verification(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                                      reason: str) -> dict[str, Any]:
        """A Ticket's failed verification, classified (WC §6); a parent's is the hierarchy's."""
        with self.k.lead_txn(token, expect_rev, "verify.classify", reason=reason) as ctx:
            unit = self.units.unit(ctx.state, work_id)
            if unit["state"] != "VERIFICATION_FAILED":
                raise IllegalTransition(f"{work_id} is {unit['state']}; only VERIFICATION_FAILED is classified")
            to = transitions.VERIFICATION_CLASSIFICATIONS[classification]
            transitions.check("VERIFICATION_FAILED", to, "verify.classify")
            failing = (unit.get("last_verification") or {}).get("evidence")
            change = {"from": "VERIFICATION_FAILED", "to": to}
            decision = self.k.new_decision(
                ctx, "verification_failure_classification",
                f"{work_id} verification failure classified {classification}", work_unit=work_id,
                classification=classification, evidence_refs=[failing] if failing else [],
                resulting_transition=change, reason=reason)
            unit.setdefault("classifications", []).append(
                {"decision": decision, "classification": classification, "evidence": failing})
            if to == "RUNNING":
                unit["failure_evidence"] = failing
                if (unit.get("integration") or {}).get("status") == "validation_failed":
                    unit["integration"]["status"] = "discarded"
            elif to == "VERIFICATION_INCONCLUSIVE":
                unit["environment_blocker"] = {"decision": decision, "reason": reason}
            self.units.set_state(unit, to, f"{classification}: {reason}", state=ctx.state)
            ctx.summary = f"{work_id} classified {classification} -> {to} ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "classification": classification, "to": to, "decision": decision,
                "revision": ctx.session.committed_revision}

    def waive(self, *, token: str, expect_rev: int, work_id: str, reason: str, gate: str | None = None,
              finding: str | None = None) -> dict[str, Any]:
        if bool(gate) == bool(finding):
            raise UsageError("waive exactly one gate or one finding")
        with self.k.lead_txn(token, expect_rev, "waive", reason=reason) as ctx:
            unit = self.units.unit(ctx.state, work_id)
            policy = self.k.policy("gates")
            if gate:
                gc = self.gates.gate_context(ctx.state, work_id)
                if gate in gc["obligations"]["non_waivable"]:
                    raise GateUnsatisfied(f"{gate} is inherited as non-waivable")
                if gate not in policy.get("waivable_gates", []):
                    raise GateUnsatisfied(f"project policy does not allow waiving {gate}")
            else:
                target = next((f for f in unit.get("findings", []) if f["id"] == finding), None)
                if target is None:
                    raise NotFound(f"no finding {finding}")
                if target["severity"] not in policy.get("waivable_finding_severities", []):
                    raise GateUnsatisfied(f"project policy does not allow waiving {target['severity']} findings")
            decision = self.k.new_decision(ctx, "waiver", f"waived {gate or finding} on {work_id}", work_unit=work_id,
                                         reason=reason)
            unit.setdefault("waivers", []).append({"gate": gate, "finding": finding, "decision": decision})
            ctx.summary = f"{work_id}: waived {gate or finding}"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}
