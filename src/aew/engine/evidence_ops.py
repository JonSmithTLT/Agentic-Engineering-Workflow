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
from typing import Any

from aew.engine import gates as G
from aew.engine import transitions
from aew.engine.authority import require_invocation
from aew.engine.base import TxnContext
from aew.engine.workspace_ops import WorkspaceOps
from aew.errors import (
    GateUnsatisfied,
    IllegalTransition,
    NotFound,
    PermissionDenied,
    StaleCandidate,
    UsageError,
    ValidationFailed,
)
from aew.knowledge import evidence as E
from aew.knowledge.records import read_record
from aew.policy import checks as C
from aew.policy import guardrails as GR
from aew.snapshot.fingerprint import changed_paths
from aew.util import create_exclusive, parse_frontmatter, sha256_file, utc_now

REVIEW_ROLES = {"reviewer"}


class EvidenceOps(WorkspaceOps):
    # ------------------------------------------------------------------ context helpers

    def _record_meta(self, unit: dict[str, Any]) -> dict[str, Any]:
        return read_record(self.aew_root / unit["record"], "work-unit").meta

    def _invocation_workspace(self, state: dict[str, Any], inv: dict[str, Any]) -> tuple[Path, str, str | None]:
        """The workspace this invocation was dispatched for — and only while it is still live (review M2).

        An invocation is never retargeted to a later workspace or candidate of the same Ticket.
        """
        unit = state["work"][inv["work_unit"]]
        if inv.get("scope") == "integration":
            integ = unit.get("integration") or {}
            if not integ or integ.get("workspace") != inv.get("workspace") \
                    or inv.get("integration_attempt") != integ.get("attempt"):
                raise PermissionDenied(
                    f"this invocation was dispatched for integration candidate {inv.get('workspace_id')}, which is "
                    "no longer the Ticket's live candidate", dispatched_for=inv.get("workspace"))
            return Path(integ["workspace"]), integ["workspace_id"], integ.get("base")
        ws = unit.get("workspace") or {}
        if ws.get("status") != "active" or ws.get("path") != inv.get("workspace"):
            raise PermissionDenied(
                f"this invocation was dispatched for workspace {inv.get('workspace_id') or inv.get('workspace')}, "
                f"which is no longer the Ticket's live workspace", dispatched_for=inv.get("workspace"),
                current=ws.get("id"), current_status=ws.get("status"))
        return Path(ws["path"]), ws["id"], ws.get("base_commit")

    @staticmethod
    def _card_ref(inv: dict[str, Any]) -> dict[str, Any] | None:
        card = inv.get("card")
        return {k: card[k] for k in ("id", "version", "sha256")} if card else None

    def gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        unit = self.unit(state, work_id)
        gates_policy = self.policy("gates")
        snapshot = self.current_snapshot(unit)
        guard = {"violations": [], "triggered_gates": [], "changed_paths": []}
        ws = unit.get("workspace")
        if snapshot and ws:
            guard = GR.evaluate(changed_paths(Path(ws["path"]), ws["base_commit"]), self.policy("guardrails"),
                                (self._record_meta(unit).get("scope") or {}).get("paths", []))
        obligations = G.effective_obligations(state, work_id, gates_policy, guard["triggered_gates"],
                                              self.plan_gates(unit))
        evidence, problems = E.scan(self.aew_root, work_id)
        plan = unit.get("plan") or {}
        plan_ok = bool(plan) and sha256_file(self.aew_root / plan["path"]) == plan["sha256"]
        fingerprint = snapshot["relevant_inputs_fingerprint"] if snapshot else None
        results = G.evaluate(state, work_id, evidence, obligations=obligations, gates_policy=gates_policy,
                             fingerprint=fingerprint, plan_ok=plan_ok)
        return {"snapshot": snapshot, "guardrails": guard, "obligations": obligations, "gates": results,
                "evidence": evidence, "evidence_problems": problems,
                "open_required_findings": G.open_required_findings(unit)}

    def gate_show(self, work_id: str) -> dict[str, Any]:
        state = self.store.read()
        gc = self.gate_context(state, work_id)
        gc.pop("evidence")
        gc["evidence_ids"] = [e["id"] for e in E.scan(self.aew_root, work_id)[0]]
        gc["unmet"] = G.unmet(gc["gates"])
        return gc

    def _require_gates(self, gc: dict[str, Any], names: list[str], *, what: str) -> None:
        unmet = G.unmet(gc["gates"], [n for n in names if n in gc["obligations"]["gates"]])
        if gc["evidence_problems"]:
            raise GateUnsatisfied("evidence integrity problems", problems=gc["evidence_problems"])
        if gc["guardrails"]["violations"]:
            raise GateUnsatisfied(f"{what}: guardrail violations", violations=gc["guardrails"]["violations"])
        if unmet:
            raise GateUnsatisfied(f"{what}: gates not satisfied for the current evaluated snapshot",
                                  unmet=unmet, fingerprint=(gc["snapshot"] or {}).get("relevant_inputs_fingerprint"))

    def _ingest_ref(self, unit: dict[str, Any], ev: dict[str, Any]) -> None:
        refs = unit.setdefault("evidence", [])
        if not any(r["id"] == ev["id"] for r in refs):
            refs.append({"id": ev["id"], "kind": ev["kind"], "path": ev["_path"], "sha256": ev["_sha256"],
                         "result": ev["result"],
                         "fingerprint": ev["evaluated_snapshot"]["relevant_inputs_fingerprint"],
                         "findings": [f["id"] for f in (ev.get("review") or {}).get("findings", [])]})

    # ------------------------------------------------------------------ gate-based guards (WorkOps._guard)

    PRE_REVIEW = ["accepted_plan", "local_checks", "self_review"]

    def _review_gates(self, gc: dict[str, Any]) -> list[str]:
        return [g for g in gc["obligations"]["gates"] if g.startswith(G.REVIEW_GATES_PREFIX)]

    def _verification_gates(self, gc: dict[str, Any]) -> list[str]:
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

    def _record_relied_on(self, ctx: TxnContext, unit: dict[str, Any], gc: dict[str, Any], names: list[str]) -> None:
        """Pin (id + sha256) the evidence a transition relied on into control state."""
        wanted = self._gate_evidence_ids(gc, names)
        for ev in gc["evidence"]:
            if ev["id"] in wanted:
                self._ingest_ref(unit, ev)
                ctx.refs.append(ev["_path"])

    def _ingest_implementation(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], gc: dict[str, Any]) -> None:
        self._record_relied_on(ctx, unit, gc, self.PRE_REVIEW)
        # Bounded subagents are retired once their artifact is accepted (WC §5). If work returns to
        # RUNNING, the Lead dispatches a fresh implementer whose pack carries the findings/failure evidence.
        if unit.get("implementer_invocation"):
            self._complete_invocation(ctx.state, unit["implementer_invocation"])

    def _guard_ready_for_review(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        if not self._review_gates(gc):
            raise GateUnsatisfied("no review gate applies to this Ticket; advance to verification or commit-ready")
        self._require_gates(gc, self.PRE_REVIEW, what="RUNNING -> REVIEW_PENDING")
        self._ingest_implementation(ctx, work_id, unit, gc)

    def _guard_ready_for_verification_without_review(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        if self._review_gates(gc):
            raise GateUnsatisfied("independent review is required before verification", required=self._review_gates(gc))
        if not self._verification_gates(gc):
            raise GateUnsatisfied("no verification gate applies; advance to commit-ready")
        self._require_gates(gc, self.PRE_REVIEW, what="RUNNING -> VERIFY_PENDING")
        self._ingest_implementation(ctx, work_id, unit, gc)

    def _guard_commit_ready_without_review_or_verification(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        if self._review_gates(gc) or self._verification_gates(gc):
            raise GateUnsatisfied("review/verification gates apply to this Ticket",
                                  required=self._review_gates(gc) + self._verification_gates(gc))
        self._commit_ready(ctx, work_id, unit, gc)

    def _guard_review_current(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        self._require_gates(gc, self.PRE_REVIEW + self._review_gates(gc), what="REVIEW_PASSED -> VERIFY_PENDING")

    def _guard_commit_ready_without_verification(self, ctx, work_id, unit, to) -> None:
        gc = self.gate_context(ctx.state, work_id)
        if self._verification_gates(gc):
            raise GateUnsatisfied("verification gates apply to this Ticket", required=self._verification_gates(gc))
        self._commit_ready(ctx, work_id, unit, gc)

    def _guard_all_gates_current(self, ctx, work_id, unit, to) -> None:
        self._commit_ready(ctx, work_id, unit, self.gate_context(ctx.state, work_id))

    def _commit_ready(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], gc: dict[str, Any]) -> None:
        """WC §8: VERIFIED -> COMMIT_READY needs every effective gate current and required findings resolved/waived."""
        self._require_gates(gc, gc["obligations"]["gates"], what="-> COMMIT_READY")
        if gc["open_required_findings"]:
            raise GateUnsatisfied("mandatory review findings are unresolved and not waived",
                                  findings=[f["id"] for f in gc["open_required_findings"]])
        self._record_relied_on(ctx, unit, gc, list(gc["gates"]))
        unit["commit_ready_snapshot"] = gc["snapshot"]
        unit["commit_ready_gates"] = {g: v["status"] for g, v in gc["gates"].items()}
        # Identity of this acceptance: an integration candidate is bound to it (review B1).
        unit["commit_ready_seq"] = unit.get("commit_ready_seq", 0) + 1
        if unit.get("implementer_invocation"):
            self._complete_invocation(ctx.state, unit["implementer_invocation"])

    # ------------------------------------------------------------------ integration binding (review B1)

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

    def _require_current_binding(self, unit: dict[str, Any]) -> None:
        problem = self.binding_problem(unit)
        if problem:
            raise StaleCandidate("the integration candidate was built from an earlier COMMIT_READY or plan; "
                                 "run `aew integrate prepare` again", **problem)

    # ------------------------------------------------------------------ invocations

    def invoke_create(self, *, token: str, expect_rev: int, work_id: str, role: str | None = None,
                      card: str | None = None, scope: str = "ticket") -> dict[str, Any]:
        """Dispatch a bounded invocation. The Role card (explicit, planned, or workflow default)
        determines the archetype; authority comes from the archetype only (ADR-0006)."""
        with self.lead_txn(token, expect_rev, "invoke.create") as ctx:
            state = ctx.state
            unit = self.unit(state, work_id)
            st = unit["state"]
            if scope == "integration":
                slot = "verify"
                if not (st == "COMMIT_READY" and (unit.get("integration") or {}).get("status") == "prepared"):
                    raise IllegalTransition("post-integration verification needs a prepared integration candidate")
                self._require_current_binding(unit)
            elif st in {"ASSIGNED", "RUNNING"}:
                slot = "execute"
                current = state["invocations"].get(unit.get("implementer_invocation") or "")
                if current and current["status"] == "active":
                    raise IllegalTransition(f"{unit['implementer_invocation']} is still active; cancel it first")
            elif st == "REVIEW_PENDING":
                slot = "review"
            elif st == "VERIFY_PENDING":
                slot = "verify"
            else:
                raise IllegalTransition(f"no role is dispatched for {work_id} in state {st}")
            gc = self.gate_context(state, work_id) if slot in {"review", "verify"} and scope == "ticket" else None
            chosen = self.resolve_card(state, work_id, slot, card_id=card, role=role, gc=gc)
            if scope == "integration":
                integ = unit["integration"]
                workspace, ws_id = integ["workspace"], integ["workspace_id"]
            else:
                ws = unit.get("workspace") or {}
                if ws.get("status") != "active":
                    raise IllegalTransition(f"{work_id} has no active workspace")
                workspace, ws_id = ws["path"], ws["id"]
            snapshot = self.snapshot_of(workspace, ws_id)
            archetype = chosen.archetype
            inv_id, inv_token = self._new_invocation(ctx, archetype, work_id, scope=scope, workspace=workspace,
                                                     workspace_id=ws_id, snapshot=snapshot, card=chosen)
            if archetype == "implementer":
                unit["implementer_invocation"] = inv_id
            if scope == "integration":  # the candidate this invocation serves (re-review M2/R1)
                state["invocations"][inv_id].update(integration_attempt=unit["integration"]["attempt"],
                                                    candidate=unit["integration"]["candidate"])
            self.build_pack(ctx, inv_id)
            ctx.summary = f"{inv_id} ({chosen.id} / {archetype}, {scope}) dispatched for {work_id}"
        pack = ctx.state["invocations"][inv_id].get("pack") or {}
        return {"ok": True, "invocation": inv_id, "invocation_token": inv_token, "role": archetype,
                "role_card": chosen.id, "scope": scope, "evaluated_snapshot": snapshot,
                "pack": pack or None, "revision": ctx.session.committed_revision}

    def invoke_cancel(self, *, token: str, expect_rev: int, invocation: str, reason: str) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "invoke.cancel", reason=reason) as ctx:
            inv = ctx.state["invocations"].get(invocation)
            if inv is None:
                raise NotFound(f"no invocation {invocation}")
            if inv["status"] != "active":
                raise IllegalTransition(f"{invocation} is {inv['status']}")
            self._complete_invocation(ctx.state, invocation, "cancelled")
            ctx.summary = f"{invocation} cancelled"
        return {"ok": True, "revision": ctx.session.committed_revision}

    def invoke_show(self, invocation: str) -> dict[str, Any]:
        state = self.store.read()
        inv = state["invocations"].get(invocation)
        if inv is None:
            raise NotFound(f"no invocation {invocation}")
        return {"id": invocation, **{k: v for k, v in inv.items() if k != "token_id"}}

    # ------------------------------------------------------------------ checks (bounded roles)

    def check_run(self, *, invocation_token: str, check_id: str) -> dict[str, Any]:
        with self.store.session() as s:
            inv_id, inv, actor = require_invocation(s.state, invocation_token, "check.run")
            work_id = inv["work_unit"]
            workspace, ws_id, base = self._invocation_workspace(s.state, inv)
            unit = s.state["work"][work_id]
            allowed_checks = inv.get("allowed_checks")
            if allowed_checks is not None and check_id not in allowed_checks:
                card_id = (inv.get("card") or {}).get("id")
                raise PermissionDenied(f"role card {card_id} does not permit check {check_id}")
            cfg = C.resolve(self.policy("checks"), check_id)
            scope_paths = (self._record_meta(unit).get("scope") or {}).get("paths", [])
            plan = unit.get("plan") or {}
        if not workspace.exists():
            raise NotFound(f"workspace {workspace} is missing")
        before = self.snapshot_of(workspace, ws_id)
        if cfg.get("builtin"):
            verdict = GR.evaluate(changed_paths(workspace, base), self.policy("guardrails"), scope_paths)
            run = {"exit_code": 1 if verdict["violations"] else 0, "duration_s": 0.0,
                   "log": json.dumps(verdict, indent=2), "command": ["aew-builtin", "guardrails"]}
        else:
            verdict = None
            run = C.run(cfg, workspace)
        after = self.snapshot_of(workspace, ws_id)
        mutated = before["relevant_inputs_fingerprint"] != after["relevant_inputs_fingerprint"]
        result = "inconclusive" if mutated else ("pass" if run["exit_code"] == 0 else "fail")
        with self.store.session() as s:
            # Re-verify: a credential revoked while the check ran must not write evidence.
            inv_id, inv, actor = require_invocation(s.state, invocation_token, "check.run")
            seq = E.next_seq(self.aew_root, work_id)
            eid = f"{inv_id}-check-{check_id}-{seq}"
            log_rel = f"evidence/{work_id}/logs/{eid}.log"
            create_exclusive(self.aew_root / log_rel, run["log"])
            meta = {
                "schema": "aew/evidence/v1", "id": eid, "kind": "check_result", "work_unit": work_id,
                "producer": {"role": inv["role"], "invocation": inv_id, "role_card": self._card_ref(inv)},
                "created_at": utc_now(), "seq": seq,
                "plan_revision": {"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None,
                "evaluated_snapshot": before,
                "method": {"capability": "targeted_test_execution" if not cfg.get("builtin") else "guardrail_check",
                           "provider": "aew-check-runner", "command": run["command"]},
                "claim": f"check {check_id} passes on the evaluated snapshot",
                "result": result,
                "evidence": [{"path": log_rel, "sha256": sha256_file(self.aew_root / log_rel)}],
                "check": {"check_id": check_id, "exit_code": run["exit_code"], "duration_s": run["duration_s"],
                          "mutated_inputs": mutated,
                          **({"violations": verdict["violations"], "triggered_gates": verdict["triggered_gates"]}
                             if verdict else {})},
            }
            if check_id in self.policy("checks").get("baseline_failures", []):
                meta["check"]["baseline_known_failure"] = True
            create_exclusive(self.aew_root / f"evidence/{work_id}/{eid}.md", E.seal(meta, ""))
        return {"ok": True, "evidence": eid, "result": result, "exit_code": run["exit_code"],
                "mutated_inputs": mutated, "evaluated_snapshot": before, "log": log_rel}

    # ------------------------------------------------------------------ evidence submission (bounded roles)

    def submit(self, *, invocation_token: str, kind: str, text: str) -> dict[str, Any]:
        submitted, body = parse_frontmatter(text, source="submission")
        with self.store.session() as s:
            state = s.state
            inv_id, inv, actor = require_invocation(state, invocation_token, f"submit.{kind}")
            E.check_submission(inv["role"], kind, submitted)
            # Any report — implementation, review or verification — is written only while the invocation's
            # own workspace/candidate is still live (review M2, re-review M2).
            workspace, ws_id, _ = self._invocation_workspace(state, inv)
            work_id = inv["work_unit"]
            unit = state["work"][work_id]
            plan = unit.get("plan") or {}
            meta: dict[str, Any] = {
                "schema": "aew/evidence/v1", "kind": kind, "work_unit": work_id,
                "producer": {"role": inv["role"], "invocation": inv_id, "role_card": self._card_ref(inv),
                             **(submitted.get("producer") or {})},
                "created_at": utc_now(),
                "plan_revision": {"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None,
                "method": submitted.get("method") or {"capability": kind, "provider": "harness-role"},
                "claim": submitted.get("claim") or kind.replace("_", " "),
                "evidence": submitted.get("evidence") or [],
            }
            if kind == "implementation_report":
                meta["evaluated_snapshot"] = self.snapshot_of(workspace, ws_id)
                meta["implementation"] = submitted.get("implementation") or {}
                meta["result"] = submitted.get("result", "pass")
                if meta["result"] not in {"pass", "blocked"}:
                    raise ValidationFailed("an implementation report result is pass (complete) or blocked")
            elif kind == "review":
                review = dict(submitted.get("review") or {})
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
                meta["review"] = review
                meta["evaluated_snapshot"] = inv["snapshot"]
                meta["result"] = "pass" if review.get("disposition") == "pass" else "fail"
            elif kind == "verification":
                meta.update(self._verification_binding(state, inv_id, inv, submitted))
            else:
                raise UsageError(f"unknown evidence kind {kind}")
            seq = E.next_seq(self.aew_root, work_id)
            meta["id"] = f"{inv_id}-{E.SHORT[kind]}-{seq}"
            meta["seq"] = seq
            ordered = {k: meta[k] for k in ("schema", "id", "kind", "work_unit", "producer", "created_at", "seq",
                                             "plan_revision", "evaluated_snapshot", "method", "claim", "result",
                                             "evidence") if k in meta}
            ordered.update({k: v for k, v in meta.items() if k not in ordered})
            path = self.aew_root / f"evidence/{work_id}/{meta['id']}.md"
            create_exclusive(path, E.seal(ordered, body))
        return {"ok": True, "evidence": meta["id"], "result": meta["result"],
                "evaluated_snapshot": meta["evaluated_snapshot"], "path": str(path)}

    def _verification_binding(self, state: dict[str, Any], inv_id: str, inv: dict[str, Any],
                              submitted: dict[str, Any]) -> dict[str, Any]:
        v = dict(submitted.get("verification") or {})
        v.setdefault("scope", inv.get("scope", "ticket"))
        if v["scope"] != inv.get("scope", "ticket"):
            raise ValidationFailed("verification scope must match the dispatched scope")
        claims = v.get("claims") or []
        types = {c.get("type") for c in claims}
        if v["scope"] == "ticket" and not {"goal_backwards", "contract"} <= types:
            raise ValidationFailed("ticket verification needs both goal_backwards and contract claims (WC §11.4)")
        if not claims:
            raise ValidationFailed("verification needs at least one claim")
        work_id = inv["work_unit"]
        records = {e["id"]: e for e in E.scan(self.aew_root, work_id)[0]}
        expected_fp = inv["snapshot"]["relevant_inputs_fingerprint"]
        for c in claims:
            for cid in c.get("checks", []):
                ev = records.get(cid)
                if ev is None or ev["kind"] != "check_result" or ev["producer"]["invocation"] != inv_id:
                    raise ValidationFailed(f"claim cites {cid}, which is not a check run by this verifier invocation")
                if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != expected_fp:
                    raise ValidationFailed(
                        f"{cid} evaluated a different snapshot than this verification package; re-run the check")
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

    # ------------------------------------------------------------------ Lead ingest

    def _find_evidence(self, work_id: str, evidence_id: str) -> dict[str, Any]:
        records, problems = E.scan(self.aew_root, work_id)
        if problems:
            raise GateUnsatisfied("evidence integrity problems", problems=problems)
        for ev in records:
            if ev["id"] == evidence_id:
                return ev
        raise NotFound(f"no evidence {evidence_id} for {work_id}")

    def _require_bound_report(self, state: dict[str, Any], unit: dict[str, Any], ev: dict[str, Any], *,
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
                    "integration_attempt"), "current": integ.get("workspace_id"), "current_attempt": integ.get("attempt")}
        else:
            ws = unit.get("workspace") or {}
            if (inv.get("scope") or "ticket") != "ticket" or inv.get("workspace") != ws.get("path"):
                problems["workspace"] = {"report_for": inv.get("workspace_id") or inv.get("workspace"),
                                         "current": ws.get("id")}
        if problems:
            raise GateUnsatisfied(
                f"{ev['id']} was produced for a different plan, attempt or candidate than the one being accepted; "
                "it remains in history, but the current work needs its own report", **problems)

    def review_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "review.ingest") as ctx:
            state = ctx.state
            unit = self.unit(state, work_id)
            if unit["state"] != "REVIEW_PENDING":
                raise IllegalTransition(f"{work_id} is {unit['state']}, not REVIEW_PENDING")
            ev = self._find_evidence(work_id, evidence_id)
            inv = state["invocations"][ev["producer"]["invocation"]]
            if ev["kind"] != "review" or inv["role"] not in REVIEW_ROLES or inv["work_unit"] != work_id:
                raise IllegalTransition(f"{evidence_id} is not a review of {work_id}")
            if ev["producer"]["invocation"] == unit.get("implementer_invocation"):
                raise GateUnsatisfied("a review must come from an invocation independent of the implementer")
            gc = self.gate_context(state, work_id)
            current = (gc["snapshot"] or {}).get("relevant_inputs_fingerprint")
            if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != current:
                raise GateUnsatisfied("review evaluated a snapshot that is no longer current (stale)",
                                      reviewed=ev["evaluated_snapshot"]["relevant_inputs_fingerprint"], current=current)
            self._require_bound_report(state, unit, ev, scope="ticket")
            findings = unit.setdefault("findings", [])
            known = {f["id"] for f in findings}
            for rid in ev["review"].get("resolved_findings", []):
                target = next((f for f in findings if f["id"] == rid), None)
                if target is None:
                    raise ValidationFailed(f"review resolves unknown finding {rid}")
                target.update(status="resolved", resolved_by=evidence_id)
            for f in ev["review"]["findings"]:
                fid = f"{evidence_id}#{f['id']}"
                if fid not in known:
                    findings.append({"id": fid, "severity": f["severity"], "summary": f["summary"],
                                     "location": f.get("location"), "required": f["required"],
                                     "status": "open" if f["required"] else "noted", "source": evidence_id})
            self._ingest_ref(unit, ev)
            self._complete_invocation(state, ev["producer"]["invocation"])
            open_required = G.open_required_findings(unit)
            gc = self.gate_context(state, work_id)
            pending = G.unmet(gc["gates"], self._review_gates(gc))
            if ev["review"]["disposition"] != "pass" or open_required:
                to = "REVIEW_FAILED"
            elif pending:
                to = None  # other required reviews (triggered/inherited) still outstanding
            else:
                to = "REVIEW_PASSED"
            change = None
            if to:
                transitions.check(unit["state"], to, "review.ingest")
                change = self._set_state(unit, to, f"review {evidence_id}: {ev['review']['disposition']}",
                                         state=state)
            ctx.refs.append(ev["_path"])
            ctx.summary = f"{work_id} review {evidence_id} ingested" + (f" -> {to}" if to else " (reviews pending)")
            self.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "transition": change, "pending_reviews": pending,
                "open_required_findings": [f["id"] for f in open_required],
                "revision": ctx.session.committed_revision}

    def verify_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "verify.ingest") as ctx:
            state = ctx.state
            unit = self.unit(state, work_id)
            ev = self._find_evidence(work_id, evidence_id)
            inv = state["invocations"][ev["producer"]["invocation"]]
            if ev["kind"] != "verification" or inv["role"] != "verifier" or inv["work_unit"] != work_id:
                raise IllegalTransition(f"{evidence_id} is not a verification of {work_id}")
            scope = ev["verification"]["scope"]
            if scope == "ticket":
                if unit["state"] != "VERIFY_PENDING":
                    raise IllegalTransition(f"{work_id} is {unit['state']}, not VERIFY_PENDING")
                current = (self.current_snapshot(unit) or {}).get("relevant_inputs_fingerprint")
            else:
                integ = unit.get("integration") or {}
                if unit["state"] != "COMMIT_READY" or integ.get("status") != "prepared":
                    raise IllegalTransition(f"{work_id} has no prepared integration candidate")
                self._require_current_binding(unit)
                current = self.snapshot_of(integ["workspace"], integ["workspace_id"])["relevant_inputs_fingerprint"]
            if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != current:
                raise GateUnsatisfied("verification evaluated a snapshot that is no longer current (stale)",
                                      verified=ev["evaluated_snapshot"]["relevant_inputs_fingerprint"], current=current)
            self._require_bound_report(state, unit, ev, scope=scope)
            self._ingest_ref(unit, ev)
            self._complete_invocation(state, ev["producer"]["invocation"])
            result = ev["result"]
            unit["last_verification"] = {"evidence": evidence_id, "result": result, "scope": scope}
            change = None
            pending: dict[str, str] = {}
            if scope == "ticket":
                # The Verifier's result determines the state mechanically (ambiguity report B1, B2).
                to = {"pass": "VERIFIED", "fail": "VERIFICATION_FAILED"}.get(result, "VERIFICATION_INCONCLUSIVE")
                if to == "VERIFIED":
                    gc = self.gate_context(state, work_id)
                    pending = G.unmet(gc["gates"], self._verification_gates(gc))
                    if pending:
                        to = None  # other planned verifier cards are still outstanding
                if to:
                    transitions.check(unit["state"], to, "verify.ingest")
                    change = self._set_state(unit, to, f"verification {evidence_id}: {result}", state=state)
            elif result == "pass":
                unit["integration"]["status"] = "validated"
                unit["integration"]["post_integration_evidence"] = evidence_id
            elif result == "fail":
                unit["integration"]["status"] = "validation_failed"
                transitions.check(unit["state"], "VERIFICATION_FAILED", "verify.ingest")
                change = self._set_state(unit, "VERIFICATION_FAILED",
                                         f"post-integration verification {evidence_id} failed", state=state)
            else:
                unit["integration"]["status"] = "validation_inconclusive"
            ctx.refs.append(ev["_path"])
            ctx.summary = f"{work_id} verification {evidence_id} ({scope}) ingested: {result}"
            self.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "scope": scope, "result": result, "transition": change,
                "pending_verifications": pending, "revision": ctx.session.committed_revision}

    def verify_classify(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                        reason: str) -> dict[str, Any]:
        if classification not in transitions.VERIFICATION_CLASSIFICATIONS:
            raise UsageError(f"classification must be one of {sorted(transitions.VERIFICATION_CLASSIFICATIONS)}")
        if not (reason and reason.strip()):
            raise UsageError("a classification needs a reason")
        with self.lead_txn(token, expect_rev, "verify.classify", reason=reason) as ctx:
            unit = self.unit(ctx.state, work_id)
            if unit["state"] != "VERIFICATION_FAILED":
                raise IllegalTransition(f"{work_id} is {unit['state']}; only VERIFICATION_FAILED is classified")
            to = transitions.VERIFICATION_CLASSIFICATIONS[classification]
            transitions.check("VERIFICATION_FAILED", to, "verify.classify")
            failing = (unit.get("last_verification") or {}).get("evidence")
            change = {"from": "VERIFICATION_FAILED", "to": to}
            decision = self.new_decision(
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
            self._set_state(unit, to, f"{classification}: {reason}", state=ctx.state)
            ctx.summary = f"{work_id} classified {classification} -> {to} ({decision})"
            self.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "classification": classification, "to": to, "decision": decision,
                "revision": ctx.session.committed_revision}

    # ------------------------------------------------------------------ waivers (policy-bounded)

    def waive(self, *, token: str, expect_rev: int, work_id: str, reason: str, gate: str | None = None,
              finding: str | None = None) -> dict[str, Any]:
        if bool(gate) == bool(finding):
            raise UsageError("waive exactly one gate or one finding")
        with self.lead_txn(token, expect_rev, "waive", reason=reason) as ctx:
            unit = self.unit(ctx.state, work_id)
            policy = self.policy("gates")
            if gate:
                gc = self.gate_context(ctx.state, work_id)
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
            decision = self.new_decision(ctx, "waiver", f"waived {gate or finding} on {work_id}", work_unit=work_id,
                                         reason=reason)
            unit.setdefault("waivers", []).append({"gate": gate, "finding": finding, "decision": decision})
            ctx.summary = f"{work_id}: waived {gate or finding}"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}
