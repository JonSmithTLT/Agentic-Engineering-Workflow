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
from typing import TYPE_CHECKING, Any

from aew.engine import faults, transitions
from aew.engine import queue_ops as Q
from aew.engine.dispatch import GuardRegistration as DispatchGuard
from aew.engine.dispatch import checked
from aew.errors import (
    GateUnsatisfied,
    GitError,
    IllegalTransition,
    IntegrityError,
    LeaseNotHeld,
    LeaseReconcileRequired,
    StaleCandidate,
)
from aew.knowledge import evidence as E
from aew.policy import checks as C
from aew.policy import guardrails as GR
from aew.util import render_frontmatter, utc_now
from aew.workspace import git, worktrees
from aew.workspace import integration as I

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import DispatchPort, GatesPort, InvocationsPort, QueuePort, WorkUnitsPort


# An integration record is "open" until it is published or retired; each belongs to one COMMIT_READY.
OPEN_INTEGRATION = frozenset({"prepared", "validated", "validation_inconclusive", "validation_failed", "conflict",
                              "stale_candidate", "discarded"})
# The default most paths one candidate may change (gates.yaml `max_publish_paths`; register E34). A publish syncs each
# changed path into the authoritative checkout under the control lock, measured at about 4.5 to 5.5 ms a path on the
# Windows reference machine (tools/perf/publish_sync.py), so 2,000 paths keep the hold near 10 s, well inside the
# 31 s other writers wait for the lock.
MAX_PUBLISH_PATHS = 2000
# States a Ticket may enter while keeping its open integration record: still at (or interrupted in, or
# awaiting classification of a post-integration failure for) the COMMIT_READY the candidate was built from.
KEEPS_INTEGRATION = frozenset({"COMMIT_READY", "DONE", "INTERRUPTED", "VERIFICATION_FAILED"})


class Integration:
    """Lead-controlled integration: prepare -> post-integration verification -> publish (CAS) -> DONE."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, invocations: InvocationsPort, gates: GatesPort,
                 dispatch: DispatchPort, queue: QueuePort) -> None:
        self.k = k
        self.units = units
        self.invocations = invocations
        self.gates = gates
        self.dispatch = dispatch
        self.queue = queue

    def _ref(self) -> str:
        return f"refs/heads/{self.k.authoritative_branch}"

    def before_state_change(self, unit: dict[str, Any], change: dict[str, str]) -> None:
        """State hook: no state change while a publish of the Ticket's candidate is in progress."""
        if (unit.get("integration") or {}).get("status") == "publishing" and change["to"] != "DONE":
            raise IllegalTransition(
                "a publish of this Ticket's integration candidate is in progress; run `aew integrate reconcile` "
                "before changing its state", from_state=change["from"], to_state=change["to"])

    def on_state_change(self, state: dict[str, Any], unit: dict[str, Any], change: dict[str, str],
                        reason: str | None) -> None:
        """State hook: a Ticket leaving COMMIT_READY retires its open integration candidate (review B1)."""
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
                self.invocations.complete_invocation(state, inv_id, "cancelled")
        unit.setdefault("integration_history", []).append(record)
        unit["integration"] = None

    def _prune_retired_candidates(self, unit: dict[str, Any]) -> None:
        """Remove integration worktrees of retired candidates (never one referenced by an open record)."""
        live = (unit.get("integration") or {}).get("workspace")
        for record in unit.get("integration_history", []):
            path = record.get("workspace")
            if path and path != live and Path(path).exists():
                worktrees.remove(self.k.repo_root, path)

    # ---- the dispatch guards of ``integrate.prepare`` (M4-D): the checks prepare made before the queue, in order

    def dispatch_guards(self) -> list[DispatchGuard]:
        return [DispatchGuard("integrate.ticket", self._g_ticket), DispatchGuard("integrate.gates", self._g_gates)]

    def _g_ticket(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> Any:
        return checked(lambda: self._require_integrable(state, work_id))

    def _g_gates(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> Any:
        return checked(lambda: self._require_gated(state, work_id))

    def require_legal(self, state: dict[str, Any], work_id: str) -> None:
        """Whether ``work_id``'s integration could be prepared now, apart from the queue (raises when not)."""
        self._require_integrable(state, work_id)
        self._require_gated(state, work_id)

    def _require_integrable(self, state: dict[str, Any], work_id: str) -> None:
        unit = self.units.unit(state, work_id)
        if unit["state"] != "COMMIT_READY":
            raise IllegalTransition(f"{work_id} is {unit['state']}; only COMMIT_READY candidates are integrated")
        if not unit.get("mutating"):
            raise IllegalTransition(f"{work_id} is a non-mutating (evidence-only) Ticket; "
                                    "it never integrates source")
        integ = unit.get("integration") or {}
        if integ.get("status") == "publishing":
            raise IllegalTransition(f"{work_id} is publishing; run `aew integrate reconcile`")
        lost = bool(integ.get("workspace")) and not Path(integ["workspace"]).is_dir()
        # Under the queue, an open candidate is held by its entry's lease. One with no lease was prepared before the
        # queue existed (an upgraded project): prepare replaces it under fresh checks and custody, never adopts it.
        unleased = Q.queued(state) and Q.lease_of(state, work_id) is None
        if (integ.get("status") in {"prepared", "validated"} and self.gates.binding_problem(unit) is None
                and not lost and not unleased):
            raise IllegalTransition(f"{work_id} already has an integration in state {integ['status']}")

    def _require_gated(self, state: dict[str, Any], work_id: str) -> None:
        unit = self.units.unit(state, work_id)
        gc = self.gates.gate_context(state, work_id)
        self.gates.require_gates(gc, gc["obligations"]["gates"], what="integration")
        if gc["open_required_findings"]:
            raise GateUnsatisfied("mandatory review findings are unresolved")
        gated = (unit.get("commit_ready_snapshot") or {}).get("relevant_inputs_fingerprint")
        current = gc["snapshot"]["relevant_inputs_fingerprint"]
        if gated != current:
            raise GateUnsatisfied("the workspace changed after COMMIT_READY; return it to RUNNING and revalidate",
                                  gated=gated, current=current)

    def _admission_refusal(self, unit: dict[str, Any], changed: list[str]) -> GateUnsatisfied | None:
        """Why a merged candidate may not be admitted, or None: the publish path bound (register E34), protected
        paths, and case-only renames this checkout cannot hold."""
        limit = self.k.policy("gates").get("max_publish_paths") or MAX_PUBLISH_PATHS
        if len(changed) > limit:
            return GateUnsatisfied(
                f"the candidate changes {len(changed)} paths, more than the {limit} one publish may sync into "
                "the authoritative checkout while it holds the control lock (gates.yaml `max_publish_paths`): "
                "split the change into smaller Tickets, or raise the limit knowing a larger publish blocks "
                "every other writer for longer", changed=len(changed), limit=limit)
        meta = self.gates.record_meta(unit)
        verdict = GR.evaluate(changed, self.k.policy("guardrails"), list((meta.get("scope") or {}).get(
            "paths") or []), (meta.get("acceptance") or {}).get("inputs"))
        protected = [v for v in verdict["violations"] if v["rule"] != "outside_ticket_scope"]
        if protected:
            return GateUnsatisfied("the integrated change touches protected paths", violations=protected)
        clashes = I.case_only_renames(self.k.repo_root, changed)
        if clashes:
            return GateUnsatisfied(
                "the change renames paths only by letter case, which this checkout's case-insensitive "
                "filesystem cannot hold side by side, so the authoritative worktree could never be synced. "
                "Rename in two steps (to a different name, then to the target), or integrate on a "
                "case-sensitive filesystem", paths=clashes[:50])
        return None

    def integrate_prepare(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        conflict: dict[str, Any] | None = None
        refused: GateUnsatisfied | None = None
        with self.k.lead_txn(token, expect_rev, "integrate.prepare") as ctx:
            state = ctx.state
            self.queue.sync(state)
            # Legality and queue order are the decision's (M4-D); the lease it grants is held by a new custodian.
            decision = self.dispatch.decide_in(ctx, "integrate.prepare", work_id)
            unleased = Q.queued(state) and Q.lease_of(state, work_id) is None
            self.queue.grant(ctx, work_id)
            unit = self.units.unit(state, work_id)
            integ = unit.get("integration") or {}
            if integ:
                lost = bool(integ.get("workspace")) and not Path(integ["workspace"]).is_dir()
                why = ("its integration worktree is gone" if lost
                       else "prepared before the integration queue, so no lease held it; replaced under the queue"
                       if unleased and integ.get("status") in {"prepared", "validated"}
                       else "replaced by a new candidate")
                self._retire_integration(state, unit, f"{why} (was {integ.get('status')})")
            gated = (unit.get("commit_ready_snapshot") or {}).get("relevant_inputs_fingerprint")
            ws = unit["workspace"]
            ws_path = Path(ws["path"])
            ticket_commit = I.commit_workspace(ws_path, f"aew({work_id}): {unit['title']}")
            committed = self.invocations.snapshot_of(ws_path, ws["id"])["relevant_inputs_fingerprint"]
            if committed != gated:
                raise IntegrityError("committed tree differs from the gated evaluated snapshot",
                                     gated=gated, committed=committed)
            base = self.k.authoritative_commit()
            if base is None:
                raise IntegrityError(f"the authoritative branch {self.k.authoritative_branch} has no commit")
            attempt = 1 + max([r.get("attempt", 0) for r in unit.get("integration_history", [])], default=0)
            name = f"{work_id}-int-{attempt}"
            referenced = {u["integration"]["workspace"] for u in state["work"].values()
                          if (u.get("integration") or {}).get("status") in {"prepared", "validated", "publishing"}}
            int_ws = worktrees.allocate_detached(
                repo_root=self.k.repo_root, aew_root=self.k.aew_root, workspaces_root=self.k.workspaces_root(),
                work_id=work_id, name=name, workspace_id=f"int-{work_id}-{attempt}", commit=base,
                referenced_paths=referenced)
            try:
                merged = I.merge_candidate(self.k.repo_root, Path(int_ws["path"]), ticket_commit,
                                           f"aew: integrate {work_id} ({unit['title']})")
            except GitError:
                worktrees.remove(self.k.repo_root, int_ws["path"])
                raise
            record = {"attempt": attempt, "base": base, "ticket_commit": ticket_commit,
                      "workspace": int_ws["path"], "workspace_id": int_ws["workspace_id"], "prepared_at": utc_now(),
                      "binding": self.gates.integration_binding(unit)}
            candidate: str = merged.get("commit") or ""
            changed: list[str] = []
            if merged["conflict"]:
                worktrees.remove(self.k.repo_root, int_ws["path"])
                conflict = {"paths": merged["paths"]}
                unit["integration"] = {**record, "status": "conflict", "conflict_paths": merged["paths"]}
                # A conflict releases the lease and returns the entry to the Lead; it is never auto-resolved.
                self.queue.record_attempt(state, work_id, unit["integration"])
                self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="conflict",
                                   detail={"paths": merged["paths"][:50]})
                ctx.summary = f"{work_id} integration conflict on {merged['paths']}"
            else:
                changed = I.changed_between(self.k.repo_root, base, candidate)
                refused = self._admission_refusal(unit, changed)
                if refused is not None and not Q.queued(state):
                    worktrees.remove(self.k.repo_root, int_ws["path"])
                    raise refused  # v1: no queue entry to hold the refusal, so nothing is committed
            if refused is not None:
                # Like a conflict, a refused candidate is the Lead's to settle: the lease is released and the entry
                # waits for disposition, committed, so it never holds up an independent entry behind it (FIFO).
                worktrees.remove(self.k.repo_root, int_ws["path"])
                self.queue.record_attempt(state, work_id, {**record, "status": "refused"})
                self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="refused",
                                   detail={"code": refused.code, "reason": refused.message})
                ctx.summary = f"{work_id} integration candidate refused at admission: {refused.message}"
            elif not merged["conflict"]:
                snap = self.invocations.snapshot_of(int_ws["path"], int_ws["workspace_id"])
                unit["integration"] = {**record, "status": "prepared", "candidate": candidate,
                                       "candidate_snapshot": snap, "changed_paths": changed}
                self.queue.record_attempt(state, work_id, unit["integration"])
                ctx.summary = f"{work_id} integration candidate {candidate[:12]} prepared on {base[:12]}"
            self.units.before_commit(ctx)
        self._prune_retired_candidates(unit)
        if refused is not None:
            refused.details.update(queue=self._queue_brief(ctx.state, work_id), revision=ctx.session.committed_revision,
                                   next="the entry waits for disposition: change the Ticket (return it to RUNNING, "
                                        "which retires the entry) or the policy, then make it COMMIT_READY again")
            raise refused
        result = {"ok": conflict is None, "work_id": work_id, "integration": unit["integration"],
                  "queue": self._queue_brief(ctx.state, work_id), "dispatch": decision.to_dict(),
                  "revision": ctx.session.committed_revision}
        if conflict:
            result["next"] = "resolve by returning the Ticket to RUNNING (rebase) or REPLAN_REQUIRED"
        return result

    @staticmethod
    def _queue_brief(state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        qid, entry = Q.entry_of(state, work_id)
        if qid is None or entry is None:
            return None
        lease = (state.get("queue") or {}).get("lease")
        return {"entry": qid, "state": entry["state"], "seq": entry["seq"],
                "custodian": lease["custodian"] if lease and lease["entry"] == qid else None}

    def _post_integration_ok(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> None:
        policy = self.k.policy("gates")["post_integration"]
        integ = unit["integration"]
        fp = integ["candidate_snapshot"]["relevant_inputs_fingerprint"]
        if not Path(integ["workspace"]).is_dir():
            raise GateUnsatisfied(f"the integration worktree of {work_id} is gone ({integ['workspace']}); run "
                                  "`aew integrate prepare` to build the candidate again", workspace=integ["workspace"])
        now = self.invocations.snapshot_of(integ["workspace"], integ["workspace_id"])["relevant_inputs_fingerprint"]
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
        gc = self.gates.accepted_gate_context(state, work_id)
        self.gates.require_gates(gc, gc["obligations"]["gates"], what="publication")
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
        policy = self.k.policy("gates")["post_integration"]
        if not policy["verification"] and not policy["checks"]:
            return
        integ = unit["integration"]
        fp = integ["candidate_snapshot"]["relevant_inputs_fingerprint"]
        evidence = {e["id"]: e for e in E.scan(self.k.aew_root, work_id)[0]}
        ver = evidence.get(integ.get("post_integration_evidence") or "")
        if ver is None or ver["evaluated_snapshot"]["relevant_inputs_fingerprint"] != fp or ver["result"] != "pass":
            raise GateUnsatisfied("post-integration verification is not bound to the integrated snapshot")
        self.gates.require_bound_report(state, unit, ver, scope="integration")
        cited = {cid for c in ver["verification"]["claims"] for cid in c.get("checks", [])}
        definitions = C.current_definitions(self.k.policy("checks"), self.k.policy("guardrails"))
        passed = {evidence[c]["check"]["check_id"] for c in cited
                  if c in evidence and evidence[c]["result"] == "pass"
                  and evidence[c]["evaluated_snapshot"]["relevant_inputs_fingerprint"] == fp
                  and C.proves_current_definition(evidence[c], definitions)}  # independent audit I1
        missing = [c for c in policy["checks"] if c not in passed]
        if missing:
            raise GateUnsatisfied("policy-required post-integration checks are missing, or ran under a check "
                                  "definition that policy/checks.yaml has since changed", missing=missing)

    def integrate_publish(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        # Phase 1: record intent (publishing H -> M) after re-validating everything.
        stale = None
        with self.k.lead_txn(token, expect_rev, "integrate.publishing") as ctx:
            unit = self.units.unit(ctx.state, work_id)
            integ = unit.get("integration") or {}
            if unit["state"] != "COMMIT_READY" or integ.get("status") not in {"prepared", "validated"}:
                raise IllegalTransition(f"{work_id} has no validated integration candidate to publish",
                                        state=unit["state"], integration=integ.get("status"))
            self.queue.sync(ctx.state)
            self.queue.require_live_lease(ctx.state, work_id, "publishing")
            superseded = self.gates.binding_problem(unit)
            current = self.k.authoritative_commit()
            if superseded:
                self._retire_integration(ctx.state, unit, "bound to an earlier COMMIT_READY or plan")
                self.queue.release(ctx.state, work_id, to="QUEUED", result="superseded")
                stale = {"reason": "candidate built from an earlier COMMIT_READY or plan", **superseded}
                ctx.op = "integrate.superseded"
                ctx.summary = f"{work_id} candidate superseded (bound to an earlier COMMIT_READY)"
            elif current != integ["base"]:
                integ["status"] = "stale_candidate"
                # D3: the entry keeps its place and the Lead prepares again (D4 rebuilds once under the same lease).
                self.queue.release(ctx.state, work_id, to="QUEUED", result="stale_candidate")
                stale = {"expected": integ["base"], "current": current}
                ctx.summary = f"{work_id} candidate stale: authoritative ref moved"
            else:
                self._require_obligations_at_acceptance(ctx.state, work_id, unit)
                self._post_integration_ok(ctx.state, work_id, unit)
                if I.authoritative_worktree_applies(self.k.repo_root, self.k.authoritative_branch):
                    I.precheck_sync(self.k.repo_root, integ["base"], integ["changed_paths"])
                integ["status"] = "publishing"
                integ["publishing_at"] = utc_now()
                ctx.summary = f"{work_id} publishing {integ['candidate'][:12]} over {integ['base'][:12]}"
        if stale:
            what = ("the integration candidate was built from an earlier COMMIT_READY or plan; run `aew integrate "
                    "prepare` again" if "reason" in stale else
                    "the authoritative ref moved since the candidate was built; rebuild and revalidate")
            raise StaleCandidate(what, **stale)
        faults.hit("integrate.after_publishing_record")
        committed = ctx.session.committed_revision
        assert committed is not None  # the transaction above committed
        return self._finish_publish(token, committed, work_id)

    def _finish_publish(self, token: str, expect_rev: int, work_id: str, *,
                        reconciling: bool = False) -> dict[str, Any]:
        """CAS, worktree sync and DONE as ONE Lead transaction (review 2026-09-26 M1).

        Authority, the expected control revision and the manifest pin are all verified under the
        control-state lock *before* any ref or worktree side effect, and the lock is held until DONE
        commits. A rejected call therefore never moves the ref, and no other writer can interleave
        between publication and completion. A crash at any fault point leaves ``publishing`` for
        ``integrate reconcile``; a refused sync aborts the transaction, so nothing is overwritten.
        """
        stale: StaleCandidate | None = None
        withdrawn: GateUnsatisfied | None = None
        sync: dict[str, Any] = {}  # set on the path that completes; the others raise below
        remove_ticket_workspace = False
        with self.k.lead_txn(token, expect_rev, "integrate.publish") as ctx:
            unit = self.units.unit(ctx.state, work_id)
            integ = unit.get("integration") or {}
            if integ.get("status") != "publishing":
                raise IllegalTransition(f"{work_id} is not publishing (integration {integ.get('status')})")
            self.queue.sync(ctx.state)
            lease = self._publishing_lease(ctx.state, work_id, reconciling)
            ref, base, candidate = self._ref(), integ["base"], integ["candidate"]
            applies = I.authoritative_worktree_applies(self.k.repo_root, self.k.authoritative_branch)
            current = git.rev_parse(ref, cwd=self.k.repo_root)
            cas = "already_published"
            mismatch = self.gates.binding_problem(unit)
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
                        I.precheck_sync(self.k.repo_root, base, integ["changed_paths"])
                    try:
                        I.cas_publish(self.k.repo_root, ref, candidate, base, f"aew: integrate {work_id}")
                        cas = "published"
                    except StaleCandidate as exc:
                        stale = exc
            elif current is None or not git.is_ancestor(candidate, current, cwd=self.k.repo_root):
                stale = StaleCandidate("the authoritative ref no longer contains the candidate", current=current)
            if stale:
                if unit.get("integration") is not None:
                    integ["status"] = "stale_candidate"
                self.queue.release(ctx.state, work_id, to="QUEUED", result="stale_candidate")
                ctx.op = "integrate.stale"
                ctx.summary = f"{work_id} candidate stale"
            elif withdrawn:
                pass
            else:
                faults.hit("integrate.after_cas")
                sync = {"status": "not_applicable (authoritative branch not checked out here)"}
                if applies:
                    # AEW-INV-ISO-004: syncing into the shared checkout is serialized by a lock held for this bounded
                    # step only, in the lease custodian's name. It grants nothing (M4-B6).
                    with self.queue.checkout_sync_lock(ctx.state, lease=lease, work_id=work_id):
                        try:
                            sync = I.sync_worktree(self.k.repo_root, base, candidate, integ["changed_paths"],
                                                   head=current if cas == "already_published" else None,
                                                   on_first=lambda: faults.hit("integrate.mid_sync"))
                        except IntegrityError as exc:
                            raise IntegrityError(exc.message, published=candidate, ref=ref, **exc.details) from None
                    sync["status"] = "synced"
                faults.hit("integrate.before_done")
                transitions.check(unit["state"], "DONE", "integrate.publish")
                integ.update(status="integrated", commit=candidate, integrated_at=utc_now(), cas=cas,
                             worktree_sync=sync)
                completion = self._completion_record(ctx.state, work_id, unit)
                ctx.session.write(f"work/{work_id}/completion.md", completion)
                ctx.refs.append(f"work/{work_id}/completion.md")
                unit["completion_record"] = f"work/{work_id}/completion.md"
                self.units.set_state(unit, "DONE",
                                     f"integrated as {candidate[:12]}; post-integration verification passed",
                                state=ctx.state)
                remove_ticket_workspace = self._settle_ticket_workspace(unit, integ["ticket_commit"])
                ctx.summary = f"{work_id} DONE: integrated {candidate[:12]} into {self.k.authoritative_branch}"
                self.units.before_commit(ctx)
        if stale:
            raise stale
        if withdrawn:
            raise withdrawn
        worktrees.remove(self.k.repo_root, integ["workspace"])
        self._prune_retired_candidates(unit)
        if remove_ticket_workspace:
            worktrees.remove(self.k.repo_root, unit["workspace"]["path"])
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
                f"controlled integration into `{self.k.authoritative_branch}` and post-integration verification "
                f"of the integrated snapshot.\n")
        return render_frontmatter(meta, body)

    def _publishing_lease(self, state: dict[str, Any], work_id: str, reconciling: bool) -> dict[str, Any] | None:
        """The lease a publish in progress runs under. Reconciling an interrupted publish needs no live custodian
        (that is what it reconciles), and a publish begun before the queue existed has no lease at all."""
        lease = Q.lease_of(state, work_id)
        if reconciling or not Q.queued(state):
            return lease
        if lease is None:
            raise LeaseNotHeld(f"publishing {work_id} needs its integration lease")
        if lease["reconcile"] is not None:
            raise LeaseReconcileRequired(
                f"{work_id}'s integration lease lost its custodian ({lease['reconcile']['reason']}): run `aew "
                f"integrate reconcile {work_id}`", entry=lease["entry"])
        return lease

    def integrate_reconcile(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        """Resume an interrupted publish by inspecting git: CAS pending, already done, or stale. A lease whose
        custodian died, with no publish in progress, is reconciled instead: nothing was published, so its open
        candidate is retired and the entry returns to the queue in its place (M4-D: never a timeout)."""
        state = self.k.store.read()
        unit = state["work"].get(work_id) or {}
        lease = Q.lease_of(state, work_id)
        if (unit.get("integration") or {}).get("status") == "publishing" or not (lease and lease["reconcile"]):
            return self._finish_publish(token, expect_rev, work_id, reconciling=True)
        with self.k.lead_txn(token, expect_rev, "integrate.reconcile") as ctx:
            unit = self.units.unit(ctx.state, work_id)
            lease = Q.lease_of(ctx.state, work_id)
            if lease is None or lease["reconcile"] is None or \
                    (unit.get("integration") or {}).get("status") == "publishing":
                raise IllegalTransition(f"{work_id}'s integration changed while reconciling; run it again")
            why = lease["reconcile"]["reason"]
            if (unit.get("integration") or {}).get("status") in OPEN_INTEGRATION:
                self._retire_integration(ctx.state, unit, f"its lease's custodian died ({why})")
            self.queue.release(ctx.state, work_id, to="QUEUED", result=f"reconciled: {why}")
            ctx.summary = f"{work_id} integration lease reconciled ({why}); the entry keeps its place in the queue"
            self.units.before_commit(ctx)
        self._prune_retired_candidates(unit)
        return {"ok": True, "work_id": work_id, "reconciled": "lease", "reason": why,
                "queue": self._queue_brief(ctx.state, work_id), "revision": ctx.session.committed_revision}
