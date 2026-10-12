**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-11).** Still present:
`max_steps` is projected only as OpenCode's per-agent `steps` (`src/aew/harness/opencode/projection.py:155-156`),
which the harness resets at each promoted input, and no supervisor reads the live step meter to stop at the bound.
Not covered by an in-flight plan. The operator's acceptance of 2026-10-10 stands; the join is for when this row is
revisited. Routing only, under the feature pause.
