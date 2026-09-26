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
