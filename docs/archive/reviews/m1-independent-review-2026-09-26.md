# AEW M1 independent technical review

**Merge assessment: do not merge this revision.** There are two Blockers and eight Major findings, including reproducible loss of newly verified work and staged user changes. One additional Minor finding concerns documentation.

Reviewed branch: `impl/m1-serial-slice`  
Reviewed commit: `1d914cb59564303d1c1fef672dd81628bdcb0156`  
Review date: 2026-09-26  
Basis: Workflow Contract v0.7 (WC), Knowledge Contract v0.4 (KC), frozen manifest, and implementation ADRs. The spec-set identifier is `aew-frozen-2026-09-25`; its Git tag is `aew-spec-frozen-2026-09-25`. These are distinct identifiers, not a missing-tag defect.

The supplied `Code_Review.txt` was used as review context. Its author claims were independently checked. This review concerns the implemented M1 core, not the future scheduler or harness/provider integrations. No implementation files were changed. Test projects were disposable temporary repositories; this report and its probes are outside the implementation repository.

## Validation

- **Existing suite:** **477 passed in 387.62 seconds (6m 28s)**. See `existing-suite.txt`.
- **Independent regression probes:** 12 failures at the intended safety assertions, in 86.05 seconds, covering the ten substantive findings below. These probes assert the expected safe behavior; their failures reproduce defects, rather than indicate setup failures. See [probe source](../../../eval/reviews/m1-2026-09-26/reproductions/test_review_regressions.py) and [failure evidence](../../../eval/reviews/m1-2026-09-26/reproductions/results.txt).
- **Acceptance inventory:** independently collected **37 of 477 tests** with the acceptance marker.
- **Frozen contracts:** the Workflow Contract, Knowledge Contract, and manifest have no differences from the frozen tag.
- **Environment:** Linux/WSL, Python 3.11, PyYAML 6.0.3, jsonschema 4.26.0, pytest 9.1.1; dependencies were isolated in `/tmp`. The original suite runs in a local clone of the exact reviewed commit. Windows test results reported in the supplied document were not rerun.

## Blockers

### B1 — A superseded integration candidate can discard newly verified work

**Affected:** `IntegrationOps.integrate_publish`, `src/aew/engine/integration_ops.py:129`; cleanup at lines 201–203; `WorkOps.work_transition`.

**Reproduction:** Reach COMMIT_READY, prepare and validate candidate A, return the Ticket to RUNNING, add a new function and test, and pass fresh implementation/review/verification gates to reach COMMIT_READY for snapshot B. The old integration record remains `validated`. `integrate publish` publishes A, records DONE, and deletes the Ticket workspace. The newly verified function is absent from main and its workspace is gone. Re-preparing also encounters the retained old candidate.

**Cause and impact:** Publication checks the old candidate's validation but does not bind it to the current COMMIT_READY snapshot or accepted work generation. Cleanup then removes newer uncommitted engineering output. This violates WC §8/§8.1/§13 and KC §11: the accepted, evaluated output must be the integrated output.

**Smallest remediation:** Invalidate pending candidates when returning to mutation or changing plans; record their source-plan and COMMIT_READY identity; compare those bindings at publication and reconciliation. Preserve workspaces on mismatch.

**Probe:** `test_old_candidate_cannot_discard_newly_verified_implementation`.

### B2 — Reconciliation silently overwrites independent staged work

**Affected:** `sync_worktree`, `src/aew/workspace/integration.py:96`, particularly lines 115–117; `IntegrationOps._finish_publish`.

**Reproduction:** Crash at `integrate.after_publishing_record`, then stage an independent change to a path the integration changes. Restore only its working-copy content to the integration candidate, leaving the independent staged change intact. `integrate reconcile` succeeds and marks DONE, but the staged change is replaced with the candidate content.

**Cause and impact:** Recovery checks working-copy blob content, but never establishes that the index still contains only the recorded base/candidate state. The unconditional `git reset <candidate> -- <paths>` destroys the independent index entry. The initial precheck happened before the crash. This is data loss on the supported recovery path, contrary to ADR-0004's protected synchronization behavior and WC §8.2's safe recovery requirement.

**Smallest remediation:** Revalidate both index and working-copy state before recovery writes; explicitly allow only known base/candidate intermediate states, and reject conflicting staged content before changing refs or files.

**Probe:** `test_reconcile_preserves_independent_staged_edit`.

## Major findings

### M1 — A stale control revision is rejected only after publishing Git changes

**Affected:** `IntegrationOps._finish_publish`, `src/aew/engine/integration_ops.py:156`, with the delayed revision check at line 187.

**Reproduction:** Crash after the publishing record but before ref CAS. Call `integrate reconcile` with the current Lead token and an outdated `--expect-rev`. It returns `STALE_REVISION`, yet main has advanced to the candidate and worktree synchronization has already occurred.

**Why it matters:** A rejected mutation has authoritative side effects. This violates WC §8.2/§15.6 and KC §12.3 even though stale Lead generation checks themselves occur before CAS.

**Smallest remediation:** Validate the expected revision and manifest pin under the control lock before any ref/worktree side effect; retain coherent preconditions across publication and finalization.

**Probe:** `test_stale_reconcile_cannot_move_authoritative_ref`.

### M2 — Replanning leaves live invocations outside the serial cap and retargets old credentials

**Affected:** `WorkOps.plan_accept`, `src/aew/engine/work_ops.py:223`; `WorkspaceOps._mutating_slots_in_use`, `src/aew/engine/workspace_ops.py:78`; `EvidenceOps._invocation_workspace`, `src/aew/engine/evidence_ops.py:45`.

**Reproduction:** Assign a Ticket, move it to REPLAN_REQUIRED, and accept plan v2. It becomes READY while its original workspace and invocation remain active. A second mutating Ticket can now be assigned despite the cap of one. In a separate probe, reassign the original Ticket instead: its old credential successfully runs `guardrails` against `ws-T-0001-2`, although that invocation was launched for `ws-T-0001-1`.

**Why it matters:** The state-based capacity calculation excludes READY despite its live workspace. Check execution resolves the Ticket's latest workspace rather than the invocation's recorded workspace. This breaks M1's declared serial boundary and bounded assignment provenance (WC §8.1/§15.4, KC §9.5, ambiguity disposition B6).

**Smallest remediation:** Retire or explicitly reconcile previous invocations/workspaces before readiness or reassignment; count live unintegrated workspaces independently of the phase name; enforce invocation-to-workspace binding.

**Probes:** `test_replanned_active_workspace_still_counts_against_serial_cap`, `test_reassignment_does_not_retarget_old_invocation_credential`.

### M3 — Git assume-unchanged flags hide materially changed inputs from evidence freshness

**Affected:** `_working_index`, `src/aew/snapshot/fingerprint.py:45`.

**Reproduction:** Reach VERIFIED, stage the tested tracked source, mark it `git update-index --assume-unchanged`, and change `subtract()` to return 999. The fingerprint remains identical, all gates remain CURRENT, and transition to COMMIT_READY succeeds.

**Why it matters:** Copying the real index preserves flags that cause `git add -A` to skip reading changed content. This violates the actual-input requirement in WC §9.9 and KC §11; it is separate from ADR-0002's documented submodule, LFS, and normalization limitations.

**Smallest remediation:** Clear or reject content-suppressing index flags in the temporary index, and explicitly define handling for sparse/skip-worktree inputs. Do not change the user's real index.

**Probe:** `test_assume_unchanged_source_invalidates_verified_gates`.

### M4 — Submitted but unaccepted reviews satisfy required gates

**Affected:** `gates.evaluate`, `src/aew/engine/gates.py:118`; `EvidenceOps.review_ingest`, `src/aew/engine/evidence_ops.py:446`.

**Reproduction:** Require both code_reviewer and security_reviewer. Submit passing reports from both, then ingest only the code review. The Ticket moves to REVIEW_PASSED even though the security review is absent from its accepted evidence references and its invocation has not been completed. The normal security ingestion can no longer run because the state is no longer REVIEW_PENDING.

**Why it matters:** Gate evaluation reads every sealed submission from the Ticket's invocation history, without distinguishing Lead-ingested review/verification evidence. This skips the other report's ingestion checks and bookkeeping. It conflicts with the Lead/evidence separation (WC §6, KC §7.2/§16) and ADR-0006's per-card gate processing. The verification-card evaluators use the same broad evidence set, but the preserved executable probe specifically establishes the review case.

**Smallest remediation:** Evaluate accepted review/verification records, including the record being atomically ingested, rather than all submitted records. Keep implementation/check acceptance behavior explicit. Do not retire a whole gate while another required report still awaits ingestion.

**Probe:** `test_submitted_review_is_not_counted_as_ingested`.

### M5 — Handoff and reconciliation bypass mandatory verification-failure classification

**Affected:** `LeadOps._interrupt_invocations`, `src/aew/engine/lead_ops.py:46`; `WorkOps._guard_not_beyond_interrupted_phase` and `work_reconcile`, `src/aew/engine/work_ops.py:269`.

**Reproduction:** Dispatch two verifier invocations. Ingest a failing report from one, leaving the other active. Handoff interrupts the remaining invocation and changes VERIFICATION_FAILED to INTERRUPTED. The successor reconciles directly to RUNNING; the classification list remains empty.

**Why it matters:** Comparing phase numbers permits an earlier state but loses the special requirement that only a recorded Lead classification can select remediation after verification failure. WC §8/§12 and KC §11 explicitly require that decision.

**Smallest remediation:** Preserve failure obligations across interruption; restore the failed state or require its classification before any reconciliation into mutation/replanning.

**Probe:** `test_interruption_does_not_bypass_failure_classification`.

### M6 — Executable-bit-only integration publishes but cannot complete synchronization

**Affected:** `sync_worktree`, `src/aew/workspace/integration.py:100`.

**Reproduction:** On a filemode-aware Linux repository, prepare a valid 100644 → 100755 change with unchanged file bytes. Precheck and ref CAS succeed. Synchronization compares only blob hashes, skips checkout because the content is equal, then updates only the index. The working file stays non-executable and the final convergence check raises `GitError`; retrying repeats the condition.

**Why it matters:** A normal executable-permission change leaves the authoritative ref published while integration cannot reach a consistent completed state. This breaks the integration/recovery behavior promised by WC §8.1/§8.2 and ADR-0004. The preserved probe exercises the actual Git integration primitives after ref publication.

**Smallest remediation:** Compare complete Git entries, including mode/type, and materialize mode changes. Add executable-bit and file/symlink transition recovery tests.

**Probe:** `test_sync_handles_executable_bit_only_change`.

### M7 — Operator card pins can be silently ignored

**Affected:** `RoleOps.work_staff`, `src/aew/engine/role_ops.py:151`; `resolve_card`, `src/aew/engine/role_ops.py:227`.

**Reproduction:** (1) Select c_engineer as Lead, then staff the same card with `--by operator --pin`: it remains `selected_by: lead, pinned: false`. (2) Set a real operator c_engineer pin, cancel its current invocation, then use `invoke create --card python_engineer`: dispatch succeeds without overriding the pin with a reason and decision.

**Why it matters:** The recorded constraint and actual dispatch disagree. This is enforcement of an already recorded constraint, not a claim that operator attribution is an OS security boundary. It violates ADR-0006's explicit selection precedence and override requirements.

**Smallest remediation:** Update pin/selection metadata when staffing an existing entry; check effective operator constraints on explicit dispatch as well as staffing changes, routing overrides through the recorded decision path.

**Probes:** `test_pinning_existing_card_updates_constraint`, `test_explicit_dispatch_cannot_bypass_operator_pin`.

### M8 — The first post-crash resume uses an outdated authority manifest

**Affected:** `EngineBase.__init__`, `src/aew/engine/base.py:37`; `authority_list`, `src/aew/engine/api.py:116`; resume authority rendering.

**Reproduction:** Kill `authority accept` at `txn.after_replace`. The first fresh `resume --json` recovers control revision 2 but reports no accepted authority, leaves the accepted candidate pending, and reports no contradictions. The recovered manifest on disk and the next fresh command correctly contain the accepted authority.

**Why it matters:** The engine caches the manifest before store recovery replays its committed replacement. The first reconstruction therefore exposes a mixed old/new view of authoritative state, violating WC §8.2 and KC §12.3/§15.1. Reusing a long-lived engine also warrants testing for manifest cache drift.

**Smallest remediation:** Recover and load/validate the manifest in a coherent locked snapshot before consuming it, refreshing cached values across operations. Test the first read after a manifest-changing crash, not only subsequent reads.

**Probe:** `test_first_resume_after_manifest_crash_exposes_recovered_authority`.

## Minor finding

### N1 — ADR-0006 advertises a card path restriction the schema rejects

**Affected:** [ADR-0006](../../implementation/adr/0006-role-archetypes-and-cards.md), the Role cards `restrict` bullet; [role.schema.json](../../../src/aew/schemas/role.schema.json), `restrict.properties`.

The ADR describes restrictions for operations, checks, and paths. The strict schema permits only operations and checks, so a card using `restrict.paths` is rejected. This fails closed and does not widen authority, but misstates the usable configuration surface. Clarify that path restrictions are deferred, or implement the documented feature with explicit enforcement. This is an ADR/schema mismatch, not a frozen-contract ambiguity.

## Test gaps

The suite has substantial crash/race coverage, but the confirmed defects concentrate at compositions between otherwise tested operations:

| Missing interaction | Finding |
|---|---|
| Validated candidate → regression → new verified snapshot → publish | B1 |
| Publication interruption followed by independent index changes | B2 |
| Stale expected control revision at integration reconciliation | M1 |
| Replan/accept followed by another assignment and old-token use | M2 |
| Index flags suppressing reads during synthesized snapshots | M3 |
| Multiple reports submitted before any ingestion | M4 |
| Failed verification + active sibling + handoff + reconcile | M5 |
| Git tree-entry mode changes, not just content changes | M6 |
| Pinning an existing choice and explicitly dispatching around a pin | M7 |
| First reconstruction after a committed manifest replacement crash | M8 |

Additional useful tests, not separately claimed as confirmed defects: symlink/type-only synchronization; sparse checkout and skip-worktree policy; long-lived engine manifest refresh; verifier-card submission-before-ingestion ordering; repeated interruption/replanning cycles. Expand adversarial sequences, not only the number of random store writes.

## Contract observations and documented limits

- None of the Blocker/Major findings requires redesigning the frozen contracts. Most require enforcing an existing invariant across transitions or recovery boundaries.
- Validate-before-publish is the documented resolution of the post-integration failure ambiguity (ADR-0004 and ambiguity A1); the review does not object to that design choice.
- Operator-only non-cooperative takeover is the documented A2 resolution. Same-UID deliberate process tampering is outside the stated M1 threat model; it is not reported as an authority exploit here.
- Dirty submodule contents, LFS content behind pointers, and Git-normalized line endings are documented fingerprint limits. The new assume-unchanged defect is not among them.
- Story/Epic execution, provider resolution, harness skill loading, non-mutating role dispatch, and a scheduler are explicitly staged/designed. Their absence is not an M1 defect.
- The card-path restriction discrepancy is implementation documentation drift. No new frozen-contract ambiguity was established by this review.

## Confirmed strengths

Source inspection and the existing tests exercise substantive safeguards:

- The control store uses locked revisions, checksum validation, staged writes, fsync/replace, and redo recovery. Its tests include real process termination, randomized crash sequences, and competing writers; the findings above identify integration/reconstruction compositions not established by those store-level checks.
- Standard Lead mutations verify current authority and expected revision under the same lock; stale authority is checked before revision. Handoff/takeover revokes superseded credentials. M1 specifically identifies an exception in integration reconciliation.
- Ordinary source edits make evidence STALE while preserving historical report bytes; AEW control/report writes are excluded from engineering fingerprints. M3 identifies a Git-index exception.
- Mutating dependencies remain blocked at COMMIT_READY and require DONE plus the integrated commit's presence in the downstream source lineage.
- Archetype operation/capability ceilings, evidence-kind separation, engine-owned submission fields, and role-card identity/content pinning have direct negative tests. Pin enforcement in M7 is a separate selection-policy issue.
- Reviewer context construction excludes the implementer's free-form reasoning; recorded snapshot tree IDs support reproducible source diffs.
- Ordinary integration uses Git ref compare-and-swap and rejects a moved authoritative head; the suite covers crashes at four publication points. B1/B2/M1/M6 show why those normal-path checks are insufficient by themselves.

## Merge assessment

**Unresolved: 2 Blockers, 8 Majors, 1 Minor.** The architecture has meaningful foundations, but M1's advertised safety properties are not yet established across replanning, publication recovery, and evidence ingestion. Resolve the Blocker/Major findings and turn the preserved probes into passing regressions before merging. Passing the existing suite alone cannot close these findings.
