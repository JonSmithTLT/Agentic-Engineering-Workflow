**The generated reference's machine index is no longer committed (operator, 2026-11-05).**
`docs/reference/index.json` is git-ignored and removed from the tree; the pages stay committed and checked.

- **The decision.** The operator chose to stop committing the index and to keep the generated pages committed. Nobody
  edits or reviews the index (about 47,000 lines, 1.6 MB), yet every record-changing pull request had to commit it: in
  #330 it was about 12,800 of the roughly 13,000 changed reference lines. Its `counts.digest` line made any two
  record-changing pull requests conflict by design, and each conflict cost a re-render, a push and a CI run.
- **The designer's reading, the same day.** Nothing stops it and no amendment is needed, only this note. The
  generator's adopted shape stands: `render`, `check` and a CI equality check. The design side renders the index at a commit itself, from an
  archive of that commit, so `render` must keep running on a tree with no `.git`; a fast-lane test holds that
  (`tests/unit/test_reference.py`).
- **What stays the same.** `render` still writes `index.json` (git ignores it), for local use and the design side.
  `check` still renders everything in memory, the index included, and fails on any difference in the committed pages;
  a local index, absent, stale or current, is never compared. The pages are drawn from the in-memory index, so they
  carry what it measures.
- **What the digest guarded, now.** Two pull requests that each edit a page's total to the same text can merge cleanly
  into a stale total. `check` on the merged code fails on it, because it compares the pages with a render of that code:
  a pull request's CI runs on its merge with `main`, a check of the merge result before merging finds it, and `main`'s
  push run is the backstop. A planted stale total is one of `check`'s wrong cases.
- **S12-2's hand-off, amended in practice.** The hand-off's "counts in `index.json` and in each PR" is now "counts
  printed by CI for each PR": the `static` job runs `python tools/reference.py counts` and puts the counts in the run's
  summary (reported, never gating). A pull request description still quotes `counts` when it adds records.
