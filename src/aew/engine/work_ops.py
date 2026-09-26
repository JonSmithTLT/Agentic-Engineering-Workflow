"""Work graph operations: Epic/Story/Ticket records, plan revisions, Lead transitions (WC §7-§9; KC §9, §12)."""

from __future__ import annotations

from typing import Any

from aew.engine import transitions
from aew.engine.base import EngineBase, TxnContext
from aew.engine.dependencies import readiness_blockers, recompute_readiness
from aew.errors import GateUnsatisfied, IllegalTransition, NotFound, UsageError
from aew.knowledge.records import KIND_PREFIX, format_id, plan_record, work_unit_record
from aew.util import sha256_text, utc_now
from aew.workspace import git

RECORD_NAME = {"ticket": "ticket.md", "story": "story.md", "epic": "epic.md"}
PARENT_KINDS = {"ticket": {"story", "epic"}, "story": {"epic"}, "epic": set()}


class WorkOps(EngineBase):
    # ------------------------------------------------------------------ helpers

    def authoritative_commit(self) -> str | None:
        return git.rev_parse(f"refs/heads/{self.authoritative_branch}", cwd=self.repo_root)

    def before_commit(self, ctx: TxnContext) -> None:
        """Keep BLOCKED/READY consistent with the durable graph inside every Lead commit."""
        changed = recompute_readiness(ctx.state, repo_root=self.repo_root, base_commit=self.authoritative_commit())
        if changed:
            ctx.refs.extend(f"readiness:{wid}" for wid in changed)

    @staticmethod
    def unit(state: dict[str, Any], work_id: str) -> dict[str, Any]:
        unit = state["work"].get(work_id)
        if unit is None:
            raise NotFound(f"no work unit {work_id}")
        return unit

    def _set_state(self, unit: dict[str, Any], to: str, reason: str | None) -> dict[str, str]:
        change = {"from": unit["state"], "to": to}
        unit["state"] = to
        unit["state_reason"] = reason
        unit.setdefault("history", []).append({**change, "at": utc_now(), "reason": reason})
        return change

    def _guard(self, name: str | None, ctx: TxnContext, work_id: str, unit: dict[str, Any], to: str) -> None:
        if not name:
            return
        guard = getattr(self, f"_guard_{name}", None)
        if guard is None:
            raise GateUnsatisfied(f"guard {name} is not available")
        guard(ctx, work_id, unit, to)

    # ------------------------------------------------------------------ guards not based on evidence gates

    def _guard_implementer_active(self, ctx, work_id, unit, to) -> None:
        inv = ctx.state["invocations"].get(unit.get("implementer_invocation") or "")
        if not inv or inv["status"] != "active":
            raise GateUnsatisfied(f"{work_id} has no active implementer invocation")

    def _guard_findings_recorded(self, ctx, work_id, unit, to) -> None:
        # WC §8: REVIEW_FAILED -> RUNNING requires recorded findings (new ones, or earlier ones still open).
        reviews = [e for e in unit.get("evidence", []) if e["kind"] == "review"]
        still_open = [f for f in unit.get("findings", []) if f["required"] and f["status"] == "open"]
        if not still_open and not (reviews and reviews[-1].get("findings")):
            raise GateUnsatisfied(f"{work_id}: REVIEW_FAILED -> RUNNING requires recorded review findings")

    def _guard_returning_from_escalation(self, ctx, work_id, unit, to) -> None:
        origin = unit.get("escalated_from")
        if origin is None or transitions.PHASE_ORDER.get(to, 99) > transitions.PHASE_ORDER.get(origin, -1):
            raise GateUnsatisfied(f"{work_id} may return from escalation only to {origin} or an earlier phase")

    def _guard_not_beyond_interrupted_phase(self, ctx, work_id, unit, to) -> None:
        origin = unit.get("interrupted_from")
        if origin is None or transitions.PHASE_ORDER.get(to, 99) > transitions.PHASE_ORDER.get(origin, -1):
            raise GateUnsatisfied(
                f"{work_id} was interrupted in {origin}; reconciliation may not move it beyond that phase "
                "(success is never inferred from a prior invocation)"
            )

    # ------------------------------------------------------------------ create

    def work_create(
        self,
        *,
        token: str,
        expect_rev: int,
        kind: str,
        title: str,
        risk_class: int,
        mutating: bool | None = None,
        parent: str | None = None,
        depends_on: list[str] | None = None,
        scope_paths: list[str] | None = None,
        goal_backwards: list[str] | None = None,
        contract: list[str] | None = None,
        mandatory_gates: list[str] | None = None,
        min_descendant_class: int | None = None,
        rationale: str | None = None,
        external_refs: list[str] | None = None,
        body: str = "",
        card: str | None = None,
    ) -> dict[str, Any]:
        if kind not in RECORD_NAME:
            raise UsageError("kind must be ticket, story or epic")
        if not 0 <= risk_class <= 4:
            raise UsageError("risk class must be 0..4")
        if min_descendant_class is not None and not rationale:
            raise UsageError("a minimum descendant class requires a recorded rationale (WC §7.4)")
        if kind != "ticket" and depends_on:
            raise UsageError("M1 supports dependency edges between Tickets only")
        with self.lead_txn(token, expect_rev, "work.create") as ctx:
            state = ctx.state
            if parent is not None:
                parent_unit = self.unit(state, parent)
                if parent_unit["kind"] not in PARENT_KINDS[kind]:
                    raise UsageError(f"a {kind} cannot have a {parent_unit['kind']} parent")
            edges = self._parse_edges(state, depends_on or [])
            counter = kind
            state["counters"][counter] = state["counters"].get(counter, 0) + 1
            work_id = format_id(KIND_PREFIX[kind], state["counters"][counter])
            is_mutating = (kind == "ticket") if mutating is None else (mutating and kind == "ticket")
            policy = None
            if kind != "ticket" and (mandatory_gates or min_descendant_class is not None):
                policy = {"mandatory_gates": list(mandatory_gates or []),
                          "min_descendant_class": min_descendant_class, "rationale": rationale}
            record = work_unit_record(
                unit_id=work_id, kind=kind, title=title, created_at=utc_now(),
                created_by={k: ctx.actor[k] for k in ("kind", "session_label", "generation")},
                risk_class=risk_class, mutating=is_mutating, parent=parent, scope_paths=scope_paths,
                goal_backwards=goal_backwards, contract=contract, policy=policy,
                external_refs=external_refs, body=body,
            )
            text = record.render()
            path = f"work/{work_id}/{RECORD_NAME[kind]}"
            ctx.session.write(path, text)
            ctx.refs.append(path)
            unit: dict[str, Any] = {
                "kind": kind, "title": title, "record": path, "record_sha256": sha256_text(text),
                "parent": parent, "state": "OPEN" if kind != "ticket" else "BLOCKED", "state_reason": "created",
                "risk_class": risk_class, "mutating": is_mutating, "depends_on": edges,
                "policy": policy, "created_at": utc_now(), "plan": None, "plans": [],
            }
            if kind == "ticket":
                unit.update(blocked_by=[{"kind": "plan_not_accepted"}], workspace=None, invocations=[],
                            implementer_invocation=None, evidence=[], classifications=[], waivers=[],
                            integration=None)
            state["work"][work_id] = unit
            if card:
                chosen = self.role_catalog().get(card)  # type: ignore[attr-defined]  (RoleOps)
                self._slot_ok(unit, "execute", chosen)  # type: ignore[attr-defined]
                unit["role_plan"] = {"execute": [{"card": chosen.id, "version": chosen.meta.get("version"),
                                                  "selected_by": "lead", "pinned": False}],
                                     "review": [], "verify": [], "forbidden": []}
            ctx.summary = f"created {kind} {work_id}: {title}"
            self.before_commit(ctx)
        return {"ok": True, "id": work_id, "record": path, "revision": ctx.session.committed_revision}

    def _parse_edges(self, state: dict[str, Any], specs: list[str]) -> list[dict[str, str]]:
        edges = []
        for spec in specs:
            dep_id, _, dep_kind = spec.partition(":")
            up = self.unit(state, dep_id)
            if up["kind"] != "ticket":
                raise UsageError(f"{dep_id}: M1 dependency edges must point at Tickets")
            dep_kind = dep_kind or ("mutating" if up["mutating"] else "evidence")
            if dep_kind not in {"mutating", "evidence"}:
                raise UsageError(f"dependency kind must be mutating or evidence, got {dep_kind}")
            if dep_kind == "mutating" and not up["mutating"]:
                raise UsageError(f"{dep_id} is not mutating; use an evidence dependency")
            edges.append({"id": dep_id, "kind": dep_kind})
        return edges

    # ------------------------------------------------------------------ plans

    def plan_propose(self, *, token: str, expect_rev: int, work_id: str, body: str,
                     reason: str | None = None, affected_paths: list[str] | None = None) -> dict[str, Any]:
        if not body.strip():
            raise UsageError("plan body is empty")
        with self.lead_txn(token, expect_rev, "plan.propose", reason=reason) as ctx:
            unit = self.unit(ctx.state, work_id)
            if unit["state"] in transitions.TERMINAL:
                raise IllegalTransition(f"{work_id} is {unit['state']}")
            revision = len(unit["plans"]) + 1
            supersedes = (unit.get("plan") or {}).get("accepted")
            if supersedes and not reason:
                raise UsageError("a plan revision that supersedes an accepted plan must state its reason")
            record = plan_record(
                work_unit=work_id, revision=revision, created_at=utc_now(),
                author={"role": "lead", "session_label": ctx.actor.get("session_label"),
                        "generation": ctx.actor["generation"]},
                body=body, supersedes=supersedes, reason=reason, affected_paths=affected_paths,
            )
            text = record.render()
            path = f"work/{work_id}/plan-v{revision}.md"
            ctx.session.write(path, text)
            ctx.refs.append(path)
            unit["plans"].append({"revision": revision, "path": path, "sha256": sha256_text(text),
                                  "supersedes": supersedes, "status": "proposed"})
            ctx.summary = f"{work_id} plan v{revision} proposed"
            self.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "revision_number": revision, "path": path,
                "revision": ctx.session.committed_revision}

    def plan_accept(self, *, token: str, expect_rev: int, work_id: str, revision: int) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "plan.accept") as ctx:
            unit = self.unit(ctx.state, work_id)
            if unit["state"] not in {"BLOCKED", "READY", "REPLAN_REQUIRED", "OPEN"}:
                raise IllegalTransition(
                    f"{work_id} is {unit['state']}; move it to REPLAN_REQUIRED before changing the accepted plan",
                )
            entry = next((p for p in unit["plans"] if p["revision"] == revision), None)
            if entry is None:
                raise NotFound(f"{work_id} has no plan revision {revision}")
            if entry["status"] != "proposed":
                raise IllegalTransition(f"plan v{revision} is {entry['status']}")
            for p in unit["plans"]:
                if p["status"] == "accepted":
                    p["status"] = "superseded"
            entry["status"] = "accepted"
            unit["plan"] = {"accepted": revision, "path": entry["path"], "sha256": entry["sha256"]}
            decision = self.new_decision(ctx, "plan_acceptance", f"{work_id} plan v{revision} accepted",
                                         work_unit=work_id, evidence_refs=[entry["path"]])
            if unit["state"] == "REPLAN_REQUIRED":
                blockers = readiness_blockers(ctx.state, unit, repo_root=self.repo_root,
                                              base_commit=self.authoritative_commit())
                to = "BLOCKED" if blockers else "READY"
                transitions.check("REPLAN_REQUIRED", to, "plan.accept")
                self._set_state(unit, to, f"plan v{revision} accepted")
            ctx.summary = f"{work_id} plan v{revision} accepted ({decision})"
            self.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "accepted": revision, "decision": decision,
                "revision": ctx.session.committed_revision}

    # ------------------------------------------------------------------ generic Lead transitions

    def work_transition(self, *, token: str, expect_rev: int, work_id: str, to: str,
                        reason: str | None = None) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "work.transition", reason=reason) as ctx:
            unit = self.unit(ctx.state, work_id)
            if unit["kind"] != "ticket":
                raise IllegalTransition("Story/Epic state is derived from child work (WC §8)")
            frm = unit["state"]
            rule = transitions.check(frm, to, "transition")
            if rule.reason_required and not (reason and reason.strip()):
                raise UsageError(f"{frm} -> {to} requires --reason")
            self._guard(rule.guard, ctx, work_id, unit, to)
            if to == "ESCALATED":
                unit["escalated_from"] = frm
            if frm == "ESCALATED":
                unit.pop("escalated_from", None)
            change = self._set_state(unit, to, reason)
            decision = None
            if to == "CANCELLED":
                decision = self.new_decision(ctx, "cancellation", f"{work_id} cancelled", work_unit=work_id,
                                             resulting_transition=change, reason=reason)
                self._release_workspace(ctx, unit, "cancelled")
            elif to == "RUNNING" and transitions.PHASE_ORDER.get(frm, 0) > transitions.PHASE_ORDER["RUNNING"]:
                decision = self.new_decision(ctx, "state_regression", f"{work_id} returned to RUNNING from {frm}",
                                             work_unit=work_id, resulting_transition=change, reason=reason)
            self.after_transition(ctx, work_id, unit, change)
            ctx.summary = f"{work_id} {frm} -> {to}"
            self.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "from": frm, "to": to, "decision": decision,
                "revision": ctx.session.committed_revision}

    def work_reconcile(self, *, token: str, expect_rev: int, work_id: str, to: str, reason: str,
                       inspection: dict[str, Any] | None = None) -> dict[str, Any]:
        """INTERRUPTED -> an earlier-or-equal phase, after the Lead inspected workspace and artifacts."""
        with self.lead_txn(token, expect_rev, "work.reconcile", reason=reason) as ctx:
            unit = self.unit(ctx.state, work_id)
            frm = unit["state"]
            rule = transitions.check(frm, to, "reconcile")
            if not (reason and reason.strip()):
                raise UsageError("reconciliation requires --reason describing what was inspected")
            self._guard(rule.guard, ctx, work_id, unit, to)
            inspection = inspection or self.inspect_workspace(unit)
            change = self._set_state(unit, to, reason)
            unit.pop("interrupted_from", None)
            decision = self.new_decision(
                ctx, "reconciliation", f"{work_id} reconciled from INTERRUPTED to {to}", work_unit=work_id,
                resulting_transition=change, reason=reason,
                body="Inspection at reconciliation:\n\n" + "\n".join(f"- {k}: {v}" for k, v in inspection.items()),
            )
            ctx.summary = f"{work_id} reconciled -> {to}"
            self.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "to": to, "decision": decision, "inspection": inspection,
                "revision": ctx.session.committed_revision}

    # Hooks refined by later mixins (workspaces, evidence).
    def inspect_workspace(self, unit: dict[str, Any]) -> dict[str, Any]:
        return {"workspace": (unit.get("workspace") or {}).get("id", "none")}

    def _release_workspace(self, ctx: TxnContext, unit: dict[str, Any], why: str) -> None:
        if unit.get("workspace"):
            unit["workspace"]["status"] = f"released ({why})"

    def after_transition(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], change: dict[str, str]) -> None:
        return None

    # ------------------------------------------------------------------ queries

    def work_show(self, work_id: str) -> dict[str, Any]:
        state = self.store.read()
        unit = self.unit(state, work_id)
        record_path = self.aew_root / unit["record"]
        return {"id": work_id, "revision": state["revision"], "control": unit,
                "record": record_path.read_text(encoding="utf-8") if record_path.exists() else None,
                "allowed_transitions": transitions.allowed_from(unit["state"]),
                "children": sorted(k for k, v in state["work"].items() if v.get("parent") == work_id),
                "rollup": self.rollup(state, work_id) if unit["kind"] != "ticket" else None}

    def work_list(self, *, state_filter: str | None = None) -> dict[str, Any]:
        state = self.store.read()
        items = [
            {"id": wid, "kind": u["kind"], "state": u["state"], "title": u["title"], "parent": u.get("parent"),
             "risk_class": u["risk_class"], "blocked_by": u.get("blocked_by", [])}
            for wid, u in sorted(state["work"].items())
            if state_filter is None or u["state"] == state_filter
        ]
        return {"revision": state["revision"], "items": items}

    @staticmethod
    def rollup(state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """Derived Story/Epic state from child work (WC §8: never hand-maintained)."""
        counts: dict[str, int] = {}
        stack = [work_id]
        while stack:
            current = stack.pop()
            for cid, child in state["work"].items():
                if child.get("parent") == current:
                    if child["kind"] == "ticket":
                        counts[child["state"]] = counts.get(child["state"], 0) + 1
                    else:
                        stack.append(cid)
        total = sum(counts.values())
        done = counts.get("DONE", 0) + counts.get("CANCELLED", 0)
        derived = "EMPTY" if total == 0 else ("CHILDREN_COMPLETE" if done == total else "IN_PROGRESS")
        return {"derived_state": derived, "children_by_state": counts,
                "note": "children complete does not prove parent acceptance (WC §8)"}
