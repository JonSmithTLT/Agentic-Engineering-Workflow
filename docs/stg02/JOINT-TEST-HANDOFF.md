# STG-02 joint test handoff

Date: 2026-10-20 local / 2026-10-21 UTC. Author results; designer decision pending.

Run 2 used unchanged website runtime `af77308aa48cbc73a73791b58b807c0a9ebdbe55` and exact-reviewed wrapper `f8dd097cf9f929c1759820b66b4f169cb32fad11`, against reviewed backend `966fc2c610c7b9e26c8d9d9f004139532c956520` with fresh synthetic `joint-state-2`. Backend and website remote CI are not observed. No production build or wire-contract change was made for this run.

The six journey steps and four probes were exercised at 1440 and 390 responsive widths. The repaired percent-encoded owner GET now returns the matching operation through the product UI. Reload does not submit again. Unknown IDs and withdrawn reads are nondisclosing; unavailable engine-backed detail shows 503 while waiting remains partial. Protected actions remain held text with no controls.

Controlled response loss: the real replay response was withheld at a browser barrier, the owned wrapper stopped before the application deadline, and the UI showed unknown outcome. After restarting the same wrapper within its original expiry, explicit reconciliation returned the same key/body and byte-identical stored receipt. The backend owner reports exactly one key and one operation after three POSTs. This instrumented staging does not claim an unassisted TCP-loss test.

Designer decisions remain:

1. JT-01 / WEB-STG02-004: waiting has no supplied eligible run link. The browser did not invent one; the fixture run ID was entered separately as the brief directs.
2. JT-02 / WEB-STG02-005: interim `SOURCE_UNQUALIFIED` is structurally valid but not adopted vocabulary. It is rendered raw without an authority or permission inference.
3. WEB-STG02-006: accept or request further coverage for the explicitly controlled lost-response staging. Run 1's timeout-first attempt remains preserved as limited.

Naming crosswalk: **website JT-03 = backend JT-02**, the corrected encoded owner path. The backend correction applies to O-01; D-01 IDs still reject percent sequences. Run-1 capture/staging failures were not erased: one early work-503 capture was inconclusive and was repeated in run 2 with completed-state captures.

Full chronology, exact normalized commands and source/build identities: [JOINT-TEST-NOTES.md](JOINT-TEST-NOTES.md). Triage register: [GAP-ENTRIES.md](GAP-ENTRIES.md). Selected hashed evidence: [run 1](evidence/joint-run-1/README.md), [run 2](evidence/joint-run-2/README.md). No independent acceptance or fulfilled charter exit is declared by the author; the designer owns that decision after both sides commit their notes.
