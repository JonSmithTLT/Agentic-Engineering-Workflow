# ADR-0004 — Controlled integration: validate, then publish by ref CAS

- **Status:** Accepted (M1)
- **Spec basis:** WC §8, §8.1, §13, invariants 4 and 6; KC §9.5; decision D-op-2; plan review §2
- **Nature:** Resolves semantic gap A1 by operator decision. The mechanism (git worktrees, plumbing) is an implementation choice.

## Decision

Each mutating Ticket gets its own worktree and branch, even in serial mode. Integration is a Lead-driven saga, and every phase is a recorded control transition:

1. **prepare**
   - Requires COMMIT_READY with every effective gate CURRENT, and a workspace fingerprint equal to the one gated at COMMIT_READY.
   - Commits the workspace; the committed tree must equal the gated fingerprint.
   - Merges it (`--no-ff`) onto authoritative commit H in a detached integration worktree, giving candidate M.
   - A conflict is recorded (`integration.status = conflict`) and never forced.
   - A protected path in H..M blocks integration.
2. **post-integration verification** — a Verifier invocation (scope `integration`) runs the policy's `post_integration.checks` against snapshot(M). Verification ingest then marks the integration `validated` or fails it.
3. **publish**
   - Phase 1 records `publishing {H → M}`.
   - Under the control-state lock, with Lead authority re-verified, it runs `git update-ref refs/heads/<branch> M H`. This atomic compare-and-swap is the single publication point.
   - A moved ref gives `stale_candidate`: rebuild and revalidate.
   - The authoritative worktree is synced by forcing exactly the paths in `diff(H, M)` to M. Other paths, including dirty `.aew/`, are untouched. A dirty path in `diff(H, M)` blocks publication beforehand.
   - Phase 2 marks the Ticket DONE and writes a Completion Record (WC §9.11).
4. **reconcile** — keyed on the recorded `publishing` status. It inspects git and never infers:
   - ref == H: perform the CAS;
   - ref contains M: finish sync and mark DONE;
   - anything else: the candidate is stale.

## Consequences

- The authoritative branch never holds an unvalidated integration.
- A downstream mutating dependency is satisfied only after DONE, and only when M is an ancestor of the downstream assignment's recorded base commit.
- A takeover and a publish serialize on the lock, so a superseded Lead cannot move the ref.
- Tested:
  - crashes after the publishing record, after the CAS, mid-sync and before DONE, each reconciled;
  - a third-party ref move producing a stale candidate;
  - a stale Lead refused;
  - a conflict recorded rather than forced.

## Amendment 2026-09-26 — independent review (B1, B2, M1, M6)

The review found that the normal-path checks above did not hold across recovery and regression compositions. These are implementation corrections; the decision (validate, then publish by ref CAS) is unchanged.

- **Entry-level sync validation (B2, M6).**
  - Synchronization compares complete Git entries, mode plus object id, for the authoritative **index** and **working copy** against H and M.
  - It never compares only blob content, and never uses `git diff`, which honours assume-unchanged/skip-worktree flags.
  - Before publishing, every path in `diff(H, M)` must be exactly H in both the index and the working copy.
  - After the CAS, every path is classified *before anything is written*. Each index entry and working copy must be H's or M's; around a file↔directory transition the empty intermediate state is also allowed. Anything else belongs to someone else, and the whole sync is refused with the paths named.
  - Paths flagged assume-unchanged or skip-worktree, unmerged entries and gitlinks are refused.
  - Materialization uses `git checkout M -- <paths>`, which writes index, content and mode; removals come first. The executable bit is compared only when `core.fileMode` is true, and symlinks honour `core.symlinks`.
  - Tested: a staged independent edit survives, executable-bit-only changes, file↔symlink, file→directory, deletes, index flags, an untracked file on an added path, and idempotent re-sync from every {H, M} index/worktree mix (`tests/integration/test_worktree_sync.py`).
- **One locked finalization (M1).**
  - Publication, worktree sync and DONE are a single Lead transaction. The current Lead credential, the expected control revision and the manifest pin are verified under the control-state lock **before** any ref or worktree side effect, and the lock is held until DONE commits.
  - A rejected call (stale authority or stale revision) therefore never moves the ref, and no other writer can interleave between publication and completion.
  - When the ref is still H, the strict pre-publication check is repeated under the lock immediately before the CAS.
  - A refused sync aborts the transaction. The status stays `publishing` even if the ref already holds M, and the error names the conflicting paths; `integrate reconcile` completes the work once they are resolved.
  - Fault points (`after_cas`, `mid_sync`, `before_done`) keep their names. Tested: `test_interleaved_writer_makes_finalization_stale_before_any_git_side_effect` and review probe M1.
- **Candidates are bound to the acceptance they came from (B1).**
  - Each entry into COMMIT_READY increments `commit_ready_seq`. `prepare` records `integration.binding = {plan revision + sha256, commit_ready_seq, gated fingerprint}`.
  - The binding is re-checked at integration-scope dispatch, post-integration verification ingest, publish, and finalization/reconcile. Before publication, a mismatch retires the candidate (`superseded`) and raises `STALE_CANDIDATE`. After publication, it is an operator-level contradiction; with the guard below it is unreachable.
  - A Ticket entering any state other than COMMIT_READY, DONE, INTERRUPTED, or VERIFICATION_FAILED (a post-integration failure awaiting classification) retires its open candidate to `integration_history`. The retirement is enforced in the single state-change path, so no transition can skip it. Re-preparing therefore works after a regression, and attempt numbers continue across history.
  - While a candidate is `publishing`, every state change other than DONE is refused: run `aew integrate reconcile` first.
  - At DONE, the Ticket workspace is removed only if its HEAD is the integrated Ticket commit and it is clean. Otherwise it is **retained**, and `status`/`resume` report it as a contradiction. Integration cleanup never deletes newer engineering output.
  - Tested: review probe B1, the regression → re-verify → publish-new-work composition, a refused state change while publishing, a retained workspace, and a superseded unbound candidate.

## Addendum 2026-09-26 — focused re-review of the remediation (B1 residual, M2 residual, R1)

- **Cleanup decides from content (B1 residual).**
  - Workspace removal at DONE no longer trusts `git status`, which honours assume-unchanged/skip-worktree.
  - `worktrees.inspect` compares HEAD's tree with a tree built from the workspace **content**: tracked plus untracked-not-ignored, `.aew/` included, built in the same flag-neutralized temporary index as the fingerprint. The real index flags are preserved.
  - Removal requires positive proof: HEAD is the integrated Ticket commit and the content equals it. Where content cannot be established (sparse entries), the workspace is retained ("content could not be verified") and reported.
  - `prepare` refuses a Ticket workspace whose index marks paths assume-unchanged/skip-worktree, because `git add` would silently leave those edits out of the Ticket commit. The flags are reported, never cleared on the user's behalf.
