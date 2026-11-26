**The F19 refinement proposal is filed, and the operator answered seven questions on it (2026-11-26).**
[The proposal](../../../research/f19-refinement-proposal-2026-11-26.md) (research, not adopted; ledger FRP) is the
read-only study E389 asked for. The Lead put seven questions on it to the operator on 2026-11-26. The operator
answered all seven at once, in these words: "Yes to all 7 on the F19 proposal". Each decision below is the Lead's
question, as put, and that answer. Five are recorded here. The second is on E389's closing and the seventh on E198's
note of this day.

1. "Unfreeze F19 for feature cells only (the role-run arm, the shared walker and report), leaving the large comparison
   and its slices frozen? I recommend yes." The operator: "Yes to all 7 on the F19 proposal".
3. "#607: allow its two small hooks in F19's frozen runner, and make its walker and report the shared one? I recommend
   yes; otherwise it copies about 100 lines and becomes the fourth walker." The operator: "Yes to all 7 on the F19
   proposal". #607 is E135's skill evaluation runner (E135's note of this day).
4. "Order: pack pilot, E368 deciding run, skills, recovery section, maps, verifier. I agree with this order." The
   operator: "Yes to all 7 on the F19 proposal".
5. "Cap: does the approved cap cover F19 feature cells as a class, with the skill evaluation's $10 beside it? I
   recommend yes." The operator: "Yes to all 7 on the F19 proposal".
6. "The large comparison (Q7, M4-H): keep frozen and decide after three cells whether it is still wanted. I recommend
   yes." The operator: "Yes to all 7 on the F19 proposal".

**What this changes of F19.** The freeze of 2026-11-06 (this row's note of that day) now reads: frozen except feature
cells (operator, 2026-11-26). The large comparison (Q7, M4-H) and its slices stay frozen. No cell of this row states
the freeze, so none changes; the board's entry SYS-01 carries the same words. The feature cells' order is the order of
question 4, whose source is the proposal (its section 6, O-4, with the cells described in its sections 4 and 5): the
pack pilot, the E368 deciding run, skills, the recovery section, maps, the verifier. The approved cap is the one this
row's earlier note of 2026-11-26 records ($0.50 and 20 minutes per attempt, at most 132 attempts, a $75 hard total;
E389's Notes cell, as it stood when the row closed, adds a stop for review at half). The operator approved it for
R0's cells as then proposed; question 5 alone extends it to F19's feature cells as a class. E389 closed into this row
on 2026-11-26, so its feature-cell backlog continues here.

**Not decided.** The operator's answer covers the seven questions and nothing else in the proposal. These stay open:
- for the designer, the proposal's eight points (its section 6, D-1 to D-8): whether the role-run arm is a new arm
  kind; how a feature cell expresses its treatment; whether harness-reported cost is admissible for feature cells;
  what S13's operator ceremony stands on; how one attempt records several participants; whether thresholds and
  outcomes are schema fields; whether a public fixture with a private oracle can support a decision; and whether S18
  is dropped in favour of E97's meter;
- for the operator, the proposal's items that were not among the seven: the worker profile and its re-qualification
  (O-6), and whether E368's rewrite is held as the treatment (O-7, its first half);
- the thresholds and outcomes: the proposal's own first item (O-1) included them in the unfreeze, and the Lead's
  question 1 did not, so they are not part of what was unfrozen (they are the designer's D-6);
- the order of building: question 1 gives no order among the role-run arm, the shared walker and report and the
  cells, and question 4 orders the cells only;
- rows that wait "until F19 is unfrozen" (F17, for one): this unfreeze is for feature cells only, and whether it
  releases any of them was not asked. They are not released by it.

**R0's D4 and D5 have no owner yet, and it is settled here.** R0's candidate deltas D4 (a discovery record states
the domain it searched) and D5 (the CLI's resume text prints the latest handoff's note) were left for the proposal to
name owners for. The proposal names none. With E389 closed they are open and unowned today, and this row is where
their owners are settled. The ledger entries that E389 tracked (PAE and PAB, PAB-05 and PAB-06 among them) are
tracked by this row from this change.

The proposal's O-9, that SYS-01's text cited blockers that had closed, was not a question to the operator either: it
is a correction of fact, made in this change from the register (HOLD-20 and HOLD-21 closed on 2026-11-06; F15.5 and
F18.15 closed the same day, into STG-14 and E97; F25 is restored at V-01).

**What remains:** all of the feature-cell work, and everything frozen. Nothing is built by this change. The order of
building is the proposal's suggestion, not a decision (its section 4.3): the role-run arm first, then the shared
walker and report, then the first cell. The proposal says one design point must be settled before the arm: how a
feature cell expresses its treatment, the designer's D-2. On that suggestion the role-run arm waits on the designer's
answer to that point. The proposal also allows the walker and report in the arm's own pull request, and it runs the
skills cell on the raw arm.
