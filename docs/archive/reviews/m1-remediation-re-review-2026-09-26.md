# Focused re-review of AEW M1 remediation

**Merge remains blocked.** Eight original findings are CLOSED; B1, M2, and M8 are PARTIALLY CLOSED. A newly enabled integration-evidence replay path is reported separately as R1, REGRESSION INTRODUCED.

Scope: remediation commits `fd196ea` through `e7e723c9ff4d5dbcd1d9c11af374e170e86758a1`, compared with `1d914cb59564303d1c1fef672dd81628bdcb0156`. This is a review of the original findings and the neighboring paths changed by their fixes, not another broad M1 review. No implementation changes were made.

## Independently verified evidence

- Full Linux/Python 3.11 suite: **526 passed in 744.53 seconds (12m 24s)**. [Output](../../../eval/reviews/m1-2026-09-26/remediation-review/suite.txt).
- Original external reviewer probe file, **unchanged**: **12 passed in 82.55 seconds**. [Output](../../../eval/reviews/m1-2026-09-26/remediation-review/original-probes.txt).
- SHA-256 of the original probe: `a45f3963b215731e3ecd8b331c7e98873ba4a546cfeb6984c8643e28d043a99b`. Its function bodies also match the imported implementation-repository copy; only non-body changes such as platform decorators differ.
- Every test file present at `1d914cb` is unchanged. The remediation adds tests rather than adjusting the original expectations.
- All frozen documents listed in `docs/spec-pin.yaml`, and the pin file itself, are unchanged from the reviewed commit: manifest, Workflow Contract v0.7, Knowledge Contract v0.4, and the SPT remediation appendix. No finding required or received a frozen-contract change.
- Six focused neighboring-path cases were executed: four reproduce remaining problems, two preserve independent descendants during directory-to-file synchronization. [Probe source](../../../eval/reviews/m1-2026-09-26/remediation-review/test_neighbor_paths.py), [initial results](../../../eval/reviews/m1-2026-09-26/remediation-review/neighbors.txt), [retired invocation result](../../../eval/reviews/m1-2026-09-26/remediation-review/retired-invocation.txt). The replay case was strengthened and rerun to confirm publication through DONE: [result](../../../eval/reviews/m1-2026-09-26/remediation-review/replayed-publication.txt).
- Windows was not independently rerun. The reported Windows count and platform skips remain implementer claims.

## Finding-by-finding disposition

| Original finding | Status | Root-cause and neighboring-path assessment |
|---|---|---|
| **B1** — superseded candidate discards newer work | **PARTIALLY CLOSED** | Candidate bindings now include plan revision/hash, acceptance sequence, and gated fingerprint. State-change hooks retire old candidates, publication checks the binding, and pending publication blocks conflicting state changes. The original probe passes. However the new cleanup guard still trusts `git status`, so hidden late source is deleted; candidate evidence also remains incompletely bound (R1). |
| **B2** — reconciliation overwrites staged work | **CLOSED** | Sync now compares index and working-copy mode/object entries against the base/candidate before writes. Pre-CAS checks are repeated during finalization. The original probe passes, as do the new LF-exact staged-change, intermediate-state, and unsupported-flag cases. Independent staged and untracked descendants in a directory-to-file case survive the operation in the additional probes. No data-loss bypass was found in this focused sync review. |
| **M1** — stale revision rejected after publication | **CLOSED** | CAS, sync, and DONE now occur under one `lead_txn`, after authority, revision, and manifest-pin checks. The original stale-revision probe passes. The interleaved-writer test and existing publication crash matrix exercise the neighboring entry points. The authoritative Git ref still uses CAS. |
| **M2** — live old invocations and workspace retargeting | **PARTIALLY CLOSED** | Replan acceptance revokes old attempts and releases the workspace; capacity counts live workspaces independently of phase, including the current Ticket; check/implementation resolution verifies the invocation's path. Both original probes pass. Candidate retirement, however, leaves integration verifier credentials active, and verification submission bypasses the new live-workspace check. |
| **M3** — index flags hide relevant inputs | **CLOSED** | Snapshot synthesis clears assume-unchanged flags only in the temporary index, disables the relevant cache settings, and fails closed on sparse/skip-worktree entries. The original probe and new flag/config tests pass. The same flag remains dangerous in B1's separate cleanup decision, not in the repaired fingerprint calculation. |
| **M4** — submitted reports satisfy ingested gates | **CLOSED** | Review and verification evaluators require accepted evidence id plus content hash; implementation/check acceptance retains its explicit separate path. The original probe passes, and both-verifier-submissions-before-ingestion is covered by the new composition test. R1 concerns accepting a report for the wrong candidate/plan at ingestion, not counting an un-ingested report. |
| **M5** — interruption bypasses failure classification | **CLOSED** | The phase-driver map only interrupts a Ticket when the lost invocation drives its current phase. Evidence/decision states retain their pending obligation. The original failure-classification probe passes; neighboring tests cover review failure and a publishing Ticket with a verifier straggler. No alternate classification bypass was established in these changed paths. |
| **M6** — mode-only sync cannot converge | **CLOSED** | Sync compares modes/types as well as object IDs and materializes filemode changes. The original executable-bit probe passes on Linux; file/symlink and file/directory cases exercise the changed machinery. Unsupported sparse/gitlink paths fail closed. |
| **M7** — operator pins ignored | **CLOSED** | Existing staffing entries now acquire operator pins, Lead re-selection preserves them, and explicit executor dispatch checks the pin. Both original probes pass. The override test verifies that a different executor requires a reason and recorded staffing decision. Additional reviewers/verifiers still cannot remove pinned gates. |
| **M8** — stale manifest after recovery | **PARTIALLY CLOSED** | The store hook refreshes the manifest after recovery and commit apply under lock. The original first-resume probe passes, as do authority-list/resume long-lived-instance tests and mid-apply recovery. Public reads that never open a store session can still return a cached old manifest; `role_list()` reproduces this after manifest adoption by another engine. |
| **N1** — unsupported path restriction advertised | **CLOSED** | ADR-0006's amendment explicitly says `restrict.paths` is deferred and rejected by M1; implementation-status records that limitation. The schema remains fail-closed. N1 had no original executable probe; closure is based on the documentation/schema diff. |

## Remaining B1 defect: cleanup still deletes hidden late source

**Affected:** `IntegrationOps._settle_ticket_workspace`, `src/aew/engine/integration_ops.py:291`, and `worktrees.inspect`, `src/aew/workspace/worktrees.py`.

After preparing and validating the integration candidate, mark `calc/core.py` assume-unchanged and edit its contents. Publication succeeds and DONE cleanup removes the Ticket workspace, including those late edits. This reproduction does not forge state or use a stale Lead token.

The new guard asks `worktrees.inspect()` whether the workspace is dirty. That function uses `git status --porcelain`, which honors the content-hiding flag. It therefore reports a clean workspace at the integrated Ticket commit even though its source bytes have changed. The M3 fingerprint fix does not protect this separate deletion check.

**Impact:** The original old-candidate publication path is fixed, but the claimed root property that cleanup preserves newer engineering output is not. This remains a Blocker because it loses user/agent source edits.

**Needed to close:** Base removal eligibility on a content-aware comparison that cannot suppress relevant inputs through index flags; fail closed or retain the worktree when certainty is unavailable. Preserve the real index flags.

**Evidence:** `test_done_cleanup_preserves_assume_unchanged_late_source` in the follow-up probe and `neighbors.txt`.

## Remaining M2 defect: retired-candidate verifier can still submit

**Affected:** `IntegrationOps._retire_integration`, `src/aew/engine/integration_ops.py:55`; `EvidenceOps.submit` / `_verification_binding` in `src/aew/engine/evidence_ops.py`.

Dispatch an integration verifier for prepared candidate A and run its check. Return the Ticket to RUNNING, retiring A. The integration record is now absent, but the verifier remains active. Using its original credential through `aew submit --kind verification` still records a passing report for the retired candidate.

The new `_invocation_workspace()` guard is used by check execution and implementation submission, but not review/verification submission. Candidate retirement moves the record to history without revoking its invocations. The caller's working directory need not be the retired workspace: the engine accepts the credential against the authoritative root.

**Impact:** Workspace-bound execution is corrected on the tested replan/check path, but authority outlives the integration assignment it represents. It also supplies artifacts usable by the replay path below. The new invariant oracle itself requires active integration invocations to reference the current candidate; the tested random walks do not cover this sequence. Running that oracle on this reproduction reports `INV-0004 (integration) is not bound to the current integration candidate`.

**Needed to close:** Revoke the retired candidate's invocations as part of retirement, and enforce the invocation/candidate association on submission and ingestion paths as well as checks. Historical reports should remain durable, without retaining write authority.

**Evidence:** `test_retiring_candidate_revokes_its_verifier_submission_authority`, `retired-invocation.txt`.

## Remaining M8 defect: session-free reads retain the old manifest

**Affected:** `EngineBase.manifest`, `src/aew/engine/base.py:58`; `RoleOps.role_list` / `role_catalog`, `src/aew/engine/role_ops.py:34`.

A long-lived Engine first lists the catalog. Another process changes `project.yaml` to point at a new catalog and successfully adopts the manifest. A fresh Engine lists its new card, while the original Engine's next `role_list()` still lists the old catalog.

The refresh hook runs on store sessions, but the manifest property reads the store only when no cached value/error exists. The public catalog query opens no session. This leaves the original cache-root-cause partially addressed.

**Impact and limit:** The reproduced residual is a stale public catalog read. The first post-crash resume and session-based authority mutations are corrected; this probe does not establish that those corrected writes use a stale manifest. The residual is narrower than the original recovery failure, but the claim that long-lived engines no longer serve old manifests is not true across the public read APIs.

**Needed to close:** Establish a recovered snapshot for manifest-consuming public reads, while avoiding recursive acquisition from callbacks already inside the store lock.

**Evidence:** `test_long_lived_role_catalog_refreshes_adopted_manifest`, `neighbors.txt`.

## R1 — REGRESSION INTRODUCED: replacement candidate can publish using superseded-plan evidence

**Severity:** Major. **Related findings:** B1/M2, with an ingestion boundary adjacent to M4.

**Affected:** `EvidenceOps.verify_ingest`, `src/aew/engine/evidence_ops.py:519`, and `IntegrationOps._post_integration_ok` in `src/aew/engine/integration_ops.py`.

Reproduction:

1. Reach COMMIT_READY under plan v1 and prepare integration candidate A.
2. Submit, but do not ingest, a passing integration report for A.
3. Replan to v2; the old verifier is revoked and A is retired. Keep engineering bytes unchanged, then complete fresh Ticket implementation/review/verification under v2.
4. Prepare candidate B, bound to plan v2 and the newer COMMIT_READY sequence.
5. Ingest A's saved report. It is accepted for B, despite its old plan and workspace identity.
6. Publish B. The engine reaches DONE without fresh integration verification for B/v2.

`_require_current_binding(unit)` verifies B against the current Ticket acceptance. It does **not** compare the evidence or producing invocation to that binding. The next check compares only the engineering fingerprint. Publication again checks the fingerprint and check IDs, not the report's plan/candidate binding. Identical source bytes therefore let a report from a revoked prior assignment satisfy the replacement candidate.

**Why classified as newly enabled:** Running the same replacement sequence against `1d914cb` fails at the second `integrate prepare` because the old prepared candidate remains attached. The remediation correctly enables supersession/replacement, but exposes an existing ingestion weakness on this new path. The classification does not imply that the old revision had a correct evidence-binding implementation.

**Needed to close:** At integration ingestion and publication, validate the report's plan revision/hash and invocation's candidate/workspace/acceptance association against the candidate being accepted. A matching content fingerprint alone must not erase those bindings. Retain stale evidence historically and require appropriate current verification.

**Evidence:** `test_superseded_plan_integration_report_cannot_validate_new_candidate`; `replayed-publication.txt` confirms DONE; `baseline-comparison.txt` shows the original revision rejecting the replacement path.

## Final assessment

- **Unresolved Blockers:** B1, PARTIALLY CLOSED — hidden late source can still be deleted.
- **Unresolved Majors:** M2 and M8, PARTIALLY CLOSED; M8's demonstrated residual is limited to stale manifest-dependent public reads.
- **New regressions:** R1, REGRESSION INTRODUCED — newly enabled replacement-candidate workflow accepts superseded-plan integration evidence and publishes.
- **Findings confirmed closed:** B2, M1, M3, M4, M5, M6, M7, N1.
- **Remaining review finding that should block M1 merge:** Yes. B1's data loss and R1's stale evidence publication are independently sufficient.
