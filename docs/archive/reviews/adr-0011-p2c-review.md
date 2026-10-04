# ADR-0011 P2c independent review

## Target and scope

- PR #20: `JonSmithTLT/Agentic-Engineering-Workflow`, branch `impl/adr-0011-p2c-history`.
- Target: `db23e895875bb78807aa7f986be4565045e49094`. The implementation is in `bdabff9`; the target adds the regenerated Lead guide.
- Base: `91c0d980055804516d80a6bf2a0567f4408bd6ce`, containing the merged P2a/P2b fixes.
- Source frozen with `git archive` into `AEW-P2c-review-db23e89-d61aed`; the base was independently extracted under `base/`. All 25 changed files were byte-compared with the target Git blobs after validation: no differences.
- Read the PR description, ADR-0011 (located under `docs/implementation/adr/`, rather than the prompt's `docs/decisions/`), implementation-plan sections 3, 4, 8, R2 and P2c as built, and the entire 25-file diff.
- Reviewed history commands, audit recording/retry, finalization, reference packs, policy/status/closeout, schemas, generated ports/guide, and changed tests and documentation.
- Installed the frozen source and development/parallel test dependencies into this review copy's private Windows Python 3.13 environment. Confirmed both the interpreter and imported AEW source resolve inside this copy. Ran the requested fast, non-serial and serial lanes in order, plus disposable independent CLI/API probes.
- The active P2d checkout was used only for read-only Git operations. No tests, installs, changes to its files or branch, or public PR actions were performed.
- The two operator-approved choices (the Epic helper's audit and checking the caller's revision at the initial audit snapshot) are not findings.

## Recommendation

**Request changes.** Six verified findings: one High/P1, four Medium/P2, and one Low/P3. The passing repository suite does not cover these failing composed sequences.

## Findings

### P2c-1 — High / P1: A full audit certifies history with corrupted reachable evidence and allows Epic closeout

Location: `src/aew/engine/history_ops.py:262`; the retry uses the same verifier at line 286. The underlying record loop is in `src/aew/history/store.py:260-277`.

The new public audit delegates entirely to `History.verify`, which hashes each manifest entry's payload file. For a unit, that payload is `archive.yaml`. It does not follow the archived unit's hash-pinned evidence references. Consequently a full pass can certify the current root while an accepted evidence record reachable from that root is corrupt. This violates ADR-0011's full verification of all reachable cold records, and the false pass discharges the new Epic audit gate.

**Actually executed**, using real CLI transitions in a disposable project:

1. Create and plan an Epic and Story; dispatch, submit, ingest and accept an investigation under the Story.
2. Review, verify and close the Story; submit and ingest the Epic's review and verification.
3. Execute a checkpoint to settle transaction recovery, then append a comment to the completed investigation's sealed discovery evidence file. Leave the archive bundle and its manifest hash unchanged.
4. `history show INV-0001-discovery-1` correctly exits with `INTEGRITY_ERROR`: the content differs from the hash recorded at ingest.
5. Epic closeout is initially refused with `GATE_UNSATISFIED`, reporting two unverified history entries.
6. Record `history audit --full`: it exits successfully, reports `ok: true`, `problems: []`, and creates `AU-0001`. `cold.verified` now equals the current root.
7. Repeat Epic closeout: it succeeds and archives the Epic, despite the still-corrupted descendant evidence.

A separate fixture reproduced successful **advisory and recorded** full audits against damaged evidence. As a positive control, modifying the unit's archive bundle instead made the full audit return `INTEGRITY_ERROR`.

The corruption is an unsynchronized file change inside the repository trust boundary; this finding makes no claim about defeating hashes by rewriting authority. Extend both initial and retry verification to the reachable records covered by the audit promise, preserving verification outside the lock and attribution to the owning unit. Add the descendant-evidence/closeout regression.

Evidence: `review_p2c_epic_probe.py`, `review-p2c-epic.jsonl`; `review_p2c_probes.py`, `review-p2c-probes.jsonl` (`evidence_audit`, `bundle_audit_positive_control`).

### P2c-2 — Medium / P2: Loading a Lead record exposes credential verifiers in context packs

Location: `src/aew/engine/archive_ops.py:573-574`; consumed by `src/aew/engine/context_ops.py:124`.

`history show` recursively redacts verifiers, but the new reference-pack path reads the raw archive and passes it to `reference_summary`. Its non-unit branch dumps every field except `schema`, including the Lead archive's credential verifier fields. Redaction therefore disappears when the same record is loaded into an invocation.

**Actually executed**:

1. Offer and accept a Lead handoff, archiving `LEAD-0001`.
2. `history show LEAD-0001` redacts both credential verifiers.
3. Load that Lead archive into a live investigation with `history load LEAD-0001 --into T-0003 --reason ...`.
4. Dispatch the investigation and read `context show` for its invocation.
5. Both original verifier values appear in the context output. Regeneration reports `matches_recorded: true`, so this is also part of the recorded pack.

These are credential verifiers, rather than raw bearer tokens. Their exposure still violates the explicit output requirement and gives model/harness context fields that the history display deliberately removes. Apply consistent recursive redaction before rendering every reference kind, and cover the load/dispatch/context sequence.

Evidence: `review-p2c-probes.jsonl`, `lead_reference_redaction` (records counts, without printing verifier values).

### P2c-3 — Medium / P2: A discoverable model-authored historical record cannot be selectively loaded

Location: `src/aew/engine/history_ops.py:217-220`; unit-only fallback content at `src/aew/engine/archive_ops.py:575-587`.

`history show` resolves evidence IDs through a containing archive's links, but `history load` only accepts IDs with their own manifest entry. Accepted discovery/research records are linked evidence, so the new load surface cannot load the exact model-authored record that the show surface successfully returns. Loading its owning unit gives an engine-labelled outcome/provenance summary that omits the research facts and record body. It does not provide the requested historical material as reference context.

**Actually executed**:

1. Finish an investigation with accepted discovery record `INV-0001-discovery-1`.
2. `history show INV-0001-discovery-1` succeeds and labels its contents `source: model`.
3. Create a live follow-up investigation and attempt `history load INV-0001-discovery-1 --into T-0002 --reason ...`, with the valid Lead token and current revision.
4. The command exits 2 with `NOT_FOUND`, claiming the ID is not a historical record.
5. Load `T-0001` instead and dispatch the follow-up. The historical section contains the discovery record's ID/kind/result, but neither its facts nor body; its source is `engine`.

This leaves ADR-0011 invariants 12/14 and the selective loading of exact historical research/evidence unimplemented. The documentation describes the unit summary accurately, but that summary does not replace an exact evidence reference. Support linked evidence IDs with their own pinned content hash and original source classification, including per-invocation provenance and deterministic regeneration.

Evidence: `review-p2c-probes.jsonl`, `evidence_load`, including the actual generated historical section.

### P2c-4 — Medium / P2: Ordinary resume rebuilds the entire history index after cache loss

Location: `src/aew/engine/history_ops.py:367-368` and `380`; invoked unconditionally from `src/aew/engine/resume_ops.py:92`.

The new global next-actions calculation obtains audit ages through `archive.index(state)`. Synchronizing a missing derived index walks all manifest entries. This puts exhaustive history traversal back on ordinary `resume`, even though it was not asked to enumerate history and its current/recent output remains bounded. The never-fully-verified branch has the same index dependency when it obtains the first entry's date.

**Actually executed**, using an instrumented public API call against a valid disposable project:

1. Build six real history entries through investigation completion, audits and a Lead handoff; finish all hot work.
2. Delete only `.aew/local/history.sqlite`, the explicitly disposable derived cache.
3. Spy on `History.walk` without changing source and call `Engine.resume()`.
4. The call traverses all six entries (`T-0001`, `T-0002`, `AU-0001`, `AU-0002`, `LEAD-0001`, `T-0003`), while returning only three bounded recent work records.

The demonstrated defect is exhaustive traversal, not a measured breach of the 0.25-second performance criterion; no large-corpus timing claim is made. ADR-0011 explicitly excludes exhaustive historical traversal from normal resume. Keep the audit-age facts needed by active commands in bounded, transactionally maintained state or retrieve them without requiring a full index rebuild. Rebuild the derived history index on explicit history access.

Evidence: `review-p2c-probes.jsonl`, `resume_index_rebuild`; probe uses `unittest.mock.patch.object` to count actual manifest visits.

### P2c-5 — Medium / P2: Reindex emits a raw traceback under ordinary Windows database contention

Location: `src/aew/engine/history_ops.py:202`.

The new reindex command unlinks the SQLite file before syncing. On Windows, an open connection prevents that unlink. This raises an uncaught `PermissionError` instead of the CLI's JSON error response. An overlapping history-index operation can therefore turn a normal public command into an unstructured failure.

**Actually executed**:

1. Populate a valid index with `history list`.
2. Hold a separate `sqlite3.connect` connection and `BEGIN IMMEDIATE` transaction on it.
3. Invoke `history reindex` in a separate hidden process.
4. It exits 1 with empty stdout and a Python traceback ending in:

   ```text
   history_ops.py, line 202, in history_reindex
       index.path.unlink(missing_ok=True)
   PermissionError: [WinError 32] The process cannot access the file because it is being used by another process
   ```

5. Roll back and close the connection; repeat the same command. It succeeds and rebuilds six entries.

Coordinate rebuilding with index users, and convert filesystem/database contention into a supported JSON error. The existing SQLite busy handling in index synchronization does not cover this earlier unlink.

Evidence: `review-p2c-race.jsonl`, `reindex_contention`; also independently reproduced in `review-p2c-probes.jsonl`.

### P2c-6 — Low / P3: History output includes internal storage paths forbidden by the review contract

Location: `src/aew/engine/history_ops.py:125` and `204`.

The review brief explicitly requires no storage paths in output. `history show` returns the raw manifest entry, including `entry.path`; `history reindex` returns the absolute path to the derived SQLite file.

**Actually executed**: `history show T-0001` returned `entry.path: work/T-0001/archive.yaml`; successful `history reindex` returned the fixture's absolute `.aew/local/history.sqlite` path. The repository reindex test itself relies on this path to remove the cache.

This is an output-contract discrepancy, not a demonstrated credential leak or filesystem security boundary failure. The docs' weaker promise of access without *knowing* storage paths does not enforce the brief's stronger requirement. Project public identifiers/hash/provenance fields into the output and remove internal storage-location fields; adjust the test's cache setup accordingly. This finding concerns internal archive/index locations; no claim is made that every engineering artifact path in provenance should be removed.

Evidence: `review-p2c-probes.jsonl`, `storage_paths`; successful `reindex_contention` responses.

## Independent evidence

- `review_p2c_probes.py` / `review-p2c-probes.jsonl`: exact evidence load, full-audit damage and positive control, Lead pack redaction, cache-loss resume traversal, storage paths and reindex contention.
- `review_p2c_epic_probe.py` / `review-p2c-epic.jsonl`: corrupted reachable evidence, initial closeout refusal, false full-audit pass and successful Epic closeout.
- `review_p2c_race_probe.py` / `review-p2c-race.jsonl`: independent index contention and adversarial R2 verification of newly appended damaged history.
- Final successful executions of all three scripts have empty corresponding `.stderr` files. Fixture state and source are retained in this review directory. Mutated evidence/bundles were restored after each damage probe.
- An initial race-probe attempt hit transaction recovery's earlier write revalidation, rather than audit verification. The final probe checkpoints the concurrent archival transaction before damage, eliminating that confound. Its retained final output shows the audit itself records the failure.
- No implementation or repository-test files were modified to reproduce findings. The separate `run_review_lane.py` runner asserts private import/interpreter resolution and adds `CREATE_NO_WINDOW` to Windows subprocesses before invoking pytest.

## Test results

All requested lanes completed in order, with no repository-test failures:

| Lane | Pytest arguments | Result | Time | Log |
| --- | --- | --- | --- | --- |
| Fast | `-q -p no:cacheprovider -p no:xdist --lane fast` | 620 passed, 1 skipped, 548 deselected | 19.42 s | `review-fast.log` |
| Full non-serial | `-q -n auto -m "not serial"` | 1,147 passed, 5 skipped | 1,066.37 s | `review-nonserial.log` |
| Serial | `-q --lane serial` | 16 passed, 1 skipped, 1,152 deselected | 22.47 s | `review-serial.log` |

The non-serial and serial lanes together cover **1,163 passing tests and six skips**. The fast lane overlaps the non-serial lane and is not added to that unique total. All 16 P2c surface tests passed within the full run.

Skip details:

- Non-serial: three worktree POSIX filemode/symlink tests (`test_worktree_sync.py:170,185`), one POSIX filemode regression (`test_review_2026_09_26.py:98`), and the tagged-Git-revision spec check (`test_spec_pin.py:61`).
- Serial: POSIX pty operator path (`test_authority.py:200`).
- The Git-revision check is skipped because the required frozen source is a Git archive. The other five skips concern Windows platform behavior. This explains the non-serial count difference from the PR's 1,148 passed / four skipped claim.

`git diff --check` between the exact base and target: clean. All 25 changed target files: byte-identical after validation.

This is a full run of the requested Windows repository lanes at their default budgets. Linux/Rocky, extended nightly budgets, live model runs and P2d are outside this validation. Independent probe failures are the finding evidence, rather than failures in the existing suite.

## What was checked and found sound

- **R2 snapshot/recording structure:** root state and mutable tail bytes are copied together under the control lock; verification calls occur after releasing it. Root movement triggers incremental verification from the previous target, with a five-attempt bound in source. The approved initial-revision/then-current-recording behavior is implemented as described.
- **R2 executable race:** the repository's real-process root-movement test passed. The independent adversarial probe paused an incremental audit, committed another unit, settled its transaction, corrupted that new unit's bundle and resumed the auditor. It checked exactly the one new entry, recorded a failed `AU-0002` plus annotation, returned JSON `INTEGRITY_ERROR`, and preserved the prior verified root. Restoring the bundle allowed a recorded full audit to pass.
- **Self-link and backlog:** the audit entry records its substantive target, validates its own hash-chain link locally, and includes its own entry in `cold.verified`. Passing tests confirm no one-entry backlog and full-audit `last_full` updates. Failure tests and the independent race confirm failed audits do not advance verification.
- **Finalization:** `ctx.entries` are included in the finalizer's work guard and placed before other transaction entries in one append; context/finalizer ownership and port composition tests pass. No duplicate append or lost entry path was found in the reviewed recording flow.
- **Crash point:** the `history.audit_before_record` real-process termination/recovery test passed. It checks that the pre-record crash leaves the history root and verified point unchanged and recovery permits the later audit.
- **History reads:** inspected fixed list/depth/edge limits; tested stable unit/invocation/credential/evidence IDs, date filtering, current/unknown/v1 refusals, read-time hash checking, trust labels, and credential redaction in `history show`. Output/path and load-pack gaps are listed above. No large fanout timing claim is made.
- **Invocation pinning:** the reference set is copied at dispatch; later loads affect later invocations. Repository tests and independent positive controls regenerate matching recorded packs. Sources include `history:<id>`, pinned hash, trust and `reference: true`, with explicit historical/no-instruction-authority wording.
- **Policy and ordinary gate behavior:** optional defaults are 1,000 entries, 168 hours and 30 days; never-full age derives from history age; over-policy results become next actions. The normal Epic backlog refusal and audit next action work, apart from the false-pass scenario in P2c-1.
- **Schemas/docs/composition:** read schema and generated-port changes, `self.history` to `self.cold` callers, CLI wiring, guide/quickstart/status changes and test-side helper/walk changes. Composition and guide tests passed. The documentation generally describes the implementation accurately; it does not establish complete audit coverage or exact evidence loading.
