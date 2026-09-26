# ADR-0002 — Evaluated-snapshot fingerprint

- **Status:** Accepted (M1)
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
