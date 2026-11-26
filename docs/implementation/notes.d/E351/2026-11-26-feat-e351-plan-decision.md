**The kind's name, the operator's ruling of 2026-11-26.** The question put was whether the new decision kind should be
named `PLAN` (the V-01 burn-down's Q8, which the decisions-due list held for the designer). The operator's answer,
verbatim: "6 yeah that seems like jts less a choice and more do you like the name? Which sounds good to me". So the
kind is `PLAN`, and the vertical records it under `plan`, V1's own label, with no mapping.

**Built (#628, `feat/e351-plan-decision`), the row's Work:**

- **The decision.** Each proposed plan revision that `plan accept` would take now (`work_ops.awaiting_acceptance`: the
  unit is in a state that may accept a plan, and the revision was proposed against the plan accepted now) is a `PLAN`
  decision in that unit's action projection, a Ticket's or a parent's. Its owner is the operator's
  (`projection.DECISION_PRIMITIVES` gives it `plan.accept`, which `aew.owners` does not give the Lead), it has no
  default, and its evidence is the plan's path.
- **Its commands.** `cli_fallback` is `plan accept` bound to the plan's SHA-256 (`approval.command`), which the
  operator runs at their own terminal, or which a Lead session runs once the operator has confirmed that plan.
  `ask_operator` is the confirmation's command (`operator_decisions.command`), the same one a Lead session's refusal
  names (#618). The readable head names the decision the operator's, with both.
- **The steering loop** stops on it (`DECISION_REQUIRED`, "`<T>`: PLAN is the operator's"), reported over another
  Ticket's self-clearing BLOCKED (`LEAD_ONLY`). It reads Tickets only, so a parent's `PLAN` shows in that parent's
  status.
- **E350's pinned gaps** lose `integrate publish`: `test_decision_owners` now counts a command whose Lead-session
  commit waits for the operator's confirmation (`operator_decisions.COMMITS`: `plan accept`, `integrate publish`) as
  no gap, and pins that set.
- **Tests:** `tests/integration/test_plan_decision.py`.

**What remains, on other rows:** the typed accept (E163) and the wire action `DECIDE_WORK_PROPOSAL` (E390). The
vertical's `plan_not_accepted` fallback stays for a plan no decision offers; the scripted Lead now takes the `PLAN`
decision's `cli_fallback` from the shell.
