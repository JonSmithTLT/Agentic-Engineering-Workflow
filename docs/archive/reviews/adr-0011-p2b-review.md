# ADR-0011 P2b independent review

## Target and scope

- Target: `impl/adr-0011-p2b-archival`, commit `bff9671c063830d1f70d5017ec4a6925df921bb1`.
- Base: P2a commit `64c5a22fd91d4c5e3cb422f34935b1f1ee56b3e2`.
- Reviewed the 36-file diff, finalizer/store projection, summaries and frontiers, dependency facts, moves, credentials, historical reads, schemas, oracle additions, and changed tests.
- Source was frozen using a Git archive. The active P2a checkout and its uncommitted fixes were not changed or included.
- The six previously reported P2a findings are inherited base issues, not new P2b findings. This review does not confirm the in-progress P2a fixes. Rebase integration still needs validation after those fixes land.
- Recommendation: request changes for the four new findings below.

## Findings

### P2b-1 — Medium / P2: Historical reads omit archived ancestors

Location: `src/aew/engine/archive_ops.py:459-469`, especially the projection at line 467.

`rehydrate()` restores only the requested unit and its invocation/token records. Its callers still traverse ancestor work records through `H.ancestors()` and `G.ancestors()`. Once a Story or Epic is archived, the restored child's parent is absent from `state.work`.

Independent CLI sequence:

1. Create and plan a Story; create an investigation under it.
2. Dispatch, submit, ingest and accept the investigation, archiving it.
3. With the Story still hot, `context pack INV-0001` succeeds with `matches_recorded: true`, and `gate show T-0001` succeeds.
4. Review, verify and close the Story, archiving it too. The invariant oracle passes.
5. Repeat those two reads. Both exit 1 with an uncaught `KeyError: 'S-0001'`. Context fails in `hierarchy.ancestors`; gate evaluation fails in `gates.ancestors`.

This breaks the promised cold fallback for ordinary completed hierarchies (R7). Restore the required ancestor context or make these traversals resolve archived ancestors on demand. Keep reads bounded to the requested ancestry; avoid loading the whole history. Add regressions for both closed Stories and closed Epics.

### P2b-2 — Medium / P2: A crash loses the observation cleanup obligation

Location: `src/aew/engine/archive_ops.py:143-153`, particularly line 153; `src/aew/engine/base.py:214-218`.

Observation removal is queued only in `ctx.after_commit`. The commit removes the owning invocation from hot state. Recovery replays durable writes but has no record of this callback; later `prune_observations()` scans only hot invocations and cannot discover this worktree.

Independent CLI sequence:

1. Dispatch a running investigation with an existing observation worktree.
2. Cancel it with `AEW_FAULT=history.after_bundle` (real process termination, exit 86).
3. A fresh `work show` recovers the complete cancellation and archival. The invariant oracle passes.
4. Execute a checkpoint. The invocation is absent from hot state, but its observation directory and detached Git worktree remain.

The positive control dispatched and cancelled a second investigation normally: its observation was removed, while the earlier orphan survived that later dispatch/prune/cancellation sequence. `status --json` reported no contradictions. A failed removal is also swallowed and loses the same retry information. Persist a bounded cleanup obligation until removal succeeds, or otherwise provide recovery that can retry without sweeping archived bundles. Extend crash coverage to assert filesystem cleanup, not only control-state invariants.

### P2b-3 — Medium / P2: Current work views retain the original parent after archived moves

Location: `src/aew/engine/work_ops.py:535-540`; the bounded projection is built in `src/aew/engine/archive_ops.py:149` and consumed by `src/aew/engine/hierarchy_ops.py:587-591`.

The move annotation and parent summaries are updated correctly, and `work show` applies the annotation. However, terminal-state `work list` copies the parent from the original manifest entry; unfiltered listings, resume and the default tree use the unchanged `recent` entry.

Independent CLI sequence:

1. Complete an unparented investigation, archiving it.
2. Create a live Story and move the archived investigation under it.
3. `work show T-0001` returns `parent: S-0001`, and the Story's archived-child count is 1. The invariant oracle passes.
4. `work list --state DONE` and `resume --json` still return `parent: null` for that Ticket.
5. The default `work tree` incorrectly renders it as a separate root, beside the Story whose summary already includes it.

Apply move annotations to the current work listing, and update the bounded recent projection when a move commits. Keep immutable archive entries unchanged. Test both moves into a parent and moves back to the root, including repeated moves.

### P2b-4 — Medium / P2: The new index snapshot boundary is applied inconsistently

Location: `src/aew/history/index.py:140-143`, `149-161`, `180-190`.

P2b introduces `sync(old_root)` returning `ahead` and promises that queries stop at that root. `_rows()` filters by sequence only after SQL runs. With a listing limit, SQL first selects newer entries outside the snapshot and the Python filter then drops them. `links()` and `paths()` bypass the filter completely.

Independent store/index sequence:

1. Archive T-0001 and save that root. Sync the index; `list(limit=1)` returns T-0001, `links(T-0001)` is empty, and `paths()` contains only its bundle.
2. Archive T-0002, which depends on T-0001, and sync the shared index to the new root.
3. Sync the same index object back to the saved root: mode `ahead`.
4. Unlimited listing correctly returns only T-0001, but `list(limit=1)` incorrectly returns `[]`.
5. `links(T-0001)` leaks T-0002's dependency link, and `paths()` includes T-0002's bundle.

Apply the sequence boundary inside SQL, before sorting/limiting, and to every query, including link and path queries. Add an ahead-cache snapshot regression covering each public query method. This is a new P2b regression, separate from the inherited P2a cache-rebuild findings.

## Independent evidence

- `review_p2b_probes.py`: executable CLI and index sequences; uses only disposable fixture projects.
- `review_p2b_probe_results.jsonl`: complete results, positive controls, error traces and filesystem/Git observations.
- No implementation files were modified to create these reproductions.

## Validation

- Windows project interpreter; the frozen snapshot's `src` was first on `sys.path` and exported through `PYTHONPATH` for subprocesses.
- Unit tests plus archival, hierarchy, non-mutating and resume integration tests: **645 passed in 96.99 seconds** (`-n 8 -m "not serial"`).
- Authority, context-pack, harness-run and Lead-session integration tests: **37 passed in 206.63 seconds** (`-n 4 -m "not serial"`), recorded in `review_p2b_authority_tests.txt`.
- Modified regression walks, M2 compositions, M3 intent ingress and history-store integration tests: **75 passed in 581.74 seconds** (`-n 8 -m "not serial"`), recorded in `review_p2b_regression_tests.txt`.
- Total selected repository tests: **757 passed** across the three disjoint batches. Independent probes reproduced all four findings and their positive controls.
- Verified all 36 changed files in this snapshot still match the target commit; local and remote-tracking branch refs still point to `bff9671`.
- `git diff --check 64c5a22 bff9671`: clean.
- Full suite, serial lane, Linux/Rocky, nightly and live-model validation were not run. Selected test success does not override the independently reproduced failures.
