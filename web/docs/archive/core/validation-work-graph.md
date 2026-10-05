# Optional Work graph validation — 2026-10-02

Status: implementer validation PASS; optional visual/main-line review pending. Accepted core remains frozen separately at `7c120b4`; this worktree branches from `969b0bd` on `feat/aew-dashboard-work-graph`. Live integration is NOT RUN. No Engine, storage, contract, fixture or dependency changes.

## Offline consumer gate

Command from worktree root:

```sh
PATH="/tmp/aew-bin:$PATH" \
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/offline-gate.sh
```

Linux/amd64 immutable carrier, Node 22.22.2/npm 10.9.7, networking disabled, absent `node_modules`, native container storage. PASS: offline install of 395 packages; generation/compare of accepted OpenAPI types; typecheck; lint; 78 component/unit/contract/refresh tests across ten files (73 core plus five graph tests); production build and mock-exclusion scan; separate demo build. Evidence: `artifacts/graph-offline-final.log` and `artifacts/offline-gate/{dist,dist-demo}`. Normal production excludes fixtures/MSW initialization; the optional component is present in both builds. The existing bundle-size advisory remains an optimization candidate.

Unchanged canonical API 0.1.2 SHA-256: `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`.
Unchanged package lock SHA-256: `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`.
Cache identities and carrier provenance remain in `builder-provenance.json`. No new full-carrier validation is claimed.

## Compiled browser and visual checks

Serve the exported demo with Vite preview (including the proposed CSP):

```sh
node node_modules/vite/bin/vite.js preview --mode demo \
  --outDir artifacts/offline-gate/dist-demo --host 0.0.0.0 --port 4187 --strictPort
DASHBOARD_PREVIEW_URL=http://127.0.0.1:4187 node scripts/browser-work-graph.mjs
```

PASS: seven focused browser check groups using pinned Playwright 1.59.1 and separately staged Chromium revision 1217. Host Node 24 orchestrates the browser only; build acceptance uses carrier Node 22. Evidence: `output/playwright-work-graph/browser-work-graph.json` and light/dark/phone/large-page screenshots beside it.

Coverage: actual CSSOM-positioned card geometry/local SVG paths under CSP; selection/detail navigation and reload; branch collapse/expansion; URL-persisted focus and reload; zoom; both themes; phone overflow confined to its panel; 100-record pages plus an explicitly unloaded parent; opaque cursor next-page loading; keyboard and real pointer drag pan; archived-record warning; unknown backend state; no browser/CSP errors, remote requests, mutation requests or new graph API. Source-level tests also exercise cyclic parent references and absent focus. This is compiled demo validation with accepted synthetic projections, not live Engine or independent review.

The initial browser probe assumed five F1 records; inspecting F1 confirmed six and five edges. The corrected probe passed. No frontend bug was hidden by that test correction.

Visual inspection of light and phone screenshots confirmed readable desktop relationships, selected-edge emphasis, an adjacent inspector on desktop and stacked inspector on phones. Fit-width produces an overview on phones; zoom and panel pan provide inspection, with Table/Tree retained as linear alternatives.

## Integration/review boundary

Review this optional diff separately from the frozen core. The graph rearranges only supplied parent relationships on the loaded page. It preserves backend counts and conclusions, labels unloaded parent references, gates through the existing Work capability and uses existing detail links. It does not fetch all work/history or invent graph-wide counts, dependency meaning, lineage conclusions or workflow state. Whole-project graph traversal and relation overlays need main-line projections and renewed contract review.

No integrated-system acceptance or independent optional-feature acceptance is asserted. The accepted core archive remains unchanged in the core worktree.
