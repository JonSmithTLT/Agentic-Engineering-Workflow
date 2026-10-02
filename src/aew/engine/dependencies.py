"""Dependency satisfaction and BLOCKED/READY computation (WC §8, §8.1; KC §9.5; ADR-0007).

A dependency is satisfied only when the upstream output required downstream is
durably accepted *and* available in the downstream assignment's source snapshot:

* ``evidence`` edge: the upstream work unit is DONE (its accepted artifacts exist);
* ``mutating`` edge: the upstream Ticket is DONE — i.e. integrated into the
  authoritative lineage and post-integration validated — **and** its integrated
  commit is an ancestor of the authoritative commit the downstream assignment
  would record. A COMMIT_READY upstream is an unintegrated candidate and never
  satisfies a mutating dependency.
* an edge to a **Story/Epic** is satisfied when that parent is DONE (closed by the Lead after its
  gates); a ``mutating`` edge also requires every DONE mutating descendant's integrated commit in the
  downstream base.

A unit also waits on every edge declared on its ancestors (inherited edges, ADR-0007). Edge
satisfaction governs BLOCKED/READY only; whether a consumed record is still acceptable *input* is
checked separately at every executor dispatch (``freshness``).

A dispatched attempt is bound to the effective edges it was dispatched with (M2 review B2). Moving work
changes inherited edges, so a started Ticket whose effective dependencies differ from its dispatch, or are
not satisfied in the source snapshot it works from, completes nothing until a new dispatch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine import hierarchy as H
from aew.workspace import git


def _integrated_in_base(up: dict[str, Any], base_commit: str | None, repo_root: Path) -> dict[str, Any] | None:
    integrated = (up.get("integration") or {}).get("commit")
    if not integrated:
        return {"reason": "no_integration_record"}
    return _commit_in_base(integrated, base_commit, repo_root)


def _commit_in_base(integrated: str, base_commit: str | None, repo_root: Path) -> dict[str, Any] | None:
    if base_commit is None or not git.is_ancestor(integrated, base_commit, cwd=repo_root):
        return {"reason": "not_in_source_snapshot", "integrated_commit": integrated, "base_commit": base_commit}
    return None


def _edge_blocker(state: dict[str, Any], dep: dict[str, Any], *, repo_root: Path,
                  base_commit: str | None) -> dict[str, Any] | None:
    up = H.upstream(state, dep["id"])
    if up is None:
        return {"kind": "dependency", "id": dep["id"], "reason": "unknown_work_unit"}
    if H.is_parent(up):
        if up["state"] != "DONE":
            return {"kind": "dependency", "id": dep["id"], "reason": f"parent_not_closed ({up['state']})"}
        if dep["kind"] == "mutating":
            # Every DONE mutating descendant's integrated commit in the base. Archived descendants are represented by
            # the parent's integration frontier, the antichain of their integrated commits (R5): every member in the
            # base is exactly every one of them in it. Hot ones (a v1 project, or this very commit) are checked too.
            for commit, via in sorted((up.get("integration_frontier") or {}).items(), key=lambda kv: kv[1]):
                missing = _commit_in_base(commit, base_commit, repo_root)
                if missing:
                    return {"kind": "dependency", "id": dep["id"], "via": via, **missing}
            if not up.get("archived"):
                for wid in H.descendants(state, dep["id"]):
                    d = state["work"][wid]
                    if d["kind"] == "ticket" and d.get("mutating") and d["state"] == "DONE":
                        missing = _integrated_in_base(d, base_commit, repo_root)
                        if missing:
                            return {"kind": "dependency", "id": dep["id"], "via": wid, **missing}
        return None
    if dep["kind"] == "evidence":
        if up["state"] != "DONE":
            return {"kind": "dependency", "id": dep["id"], "reason": f"evidence_not_accepted ({up['state']})"}
        return None
    if up["state"] == "COMMIT_READY":
        return {"kind": "dependency", "id": dep["id"], "reason": "not_integrated"}
    if up["state"] != "DONE":
        return {"kind": "dependency", "id": dep["id"], "reason": f"not_done ({up['state']})"}
    missing = _integrated_in_base(up, base_commit, repo_root)
    return {"kind": "dependency", "id": dep["id"], **missing} if missing else None


def dependency_blockers(
    state: dict[str, Any], unit: dict[str, Any], *, repo_root: Path, base_commit: str | None,
    work_id: str | None = None,
) -> list[dict[str, Any]]:
    edges = [dict(e, inherited_from=None) for e in unit.get("depends_on", [])]
    if work_id is not None:
        edges = H.effective_edges(state, work_id)
    blockers: list[dict[str, Any]] = []
    for dep in edges:
        blocker = _edge_blocker(state, dep, repo_root=repo_root, base_commit=base_commit)
        if blocker is not None:
            if dep.get("inherited_from"):
                blocker["inherited_from"] = dep["inherited_from"]
            blockers.append(blocker)
    return blockers


def readiness_blockers(
    state: dict[str, Any], unit: dict[str, Any], *, repo_root: Path, base_commit: str | None,
    work_id: str | None = None, plan_problem: Any = None,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not (unit.get("plan") or {}).get("accepted"):
        blockers.append({"kind": "plan_not_accepted"})
    elif plan_problem is not None and work_id is not None:
        # An ancestor's accepted plan changed after this plan was accepted (ADR-0007, fail closed).
        problem = plan_problem(state, work_id)
        if problem:
            blockers.append({"kind": "plan_binding_stale", "detail": problem})
    blockers.extend(dependency_blockers(state, unit, repo_root=repo_root, base_commit=base_commit,
                                        work_id=work_id))
    return blockers


# Tickets without a dispatched attempt: the only ones whose effective dependencies may change (ADR-0007).
UNSTARTED = frozenset({"BLOCKED", "READY", "REPLAN_REQUIRED"})


def edge_set(edges: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The identity of a set of dependency edges: unique ``(id, kind)``, sorted (where each is declared is not)."""
    return [{"id": i, "kind": k} for i, k in sorted({(e["id"], e["kind"]) for e in edges})]


def effective_edge_set(state: dict[str, Any], work_id: str) -> list[dict[str, str]]:
    return edge_set(H.effective_edges(state, work_id))


def dispatch_binding(unit: dict[str, Any]) -> dict[str, Any] | None:
    """What a started Ticket's current attempt was dispatched with: its source commit and effective edges.

    Mutating: the live workspace (base commit). Non-mutating: the current execution (observed commit).
    ``dependencies`` is None for an attempt dispatched before bindings were recorded.
    """
    if unit["kind"] != "ticket" or unit["state"] in UNSTARTED | H.TERMINAL:
        return None
    if unit.get("mutating"):
        ws = unit.get("workspace") or {}
        if ws.get("status") != "active":
            return None
        return {"commit": ws.get("base_commit"), "dependencies": ws.get("dependencies")}
    execution = unit.get("execution") or {}
    if not execution:
        return None
    return {"commit": execution.get("observed_commit"), "dependencies": execution.get("dependencies")}


def dispatch_binding_problem(state: dict[str, Any], work_id: str, *, repo_root: Path) -> dict[str, Any] | None:
    """Why a started Ticket's attempt no longer holds under its current effective dependencies, or None.

    The M1 rule: every required upstream output is available in the downstream assignment's source snapshot.
    An edge gained or lost since dispatch (a move re-parents inherited edges) or an edge not satisfied at the
    attempt's own commit means the attempt was dispatched for other dependencies: a new dispatch is required.
    """
    unit = state["work"][work_id]
    binding = dispatch_binding(unit)
    if binding is None:
        return None
    problem: dict[str, Any] = {}
    current = {(e["id"], e["kind"]) for e in effective_edge_set(state, work_id)}
    if binding["dependencies"] is not None:
        recorded = {(e["id"], e["kind"]) for e in binding["dependencies"]}
        if current != recorded:
            problem["added"] = [f"{i}:{k}" for i, k in sorted(current - recorded)]
            problem["removed"] = [f"{i}:{k}" for i, k in sorted(recorded - current)]
    unsatisfied = dependency_blockers(state, unit, repo_root=repo_root, base_commit=binding["commit"],
                                      work_id=work_id)
    if unsatisfied:
        problem["unsatisfied_at_dispatch_commit"] = unsatisfied
    if not problem:
        return None
    return {"reason": "the effective dependencies differ from the ones this attempt was dispatched with",
            "dispatch_commit": binding["commit"], **problem}


def recompute_readiness(state: dict[str, Any], *, repo_root: Path, base_commit: str | None,
                        plan_problem: Any = None) -> list[str]:
    """Move Tickets between BLOCKED and READY; returns the ids that changed. Part of the Lead's commit."""
    changed = []
    for wid, unit in state["work"].items():
        if unit["kind"] != "ticket" or unit["state"] not in {"BLOCKED", "READY"}:
            continue
        blockers = readiness_blockers(state, unit, repo_root=repo_root, base_commit=base_commit, work_id=wid,
                                      plan_problem=plan_problem)
        new_state = "BLOCKED" if blockers else "READY"
        unit["blocked_by"] = blockers
        if new_state != unit["state"]:
            unit["state"] = new_state
            unit["state_reason"] = "dependencies and plan satisfied" if new_state == "READY" else "blocked"
            changed.append(wid)
    return changed
