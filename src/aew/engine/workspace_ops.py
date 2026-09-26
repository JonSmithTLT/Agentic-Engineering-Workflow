"""Assignment, mutation workspaces, evaluated snapshots and invocations (WC §8, §8.1, §9.9, §15.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine import transitions
from aew.engine.authority import issue_token, revoke
from aew.engine.base import TxnContext
from aew.engine.dependencies import readiness_blockers
from aew.engine.work_ops import WorkOps
from aew.errors import ConcurrencyLimit, DependencyUnsatisfied, IllegalTransition
from aew.knowledge.records import format_id
from aew.snapshot import fingerprint
from aew.util import utc_now
from aew.workspace import worktrees

# Isolation + controlled integration for concurrency > 1 are not implemented yet (M5),
# so the effective mutating concurrency is 1 regardless of policy (WC §8.1, §21.1).
EFFECTIVE_MUTATING_CAP = 1


class WorkspaceOps(WorkOps):
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
        snapshot: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        state = ctx.state
        state["counters"]["invocation"] = state["counters"].get("invocation", 0) + 1
        inv_id = format_id("INV", state["counters"]["invocation"])
        token = issue_token(state, "invocation", {"invocation_id": inv_id, "role": role, "work_unit": work_id,
                                                  "generation": state["lead"]["generation"]})
        state["invocations"][inv_id] = {
            "role": role, "work_unit": work_id, "status": "active", "token_id": token.split(".")[1],
            "created_at": utc_now(), "generation": state["lead"]["generation"], "scope": scope,
            "specialty": specialty, "workspace": workspace, "snapshot": snapshot, "pack": None,
        }
        state["work"][work_id]["invocations"].append(inv_id)
        ctx.refs.append(f"invocation:{inv_id}")
        return inv_id, token

    def _complete_invocation(self, state: dict[str, Any], inv_id: str, status: str = "completed") -> None:
        inv = state["invocations"][inv_id]
        if inv["status"] == "active":
            inv["status"] = status
            revoke(state, inv["token_id"], f"invocation {status}")

    # ------------------------------------------------------------------ assignment

    def _mutating_slots_in_use(self, state: dict[str, Any], excluding: str) -> list[str]:
        return sorted(
            wid for wid, u in state["work"].items()
            if wid != excluding and u["kind"] == "ticket" and u["mutating"]
            and u["state"] in transitions.HOLDS_WORKSPACE
            and (u.get("workspace") or {}).get("status") == "active"
        )

    def work_assign(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "work.assign") as ctx:
            state = ctx.state
            unit = self.unit(state, work_id)
            if unit["kind"] != "ticket":
                raise IllegalTransition("only Tickets are assigned")
            transitions.check(unit["state"], "ASSIGNED", "assign")
            base = self.authoritative_commit()
            if base is None:
                raise IllegalTransition(f"authoritative branch {self.authoritative_branch} has no commits")
            blockers = readiness_blockers(state, unit, repo_root=self.repo_root, base_commit=base)
            if blockers:
                raise DependencyUnsatisfied(
                    f"{work_id} cannot be assigned: its recorded source snapshot would not contain every "
                    "satisfied dependency", blockers=blockers, base_commit=base)
            if unit["mutating"]:
                busy = self._mutating_slots_in_use(state, work_id)
                if len(busy) >= EFFECTIVE_MUTATING_CAP:
                    raise ConcurrencyLimit(
                        "mutating concurrency is 1 until isolated concurrent integration exists (WC §8.1); "
                        f"{busy} still hold unintegrated workspaces", holding=busy)
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
                unit["workspace"] = ws
                inv_id, inv_token = self._new_invocation(ctx, "implementer", work_id, workspace=ws["path"],
                                                         snapshot=snapshot)
                unit["implementer_invocation"] = inv_id
                self.build_pack(ctx, inv_id)
                change = self._set_state(unit, "ASSIGNED", f"assigned to {inv_id} in {ws['id']}")
                ctx.summary = f"{work_id} assigned: {ws['id']} at {base[:12]}"
                self.before_commit(ctx)
            except BaseException:
                worktrees.remove(self.repo_root, ws["path"])
                raise
        return {"ok": True, "work_id": work_id, "workspace": ws, "invocation": inv_id,
                "invocation_token": inv_token, "transition": change,
                "revision": ctx.session.committed_revision}

    # Refined by the context-pack mixin (step 8).
    def build_pack(self, ctx: TxnContext, inv_id: str) -> None:
        return None

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
        ws = unit.get("workspace")
        if not ws or ws.get("status") != "active":
            return
        ws["status"] = f"released ({why})"
        for inv_id in unit.get("invocations", []):
            self._complete_invocation(ctx.state, inv_id, "cancelled")
        # The worktree is left on disk for inspection; the branch preserves provenance.
