# ADR-0011 P2d independent review

## Target and scope

- PR #21: `JonSmithTLT/Agentic-Engineering-Workflow`, `impl/adr-0011-p2d-migrate`.
- Current reviewed head: `1d79d19c880c091b7e07df531733fb4577e73b8e`; base: `c62be57a08f97c3e15d52a722b8aab700b5b365e` (merged P2c, including its fixes).
- Source was initially frozen with `git archive` at `c5f7e8ac793a278db74207cc171133e0ade8dbbc`, against `abb9096b3b91f8ec92a9d2beed478aa7cac89833`, into `AEW-P2d-review-c5f7e8a-1adc83`; the base is extracted under `base/`.
- The branch was rebased during review. Verified **whole-tree identity**, rather than assuming rebase equivalence: both target commits have tree `06bf5714b99c7b35e6ec70580aeeb637bc7e625c`; both base commits have tree `4075caa9f4e3ade27e043f226b3ad51a01d19845`. Thus the frozen executable source and reviewed 19-file diff are identical to PR #21's rebased source and diff. GitHub metadata confirms its head is `1d79d19` and base branch is `main`.
- Read the PR description, ADR-0011, R3/R8 and migration/schema/history requirements in the implementation plan, P2d as built, and all 19 changed files. Reviewed migration and store/finalizer composition, v1 refusal/seat exceptions, live-run checking, parent evidence aliases, schemas/ports, fingerprinting, perf fixtures/tooling, tests and docs.
- Created a private Windows Python 3.13 environment, installed this copy with `[dev,parallel]`, and confirmed AEW imports resolve inside this frozen copy. Ran fast, full non-serial and serial lanes in order, and independent disposable probes.
- The active checkout was used only for read-only Git commands. No source/test implementation files there, its environment, or any PR/branch were modified. Windows subprocesses were hidden with `CREATE_NO_WINDOW`.
- The plan's operator-approved choices are accepted: profiling migration time in P3, the existing-test edits, and CI's H1 points of 250/1,000 with acceptance at 250/3,000 deferred to P3. They are not findings.

## Recommendation

**Request changes for the two verified Medium/P2 findings below.**

## Findings

### P2d-1 — Medium / P2: An allowed handoff after a prewrite crash makes migration permanently refuse its orphan Lead archive

Location: `src/aew/engine/archive_ops.py:253-258`, especially the new `prewrite=prewrite` path at line 258; migration invokes it at `src/aew/engine/migrate_ops.py:79-80`.

Migration prewrites the ended Lead credentials to a path determined by the next `lead_archive` counter, but that counter is not committed if migration crashes before its commit point. Recovery correctly leaves v1 state and the unreferenced file. A Lead handoff remains explicitly allowed on v1 and changes both the generation and ended credential set. The next migration reuses the same path for different bytes. `history.store.prewrite` refuses the collision as immutable content, leaving the project on v1 with its work mutations still blocked.

**Actually executed through the CLI**, in a disposable v1 project with no work or runs:

1. Acquire generation 1, then offer/accept a cooperative handoff to generation 2. The project now has ended Lead/offer credentials to archive.
2. Run migration with `AEW_FAULT=history.after_prewrite`: the process exits 86 after writing `history/lead/000001.yaml`.
3. Recover with a fresh read: the control schema remains `aew/control/v1`; the Lead archive is present but unreferenced.
4. Offer/accept another cooperative handoff. Both commands succeed, producing generation 3; the orphan file remains unchanged.
5. Retry `aew migrate` with the new valid Lead token and current revision. It exits 6 with JSON:

   ```json
   {
     "code": "INTEGRITY_ERROR",
     "message": "history/lead/000001.yaml already exists with other content; history records are immutable",
     "details": {"path": "history/lead/000001.yaml"}
   }
   ```

6. Control state is still v1. No supported migration recovery path reconciles that file.

Positive control: in another otherwise equivalent project, crash at the same point and retry **without** the intervening handoff. Migration succeeds, archives both ended credentials, and the invariant oracle passes.

This is not file corruption or an operator rewriting authority: every state-changing action is permitted by the new v1 policy, and the orphan was created by the migration itself. R8's deterministic retry assumption holds only while the source state stays unchanged; the approved seat exceptions invalidate it. Treat proven unreachable prewrites safely when retry state changes, or use an identity/path that can coexist with earlier uncommitted content. Preserve the refusal to overwrite reachable immutable records. Add crash → allowed seat transition → retry coverage, including the ended-credential bundle.

Evidence: `review_p2d_probes.py`; `review-p2d-probes.jsonl`, `lead_handoff_after_prewrite` and `same_state_retry_control`.

### P2d-2 — Medium / P2: Migration's recent ring drops the latest finished work in favor of older, higher IDs

Location: `src/aew/engine/migrate_ops.py:79-80`; the existing finalizer orders by depth/ID at `src/aew/engine/archive_ops.py:175-176` and truncates its recent list at line 226.

Running the finalizer once over all v1 terminal work preserves archival dependency order, but it also treats that order as completion recency. For unrelated Tickets, this chooses the 20 highest IDs regardless of when they finished. Normal v2 archival builds the ring across finishing commits, so the new migration path does not give the same recent projection. Default `resume` and unfiltered `work list` consume this ring and can omit the most recently completed item immediately after migration.

**Actually executed**, with real creation, dispatch, submission, ingest and acceptance transitions:

1. Create 21 non-mutating v1 investigations, `T-0001` through `T-0021`.
2. Finish them in reverse creation order: `T-0021` first, `T-0001` last. The invariant oracle passes before migration.
3. Migrate successfully. The resulting `recent` IDs are `T-0002` through `T-0021`.
4. Both ordinary `resume` and unfiltered `work list` omit `T-0001`, the latest completion, and retain `T-0021`, the oldest. The post-migration invariant oracle also passes.

The records themselves remain in history; this is incorrect default reconstruction, not data loss. The claim that summaries and `recent` follow as if work had been archived when it finished is not met. Select migration's bounded recent projection by recorded completion time, independently of the deepest-first archive write order. Keep ordinary future commits bounded. Add a regression with more than the ring capacity and different creation/completion orders.

Evidence: `review_p2d_recent.py`; `review-p2d-recent.jsonl`, including actual completion order/dates and the two public view results.

## Independent evidence

- `review_p2d_probes.py` / `review-p2d-probes.jsonl`: prewrite crash, allowed handoff and failed migration retry; unchanged-state retry control; empty-project migration and idempotent second call.
- `review_p2d_composition.py` / `review-p2d-composition.jsonl`: a closed Story with DONE/CANCELLED Tickets under an open Epic and a second open Story; full reconstructed-state preservation; parent/subtree summaries; regeneration of a parent pack before/after migration; successful late ingest of a pre-migration parent review; full audit and invariant oracle.
- The same composition script compares target and base fingerprint implementations on five cases: clean tracked `.aew`, dirty source with tracked/untracked `.aew`, policy-declared ignored input, a source exclusion, and a staged-only source edit. All trees match and the real Git index is unchanged. A separate positive check confirms `working_tree_id` still sees `.aew` changes.
- `review_p2d_recent.py` / `review-p2d-recent.jsonl`: 21 actual completed investigations, migration and public recent views.
- Final successful probe executions have empty corresponding `.stderr` files. An initial recent-view probe used the wrong response field (`work` instead of `items`); corrected it and reran the full scenario. That helper failure is not a finding.
- Probe projects are retained inside this review copy. No implementation files were modified. The perf template's in-process `legacy_v1_writes` setting constructs v1 fixtures; it is not a CLI bypass used to perform the crash/handoff/retry sequence.

## Test results

All requested Windows lanes completed in order, with no repository-test failures:

| Lane | Pytest arguments | Result | Time | Log |
| --- | --- | --- | --- | --- |
| Fast | `-q -p no:cacheprovider -p no:xdist --lane fast` | 620 passed, 1 skipped, 564 deselected | 19.73 s | `review-fast.log` |
| Full non-serial | `-q -n auto -m "not serial"` | 1,163 passed, 5 skipped | 1,257.41 s | `review-nonserial.log` |
| Serial | `-q --lane serial` | 16 passed, 1 skipped, 1,168 deselected | 29.44 s | `review-serial.log` |

The disjoint non-serial and serial lanes total **1,179 passed and six skipped**. Fast overlaps non-serial and is not added to that unique count. All eight migration tests and the new H1 regression passed, as did the existing/default-budget regression and adversarial tests. The independently reproduced defects above are not failures covered by the existing repository suite.

Skips:

- Non-serial: three POSIX worktree filemode/symlink cases (`test_worktree_sync.py:170,185`), one POSIX filemode regression (`test_review_2026_09_26.py:98`), and the tagged-Git-revision check (`test_spec_pin.py:61`).
- Serial: the POSIX pty operator path (`test_authority.py:200`).
- The Git-revision skip is expected for the required Git-archive source freeze; the other five skips concern Windows platform behavior.

The runner `run_review_lane.py` asserts this private interpreter and source path before calling pytest, and adds `CREATE_NO_WINDOW` to Windows subprocesses. It does not change test assertions.

All 19 changed files were byte-compared with both the original and rebased target blobs after execution: no mismatches. `git diff --check` for the reviewed base/head is clean. Target and base whole-tree IDs prove the rebase made no source changes; the results apply to the source of PR #21 at `1d79d19`.

## What was checked and found sound

- **Migration transaction:** credential/revision/manifest checks and live-run refusal precede archival. It holds the normal store lock and commits through the existing single control-state commit point. Prewritten bundles are hash-checked before commitment and represented by a bounded count/hash in hot `last_transition`; the full listing stays in the redo record.
- **Unchanged-state crash/retry:** the independent prewrite retry control passes. The repository migration crash matrix passed for all 11 fault points, including a 256-unit segment seal. The state-change gap is P2d-1.
- **Preservation and hierarchy:** the independent mixed hierarchy preserves every unit/invocation/token after reconstruction, apart from intentional added summaries/hash/alias fields. Migration archives three DONE units and one CANCELLED unit, retains two open parents, and the Epic's transitive Ticket counters are correct. Full audit and invariant oracle pass.
- **Parent evidence aliases:** the repository tests cover already-ingested review/verification, invalidation after adding a child, and a classified `LOCAL_IMPLEMENTATION_DEFECT` still requiring remediation. The independent late-ingest probe covers the third alias comparison path. Parent pack regeneration continues to match its recorded hash.
- **Empty/idempotent migration:** an empty v1 work state migrates with zero history entries; a second call returns `migrated: false` without changing revision.
- **v1 refusal:** the new error is a normal JSON `AEWError` with `next_action`; work mutations through `lead_txn` are refused. The explicit migration-enabling seat/invocation-cancellation/manifest exceptions were reviewed; cooperative seat transitions were executed independently. No CLI flag/environment path to the perf-only kernel override was found.
- **Fingerprint semantics:** target and base tree identity was executed for the five cases listed above, including real-index preservation. Existing source/index-flag tests are part of the full suite. The PR's reported speedup and idle-machine P3 performance thresholds were not independently measured here.
- **Perf/test/doc changes:** reviewed separate migrated projects per scale point, hot aggregate/cold footprint accounting, the new H1 regression, API/port composition, quickstart/status and operator decisions. The smaller approved CI points are not presented as P3 acceptance evidence.

## Validation limits

The test environment is Windows, with disposable fixtures built using the project's v1 perf template and real engine/CLI transitions. This review does not certify every production v1 snapshot. Linux/Rocky, live models, extended nightly budgets, P3 sweeps/profiling and acceptance thresholds were not run. No independent reconfirmation of all six earlier P2c reproductions is claimed; P2c fixes are part of the base and its expanded repository tests run in the full suite.
