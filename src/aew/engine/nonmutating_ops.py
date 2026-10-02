"""Non-mutating (evidence-only) Tickets: dispatch, attempts, observation workspaces, records, acceptance.

ADR-0008. The executor of a non-mutating Ticket is an investigator, researcher or planner card; its
authority comes from that archetype, never from the Ticket's label. It observes the authoritative
source through its **own** detached observation worktree (never a mutation workspace, never shared),
writes exactly one record kind (pinned at dispatch as ``expected_kind``) and never integrates anything.

Attempts are explicit (operator review 2026-09-27): each attempt owns one execute invocation, its
credential and its observation. ``work redispatch`` supersedes the attempt atomically — invocation
superseded, credential revoked, observation retired — and nothing produced by an earlier attempt can be
ingested or satisfy a gate of the current one.

Whether a consumed record is still acceptable *input* is checked at every executor dispatch, separately
from dependency satisfaction: a STALE/UNKNOWN source-bound input blocks dispatch unless it is refreshed or
acknowledged by the Lead for the current authoritative commit (``freshness``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import freshness as F
from aew.engine import gates as G
from aew.engine import hierarchy as H
from aew.engine import transitions
from aew.engine.base import TxnContext
from aew.engine.seams import NON_MUTATING, GuardRegistration
from aew.engine.dependencies import dependency_blockers, effective_edge_set, readiness_blockers
from aew.errors import (
    ConcurrencyLimit,
    DependencyUnsatisfied,
    GateUnsatisfied,
    IllegalTransition,
    InputStale,
    NotFound,
    ObservationMutated,
    UsageError,
    ValidationFailed,
)
from aew.knowledge import evidence as E
from aew.knowledge.records import format_id
from aew.snapshot.fingerprint import changed_paths
from aew.util import parse_frontmatter, render_frontmatter, sha256_text, utc_now
from aew.workspace import git, worktrees

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.context_ops import ContextPacks
    from aew.engine.evidence_ops import Gates
    from aew.engine.role_ops import Roles
    from aew.engine.work_ops import WorkCommands, WorkUnits
    from aew.engine.workspace_ops import Invocations

EXECUTE_STATES = frozenset({"ASSIGNED", "RUNNING"})
NO_GUARDRAILS = {"violations": [], "triggered_gates": [], "changed_paths": []}


def is_nm_ticket(unit: dict[str, Any]) -> bool:
    return unit["kind"] == "ticket" and not unit.get("mutating")


class Inputs:
    """Consumed non-mutating records: which inputs a unit consumes and whether each still allows a dispatch
    (ADR-0008)."""

    def __init__(self, k: Kernel) -> None:
        self.k = k

    def _same_source(self, observed: str | None, current: str | None) -> bool:
        """The engineering source at two commits is identical (AEW's own files excluded)."""
        if not observed or not current:
            return False
        if observed == current:
            return True
        return git.ok("diff", "--quiet", observed, current, "--", ".", F.AEW_EXCLUDE, cwd=self.k.repo_root)

    def _find_unit_evidence(self, work_id: str, evidence_id: str) -> dict[str, Any]:
        records, problems = E.scan(self.k.aew_root, work_id)
        if problems:
            raise GateUnsatisfied("evidence integrity problems", problems=problems)
        for ev in records:
            if ev["id"] == evidence_id:
                return ev
        raise NotFound(f"no evidence {evidence_id} for {work_id}")

    def consumed_inputs(self, state: dict[str, Any], work_id: str) -> list[dict[str, Any]]:
        """Accepted non-mutating records this unit consumes through its (own or inherited) dependency edges.

        Records flow only through an edge to a non-mutating Ticket. An edge to a Story or Epic is an
        acceptance dependency: it is satisfied by the parent's closeout, which already judged its children's
        records against the parent snapshot, so those Story-internal inputs are not consumed again downstream.
        """
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for edge in H.effective_edges(state, work_id):
            u = state["work"].get(edge["id"])
            rec = ((u or {}).get("execution") or {}).get("record")
            if u and is_nm_ticket(u) and u["state"] == "DONE" and rec and rec["id"] not in seen:
                seen.add(rec["id"])
                out.append({"id": rec["id"], "sha256": rec["sha256"], "kind": rec["kind"], "from": edge["id"],
                            "declared_on": edge.get("inherited_from") or work_id})
        return out

    def _acknowledged(self, unit: dict[str, Any], evidence_id: str, sha: str, commit: str) -> dict[str, Any] | None:
        return next((a for a in unit.get("input_acknowledgements", [])
                     if a["evidence"] == evidence_id and a["sha256"] == sha and a["commit"] == commit), None)

    def dispatch_inputs(self, state: dict[str, Any], work_id: str, commit: str | None) -> list[dict[str, Any]]:
        """Pin every consumed input for an executor dispatch; refuse STALE/UNKNOWN source-bound ones (INPUT_STALE).

        Dependency satisfaction (BLOCKED/READY) is not enough: a consumed investigation or plan proposal
        must still describe the source the new executor will work from, or the Lead must acknowledge it for
        exactly this authoritative commit (``aew work acknowledge-input``).
        """
        unit = state["work"][work_id]
        pinned, stale = [], []
        for inp in self.consumed_inputs(state, work_id):
            ev = self._find_unit_evidence(inp["from"], inp["id"])
            if ev["_sha256"] != inp["sha256"]:
                raise GateUnsatisfied(f"input {inp['id']} changed after it was accepted", input=inp)
            fresh = F.record_freshness(self.k.repo_root, ev, commit)
            ack = self._acknowledged(unit, inp["id"], inp["sha256"], commit or "")
            entry = {**inp, "freshness": fresh["status"], "basis": fresh.get("basis"),
                     "acknowledgement": (ack or {}).get("decision")}
            if F.is_acceptable_input(fresh) or ack:
                pinned.append(entry)
            else:
                detail = {k: fresh[k] for k in ("changed_paths", "detail", "observed_commit") if k in fresh}
                stale.append({**entry, **detail})
        if stale:
            raise InputStale(
                f"{work_id} consumes {len(stale)} source-bound record(s) that no longer match the authoritative source "
                "they would be used against; refresh them (a new CURRENT record) or acknowledge them for this commit "
                f"with `aew work acknowledge-input {work_id} --input <E> --from <T> --reason ...`",
                inputs=stale, authoritative_commit=commit)
        return pinned

    def dispatch_commit(self, unit: dict[str, Any]) -> str | None:
        """The commit an executor dispatched now would work from: a live mutation workspace's base, else A."""
        ws = unit.get("workspace") or {}
        if unit.get("mutating") and ws.get("status") == "active":
            return ws.get("base_commit")
        return self.k.authoritative_commit()

    def input_status(self, state: dict[str, Any], work_id: str) -> list[dict[str, Any]]:
        """Non-raising view of ``dispatch_inputs`` (resume, status): would each input allow a dispatch now?"""
        unit = state["work"][work_id]
        inputs = self.consumed_inputs(state, work_id)
        if not inputs:  # most units: no git subprocess for a commit nothing would be compared with (M3 step 7)
            return []
        commit = self.dispatch_commit(unit)
        out = []
        for inp in inputs:
            try:
                ev = self._find_unit_evidence(inp["from"], inp["id"])
            except (GateUnsatisfied, NotFound) as exc:
                out.append({**inp, "freshness": "UNKNOWN", "detail": exc.message, "blocks_dispatch": True})
                continue
            fresh = F.record_freshness(self.k.repo_root, ev, commit)
            ack = self._acknowledged(unit, inp["id"], inp["sha256"], commit or "")
            out.append({**inp, "freshness": fresh["status"], "basis": fresh.get("basis"),
                        "acknowledgement": (ack or {}).get("decision"),
                        "blocks_dispatch": ev["_sha256"] != inp["sha256"]
                        or not (F.is_acceptable_input(fresh) or ack)})
        return out



class NonMutating:
    """Non-mutating (evidence-only) Tickets: attempts, observations, records, gates and acceptance."""

    def __init__(self, k: Kernel, *, units: WorkUnits, roles: Roles, invocations: Invocations, inputs: Inputs,
                 packs: ContextPacks, gates: Gates, work: WorkCommands) -> None:
        self.k = k
        self.units = units
        self.roles = roles
        self.invocations = invocations
        self.inputs = inputs
        self.packs = packs
        self.gates = gates
        self.work = work

    _MUTATING_INSTEAD = {
        "`aew work dispatch`": "start a mutating Ticket with `aew work assign {w} --launch`",
        "`aew work redispatch`": "a mutating Ticket gets a new implementer with "
                                 "`aew invoke create {w} --role implementer --launch`",
        "`aew evidence ingest`": "a mutating Ticket's implementation report is accepted by its transition, "
                                 "`aew work transition {w} --to REVIEW_PENDING` (or VERIFY_PENDING or COMMIT_READY, "
                                 "as its gates allow); reviews and verifications use `aew review ingest` and "
                                 "`aew verify ingest`",
    }

    def _require_nm_ticket(self, unit: dict[str, Any], work_id: str, what: str) -> None:
        if not is_nm_ticket(unit):
            mutating = unit["kind"] == "ticket"
            instead = self._MUTATING_INSTEAD.get(what) if mutating else None
            raise IllegalTransition(f"{what} applies to non-mutating (evidence-only) Tickets; {work_id} is "
                                    + ("a mutating Ticket" if mutating else f"a {unit['kind']}")
                                    + (f": {instead.format(w=work_id)}" if instead else ""))

    def _referenced_paths(self, state: dict[str, Any]) -> set[str]:
        paths = {u["workspace"]["path"] for u in state["work"].values()
                 if (u.get("workspace") or {}).get("status") == "active"}
        paths |= {(u.get("integration") or {}).get("workspace") for u in state["work"].values()} - {None}
        paths |= {inv["observation"]["path"] for inv in state["invocations"].values()
                  if (inv.get("observation") or {}).get("status") == "active"}
        return paths

    def prune_observations(self, state: dict[str, Any] | None = None) -> list[str]:
        """Remove observation worktrees whose invocation has ended (best effort; outside any transaction)."""
        state = state or self.k.store.read()
        removed = []
        for inv in state["invocations"].values():
            obs = inv.get("observation") or {}
            if obs and (inv["status"] != "active" or obs.get("status") != "active") and Path(obs["path"]).exists():
                worktrees.remove(self.k.repo_root, obs["path"])
                removed.append(obs["path"])
        return removed

    def _dispatch_observer(self, ctx: TxnContext, work_id: str, *, card: Any, scope: str, commit: str,
                           attempt: int | None = None, subject: dict[str, Any] | None = None,
                           inputs: list[dict[str, Any]] | None = None,
                           children_digest: str | None = None) -> tuple[str, str, dict[str, Any]]:
        """A read-only invocation with its own detached observation worktree at ``commit``."""
        state = ctx.state
        inv_id = format_id("INV", state["counters"].get("invocation", 0) + 1)
        self.prune_observations(state)
        ws = worktrees.allocate_detached(
            repo_root=self.k.repo_root, aew_root=self.k.aew_root, workspaces_root=self.k.workspaces_root(),
            work_id=work_id, name=f"obs/{inv_id}", workspace_id=f"obs-{inv_id}", commit=commit,
            referenced_paths=self._referenced_paths(state))
        state["work"][work_id].setdefault("invocations", [])  # parents gain an invocation list on first dispatch
        try:
            snap = self.invocations.snapshot_of(ws["path"], ws["workspace_id"])
            snapshot = dict(snap)
            if children_digest is not None:
                snapshot["relevant_inputs_fingerprint"] = f"{snap['relevant_inputs_fingerprint']}+children:{children_digest}"
            got, token = self.invocations._new_invocation(ctx, card.archetype, work_id, scope=scope,
                                                          workspace=ws["path"],
                                              workspace_id=ws["workspace_id"], snapshot=snapshot, card=card)
            assert got == inv_id, (got, inv_id)
            inv = state["invocations"][inv_id]
            inv.update(observation={"id": ws["workspace_id"], "path": ws["path"], "commit": commit,
                                    "fingerprint": snap["relevant_inputs_fingerprint"], "status": "active",
                                    "allocated_at": utc_now()},
                       attempt=attempt, subject=subject, inputs=list(inputs or []))
            self.packs.build_pack(ctx, inv_id)
        except BaseException:
            worktrees.remove(self.k.repo_root, ws["path"])
            raise
        return inv_id, token, snapshot

    def require_observation_intact(self, inv_id: str, inv: dict[str, Any]) -> None:
        """A read-only invocation's observation still holds exactly its dispatch snapshot (ADR-0008).

        Checked when a record or report is submitted, and again when the Lead ingests it (M2 review major 2): a
        change made after submission is the same read-only authority violation, and it must not be lost when
        ingestion retires the observation. A report whose invocation ended before ingest can no longer be
        checked (its observation is retired), so it is not accepted either (fail closed).
        """
        obs = inv.get("observation") or {}
        if inv.get("status") != "active" or obs.get("status") != "active":
            raise GateUnsatisfied(f"{inv_id} ended ({inv.get('status')}) before its report was ingested: its read-only "
                                  "observation can no longer be checked, so the report stays history; dispatch a new "
                                  "invocation", invocation=inv_id, observation=obs.get("status"))
        path = Path(obs["path"])
        if not path.exists():
            raise ObservationMutated(f"{inv_id}'s read-only observation workspace is missing", changed=[],
                                     observation=obs["path"])
        if self.invocations.snapshot_of(path, obs["id"])["relevant_inputs_fingerprint"] != obs["fingerprint"]:
            raise ObservationMutated(
                f"{inv_id} changed its read-only observation workspace; a non-mutating invocation may not mutate "
                "source (the Lead redispatches the attempt, or dispatches another reviewer or verifier)",
                changed=changed_paths(path, obs["commit"]))

    def work_acknowledge_input(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str,
                               source: str, reason: str) -> dict[str, Any]:
        if not (reason and reason.strip()):
            raise UsageError("acknowledging a stale input needs a reason (what was rechecked)")
        with self.k.lead_txn(token, expect_rev, "input.acknowledge", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["state"] in H.TERMINAL:
                raise IllegalTransition(f"{work_id} is {unit['state']}")
            src = self.units.unit(state, source)
            rec = (src.get("execution") or {}).get("record") or {}
            if not (is_nm_ticket(src) and src["state"] == "DONE" and rec.get("id") == evidence_id):
                raise UsageError(f"{evidence_id} is not the accepted record of a DONE non-mutating Ticket {source}")
            commit = self.k.authoritative_commit()
            ev = self.inputs._find_unit_evidence(source, evidence_id)
            fresh = F.record_freshness(self.k.repo_root, ev, commit)
            decision = self.k.new_decision(
                ctx, "input_acknowledgement",
                f"{work_id}: input {evidence_id} ({fresh['status']}) acknowledged for commit {(commit or '')[:12]}",
                work_unit=work_id, evidence_refs=[ev["_path"]], reason=reason,
                body=f"Freshness at acknowledgement: {fresh}\n")
            unit.setdefault("input_acknowledgements", []).append(
                {"evidence": evidence_id, "sha256": ev["_sha256"], "from": source, "commit": commit,
                 "freshness": fresh["status"], "decision": decision, "at": utc_now()})
            ctx.summary = f"{work_id}: input {evidence_id} acknowledged ({decision})"
        return {"ok": True, "work_id": work_id, "decision": decision, "commit": commit, "freshness": fresh,
                "revision": ctx.session.committed_revision}

    def work_reconcile(self, *, token: str, expect_rev: int, work_id: str, to: str, reason: str,
                       inspection: dict[str, Any] | None = None) -> dict[str, Any]:
        """Non-mutating Tickets are reconciled on their attempt, not a workspace (nothing is inferred)."""
        if inspection is None:
            state = self.k.store.read()
            unit = state["work"].get(work_id)
            if unit is not None and is_nm_ticket(unit):
                inspection = self._inspect_attempt(state, work_id, unit)
        return self.work.work_reconcile(token=token, expect_rev=expect_rev, work_id=work_id, to=to, reason=reason,
                                      inspection=inspection)

    def _inspect_attempt(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> dict[str, Any]:
        execution = unit.get("execution") or {}
        inv_id = execution.get("invocation")
        records, _ = E.scan(self.k.aew_root, work_id)
        return {"workspace": "none (non-mutating: one read-only observation per invocation)",
                "attempt": execution.get("attempt"), "executor": inv_id,
                "executor_status": (state["invocations"].get(inv_id or "") or {}).get("status"),
                "records_submitted": [e["id"] for e in records if inv_id and e["producer"]["invocation"] == inv_id],
                "next": "records of an ended attempt are history; continue with `aew work redispatch`"}

    def _executor_card(self, state: dict[str, Any], work_id: str, card: str | None) -> tuple[Any, str]:
        chosen = self.roles.resolve_card(state, work_id, "execute", card_id=card, role=None)
        stored = {e["card"]: e for e in ((state["work"][work_id].get("role_plan") or {}).get("execute") or [])}
        if chosen.id in stored:
            selected_by = stored[chosen.id]["selected_by"]
        elif card:
            selected_by = "lead"
        else:
            selected_by = "workflow-default"
        return chosen, selected_by

    def _check_nm_concurrency(self, state: dict[str, Any]) -> None:
        limit = self.k.policy("gates").get("non_mutating_concurrency")
        if not limit:
            return
        busy = sorted(wid for wid, u in state["work"].items() if is_nm_ticket(u)
                      and state["invocations"].get((u.get("execution") or {}).get("invocation") or "", {}).get(
                          "status") == "active")
        if len(busy) >= limit:
            raise ConcurrencyLimit(f"non-mutating concurrency is capped at {limit} by policy", holding=busy)

    def _start_attempt(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], card: str | None,
                       commit: str) -> tuple[str, str]:
        state = ctx.state
        self.units.require_plan_binding(state, work_id)
        # A redispatch starts a new attempt, too: its dependencies must be in the source it will observe (B2).
        blockers = dependency_blockers(state, unit, repo_root=self.k.repo_root, base_commit=commit, work_id=work_id)
        if blockers:
            raise DependencyUnsatisfied(f"{work_id} cannot start a new attempt: a dependency is not satisfied in "
                                        f"{str(commit)[:12]}", blockers=blockers)
        inputs = self.inputs.dispatch_inputs(state, work_id, commit)
        chosen, selected_by = self._executor_card(state, work_id, card)
        # A previous attempt (ingested, cancelled by a replan, or interrupted) is retired to history first.
        self._end_attempt(state, unit, "a new attempt starts", "superseded")
        # Every attempt start (dispatch or redispatch) takes a slot under the policy cap. It is counted after the
        # previous attempt is retired in this same transaction, so a redispatch may replace its own active
        # executor but never adds one beyond the cap (M2 re-review).
        self._check_nm_concurrency(state)
        attempt = unit.get("attempts", 0) + 1
        unit["attempts"] = attempt
        inv_id, inv_token, _ = self._dispatch_observer(ctx, work_id, card=chosen, scope="observation", commit=commit,
                                                       attempt=attempt, inputs=inputs)
        unit["execution"] = {
            "attempt": attempt, "invocation": inv_id, "archetype": chosen.archetype,
            "card": {"id": chosen.id, "version": chosen.meta.get("version"), "sha256": chosen.sha256},
            "expected_kind": E.EXECUTE_KIND[chosen.archetype], "selected_by": selected_by,
            "observed_commit": commit, "record": None, "started_at": utc_now(),
            "dependencies": effective_edge_set(state, work_id),
        }
        # The pack states the attempt's output contract, which exists only now: pin the pack that durable state
        # regenerates (M3-D1; a harness launch refuses a drifted pack).
        self.packs.build_pack(ctx, inv_id)
        return inv_id, inv_token

    def _end_attempt(self, state: dict[str, Any], unit: dict[str, Any], why: str, status: str) -> None:
        """Retire the current attempt into history: its executor ends (credential revoked, observation retired).

        An attempt whose record was already ingested (or whose executor was cancelled or interrupted) is
        still moved to history, so nothing from it can be mistaken for the next attempt's output.
        """
        execution = unit.pop("execution", None)
        if not execution:
            return
        inv = state["invocations"].get(execution["invocation"])
        if inv and inv["status"] == "active":
            self.invocations._complete_invocation(state, execution["invocation"], status)
        if not execution.get("ended"):
            execution.update(ended=status if inv and inv["status"] == status else (inv or {}).get("status", status),
                             ended_at=utc_now(), end_reason=why)
        execution["retired_reason"] = why
        unit.setdefault("execution_history", []).append(execution)

    def work_dispatch(self, *, token: str, expect_rev: int, work_id: str, card: str | None = None,
                      execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        """READY -> ASSIGNED for a non-mutating Ticket: attempt 1 with its own observation, no mutation workspace."""
        with self.k.lead_txn(token, expect_rev, "work.dispatch") as ctx:
            ctx.execution_request, ctx.launch_request = execution_profile, launch
            state = ctx.state
            unit = self.units.unit(state, work_id)
            self._require_nm_ticket(unit, work_id, "`aew work dispatch`")
            transitions.check(unit["state"], "ASSIGNED", "assign")
            commit = self.k.authoritative_commit()
            if commit is None:
                raise IllegalTransition(f"authoritative branch {self.k.authoritative_branch} has no commits")
            blockers = readiness_blockers(state, unit, repo_root=self.k.repo_root, base_commit=commit, work_id=work_id,
                                          plan_problem=self.units.plan_binding_problem)
            if blockers:
                raise DependencyUnsatisfied(f"{work_id} cannot be dispatched", blockers=blockers)
            inv_id, inv_token = self._start_attempt(ctx, work_id, unit, card, commit)
            execution = unit["execution"]
            change = self.units._set_state(unit, "ASSIGNED", f"dispatched {inv_id} ({execution['card']['id']}, attempt "
                                     f"{execution['attempt']}, expects {execution['expected_kind']}, "
                                     f"selected by {execution['selected_by']})", state=state)
            ctx.summary = f"{work_id} dispatched: {inv_id} observes {commit[:12]}"
            self.units.before_commit(ctx)
        inv = ctx.state["invocations"][inv_id]
        return {"ok": True, "work_id": work_id, "invocation": inv_id, "invocation_token": inv_token,
                "execution": execution, "observation": inv["observation"], "pack": inv.get("pack"),
                "transition": change, "revision": ctx.session.committed_revision}

    def work_redispatch(self, *, token: str, expect_rev: int, work_id: str, reason: str,
                        card: str | None = None, execution_profile: dict[str, Any] | None = None,
                        launch: bool = False) -> dict[str, Any]:
        """Supersede the current attempt atomically and start the next one (operator review #2)."""
        if not (reason and reason.strip()):
            raise UsageError("a redispatch supersedes the current attempt; it needs a reason")
        with self.k.lead_txn(token, expect_rev, "work.redispatch", reason=reason) as ctx:
            ctx.execution_request, ctx.launch_request = execution_profile, launch
            state = ctx.state
            unit = self.units.unit(state, work_id)
            self._require_nm_ticket(unit, work_id, "`aew work redispatch`")
            if unit["state"] not in EXECUTE_STATES:
                raise IllegalTransition(f"{work_id} is {unit['state']}; a new attempt starts from ASSIGNED or RUNNING "
                                        "(reconcile an INTERRUPTED Ticket first)")
            previous = dict(unit.get("execution") or {})
            commit = self.k.authoritative_commit()
            decision = self.k.new_decision(
                ctx, "attempt_supersession",
                f"{work_id} attempt {previous.get('attempt')} superseded; attempt {unit.get('attempts', 0) + 1} starts",
                work_unit=work_id, reason=reason,
                body=f"Superseded execution: {previous}\n\nNothing produced by the superseded attempt can be ingested "
                     "or satisfy a gate of the new one.\n")
            self._end_attempt(state, unit, f"superseded ({decision}): {reason}", "superseded")
            inv_id, inv_token = self._start_attempt(ctx, work_id, unit, card, commit)
            unit.setdefault("history", []).append(
                {"from": unit["state"], "to": unit["state"], "at": utc_now(), "event": "attempt_superseded",
                 "reason": f"{reason} ({decision}); attempt {unit['execution']['attempt']} = {inv_id}"})
            ctx.summary = f"{work_id} redispatched: attempt {unit['execution']['attempt']} ({inv_id})"
            self.units.before_commit(ctx)
        self.prune_observations()
        inv = ctx.state["invocations"][inv_id]
        return {"ok": True, "work_id": work_id, "decision": decision, "superseded": previous,
                "invocation": inv_id, "invocation_token": inv_token, "execution": unit["execution"],
                "observation": inv["observation"], "revision": ctx.session.committed_revision}

    def execute_record_binding(self, state: dict[str, Any], inv_id: str, inv: dict[str, Any], kind: str,
                               submitted: dict[str, Any]) -> dict[str, Any]:
        """Engine-owned fields of a discovery/research/plan record (called by ``submit``)."""
        unit = state["work"][inv["work_unit"]]
        execution = unit.get("execution") or {}
        if inv.get("scope") != "observation" or execution.get("invocation") != inv_id \
                or inv.get("attempt") != execution.get("attempt") or execution.get("ended"):
            raise GateUnsatisfied(f"{inv_id} is not the executor of {inv['work_unit']}'s current attempt; its "
                                  "records are history and cannot be submitted now")
        if kind != execution["expected_kind"]:
            raise ValidationFailed(f"attempt {execution['attempt']} of {inv['work_unit']} must produce a "
                                   f"{execution['expected_kind']} (pinned at dispatch), not a {kind}")
        section = {"discovery_record": "discovery", "research_record": "research", "plan_proposal": "proposal"}[kind]
        result = submitted.get("result", "pass")
        if result not in {"pass", "blocked", "inconclusive"}:
            raise ValidationFailed("a record's result is pass (the question is answered), blocked or inconclusive")
        return {"evaluated_snapshot": inv["snapshot"], "attempt": inv["attempt"], "result": result,
                section: submitted.get(section) or {}}

    def evidence_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        """Lead accepts the current attempt's execute record into control state (it is not yet DONE)."""
        with self.k.lead_txn(token, expect_rev, "evidence.ingest") as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            self._require_nm_ticket(unit, work_id, "`aew evidence ingest`")
            if unit["state"] != "RUNNING":
                raise IllegalTransition(f"{work_id} is {unit['state']}; records are ingested while RUNNING")
            execution = unit.get("execution") or {}
            ev = self.inputs._find_unit_evidence(work_id, evidence_id)
            inv = state["invocations"].get(ev["producer"]["invocation"]) or {}
            problems: dict[str, Any] = {}
            if ev["kind"] != execution.get("expected_kind"):
                problems["kind"] = {"record": ev["kind"], "expected": execution.get("expected_kind")}
            if ev["producer"]["invocation"] != execution.get("invocation") or ev.get("attempt") != execution.get("attempt"):
                problems["attempt"] = {"record_attempt": ev.get("attempt"), "current_attempt": execution.get("attempt")}
            if inv.get("status") != "active" or execution.get("ended"):
                problems["executor"] = f"the attempt's executor is {inv.get('status')}; its records are history"
            plan = unit.get("plan") or {}
            if ev.get("plan_revision") != ({"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None):
                problems["plan"] = {"record": ev.get("plan_revision"), "accepted": plan.get("accepted")}
            if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != (inv.get("snapshot") or {}).get(
                    "relevant_inputs_fingerprint"):
                problems["observation"] = "the record is not bound to its executor's observation snapshot"
            binding = self.units.dispatch_binding_problem(state, work_id)
            if binding:
                problems["dependencies"] = binding
            if problems:
                raise GateUnsatisfied(f"{evidence_id} cannot be accepted for {work_id}'s current attempt; it remains "
                                      "history", **problems)
            self.require_observation_intact(ev["producer"]["invocation"], inv)  # changed since submission?
            self.gates._ingest_ref(unit, ev)
            execution["record"] = {"id": ev["id"], "sha256": ev["_sha256"], "kind": ev["kind"], "result": ev["result"]}
            self.invocations._complete_invocation(state, ev["producer"]["invocation"])
            execution.update(ended="completed", ended_at=utc_now(), end_reason=f"record {ev['id']} ingested")
            ctx.refs.append(ev["_path"])
            ctx.summary = f"{work_id} record {evidence_id} ingested ({ev['result']})"
            self.units.before_commit(ctx)
        self.prune_observations()
        return {"ok": True, "work_id": work_id, "record": execution["record"],
                "revision": ctx.session.committed_revision}

    def execute_record_status(self, state: dict[str, Any], work_id: str, records: dict[str, dict[str, Any]],
                              commit: str | None) -> dict[str, Any]:
        unit = state["work"][work_id]
        execution = unit.get("execution") or {}
        rec = execution.get("record")
        if not rec:
            return {"status": G.MISSING, "expected_kind": execution.get("expected_kind")}
        ev = records.get(rec["id"])
        if ev is None or ev["_sha256"] != rec["sha256"]:
            return {"status": G.FAILED, "evidence": rec["id"], "detail": "record missing or modified"}
        if ev["kind"] != execution.get("expected_kind") or ev.get("attempt") != execution.get("attempt"):
            return {"status": G.FAILED, "evidence": rec["id"], "detail": "not the pinned output of the current attempt"}
        if ev["result"] != "pass":
            return {"status": G.FAILED, "evidence": rec["id"], "detail": f"record result is {ev['result']}"}
        plan_rev = (unit.get("plan") or {}).get("accepted")
        if (ev.get("plan_revision") or {}).get("revision") != plan_rev:
            return {"status": G.STALE, "evidence": rec["id"], "detail": "record was produced under another plan"}
        fresh = F.record_freshness(self.k.repo_root, ev, commit)
        if fresh.get("source_bound") and fresh["status"] != F.CURRENT:
            return {"status": G.STALE, "evidence": rec["id"], "freshness": fresh,
                    "action": f"`aew work redispatch {work_id}` for a record of the current source"}
        return {"status": G.CURRENT, "evidence": rec["id"], "freshness": fresh}

    def evidence_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        unit = self.units.unit(state, work_id)
        gates_policy = self.k.policy("gates")
        obligations = G.effective_obligations(state, work_id, {**gates_policy, "risk_paths": G.path_table(
            gates_policy, unit)}, None, self.roles.plan_gates(unit))
        evidence, problems = E.scan(self.k.aew_root, work_id)
        commit = self.k.authoritative_commit()
        special = {"accepted_plan": self.gates.plan_gate_status(state, work_id),
                   "execute_record": self.execute_record_status(state, work_id, {e["id"]: e for e in evidence}, commit)}
        subject = (unit.get("execution") or {}).get("record")
        subject_ref = {"id": subject["id"], "sha256": subject["sha256"]} if subject else None

        def is_current(e: dict[str, Any]) -> bool:
            return subject_ref is not None and e.get("subject") == subject_ref

        results = G.evaluate_evidence_unit(state, work_id, evidence, obligations=obligations, special=special,
                                           is_current=is_current)
        return {"snapshot": {"base_revision": commit, "subject": subject_ref,
                             "relevant_inputs_fingerprint": (subject or {}).get("id")},
                "guardrails": dict(NO_GUARDRAILS), "obligations": obligations, "gates": results, "evidence": evidence,
                "evidence_problems": problems, "open_required_findings": G.open_required_findings(unit),
                "plan_binding": self.units.plan_binding_problem(state, work_id),
                "dispatch_binding": self.units.dispatch_binding_problem(state, work_id)}

    NM_PRE_REVIEW = ["accepted_plan", "execute_record"]

    def guard_registrations(self) -> list[GuardRegistration]:
        """Lead-transition guards for non-mutating Tickets (mutating Tickets keep their M1 guards): each replaces the
        general guard of the same name for this kind only. ``evidence_only_complete`` exists only here, for every
        kind (a mutating Ticket is refused by it)."""
        own = [("implementer_active", self._guard_implementer_active),
               ("ready_for_review", self._guard_ready_for_review),
               ("ready_for_verification_without_review", self._guard_ready_for_verification_without_review),
               ("review_current", self._guard_review_current),
               ("commit_ready_without_review_or_verification",
                self._guard_commit_ready_without_review_or_verification),
               ("commit_ready_without_verification", self._guard_commit_ready_without_verification),
               ("all_gates_current", self._guard_all_gates_current)]
        return [GuardRegistration(name, guard, (NON_MUTATING,), replace=True) for name, guard in own] + [
            GuardRegistration("evidence_only_complete", self._guard_evidence_only_complete)]

    def _guard_implementer_active(self, ctx, work_id, unit, to) -> None:
        inv = ctx.state["invocations"].get((unit.get("execution") or {}).get("invocation") or "")
        if not inv or inv["status"] != "active":
            raise GateUnsatisfied(f"{work_id} has no active executor for its current attempt")

    def _guard_ready_for_review(self, ctx, work_id, unit, to) -> None:
        gc = self.gates.gate_context(ctx.state, work_id)
        if not self.gates._review_gates(gc):
            raise GateUnsatisfied("no review gate applies; accept the record (`aew work accept`) or verify it")
        self.gates._require_gates(gc, self.NM_PRE_REVIEW, what="RUNNING -> REVIEW_PENDING")
        self.gates._record_relied_on(ctx, unit, gc, self.NM_PRE_REVIEW)

    def _guard_ready_for_verification_without_review(self, ctx, work_id, unit, to) -> None:
        gc = self.gates.gate_context(ctx.state, work_id)
        if self.gates._review_gates(gc):
            raise GateUnsatisfied("independent review is required before verification",
                                  required=self.gates._review_gates(gc))
        if not self.gates._verification_gates(gc):
            raise GateUnsatisfied("no verification gate applies; accept the record (`aew work accept`)")
        self.gates._require_gates(gc, self.NM_PRE_REVIEW, what="RUNNING -> VERIFY_PENDING")
        self.gates._record_relied_on(ctx, unit, gc, self.NM_PRE_REVIEW)

    def _guard_review_current(self, ctx, work_id, unit, to) -> None:
        gc = self.gates.gate_context(ctx.state, work_id)
        self.gates._require_gates(gc, self.NM_PRE_REVIEW + self.gates._review_gates(gc),
                                  what="REVIEW_PASSED -> VERIFY_PENDING")

    def _refuse_commit_ready(self, work_id: str) -> None:
        raise IllegalTransition(f"{work_id} is non-mutating: it is never an integration candidate (COMMIT_READY); "
                                "the Lead completes it with `aew work accept`")

    def _guard_commit_ready_without_review_or_verification(self, ctx, work_id, unit, to) -> None:
        self._refuse_commit_ready(work_id)

    def _guard_commit_ready_without_verification(self, ctx, work_id, unit, to) -> None:
        self._refuse_commit_ready(work_id)

    def _guard_all_gates_current(self, ctx, work_id, unit, to) -> None:
        self._refuse_commit_ready(work_id)

    def _guard_evidence_only_complete(self, ctx, work_id, unit, to) -> None:
        if not is_nm_ticket(unit):
            raise IllegalTransition(f"{work_id} is mutating: it reaches DONE only through controlled integration")
        gc = self.gates.gate_context(ctx.state, work_id)
        self.gates._require_gates(gc, gc["obligations"]["gates"], what="-> DONE (record acceptance)")
        if gc["open_required_findings"]:
            raise GateUnsatisfied("mandatory review findings are unresolved and not waived",
                                  findings=[f["id"] for f in gc["open_required_findings"]])
        self.gates._record_relied_on(ctx, unit, gc, list(gc["gates"]))
        ctx.accepted_gates = gc  # type: ignore[attr-defined]  (read by work_accept for the completion record)

    def work_accept(self, *, token: str, expect_rev: int, work_id: str, reason: str | None = None) -> dict[str, Any]:
        """The Lead accepts a non-mutating Ticket's record: -> DONE with an evidence-only completion record."""
        with self.k.lead_txn(token, expect_rev, "work.accept", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["kind"] != "ticket":
                raise IllegalTransition("Stories and Epics are closed with `aew work close`")
            rule = transitions.check(unit["state"], "DONE", "accept")
            self.units._guard(rule.guard, ctx, work_id, unit, "DONE")
            gc = ctx.accepted_gates  # type: ignore[attr-defined]
            execution = unit["execution"]
            decision = self.k.new_decision(
                ctx, "evidence_acceptance", f"{work_id} record {execution['record']['id']} accepted", work_unit=work_id,
                evidence_refs=[r["path"] for r in unit.get("evidence", []) if r["id"] == execution["record"]["id"]],
                reason=reason)
            path = f"work/{work_id}/completion.md"
            text = self._evidence_only_completion(state, work_id, unit, gc, decision)
            ctx.session.write(path, text)
            ctx.refs.append(path)
            unit["completion_record"] = path
            unit["completion_sha256"] = sha256_text(text)
            change = self.units._set_state(unit, "DONE", reason or f"record accepted ({decision})", state=state)
            ctx.summary = f"{work_id} accepted -> DONE ({decision})"
            self.units.before_commit(ctx)
        self.prune_observations()
        return {"ok": True, "work_id": work_id, "decision": decision, "completion_record": path,
                "transition": change, "revision": ctx.session.committed_revision}

    def _evidence_only_completion(self, state: dict[str, Any], work_id: str, unit: dict[str, Any],
                                  gc: dict[str, Any], decision: str) -> str:
        plan = unit.get("plan") or {}
        execution = unit["execution"]
        meta = {
            "schema": "aew/completion/v1", "work_unit": work_id, "kind": "evidence_only", "at": utc_now(),
            "decision": decision,
            "plan": {"revision": plan.get("accepted"), "sha256": plan.get("sha256")},
            "execution": {k: execution.get(k) for k in ("attempt", "invocation", "archetype", "card", "expected_kind",
                                                        "selected_by", "observed_commit")},
            "accepted_record": execution["record"],
            "record_freshness": (gc["gates"].get("execute_record") or {}).get("freshness"),
            "gates": {g: v["status"] for g, v in gc["gates"].items()},
            "basis": sorted({execution["record"]["id"]} | {v["evidence"] for v in gc["gates"].values()
                                                             if isinstance(v.get("evidence"), str)}),
            "evidence": [{"id": e["id"], "kind": e["kind"], "result": e["result"], "sha256": e["sha256"]}
                         for e in unit.get("evidence", [])],
            "waivers": unit.get("waivers", []),
            "superseded_attempts": [{"attempt": h.get("attempt"), "invocation": h.get("invocation"),
                                     "ended": h.get("ended"), "record": (h.get("record") or {}).get("id"),
                                     "reason": h.get("retired_reason")}
                                    for h in unit.get("execution_history", [])],
        }
        body = (f"# Completion — {work_id}: {unit['title']}\n\nEvidence-only Ticket: the Lead accepted the "
                f"{execution['expected_kind']} produced by attempt {execution['attempt']} "
                f"({execution['card']['id']}, selected by {execution['selected_by']}). No source was changed or "
                "integrated.\n")
        return render_frontmatter(meta, body)

    def invoke_evidence_unit(self, *, token: str, expect_rev: int, work_id: str, role: str | None,
                             card: str | None, scope: str, execution_profile: dict[str, Any] | None = None,
                             launch: bool = False) -> dict[str, Any]:
        """Review/verify invocations for a non-mutating Ticket, bound to the record they evaluate."""
        with self.k.lead_txn(token, expect_rev, "invoke.create") as ctx:
            ctx.execution_request, ctx.launch_request = execution_profile, launch
            state = ctx.state
            unit = self.units.unit(state, work_id)
            self._require_nm_ticket(unit, work_id, "this dispatch")
            if scope != "ticket":
                raise UsageError("--scope integration applies to mutating Tickets only")
            st = unit["state"]
            if st in EXECUTE_STATES:
                raise IllegalTransition(f"{work_id}'s executor is dispatched per attempt (one active executor per "
                                        f"attempt): use `aew work redispatch {work_id} --reason ...`")
            slot = {"REVIEW_PENDING": "review", "VERIFY_PENDING": "verify"}.get(st)
            if slot is None:
                raise IllegalTransition(f"no role is dispatched for {work_id} in state {st}")
            gc = self.gates.gate_context(state, work_id)
            chosen = self.roles.resolve_card(state, work_id, slot, card_id=card, role=role, gc=gc)
            record = (unit.get("execution") or {}).get("record")
            if not record:
                raise IllegalTransition(f"{work_id} has no accepted record to {slot}")
            ev = self.inputs._find_unit_evidence(work_id, record["id"])
            # The reviewer/verifier observes exactly the source the executor observed.
            inv_id, inv_token, snapshot = self._dispatch_observer(
                ctx, work_id, card=chosen, scope="observation", commit=ev["evaluated_snapshot"]["base_revision"],
                subject={"id": record["id"], "sha256": record["sha256"]})
            ctx.summary = f"{inv_id} ({chosen.id} / {chosen.archetype}) dispatched for {work_id}'s {record['id']}"
        inv = ctx.state["invocations"][inv_id]
        return {"ok": True, "invocation": inv_id, "invocation_token": inv_token, "role": chosen.archetype,
                "role_card": chosen.id, "scope": "observation", "subject": inv["subject"],
                "evaluated_snapshot": snapshot, "observation": inv["observation"], "pack": inv.get("pack"),
                "revision": ctx.session.committed_revision}

    @staticmethod
    def _record_review_findings(unit: dict[str, Any], ev: dict[str, Any], evidence_id: str) -> None:
        """Same finding bookkeeping as M1 review ingest (resolved earlier findings; required vs noted)."""
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

    def ingest_evidence_unit_report(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str,
                                    kind: str) -> dict[str, Any]:
        """Lead ingests a review/verification of a non-mutating Ticket's accepted record."""
        op = "review.ingest" if kind == "review" else "verify.ingest"
        with self.k.lead_txn(token, expect_rev, op) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            self._require_nm_ticket(unit, work_id, "this ingest")
            expected_state = "REVIEW_PENDING" if kind == "review" else "VERIFY_PENDING"
            if unit["state"] != expected_state:
                raise IllegalTransition(f"{work_id} is {unit['state']}, not {expected_state}. "
                                        f"{transitions.next_steps(unit['state'], work_id)}".rstrip())
            ev = self.inputs._find_unit_evidence(work_id, evidence_id)
            inv = state["invocations"][ev["producer"]["invocation"]]
            role = "reviewer" if kind == "review" else "verifier"
            if ev["kind"] != kind or inv["role"] != role or inv["work_unit"] != work_id:
                raise IllegalTransition(f"{evidence_id} is not a {kind} of {work_id}")
            record = (unit.get("execution") or {}).get("record") or {}
            if ev.get("subject") != {"id": record.get("id"), "sha256": record.get("sha256")}:
                raise GateUnsatisfied(f"{evidence_id} evaluated {ev.get('subject')}, not {work_id}'s current record "
                                      f"{record.get('id')} (stale)")
            plan = unit.get("plan") or {}
            if ev.get("plan_revision") != ({"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None):
                raise GateUnsatisfied(f"{evidence_id} was produced under another plan than the accepted one")
            self.require_observation_intact(ev["producer"]["invocation"], inv)
            if kind == "review":
                self._record_review_findings(unit, ev, evidence_id)
            self.gates._ingest_ref(unit, ev)
            self.invocations._complete_invocation(state, ev["producer"]["invocation"])
            gc = self.gates.gate_context(state, work_id)
            change = None
            if kind == "review":
                open_required = G.open_required_findings(unit)
                pending = G.unmet(gc["gates"], self.gates._review_gates(gc))
                to = "REVIEW_FAILED" if ev["review"]["disposition"] != "pass" or open_required else (
                    None if pending else "REVIEW_PASSED")
                via = "review.ingest"
            else:
                unit["last_verification"] = {"evidence": evidence_id, "result": ev["result"], "scope": "ticket"}
                to = {"pass": "VERIFIED", "fail": "VERIFICATION_FAILED"}.get(ev["result"], "VERIFICATION_INCONCLUSIVE")
                pending = G.unmet(gc["gates"], self.gates._verification_gates(gc)) if to == "VERIFIED" else {}
                if pending:
                    to = None
                via = "verify.ingest"
            if to:
                transitions.check(unit["state"], to, via)
                change = self.units._set_state(unit, to, f"{kind} {evidence_id}: {ev['result']}", state=state)
            ctx.refs.append(ev["_path"])
            ctx.summary = f"{work_id} {kind} {evidence_id} ingested" + (f" -> {to}" if to else " (pending)")
            self.units.before_commit(ctx)
        self.prune_observations()
        return {"ok": True, "work_id": work_id, "transition": change, "pending": pending,
                "revision": ctx.session.committed_revision}

    def plan_adopt(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str, source: str,
                   reason: str | None = None, review: list[str] | None = None, verify: list[str] | None = None,
                   no_assurance: bool = False) -> dict[str, Any]:
        """Create a *proposed* plan revision on any unit from an accepted Planner plan_proposal (ADR-0008)."""
        with self.k.lead_txn(token, expect_rev, "plan.adopt", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["state"] in H.TERMINAL:
                raise IllegalTransition(f"{work_id} is {unit['state']}")
            assurance = self.roles.resolve_plan_assurance(unit, review=review, verify=verify, none=no_assurance)
            src = self.units.unit(state, source)
            rec = (src.get("execution") or {}).get("record") or {}
            if not (is_nm_ticket(src) and src["state"] == "DONE" and rec.get("id") == evidence_id
                    and rec.get("kind") == "plan_proposal"):
                raise UsageError(f"{evidence_id} is not the accepted plan_proposal of a DONE planning Ticket {source}")
            ev = self.inputs._find_unit_evidence(source, evidence_id)
            commit = self.k.authoritative_commit()
            fresh = F.record_freshness(self.k.repo_root, ev, commit)
            if not F.is_acceptable_input(fresh) and not self.inputs._acknowledged(unit, evidence_id, ev["_sha256"],
                                                                           commit or ""):
                raise InputStale(f"{evidence_id} is {fresh['status']} against the current source; acknowledge it for "
                                 f"{work_id} first (`aew work acknowledge-input`) or plan again", freshness=fresh)
            _, body = parse_frontmatter((self.k.aew_root / ev["_path"]).read_text(encoding="utf-8"))
            proposal = ev.get("proposal") or {}
            inv = state["invocations"][ev["producer"]["invocation"]]
            path, revision = self.units._propose(
                ctx, work_id, unit, body=body, reason=reason, affected_paths=proposal.get("affected_paths"),
                assurance=assurance, author={"role": "planner", "invocation": ev["producer"]["invocation"],
                        "card": (inv.get("card") or {}).get("id"), "adopted_by_generation": ctx.actor["generation"]},
                source_evidence={"id": evidence_id, "sha256": ev["_sha256"], "work_unit": source,
                                 "invocation": ev["producer"]["invocation"]})
            ctx.summary = f"{work_id} plan v{revision} adopted from {evidence_id} (proposed)"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "revision_number": revision, "path": path,
                "revision": ctx.session.committed_revision}

    def plan_reconfirm(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        """Rebind an accepted plan to its ancestors' current plans after they changed (fail-closed binding)."""
        if not (reason and reason.strip()):
            raise UsageError("reconfirming a plan under changed ancestor plans needs a reason")
        with self.k.lead_txn(token, expect_rev, "plan.reconfirm", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            problem = self.units.plan_binding_problem(state, work_id)
            if problem is None:
                raise UsageError(f"{work_id}'s accepted plan is bound to its ancestors' current plans; nothing to "
                                 "reconfirm")
            decision = self.k.new_decision(ctx, "plan_reconfirmation",
                                         f"{work_id} plan v{unit['plan']['accepted']} reconfirmed under current "
                                         "ancestor plans", work_unit=work_id, reason=reason,
                                         body=f"Binding problem resolved: {problem}\n")
            unit["plan"]["ancestor_plans"] = self.units.ancestor_plan_snapshot(state, work_id)
            unit["plan"].pop("bindings_invalidated", None)
            unit["plan"].setdefault("reconfirmations", []).append({"decision": decision, "at": utc_now()})
            ctx.summary = f"{work_id} plan reconfirmed ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "decision": decision, "revision": ctx.session.committed_revision}
