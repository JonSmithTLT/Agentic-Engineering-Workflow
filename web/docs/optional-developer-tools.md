# Optional developer tools — 2026-10-02

Worktree: `AEW-dashboard-graph`, branch `feat/aew-dashboard-work-graph`. Accepted core remains frozen separately at `7c120b4`; branch base is `969b0bd`, with the optional Work graph at `a4eef03`. This packet describes additional optional work for review, not a new core or integrated-system acceptance.

| Request | Result under API 0.1.2 |
| --- | --- |
| API developer panel | Implemented. Header toggle opens a keyboard-accessible drawer; Escape closes it. Last 200 completed requests are retained in memory, including path, start time, duration, HTTP status, sent/returned/represented ETags, validated revision/project, errors and exact Zod field paths. Clear affects the log only. |
| Copy as CLI | Implemented for Work, invocation and History records and typed links. Commands verified against current AEW CLI source: `aew work show ID`, `aew invoke show ID`, `aew history show ID`. URL-safe opaque IDs are single non-option shell arguments. Clipboard only, never execution; unavailable clipboard exposes selectable command text. |
| Jump to an ID | Implemented with Ctrl/Cmd+K and a header button. Native modal supports Escape, focus return, explicit entity type and validated opaque ID. Existing capability gates and centralized routes apply; no lookup/search request is introduced. |
| Ticket lifecycle timeline | Unavailable under this contract. Work exposes `updated_at`, not timestamped state transitions. Bounded recent activity cannot establish a complete unit lifecycle or review/worker duration. User reports this is now tracked as future work; no synthetic timeline is shown. |
| Historical lineage/link graph | Implemented in History detail. Explicit expansion follows supplied `depends_on`, `moved_to` and audit references through existing History detail reads, up to three levels; invocations/evidence are typed terminal links to Runs/Evidence. Unknown relations, tokens and commits remain reference-only. Limit: 24 cards, 80 edges; missing records remain visibly unavailable references. |
| Since you last looked | Implemented on Work and Runs lists. Browser comparison of bounded loaded-page snapshots; stores only project/scope, revision, time, IDs and state/status, up to 100 records per scope and 20 scopes. No global delta/event/count claim. Empty/malformed/blocked storage fails gracefully; project, filters, cursor, demo fixture and live scopes remain separate. |

AEW has no equivalent read-only evidence-detail CLI command. Evidence detail explains that rather than copying a nonexistent or mutating command. Related producer/provenance invocation links retain their own verified commands. User confirms the CLI gap is already actively tracked. No new tracking ID was supplied; these notes do not create duplicate tickets.

## Honesty and behavior

The request drawer is observational. A validated 200 with a changed revision but unchanged ETag is flagged as a **browser observation**, not backend health/integrity. A 304 carries the cached representation revision and cannot prove the server’s unseen live revision. It preserves payload and `generated_at`. No cookies, authorization headers or response bodies are retained. Logs are bounded and disappear on reload. JSON parse failures use a generic message rather than retaining a body excerpt.

Since-viewed comparisons use the previous visit’s saved page snapshot, while the latest successfully validated visible-page representation is remembered for the next visit. Arrivals are labeled “New to this loaded page.” Missing rows are not classified as deletions or completion. State changes use supplied strings without deriving workflow conclusions. Newer saved revisions are preserved if a projection goes backwards. “Clear saved comparisons” removes stored snapshots and pauses remembering for the current mount. Browser storage is deliberately expanded beyond the accepted core’s theme preference by this user-authorized optional feature; independent review should assess this added boundary.

Historical graph expansion is explicit and uses the centralized transport/runtime validation and query cache. It does not automatically crawl references or request unsupported capabilities. Archived data stays historical. A relation target may have a Work representation and no History record yet; the failed History lookup is labeled, and the existing Work/History lookup display remains available below the graph. Loaded graph references retain their response revisions and a graph freshness banner checks coherence against active project projections. Reset returns to the current root without implicitly crawling references. Geometry and graph-limit notices are frontend presentation, not AEW conclusions.

## Reported graph behavior

Fit width originally removed scrollable overflow, leaving the scroll-only drag handler no room to move. Free translation now handles fitted axes, with ordinary scrolling on overflowing axes; keyboard movement remains supported. Reset zoom and Fit width reset translation. Browser regression checks verify real pointer dragging after Fit width.

Direct probes initially returned 200 for `S-0001`, but the strict combined browser trace later caught intermittent 404 responses for Work detail during navigation/reload. No fixture or contract repair was needed: Epic, Story and Ticket responses and the bounded fallback already existed. Old-document queries are now canceled in a capture-phase `beforeunload` handler before the demo worker deactivates; visibility/revision handling resumes on back-cache restoration. The stricter rerun passed with only the deliberately missing History reference returning 404. Preview responses also use `Cache-Control: no-store` and demo registration uses `updateViaCache: none`. Current graph navigation plus reload passes for all three record types; reload the preview to consume current assets.

## Validation and handoff

Same immutable Linux/amd64 carrier: `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, Node 22.22.2/npm 10.9.7. No dependency additions or SPT image repair. Accepted contract SHA-256 remains `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`; package lock remains `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`.

Offline command from worktree root:

```sh
PATH="/tmp/aew-bin:$PATH" \
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/offline-gate.sh
```

PASS: absent modules, 395-package offline install with networking disabled, generated-type comparison, typecheck, lint, 85 tests across 11 files, production/mock-exclusion gate and separate demo build. Seven new meaningful tests cover trace/cache semantics, exact validation fields, bounded logs, network/304 errors, ETag observations, command safety, scoped storage/rollback/retention, malformed storage and bounded explicit lineage expansion. Evidence: `artifacts/tools-offline-final.log`, exported static builds in `artifacts/offline-gate/`.

Compiled browser command from `web/`:

```sh
DASHBOARD_PREVIEW_URL=http://127.0.0.1:4187 \
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4188 \
node scripts/browser-developer-tools.mjs
```

PASS: 11 focused browser check groups. Evidence: `output/playwright-developer-tools/browser-developer-tools.json` and drawer, exact-field, historical graph, page-comparison and phone screenshots. Matched Playwright 1.59.1/Chromium revision 1217; host Node only orchestrates browser checks. Normal production storage/validation probes use a synthetic same-origin API with service workers blocked; demo graph/navigation probes use accepted fixtures. The expected absent History reference returns 404; it is asserted separately from unexpected browser/CSP errors. This is implementer evidence, not independent review or live AEW integration. The four accepted FR-1/FR-2 browser regression checks also pass against this final demo/production build (`artifacts/tools-browser-review-fixes.log`). The existing D1 lane passed earlier in this turn; its normal-production adapter lane still used the accepted-core adapter on port 4175, so it is not relabeled as optional-build production verification.

Demo limitation: blocking all browser storage also blocks MSW initialization. Normal production has no mock initialization and passes the blocked-storage probe. This third-party demo-only requirement is not an SPT image failure or live frontend storage dependency. Existing bundle-size advisory remains a non-blocking frontend optimization candidate.

Review focus: central transport instrumentation preserving cache/errors, read-only command allowlist, opaque-ID/type selection, bounded explicit lineage reads, locally stored page snapshots, storage failure, accessibility/CSP and compiled production exclusion of mocks. Main-line acceptance of these optional changes remains pending. No Engine/history/control schema edits or ongoing AEW suite were invoked.

Preview: `http://localhost:4187/work?view=graph&fixture=F1`. Header has API panel and Jump to ID. History graph: `http://localhost:4187/history/T-0004?fixture=F3`.
