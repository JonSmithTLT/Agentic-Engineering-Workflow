# D1 frontend validation — 2026-10-02

Scope: API-driven Overview, bounded Work explorer and Work details. C0 0.1.2 is ACCEPTED at `322301d1200dce54d31a54348dd15ba7a71c9376`; canonical SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`. This stage leaves that artifact byte-identical.

## Offline gate: PASS

From the repository root:

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh
```

Networking disabled, absent node_modules, offline installation of 395 packages: generated types match, typecheck and lint pass, **51 tests in six files pass**, production/demo builds pass, production mock exclusion passes. Node 22.22.2, npm 10.9.7, Tailwind/adapter 4.2.4, Vite 8.0.10. Lock SHA-256 remains `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`. No dependencies were added. Builder/cache provenance remains in `builder-provenance.json`.

Local ignored evidence: `artifacts/d1-offline-gate.log`, `artifacts/d1-offline-driver.log`, and `artifacts/offline-gate/dist{,-demo}`. The offline driver copies sources to container-native storage before installation and does not invoke AEW tests.

Six D1 tests cover filter/cursor whitelisting, bounded hierarchy/cycle handling, explicit archived-state filtering, virtualized versus accessible page rows, capability-suppressed requests, and a shrinking refreshed page. An initial test raced filtered loading; the corrected probe waits for the server response. Refresh shrinking also has a clamp regression check.

## Compiled browser gate: PASS

From web/, with compiled demo served on 4173 and test-only production fixture adapter on 4175:

```bash
node scripts/projection-server.mjs
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-d1.mjs
```

**18 checks pass**; see `browser-d1-report.json`. Playwright 1.59.1, separately staged Chromium revision 1217 / 147.0.7727.15; browser orchestration uses host Node 24.21.0, separate from Node 22 build acceptance. Tests exercise deep-link reloads, keyboard navigation, themes, phone layouts, hostile content, refresh failures, unknown semantics, archive filtering, and capability suppression. Actual measured scroll height and row bounds establish virtualization under the proposed CSP. Keyboard End and the accessible all-loaded-rows option are exercised. Cursor navigation requests only bounded pages; large fixture details resolve arbitrary opaque IDs.

Normal compiled production reads same-origin API responses from the **test-only fixture adapter**, without MSW registration, demo controls, fixture bundles, remote resources or mutation requests. This is not live Engine integration or authentication/server acceptance. The adapter supplies the proposed CSP for browser checks; main-line server headers remain integration ownership. Intentional fixture HTTP 500 errors are recorded separately; unexpected browser errors are empty.

Screenshots are in `screenshots/d1/`. Ignored local raw evidence: `artifacts/d1-browser.log` and `output/playwright-d1/`.

## Limits and remaining gates

Tree relationships are limited to the loaded page; backend rollups are displayed unchanged. Lists use limit 100 and opaque cursor pagination. Default Work scope is backend active work plus recent 20 finished records; older finished work requires an explicit state filter. No frontend workflow conclusions or queue model were introduced.

Production main chunk is 521.78 kB (157.44 kB gzip), triggering Vite's 500 kB advisory. Route/content splitting is a non-blocking frontend optimization candidate; production fixture exclusion passes. Demo's separate fixture chunk is excluded from normal production.

D2–D4 await the user's specified Overview/Ticket visual review. Independent frontend review at core freeze and integrated-system acceptance remain outstanding. No Engine code changes or AEW Python suite execution occurred.
