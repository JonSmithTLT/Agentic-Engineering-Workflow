# Response to the independent M1 review (2026-09-26)

- **Reviewed commit:** `1d914cb` on `impl/m1-serial-slice`
- **Review:** `AEW-M1-review-2026-09-26/REPORT.md`, with 12 executable probes
- **Verdict received:** do not merge (2 Blockers, 8 Majors, 1 Minor)
- **Spec set:** `aew-frozen-2026-09-25`. The frozen contracts are unchanged. None of the findings required a contract change or met the escalation rule (frozen-contract contradiction, missing authority boundary, unsafe *spec* transition, unsatisfiable invariant). Each was an implementation failing to enforce an existing invariant across a composition of operations.

## Status after the first remediation round (see the re-review section below)

Every probe is preserved **unchanged** in `tests/regression/test_review_2026_09_26.py` (header and platform markers only) and passes. They were imported as strict xfails, and each fix commit removed its own markers. The executable-bit probe is skipped on Windows, where `core.fileMode=false`.

| ID | Finding | Root cause | Fix | Main files | Commit | Evidence |
|---|---|---|---|---|---|---|
| B1 | A superseded integration candidate could discard newly verified work | Leaving COMMIT_READY kept a `validated` candidate; publish never checked what it was built from; DONE cleanup deleted the workspace unconditionally | Candidates are bound to `{plan rev+sha, commit_ready_seq, gated fingerprint}` and re-checked at dispatch, ingest, publish and finalize. Leaving COMMIT_READY retires the open candidate to `integration_history`; exits while `publishing` are refused. At DONE the workspace is removed only if it holds exactly the integrated Ticket commit, otherwise it is retained and reported. | `engine/integration_ops.py`, `engine/work_ops.py` (`_set_state` hooks), `engine/evidence_ops.py`, `engine/status_ops.py` | `773561f` | Probe B1; `test_regression_after_validation_supersedes_…`, `test_state_cannot_leave_commit_ready_while_a_publish_is_pending`, `test_workspace_holding_unintegrated_changes_is_retained_and_reported`, `test_candidate_bound_to_an_earlier_acceptance_is_superseded_at_publish` |
| B2 | Reconciliation overwrote independent staged work | Sync compared only working-copy blobs, then ran an unconditional `git reset M -- paths` | Complete entries (mode+oid) of index **and** working copy are compared against H/M. Every path is classified before any write; anything else is refused. The strict pre-CAS check reads real content, not `git diff`. | `workspace/integration.py` | `5d5db6e` | Probe B2; `tests/integration/test_worktree_sync.py` (LF-exact staged-edit variant, precheck, index flags, untracked collisions, intermediate-state matrix) |
| M1 | A stale revision was rejected only after the ref moved | CAS and sync ran in a session that checked only the Lead credential | Finalization (publish and reconcile) is **one** `lead_txn`: authority, revision and manifest pin are checked under the lock before any git side effect, and the lock is held until DONE | `engine/integration_ops.py`, `engine/base.py` (`TxnContext.op`) | `1446c90` | Probe M1; `test_interleaved_writer_makes_finalization_stale_before_any_git_side_effect`; the existing four-point publish crash matrix |
| M2 | Replanning left live invocations outside the serial cap and retargeted old credentials | `plan_accept` left the workspace and invocations live; the cap filtered by state name; check/report resolution used the *latest* workspace | Accepting a replacement plan releases the workspace and cancels (revokes) all active invocations. The cap counts `workspace.status == active` regardless of state. Invocations record `workspace_id` and resolve only their own live workspace or candidate. | `engine/work_ops.py`, `engine/workspace_ops.py`, `engine/evidence_ops.py` | `b8fd08b` | Both M2 probes; `test_repeated_replan_and_interruption_cycles_keep_the_serial_boundary`, `test_invocation_is_never_retargeted_to_another_workspace` |
| M3 | Assume-unchanged hid changed inputs from evidence freshness | The copied real index carried content-hiding flags | In the **temporary** index only: assume-unchanged is cleared; `core.ignoreStat`, `core.fsmonitor` and `core.untrackedCache` are forced off; skip-worktree (sparse) entries are refused. The real index is never modified. | `snapshot/fingerprint.py` | `5837c42` | Probe M3; `tests/integration/test_fingerprint_flags.py` |
| M4 | Submitted but un-ingested reviews satisfied gates | Gate evaluation read every sealed submission | Review and verification gates count only evidence pinned (id+sha256) in the Ticket's ingested refs. `local_checks`/`self_review` explicitly keep counting implementer submissions, which are accepted by the transition that pins them. | `engine/gates.py` | `8ba5b2a` | Probe M4; `test_submitted_but_uningested_reports_satisfy_no_gate` (review and verifier-card variants) |
| M5 | Handoff and reconciliation bypassed mandatory classification | Interruption turned *any* state (including VERIFICATION_FAILED) into INTERRUPTED; phase-order reconciliation then allowed RUNNING | A Ticket becomes INTERRUPTED only if its current phase waits on the lost invocation. Other states (determined by evidence or a Lead decision) are retained, with the revocation recorded in history. | `engine/lead_ops.py` | `88d4185` | Probe M5; `test_interruption_keeps_a_review_failure_and_revokes_the_sibling_reviewer`, `test_handoff_while_publishing_keeps_commit_ready_and_reconcile_completes` |
| M6 | An executable-bit-only integration published but could not complete sync | Blob-only comparison skipped the checkout; convergence then failed forever | Mode-aware entries; `git checkout M -- p` materializes mode, with a chmod fallback; file↔symlink and file→directory transitions are handled | `workspace/integration.py` | `5d5db6e` | Probe M6 (POSIX); exec-bit, symlink, file→directory and delete tests in `test_worktree_sync.py` |
| M7 | Operator card pins could be silently ignored | Staffing skipped existing entries; explicit `--card` dispatch never consulted pins | Staffing updates existing entries (`--by operator` pins stick; a Lead re-selection keeps them). Execute-slot dispatch refuses any card other than the operator-pinned one; the override goes through `work staff --reason` (a decision). | `engine/role_ops.py` | `5c5f8c0` | Both M7 probes; `test_lead_override_of_an_operator_pin_goes_through_a_recorded_decision` |
| M8 | The first post-crash resume used an outdated manifest | The engine loaded `project.yaml` before store recovery replayed the committed rewrite, and cached it | An `after_apply` store hook reloads the manifest inside the lock after recovery and after every commit's apply. `manifest` is a property whose first use triggers recovery. `doctor` reports an unreadable manifest. | `engine/store.py`, `engine/base.py`, `engine/api.py` | `110578f` | Probe M8; `test_long_lived_engine_never_serves_an_older_manifest`, `test_first_resume_after_a_crash_mid_manifest_apply_shows_the_committed_authority` |
| N1 | ADR-0006 advertised `restrict.paths`, which the schema rejects | Documentation drift | ADR-0006 now states that card-level path restriction is **deferred** (Designed); M1 path limits come from Ticket scope and guardrails. The schema is unchanged (fails closed). | `docs/implementation/adr/0006-…`, `implementation-status.md` | `5c5f8c0`, R10 | — |

## Test-gap response

The review observed that the defects clustered at compositions of individually tested operations. In addition to the targeted tests above:

- **Invariant oracle** (`tests/helpers/invariants.py`). A read-only check of cross-operation invariants on durable control state:
  - the serial cap by live workspace;
  - every active invocation bound to its Ticket's current live workspace, with a live credential, and every inactive one revoked;
  - DONE implies the integrated commit is in the authoritative ref and the candidate's binding and completion record match the COMMIT_READY snapshot;
  - VERIFICATION_FAILED is left only by classification or cancellation, and never by interruption.
- **Seeded adversarial walk** (`tests/regression/test_composition_walk.py`). 5 seeds × 60 steps through the in-process Engine API.
  - Each step picks a state-plausible operation plus cross-cutting ones: handoff, takeover (operator channel stubbed only here), stale edits, a second mutating Ticket, and crash-injected commits and publishes (`AEW_FAULT_MODE=raise`, then a fresh engine).
  - The oracle runs after **every** step. Rejections are expected; any non-AEW exception fails.
  - Coverage per run includes DONE, crashed publishes reconciled to DONE, validated-candidate regressions, replans, takeovers and classifications.
  - Seeds and length can be widened with `AEW_WALK_SEEDS` and `AEW_WALK_STEPS`.
- Additional cases the review suggested:
  - symlink/type-only sync;
  - the sparse/skip-worktree policy (refused, in both the fingerprint and sync);
  - long-lived engine manifest refresh;
  - verifier-card submission before ingestion;
  - repeated interruption/replanning cycles.

**Existing tests:** none of the 477 existing tests needed a changed expectation. All changes are additive.

## Behaviour changes an operator will notice

- **Leaving COMMIT_READY retires the integration candidate.** Re-running `aew integrate prepare` builds a fresh one (attempt numbers continue). While a publish is pending, state changes are refused until `aew integrate reconcile`.
- **Publishing refuses local work in the authoritative worktree.** If the authoritative index or working copy holds local work on a path the integration changes, publishing (or reconciling a publish) refuses and names the paths; nothing is overwritten. If the ref already moved, the Ticket stays `publishing` until the operator resolves the paths and reconciles.
- **A retained workspace.** A Ticket workspace holding changes beyond the integrated commit is kept at DONE and reported as a contradiction by `status`/`resume`.
- **Replacing a plan ends the current attempt.** The next `aew work assign` starts a fresh workspace.
- **Sparse checkouts are refused.** Skip-worktree entries in a Ticket workspace fail the snapshot (AEW workspaces are full checkouts).
- **Operator pins bind dispatch.** Replacing a pinned executor requires `aew work staff --reason`.

## Focused re-review of the remediation (revision `e7e723c`)

The re-review (`AEW-M1-review-2026-09-26/remediation-review/REPORT.md`, 6 follow-up probes) found:

- **Closed:** B2, M1, M3, M4, M5, M6, M7, N1.
- **Partially closed:** B1, M2, M8.
- **Newly exposed:** one weakness, **R1**, on the replacement-candidate path the remediation enabled.

The follow-up probes are preserved unchanged in `tests/regression/test_remediation_review_2026_09_26.py`. They were imported as strict xfails, and each fix commit removed its marker; all six now pass.

| ID | Residual | Root cause | Fix | Commit | Evidence |
|---|---|---|---|---|---|
| B1 (residual) | DONE cleanup still deleted a late edit hidden by `assume-unchanged` | The new removal guard asked `git status`, which honours index flags | `worktrees.inspect` compares HEAD's tree with a tree built from workspace **content** (tracked + untracked-not-ignored, flag-neutralized temporary index). Removal needs HEAD == integrated commit **and** content == HEAD; unverifiable content (sparse) is retained. `prepare` refuses a workspace whose index hides edits from `git add`. | `82d41c7` | Probe; `test_prepare_refuses_a_workspace_index_that_hides_edits`, `test_done_cleanup_retains_a_workspace_whose_content_cannot_be_verified`, `test_workspace_inspection_reads_content_not_index_flags` |
| M2 (residual) | A retired candidate's integration verifier could still submit | Retirement did not revoke the candidate's invocations; review/verification submission skipped the live-workspace check | Retirement cancels (revokes) every active integration invocation, via the state-change path, which now receives the transaction state. Integration invocations record `integration_attempt`/`candidate`. **Every** submission kind is bound to the invocation's live workspace or candidate and attempt. | `0b37309` | Probe; `test_retiring_a_candidate_ends_its_verifiers_write_authority`, `test_reports_are_written_only_for_a_live_workspace[review, verification]` |
| M8 (residual) | Session-free reads (`role_list`) served a manifest cached before another process adopted a new one | The property reloaded only on sessions | Outside a session, each use compares the identity (mtime, size, inode) of `control.yaml` and `project.yaml` with the last locked load and reloads through a recovered read on any change. Inside a session it never re-enters the lock. | `b5a9986` | Probe; `test_every_public_read_of_a_long_lived_engine_sees_the_adopted_manifest`, `test_manifest_reads_inside_a_session_never_reenter_the_lock` |
| R1 | A replacement candidate published on an integration report produced for the superseded candidate and plan (identical bytes) | Ingest and publication compared only the engineering fingerprint | `_require_bound_report`: at review ingest, verify ingest (both scopes), publish phase 1 and pre-CAS finalization, a report must carry the current accepted plan (revision + sha256) and come from an invocation dispatched for the current attempt's workspace, or for the current candidate's workspace **and** attempt | `94705b5` | Probe; `test_review_from_a_superseded_plan_is_not_accepted_for_identical_new_work`, `test_publication_refuses_a_validation_record_not_produced_for_the_candidate` |
| (walk) | Unused stragglers kept live credentials after DONE | Only CANCELLED ended remaining invocations | Entering any terminal state cancels (revokes) every remaining active invocation of the Ticket | `de4993b` | Extended adversarial walk (below) |

**Why the regression tests missed these, and what changed.** The first round's walk exercised state transitions and crashes. It never used an old credential, left a report un-ingested, or replayed one. Commits `1e9527b` and `de4993b` extend both the oracle and the walk.

- **Oracle, new rules:**
  - no evidence is written after its invocation's credential was revoked;
  - a DONE Ticket's post-integration report was produced by that candidate's own verifier (workspace and attempt) under the bound plan.
- **Walk, new actions:**
  - stragglers;
  - submit-without-ingest;
  - late submission with *any* credential ever issued;
  - replayed ingestion of *any* earlier report.
- **Coverage per run:** about 8 replays (most correctly refused), about 14 late submissions (refused unless the credential is still legitimately live), stragglers, DONE outcomes and about 18 injected crashes. The oracle is checked after every step. On its first run the extended walk caught the terminal-state credential gap above.

**Verification.**
- The reviewer's two probe files, run **unchanged** in WSL (sha256 `a45f3963…` and `e321c0cf…`): **18/18 pass**.
- Frozen contracts unchanged.
- No test that existed at `1d914cb` changed its expectations.
- Full-suite results for this round are recorded in `docs/implementation/implementation-status.md`.

## Foundation review (revision `f3fc4a3`): index-only work

A further probe showed DONE cleanup deleting a workspace whose only late change existed in the Git index. The content check replaced the index copy's entries with working-file content, so staged-only work looked clean. The same `git add -A` at `prepare` would have overwritten such an entry.

- **Fix:** workspace inspection compares HEAD with the index as staged as well as with the working content. `prepare` refuses staged content that matches neither HEAD nor the working copy. See the ADR-0004 addendum.
- **Evidence:** the reviewer's two index-only probes, preserved unchanged in `tests/regression/test_foundation_review_2026_09_26.py`; `test_done_cleanup_retains_a_workspace_with_a_staged_only_deletion`, `test_prepare_refuses_staged_content_found_nowhere_else`, `test_a_fully_staged_change_prepares_normally`.

## Follow-ups (recorded, not done here)

- An explicit `integrate abort` for a `publishing` record whose ref never moved. Today the path is to resolve the local conflict and run reconcile.
- Syncing sparse or submodule paths in the authoritative worktree (refused and documented).
- Proving operator pins through the terminal channel (ADR-0006 follow-up).
- Card-level `restrict.paths` (Designed).
