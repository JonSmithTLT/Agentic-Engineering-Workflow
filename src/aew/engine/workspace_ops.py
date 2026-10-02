"""Assignment, mutation workspaces, evaluated snapshots and invocations (WC §8, §8.1, §9.9, §15.4)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import gates as G
from aew.engine import transitions
from aew.engine.authority import issue_token, revoke
from aew.engine.base import TxnContext
from aew.engine.dependencies import effective_edge_set, readiness_blockers
from aew.errors import ConcurrencyLimit, DependencyUnsatisfied, IllegalTransition, NotFound, PermissionDenied
from aew.harness import contract as K
from aew.harness import registry
from aew.knowledge.records import format_id
from aew.policy import execution as X
from aew.roles import NON_MUTATING_EXECUTORS
from aew.snapshot import fingerprint
from aew.util import utc_now
from aew.workspace import worktrees

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import ContextPacksPort, InputsPort, InvocationsPort, RolesPort, WorkUnitsPort

# Isolation + controlled integration for concurrency > 1 are not implemented yet (M5),
# so the effective mutating concurrency is 1 regardless of policy (WC §8.1, §21.1).
EFFECTIVE_MUTATING_CAP = 1


class Invocations:
    """Evaluated snapshots and invocations: issue, pin, complete, the workspace an invocation may act in, and recording
    run 1 of a `--launch` dispatch (ADR-0009)."""

    def __init__(self, k: Kernel, *, roles: RolesPort) -> None:
        self.k = k
        self.roles = roles

    def _fingerprint_policy(self) -> dict[str, list[str]]:
        fp = self.k.manifest.get("fingerprint") or {}
        return {"exclude": list(fp.get("exclude", [])), "include_ignored": list(fp.get("include_ignored", []))}

    def snapshot_of(self, path: str | Path, workspace_id: str) -> dict[str, Any]:
        return fingerprint.evaluated_snapshot(Path(path), workspace_id, **self._fingerprint_policy())

    def current_snapshot(self, unit: dict[str, Any]) -> dict[str, Any] | None:
        ws = unit.get("workspace")
        if not ws or ws.get("status") != "active" or not Path(ws["path"]).exists():
            return None
        return self.snapshot_of(ws["path"], ws["id"])

    def new_invocation(
        self,
        ctx: TxnContext,
        role: str,
        work_id: str,
        *,
        scope: str = "ticket",
        specialty: str | None = None,
        workspace: str | None = None,
        workspace_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
        card: Any = None,
    ) -> tuple[str, str]:
        state = ctx.state
        state["counters"]["invocation"] = state["counters"].get("invocation", 0) + 1
        inv_id = format_id("INV", state["counters"]["invocation"])
        token = issue_token(state, "invocation", {"invocation_id": inv_id, "role": role, "work_unit": work_id,
                                                  "generation": state["lead"]["generation"]})
        state["invocations"][inv_id] = {
            "role": role, "work_unit": work_id, "status": "active", "token_id": token.split(".")[1],
            "created_at": utc_now(), "generation": state["lead"]["generation"], "scope": scope,
            "specialty": specialty, "workspace": workspace, "workspace_id": workspace_id, "snapshot": snapshot,
            "pack": None,
        }
        state["invocations"][inv_id]["execution_profile"] = self._resolve_execution(ctx, role, work_id, card)
        state["work"][work_id]["invocations"].append(inv_id)
        if card is not None:
            self.roles.pin_on(ctx, inv_id, card)
        if ctx.launch_request:
            self._record_launch_run(ctx, inv_id)
        ctx.refs.append(f"invocation:{inv_id}")
        return inv_id, token

    def _resolve_execution(self, ctx: TxnContext, archetype: str, work_id: str, card: Any) -> dict[str, Any] | None:
        """The harness/provider/model/effort pin for a new invocation (ADR-0010); never changed afterwards."""
        policy, sha = self.k.execution_policy()
        return X.resolve(policy, sha, archetype=archetype, card_id=getattr(card, "id", None),
                         risk_class=G.effective_class(ctx.state, work_id), request=ctx.execution_request)

    def complete_invocation(self, state: dict[str, Any], inv_id: str, status: str = "completed") -> None:
        inv = state["invocations"][inv_id]
        if inv["status"] == "active":
            inv["status"] = status
            revoke(state, inv["token_id"], f"invocation {status}")
        obs = inv.get("observation")
        if obs and obs.get("status") == "active":
            obs["status"] = "retired"  # its read-only worktree is removed after the commit (ADR-0008)

    def on_state_change(self, state: dict[str, Any], unit: dict[str, Any], change: dict[str, str],
                        reason: str | None) -> None:
        """State hook: a unit that becomes terminal keeps no live invocation."""
        if change["to"] in transitions.TERMINAL:
            # A finished Ticket has no assignments left: no credential outlives it (re-review walk finding).
            for inv_id in unit.get("invocations", []):
                self.complete_invocation(state, inv_id, "cancelled")

    def inspect_workspace(self, unit: dict[str, Any]) -> dict[str, Any]:
        ws = unit.get("workspace")
        if not ws:
            return {"workspace": "none"}
        found = worktrees.inspect(ws["path"], ws.get("base_commit"))
        out = {"workspace": ws["id"], **found}
        if found.get("exists"):
            snap = self.snapshot_of(ws["path"], ws["id"])
            out["fingerprint"] = snap["relevant_inputs_fingerprint"]
            out["changed_since_assignment"] = (
                snap["relevant_inputs_fingerprint"] != ws["base_snapshot"]["relevant_inputs_fingerprint"])
        return out

    def release_workspace(self, ctx: TxnContext, unit: dict[str, Any], why: str) -> None:
        """End the current attempt: the workspace stops being live and every active invocation of the
        Ticket is cancelled (credentials revoked). The worktree is left on disk for inspection; the
        branch preserves provenance."""
        ws = unit.get("workspace")
        if ws and ws.get("status") == "active":
            ws["status"] = f"released ({why})"
        for inv_id in unit.get("invocations", []):
            self.complete_invocation(ctx.state, inv_id, "cancelled")

    def require_launchable(self, state: dict[str, Any], inv_id: str, *, relaunch: bool = True) -> dict[str, Any]:
        inv = state["invocations"].get(inv_id)
        if inv is None:
            raise NotFound(f"no invocation {inv_id}")
        if inv["status"] != "active":
            raise IllegalTransition(f"{inv_id} is {inv['status']}; only an active invocation is launched")
        profile = inv.get("execution_profile")
        if not profile:
            raise IllegalTransition(
                f"{inv_id} has no execution profile, so no harness, provider or model is pinned for it: configure "
                "policy/execution.yaml, or dispatch a new invocation with --profile or --model (ADR-0010)")
        registry.check(profile["harness"])
        if relaunch:  # at dispatch the workspace or observation is being allocated in this same transaction
            self.invocation_workspace(state, inv)  # its workspace, candidate or observation is still live
        return inv

    def _record_launch_run(self, ctx: TxnContext, inv_id: str) -> None:
        """``--launch`` on a dispatch: run 1 adopts the credential this transaction issued."""
        inv = self.require_launchable(ctx.state, inv_id, relaunch=False)
        run = K.run_id(inv_id, 1)
        inv["runs"] = [{"run": run, "harness": inv["execution_profile"]["harness"], "token_id": inv["token_id"],
                        "launched_at": utc_now(), "kind": "dispatch", "generation": ctx.state["lead"]["generation"]}]
        ctx.refs.append(f"run:{run}")

    def invocation_workspace(self, state: dict[str, Any], inv: dict[str, Any]) -> tuple[Path, str, str | None]:
        """The workspace this invocation was dispatched for — and only while it is still live (review M2).

        An invocation is never retargeted to a later workspace or candidate of the same Ticket.
        """
        unit = state["work"][inv["work_unit"]]
        if inv.get("scope") in {"observation", "parent"}:
            obs = inv.get("observation") or {}
            if obs.get("status") != "active" or not obs.get("path"):
                raise PermissionDenied("this invocation's read-only observation workspace has been retired",
                                       observation=obs.get("id"))
            execution = unit.get("execution") or {}
            if inv["role"] in NON_MUTATING_EXECUTORS and (execution.get("attempt") != inv.get("attempt")
                                                          or execution.get("ended")):
                raise PermissionDenied(f"this executor belongs to attempt {inv.get('attempt')}, which is not "
                                       f"{inv['work_unit']}'s current attempt ({execution.get('attempt')})")
            return Path(obs["path"]), obs["id"], obs.get("commit")
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
    def execution_provenance(inv: dict[str, Any]) -> dict[str, Any]:
        """Engine-owned producer fields (ADR-0010), taken from control state and never from the submission:
        the execution pinned at dispatch, the credential that presented the request, and the harness run
        holding that credential (None for a scripted role)."""
        run = next((r["run"] for r in reversed(inv.get("runs") or []) if r.get("token_id") == inv["token_id"]), None)
        return {"execution_profile": inv.get("execution_profile"), "run": run, "credential": inv["token_id"]}

    @staticmethod
    def card_ref(inv: dict[str, Any]) -> dict[str, Any] | None:
        card = inv.get("card")
        return {k: card[k] for k in ("id", "version", "sha256")} if card else None



class Assignment:
    """Assigning a mutating Ticket: its mutation workspace and implementer (WC §8, §8.1)."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, roles: RolesPort, invocations: InvocationsPort,
                 inputs: InputsPort, packs: ContextPacksPort) -> None:
        self.k = k
        self.units = units
        self.roles = roles
        self.invocations = invocations
        self.inputs = inputs
        self.packs = packs

    @staticmethod
    def _mutating_slots_in_use(state: dict[str, Any]) -> list[str]:
        """Mutating Tickets holding a live workspace, whatever their state (review M2)."""
        return sorted(
            wid for wid, u in state["work"].items()
            if u["kind"] == "ticket" and u["mutating"] and (u.get("workspace") or {}).get("status") == "active"
        )

    def work_assign(self, *, token: str, expect_rev: int, work_id: str,
                    execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "work.assign") as ctx:
            ctx.execution_request, ctx.launch_request = execution_profile, launch
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["kind"] != "ticket":
                raise IllegalTransition("only Tickets are assigned")
            if not unit["mutating"]:
                # Assignment allocates a mutation workspace and an implementer; an evidence-only Ticket must
                # never receive either (it would bypass the serial mutation cap). It is dispatched instead:
                # investigator/researcher/planner card, read-only observation, no workspace (ADR-0008).
                raise IllegalTransition(
                    f"{work_id} is a non-mutating (evidence-only) Ticket; it never receives a mutation workspace or an "
                    f"implementer. Dispatch it with `aew work dispatch {work_id}` (the M2 non-mutating path)")
            transitions.check(unit["state"], "ASSIGNED", "assign")
            base = self.k.authoritative_commit()
            if base is None:
                raise IllegalTransition(f"authoritative branch {self.k.authoritative_branch} has no commits")
            blockers = readiness_blockers(state, unit, repo_root=self.k.repo_root, base_commit=base, work_id=work_id,
                                          plan_problem=self.units.plan_binding_problem)
            if blockers:
                raise DependencyUnsatisfied(
                    f"{work_id} cannot be assigned: its recorded source snapshot would not contain every "
                    "satisfied dependency", blockers=blockers, base_commit=base)
            if unit["mutating"]:
                busy = self._mutating_slots_in_use(state)
                if work_id in busy:
                    raise IllegalTransition(f"{work_id} still holds live workspace {unit['workspace']['id']}; "
                                            "release it before a new assignment")
                if len(busy) >= EFFECTIVE_MUTATING_CAP:
                    raise ConcurrencyLimit(
                        "mutating concurrency is 1 until isolated concurrent integration exists (WC §8.1); "
                        f"{busy} still hold unintegrated workspaces", holding=busy)
            card = self.roles.resolve_card(state, work_id, "execute", card_id=None, role="implementer")
            # Consumed non-mutating records must still describe the source this assignment is based on (ADR-0008).
            inputs = self.inputs.dispatch_inputs(state, work_id, base)
            unit["attempts"] = unit.get("attempts", 0) + 1
            referenced = {u["workspace"]["path"] for u in state["work"].values()
                          if (u.get("workspace") or {}).get("status") == "active"}
            ws = worktrees.allocate(
                repo_root=self.k.repo_root, aew_root=self.k.aew_root, workspaces_root=self.k.workspaces_root(),
                work_id=work_id, attempt=unit["attempts"], base_commit=base, referenced_paths=referenced,
            )
            try:
                snapshot = self.invocations.snapshot_of(ws["path"], ws["id"])
                ws["base_snapshot"] = snapshot
                # The dependencies this attempt is dispatched with; completion re-checks them (M2 review B2).
                ws["dependencies"] = effective_edge_set(state, work_id)
                unit["workspace"] = ws
                inv_id, inv_token = self.invocations.new_invocation(ctx, "implementer", work_id, workspace=ws["path"],
                                                         workspace_id=ws["id"], snapshot=snapshot, card=card)
                unit["implementer_invocation"] = inv_id
                state["invocations"][inv_id]["inputs"] = inputs
                self.packs.build_pack(ctx, inv_id)
                change = self.units.set_state(unit, "ASSIGNED", f"assigned to {inv_id} in {ws['id']}", state=state)
                ctx.summary = f"{work_id} assigned: {ws['id']} at {base[:12]}"
                self.units.before_commit(ctx)
            except BaseException:
                worktrees.remove(self.k.repo_root, ws["path"])
                raise
        return {"ok": True, "work_id": work_id, "workspace": ws, "invocation": inv_id,
                "invocation_token": inv_token, "role_card": card.id, "transition": change,
                "revision": ctx.session.committed_revision}
