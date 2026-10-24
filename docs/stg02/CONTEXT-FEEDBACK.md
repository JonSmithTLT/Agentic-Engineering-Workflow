# STG-02 handoff context feedback

Intake checkpoint, 2026-10-19.

Useful: the field map identifies exact owner pins, immutable schema paths, version headers, nondisclosing errors and consumer directives. The explicit separation from the provisional dashboard prevents an accidental wire migration. The six-step journey and independence rule are actionable.

Missing or needing care:

1. The old website checkout's Git registration was gone. Operator approved a fresh worktree; existing source files were preserved. Future handoffs should give a verifiable source commit in addition to a directory alias.
2. The named examples are not one linked story, and the integrated command examples omit inherited C17. WEB-STG02-001 records the exact identity locations; an explicit fixture manifest for the whole journey would reduce accidental inference.
3. Recorded fixture validity is relative to the recording clock. WEB-STG02-002 records the distinction; a handoff should specify whether a preview replays an as-of recording or uses newly issued unqualified fixture facts.
4. The adopted schema files still contain historical proposed/not-adopted labels. Operator adoption governs; preserve those bytes and display the selected package digest alongside their original schema version rather than “correcting” the sealed source.
5. Available Python runtimes differed in JSON Schema support. A repeatable input check needs Draft 2020-12, not merely a package named jsonschema.

Unused so far: sealed oracle Python, backend implementation and backend notes. They have not been needed to validate the input schemas. Joint-test details and rendered workflow feedback remain pending.

Later 2026-10-19: operator clarified the four unwitnessed A-23 examples. This agrees with the intake's structural-only claim and requires no view rework. The website continues to render supplied stamps without treating fixture qualification labels as independently proven guarantees. The designer's explicitly permitted fixture service uses the sealed oracle internally; consuming that service is distinct from using its model as a semantic oracle for website tests. No backend code or notes have been consulted.
