**An input for this group's matching** (map v1.20 §7, item 3.4), from the designer's rulings of 2026-10-25 on the Lead's
friction log, batch 7 (B7-1, B7-3, B7-6, B7-7, B7-8). Nothing in batch 7 is built before V-01 (B7-S), with one
exception, in HOLD-15.

- **A flake is AEV-07.e's record of an unreliable check** (B7-1, with no new contract text).
  - **What it holds:** the check's identity and lane; its retained observations and the obligations it affects; the
    responsible investigation, which owns it; its mechanism, as links marked proven, supported or open; and its
    re-entry condition.
  - **Its rate** is derived at read from the observations, and never written into the record.
  - **The gate's attribution** is AEV-07.c's proportionate explanation. It compares the same lane at the first parent,
    the check's history, and the recorded classes; it reports, and never waives.
  - **A green re-run dismisses a failure only** when the failure is attributed to a recorded class whose mechanism is
    proven and does not lie in the change: AEV-07.b's demonstrated invalid test, or a failed environment. Otherwise the
    re-run is a diagnostic, and the failure stays open against the claims it affects (AEV-07.d). On a mandatory or
    security-relevant check, an open failure stays a contradiction (AEV-07.g).
  - **Class detection** reuses batch 5's M2 recurrence detector. The record is shown through A-10 (HOLD-10).
- **The review round's default shape** (B7-3), with A-04 (HOLD-04, where the shape is set out).
- **Findings carry a visibility** (B7-6, AEV-10's findings). A public text names only that a private finding exists.
  "Found in passing" reports default to private until they are classified against the threat model (W13).
- **A check that claims a property has an ablation in the suite that makes it fail** (log entry 35, AEV-04).
- **Ablations** (log entry 43, AEV-03). An ablation runner reports ERROR, HANG and BASELINE-FAIL apart from CAUGHT and
  MISSED, and never counts them as caught. In AEW an ablation is a record: its target, its anchor, and the test expected
  to fail.
