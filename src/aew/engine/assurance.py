"""Deterministic assurance checks behind the dispatch predicate (M4-A; plan assurance v0.4 §10, §18, §22).

Pure functions over a Ticket's record (scope, acceptance, the Lead's Class 0 assertions), its accepted plan, the
project's policy and the files tracked at the source commit. They decide nothing on their own: ``Dispatch`` turns
their findings into blocking conditions or obligations.

* **Protected conditions** (§10): a path the policy protects lies inside the Ticket's explicit mutation scope. The
  scope then grants a change the policy forbids, so dispatch is refused (``PROTECTED_CONDITION_OVERLAP``). A Ticket
  with no scope is unbounded; its changes are still held to the protected paths by the guardrail check at every gate.
* **Hard triggers** (§22) that are deterministic today: an acceptance input inside the mutation scope, and an
  inherited elevated obligation. They add obligations for Classes 1-4 and make Class 0 ineligible.
* **Class 0 eligibility** (the Workflow Contract amendment of 2026-10-01): structural checks, the Lead's recorded
  semantic assertions, no active hard trigger, and a clean plan lint.
* **Plan lint** (§18): the structural plan defects that need no model.
"""

from __future__ import annotations

from typing import Any

from aew.policy.guardrails import ALWAYS_PROTECTED
from aew.util import glob_any

# The Lead's recorded semantic assertions for Class 0 (amendment §2): what the engine cannot check itself.
CLASS0_ASSERTIONS = {
    "transformation_clear": "the intended transformation or behaviour is clear",
    "inputs_complete": "no known decision-sensitive input was omitted from the declared inputs",
    "no_consequential_boundary": "no consequential security, trust, persistence or compatibility boundary is touched",
}
CATCH_ALL = frozenset({"**", "**/*", "*", "./**", ""})


def _glob_chars(pattern: str) -> bool:
    return any(c in pattern for c in "*?[")


def paths_in(patterns: list[str], scope: list[str], files: list[str]) -> list[str]:
    """Tracked files matched by both ``patterns`` and ``scope``, plus literal patterns that ``scope`` covers."""
    found = {f for f in files if glob_any(f, patterns) and glob_any(f, scope)}
    found |= {p for p in patterns if not _glob_chars(p) and glob_any(p, scope)}
    return sorted(found)


def protected_overlap(scope: list[str], guardrails: dict[str, Any], files: list[str]) -> list[str]:
    if not scope:
        return []
    return paths_in(ALWAYS_PROTECTED + list(guardrails.get("protected_paths") or []), scope, files)


def acceptance_inputs_in_scope(scope: list[str], inputs: list[str], files: list[str]) -> list[str]:
    if not inputs:
        return []
    if not scope:  # an unbounded scope covers every input
        return sorted(set(inputs))
    return paths_in(inputs, scope, files)


def inherited_elevation(obligations: dict[str, Any]) -> dict[str, Any] | None:
    """An ancestor's minimum class above 0, or its non-waivable gates (``gates.effective_obligations``)."""
    floor = obligations.get("floor")
    inherited = list(obligations.get("non_waivable") or [])
    if (floor or 0) > 0 or inherited:
        return {"floor": floor, "gates": inherited}
    return None


def plan_lint(*, meta: dict[str, Any], affected: list[str], guardrails: dict[str, Any],
              checks: dict[str, Any], mutating: bool) -> list[dict[str, Any]]:
    """Deterministic plan lint (v0.4 §18): ``[{code, severity, message, paths?}]``; errors block dispatch."""
    scope = list((meta.get("scope") or {}).get("paths") or [])
    acceptance = meta.get("acceptance") or {}
    acc_checks = list(acceptance.get("checks") or [])
    acc_inputs = list(acceptance.get("inputs") or [])
    configured = checks.get("checks") or {}
    out: list[dict[str, Any]] = []
    unknown = [c for c in acc_checks if c != "guardrails" and c not in configured]
    if unknown:
        out.append({"code": "LINT_ACCEPTANCE_CHECK_UNKNOWN", "severity": "error",
                    "message": f"acceptance check(s) {unknown} are not defined in policy/checks.yaml", "checks": unknown})
    protected = ALWAYS_PROTECTED + list(guardrails.get("protected_paths") or [])
    hit = sorted(p for p in affected if glob_any(p, protected))
    if hit:
        out.append({"code": "LINT_AFFECTED_PROTECTED", "severity": "error",
                    "message": f"the plan's affected paths {hit} are protected", "paths": hit})
    if scope:
        outside = sorted(p for p in affected if not glob_any(p, scope))
        if outside:
            out.append({"code": "LINT_AFFECTED_OUTSIDE_SCOPE", "severity": "warning",
                        "message": f"the plan's affected paths {outside} are outside the Ticket's scope {scope}",
                        "paths": outside})
    writable = sorted(p for p in affected if glob_any(p, acc_inputs) or p in acc_inputs)
    if writable:
        out.append({"code": "LINT_ACCEPTANCE_INPUT_WRITABLE", "severity": "warning",
                    "message": f"the plan changes acceptance inputs {writable}", "paths": writable})
    if mutating and not (acceptance.get("goal_backwards") or acc_checks):
        out.append({"code": "LINT_NO_ACCEPTANCE_MECHANISM", "severity": "warning",
                    "message": "a mutating Ticket with no goal (--goal) and no acceptance check (--acceptance-check)"})
    return out


def class0_blockers(*, meta: dict[str, Any], files: list[str], guardrails: dict[str, Any], checks: dict[str, Any],
                    triggers: list[dict[str, Any]], lint: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Why a Class 0 request is not eligible: ``[{code, message, details?}]``, empty when it is."""
    scope = list((meta.get("scope") or {}).get("paths") or [])
    acceptance = meta.get("acceptance") or {}
    acc_checks = list(acceptance.get("checks") or [])
    out: list[dict[str, Any]] = []
    unbounded = not scope or any(g.strip() in CATCH_ALL for g in scope) \
        or not any(glob_any(f, scope) for f in files)
    if unbounded:
        out.append({"code": "CLASS0_SUBJECT_UNBOUNDED",
                    "message": f"the scope {scope or '(none)'} is not a bounded subject matching tracked files"})
    if not acceptance.get("goal_backwards") or not acc_checks:
        out.append({"code": "CLASS0_NO_ACCEPTANCE_REFERENCE",
                    "message": "Class 0 needs an explicit objective (--goal) and an acceptance check "
                               "(--acceptance-check)"})
    configured = checks.get("checks") or {}
    loose = [c for c in acc_checks
             if c != "guardrails" and not ((configured.get(c) or {}).get("configured") and configured[c].get("command"))]
    if loose:
        out.append({"code": "CLASS0_ACCEPTANCE_NOT_DETERMINISTIC",
                    "message": f"acceptance check(s) {loose} are not configured deterministic checks",
                    "details": {"checks": loose}})
    missing = sorted(set(CLASS0_ASSERTIONS) - set(meta.get("class0_assertions") or []))
    if missing:
        out.append({"code": "CLASS0_ASSERTION_MISSING",
                    "message": "the Lead has not recorded: " + "; ".join(CLASS0_ASSERTIONS[m] for m in missing)
                               + f" (`--class0-assert {' --class0-assert '.join(missing)}` at creation)",
                    "details": {"missing": missing}})
    boundary = sorted({t["name"] for t in guardrails.get("review_triggers") or []
                       if paths_in(list(t.get("paths") or []), scope, files)}) if scope else []
    if boundary:
        out.append({"code": "CLASS0_CONSEQUENTIAL_BOUNDARY",
                    "message": f"the scope reaches paths the review trigger(s) {boundary} mark consequential",
                    "details": {"triggers": boundary}})
    inherited = [t for t in triggers if t["code"] == "INHERITED_ELEVATED_OBLIGATION"]
    if inherited:
        found = inherited[0]
        out.append({"code": "CLASS0_INHERITED_ELEVATED_OBLIGATION",
                    "message": "an ancestor imposes " + "; ".join(
                        ([f"minimum class {found['floor']}"] if (found.get("floor") or 0) > 0 else [])
                        + ([f"non-waivable gate(s) {found['gates']}"] if found.get("gates") else []))
                    + ": Class 0 is not eligible beneath it",
                    "details": {"floor": found.get("floor"), "gates": found.get("gates") or []}})
    triggers = [t for t in triggers if t["code"] != "INHERITED_ELEVATED_OBLIGATION"]
    if triggers:
        out.append({"code": "CLASS0_HARD_TRIGGER",
                    "message": "hard assurance trigger(s) active: " + ", ".join(t["code"] for t in triggers),
                    "details": {"triggers": [t["code"] for t in triggers]}})
    if lint:
        out.append({"code": "CLASS0_PLAN_LINT",
                    "message": "the plan lint is not clean: " + ", ".join(sorted({x["code"] for x in lint})),
                    "details": {"lint": sorted({x["code"] for x in lint})}})
    return out
