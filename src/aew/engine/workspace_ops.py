"""Assignment, mutation workspaces, evaluated snapshots and invocations (WC §8, §8.1, §9.9, §15.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine import gates as G
from aew.engine import transitions
from aew.engine.authority import issue_token, revoke
from aew.engine.base import TxnContext
from aew.engine.dependencies import effective_edge_set, readiness_blockers
from aew.engine.role_ops import RoleOps
from aew.errors import ConcurrencyLimit, DependencyUnsatisfied, IllegalTransition
from aew.knowledge.records import format_id
from aew.policy import execution as X
from aew.snapshot import fingerprint
from aew.util import utc_now
from aew.workspace import worktrees

# Isolation + controlled integration for concurrency > 1 are not implemented yet (M5),
# so the effective mutating concurrency is 1 regardless of policy (WC §8.1, §21.1).
EFFECTIVE_MUTATING_CAP = 1


class WorkspaceOps(RoleOps):
    # ------------------------------------------------------------------ snapshots

    def _fingerprint_policy(self) -> dict[str, list[str]]:
        fp = self.manifest.get("fingerprint") or {}
        return {"exclude": list(fp.get("exclude", [])), "include_ignored": list(fp.get("include_ignored", []))}

    def snapshot_of(self, path: str | Path, workspace_id: str) -> dict[str, Any]:
        return fingerprint.evaluated_snapshot(Path(path), workspace_id, **self._fingerprint_policy())

    def current_snapshot(self, unit: dict[str, Any]) -> dict[str, Any] | None:
        ws = unit.get("workspace")
        if not ws or ws.get("status") != "active" or not Path(ws["path"]).exists():
            return None
        return self.snapshot_of(ws["path"], ws["id"])

    # ------------------------------------------------------------------ invocations

    def _new_invocation(
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
            self._pin_on(ctx, inv_id, card)
        ctx.refs.append(f"invocation:{inv_id}")
        return inv_id, token

    def _resolve_execution(self, ctx: TxnContext, archetype: str, work_id: str, card: Any) -> dict[str, Any] | None:
        """The harness/provider/model/effort pin for a new invocation (ADR-0010); never changed afterwards."""
        policy, sha = self.execution_policy()
        return X.resolve(policy, sha, archetype=archetype, card_id=getattr(card, "id", None),
                         risk_class=G.effective_class(ctx.state, work_id), request=ctx.execution_request)

    def _complete_invocation(self, state: dict[str, Any], inv_id: str, status: str = "completed") -> None:
        inv = state["invocations"][inv_id]
        if inv["status"] == "active":
            inv["status"] = status
            revoke(state, inv["token_id"], f"invocation {status}")
        obs = inv.get("observation")
        if obs and obs.get("status") == "active":
            obs["status"] = "retired"  # its read-only worktree is removed after the commit (ADR-0008)

    def _after_state_change(self, state: dict[str, Any], unit: dict[str, Any], change: dict[str, str],
                            reason: str | None) -> None:
        super()._after_state_change(state, unit, change, reason)
        if change["to"] in transitions.TERMINAL:
            # A finished Ticket has no assignments left: no credential outlives it (re-review walk finding).
            for inv_id in unit.get("invocations", []):
                self._complete_invocation(state, inv_id, "cancelled")

    # ------------------------------------------------------------------ assignment

    @staticmethod
    def _mutating_slots_in_use(state: dict[str, Any]) -> list[str]:
        """Mutating Tickets holding a live workspace, whatever their state (review M2)."""
        return sorted(
            wid for wid, u in state["work"].items()
            if u["kind"] == "ticket" and u["mutating"] and (u.get("workspace") or {}).get("status") == "active"
        )

    def work_assign(self, *, token: str, expect_rev: int, work_id: str,
                    execution_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "work.assign") as ctx:
            ctx.execution_request = execution_profile
            state = ctx.state
            unit = self.unit(state, work_id)
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
            base = self.authoritative_commit()
            if base is None:
                raise IllegalTransition(f"authoritative branch {self.authoritative_branch} has no commits")
            blockers = readiness_blockers(state, unit, repo_root=self.repo_root, base_commit=base, work_id=work_id,
                                          plan_problem=self.plan_binding_problem)
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
            card = self.resolve_card(state, work_id, "execute", card_id=None, role="implementer")
            # Consumed non-mutating records must still describe the source this assignment is based on (ADR-0008).
            inputs = self.dispatch_inputs(state, work_id, base)
            unit["attempts"] = unit.get("attempts", 0) + 1
            referenced = {u["workspace"]["path"] for u in state["work"].values()
                          if (u.get("workspace") or {}).get("status") == "active"}
            ws = worktrees.allocate(
                repo_root=self.repo_root, aew_root=self.aew_root, workspaces_root=self.workspaces_root(),
                work_id=work_id, attempt=unit["attempts"], base_commit=base, referenced_paths=referenced,
            )
            try:
                snapshot = self.snapshot_of(ws["path"], ws["id"])
                ws["base_snapshot"] = snapshot
                # The dependencies this attempt is dispatched with; completion re-checks them (M2 review B2).
                ws["dependencies"] = effective_edge_set(state, work_id)
                unit["workspace"] = ws
                inv_id, inv_token = self._new_invocation(ctx, "implementer", work_id, workspace=ws["path"],
                                                         workspace_id=ws["id"], snapshot=snapshot, card=card)
                unit["implementer_invocation"] = inv_id
                state["invocations"][inv_id]["inputs"] = inputs
                self.build_pack(ctx, inv_id)
                change = self._set_state(unit, "ASSIGNED", f"assigned to {inv_id} in {ws['id']}", state=state)
                ctx.summary = f"{work_id} assigned: {ws['id']} at {base[:12]}"
                self.before_commit(ctx)
            except BaseException:
                worktrees.remove(self.repo_root, ws["path"])
                raise
        return {"ok": True, "work_id": work_id, "workspace": ws, "invocation": inv_id,
                "invocation_token": inv_token, "role_card": card.id, "transition": change,
                "revision": ctx.session.committed_revision}

    # Refined by the context-pack mixin (step 8).
    def build_pack(self, ctx: TxnContext, inv_id: str) -> None:
        return None

    # Refined by the non-mutating mixin (consumed-input freshness at dispatch, ADR-0008).
    def dispatch_inputs(self, state: dict[str, Any], work_id: str, commit: str | None) -> list[dict[str, Any]]:
        return []

    # ------------------------------------------------------------------ hooks from WorkOps

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

    def _release_workspace(self, ctx: TxnContext, unit: dict[str, Any], why: str) -> None:
        """End the current attempt: the workspace stops being live and every active invocation of the
        Ticket is cancelled (credentials revoked). The worktree is left on disk for inspection; the
        branch preserves provenance."""
        ws = unit.get("workspace")
        if ws and ws.get("status") == "active":
            ws["status"] = f"released ({why})"
        for inv_id in unit.get("invocations", []):
            self._complete_invocation(ctx.state, inv_id, "cancelled")
