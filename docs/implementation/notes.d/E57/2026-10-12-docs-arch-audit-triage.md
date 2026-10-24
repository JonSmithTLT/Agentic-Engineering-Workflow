**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-07).** Still present:
`record_freshness` is called only from the non-mutating paths and the dashboard (`src/aew/engine/nonmutating_ops.py`,
`src/aew/dashboard/projections.py`), never from dispatch, and plan acceptance still records a source commit only for
parents (`src/aew/engine/work_ops.py:618-619`). Not covered by an in-flight plan: the vertical path's A2 (F47.1) gives
`work acknowledge-input` and `plan reconfirm` typed homes, which would be the clearing paths for a blocker, but adds no
blocker. Priority (P2), owners and target are unchanged; routing only, under the feature pause.
