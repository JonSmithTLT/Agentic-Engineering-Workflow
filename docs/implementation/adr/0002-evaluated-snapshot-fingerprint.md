# ADR-0002 — Evaluated-snapshot fingerprint

- **Status:** Accepted (M1). Amended 2026-09-29: check results are bound to their check definition.
- **Spec basis:** WC §9.9, invariant 7; KC §11, §26 (validation staleness)
- **Nature:** Implementation choice. The spec permits "content hashes, dirty-file manifests, synthesized tree IDs, build artifact digests, or another deterministic fingerprint".

## Decision

An evaluated snapshot is `{base_revision, workspace_id, relevant_inputs_fingerprint, artifact_digests[]}`. The fingerprint is a **git tree id synthesized in a throwaway index**:

1. Copy the workspace's real index to a temporary index, so the stat cache is reused.
2. `git add -A` to capture tracked files plus untracked files that are not ignored.
3. `git rm --cached .aew` plus any policy `fingerprint.exclude` paths.
4. `git add -f` any policy `fingerprint.include_ignored` paths.
5. `git write-tree`, giving `git-tree:<oid>`.

## Consequences

- Writing AEW control, evidence or report files never changes the fingerprint of the evidence being recorded (WC §9.9). A relevant uncommitted source, config or generated input always does.
- The real index is never touched.
- Gate evaluation compares evidence fingerprints to the **current** fingerprint. Passing evidence for another snapshot is `STALE`: it is kept historically but does not satisfy the gate.
- Because the fingerprint is a real tree object, reviewer packs regenerate the exact diff later (`git diff <base> <tree>`) even after the workspace moves on.
- Documented limits:
  - dirty state inside submodules is not captured;
  - Git LFS contributes pointers, not content;
  - differences that git's filters normalize (line endings under `autocrlf`) hash identically. They would also commit identically.

## Amendment 2026-09-26 — independent review (M3)

The review showed that copying the real index into the temporary index also copied flags that make Git **skip reading** the working copy. A source marked `assume-unchanged` could change after verification without changing the fingerprint. That is not one of the documented limits (submodules, LFS, normalized line endings).

- These flags are neutralized **in the temporary index only**. The user's real index is never modified.
  - `assume-unchanged` bits are cleared (`update-index --no-assume-unchanged`).
  - `core.ignoreStat`, `core.fsmonitor` and `core.untrackedCache` are forced off for snapshot synthesis, through `GIT_CONFIG_COUNT`; git ≥ 2.31 is already the floor.
- **Skip-worktree entries** (sparse checkout) are **refused** with an integrity error. Their content is not in the workspace, so no honest snapshot of it exists. AEW workspaces are full checkouts.
- The same handling applies to `changed_paths` (guardrails) and `working_diff` (reviewer packs), which share the temporary index.
- Tested: an assume-unchanged edit changes the fingerprint and invalidates VERIFIED gates (review probe M3); `core.ignoreStat` does too; an unflagged workspace hashes to its content tree exactly as before; skip-worktree is refused; the real index flags are unchanged afterwards (`tests/integration/test_fingerprint_flags.py`).

## Amendment 2026-09-29 — a check result is also bound to its check's definition (independent audit I1)

The fingerprint deliberately excludes `.aew/` policy files, so a check result's snapshot said nothing about **which check** ran. The designer's independent M3 audit reproduced the gap: a passing `unit` result stayed `CURRENT` after `unit`'s command in `policy/checks.yaml` changed, so one check id stood for two acceptance conditions.

**Decision (operator, 2026-09-29): option (a).** An in-flight Ticket satisfies the check as it is defined *now*.
- Every check result records `check.definition_sha256`: a digest of the definition that ran. For a configured check that is its command, working directory and timeout (a description is not part of it). For the builtin guardrails check, it is the guardrails policy it evaluated.
- The `local_checks` gate counts only results for the current definition. A pass for an earlier definition is `STALE`, with the reason, so the check must run again.
- A policy-required post-integration check counts only under its current definition (`_require_bound_validation`), and a verifier cannot cite a check that ran under a definition since changed (refused at `submit`).
- A result recorded without a definition (before this amendment), or for a check no longer configured, proves nothing about the current check.

**Boundary.** A verification report already ingested stays ingested when a definition later changes. The Ticket still cannot proceed on it: its own `local_checks` gate goes `STALE`, and a re-run under the new definition is required before COMMIT_READY and publication.

Regressions: `tests/regression/test_m3_independent_audit.py` (`test_a_passed_check_goes_stale_when_its_definition_changes`, `test_a_post_integration_check_counts_only_under_its_current_definition`), written first and seen failing.

## Amendment 2026-10-23 — a fingerprint is a read (STG-05 CS-2, designer ruling D-CS2-1)

A read that fingerprints a workspace (`gate show` and `work roles` of a Ticket with uncommitted edits, or of a fresh worktree) ran `git add -A` into a throwaway index, which writes or freshens a blob for each changed or racily clean file, and `write-tree`, which writes trees. A reader has no private object store. So in a reader's sandbox, where the real store is read-only, the read failed with `GIT_ERROR`; outside one (every worker run on Windows, any non-writer run uncontained) it wrote loose objects into the real repository. The designer ruled the outcome: a fingerprint read works in a reader's sandbox, equals a writer's value for the same tree, and a reader never writes the real object store, inside a sandbox or outside one.

- **A non-writer writes no object** (`aew.process_kind`: a worker's `aew`, the dashboard's server, the Lead's MCP transport). Its throwaway index is filled from the statuses `git add -A` itself acts on (`diff-files`: a deleted path is removed, any other re-added; a file replaced by a directory counts as deleted), plus every untracked path that is not ignored, through `update-index --add --replace --info-only`, which hashes through the same filters and stores nothing. `include_ignored` adds every untracked file under its path the same way (what `git add -f` did). Every tree id is hashed in Python from the index entries, in the repository's object format, with git's ordering (a directory compares as its name plus `/`), leaving out intent-to-add entries and the empty trees they leave, as `write-tree` does. An index with unmerged entries still has no tree (`GitError`, "unknown" to callers).
- **A store writer keeps storing what it hashes** (`git add -A`, `write-tree`), with the same values. The engine reads a writer's snapshot tree back from the store: the reviewer's and verifier's packs diff the base against it (`engine/context_ops.py`), and a mutated workspace's refusal names the paths between two snapshots (`evidence_ops._paths_between`). Computing nothing stored there made `invoke create --role reviewer` fail with "bad object" (found while building; the designer's ruling leaves writers unaffected).
- **The process's kind is behaviour, not the boundary.** In a reader's sandbox the store is read-only whatever a process declares.
- **`index_only_paths`** compares the entries of HEAD, the index and the working index instead of diffing two trees, which need not be in a store.
- **`working_diff`** still stores what it adds, in any process: a unified diff reads blob content. Nothing in `src` calls it (this ADR's 2026-09-26 amendment names it for reviewer packs, which now diff against the snapshot's tree); it is flagged under "requirements are the authority", and its keep-or-remove question is with the designer and the operator.
- **On Windows,** a file named after a device is refused by name before anything is hashed, as before: `update-index` would read the device, where `git add` failed on it.

Tests: `tests/integration/test_fingerprint_reads.py` runs every case (uncommitted edits with deletions, ignored and excluded files and a file replaced by a directory; git's tree order; an empty repository; CRLF with `core.autocrlf`; an intent-to-add entry; an unmerged path; an embedded repository and a gitlink at another commit; a symlink and an executable bit; a worktree just made) as a reader and as a writer, on every platform: each value equals git's own (`add -A` and `write-tree` into a private object directory), the reader's leaves the real `objects` directory and index unchanged by digest, and the writer's tree is in the store. The worker-surface tests judge the real object store across every command a worker can run, outside a sandbox (`tests/integration/test_non_writer_reads.py`) and inside a reviewer's (`tests/integration/test_containment.py`, where `READER_GIT_GAP` is now empty), and a reader's fingerprint in its sandbox equals the writer's for uncommitted edits and a fresh worktree.
