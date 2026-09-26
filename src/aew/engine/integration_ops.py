"""Lead-controlled integration: prepare -> post-integration verification -> publish (CAS) -> DONE.

WC §8, §8.1, §13; decision D-op-2 (validate, then publish); plan review §2 (atomic CAS).

A mutating Ticket reaches DONE only when its accepted output is in the
authoritative lineage *and* the required post-integration verification passed
for the integrated snapshot. The authoritative ref is the single publication
point and only moves by compare-and-swap from the commit the candidate was
built on. Each phase is recorded in control state, so a crash anywhere can be
reconciled by inspecting git — success is never inferred.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine import faults, transitions
from aew.engine.authority import require_lead
from aew.engine.context_ops import ContextOps
from aew.engine.store import Transition
from aew.errors import GateUnsatisfied, IllegalTransition, IntegrityError, StaleCandidate
from aew.knowledge import evidence as E
from aew.policy import guardrails as GR
from aew.util import render_frontmatter, utc_now
from aew.workspace import git, worktrees
from aew.workspace import integration as I


class IntegrationOps(ContextOps):
    def _ref(self) -> str:
        return f"refs/heads/{self.authoritative_branch}"

    # ------------------------------------------------------------------ prepare

    def integrate_prepare(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        conflict: dict[str, Any] | None = None
        with self.lead_txn(token, expect_rev, "integrate.prepare") as ctx:
            state = ctx.state
            unit = self.unit(state, work_id)
            if unit["state"] != "COMMIT_READY":
                raise IllegalTransition(f"{work_id} is {unit['state']}; only COMMIT_READY candidates are integrated")
            integ = unit.get("integration") or {}
            if integ.get("status") in {"prepared", "validated", "publishing"}:
                raise IllegalTransition(f"{work_id} already has an integration in state {integ['status']}")
            gc = self.gate_context(state, work_id)
            self._require_gates(gc, gc["obligations"]["gates"], what="integration")
            if gc["open_required_findings"]:
                raise GateUnsatisfied("mandatory review findings are unresolved")
            gated = (unit.get("commit_ready_snapshot") or {}).get("relevant_inputs_fingerprint")
            current = gc["snapshot"]["relevant_inputs_fingerprint"]
            if gated != current:
                raise GateUnsatisfied("the workspace changed after COMMIT_READY; return it to RUNNING and revalidate",
                                      gated=gated, current=current)
            ws = unit["workspace"]
            ws_path = Path(ws["path"])
            ticket_commit = I.commit_workspace(ws_path, f"aew({work_id}): {unit['title']}")
            committed = self.snapshot_of(ws_path, ws["id"])["relevant_inputs_fingerprint"]
            if committed != gated:
                raise IntegrityError("committed tree differs from the gated evaluated snapshot",
                                     gated=gated, committed=committed)
            base = self.authoritative_commit()
            attempt = integ.get("attempt", 0) + 1
            name = f"{work_id}-int-{attempt}"
            referenced = {u["integration"]["workspace"] for u in state["work"].values()
                          if (u.get("integration") or {}).get("status") in {"prepared", "validated", "publishing"}}
            int_ws = worktrees.allocate_detached(
                repo_root=self.repo_root, aew_root=self.aew_root, workspaces_root=self.workspaces_root(),
                work_id=work_id, name=name, workspace_id=f"int-{work_id}-{attempt}", commit=base,
                referenced_paths=referenced)
            merged = I.merge_candidate(self.repo_root, Path(int_ws["path"]), ticket_commit,
                                       f"aew: integrate {work_id} ({unit['title']})")
            record = {"attempt": attempt, "base": base, "ticket_commit": ticket_commit,
                      "workspace": int_ws["path"], "workspace_id": int_ws["workspace_id"], "prepared_at": utc_now()}
            if merged["conflict"]:
                worktrees.remove(self.repo_root, int_ws["path"])
                conflict = {"paths": merged["paths"]}
                unit["integration"] = {**record, "status": "conflict", "conflict_paths": merged["paths"]}
                ctx.summary = f"{work_id} integration conflict on {merged['paths']}"
            else:
                candidate = merged["commit"]
                changed = I.changed_between(self.repo_root, base, candidate)
                verdict = GR.evaluate(changed, self.policy("guardrails"), [])
                protected = [v for v in verdict["violations"] if v["rule"] != "outside_ticket_scope"]
                if protected:
                    worktrees.remove(self.repo_root, int_ws["path"])
                    raise GateUnsatisfied("the integrated change touches protected paths", violations=protected)
                snap = self.snapshot_of(int_ws["path"], int_ws["workspace_id"])
                unit["integration"] = {**record, "status": "prepared", "candidate": candidate,
                                       "candidate_snapshot": snap, "changed_paths": changed}
                ctx.summary = f"{work_id} integration candidate {candidate[:12]} prepared on {base[:12]}"
            self.before_commit(ctx)
        result = {"ok": conflict is None, "work_id": work_id, "integration": unit["integration"],
                  "revision": ctx.session.committed_revision}
        if conflict:
            result["next"] = "resolve by returning the Ticket to RUNNING (rebase) or REPLAN_REQUIRED"
        return result

    # ------------------------------------------------------------------ publish

    def _post_integration_ok(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> None:
        policy = self.policy("gates")["post_integration"]
        integ = unit["integration"]
        fp = integ["candidate_snapshot"]["relevant_inputs_fingerprint"]
        now = self.snapshot_of(integ["workspace"], integ["workspace_id"])["relevant_inputs_fingerprint"]
        if now != fp:
            raise GateUnsatisfied("the integration candidate changed after it was prepared", prepared=fp, current=now)
        if not policy["verification"] and not policy["checks"]:
            return
        if integ.get("status") != "validated":
            raise GateUnsatisfied("post-integration verification has not passed for the integrated snapshot",
                                  status=integ.get("status"))
        evidence = {e["id"]: e for e in E.scan(self.aew_root, work_id)[0]}
        ver = evidence.get(integ.get("post_integration_evidence") or "")
        if ver is None or ver["evaluated_snapshot"]["relevant_inputs_fingerprint"] != fp or ver["result"] != "pass":
            raise GateUnsatisfied("post-integration verification is not bound to the integrated snapshot")
        cited = {cid for c in ver["verification"]["claims"] for cid in c.get("checks", [])}
        passed = {evidence[c]["check"]["check_id"] for c in cited
                  if c in evidence and evidence[c]["result"] == "pass"
                  and evidence[c]["evaluated_snapshot"]["relevant_inputs_fingerprint"] == fp}
        missing = [c for c in policy["checks"] if c not in passed]
        if missing:
            raise GateUnsatisfied("policy-required post-integration checks are missing", missing=missing)

    def integrate_publish(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        # Phase 1: record intent (publishing H -> M) after re-validating everything.
        stale = None
        with self.lead_txn(token, expect_rev, "integrate.publishing") as ctx:
            unit = self.unit(ctx.state, work_id)
            integ = unit.get("integration") or {}
            if unit["state"] != "COMMIT_READY" or integ.get("status") not in {"prepared", "validated"}:
                raise IllegalTransition(f"{work_id} has no validated integration candidate to publish",
                                        state=unit["state"], integration=integ.get("status"))
            self._post_integration_ok(ctx.state, work_id, unit)
            current = self.authoritative_commit()
            if current != integ["base"]:
                integ["status"] = "stale_candidate"
                stale = {"expected": integ["base"], "current": current}
                ctx.summary = f"{work_id} candidate stale: authoritative ref moved"
            else:
                if I.authoritative_worktree_applies(self.repo_root, self.authoritative_branch):
                    I.precheck_sync(self.repo_root, integ["base"], integ["changed_paths"])
                integ["status"] = "publishing"
                integ["publishing_at"] = utc_now()
                ctx.summary = f"{work_id} publishing {integ['candidate'][:12]} over {integ['base'][:12]}"
        if stale:
            raise StaleCandidate("the authoritative ref moved since the candidate was built; rebuild and revalidate",
                                 **stale)
        faults.hit("integrate.after_publishing_record")
        return self._finish_publish(token, ctx.session.committed_revision, work_id)

    def _finish_publish(self, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        # The compare-and-swap happens under the control-state lock with authority re-verified, so a
        # Lead takeover and a publish strictly serialize: a superseded Lead can never move the ref.
        stale = None
        with self.store.session() as s:
            actor = require_lead(s.state, token)
            unit = self.unit(s.state, work_id)
            integ = unit["integration"]
            if integ.get("status") != "publishing":
                raise IllegalTransition(f"{work_id} is not publishing (integration {integ.get('status')})")
            ref, base, candidate = self._ref(), integ["base"], integ["candidate"]
            current = git.rev_parse(ref, cwd=self.repo_root)
            cas = "already_published"
            if current == base:
                try:
                    I.cas_publish(self.repo_root, ref, candidate, base, f"aew: integrate {work_id}")
                    cas = "published"
                except StaleCandidate as exc:
                    stale = exc
            elif current is None or not git.is_ancestor(candidate, current, cwd=self.repo_root):
                stale = StaleCandidate("the authoritative ref no longer contains the candidate", current=current)
            if stale:
                integ["status"] = "stale_candidate"
                s.commit(Transition(op="integrate.stale", actor=actor, summary=f"{work_id} candidate stale"),
                         expect_rev=expect_rev)
        if stale:
            raise stale
        faults.hit("integrate.after_cas")
        sync = {"status": "not_applicable (authoritative branch not checked out here)"}
        if I.authoritative_worktree_applies(self.repo_root, self.authoritative_branch):
            sync = I.sync_worktree(self.repo_root, base, candidate, integ["changed_paths"],
                                   on_first=lambda: faults.hit("integrate.mid_sync"))
            sync["status"] = "synced"
        faults.hit("integrate.before_done")
        # Phase 2: DONE, with the integration record and completion record.
        with self.lead_txn(token, expect_rev, "integrate.publish") as ctx:
            unit = self.unit(ctx.state, work_id)
            transitions.check(unit["state"], "DONE", "integrate.publish")
            integ = unit["integration"]
            integ.update(status="integrated", commit=candidate, integrated_at=utc_now(), cas=cas, worktree_sync=sync)
            completion = self._completion_record(ctx.state, work_id, unit)
            ctx.session.write(f"work/{work_id}/completion.md", completion)
            ctx.refs.append(f"work/{work_id}/completion.md")
            unit["completion_record"] = f"work/{work_id}/completion.md"
            self._set_state(unit, "DONE", f"integrated as {candidate[:12]}; post-integration verification passed")
            if unit.get("workspace"):
                unit["workspace"]["status"] = "integrated"
            ctx.summary = f"{work_id} DONE: integrated {candidate[:12]} into {self.authoritative_branch}"
            self.before_commit(ctx)
        for path in (integ["workspace"], (unit.get("workspace") or {}).get("path")):
            if path:
                worktrees.remove(self.repo_root, path)
        return {"ok": True, "work_id": work_id, "state": "DONE", "integrated_commit": candidate, "cas": cas,
                "worktree_sync": sync, "revision": ctx.session.committed_revision}

    def _completion_record(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> str:
        integ = unit["integration"]
        plan = unit.get("plan") or {}
        meta = {
            "schema": "aew/completion/v1",
            "work_unit": work_id,
            "at": utc_now(),
            "plan": {"revision": plan.get("accepted"), "sha256": plan.get("sha256")},
            "base_commit": integ["base"],
            "ticket_commit": integ["ticket_commit"],
            "integrated_commit": integ["candidate"],
            "gated_snapshot": (unit.get("commit_ready_snapshot") or {}).get("relevant_inputs_fingerprint"),
            "integrated_snapshot": integ["candidate_snapshot"]["relevant_inputs_fingerprint"],
            "post_integration_evidence": integ.get("post_integration_evidence"),
            "evidence": [{"id": e["id"], "kind": e["kind"], "result": e["result"], "sha256": e["sha256"]}
                         for e in unit.get("evidence", [])],
            "classifications": unit.get("classifications", []),
            "waivers": unit.get("waivers", []),
        }
        body = (f"# Completion — {work_id}: {unit['title']}\n\n"
                f"Accepted by the Lead after independent review, goal-backwards and contract verification, "
                f"controlled integration into `{self.authoritative_branch}` and post-integration verification "
                f"of the integrated snapshot.\n")
        return render_frontmatter(meta, body)

    # ------------------------------------------------------------------ reconcile

    def integrate_reconcile(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        """Resume an interrupted publish by inspecting git: CAS pending, already done, or stale."""
        return self._finish_publish(token, expect_rev, work_id)
