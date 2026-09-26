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
from aew.engine.context_ops import ContextOps
from aew.errors import GateUnsatisfied, IllegalTransition, IntegrityError, StaleCandidate
from aew.knowledge import evidence as E
from aew.policy import guardrails as GR
from aew.util import render_frontmatter, utc_now
from aew.workspace import git, worktrees
from aew.workspace import integration as I


# An integration record is "open" until it is published or retired; each belongs to one COMMIT_READY.
OPEN_INTEGRATION = frozenset({"prepared", "validated", "validation_inconclusive", "validation_failed", "conflict",
                              "stale_candidate", "discarded"})
# States a Ticket may enter while keeping its open integration record: still at (or interrupted in, or
# awaiting classification of a post-integration failure for) the COMMIT_READY the candidate was built from.
KEEPS_INTEGRATION = frozenset({"COMMIT_READY", "DONE", "INTERRUPTED", "VERIFICATION_FAILED"})


class IntegrationOps(ContextOps):
    def _ref(self) -> str:
        return f"refs/heads/{self.authoritative_branch}"

    # ------------------------------------------------------------------ candidate lifecycle (review B1)

    def _before_state_change(self, unit: dict[str, Any], change: dict[str, str]) -> None:
        super()._before_state_change(unit, change)
        if (unit.get("integration") or {}).get("status") == "publishing" and change["to"] != "DONE":
            raise IllegalTransition(
                "a publish of this Ticket's integration candidate is in progress; run `aew integrate reconcile` "
                "before changing its state", from_state=change["from"], to_state=change["to"])

    def _after_state_change(self, state: dict[str, Any], unit: dict[str, Any], change: dict[str, str],
                            reason: str | None) -> None:
        super()._after_state_change(state, unit, change, reason)
        if change["to"] not in KEEPS_INTEGRATION and (unit.get("integration") or {}).get("status") in OPEN_INTEGRATION:
            self._retire_integration(state, unit, f"Ticket left COMMIT_READY ({change['from']} -> {change['to']})"
                                     + (f": {reason}" if reason else ""))

    def _retire_integration(self, state: dict[str, Any], unit: dict[str, Any], why: str) -> None:
        """Move the open candidate to history: it can never be published for a later acceptance.

        Retirement also ends the write authority of every invocation dispatched for the candidate
        (re-review M2); their reports stay durable history but can no longer be written or accepted.
        """
        record = dict(unit["integration"])
        if record.get("status") in OPEN_INTEGRATION - {"validation_failed", "discarded"}:
            record["status"] = "superseded"
        record["retired"] = {"at": utc_now(), "reason": why}
        for inv_id in unit.get("invocations", []):
            inv = state["invocations"].get(inv_id) or {}
            if inv.get("status") == "active" and inv.get("scope") == "integration":
                self._complete_invocation(state, inv_id, "cancelled")
        unit.setdefault("integration_history", []).append(record)
        unit["integration"] = None

    def _prune_retired_candidates(self, unit: dict[str, Any]) -> None:
        """Remove integration worktrees of retired candidates (never one referenced by an open record)."""
        live = (unit.get("integration") or {}).get("workspace")
        for record in unit.get("integration_history", []):
            path = record.get("workspace")
            if path and path != live and Path(path).exists():
                worktrees.remove(self.repo_root, path)

    # ------------------------------------------------------------------ prepare

    def integrate_prepare(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        conflict: dict[str, Any] | None = None
        with self.lead_txn(token, expect_rev, "integrate.prepare") as ctx:
            state = ctx.state
            unit = self.unit(state, work_id)
            if unit["state"] != "COMMIT_READY":
                raise IllegalTransition(f"{work_id} is {unit['state']}; only COMMIT_READY candidates are integrated")
            if not unit.get("mutating"):
                raise IllegalTransition(f"{work_id} is a non-mutating (evidence-only) Ticket; it never integrates source")
            integ = unit.get("integration") or {}
            if integ.get("status") == "publishing":
                raise IllegalTransition(f"{work_id} is publishing; run `aew integrate reconcile`")
            if integ.get("status") in {"prepared", "validated"} and self.binding_problem(unit) is None:
                raise IllegalTransition(f"{work_id} already has an integration in state {integ['status']}")
            if integ:
                self._retire_integration(state, unit, f"replaced by a new candidate (was {integ.get('status')})")
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
            attempt = 1 + max([r.get("attempt", 0) for r in unit.get("integration_history", [])], default=0)
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
                      "workspace": int_ws["path"], "workspace_id": int_ws["workspace_id"], "prepared_at": utc_now(),
                      "binding": self.integration_binding(unit)}
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
        self._prune_retired_candidates(unit)
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
        self._require_bound_validation(state, work_id, unit)

    def _require_obligations_at_acceptance(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> None:
        """Every effective obligation — including any added after validation — is met at the accepted snapshot."""
        gc = self.accepted_gate_context(state, work_id)
        self._require_gates(gc, gc["obligations"]["gates"], what="publication")
        if gc["open_required_findings"]:
            raise GateUnsatisfied("publication: mandatory review findings are unresolved and not waived",
                                  findings=[f["id"] for f in gc["open_required_findings"]])

    def _publication_blocker(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> GateUnsatisfied | None:
        try:
            self._require_obligations_at_acceptance(state, work_id, unit)
            self._require_bound_validation(state, work_id, unit)
        except GateUnsatisfied as exc:
            return exc
        return None

    def _require_bound_validation(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> None:
        """The recorded post-integration report passed for THIS candidate, under its plan (re-review R1)."""
        policy = self.policy("gates")["post_integration"]
        if not policy["verification"] and not policy["checks"]:
            return
        integ = unit["integration"]
        fp = integ["candidate_snapshot"]["relevant_inputs_fingerprint"]
        evidence = {e["id"]: e for e in E.scan(self.aew_root, work_id)[0]}
        ver = evidence.get(integ.get("post_integration_evidence") or "")
        if ver is None or ver["evaluated_snapshot"]["relevant_inputs_fingerprint"] != fp or ver["result"] != "pass":
            raise GateUnsatisfied("post-integration verification is not bound to the integrated snapshot")
        self._require_bound_report(state, unit, ver, scope="integration")
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
            superseded = self.binding_problem(unit)
            current = self.authoritative_commit()
            if superseded:
                self._retire_integration(ctx.state, unit, "bound to an earlier COMMIT_READY or plan")
                stale = {"reason": "candidate built from an earlier COMMIT_READY or plan", **superseded}
                ctx.op = "integrate.superseded"
                ctx.summary = f"{work_id} candidate superseded (bound to an earlier COMMIT_READY)"
            elif current != integ["base"]:
                integ["status"] = "stale_candidate"
                stale = {"expected": integ["base"], "current": current}
                ctx.summary = f"{work_id} candidate stale: authoritative ref moved"
            else:
                self._require_obligations_at_acceptance(ctx.state, work_id, unit)
                self._post_integration_ok(ctx.state, work_id, unit)
                if I.authoritative_worktree_applies(self.repo_root, self.authoritative_branch):
                    I.precheck_sync(self.repo_root, integ["base"], integ["changed_paths"])
                integ["status"] = "publishing"
                integ["publishing_at"] = utc_now()
                ctx.summary = f"{work_id} publishing {integ['candidate'][:12]} over {integ['base'][:12]}"
        if stale:
            what = ("the integration candidate was built from an earlier COMMIT_READY or plan; run `aew integrate "
                    "prepare` again" if "reason" in stale else
                    "the authoritative ref moved since the candidate was built; rebuild and revalidate")
            raise StaleCandidate(what, **stale)
        faults.hit("integrate.after_publishing_record")
        return self._finish_publish(token, ctx.session.committed_revision, work_id)

    def _finish_publish(self, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        """CAS, worktree sync and DONE as ONE Lead transaction (review 2026-09-26 M1).

        Authority, the expected control revision and the manifest pin are all verified under the
        control-state lock *before* any ref or worktree side effect, and the lock is held until DONE
        commits. A rejected call therefore never moves the ref, and no other writer can interleave
        between publication and completion. A crash at any fault point leaves ``publishing`` for
        ``integrate reconcile``; a refused sync aborts the transaction, so nothing is overwritten.
        """
        stale: StaleCandidate | None = None
        withdrawn: GateUnsatisfied | None = None
        with self.lead_txn(token, expect_rev, "integrate.publish") as ctx:
            unit = self.unit(ctx.state, work_id)
            integ = unit.get("integration") or {}
            if integ.get("status") != "publishing":
                raise IllegalTransition(f"{work_id} is not publishing (integration {integ.get('status')})")
            ref, base, candidate = self._ref(), integ["base"], integ["candidate"]
            applies = I.authoritative_worktree_applies(self.repo_root, self.authoritative_branch)
            current = git.rev_parse(ref, cwd=self.repo_root)
            cas = "already_published"
            mismatch = self.binding_problem(unit)
            if mismatch and current != base:
                raise IntegrityError("CONTRADICTION: the published candidate is not bound to the Ticket's current "
                                     "COMMIT_READY acceptance; operator inspection required", ref=ref, **mismatch)
            if mismatch:
                self._retire_integration(ctx.state, unit,
                                         "bound to an earlier COMMIT_READY or plan (found at finalization)")
                stale = StaleCandidate("the integration candidate was built from an earlier COMMIT_READY or plan; "
                                       "run `aew integrate prepare` again", **mismatch)
            elif current == base:
                withdrawn = self._publication_blocker(ctx.state, work_id, unit)
                if withdrawn:
                    # Nothing was published (the ref is still H): withdraw the intent so the Lead can act on
                    # the unmet obligation instead of being held in `publishing`.
                    integ["status"] = "validated"
                    integ.pop("publishing_at", None)
                    ctx.op = "integrate.withdrawn"
                    ctx.summary = f"{work_id} publish withdrawn: {withdrawn.message}"
                else:
                    if applies:
                        I.precheck_sync(self.repo_root, base, integ["changed_paths"])
                    try:
                        I.cas_publish(self.repo_root, ref, candidate, base, f"aew: integrate {work_id}")
                        cas = "published"
                    except StaleCandidate as exc:
                        stale = exc
            elif current is None or not git.is_ancestor(candidate, current, cwd=self.repo_root):
                stale = StaleCandidate("the authoritative ref no longer contains the candidate", current=current)
            if stale:
                if unit.get("integration") is not None:
                    integ["status"] = "stale_candidate"
                ctx.op = "integrate.stale"
                ctx.summary = f"{work_id} candidate stale"
            elif withdrawn:
                pass
            else:
                faults.hit("integrate.after_cas")
                sync: dict[str, Any] = {"status": "not_applicable (authoritative branch not checked out here)"}
                if applies:
                    try:
                        sync = I.sync_worktree(self.repo_root, base, candidate, integ["changed_paths"],
                                               on_first=lambda: faults.hit("integrate.mid_sync"))
                    except IntegrityError as exc:
                        raise IntegrityError(
                            f"{candidate[:12]} is published on {ref}, but the authoritative worktree holds local "
                            f"work on paths it changes; nothing was overwritten. {exc.message}",
                            published=candidate, ref=ref, **exc.details) from None
                    sync["status"] = "synced"
                faults.hit("integrate.before_done")
                transitions.check(unit["state"], "DONE", "integrate.publish")
                integ.update(status="integrated", commit=candidate, integrated_at=utc_now(), cas=cas,
                             worktree_sync=sync)
                completion = self._completion_record(ctx.state, work_id, unit)
                ctx.session.write(f"work/{work_id}/completion.md", completion)
                ctx.refs.append(f"work/{work_id}/completion.md")
                unit["completion_record"] = f"work/{work_id}/completion.md"
                self._set_state(unit, "DONE", f"integrated as {candidate[:12]}; post-integration verification passed",
                                state=ctx.state)
                remove_ticket_workspace = self._settle_ticket_workspace(unit, integ["ticket_commit"])
                ctx.summary = f"{work_id} DONE: integrated {candidate[:12]} into {self.authoritative_branch}"
                self.before_commit(ctx)
        if stale:
            raise stale
        if withdrawn:
            raise withdrawn
        worktrees.remove(self.repo_root, integ["workspace"])
        self._prune_retired_candidates(unit)
        if remove_ticket_workspace:
            worktrees.remove(self.repo_root, unit["workspace"]["path"])
        return {"ok": True, "work_id": work_id, "state": "DONE", "integrated_commit": candidate, "cas": cas,
                "worktree_sync": sync, "revision": ctx.session.committed_revision}

    @staticmethod
    def _settle_ticket_workspace(unit: dict[str, Any], ticket_commit: str) -> bool:
        """At DONE: the Ticket workspace is removable only if it holds exactly the integrated commit.

        ``worktrees.inspect`` compares HEAD with both the working content (index flags neutralized, never
        ``git status``) and the index as staged; if either differs, or cannot be verified, the workspace is
        retained and reported as a contradiction. Integration cleanup never deletes newer engineering
        output — working, flag-hidden or staged-only (review B1, re-review, foundation review).
        """
        ws = unit.get("workspace")
        if not ws:
            return False
        found = worktrees.inspect(ws["path"], ws.get("base_commit"))
        if not found.get("exists"):
            ws["status"] = "integrated"
            return False
        if found["head"] == ticket_commit and found["dirty"] is False:
            ws["status"] = "integrated"
            return True
        ws["status"] = ("retained (content could not be verified)" if found["dirty"] is None
                        else "retained (differs from integrated commit)")
        ws["retained"] = {"head": found["head"], "dirty": found["dirty"], "staged": found.get("staged"),
                          "integrated_ticket_commit": ticket_commit,
                          **({"reason": found["dirty_unknown"]} if found.get("dirty_unknown") else {})}
        return False

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
