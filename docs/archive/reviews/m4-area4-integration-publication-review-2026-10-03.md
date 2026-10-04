# AEW independent review — Area 4: integration and publication

- **Date:** 2026-10-03
- **Reviewed commit:** `a6cdc64` (merge of PR #32 on `main`), frozen clone at `AEW-reviews/integration-publication-a6cdc64/tree`. Line numbers are from that commit.
- **Scope:** `src/aew/engine/integration_ops.py`, `src/aew/workspace/integration.py`, `src/aew/workspace/worktrees.py`, read against ADR-0004 (controlled integration). Supporting code read where a guarantee depends on it: `workspace/git.py`, `snapshot/fingerprint.py`, `engine/evidence_ops.py` (gate context, binding, bound reports, verification ingest, integration-scope dispatch), `engine/work_ops.py` (`set_state`, `before_commit`), `engine/lead_ops.py` (interruption), `engine/transitions.py`, `engine/base.py` (`lead_txn`), `engine/store.py`.
- **Environment:** Windows 11, Python 3.13.1, git 2.46.0.windows.1, own venv (`venv/`), tests run only in this checkout. Baseline: `tests/integration/test_integration.py` and `test_worktree_sync.py` pass here (22 passed, 3 POSIX-only skips, 7 min). Linux reproduction was not needed: nothing found is platform-specific to Linux. R2 is specific to case-insensitive filesystems.
- **Reproductions:** `repro/test_area4_repro.py` (run from the review folder: `venv/Scripts/python -m pytest repro/test_area4_repro.py -q -p no:cacheprovider --rootdir repro`), `repro/time_sync.py`. Logs: `repro/run-r1-r3-r4.log`, `repro/run-r3-r4.log`.
- **Independence:** `aew-private`, earlier review responses and triage notes were not read.

## Questions from the brief

| Question | Answer |
|---|---|
| Can a candidate be published that is not bound to the accepted, verified state? | No. Binding (plan revision + sha, `commit_ready_seq`, gated fingerprint) is checked at phase 1 and again under the lock before the CAS; the post-integration report must be from an integration-scope invocation of this candidate and attempt, under the current plan, with the candidate's fingerprint and the policy's checks under current definitions; obligations are re-evaluated at the accepted snapshot. Sound. |
| Crash at each fault point: always recoverable with reconcile, never half-published? | Each named fault point reconciles (confirmed by the existing suite here). Two ways to make `publishing` permanent were found: an operator commit on a changed path after a post-CAS crash, where the refusal's own advice leads into the dead end (F1); and a candidate whose integration worktree is gone, which cannot be published or re-prepared (F3). A leftover ref lock discards a validated candidate as "stale" (F2). |
| Can the worktree sync overwrite the operator's local work? | No overwrite found. Classification compares complete index and working-copy entries against H and M before any write, and refuses otherwise. Residuals: a case-only rename is refused as the operator's "local change" on case-insensitive filesystems (F4, fails closed); an edit made between classification and `git checkout` is not protected (inherent; see notes); a second worktree on the authoritative branch is not synced at all (notes). |

## Findings

### F1. Major — after a crash past the CAS, following the refusal's advice leaves the Ticket published but permanently `publishing`

- **Where:** `src/aew/workspace/integration.py:292-302` (`_classify_for_sync` admits only H's and M's entries), `integration.py:329-333` (the refusal says "commit/stash it ... then run `aew integrate reconcile`"), `src/aew/engine/integration_ops.py:299-320` (reconcile path when the ref already contains M), `integration_ops.py:52-57` (every state change except DONE refused while `publishing`).
- **Guarantee:** ADR-0004 "reconcile ... ref contains M: finish sync and mark DONE"; the amendment's "a refused sync aborts the transaction ... `integrate reconcile` completes the work once they are resolved".
- **Scenario:** publish crashes after the CAS (`integrate.after_cas`); the ref holds M. The operator, seeing their checkout show the Ticket's paths as modified, edits one of them and runs reconcile: refused, correctly, with "commit/stash it, then reconcile". They commit it, as advised. Now HEAD is X on top of M and the path's index and working-copy entries are X's, which is neither H's nor M's, so every reconcile is refused for ever. While `publishing`, `work transition` and `work cancel` are refused too, and a Ticket that depends on A stays BLOCKED although A's output is on `main`. The only way out is undocumented git surgery (`git checkout M -- <path>`, reconcile, restore X) or hand-editing control state.
- **Fix:** when the ref already contains the candidate, treat a path whose index and working-copy entries equal the current authoritative HEAD's entry as converged (a later commit has superseded M on that path; nothing of M's is lost since M is in the lineage). Make the post-CAS refusal say "stash" or "restore to the published commit", not "commit". Consider letting `aew integrate reconcile --accept-worktree` finish a publish whose ref is right while the operator keeps their newer content.
- **Reproduced:** yes, `test_r3b_after_a_post_cas_crash_the_advised_commit_leaves_the_ticket_stuck_in_publishing` (`repro/run-r3-r4.log`). Confidence: high.

### F2. Minor — any `update-ref` failure is recorded as "the ref moved" and discards the validated candidate

- **Where:** `src/aew/workspace/integration.py:102-108` (`cas_publish`), `src/aew/engine/integration_ops.py:294-305` (the `StaleCandidate` is committed as `stale_candidate`).
- **Guarantee:** ADR-0004 "A moved ref gives `stale_candidate`"; a validated candidate should be retired only when its base is gone.
- **Scenario:** a leftover `refs/heads/main.lock` (a git process killed mid-write, an editor's git integration) makes `update-ref` fail. The ref did not move: the error's `current` equals `expected`. The candidate is nevertheless committed as `stale_candidate`, so the Lead must re-prepare and re-run post-integration verification for a candidate that was valid, and the reported cause is wrong.
- **Fix:** after a failed `update-ref`, re-read the ref; raise `StaleCandidate` only when it differs from `expected_old`, otherwise raise `GitError` and leave the record as it was (`validated`, or `publishing` for reconcile).
- **Reproduced:** yes, `test_r1_update_ref_failure_with_unmoved_ref_is_recorded_as_stale_candidate`. Confidence: high.

### F3. Minor — a validated candidate whose integration worktree is gone can neither be published nor re-prepared, and publish crashes

- **Where:** `src/aew/engine/integration_ops.py:164-170` (`_post_integration_ok` re-snapshots the integration worktree), `integration_ops.py:103-104` (`prepare` refuses while a validated candidate exists), `src/aew/workspace/git.py:30` (a missing `cwd` raises `NotADirectoryError` / `FileNotFoundError`, not `GitError`).
- **Guarantee:** ADR-0004's saga is Lead-driven and every phase is recoverable by a recorded transition; the brief's "crashes".
- **Scenario:** the integration worktree under `workspaces_root` is removed (disk cleanup, a stray `git worktree prune` after a move). `integrate publish` dies with a Python traceback instead of an AEW error (no state change, since the exception leaves the transaction). `integrate prepare` refuses: "already has an integration in state validated". There is no `integrate discard`. The only path forward is a regression to RUNNING, which retires the candidate and requires review and verification again.
- **Fix:** in `prepare`, allow replacing a candidate whose worktree no longer exists (or add `integrate discard`); in `git()`, turn `OSError` on `cwd` into `GitError` so the CLI reports it.
- **Reproduced:** yes, `test_r4_a_validated_candidate_whose_worktree_is_gone_cannot_be_published_or_re_prepared`. Confidence: high.

### F4. Minor — a case-only rename can never be published on a case-insensitive checkout, and the refusal blames the operator

- **Where:** `src/aew/workspace/integration.py:182-208` (`worktree_entries` uses `is_file()`/`is_dir()`, which resolve the new name to the old file), `integration.py:266-278` (`precheck_sync`).
- **Guarantee:** the amendment's "Before publishing, every path in `diff(H, M)` must be exactly H" — the worktree is exactly H here.
- **Scenario:** a Ticket renames `Foo.txt` to `foo.txt`. `diff(H, M)` lists both. In the authoritative worktree, which is exactly H, `foo.txt` resolves to `Foo.txt`, so the precheck sees content at a path H does not have and refuses with "local change (staged or unstaged)". Nothing is written (fails closed), but the candidate is unpublishable on Windows and macOS and the message sends the operator looking for an edit that does not exist.
- **Fix:** detect paths that differ only by case within `changed_paths` and either handle them as one removal-then-add with a case-aware existence check (`os.listdir` of the parent, exact name match) or refuse up front with a message that names the platform limit.
- **Reproduced:** yes, `test_r2_case_only_rename_is_refused_as_a_local_change` (Windows). Confidence: high.

## What looks sound

- **Binding of the candidate to the acceptance.** `commit_ready_seq` increments only in `_commit_ready`; `binding_problem` is checked at integration-scope dispatch, verification ingest, publish phase 1 and finalization; a mismatch before publication retires the candidate, and after publication is a reported contradiction.
- **Bound validation.** `_require_bound_validation` requires the recorded report to be a pass on the candidate's fingerprint, produced by an integration-scope invocation for this workspace and attempt under the current plan, citing policy checks that passed on the same fingerprint under current check definitions.
- **Obligations re-evaluated at the accepted snapshot**, at phase 1 and again under the lock; an unmet one withdraws the intent back to `validated` while the ref is still H.
- **One locked finalization.** Authority, revision and manifest pin are verified before any git side effect; the CAS (`update-ref ref M H`) is the single publication point; the lock is held through sync and DONE. A superseded Lead and a stale revision are refused before the ref moves (confirmed by the existing suite here).
- **Crash points.** `after_publishing_record`, `after_cas`, `mid_sync`, `before_done` all reconcile (suite passes here); staged writes (completion record) are applied by recovery.
- **Sync classification.** Complete entries (mode + oid) for index and working copy against H and M, never `git diff`; index flags, unmerged entries and gitlinks refused; removals before updates; idempotent from every {H, M} mix; executable bit and symlinks per `core.fileMode` / `core.symlinks`; untracked files on added paths refused.
- **Prepare.** Refuses assume-unchanged / skip-worktree and index-only content before `git add`; the committed tree is compared with the gated fingerprint after the commit; a conflict is recorded, never forced; protected paths in `diff(H, M)` block.
- **Retirement.** Leaving COMMIT_READY (except DONE, INTERRUPTED, VERIFICATION_FAILED) retires the open candidate, cancels its integration-scope invocations and revokes their credentials; `invocation_workspace` never retargets an invocation to a later candidate.
- **Two mutating Tickets cannot race the sync.** The mutating-concurrency guard refuses a second mutating assignment while the first holds an unintegrated workspace, so overlapping candidates are unreachable today (`test_r3_two_mutating_tickets_cannot_overlap_at_publish`).
- **Workspace cleanup at DONE** needs positive proof (HEAD is the Ticket commit, content and index equal it); otherwise retained and reported.

## Process, architecture and efficiency notes (outside the findings)

1. **The sync classifier assumes a single publisher.** It is exactly right under today's concurrency-1 guard. When "isolated concurrent integration" arrives, `_classify_for_sync` must admit entries from any commit between M and the current ref, or F1 becomes reachable without any operator action.
2. **One path bypasses `set_state`.** `lead_ops._interrupt_invocations` writes `unit["state"] = "INTERRUPTED"` directly (`lead_ops.py:107`), skipping the hooks ADR-0004 relies on ("enforced in the single state-change path, so no transition can skip it"). Harmless today because `_phase_waits_on` excludes a `publishing` record, but it is the one place the invariant is not structural. `dependencies.py:189` and `hierarchy.py:144` do the same for derived states.
3. **Post-CAS refusal text.** The pre-publish advice ("commit/stash") is right; the post-CAS advice should differ (F1). A single message serves both today.
4. **`validation_inconclusive` dead end.** Resume says "resolve the blocker and re-verify", but integration-scope dispatch requires `status == prepared` (`evidence_ops.py:481-483`) and ingest does too, so the actual next step is `integrate prepare` (which retires and rebuilds). Say so.
5. **Non-conflict merge failures are recorded as conflicts.** `merge_candidate` records `conflict` with an empty path list whenever `git merge` fails, including failures that are not conflicts (`integration.py:79-85`). Distinguish by `MERGE_HEAD` or by the unmerged list being empty.
6. **Only `repo_root` is synced.** If the authoritative branch is checked out in another worktree of the same repository, `update-ref` still moves it (git does not protect `update-ref`), and that worktree is left with M as HEAD over an H index and working copy. ADR-0004 should state that the authoritative branch must be checked out at `repo_root` or nowhere.
7. **Operator TOCTOU.** An edit made between classification and `git checkout M -- paths` is overwritten. Inherent to a non-exclusive filesystem; worth a sentence in the ADR so "nothing is overwritten" is read as "nothing present at classification time".
8. **Orphan worktrees.** A crash between the DONE commit and the post-commit `worktrees.remove` calls (`integration_ops.py:339-342`) leaves the integration and Ticket worktrees on disk with nothing scheduled to remove them (observations have `retired_observations`; candidates do not). `aew doctor` could list worktrees under `workspaces_root` that no hot record references.
9. **Lock hold time scales linearly.** `repro/time_sync.py` on this machine: precheck 2.1 s and sync 7.1 s for 2,000 changed paths (about 4.6 ms per path, dominated by git process spawns per 200-path chunk). Pollers (run supervisors, the Lead broker watchdog) read control state with a 60 s lock timeout, which a publish of roughly 13,000 changed paths would exceed; a supervisor then ends its run as `crashed`. Not a practical risk for Ticket-sized changes, but worth a bound: refuse or warn above a path count, or batch git calls with `--batch`-style plumbing.
10. **Test cost.** The integration lane runs each step as a separate CLI process; 22 tests take 7 minutes on Windows. An in-process `Engine` driver for the non-CLI parts of these flows would cut that several-fold without changing what is asserted.
