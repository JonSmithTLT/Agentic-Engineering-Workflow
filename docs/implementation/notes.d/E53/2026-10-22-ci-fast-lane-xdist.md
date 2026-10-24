**The premise flags timing-dependent lines, whatever the mode (#232, review finding F6, 2026-10-22).** `core`'s fast
step now runs under xdist, and so does `fastbase`, with exactly its flags (a guard in `test_ci_tools` compares the two
steps). Both sides of the premise are therefore measured the same way. That closes the half of F6 caused by a
single-process base against an xdist head.

The other half remains, and this PR does not cause it. On WSL, the whole fast lane was run twice under coverage at the
same commit, both runs with the same xdist flags. `coverage_premise` still reported a **LOSS** in each direction:
- `harness/opencode/adapter.py` 616-617 (the server gone during a poll), base the first run, head the second;
- `harness/usage_live.py` 539-540, the other way.

These are lines the fast lane does not cover deterministically. A fast-tier PR that changes nothing in `src/` can
therefore read as an unexplained loss. That is this row's gate for PR 1b (`mode: enforce`).

Before enforcing, decide how the premise treats such lines: make the tests behind them deterministic, or report the
base's unstable lines separately (lines two runs of the base disagree on, or a pinned list a test owns). Owner: this
row (CI plan v7 §5).
