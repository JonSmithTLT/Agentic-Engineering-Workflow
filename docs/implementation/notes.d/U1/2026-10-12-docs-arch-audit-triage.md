**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-16).** Still present:
no run carries a health field, and `harness_wait` returns only on a run's end, its invocation leaving `active`, or the
timeout (`src/aew/engine/harness_ops.py:394`), so a stall with a fresh heartbeat stays invisible. Not covered by an
in-flight plan. Target unchanged; routing only, under the feature pause.
