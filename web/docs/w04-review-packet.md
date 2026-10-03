# W04 review packet

## Disposition and source

W04-01–03 is implemented as a demo-only Investigation preview 0.1.0 PROVISIONAL. Operator approval is factual and bound to plan1.0 in `web/docs/design/plans/w04-approval.json`. Independent frontend fixture acceptance is **PENDING**; the implementer checks below do not substitute for a reviewer performing the product task. Backend schema adoption and live integration remain separately pending. No Engine work records were created and no Engine suites were invoked locally.

Implementation starts at merged W03 `86d301b5dc848de095028470b6efcc3b515c420c`. The exact source freeze, preview digest, commands, screenshot hashes and measurements are in `web/docs/w04-evidence/result.json` and `SHA256SUMS`. Review the commit named there. Evidence commits do not change runtime code.

## Product boundaries

Demo Work and invocation details offer Compare invocations. Both source choices remain explicit; the chooser is a 50-row cursor table with exact supplied work filtering. Invocation entry seeds an identity and asks the operator to select its supplied source rather than choosing an ambiguous snapshot. Each side optionally selects a run. Structural comparison covers accepted invocation/run fields, separately supplied configuration, evidence and run-filtered packet associations. Partial/missing values remain Unavailable; Show differences makes no causal claim.

The packet inspector replaces comparison. Contents expose supplied, bounded excerpts and references, not an artifact retrieval interface. Selection & budget shows supplied policy/accounting/explanations. Receipts separate preparation, delivery acknowledgment, citation and evaluated benefit, including exact source/invocation/run/packet/snapshot bindings and provenance. Missing receipts never establish that an event did not occur. Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.

Packet/receipt schemas, binding functions, ReceiptCard, ContextReferences and PacketInspector are reusable domain components independent of comparison. No topic contract, grouping inference, semantic relationship inference, evolution mode, evidence lookup, replay, knowledge creation or backend adoption is introduced. Later canonical/knowledge/subject distinctions remain W04-Q07 in `web/docs/design/w04-backend-question-ledger.md`.

Readers bootstrap the accepted project and isolate each side by digest, dataset/case, project, source/snapshot, visibility, session generation and side ownership. Identity discovery is discarded before the bound payload read. Source/packet/receipt mismatches are rejected before caching. Refusal clears affected payloads and validators while ordinary refresh failures retain explicitly stale valid data. Fixed snapshots are manual-only after initial loading; current visible details use10-second polling. Concealed comparison sides and packet pages have no intervals. Allowlisted copy/reload presentation parameters do not extend accepted API queries.

Production excludes the Investigation and Journal preview modules, initialization, fixtures and endpoints. Accepted API0.1.2, generated accepted types, Journal preview0.1.0 and the dependency lock remain unchanged. Worker-backed fixtures and the reusable worker-free HTTP demo share projectors. The HTTP browser path blocks service workers explicitly.

## Required independent investigation

Start the compiled HTTP demo from `web/` using pinned Node22: `node --experimental-strip-types scripts/demo-server.mjs`. Its default URL is `http://127.0.0.1:4249`; DASHBOARD_PORT can select a free port. Use `/compare?fixture=F1`, with Investigation scenario story. The operator preview uses the same reusable server, not a separately generated review artifact.

Perform the following independently on desktop and at390px phone width. Use only product UI; do not inspect fixture source or developer/API/Contract panels to discover answers. No arbitrary completion-time target.

1. Choose source A and B explicitly. Identify the failed-removal source and corrected retry through their supplied summaries. Record invocation/source/snapshot IDs, work identity, capture timestamps and optional run choices. Expected story identities are SRC-Removal / CLANGD-INV-Removal / SNAP-Removal / CLANGD-R-A2-2 and SRC-Retry / CLANGD-INV-Retry / SNAP-Retry / CLANGD-R-A2-4; these hints do not substitute for finding the records through the UI.
2. Establish the recorded removal failure/reversion and the reported corrected build outcome. Compare the supplied starting configuration without asserting which difference caused success. Verify source choices and run selections remain explicit.
3. Open PKT-Removal. Establish its supplied current constraints, mistaken hypothesis J-02, preparation receipt and absent delivery receipt. Establish that the absence is projection uncertainty.
4. Return to comparison and open PKT-Retry. Establish refreshed compilation evidence CLANGD-E875 and discovery J-04, excerpt scope/truncation, selection explanations/accounting, preparation time, receipt stages and canonical CLANGD-D42. Verify J-05 is absent from the retry packet; this earlier preparation predates its16:40UTC publication.
5. Inspect delivery acknowledgment and output citation separately. Establish the absence of benefit evaluation and avoid attention/influence claims. Record actual receipt IDs, bindings, timestamps and provenance.
6. Return to comparison. Change B explicitly to SRC-Later and open PKT-Later. Follow its J-05 reference to Journal through the UI and return. Establish the published lesson's inclusion and delivery acknowledgment, with no output citation or benefit evaluation. Explain why neither inclusion nor acknowledgment proves benefit.
7. On both layouts exercise Change, optional run selection, Swap, tabs, Show differences, Back to comparison and Copy dashboard link/reload. Confirm the UI preserves source choices and useful focus/scroll position. Record failures to complete any step, not just code observations.

Record performed steps, observed IDs, outcomes, starting-context differences, receipts, canonical references and usability failures in a new `web/docs/w04-review-main-line.md`, using `web/docs/w04-independent-task-review-template.md`. Independent disposition gates frontend fixture acceptance only.

## Validation and limitations

Frozen evidence records the pinned Node22.22.2/npm10.9.7 offline gate, strict artifact checks, typecheck/lint,136 tests in16files, both builds and production exclusion. Browser regressions cover W01–W03 and the worker-free HTTP path. W04 exercises desktop/phone tasks through both adapters, paging and copied cursors, partial/missing/unknown/malformed/denied/historical states, stale retained data, hidden polling,304s, obsolete responses, source/receipt bindings, CSP-safe hostile excerpts, keyboard tabs, focus and swap. CI runs both W04 adapters with CHROMIUM_PATH support.

Measurements use frozen W03 and W04 large fixtures, one warmup and two warm samples per surface. Both mount50rows before/after paging with four initial API reads. Different datasets/workflows make this a boundedness check, not a speed comparison or SLA. Existing chunk-size advisories remain. Phone checks emulate a390px viewport in desktop Chromium;200% uses CSS zoom emulation, not a browser-toolbar zoom claim. The premium static audit has zero findings; the unavailable official design-lint CLI is not claimed as executed.

During verification, the HTTP server's Journal-only refresh fault initially also intercepted Investigation reads; it is now restricted to Journal. Harness assertions were corrected to target the visible stale status and the existing global historical-link guard. A W01 reload attempt exposed two404s during a service-worker navigation race; its trace remains in ignored local output and the fresh-port rerun passed all16groups without suppression or timeout increases. Failed attempts are not counted as passing evidence.

Backend owners must settle snapshots, authorization, immutable packet/source identities, accounting and receipt guarantees independently. See the backend question ledger and approved plan; do not adopt these fixture routes or fields implicitly.
