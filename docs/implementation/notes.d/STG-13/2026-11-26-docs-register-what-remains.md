**What remains** (2026-11-26): only the #213 hang diagnosis's test-fixture fix on Linux
(`tests/acceptance/test_vertical_path.py`, operator `G3-213`), which #307's note says fails with the Lead contained
(its autopsy finds no TUI `events-*`). It is tracked by V-01 cluster C15's row in open pull request #601, pending its
review and merge; this row closes in a follow-on once #601 merges (the operator, 2026-11-26, and the review of #600,
M1). **Done:** the oracle rebuilt and the frozen instrument retired in one pull request, #306 (`efc98baa`); the Linux
lane measuring again, #307; the Lead's containment minimums raised, #308. Switching `VERTICAL_MODE` to `enforce` is
the operator's decision, outside this row.
