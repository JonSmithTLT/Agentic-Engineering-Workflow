# W06 independent review packet

Frontend fixture acceptance is **CHANGES REQUESTED; F1/F2 re-review pending**. The independent report is preserved in `web/docs/w06-review-main-line.md`; corrections and the harmless-read assessment are recorded in `web/docs/w06-review-corrections.md`. W05's merged acceptance is preserved. Backend/live adoption remains blocked on accepted T3 event/outbox design and Engine-owned projections; G7/F7 requires an explicit adapter. No Engine work records were created.

Review the immutable runtime commit recorded in `web/docs/w06-evidence/result.json`. The subsequent evidence commit changes documentation only. The approved revision 1.1 plan is `web/docs/design/plans/w06-execution-investigation.md`; its factual operator approval and digest are recorded in `w06-operator-approval.json`.

## Reproduce the preview and evidence

From `web/`, run pinned Node 22 with `node --experimental-strip-types scripts/demo-server.mjs` after building the demo. `DASHBOARD_PORT` selects an available port. The HTTP demo serves all preview projectors and needs no service worker. The worker-backed adapter remains supported and is tested separately.

The pinned builder is in Ubuntu WSL's native Docker, accessed through `/snap/bin/docker`, separately from Docker Desktop. Its identity is `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`. From the repository root, `PATH=/snap/bin:$PATH SPT_FRONTEND_IMAGE=<builder> bash web/scripts/offline-gate.sh` builds with network disabled. No networked npm install is needed when that image is staged.

Freeze the merged W05 baseline with `bash web/scripts/freeze-committed-build.sh da46807d4fb35ec742f042425c347cd480ba8f65`. Then run `bash web/scripts/freeze-w06-evidence.sh <full-runtime-commit>` with `SPT_FRONTEND_IMAGE`, absolute `PINNED_NODE22`, `CHROMIUM_PATH`, required Chromium runtime libraries and `W06_BASELINE_WEB` pointing to the frozen baseline frontend. Both measurement frontends need the staged dependencies available as `node_modules`. The procedure builds and tests a clean detached source checkout, records full production/demo manifests and verifies every build file and source tree afterward. Never substitute a working-tree build or attribute its screenshots to a later commit.

The HTTP refresh-error scenario retains its failure state within the server process. Restart the demo server before repeating its initial successful load and subsequent failed refresh.

## Independent investigation

Start at `/execution?fixture=F1&execution_trace=TRACE-Clangd`. Complete the following separately on desktop and a 390px phone layout, using only product UI. Developer tools, fixture source and Contract Playground cannot substitute for the task. There is no completion-time target.

1. Establish the selected fixed trace, snapshot, project and capture identity. Inspect supplied coverage, recording gap and retention limitation. Distinguish trace-local ordinal order from source timestamps; an ordinal discontinuity alone does not prove a missing event. Captured invocation status is not authoritative status at an event.
2. Follow the recorded removal failure, compilation discovery, preparation, delivery acknowledgment, citation and retry outcome. Record event, execution, invocation and run IDs. Inspect the captured accepted invocation/run data without deriving causation or reconstructed historical state.
3. From the failure event, inspect the supplied CLANGD-E871 association through W05. Explicitly select its fixed source and artifact, identify range/digest and canonical references, then return. Repeat for the discovery's CLANGD-E875 association. Record restored selection, scroll and originating-link focus.
4. Inspect PKT-Retry from its supplied event locator. Record owning source/snapshot/invocation/run identities, supplied contents and separate receipt stages. Establish that J-05 was published later and is absent from the earlier packet. Missing benefit evaluation does not establish that benefit did or did not occur. Return to the recorder and verify restored position and focus.
5. Inspect Fanout in both hierarchy and table modes. Expand explicitly and identify relation kind and source. Explain the distinction among registered delegation, process spawn, harness helper, provider suboperation and correlation. Correlation is not parentage, custody or causation. Identify the unregistered execution and terminal process/provider references. Use cycles and partial cases to inspect bounded expansion and coverage limits.
6. Inspect the selected execution's Controls and Validation receipts. Record Engine vocabulary, environment/source/snapshot binding, supplied age/currentness and provisional extensions. Distinguish configured, available, authorized, active and successfully tested. Inspect missing, stale and mismatched receipts. Configured controls are not validated guarantees; process ownership is not a stronger process-containment claim.
7. Inspect budget observations and the fanout scenario. Record configured quantity/units, observation scope, active/unattributed counts, depth, completeness and separately reported enforcement. Observed fanout does not establish an enforcement result. Loaded page counts are not global counts; this is not a G7/F7 cost ledger or DispatchDecision.
8. Exercise lanes/table parity, pages and an off-page selection, phone Results/Detail switching, explicit trace selection, keyboard tab navigation and close-focus restoration. Copy/reload a selected event or execution. Check both themes, long content, narrow/zoomed layout and unavailable/denied/historical cases. Concealed views must make no reads; unavailable mappings must not resolve by similar IDs.

Fixture task locators include `TRACE-Clangd`, `TRACE-SNAP-1`, `EV-03` through `EV-09`, `EX-Removal`, `EX-Discovery`, `EX-Retry`, `EX-Helper`, `REF-EXEC-Failure`, `REF-EXEC-Discovery`, `LOC-RetryPacket`, `SRC-Retry`, `SNAP-Retry` and `PKT-Retry`. These orient the review; they do not substitute for recording observations through the UI.

For each layout, record starting URL, runtime commit/digest, trace/event/execution/invocation/run/source/snapshot/packet/Evidence/reference IDs, steps, outcomes, coverage limits, relationship/source attribution, budget/enforcement distinctions, control/receipt distinctions, canonical references, navigation restoration and usability failures. Record factual reviewer/date, task PASS/FAIL and an explicit frontend fixture disposition in a review artifact.

## Evidence and limits

Implementer automation is supporting evidence, not independent acceptance. `web/docs/w06-evidence/` contains committed-source provenance, complete build manifests, browser results, screenshots and measurements. Zoom automation uses a halved CSS viewport to exercise the layout available at 200% browser zoom; it is not a native browser-toolbar zoom operation. The reviewer should also exercise their browser's zoom control.

Measurements compare bounded W05 artifact pages with W06 event pages, with different fixture populations and workflows. They are observations, not an improvement claim or timing SLA. Source/tree and build identities are checked before and after verification.

The final freeze targets runtime commit `55c48ec5054a4b6830722978b36bfc4e0d55ff60` and Execution digest `481f5f0612986ad70101663c9cf4921cdd5cdd7d665d84f058660699afb27375`. The pinned offline gate passed 164 tests in 19 files; W01–W05 regressions, 22 W06 browser groups and the strict premium audit passed. Production and demo build manifests remained unchanged afterward. This records implementer verification, not independent acceptance.

| Workflow | Fixture population | Displayed rows before/after paging | DOM nodes before/after | Initial API reads / bytes | Two warm render-ready samples |
|---|---:|---|---|---|---|
| Frozen W05 artifact page | 126 | 50 / 50 | 459 / 459 | 6 / 30,700 | 1439 / 1433 ms |
| W06 recorded event page | 189 | 50 / 50 | 671 / 671 | 6 / 56,286 | 932 / 935 ms |

Each workflow also has a recorded warmup. The cache test retires prior page payloads and validators, retains only the active page, and clears owned queries on unmount. Fanout separately limits displayed nodes and supplied edges. The zoom screenshots model 720px desktop and 195px phone CSS viewports; normal phone investigation screenshots use 390px.

Execution events/ordinals/lanes/relationships are presentation-fixture semantics, not the future T3 outbox contract. Visibility is project-only, with opaque binding metadata conferring no authorization. Budget observations do not define cost-ledger fields, remaining-budget arithmetic, enforcement or dispatch decisions. Canonical decisions remain references to authoritative records; preparation, delivery acknowledgment, citation and evaluated benefit remain distinct.

Pending adoption decisions are in `web/docs/design/w06-backend-question-ledger.md`. The page-density review remains deferred and starts with Work; W06 does not redesign that page.

Overnight review corrections are recorded in `web/docs/w06-overnight-review.md`: failed-child retry, execution-table off-page status/focus and explicit Controls chooser failure/recovery. The W01 reload regression now waits for represented record content before and after reload rather than treating a breadcrumb as readiness. No errors are suppressed. The current freeze supersedes the original evidence at `5aa55df`, which remains available in Git history.
