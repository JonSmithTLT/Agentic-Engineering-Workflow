"""Ticket state machine (WC §8; ADR-0003).

WC §8 gives a *typical* state model plus mandatory transition rules. This table
encodes those rules and fills the unlisted transitions conservatively:

* every regression is Lead-initiated and needs a recorded reason;
* forward progress never skips a required gate (guards are evaluated by the
  engine against current evidence);
* results owned by other roles (review disposition, verification result) are
  applied mechanically by dedicated ingest operations, never chosen freely;
* after VERIFICATION_FAILED only the Lead's classification selects the path;
* an INTERRUPTED Ticket is reconciled only to a phase no later than the one it
  was in, after inspection: success is never inferred.

Each rule names the operation (``via``) allowed to perform it, so a generic
``aew work transition`` cannot impersonate an ingest/assign/integrate step.
"""

from __future__ import annotations

from dataclasses import dataclass

from aew.errors import IllegalTransition

STATES = (
    "BLOCKED", "READY", "ASSIGNED", "RUNNING", "REVIEW_PENDING", "REVIEW_FAILED", "REVIEW_PASSED",
    "VERIFY_PENDING", "VERIFICATION_FAILED", "VERIFICATION_INCONCLUSIVE", "VERIFIED", "COMMIT_READY", "DONE",
    "INTERRUPTED", "REPLAN_REQUIRED", "ESCALATED", "CANCELLED",
)
TERMINAL = frozenset({"DONE", "CANCELLED"})
# Phase order used to bound reconciliation of INTERRUPTED work.
PHASE_ORDER = {
    "BLOCKED": 0, "READY": 0, "ASSIGNED": 1, "RUNNING": 2, "REVIEW_PENDING": 3, "REVIEW_FAILED": 3,
    "REVIEW_PASSED": 4, "VERIFY_PENDING": 5, "VERIFICATION_FAILED": 5, "VERIFICATION_INCONCLUSIVE": 5,
    "VERIFIED": 6, "COMMIT_READY": 7, "DONE": 8,
}
# The serial cap (ADR-0003 B6) counts live workspaces directly (workspace.status == active), never
# state names: a replanned Ticket in READY must not hide a workspace that is still live (review M2).

VERIFICATION_CLASSIFICATIONS = {
    "LOCAL_IMPLEMENTATION_DEFECT": "RUNNING",
    "PLAN_OR_DESIGN_DEFECT": "REPLAN_REQUIRED",
    "CONTRACT_VIOLATION": "REPLAN_REQUIRED",
    # "remains blocked/inconclusive until the environment/evidence issue is resolved" (WC §8)
    "ENVIRONMENT_OR_EVIDENCE_BLOCKED": "VERIFICATION_INCONCLUSIVE",
}


@dataclass(frozen=True)
class Rule:
    via: str
    reason_required: bool = False
    guard: str | None = None


RULES: dict[tuple[str, str], Rule] = {
    # engine-computed dependency/plan readiness
    ("BLOCKED", "READY"): Rule("recompute"),
    ("READY", "BLOCKED"): Rule("recompute"),
    # dispatch
    ("READY", "ASSIGNED"): Rule("assign"),
    ("ASSIGNED", "RUNNING"): Rule("transition", guard="implementer_active"),
    # implementation -> review / verification / commit-ready (phases skipped only when not required)
    ("RUNNING", "REVIEW_PENDING"): Rule("transition", guard="ready_for_review"),
    ("RUNNING", "VERIFY_PENDING"): Rule("transition", guard="ready_for_verification_without_review"),
    ("RUNNING", "COMMIT_READY"): Rule("transition", guard="commit_ready_without_review_or_verification"),
    # review results are applied mechanically from the Reviewer's report
    ("REVIEW_PENDING", "REVIEW_PASSED"): Rule("review.ingest"),
    ("REVIEW_PENDING", "REVIEW_FAILED"): Rule("review.ingest"),
    ("REVIEW_FAILED", "RUNNING"): Rule("transition", guard="findings_recorded"),
    ("REVIEW_PASSED", "VERIFY_PENDING"): Rule("transition", guard="review_current"),
    ("REVIEW_PASSED", "COMMIT_READY"): Rule("transition", guard="commit_ready_without_verification"),
    # verification results are applied mechanically from the Verifier's record
    ("VERIFY_PENDING", "VERIFIED"): Rule("verify.ingest"),
    ("VERIFY_PENDING", "VERIFICATION_FAILED"): Rule("verify.ingest"),
    ("VERIFY_PENDING", "VERIFICATION_INCONCLUSIVE"): Rule("verify.ingest"),
    # only the Lead's classification chooses the path after a failure
    ("VERIFICATION_FAILED", "RUNNING"): Rule("verify.classify"),
    ("VERIFICATION_FAILED", "REPLAN_REQUIRED"): Rule("verify.classify"),
    ("VERIFICATION_FAILED", "VERIFICATION_INCONCLUSIVE"): Rule("verify.classify"),
    ("VERIFICATION_INCONCLUSIVE", "VERIFY_PENDING"): Rule("transition", reason_required=True),
    ("VERIFIED", "COMMIT_READY"): Rule("transition", guard="all_gates_current"),
    # integration (validate, then publish by CAS; D-op-2)
    ("COMMIT_READY", "DONE"): Rule("integrate.publish"),
    ("COMMIT_READY", "VERIFICATION_FAILED"): Rule("verify.ingest"),  # post-integration verification failed
    # plan replacement
    ("REPLAN_REQUIRED", "BLOCKED"): Rule("plan.accept"),
    ("REPLAN_REQUIRED", "READY"): Rule("plan.accept"),
}

# Non-mutating (evidence-only) Tickets reach DONE when the Lead accepts their executor's record; they are
# never integrated, and the guard refuses every mutating Ticket (ADR-0008; ADR-0003 amendment).
for _src in ("RUNNING", "REVIEW_PASSED", "VERIFIED"):
    RULES[(_src, "DONE")] = Rule("accept", guard="evidence_only_complete")

# Lead-initiated regressions back to mutation (e.g. evidence went stale, more work needed).
for _src in ("REVIEW_PENDING", "REVIEW_PASSED", "VERIFY_PENDING", "VERIFIED", "VERIFICATION_INCONCLUSIVE",
             "COMMIT_READY"):
    RULES[(_src, "RUNNING")] = Rule("transition", reason_required=True)

# Cross-cutting states (WC §8): any non-terminal state may be cancelled, escalated or sent to replan.
for _src in STATES:
    if _src in TERMINAL:
        continue
    if _src != "CANCELLED":
        RULES.setdefault((_src, "CANCELLED"), Rule("transition", reason_required=True))
    # After VERIFICATION_FAILED the Lead must classify (or cancel); escalation is not a bypass.
    if _src not in {"ESCALATED", "BLOCKED", "READY", "VERIFICATION_FAILED"}:
        RULES.setdefault((_src, "ESCALATED"), Rule("transition", reason_required=True))
    if _src not in {"REPLAN_REQUIRED", "VERIFICATION_FAILED"}:
        RULES.setdefault((_src, "REPLAN_REQUIRED"), Rule("transition", reason_required=True))
    if _src not in {"INTERRUPTED", "BLOCKED", "READY"}:
        RULES.setdefault((_src, "INTERRUPTED"), Rule("interrupt"))

# Return from escalation (the escalation outcome is recorded by the Lead).
for _dst in ("RUNNING", "REVIEW_PENDING", "VERIFY_PENDING"):
    RULES[("ESCALATED", _dst)] = Rule("transition", reason_required=True, guard="returning_from_escalation")

# INTERRUPTED -> reconcile to the recorded phase or an earlier one, after inspection.
for _dst in ("ASSIGNED", "RUNNING", "REVIEW_PENDING", "REVIEW_PASSED", "VERIFY_PENDING", "VERIFIED", "COMMIT_READY"):
    RULES[("INTERRUPTED", _dst)] = Rule("reconcile", reason_required=True, guard="not_beyond_interrupted_phase")


# The Lead command behind each operation, for refusals that say what applies instead (M3 audit X1).
_COMMANDS = {
    "transition": "aew work transition {w} --to {to}",
    "assign": "aew work assign {w} --launch",
    "review.ingest": "aew review ingest {w} --evidence <id>",
    "verify.ingest": "aew verify ingest {w} --evidence <id>",
    "verify.classify": "aew verify classify {w} ...",
    "plan.accept": "aew plan accept {w} --revision <n>",
    "integrate.publish": "aew integrate publish {w}",
    "accept": "aew work accept {w}",
}
_NOTES = {"accept": " (non-mutating Tickets)"}
_EXCEPTIONAL = frozenset({"BLOCKED", "CANCELLED", "ESCALATED", "INTERRUPTED", "REPLAN_REQUIRED"})


def next_steps(frm: str, work_id: str = "<T>") -> str:
    """The forward moves from ``frm``, each as the command that makes it (cancelling, escalating, replanning and
    interrupting are left out: they are decisions, not the next step)."""
    steps = [f"{dst} by `{_COMMANDS[via].format(w=work_id, to=dst)}`{_NOTES.get(via, '')}"
             for dst, via in allowed_from(frm).items() if dst not in _EXCEPTIONAL and via in _COMMANDS]
    return f"From {frm}: " + "; ".join(steps) + " (each with --expect-rev N)." if steps else ""


def check(frm: str, to: str, via: str) -> Rule:
    rule = RULES.get((frm, to))
    if rule is None or rule.via != via:
        allowed = sorted(dst for (src, dst), r in RULES.items() if src == frm and r.via == via)
        raise IllegalTransition(
            f"{frm} -> {to} is not permitted via {via}. {next_steps(frm)}".rstrip(),
            from_state=frm, to_state=to, via=via, allowed_via_this_operation=allowed,
            required_operation=rule.via if rule else None,
        )
    return rule


def allowed_from(frm: str) -> dict[str, str]:
    return {dst: r.via for (src, dst), r in RULES.items() if src == frm}
