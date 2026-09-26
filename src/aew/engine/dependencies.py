"""Dependency satisfaction and BLOCKED/READY computation (WC §8, §8.1; KC §9.5).

A dependency is satisfied only when the upstream output required downstream is
durably accepted *and* available in the downstream assignment's source snapshot:

* ``evidence`` edge: the upstream work unit is DONE (its accepted artifacts exist);
* ``mutating`` edge: the upstream Ticket is DONE — i.e. integrated into the
  authoritative lineage and post-integration validated — **and** its integrated
  commit is an ancestor of the authoritative commit the downstream assignment
  would record. A COMMIT_READY upstream is an unintegrated candidate and never
  satisfies a mutating dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.workspace import git


def dependency_blockers(
    state: dict[str, Any], unit: dict[str, Any], *, repo_root: Path, base_commit: str | None
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for dep in unit.get("depends_on", []):
        up = state["work"].get(dep["id"])
        if up is None:
            blockers.append({"kind": "dependency", "id": dep["id"], "reason": "unknown_work_unit"})
            continue
        if dep["kind"] == "evidence":
            if up["state"] != "DONE":
                blockers.append({"kind": "dependency", "id": dep["id"], "reason": f"evidence_not_accepted ({up['state']})"})
            continue
        if up["state"] == "COMMIT_READY":
            blockers.append({"kind": "dependency", "id": dep["id"], "reason": "not_integrated"})
            continue
        if up["state"] != "DONE":
            blockers.append({"kind": "dependency", "id": dep["id"], "reason": f"not_done ({up['state']})"})
            continue
        integrated = (up.get("integration") or {}).get("commit")
        if not integrated:
            blockers.append({"kind": "dependency", "id": dep["id"], "reason": "no_integration_record"})
            continue
        if base_commit is None or not git.is_ancestor(integrated, base_commit, cwd=repo_root):
            blockers.append({"kind": "dependency", "id": dep["id"], "reason": "not_in_source_snapshot",
                             "integrated_commit": integrated, "base_commit": base_commit})
    return blockers


def readiness_blockers(
    state: dict[str, Any], unit: dict[str, Any], *, repo_root: Path, base_commit: str | None
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not (unit.get("plan") or {}).get("accepted"):
        blockers.append({"kind": "plan_not_accepted"})
    blockers.extend(dependency_blockers(state, unit, repo_root=repo_root, base_commit=base_commit))
    return blockers


def recompute_readiness(state: dict[str, Any], *, repo_root: Path, base_commit: str | None) -> list[str]:
    """Move Tickets between BLOCKED and READY; returns the ids that changed. Part of the Lead's commit."""
    changed = []
    for wid, unit in state["work"].items():
        if unit["kind"] != "ticket" or unit["state"] not in {"BLOCKED", "READY"}:
            continue
        blockers = readiness_blockers(state, unit, repo_root=repo_root, base_commit=base_commit)
        new_state = "BLOCKED" if blockers else "READY"
        unit["blocked_by"] = blockers
        if new_state != unit["state"]:
            unit["state"] = new_state
            unit["state_reason"] = "dependencies and plan satisfied" if new_state == "READY" else "blocked"
            changed.append(wid)
    return changed
