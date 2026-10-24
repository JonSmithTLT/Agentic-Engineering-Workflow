**A known gap in readers' sandboxes, found by CB-09's sandbox test (2026-10-23): a read that fingerprints a workspace
fails there.** This predates STG-05 (it is M4-B's reader layout). It is pinned, shrink-only, as
`READER_GIT_GAP` in `tests/helpers/worker_surface.py`, and was reported to the designer for the reader layout of
CS-2 and CS-4.

- **The mechanism.** `aew.snapshot.fingerprint._working_index` runs `git add -A` into a throwaway index.
  - git has to write the blob of every changed file, and of every racily clean one: in a fresh worktree, the files
    share the index's timestamp second, so git re-hashes them.
  - For a blob that already exists, git first tries to freshen it, and on failure it writes it again.
  - A reader's layout has no private object store, only the real one, bound read-only, so both writes fail
    (`unable to create temporary file: Read-only file system`). The command answers `GIT_ERROR`.
  - Writers are unaffected: they have a private index and object store, with the real objects as alternates.
- **Its two faces.** The pin sees only the first.
  - **In a reader's sandbox,** the read fails as above.
  - **Outside a sandbox** (every worker run on Windows, and any non-writer run uncontained), the same read succeeds by
    writing loose objects into the real repository's `.git/objects`. In #231's re-review, a worker's `gate show` of
    the in-flight Ticket added 3. No test sees this: the tree diff judges `.aew` only.
- **Its reach.**
  - The engine computes the fingerprint through `invocations.snapshot_of` and `current_snapshot`, and through
    `worktrees.status`.
  - The sandbox test's run decides which read commands reach it. On a project whose in-flight Ticket has an edit
    not yet committed, those are `gate show` and `work roles` for that Ticket.
- **The designer ruled the outcome (D-CS2-1, 2026-10-23).**
  - A fingerprint is a read. It works in a reader's sandbox, for a changed or a fresh workspace, and equals a
    writer's value for the same tree.
  - A reader still writes only its scratch and harness state, never the real object store.
  - Either fix is acceptable if it keeps that boundary: a fingerprint computed without writing objects (preferred),
    or a private object directory in the reader's scratch with the real store as a read-only alternate.
  - The operator placed it in CS-2, as its outcome 7. Its fix and its test cover both faces: for example, the test
    compares `.git/objects` before and after a non-writer's read. When it lands, the pin empties.
- **The two other outcomes of this fix round.**
  - A non-writer writes neither the store nor the control lock.
  - Under `.aew/local` a non-writer writes only the derived history index's catch-up, which every reader of archived
    history makes, the dashboard server included. Every result of that index is authenticated against the store's
    history root, and on a read-only view it is a private copy instead.
