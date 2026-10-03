# Core frontend candidate validation — 2026-10-02

Status: implementation and focused frontend checks PASS; independent main-line frontend review PENDING; integrated-system acceptance NOT RUN. The user approved Overview/Ticket visuals on 2026-10-02 after the ticket-ID display correction. This is a review candidate, not a claim that passing mocks completes core freeze.

## Accepted contract and immutable builder

Contract 0.1.2 was accepted by Claude at `322301d1200dce54d31a54348dd15ba7a71c9376`. SHA-256 remains `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`. This expansion changes neither canonical YAML, generated API types, Zod wire schemas nor F0–F11 fixture bytes. C0 approval records remain unchanged. Known semantic values come from the accepted contract/review; unregistered values warn with raw strings. Backend authority text is displayed as text, never interpreted as permission.

Linux/amd64 builder: `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`. Node 22.22.2, npm 10.9.7, Vite 8.0.10, Tailwind/adapter 4.2.4. AEW lock SHA-256 `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`; no added/updated dependencies. Full package/cache and separate browser provenance is in `builder-provenance.json`. The separate SPT prerequisite remains outside AEW history.

## Offline frontend gate: PASS

From the repository root:

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh
```

Absent modules, networking disabled, install 395 cached packages: generated types match; typecheck and lint pass; **61 tests in seven files pass**; production/demo builds and production mock exclusion pass. New tests cover nested invocations, Evidence filtering/safety/bindings, grouped Knowledge/provenance, bounded History/annotations, invalid-filter suppression, synthetic AVAILABLE integrity and backend Attention/unsupported Queue. Existing contract, transport, conditional-request, hidden-tab, freshness and Work virtualization lanes also pass. Logs: `artifacts/core-offline-gate.log` and `artifacts/core-offline-driver.log` (local ignored artifacts).

Final exports replace previous generated output directories. Inspection found that merging successive build exports could retain obsolete hashed assets; the export step now clears only its owned generated dist directories before copying. Build directories in the handoff contain exactly the fresh gate output.

## Compiled browser checks: PASS

From web/, demo preview on 4173 and the test-only normal-production fixture adapter on 4175:

```bash
node scripts/projection-server.mjs
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-d1.mjs
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-core.mjs
```

**18 D1 regression checks + 12 core checks pass**. Reports: `browser-core-d1-report.json`, `browser-core-report.json`. Chromium revision 1217 / 147.0.7727.15 matched to Playwright 1.59.1. Browser orchestration uses host Node 24.21.0 with separately staged OS libraries; it is distinct from the immutable Node 22 build gate.

Checks cover all core routes, opaque deep-link reloads, backend filters, keyboard skip navigation, both themes, phone layouts, active-list windowing/cursor pagination, 50,000-record bounded History pagination and generated detail reload, annotation bounds, refresh errors, unknown semantics, hostile Markdown/code/JSON and capability suppression. Production reads the same-origin fixture adapter without MSW, fixtures, demo controls, remote subresources or mutation requests. Compiled styles, native disclosure panels and virtualization are exercised under the proposed CSP. Unexpected page/console/CSP errors and remote/write requests are empty; intentional D1 HTTP 500 fixture errors are reported separately.

An original D1 exact accessible-name probe still expected title-only Overview links. It was updated to require the user-requested `T-0001` plus title; the complete lane then passed. A new test exposed demo-only dispatch of `/history/integrity` through annotation pagination; that exclusion is corrected and retested. F7 generated archive IDs also support mock detail reloads now.

Synthetic integrity availability is deliberately injected in the browser/unit tests from F4's provisional response. Frozen fixtures retain integrity UNSUPPORTED. This proves renderer behavior if advertised, not current backend audit functionality. Queue is unsupported and has no accepted wire endpoint/model, even if an unexpected AVAILABLE state appears.

Current screenshots: `screenshots/core/`. Raw local evidence: `output/playwright-core/`, `output/playwright-d1/`, `artifacts/core-browser.log`, `artifacts/core-d1-regression.log`.

## Boundaries and dispositions

- All reads remain same-origin GET with cookie-compatible credentials, validation and conditional ETags; no mutation surface, Engine/storage coupling or extra persistence was introduced. Appearance is the only persisted setting. Browser read-only checks complement source inspection; server authentication and headers are not accepted by this gate.
- Overview remains one coherent composite. Lists poll at 5 seconds and details at 10; Overview is 2 seconds. Historical Knowledge/History/integrity refresh manually or on focus; hidden intervals stop and visibility refetches active queries. A 304 preserves generation/revision/payload while updating last check. Invalid refreshes retain visibly stale valid content; initial failures show load errors. Existing 30-second visible mixed-revision tests pass without inferring integrity failure.
- Work hierarchy is loaded-page scope, backend rollups untouched; lists/annotations use bounded opaque cursors. History shows manifest sequence, trust, hash, lineage and annotation lists; archived evidence never becomes current. Untyped History target IDs offer explicit Work/History lookups instead of inventing target types. Entity/navigation links discard foreign collection cursors.
- New detail spacing and wrapping were corrected after screenshot inspection. Production main chunk is 545.20 kB (161.31 kB gzip); Vite's 500 kB advisory remains a non-blocking route/content-splitting improvement. Demo fixtures stay out of normal production.
- Knowledge states, Attention severity and Integrity status have no registered vocabulary in this accepted artifact; raw warning rendering is intentional. A backend-owned registry/contract amendment can establish recognized values during integration. No client meaning was invented to remove those warnings.
- SPT-UI-009 retains the demonstrated offline one-off-tool metadata issue and verified exact-tarball workaround. Other resolved/open feedback is retained in `spt-toolchain-feedback.md`; non-blocking SPT improvements do not delay review.

No AEW engine source edits or Python suite runs. Graph/global search/metrics/comparison/standalone timeline remain outside core. Independent frontend review, finding disposition and live integration remain separate required gates; see `frontend-core-review-packet.md` and `integration-checklist.md`.
