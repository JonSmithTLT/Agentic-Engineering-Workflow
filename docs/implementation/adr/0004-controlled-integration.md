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
- **Retirement ends write authority (M2 residual).**
  - Retiring a candidate (leaving COMMIT_READY, re-preparing, or a binding mismatch at publish or finalization) cancels every active integration-scope invocation of the Ticket and revokes its credential. The state-change path now receives the transaction's control state for this.
  - Integration invocations record the candidate they serve (`integration_attempt`, `candidate`).
  - **Every** submission kind (implementation report, review, verification) and every check run resolves the invocation's own workspace or candidate, and only while it is live, so a credential never outlives its assignment. Earlier reports remain durable history.
- **Reports are accepted only for the assignment they were produced for (R1).** The remediation made candidates replaceable, which exposed an ingestion weakness: a report compared only by engineering fingerprint could be accepted for a *different* attempt, plan or candidate with identical bytes.
  - At review/verification ingest, and again at publication (phase 1 and pre-CAS finalization), a report must have been produced under the Ticket's current accepted plan (revision + sha256).
  - Its producing invocation must have been dispatched for the current attempt's live workspace (ticket scope) or for the current candidate's workspace **and** attempt (integration scope).
  - Otherwise the report is refused with the mismatched bindings named. It stays durable history, and current work needs its own report.
  - The invariant oracle now also checks that a DONE Ticket's post-integration report came from that candidate's own verifier under the bound plan, and that no evidence postdates its producer's revocation.
- **Index-only work counts too (foundation review, `f3fc4a3`).** The content check built its tree with `git add -A` over a copy of the index, which overwrites staged entries with working-file content. A change that existed only in the index (staged, then the working file restored) was therefore invisible, and DONE cleanup deleted the workspace holding it.
  - `worktrees.inspect` now compares HEAD's tree with **both** the working content (flag-neutralized) **and** the index as staged (`fingerprint.index_tree_id`, written from a copy). Either differing, or either being unverifiable (sparse or unmerged entries), retains the workspace.
  - `prepare` refuses a Ticket workspace whose index holds staged content matching neither HEAD nor the working copy (`fingerprint.index_only_paths`). `git add` of the evaluated working state would overwrite it, and it exists nowhere else. A fully staged change (index == working copy) prepares normally.
- **Publication re-checks obligations at the accepted snapshot (foundation review).** `prepare` checked the Ticket's effective gates once, and publication re-checked only the integration evidence. An obligation added after validation (an operator-pinned review card, a new policy gate) was never enforced.
  - Publish phase 1 and pre-CAS finalization now re-evaluate every effective obligation **at the accepted (COMMIT_READY) snapshot**. The fingerprint comes from the gated snapshot, and guardrail triggers from the committed Ticket diff, so later workspace edits cannot change the answer.
  - When finalization finds an unmet obligation or an unbound validation while the ref is still H, it **withdraws** the publish intent back to `validated` and reports the reason. The Ticket is never held in `publishing`, where state changes are refused, over something the Lead must act on.
  - Only a Ticket whose integration record is still valid can publish; `prepare` refuses non-mutating Tickets.

## Amendment 2026-10-04 — independent review of integration and publication

- **A reconcile after the CAS keeps a later commit.** When the ref already contains the candidate M and has moved on (the operator committed on top), a path whose index and working copy hold exactly the current HEAD's entry is settled by that commit and left as it is. M stays in the lineage. The result lists those paths (`worktree_sync.settled_by_later_commit`), so the operator can check that the later commit kept what the integration changed. A refusal after the CAS says to stash the local work or restore the paths to the published commit, never to commit it.
- **A failed CAS is classified by re-reading the ref.** `stale_candidate` is recorded only when the ref moved. A failure with the ref unmoved (for example a leftover `main.lock`) is a git error: the record stays `publishing`, and `aew integrate reconcile` publishes once the cause is gone.
- **A lost integration worktree is recoverable.**
  - Publish refuses with `GATE_UNSATISFIED`, naming `aew integrate prepare`.
  - `prepare` retires a candidate whose worktree is gone and builds a new one.
  - git run in a directory that no longer exists is a `GitError`, never a traceback.
- **Case-only renames** (`Foo.txt` to `foo.txt`) are refused at `prepare` on a case-insensitive filesystem. There the two names are one file, and the authoritative worktree could never be synced. A rename in two steps, or a case-sensitive checkout, integrates normally.
- **A merge that fails without a conflict** (a hook, a lock, a missing commit) is a `GitError`, not a conflict with no paths.
- **What the sync guarantees, precisely:**
  - The authoritative branch must be checked out at the repository root, or nowhere. `update-ref` also moves a branch checked out in another worktree of the repository, and that worktree is not synced.
  - "Nothing is overwritten" means nothing present when the paths were classified. An edit made between classification and `git checkout` of the integrated paths is not protected, because the filesystem gives no exclusive hold.
- **After an inconclusive post-integration verification** (`validation_inconclusive`), the next step is `aew integrate prepare` (a new candidate), then its verification. `aew resume` says so.

## Amendment 2026-10-05 — the integration queue and its lease (M4-D3)

Integration is now served by a queue in control state (M4 report §2.6; the M4-D plan, approved 2026-10-04). Everything above still holds: prepare, post-integration verification, the CAS, the sync, DONE and `reconcile` are unchanged. They now also run under a lease.

- **Entries.**
  - Each COMMIT_READY mutating Ticket has one live entry in `queue.entries`: `QUEUED`, `LEASED`, `DEFERRED` or `AWAITING_DISPOSITION`.
  - An entry has a `seq` (its FIFO position), the `commit_ready_seq` it was queued for, its attempts and its disposition.
  - It is enqueued and retired by a transaction finalizer, so every route that changes a Ticket's state keeps the queue consistent in the same commit. The Lead's direct commits (acquire, handoff accept, takeover) call the same step.
  - **Retirement.** A Ticket no longer COMMIT_READY (DONE, CANCELLED, back to RUNNING, VERIFICATION_FAILED, INTERRUPTED, …) retires its entry into the unit's `queue_history`, which archival moves with the unit.
- **The lease.**
  - At most one entry holds `queue.lease`, kept by an `integration_attempt` custody invocation (ADR-0003, amendment of today).
  - `aew integrate prepare` grants it. Its legality is the `integrate.prepare` dispatch decision, computed afresh at every grant (M4-A), with these guards:
    - `integrate.ticket` and `integrate.gates`: the checks prepare made before, in the same order and with the same errors;
    - `queue.order`: FIFO among runnable entries;
    - `queue.lease`: the lease is free, or this entry already holds it.
  - `aew integrate publish` and post-integration verification (dispatch and ingest) run only under the Ticket's own live lease.
  - **The lease ends:**
    - at DONE;
    - when the Ticket leaves COMMIT_READY;
    - on a conflict: the entry goes to AWAITING_DISPOSITION, for the Lead;
    - on a candidate refused at admission (the `max_publish_paths` bound, protected paths, a case-only rename): the same, committed with the refusal's code, and the error is then returned. A refusal that rolled back would leave the entry QUEUED and runnable, so it would hold up every independent entry behind it;
    - on a stale or superseded candidate: the entry goes back to QUEUED in its place, and D4 will rebuild once under the same lease instead;
    - when `reconcile` reconciles a dead custodian.
  - **A withdrawn publish** (an obligation unmet, nothing published) keeps the lease.
- **Order, and no head-of-line blocking.**
  - Runnable entries are served by `seq`. An earlier QUEUED entry whose integration is legal now goes first (`QUEUE_ORDER`).
  - An earlier entry that cannot integrate now, or is DEFERRED or AWAITING_DISPOSITION, holds up nothing.
  - Queue state is scheduling, never eligibility.
- **A candidate from before the queue.** A project upgraded with an open candidate (`prepared` or `validated`) that no lease holds is enqueued like any COMMIT_READY Ticket. Its candidate is never adopted: `aew integrate prepare` retires it and builds a new one under a lease, so the post-integration checks rerun under fresh custody. An interrupted `publishing` candidate finishes through `reconcile`, which needs no lease.
- **A dead custodian is reconciled, never timed out.**
  - A custodian ended by anything but its own lease's end (a takeover, an uncarried handoff, a cancel) marks the lease `reconcile` in the same transaction and cancels the custodian's children. Grants, publishes and verification are then refused (`LEASE_RECONCILE_REQUIRED`).
  - `aew integrate reconcile <T>` resolves it:
    - an interrupted publish finishes as before; a reconcile needs no live custodian;
    - otherwise nothing was published, so the open candidate is retired and the entry returns to QUEUED in its place.
- **`AEW-INV-ISO-004`.**
  - Syncing a published commit into the authoritative checkout takes `local/checkout-sync.lock` in the lease custodian's name, for the bounded sync only.
  - It is serialization only (M4-B6): it is taken after every check allowed the publish, and holding it lets nothing else happen.
  - A holder a crash left behind is a stale owner. It is reconciled before the lock is taken again; the sync is idempotent and re-verified.
- **Register E34.**
  - The sync classifier accepts a path that any commit between the candidate and the ref settled (up to 256 of them), not only the head. It reads that range once (`git log --raw` against every parent) and considers only paths whose index differs from the candidate, so its cost under the control lock does not multiply by the number of later commits.
  - A candidate may change at most `gates.yaml` `max_publish_paths` paths (default 2,000), refused at prepare before anything is published. A publish syncs every changed path while it holds the control lock, measured at about 4.5 to 5.5 ms a path on the Windows reference machine (`tools/perf/publish_sync.py`), so 2,000 keeps the hold near 10 s, inside the 31 s other writers wait.
- **Schema.** `aew/control/v2`, additive (the M4-D plan §1.1). `queue` is a v2-only key, and the engine before M4-D refuses the file (`tests/regression/test_m4_schema_downgrade.py`). A v1 project has no queue and integrates as before until it is migrated.
- **Events.** `queue.entry {id, from, to}` and `queue.lease {entry, custodian}` are derived kinds in the transition log (ADR-0012 D2). A released lease has both fields null.
- **Oracle rules 34 to 38** (`tests/helpers/invariants.py`; 24 to 28 are ADR-0012's, 29 to 33 ADR-0013's):
  - 34: one live entry per COMMIT_READY mutating Ticket, positions unique;
  - 35: at most one lease, with its custodian active or marked for reconciliation;
  - 36: a custody invocation is the engine's, and an active one holds the lease;
  - 37: no publish in progress without the lease;
  - 38: integration verifiers are children of a live lease.

  They hold in the seeded queue walk (`tests/regression/test_m4_queue_walk.py`).

## Amendment 2026-10-05 (2) — what survives a head move, and the Lead's queue commands (M4-D4)

D3's answers to a moved head (the lease released, the entry back to QUEUED) are replaced by the M4 report's §2.6 and §2.7. Everything else in the D3 amendment holds.

- **The one automatic rebuild.**
  - When `aew integrate publish` finds the authoritative head moved under its candidate, or `reconcile` finds a CAS that never happened against a moved head, the engine:
    1. proves nothing was published: the ref does not contain the candidate;
    2. recomputes legality as a grant would: the `integrate.prepare` decision, recorded;
    3. rebuilds the candidate on the new head, under the same lease, custodian and queue position. There is no release, no new `seq` and no new `commit_ready_seq`. The entry's `rebuilds_used` becomes 1.
  - The Ticket's work product and Ticket-scope evidence are reused, because their bindings are unchanged.
  - The integration candidate and its validation are not reused: publish answers `rebuilt`, and post-integration validation reruns on the new candidate before it can publish.
  - Each grant starts with a fresh allowance of one rebuild.
- **When the entry goes to the Lead instead.** The lease is released to AWAITING_DISPOSITION, with the reason recorded in `disposition`, when:
  - the head moves again after the rebuild (`head_moved_again`);
  - legality changed on the moved head (`legality_changed`, naming the blocking conditions);
  - the rebuild conflicts (`conflict`) or is refused at admission (`refused`);
  - the ref can't prove the candidate unpublished (`not_provably_unpublished`);
  - post-integration validation is inconclusive (`validation_inconclusive`).
  
  A failed validation still moves the Ticket to VERIFICATION_FAILED, which retires the entry. A superseded binding (an earlier COMMIT_READY or plan) is not a head move: the entry keeps its place in QUEUED, as in D3.
- **A reconcile under a dead custodian never rebuilds.** Nothing was published, so the entry returns to its place, as D3 reconciles a dead custodian.
- **The Lead's queue commands.** They are scheduling, never eligibility, and each records its reason in the transaction:
  - `aew integrate defer <T> --reason`: QUEUED, AWAITING_DISPOSITION or LEASED to DEFERRED.
    - A LEASED entry gives up its lease: the custodian completes, and the open candidate, which nothing published, is retired.
    - A publish in progress, or a lease awaiting reconciliation, is refused.
  - `aew integrate requeue <T> --reason`: DEFERRED or AWAITING_DISPOSITION back to QUEUED, in its own place (`seq` kept).
  - `aew integrate reorder <T> (--before <T2> | --first) --reason`: the live entries are renumbered in the new order with fresh, never reused, positions.
  - The three are declared judgment-bearing primitives (`queue_disposition`).
  - Preparing a DEFERRED or AWAITING_DISPOSITION entry is refused until it is requeued.
- **Oracle rule 39:** a live entry has used at most one automatic rebuild, and only a DEFERRED or AWAITING_DISPOSITION entry carries a disposition record.
- **Tests:**
  - `tests/integration/test_queue_disposition.py` covers the rebuild, the second move, the conflicting rebuild, reconcile's rebuild after a crash before the CAS, inconclusive validation, defer, defer of a leased entry, reorder and the refusals;
  - the queue walk adds defer, requeue and reorder.

## Amendment 2026-10-05 (3) — checks-mode validation (M4-D5)

The M4 report's §2.8, built to the M4-D5 plan, revision 3 (approved by the designer, 2026-10-05). With `gates.post_integration.validation` resolving to `checks` for a Ticket, a candidate is validated with no model. With `verifier`, the default, nothing changes.

- **Which Tickets.** The policy prefers a mode by the Ticket's own local risk class (`validation: checks`, or `{by_class: {"0": checks, ...}, default: verifier}`). Effective obligations override it: a verifier is mandatory when an ancestor lists the gate `post_integration_verifier`, or when an ancestor's minimum descendant class maps to `verifier`. No class inherited from ancestors chooses the mode. Policy that would weaken a required verifier is refused, naming the obligation and its source.
- **The command.** `aew integrate validate <T>`, the primitive `integrate.validate`, is `POLICY_RESOLVED`: the mode and the exact check set come from recorded policy, and its substeps (pin, execute, fingerprint, write evidence) are mechanical. It needs a live lease and a prepared candidate.
- **Two transactions around the checks.**
  1. Transaction 1 pins the run: the lease and its custodian, the candidate, its snapshot, the check set's digest, the **obligation binding** (the digest of the legality inputs the mode was resolved from) and the run's hard deadline. The operational digest is not pinned: an operational change never abandons a run.
  2. The checks run outside the control lock, contained.
  3. Transaction 2 re-resolves the obligation and re-verifies everything pinned. Any difference abandons the run with its reason (`STALE_OBLIGATION`, `CHECK_SET_CHANGED`, `CANDIDATE_CHANGED`, `LEASE_LOST`, `SUPERSEDED`, `VALIDATION_DEADLINE_EXPIRED`) and writes nothing satisfying.
- **The run's identity and history.** A run is identified by (candidate, snapshot, check-set digest, obligation binding). A committed run is reused only on an exact match; otherwise a new run starts, and publish refuses the old evidence. One run per candidate runs at a time. Each terminal run is an immutable record, `work/<T>/validation-runs/<IV>.yaml`, created once; hot state keeps the current run (with its record's path and digest) and the run ids. A run of a retired candidate ends `abandoned` (`SUPERSEDED`) with the retired record.
- **Crash and retry.** Results are staged per check, atomically, with `finished.json` last. A `running` run whose executor is gone is ingested without re-running when `finished.json` is consistent and its identity current, and abandoned otherwise (`VALIDATION_INTERRUPTED`, one infrastructure attempt). `resume` names such a run.
- **Containment: fail closed.** Checks mode produces satisfying evidence only where the integration worktree is immutable for the whole run: Linux, `os_readonly_roots`, the verifier layout, self-tested. Elsewhere (Windows, or `containment.mode: allow_weaker`), `validate` is refused before anything is pinned, with `VALIDATION_CONTAINMENT_UNAVAILABLE`, and the Ticket takes the verifier path. A before/after fingerprint stays as a second line; a mismatch is `inconclusive` with `WORKSPACE_MUTATED`. `--diagnostic` runs the checks for information on any host: an advisory run, never evidence, never a state change.
- **Results.**

  | What happened | Evidence | Ticket and entry |
  |---|---|---|
  | Every check passed | `check_result: pass` per check, `kind: engine` | `validated`; publish next, under the lease |
  | A check failed | `check_result: fail` | VERIFICATION_FAILED through `integrate.validate`; the entry retires with the Ticket |
  | A check timed out, or the candidate changed | `check_result: inconclusive` | `validation_inconclusive`; the Ticket stays COMMIT_READY and the entry goes to AWAITING_DISPOSITION (M4-D4's path) |
  | Infrastructure: a check could not start, the sandbox could not be established, the run was interrupted or passed its deadline | none satisfying; the run `unavailable` or `abandoned` with its code | after the bounded handling below: `validation_unavailable`, the entry to AWAITING_DISPOSITION |

- **The hard deadline.** Every run has `deadline_at`, from `gates.post_integration.validation_deadline_s` or the checks' timeouts plus an orchestration allowance, capped at six hours. Expiry is authority-reducing only: the checks are killed, a hung executor is terminated by whoever finds it, and transaction 2 refuses a run past its deadline. The lease is released only through AWAITING_DISPOSITION, never by the timer.
- **Infrastructure, bounded.**
  - Retry only for an allow-listed transient reason: `SPAWN_RACE` (a check's executable busy, ETXTBSY) and `SANDBOX_SETUP_TRANSIENT` (the containment self-test timed out). Never for a missing executable, a failed self-test, resource exhaustion (ENOMEM, EAGAIN), a deadline or any unknown reason.
  - One retry per identity, after a 30 s backoff.
  - A project circuit breaker (`queue.validation_breaker`): three infrastructure failures in ten minutes stop automatic retries for every entry. `aew integrate breaker status` shows it; `aew integrate breaker reset` clears it only with the operator's typed-back confirmation at the terminal. It is operational safety state, not workflow authority.
  - The bound reached, one transaction records the run, proves nothing was published (the ref and the candidate's fingerprint unchanged), parks the candidate and releases the lease to AWAITING_DISPOSITION. Independent entries behind it integrate meanwhile. No `fail` evidence and no VERIFICATION_FAILED for an environment failure.
- **Publish.** In checks mode, publish requires the committed passing run under the exact current identity, and a passing engine `check_result` of that run, under its custodian, on the candidate's snapshot, for every policy check's current definition. A verifier's passing report is accepted in either mode.
- **After the one automatic rebuild** publish says to run `aew integrate validate`: the rebuild retired the old validation with its candidate.
- **The check's environment** is an allowlist (operating-system basics and the sandbox's settings): the candidate's code never sees the Lead's credential.
- **Oracle rules 40 to 42:** a running run only under its entry's lease, ids never reused, and every terminal run's record intact; engine evidence only as above; a checks-mode `validated` candidate has a committed passing result for every policy check.
- **Tests:** `tests/integration/test_validation_checks.py` covers every result path, the obligation pin, identity and history, the containment refusal and `--diagnostic`, the crash table, a lost lease, the deadline (a hung executor and a check past it), the transient allow-list, the breaker and its reset, the rebuild and the producer rules; on Linux, a check that tries to write the candidate is refused by the sandbox.
