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
