# AEW read-only workbench

D0 foundation on an isolated branch from AEW `main`. The canonical API proposal is `../docs/design/dashboard-api-v1-provisional.yaml`. C0 is **pending**. Domain pages D1–D4 and integrated-system acceptance are not claimed.

The supplied v0.2 documents are preserved under `docs/`, with their outdated v0.1 reference and F0–F10 typo corrected. The user's approved implementation plan governs where those documents differ, including cookie-compatible requests, four-state capabilities, generated OpenAPI types, a separate immutable SPT prerequisite, and the 30-second mixed-revision warning.

## Commands

Use the validated SPT image ID in `docs/builder-provenance.json`. Do not substitute a floating image tag for acceptance.

```bash
export SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407
bash scripts/offline-gate.sh
```

The gate copies only frontend/contract sources into an ephemeral container, verifies that `node_modules` is absent, installs offline with networking disabled, regenerates types and checks for drift, then runs typecheck, lint, tests, production and demo builds. It never invokes AEW's Python suite. Artifacts are in `artifacts/offline-gate/` and logs in `artifacts/`.

After installing from that cache, development commands are:

```bash
npm run dev:demo           # provisional previews, F1 by default
npm run build:demo
npm run preview:demo       # compiled demo with proposed CSP
npm run build             # generic production shell; mocks excluded
npm run preview           # compiled production with proposed CSP
```

Select fixture worlds with `?fixture=F0` through `F11`. F10 supports `fault=404`, `fault=offline`, or `fault=malformed`; its default is a server failure. Mock previews are deliberately limited to Overview and work detail pending C0. Other routes render the generic pending view.

Browser checks: start both compiled preview servers, then run `DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4174 node scripts/browser-d0.mjs` from `web/` (demo defaults to port 4173). Screenshots and the check report are under `output/playwright/`.

The `src/api/mock` subtree owns all provisional preview assumptions. `types.ts` is generated; `schema.ts` validates wire input at runtime. Tests check fixtures against both the canonical contract and Zod. Semantic strings are open for future values, which render raw warnings. Absent or non-AVAILABLE capabilities suppress queries.

## Separate browser artifact

```bash
bash scripts/stage-browsers.sh  # connected staging, not the offline gate
```

This downloads Chromium matched to pinned Playwright 1.59.1 and records the browser revision manifest and checksums under `artifacts/playwright`. Runtime OS libraries are a separate environment prerequisite. Browser staging does not change or enlarge the carrier. Browser checks should use the staged revision, not an unrelated global browser installation.

## Boundaries and handoff

See `docs/c0-review-packet.md`, `docs/spt-toolchain-feedback.md`, and `docs/validation-d0.md`. No mutation APIs, secret persistence, `.aew` parsing, or frontend decisions about workflow legality are present. Local storage contains appearance preference only. Authentication/bootstrap, host/origin checks, HTTP security headers in the actual server, projection caching, Python packaging, and live-state integration remain main-line work.
