# Independent frontend core review packet

Prepared 2026-10-02. Historical frozen packet: main-line review returned **AMEND (minor)** in `frontend-core-review-main-line.md`. Current fixing commit and retests are in `frontend-core-review-fix-response.md`; fixing-diff verification remains pending. The original target description/evidence below is retained. Do not declare core freeze accepted on this packet alone.

## Frozen target

- Implementation commit: **`e632cc83135ed98f70804df166d1c88f37a0b674`**, branch `feat/aew-dashboard-readonly`, isolated `AEW-dashboard` worktree.
- Original base: `c380aea781736541c3a5f30a5ed4f8bc36227a7f`. Ownership diff: only `web/` and `docs/design/dashboard-api-v1-provisional.yaml`.
- Accepted C0 target: `322301d1200dce54d31a54348dd15ba7a71c9376`; contract 0.1.2, SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`. `c0-approval.json` records Claude's actual ACCEPT. Contract/schema/types/fixture bytes are unchanged in this expansion.
- Original AEW checkout and running tests were not modified or invoked. No Engine semantics are implemented here.

Use a disposable review checkout of the frozen commit. Record target/base and commands rather than treating this packet's claims as evidence. Documentation-only handoff commits after this target do not alter runtime code; verify the diff before using a newer target.

## Resulting behavior

Overview is the coherent backend composite. Work offers bounded filters, loaded-page hierarchy, virtualization, opaque deep links and explicit ticket IDs. Runs displays invocations including those with no harness run, then nested harness records. Evidence exposes claims/body, backend result/currentness/disposition, bindings and producer provenance. Knowledge groups loaded-page decisions/facts/assumptions with safe detail presentation. History displays bounded manifest entries, trust labels/content hashes, lineage and paged annotations; integrity is capability-gated. Attention shows backend decisions/blockers/findings/anomalies with reasons and subject links. Queue has no wire model and explains unavailability without requests or actions.

Shared `ProjectionViews.tsx` owns bounded collection/detail states and pagination. Transport/validation/capabilities remain centralized. Normal production consumes actual same-origin reads; only demo initializes MSW/fixtures. Foreign collection cursors are not propagated through entity/navigation links. Unknown or unregistered semantic strings warn with raw values. History target references have explicit Work/History lookups because the accepted wire carries no target type; absence from one projection is a load error, not a workflow conclusion.

## Reproducible evidence

`validation-core.md` records 61 offline tests in seven files, typecheck/lint/generated-type consistency and both builds, using the immutable SPT carrier with networking disabled and absent modules. Browser reports contain 18 D1 regression checks and 12 core checks on compiled UI under proposed CSP. Inspect the scripts and rerun relevant lanes; no historical green result or fixture-backed adapter establishes live Engine integration.

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh
# From web/, after starting compiled demo on 4173 and test adapter on 4175:
node scripts/projection-server.mjs
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-d1.mjs
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-core.mjs
```

Builder/package/cache/browser identities: `builder-provenance.json`; SPT fix is separate at `ae65ad0408536140a96335e8e76a6245a33ace4a`. Browser OS libraries and host Node orchestration are separate prerequisites. The test adapter is a fixture harness, not main-line server/authentication/security implementation.

## Review focus

1. Verify canonical hash/acceptance pins, generated types and Zod/fixture conformance; ensure unknown capability names remain valid and unsupported projections suppress reads.
2. Probe public sequences: good data → 304 → malformed/failed refresh; hidden → visible; coherent → mixed revisions → convergence. Check payload/generation/revision preservation and the 30-second visible-only warning, without invented health/integrity outcomes.
3. Probe filtering/cursor changes, deep-link reloads and pagination bounds, including older finished Work, 50k History and annotation paging. Inspect loaded-page tree honesty and virtualized/accessibility views.
4. Review code/Markdown/JSON safety, explicit external navigation, local assets, proposed CSP, keyboard focus and phone overflow. Use hostile and negative-control data, not only happy fixture screenshots.
5. Verify read-only boundaries, no `.aew`/filesystem/Engine coupling, no credential persistence, no inferred assurance/gates/currentness/custody, and no fixture/MSW production leakage. Confirm only consumed dependencies.
6. Assess readability of source/data/error states and inspect actual compiled UI. Synthetic AVAILABLE integrity is explicitly a renderer test; queue cannot display nonexistent state.

## Known non-blocking limits and self-inspection dispositions

These are implementer observations, not independent findings:

- Corrected: demo integrity dispatch through annotation paging, new-detail panel spacing, untyped History lookup labeling, stale hashed assets accumulating in exported builds, and an old exact-name browser probe after the user requested ticket IDs. Retests pass.
- Open frontend optimization: main bundle 545.20 kB / 161.31 kB gzip exceeds the Vite advisory threshold. No mock leakage; route/content splitting may be done separately if review finds a material performance issue.
- Backend integration: Knowledge states, Attention severity and Integrity status have no registered vocabulary in this artifact. Raw warnings are intentional pending backend-owned registry/contract review. No semantic mapping was invented.
- Queue remains unavailable pending a reviewed projection. Integrity remains UNSUPPORTED in the frozen fixtures; runtime AVAILABLE rendering was tested with a explicitly synthetic contract-shaped response.
- SPT non-blockers remain ticket-ready in `spt-toolchain-feedback.md`, including SPT-UI-009's exact cached-tarball formatter workaround. No further SPT repair is needed for this build.
- Graph/search/metrics/comparison/standalone timeline remain optional after core freeze.

## Reviewer return and gate

Record ACCEPT / AMEND with reviewer identity/date, frozen implementation commit, commands/evidence, severity and finding IDs, then any required retest. Write the return alongside this packet (for example `frontend-core-review-main-line.md`). The frontend will retain findings and disposition evidence before core freeze. Real authentication/bootstrap, headers/Host/Origin validation, caching, packaging and live-state browser checks remain main/integration ownership; see `integration-checklist.md`.

Static build/review materials are exported under `artifacts/core-handoff/` and archived as `artifacts/aew-dashboard-core-e632cc8.tar.gz`, with source-commit and file-checksum manifests. Serve only its `static/` directory; review fixtures/docs are outside that served directory. The archive does not assert main-line acceptance.
