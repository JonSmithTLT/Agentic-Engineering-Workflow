"""Story/Epic lifecycle: parent gates and closeout, cascade cancellation, moves, promotion, dependency edits.

ADR-0007. Parent state is derived from child work (``hierarchy.recompute_parents`` inside every Lead
commit); the only parent facts the Lead records are its accepted plan, its gate evidence, a closeout
decision and a cancellation decision. Children completing never proves parent acceptance: closeout
requires the parent's own gates (its class path from ``parent_paths`` plus inherited non-waivable ancestor
gates) CURRENT against the **parent snapshot** — the authoritative source plus the digest of the children's
identities, states and completion records — so a new child, a moved-in child or any integration makes
earlier parent review/verification stale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aew.engine import gates as G
from aew.engine import hierarchy as H
from aew.engine import transitions
from aew.engine.dependencies import UNSTARTED, dependency_blockers, effective_edge_set
from aew.engine.nonmutating_ops import NO_GUARDRAILS, is_nm_ticket
from aew.engine.seams import CLASSIFY_VERIFICATION, GATE_CONTEXT, INGEST, INVOKE, PARENT, KindRegistration
from aew.errors import DependencyUnsatisfied, GateUnsatisfied, IllegalTransition, NotFound, UsageError
from aew.knowledge import evidence as E
from aew.knowledge.records import KIND_PREFIX, format_id
from aew.util import render_frontmatter, sha256_text, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import (
        ArchivePort,
        GatesPort,
        HistoryCommandsPort,
        InputsPort,
        InvocationsPort,
        NonMutatingPort,
        RolesPort,
        WorkUnitsPort,
    )

PROMOTION = {"ticket": {"story", "epic"}, "story": {"epic"}}


class Hierarchy:
    """Story/Epic lifecycle: parent gates and closeout, cancellation, moves, promotion, dependency edits."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, roles: RolesPort, invocations: InvocationsPort,
                 inputs: InputsPort, gates: GatesPort, nm: NonMutatingPort, archive: ArchivePort,
                 history: HistoryCommandsPort) -> None:
        self.k = k
        self.units = units
        self.roles = roles
        self.invocations = invocations
        self.inputs = inputs
        self.gates = gates
        self.nm = nm
        self.archive = archive
        self.history = history

    def _completion_of(self, state: dict[str, Any], work_id: str) -> str | None:
        """A unit's completion-record hash, hot or archived (what an edge or a closeout record pins)."""
        if work_id in state["work"]:
            return self.units.completion_sha(state, work_id)
        return (H.upstream(state, work_id) or self.units.view(state, work_id)).get("completion_sha256")

    def children_digest(self, state: dict[str, Any], work_id: str) -> str:
        return H.children_digest(state, work_id, {c: self.units.completion_sha(state, c)
                                                  for c in H.children(state, work_id)})

    def _parent_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        unit = self.units.unit(state, work_id)
        gates_policy = self.k.policy("gates")
        obligations = G.effective_obligations(state, work_id, {**gates_policy, "risk_paths": G.path_table(
            gates_policy, unit)}, None, self.roles.plan_gates(unit))
        evidence, problems = E.scan(self.k.aew_root, work_id)
        commit = self.k.authoritative_commit()
        digest = self.children_digest(state, work_id)
        kids = H.children(state, work_id)
        archived = H.archived_summary(unit)  # finished children already archived (R3): all terminal, counted
        complete = (bool(kids) or bool(archived["done"] + archived["cancelled"])) \
            and all(state["work"][k]["state"] in H.TERMINAL for k in kids) \
            and (any(state["work"][k]["state"] == "DONE" for k in kids) or archived["done"] > 0)
        children = {"status": G.CURRENT if complete else G.MISSING,
                    "children": {k: state["work"][k]["state"] for k in kids}}
        if archived["done"] or archived["cancelled"]:
            children["archived"] = {"done": archived["done"], "cancelled": archived["cancelled"]}
        special = {"accepted_plan": self.gates.plan_gate_status(state, work_id), "children_complete": children}

        edges = effective_edge_set(state, work_id)

        def is_current(e: dict[str, Any]) -> bool:
            snap = e["evaluated_snapshot"]
            dispatched_with = (state["invocations"].get(e["producer"]["invocation"]) or {}).get("dependencies")
            return snap["relevant_inputs_fingerprint"].endswith(f"+children:{digest}") \
                and self.inputs.same_source(snap.get("base_revision"), commit) and dispatched_with == edges

        results = G.evaluate_evidence_unit(state, work_id, evidence, obligations=obligations, special=special,
                                           is_current=is_current)
        return {"snapshot": {"base_revision": commit, "children_digest": digest,
                             "relevant_inputs_fingerprint": f"authoritative:{(commit or '')[:12]}+children:{digest}"},
                "guardrails": dict(NO_GUARDRAILS), "obligations": obligations, "gates": results, "evidence": evidence,
                "evidence_problems": problems, "open_required_findings": G.open_required_findings(unit),
                "plan_binding": self.units.plan_binding_problem(state, work_id)}

    def kind_registrations(self) -> list[KindRegistration]:
        return [KindRegistration(GATE_CONTEXT, PARENT, self.evidence_gate_context),
                KindRegistration(INVOKE, PARENT, self.invoke_evidence_unit),
                KindRegistration(INGEST, PARENT, self.ingest_evidence_unit_report),
                KindRegistration(CLASSIFY_VERIFICATION, PARENT, self.classify_parent_verification)]

    def evidence_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """The gate context of a Story or Epic (its ``KindRegistry`` handler)."""
        return self._parent_gate_context(state, work_id)

    def invoke_evidence_unit(self, *, token: str, expect_rev: int, work_id: str, role: str | None,
                             card: str | None, scope: str, execution_profile: dict[str, Any] | None = None,
                             launch: bool = False) -> dict[str, Any]:
        """Review/verify invocations for a Story or Epic's acceptance, bound to the parent snapshot."""
        with self.k.lead_txn(token, expect_rev, "invoke.create") as ctx:
            ctx.execution_request, ctx.launch_request = execution_profile, launch
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["state"] != "ACCEPTANCE_PENDING":
                raise IllegalTransition(f"{work_id} is {unit['state']}; parent review and verification run once every "
                                        "child is DONE or CANCELLED (ACCEPTANCE_PENDING)")
            if card:
                archetype = self.roles.role_catalog().get(card).archetype
            elif role:
                archetype = role
            else:
                raise UsageError("name the gate to dispatch: --role reviewer|verifier or --card")
            slot = {"reviewer": "review", "verifier": "verify"}.get(archetype)
            if slot is None:
                raise UsageError("a Story/Epic has only review and verification gates; its Tickets do the work")
            if slot == "verify" and (unit.get("parent_verification") or {}).get("awaiting_classification"):
                raise IllegalTransition(f"{work_id}'s last parent verification failed; classify it first "
                                        f"(`aew verify classify {work_id}`)")
            gc = self._parent_gate_context(state, work_id)
            chosen = self.roles.resolve_card(state, work_id, slot, card_id=card, role=role, gc=gc)
            commit = self.k.authoritative_commit()
            # Parent acceptance is a downstream assignment (WC §8: a dependency is satisfied only when the upstream
            # output is in the downstream assignment's recorded input/source snapshot; operator decision after the
            # M2 re-review). Its reviewer and verifier start only once the parent's own and inherited dependencies
            # are satisfied, and they consume the prerequisite records under the ADR-0008 input rule.
            blockers = dependency_blockers(state, unit, repo_root=self.k.repo_root, base_commit=commit, work_id=work_id)
            if blockers:
                raise DependencyUnsatisfied(f"{work_id}'s acceptance review and verification wait for its "
                                            "dependencies", blockers=blockers)
            inputs = self.inputs.dispatch_inputs(state, work_id, commit)
            inv_id, inv_token, snapshot = self.nm.dispatch_observer(
                ctx, work_id, card=chosen, scope="parent", commit=commit, inputs=inputs,
                children_digest=gc["snapshot"]["children_digest"])
            # Its report is bound to the dependencies it was dispatched under: a later edge change (a move, an
            # edit) makes it STALE, like a change of the child set.
            state["invocations"][inv_id]["dependencies"] = effective_edge_set(state, work_id)
            ctx.summary = f"{inv_id} ({chosen.id}) dispatched for {work_id} acceptance"
        inv = ctx.state["invocations"][inv_id]
        return {"ok": True, "invocation": inv_id, "invocation_token": inv_token, "role": chosen.archetype,
                "role_card": chosen.id, "scope": "parent", "evaluated_snapshot": snapshot,
                "observation": inv["observation"], "pack": inv.get("pack"), "revision": ctx.session.committed_revision}

    def ingest_evidence_unit_report(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str,
                                    kind: str) -> dict[str, Any]:
        """Lead ingests a review/verification of a Story or Epic's acceptance."""
        op = "review.ingest" if kind == "review" else "verify.ingest"
        with self.k.lead_txn(token, expect_rev, op) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["state"] != "ACCEPTANCE_PENDING":
                raise IllegalTransition(f"{work_id} is {unit['state']}, not ACCEPTANCE_PENDING")
            ev = self.inputs.find_unit_evidence(work_id, evidence_id)
            inv = state["invocations"][ev["producer"]["invocation"]]
            role = "reviewer" if kind == "review" else "verifier"
            if ev["kind"] != kind or inv["role"] != role or inv["work_unit"] != work_id or inv.get("scope") != "parent":
                raise IllegalTransition(f"{evidence_id} is not a parent {kind} of {work_id}")
            gc = self._parent_gate_context(state, work_id)
            snap = ev["evaluated_snapshot"]
            if not (snap["relevant_inputs_fingerprint"].endswith(f"+children:{gc['snapshot']['children_digest']}")
                    and self.inputs.same_source(snap.get("base_revision"), gc["snapshot"]["base_revision"])):
                raise GateUnsatisfied(f"{evidence_id} evaluated another source or child set than {work_id}'s current "
                                      "parent snapshot (stale)", evaluated=snap, current=gc["snapshot"])
            edges = effective_edge_set(state, work_id)
            if inv.get("dependencies") != edges:
                raise GateUnsatisfied(f"{evidence_id} was dispatched under other dependencies than {work_id}'s current "
                                      "ones (stale)", dispatched_with=inv.get("dependencies"), current=edges)
            plan = unit.get("plan") or {}
            if ev.get("plan_revision") != ({"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None):
                raise GateUnsatisfied(f"{evidence_id} was produced under another plan than the accepted one")
            self.nm.require_observation_intact(ev["producer"]["invocation"], inv)
            if kind == "review":
                self.nm.record_review_findings(unit, ev, evidence_id)
            else:
                unit["last_verification"] = {"evidence": evidence_id, "result": ev["result"], "scope": "parent"}
                if ev["result"] == "fail":
                    unit["parent_verification"] = {"awaiting_classification": evidence_id,
                                                   "children_digest": gc["snapshot"]["children_digest"],
                                                   "plan_revision": plan.get("accepted")}
            self.gates.ingest_ref(unit, ev)
            self.invocations.complete_invocation(state, ev["producer"]["invocation"])
            ctx.refs.append(ev["_path"])
            ctx.summary = f"{work_id} parent {kind} {evidence_id} ingested ({ev['result']})"
            self.units.before_commit(ctx)
        self.nm.prune_observations()
        return {"ok": True, "work_id": work_id, "result": ev["result"], "revision": ctx.session.committed_revision}

    def classify_parent_verification(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                                     reason: str) -> dict[str, Any]:
        """The Lead classifies a failed parent verification (WC §6); it prescribes what closeout then requires."""
        with self.k.lead_txn(token, expect_rev, "verify.classify", reason=reason) as ctx:
            unit = self.units.unit(ctx.state, work_id)
            pv = unit.get("parent_verification") or {}
            if not pv.get("awaiting_classification"):
                raise IllegalTransition(f"{work_id} has no failed parent verification awaiting classification")
            requires = {"LOCAL_IMPLEMENTATION_DEFECT": "a remediation child (the child set must change)",
                        "PLAN_OR_DESIGN_DEFECT": "a new accepted parent plan revision",
                        "CONTRACT_VIOLATION": "a new accepted parent plan revision",
                        "ENVIRONMENT_OR_EVIDENCE_BLOCKED": "re-verification once the environment is fixed"}[classification]
            decision = self.k.new_decision(ctx, "verification_failure_classification",
                                         f"{work_id} parent verification failure classified {classification}",
                                         work_unit=work_id, classification=classification,
                                         evidence_refs=[pv["awaiting_classification"]], reason=reason,
                                         body=f"Closeout now requires {requires}.\n")
            unit["parent_verification"] = {**pv, "awaiting_classification": None, "failed_evidence":
                                           pv["awaiting_classification"], "classification": classification,
                                           "decision": decision, "requires": requires}
            unit.setdefault("classifications", []).append({"decision": decision, "classification": classification,
                                                           "evidence": pv["awaiting_classification"]})
            ctx.summary = f"{work_id} parent verification classified {classification} ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "classification": classification, "decision": decision,
                "requires": requires, "revision": ctx.session.committed_revision}

    def _classification_unmet(self, state: dict[str, Any], unit: dict[str, Any], digest: str) -> str | None:
        pv = unit.get("parent_verification") or {}
        if pv.get("awaiting_classification"):
            return "a failed parent verification awaits the Lead's classification"
        cls = pv.get("classification")
        if cls == "LOCAL_IMPLEMENTATION_DEFECT" and digest == pv.get("children_digest"):
            return "classified LOCAL_IMPLEMENTATION_DEFECT: a remediation child must change the child set first"
        if cls in {"PLAN_OR_DESIGN_DEFECT", "CONTRACT_VIOLATION"} \
                and (unit.get("plan") or {}).get("accepted") == pv.get("plan_revision"):
            return f"classified {cls}: a new parent plan revision must be accepted first"
        return None

    def _end_parent_invocations(self, state: dict[str, Any], unit: dict[str, Any], status: str) -> None:
        """A closed or cancelled parent keeps no live credentials (as M1 does for terminal Tickets)."""
        for inv_id in unit.get("invocations", []):
            self.invocations.complete_invocation(state, inv_id, status)

    def work_close(self, *, token: str, expect_rev: int, work_id: str, reason: str | None = None) -> dict[str, Any]:
        """Lead closeout of a Story/Epic: every child terminal, parent gates CURRENT, findings resolved."""
        with self.k.lead_txn(token, expect_rev, "work.close", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if not H.is_parent(unit):
                raise IllegalTransition("Tickets complete by integration (mutating) or acceptance (non-mutating)")
            if unit["state"] != "ACCEPTANCE_PENDING":
                raise IllegalTransition(f"{work_id} is {unit['state']}; closeout needs every child DONE or CANCELLED")
            # A parent's own and inherited edges bind its acceptance too (M2 review major 1): a DONE child moved in
            # (or finished) does not close it before what it depends on is satisfied.
            blockers = dependency_blockers(state, unit, repo_root=self.k.repo_root,
                                           base_commit=self.k.authoritative_commit(), work_id=work_id)
            if blockers:
                raise DependencyUnsatisfied(f"{work_id} cannot close while its dependencies are unsatisfied",
                                            blockers=blockers)
            gc = self._parent_gate_context(state, work_id)
            self.gates.require_gates(gc, gc["obligations"]["gates"], what="closeout")
            if gc["open_required_findings"]:
                raise GateUnsatisfied("parent-level findings are unresolved and not waived",
                                      findings=[f["id"] for f in gc["open_required_findings"]])
            unmet = self._classification_unmet(state, unit, gc["snapshot"]["children_digest"])
            if unmet:
                raise GateUnsatisfied(f"{work_id}: {unmet}")
            backlog = self.history.audit_backlog(state) if unit["kind"] == "epic" else None
            if backlog:  # ADR-0011: Epic closeout requires at least an incremental audit through the current root
                raise GateUnsatisfied(f"{work_id}: an Epic closes only once the history is audited through the current "
                                      f"root ({backlog} entries are unverified): run `aew history audit --expect-rev "
                                      "N`, then close it", unverified=backlog)
            self.gates.record_relied_on(ctx, unit, gc, list(gc["gates"]))
            decision = self.k.new_decision(ctx, "closeout", f"{work_id} closed: {unit['title']}", work_unit=work_id,
                                         reason=reason)
            path = f"work/{work_id}/closeout.md"
            text = self._closeout_record(state, work_id, unit, gc, decision)
            ctx.session.write(path, text)
            ctx.refs.append(path)
            self._end_parent_invocations(state, unit, "cancelled")
            unit["closeout"] = {"decision": decision, "record": path, "at": utc_now()}
            unit["completion_record"] = path
            unit["completion_sha256"] = sha256_text(text)
            ctx.summary = f"{work_id} closed ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "decision": decision, "closeout_record": path,
                "revision": ctx.session.committed_revision}

    def _closeout_record(self, state: dict[str, Any], work_id: str, unit: dict[str, Any], gc: dict[str, Any],
                         decision: str) -> str:
        children = []
        # Its own children, hot and archived: a closeout reads the bundles of this parent's children only (R3).
        kids = sorted([(cid, state["work"][cid]) for cid in H.children(state, work_id)]
                      + self.archive.archived_children(state, work_id))
        for cid, c in kids:
            entry = {"id": cid, "kind": c["kind"], "state": c["state"], "mutating": c.get("mutating"),
                     "completion_record": c.get("completion_record"),
                     "completion_sha256": self._completion_of(state, cid) if cid in state["work"]
                     else c.get("completion_sha256")}
            if c["state"] == "CANCELLED":
                entry["cancelled"] = next((h.get("reason") for h in reversed(c.get("history", []))
                                           if h.get("to") == "CANCELLED"), None) or (c.get("cancellation") or {}).get(
                    "decision")
            if c.get("integration", {}) and (c.get("integration") or {}).get("commit"):
                entry["integrated_commit"] = c["integration"]["commit"]
            children.append(entry)
        plan = unit.get("plan") or {}
        meta = {"schema": "aew/closeout/v1", "work_unit": work_id, "kind": unit["kind"], "at": utc_now(),
                "decision": decision, "plan": {"revision": plan.get("accepted"), "sha256": plan.get("sha256")},
                "baseline_commit": unit.get("baseline_commit"), "authoritative_commit": gc["snapshot"]["base_revision"],
                "children_digest": gc["snapshot"]["children_digest"], "children": children,
                "dependencies": [{**e, "state": (H.upstream(state, e["id"]) or {}).get("state"),
                                  "completion_sha256": self._completion_of(state, e["id"])}
                                 for e in effective_edge_set(state, work_id)],
                "gates": {g: v["status"] for g, v in gc["gates"].items()},
                "basis": {g: v["evidence"] for g, v in sorted(gc["gates"].items())
                          if isinstance(v.get("evidence"), str)},
                "evidence": [{"id": e["id"], "kind": e["kind"], "result": e["result"], "sha256": e["sha256"]}
                             for e in unit.get("evidence", [])],
                "classifications": unit.get("classifications", []), "waivers": unit.get("waivers", [])}
        body = (f"# Closeout — {work_id}: {unit['title']}\n\nClosed by the Lead after every child reached DONE or "
                "CANCELLED and the parent's own acceptance gates passed against the parent snapshot (authoritative "
                "source + child set). Children completing alone does not prove parent acceptance (WC §8).\n")
        return render_frontmatter(meta, body)

    def work_cancel(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        """Cancel a Story/Epic and, atomically, every non-terminal descendant (decision recorded)."""
        if not (reason and reason.strip()):
            raise UsageError("cancelling a parent needs a reason")
        with self.k.lead_txn(token, expect_rev, "work.cancel", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if not H.is_parent(unit):
                raise IllegalTransition("cancel a Ticket with `aew work transition --to CANCELLED --reason ...`")
            if unit["state"] in H.TERMINAL:
                raise IllegalTransition(f"{work_id} is {unit['state']}")
            open_desc = [d for d in H.descendants(state, work_id) if state["work"][d]["state"] not in H.TERMINAL]
            publishing = [d for d in open_desc if (state["work"][d].get("integration") or {}).get("status") == "publishing"]
            if publishing:
                raise IllegalTransition("a publish is in progress under this parent; run `aew integrate reconcile` "
                                        "first", publishing=publishing)
            decision = self.k.new_decision(ctx, "cancellation", f"{work_id} cancelled with its open descendants",
                                         work_unit=work_id, reason=reason,
                                         body="Cascaded to: " + (", ".join(open_desc) or "none") + "\n")
            for did in sorted(open_desc, key=lambda d: -H.depth(state, d)):
                d = state["work"][did]
                why = f"cancelled with {work_id} ({decision}): {reason}"
                if H.is_parent(d):
                    d["cancellation"] = {"decision": decision, "inherited_from": work_id, "at": utc_now()}
                    self._end_parent_invocations(state, d, "cancelled")
                    continue
                transitions.check(d["state"], "CANCELLED", "transition")
                self.units.set_state(d, "CANCELLED", why, state=state)
                self.invocations.release_workspace(ctx, d, "cancelled")
            self._end_parent_invocations(state, unit, "cancelled")
            unit["cancellation"] = {"decision": decision, "reason": reason, "at": utc_now()}
            ctx.summary = f"{work_id} cancelled ({decision}); {len(open_desc)} descendant(s) cancelled"
            self.units.before_commit(ctx)
        self.nm.prune_observations()
        return {"ok": True, "work_id": work_id, "decision": decision, "cancelled_descendants": open_desc,
                "revision": ctx.session.committed_revision}

    def _invalidate_bindings(self, state: dict[str, Any], work_id: str, why: str) -> list[str]:
        touched = []
        for wid in [work_id, *H.descendants(state, work_id)]:
            plan = state["work"][wid].get("plan") or {}
            if plan.get("accepted"):
                plan["bindings_invalidated"] = why
                touched.append(wid)
        return touched

    def _move(self, ctx: Any, work_id: str, new_parent: str | None, why: str) -> list[str]:
        state = ctx.state
        if work_id not in state["work"]:
            return self._move_archived(ctx, work_id, new_parent, why)
        unit = self.units.unit(state, work_id)
        old = unit.get("parent")
        if old and state["work"][old]["state"] in H.TERMINAL:
            raise IllegalTransition(f"{work_id} belongs to {old}, which is {state['work'][old]['state']}; a closed or "
                                    "cancelled parent's children are part of its record")
        if new_parent is not None:
            self.units.check_parent(state, unit["kind"], new_parent)
            if new_parent == work_id or new_parent in H.descendants(state, work_id):
                raise UsageError(f"{work_id} cannot be moved under itself or its own descendant")
        subtree = [w for w in [work_id, *H.descendants(state, work_id)] if state["work"][w]["kind"] == "ticket"]
        before = {w: effective_edge_set(state, w) for w in subtree}
        self.archive.move_hot_subtree(state, unit, old, new_parent)  # archived work below it moves too (R3)
        unit["parent"] = new_parent
        unit.setdefault("parent_history", []).append({"from": old, "to": new_parent, "at": utc_now(), "reason": why})
        self.units.refuse_cycles(state)
        self._refuse_dependency_change_of_started_work(state, before, "this move")
        return self._invalidate_bindings(state, work_id, f"moved from {old} to {new_parent}: {why}")

    def _move_archived(self, ctx: Any, work_id: str, new_parent: str | None, why: str) -> list[str]:
        """A finished unit moves too (into a live parent, whose acceptance then sees it). It is archived, so the move
        updates both parents' summaries and is recorded as an annotation; nothing below it is hot (R3)."""
        state = ctx.state
        unit = self.units.view(state, work_id)
        old = unit.get("parent")
        if old:
            old_state = (state["work"].get(old) or self.units.view(state, old))["state"]
            if old_state in H.TERMINAL:
                raise IllegalTransition(f"{work_id} belongs to {old}, which is {old_state}; a closed or cancelled "
                                        "parent's children are part of its record")
        if new_parent is not None:
            self.units.check_parent(state, unit["kind"], new_parent)
        self.archive.move(ctx, work_id, unit, new_parent, decision=None, note=why)
        return []

    def _refuse_dependency_change_of_started_work(self, state: dict[str, Any], before: dict[str, list[dict[str, str]]],
                                                  what: str) -> None:
        """A structure change may not change the inherited edges of started work (M2 review B2).

        Moving re-parents inherited edges, which is an edge edit for every Ticket below the moved unit, so the
        rule for ``work depend`` applies (ADR-0007): each such Ticket must be BLOCKED, READY or REPLAN_REQUIRED.
        A started attempt was dispatched for its old dependencies; it ends when the replacement plan is
        accepted, and the next dispatch checks the new ones. Finished Tickets are not re-dispatched.
        """
        changed = {w: {"before": [f"{e['id']}:{e['kind']}" for e in edges],
                       "after": [f"{e['id']}:{e['kind']}" for e in effective_edge_set(state, w)]}
                   for w, edges in before.items() if effective_edge_set(state, w) != edges}
        started = sorted(w for w in changed if state["work"][w]["state"] not in UNSTARTED | H.TERMINAL)
        if started:
            raise IllegalTransition(
                f"{what} changes the effective dependencies of started work; a new dispatch is required. Move "
                f"{', '.join(started)} to REPLAN_REQUIRED first (the attempt ends when a plan revision is accepted, and "
                "the next dispatch checks the new dependencies)",
                in_progress=started, dependencies={w: changed[w] for w in started})

    def work_move(self, *, token: str, expect_rev: int, work_id: str, parent: str | None,
                  reason: str) -> dict[str, Any]:
        if not (reason and reason.strip()):
            raise UsageError("a hierarchy change needs a reason")
        with self.k.lead_txn(token, expect_rev, "work.move", reason=reason) as ctx:
            old = self.units.view(ctx.state, work_id).get("parent")
            decision = self.k.new_decision(ctx, "hierarchy_change", f"{work_id} moved from {old} to {parent}",
                                         work_unit=work_id, reason=reason)
            invalidated = self._move(ctx, work_id, parent, f"{reason} ({decision})")
            ctx.summary = f"{work_id} moved {old} -> {parent} ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "from": old, "to": parent, "decision": decision,
                "plans_needing_reconfirmation": invalidated, "revision": ctx.session.committed_revision}

    def work_promote(self, *, token: str, expect_rev: int, work_id: str, to: str, title: str, reason: str,
                     risk_class: int | None = None) -> dict[str, Any]:
        """Promote a Ticket to a Story (or a Ticket/Story to an Epic): identity and evidence are preserved."""
        if not (reason and reason.strip()):
            raise UsageError("promotion needs the reason evidence showed the unit was too small (KC §9.4)")
        with self.k.lead_txn(token, expect_rev, "work.promote", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if to not in PROMOTION.get(unit["kind"], set()):
                raise UsageError(f"a {unit['kind']} cannot be promoted to a {to}")
            if unit["state"] in H.TERMINAL or unit["state"] == "VERIFICATION_FAILED":
                raise IllegalTransition(f"{work_id} is {unit['state']}"
                                        + ("; classify the failure first" if unit["state"] == "VERIFICATION_FAILED" else ""))
            if (unit.get("integration") or {}).get("status") == "publishing":
                raise IllegalTransition("a publish is in progress; run `aew integrate reconcile` first")
            cls = max(unit["risk_class"], risk_class if risk_class is not None else unit["risk_class"])
            new_parent = next((a for a in H.ancestors(state, work_id)
                               if state["work"][a]["kind"] in H.PARENT_KINDS[to]), None)
            decision = self.k.new_decision(ctx, "promotion", f"{work_id} promoted to a {to}: {title}",
                                         work_unit=work_id, reason=reason)
            new_id = self._create_promoted(ctx, to, title, cls, new_parent, work_id)
            # A promoted Ticket's attempt ends with its replan, so its own inherited edges may change in the move.
            if unit["kind"] == "ticket" and unit["state"] != "REPLAN_REQUIRED":
                transitions.check(unit["state"], "REPLAN_REQUIRED", "transition")
                self.units.set_state(unit, "REPLAN_REQUIRED", f"promoted to {new_id} ({decision}): {reason}",
                                     state=state)
            self._move(ctx, work_id, new_id, f"promoted to {new_id} ({decision})")
            ctx.summary = f"{work_id} promoted to {new_id} ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "promoted_to": new_id, "decision": decision,
                "revision": ctx.session.committed_revision}

    def _create_promoted(self, ctx: Any, kind: str, title: str, risk_class: int, parent: str | None,
                         promoted_from: str) -> str:
        from aew.knowledge.records import work_unit_record
        from aew.engine.work_ops import RECORD_NAME

        state = ctx.state
        origin = state["work"][promoted_from]
        state["counters"][kind] = state["counters"].get(kind, 0) + 1
        new_id = format_id(KIND_PREFIX[kind], state["counters"][kind])
        record = work_unit_record(
            unit_id=new_id, kind=kind, title=title, created_at=utc_now(),
            created_by={k: ctx.actor[k] for k in ("kind", "session_label", "generation")}, risk_class=risk_class,
            mutating=False, parent=parent, body=f"Promoted from {promoted_from} ({origin['title']}).\n",
            promoted_from=promoted_from)
        text = record.render()
        path = f"work/{new_id}/{RECORD_NAME[kind]}"
        ctx.session.write(path, text)
        ctx.refs.append(path)
        state["work"][new_id] = {"kind": kind, "title": title, "record": path, "record_sha256": sha256_text(text),
                                 "parent": parent, "state": "PLANNING", "state_reason": "created by promotion",
                                 "risk_class": risk_class, "mutating": False, "depends_on": [], "policy": None,
                                 "created_at": utc_now(), "plan": None, "plans": [], "promoted_from": promoted_from}
        return new_id

    def work_depend(self, *, token: str, expect_rev: int, work_id: str, add: list[str] | None = None,
                    remove: list[str] | None = None, reason: str) -> dict[str, Any]:
        """Edit a unit's dependency edges (a decision); only while no affected Ticket is in progress."""
        if not (reason and reason.strip()):
            raise UsageError("a dependency change needs a reason")
        if not add and not remove:
            raise UsageError("nothing to change: pass --add and/or --remove")
        with self.k.lead_txn(token, expect_rev, "work.depend", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["state"] in H.TERMINAL:
                raise IllegalTransition(f"{work_id} is {unit['state']}")
            affected = [work_id] if unit["kind"] == "ticket" else H.descendants(state, work_id)
            # ADR-0007: only while every affected Ticket is BLOCKED, READY or REPLAN_REQUIRED. A DONE Ticket finished
            # without an edge added now, so the edge would never have held for it (M2 review major 1). A cancelled
            # Ticket never runs again and contributes nothing, so it is not affected.
            busy = {a: state["work"][a]["state"] for a in sorted(affected) if state["work"][a]["kind"] == "ticket"
                    and state["work"][a]["state"] not in UNSTARTED | {"CANCELLED"}}
            if unit["kind"] != "ticket" and H.archived_summary(unit)["done_tickets_subtree"]:
                # Archived DONE Tickets below it finished under the current edges too (R3): the counter says so in
                # O(1); only this refusal reads which ones.
                busy.update({a: "DONE" for a in self.archive.archived_tickets_below(state, work_id, "DONE")})
                busy = dict(sorted(busy.items()))
            if busy:
                raise IllegalTransition("dependencies change only while every affected Ticket is BLOCKED, READY or "
                                        "REPLAN_REQUIRED; move started ones to REPLAN_REQUIRED first (a finished "
                                        "Ticket completed under the current edges: plan the change as a new unit)",
                                        affected=busy)
            edges = list(unit.get("depends_on", []))
            for dep in remove or []:
                if not any(e["id"] == dep for e in edges):
                    raise NotFound(f"{work_id} has no dependency on {dep}")
                edges = [e for e in edges if e["id"] != dep]
            new = self.units.parse_edges(state, add or [])
            clash = {e["id"] for e in new} & {e["id"] for e in edges}
            if clash:
                raise UsageError(f"already a dependency: {sorted(clash)}")
            unit["depends_on"] = edges + new
            self.units.refuse_cycles(state)
            decision = self.k.new_decision(ctx, "dependency_change", f"{work_id} dependencies changed",
                                           work_unit=work_id,
                                         reason=reason, body=f"added: {add or []}\nremoved: {remove or []}\n")
            ctx.summary = f"{work_id} dependencies changed ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "depends_on": unit["depends_on"], "decision": decision,
                "revision": ctx.session.committed_revision}

    def work_tree(self, root: str | None = None) -> dict[str, Any]:
        state = self.k.store.read()

        def node(wid: str) -> dict[str, Any]:
            if wid not in state["work"]:
                return archived_node(wid)
            u = state["work"][wid]
            out: dict[str, Any] = {"id": wid, "kind": u["kind"], "state": u["state"], "title": u["title"],
                                   "risk_class": u["risk_class"]}
            if u["kind"] == "ticket":
                out["mutating"] = u.get("mutating")
                if is_nm_ticket(u) and u.get("execution"):
                    out["execution"] = {k: u["execution"].get(k) for k in ("attempt", "expected_kind", "selected_by")}
                if u.get("blocked_by"):
                    out["blocked_by"] = u["blocked_by"]
            else:
                out["attention"] = u.get("attention", [])
                out["blocked_descendants"] = u.get("blocked_descendants", False)
                out["children"] = [node(c) for c in H.children(state, wid)]
                archived = H.archived_summary(u)
                if archived["done"] or archived["cancelled"]:
                    out["archived"] = {"done": archived["done"], "cancelled": archived["cancelled"]}
            if u.get("depends_on"):
                out["depends_on"] = u["depends_on"]
            return out

        def archived_node(wid: str) -> dict[str, Any]:
            """An archived unit asked for by id: its record and its archived children, read on request (R7)."""
            u = self.units.view(state, wid)
            out = {"id": wid, "kind": u["kind"], "state": u["state"], "title": u["title"],
                   "risk_class": u["risk_class"], "archived": True}
            if u["kind"] == "ticket":
                out["mutating"] = u.get("mutating")
            else:
                out["children"] = [archived_node(c) for c, _ in self.archive.archived_children(state, wid)]
            return out

        if root:
            self.units.view(state, root)  # NotFound for an unknown id
            tree = [node(root)]
        else:
            # The hot roots, and the most recently finished ones as single lines (``recent``, bounded): a view shows a
            # bounded summary and recent items, never the whole history (ADR-0011, operator 2026-10-01).
            recent = {r["id"]: r for r in state.get("recent", [])
                      if r["id"] not in state["work"] and not (r.get("parent") and r["parent"] in state["work"])}
            roots = sorted({w for w, u in state["work"].items() if not u.get("parent")} | set(recent))
            tree = [node(r) if r in state["work"] else {**{k: recent[r][k] for k in ("id", "kind", "state", "title")},
                                                         "archived": True} for r in roots]
        return {"revision": state["revision"], "tree": tree, "lines": self.tree_lines(tree)}

    @staticmethod
    def tree_lines(tree: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []

        def walk(n: dict[str, Any], indent: int) -> None:
            tag = n["kind"].capitalize()
            extra = ""
            if n["kind"] == "ticket":
                extra = "" if n.get("mutating") else " [non-mutating" + (
                    f", attempt {n['execution']['attempt']}: {n['execution']['expected_kind']}]" if n.get("execution")
                    else "]")
            if n.get("attention"):
                extra += "  ! " + "; ".join(n["attention"])
            if n.get("archived") is True:
                extra += "  (archived)"
            elif n.get("archived"):
                extra += f"  ({n['archived']['done']} done, {n['archived']['cancelled']} cancelled, archived)"
            deps = ", ".join(e["id"] for e in n.get("depends_on", []))
            lines.append(f"{'  ' * indent}{tag} {n['id']} [{n['state']}] {n['title']}{extra}"
                         + (f"  -> {deps}" if deps else ""))
            for c in n.get("children", []):
                walk(c, indent + 1)

        for n in tree:
            walk(n, 0)
        return lines or ["(no work units)"]
