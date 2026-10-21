# STG-02 website gap entries

Date: 2026-10-19. Author-side entries for designer triage. No architecture-workspace changes. Classes below use the handoff's vocabulary. An observation is not a reopened contract boundary or an acceptance verdict.

## WEB-STG02-001 — coherent fixture journey is not supplied by the named examples

- Class: **host or profile qualification deficit**.
- Source: adopted A-23 `04-FIXTURES/LEGACY/F01-waiting-positive.json`, `$.items[*].data.work` and `$.items[*].links`; A-23 `04-FIXTURES/NEW/F05-run-multiaxis-HEB-observed.json`, `$.items[0].data.work_ref`; v0.5.4 `05-INTEGRATED-FIXTURES/continuation-full-http-200.json`, `$.body.items[0].data.work_ref`; `command-requests.json` top-level keys.
- Observation: the waiting example names `T-A` and `STORY-1`, without a run link; the run names `invocation:demo-1` with null work; continuation names `ticket:one`. The integrated command examples contain attach, reattach and reaffirm, not inherited C17. These examples cannot themselves establish the one-work-item journey.
- Plausible readings: examples are independent specimens and the slice needs a separately labelled coherent fixture world; or they were intended as a directly navigable story. The latter is unsupported by their bindings.
- Interim choice: validate examples independently, never infer a run/work relation or rewrite it in the browser. Extract inherited C17 from adopted A-24, then distinguish any explicitly authored synthetic journey fixture from immutable recordings. Do not claim end-to-end journey coverage until all bindings are explicit and validated.
- Status: addressed for the author fixture journey by an explicitly derived, unqualified waiting/run fixture: same supplied `ticket:one` and `revision:one`, plus a supplied source link to `invocation:demo-1`. Original recordings remain unchanged. Browser construction/guessing is not used. Designer triage and real joint bindings remain pending; no wire change requested.

## WEB-STG02-002 — historical fixture time versus current qualification

- Class: **host or profile qualification deficit**.
- Source: v0.5.4 `05-INTEGRATED-FIXTURES/continuation-full-http-200.json`, `$.body.projection_as_of`, `$.body.items[0].source.renewal.valid_until` and axis `valid_until`; A-23 waiting/run `source.renewal.valid_until`; selection profile section “Reason and observation contract”.
- Observation: recordings describe finite validity intervals at their recorded clock. The referenced A-23 recordings expire before the date of this implementation; new recordings expire during 2026-10-19. Replaying today cannot establish current owner facts merely because HTTP just succeeded.
- Plausible readings: replay is explicitly at the recorded fixture clock; or a current demo uses fixture-issued unqualified observations. Silently advancing timestamps is neither.
- Interim choice: show a clear recorded-fixture identity and its as-of/last-known times; never renew or upgrade owner qualification in the browser. A current synthetic world needs separate fixture provenance and explicit unqualified stamps. Preserve immutable original recordings.
- Status: author fixture host and desktop/phone rendered checks completed. Designer triage and real source/currentness qualification remain pending; no contract amendment requested and no independent acceptance claimed.

## WEB-STG02-003 — retention duration remains an owner/host choice

- Class: **architecture gap**.
- Source: handoff field map “Where the design is expected to bend”, item 4; adopted selection profile CS-03/CS-04/CS-08, client key/ledger lifetime and expired-ledger behavior.
- Missing: a selected operational duration for request keys, receipts and owner records; schema timestamps and expired-ledger behavior do not specify that duration.
- Plausible readings: a host sets a documented finite retention policy; or retention is an additional selected profile requirement. The website cannot choose the owner's ledger duration.
- Interim choice: no browser-based expiry causes redispatch. Preserve an unresolved submission's exact request identity for reconciliation and show unresolved/unknown when the owner cannot establish it. Website-local recovery uses origin-local, package-digest-keyed tab sessionStorage for this one synthetic recipient/installation; its lifetime is the tab session, not an owner-ledger promise. Storage failure prevents sending a new command. Reload never automatically resubmits.
- Status: open design feedback; does not block fixture UI construction. Run 1's operator-relayed owner observation reports a 15-minute receipt and an operation retained until 2026-11-20. These test-host choices do not select an adopted retention policy. Backend implementation has not been inspected or retention negotiated.

## WEB-STG02-004 — pre-qualification waiting-to-run navigation

- Class: **host or profile qualification deficit**, for designer triage.
- Source: shared `JOINT-TEST-BRIEF.md`, steps 1–2; actual joint-run waiting responses, all supplied `links` arrays empty.
- Observation: waiting work cannot open its run through a supplied eligible link. A separately provided fixture run ID lets the test continue, but does not make that journey connected.
- Interim choice: preserve the absence of a supplied link. Do not manufacture associations from work IDs, prose, timestamps or the test world's known topology.
- Status: open; tracked as JT-01 in `JOINT-TEST-NOTES.md`. No frontend workaround or adopted wire change.

## WEB-STG02-005 — interim continuation reason vocabulary

- Class: **wire defect**, provisional semantic-vocabulary classification for designer triage.
- Source: shared joint brief step 3 and its BE-05/E-2 warning; actual continuation axis `reason_code: SOURCE_UNQUALIFIED`.
- Observation: the adopted structural schema accepts a string, while the brief explicitly identifies this value as interim rather than adopted vocabulary. Structural acceptance does not settle semantic adoption.
- Interim choice: render the exact supplied reason with unknown/unqualified state; assign no inferred meaning, qualification or command permission.
- Status: open; JT-02 in the website notes. This differs from the backend's JT-02 name for the encoded owner-locator defect (website JT-03).

## WEB-STG02-006 — controlled response-loss staging

- Class: **host or profile qualification deficit**, limited to test staging.
- Source: shared joint brief's lost-response probe; run 1's held-response and wrapper-stop timestamps.
- Observation: the application deadline elapsed before the wrapper was stopped. Identical-body reconciliation worked, but a wrapper-stop-only cause was not isolated.
- Interim choice: preserve the failed staging and distinguish timeout/lost-reply recovery from the strict requested variant. A fresh-state rerun must record its actual fault mechanism and timing rather than inherit a blanket pass.
- Status: run 1 remains limited (JT-04); run 2 is recorded separately in the joint notes. This requests no contract change.

## Clarification incorporated — unwitnessed A-23 examples

The operator's later 2026-10-19 field-map clarification identifies F01/F32/F03/F04 as shape examples without independent witnesses, and F05/F13 as witnessed. No new gap entry or contract reopening is requested: the independent intake already claimed structural checks only. The website renders stamps as supplied, never as a locally proven guarantee. Derived waiting/run fixtures use explicit `fixture:` references and unqualified stamps. The source recordings and sealed archive are unchanged.
