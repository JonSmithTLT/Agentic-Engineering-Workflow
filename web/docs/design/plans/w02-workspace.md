# W02 — Shared Investigation Workspace

Revision: 1.1 · Approved: 2026-10-03 · Approval: operator “got it then implement the plan”, following the two accepted tightenings.

## Outcome and boundaries

Deliver W02-01–04 as one independently reviewable increment. Work and Runs are full results/detail workspace pilots. Other core views receive shared inspectors without rebuilding collection browsers. Use accepted API 0.1.2 only; preserve canonical artifact/digest/generated types and dependency lock. No new packages, explanation preview contract, historical snapshot interface, Engine changes/tests, GitHub push, or integrated-system acceptance.

Implement in isolated `feat/aew-dashboard-w02`, based on accepted W01 docs commit ab6ab9814bee2f270ef61f69246aa19aca2431a9. Preserve other checkouts and running Engine work. Main-line independent review gates frontend acceptance; F20 owns authentication/live projections/integration.

## W02-01 — Workspace

Reusable results/detail/optional inspector panes. Reuse standalone record renderers. Collection URLs gain presentation-only `selected`; legacy detail paths remain. Keep results mounted across panel changes, retaining scroll, tree expansion, graph pan/zoom. Filters/pagination retain explicit out-of-page selection; never silently substitute a record. Selection/open/close changes use browser history. No neighboring-detail prefetch.

At >=1440px use three panes; 1024–1439px results/detail plus modal inspector; below1024px Results/Detail navigation plus modal sheet. Concealed detail intervals stop and immediately revalidate on reveal. Inspector focus starts at heading; Escape closes topmost overlay, returns to trigger or workspace heading. Modals trap focus/inert underlying content. W01 generation remount retires detail/inspector/graph state and late responses.

## W02-02 — Source and Why

Visually separate SOURCE (supplied project, contract, response revision, generated time; roots/hashes/sequence only where supplied) from BROWSER (last checked and browser refresh state). Browser freshness is not provenance or backend health. Generation time is not modification time.

Why/Relations tabs inspect exact raw status field. Work state/integration/attention; invocation and harness status; evidence result/currentness/disposition; Knowledge state; Attention severity; Overview health; History state/trust; integrity and capability state. Record reasons explicitly lack status binding unless the accepted shape provides one. Keep blocked_by, findings, deviations and capability/health reasons in named sections; never reassign neighboring reasons/references. Null/empty reasons and unknown semantic strings stay explicit, raw reason codes are opaque. Why opens without requests and updates from validated projections.

HTTP failure classifications distinguish initial401/403,404,malformed,network failures. 404 means Not found, never deletion. Access refusal hides/evicts affected data and validator; ordinary failures retain marked last-known-good. No invented permission reason or automatic cookie-change detection.

## W02-03 — Provenance

Explicit adapters only: Work parent/children/related; Invocation work/evidence; Evidence subject/provenance/producer invocation; Knowledge provenance; History links and typed annotation references. Edges retain source entity, exact source field/key, projection metadata. Generic related/provenance fields confer no causal/supporting meaning. Unknown types, tokens, commits and harness IDs stay terminal without accepted interfaces.

Expand explicitly one entity at a time through W01 context/transport. Limits:3levels,24nodes,80edges. Failures retained for retry; retired session/root cancels expansion. Accessible locally paged100-row relation list shares model; accepted History annotation paging stays available. Show locally known omissions/backend truncation, overall completeness unknown. No relation is not proof of absence. Preserve selection and pan after fit; graph/list toggles preserve exploration. Highlight only loaded connectivity, labeled browser calculation. Archived records never current evidence; current destinations of historical links are not historical snapshots.

## W02-04 — Navigation

Central allowlisted dashboard links for anchors, Jump, workspace and graph. URL state: selected,inspector=why|relations,allowlisted field; retain existing Work view/focus and supported filters/cursors/demo identities. Presentation params never enter API or query identity. Copy absolute same-origin link excludes payloads, credentials, authorization generation and cached revisions. Clipboard failure yields selectable URL. Reload restores URL-described root/selection/inspector, not expanded graph/pan.

Locally malformed identifiers under accepted0.1.2 syntax or unsupported presentation values show message/no invalid request. Syntactically valid opaque IDs resolve through the selected accepted backend interface regardless of namespace recognition and may return Not found. Historical revision/snapshot params explicitly unsupported and never silently load current data. Keep safe external navigation and read-only CLI copy; never execute commands.

## Evidence and gates

Ticket-order reviewable checkpoints; running Work and realistic Invocation previews after02 before provenance expansion. Composed tests cover session/late-response isolation, filters/paging/history, focus/scroll, visible polling, cache identity, exact reason/edge sources, null/unknown/error/refusal states, graph limits/cycles, historical honesty and safe copied URLs. Compiled browser under CSP: themes,desktop/phone,keyboard,modal Escape/focus,graph fit/pan/reload,hostile content. Keep W01 normal/manual refresh tests; ordinal replay is harness-only.

Offline immutable Node22 carrier, empty modules/network disabled: install, artifacts,typecheck,lint,tests,production/demo builds, production exclusion. MeasureF6/F7 against frozenW01 baseline, investigate regressions without arbitrary targets. Individually record expected failures; no blanket console/CSP suppression. Retain resultJSON/logs/screenshots/failure traces, source/contract/lock/cache/image/browser identities, updated SPT feedback and backend dependencies. Freeze review packet; frontend tests are implementer evidence, independent review and live acceptance separate.
