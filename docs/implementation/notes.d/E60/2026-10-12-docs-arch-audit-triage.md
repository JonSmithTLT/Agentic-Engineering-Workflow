**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-13).** Still present:
outside the coordination layer, `coordination_unseen` is named only as a control key (`src/aew/engine/base.py:39`) and
in the control schema; no projection, `status`, `resume` or dashboard reads it. **Partly covered** by the vertical
path's A1 (F47.1): its handoff serves unseen messages first, and `message unseen` becomes engine-owned, which puts a
reader in the Lead's attention path. The projection decision and the wake stay with F43 S2 and S3 and F9's reply
slice. Priority (P3) and target are unchanged; routing only, under the feature pause.
