**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-03 to AX-05).** All
three are still present.

- **AX-05 (S1):** `next_actions` (`src/aew/engine/resume_ops.py:73`) still lists stage intents but no anomalies,
  dispositions or unseen replies, and the dashboard's `attention_items`
  (`src/aew/dashboard/projections.py:494-530`) still lists none of anomalies, stage intents, dispositions or queue
  states. **Partly covered** by the vertical path's A1 (F47.1), as the earlier note says: `resume` and the dashboard
  read one engine-generated handoff, and `/attention` maps the projection's items. The dashboard's project-health
  derivation is not named there, so S1 is not wholly absorbed until it is.
- **AX-04 (S2):** the derived kinds are still the nine of ADR-0012 D2 (`src/aew/engine/outbox.py:59-66`). **Partly
  covered** by the vertical path's A3a (F47.2), which adds derived kinds for a unit's plan, evidence, findings,
  integration, stage intents and anomalies, as an additive ADR-0012 D2 amendment. Steering, dispositions and
  `coordination_unseen` are not among them, and A3a does not move the notifier off its own derivation; both stay S2's.
- **AX-03 (S3):** the `--any` control lane still ends only when a target invocation leaves `active`
  (`src/aew/engine/harness_ops.py:428-439`), so a Lead with no live run has nothing to wait on. **Not covered** by
  any in-flight plan.

Order, priorities and target are unchanged (S1, then S2, then S3, after F44); routing only, under the feature pause.
