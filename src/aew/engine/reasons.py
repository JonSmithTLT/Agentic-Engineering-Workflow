"""Durable reason codes for dispatch decisions (M4-A; plan-assurance decisions §3.1, §3.5).

One registry: every code a ``DispatchDecision`` can carry is declared here, with what it means and, where the
designer mapped one, the failure class it is evidence for (`docs/design/failure-class-registry.md`). Refusal codes
stay separate from failure-class names (decisions §3.1). Existing error codes (``CONCURRENCY_LIMIT``,
``DEPENDENCY_UNSATISFIED``, …) are reused as reason codes when a migrated check refuses with them, so a refusal
reads the same whether it came from ``aew dispatch explain`` or from the dispatch itself.
"""

from __future__ import annotations

from typing import NamedTuple


class Reason(NamedTuple):
    summary: str
    failure_class: str | None = None
    blocking: bool = True  # False: an obligation or warning the decision reports without refusing


REASONS: dict[str, Reason] = {
    # Checks that existed before M4, now evaluated inside the predicate (their error codes, unchanged).
    "ILLEGAL_TRANSITION": Reason("the unit's state does not allow this dispatch"),
    "DEPENDENCY_UNSATISFIED": Reason("a dependency is not satisfied in the source the dispatch would use"),
    "CONCURRENCY_LIMIT": Reason("the concurrency cap is reached"),
    "INPUT_STALE": Reason("a consumed record no longer describes the source the dispatch would use"),
    "GATE_UNSATISFIED": Reason("a binding or gate the dispatch needs is not current"),
    "PERMISSION_DENIED": Reason("the dispatch is not permitted for this unit or invocation"),
    "RUN_LIVE": Reason("the invocation's latest run may still be running"),
    "NOT_FOUND": Reason("a unit, card or invocation the dispatch names does not exist"),
    "USAGE": Reason("the dispatch request is malformed"),
    "VALIDATION_FAILED": Reason("a policy or card the dispatch needs is invalid"),
    # Protected conditions (plan assurance v0.4 §10).
    "PROTECTED_CONDITION_OVERLAP": Reason(
        "a protected path lies inside the Ticket's mutation scope: the scope grants a change the policy forbids",
        failure_class="PROTECTED_ACCEPTANCE_OVERLAP"),
    # Hard assurance triggers (v0.4 §22): obligations for Classes 1-4; a triggered Class 0 request fails eligibility.
    "ACCEPTANCE_INPUT_IN_SCOPE": Reason(
        "an acceptance input the Ticket declares lies inside its mutation scope",
        failure_class="PROTECTED_ACCEPTANCE_OVERLAP", blocking=False),
    "INHERITED_ELEVATED_OBLIGATION": Reason(
        "an ancestor imposes a minimum class above 0 or a non-waivable gate", blocking=False),
    # Class 0 eligibility (WC amendment 2026-10-01; v0.4 §22). Each is blocking only when Class 0 is requested.
    "CLASS0_SUBJECT_UNBOUNDED": Reason("Class 0 needs a bounded scope that matches tracked files"),
    "CLASS0_NO_ACCEPTANCE_REFERENCE": Reason("Class 0 needs an explicit objective (--goal) and an acceptance check"),
    "CLASS0_ACCEPTANCE_NOT_DETERMINISTIC": Reason(
        "Class 0 needs every acceptance check to be a configured, deterministic project check"),
    "CLASS0_ASSERTION_MISSING": Reason("Class 0 needs the Lead's recorded semantic assertions"),
    "CLASS0_CONSEQUENTIAL_BOUNDARY": Reason(
        "the scope reaches a path a review trigger marks consequential (security, trust, persistence, compatibility)"),
    "CLASS0_HARD_TRIGGER": Reason("a hard assurance trigger is active, so Class 0 is not eligible"),
    "CLASS0_INHERITED_ELEVATED_OBLIGATION": Reason(
        "an ancestor's non-waivable gate or minimum class makes Class 0 ineligible: choose a stronger class that "
        "satisfies any inherited floor (`aew work reclassify`); the inherited gate stays required"),
    "CLASS0_PLAN_LINT": Reason("Class 0 needs a clean deterministic plan lint"),
    # Deterministic plan lint (v0.4 §18); errors block, warnings are reported.
    "LINT_ACCEPTANCE_CHECK_UNKNOWN": Reason("an acceptance check names no configured project check"),
    "LINT_AFFECTED_PROTECTED": Reason("the plan's affected paths include a protected path",
                                      failure_class="PROTECTED_ACCEPTANCE_OVERLAP"),
    "LINT_AFFECTED_OUTSIDE_SCOPE": Reason("the plan's affected paths fall outside the Ticket's scope", blocking=False),
    "LINT_ACCEPTANCE_INPUT_WRITABLE": Reason("an acceptance input is among the plan's affected paths",
                                             failure_class="ACCEPTANCE_CONDITION_MUTATION", blocking=False),
    "LINT_NO_ACCEPTANCE_MECHANISM": Reason("a mutating Ticket states no goal and no acceptance check",
                                           failure_class="ACCEPTANCE_UNDERSPECIFICATION", blocking=False),
}


def require_known(code: str) -> str:
    if code not in REASONS:
        raise ValueError(f"reason code {code} is not in the registry (aew.engine.reasons)")
    return code
