# Frontend core review: FR-1 / FR-2 response

Prepared 2026-10-02. **Both findings implemented and retested; main-line fixing-diff verification is pending.** This response records neither reviewer ACCEPT nor integrated-system acceptance.

- Frozen reviewed implementation: `e632cc83135ed98f70804df166d1c88f37a0b674`.
- Fixing commit: **`7c120b4c39a059508e3b095a9bfd5498c1d7be09`**, branch `feat/aew-dashboard-readonly`, isolated `AEW-dashboard` worktree.
- Actual return: `frontend-core-review-main-line.md`, Claude, 2026-10-02, AMEND (minor). That was static review of a frozen copy with contract verification. Execution results below are frontend implementer evidence, not independently re-observed reviewer results.
- Accepted API 0.1.2, SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`, unchanged. Canonical YAML, generated types and runtime schemas are unchanged. F3 now exercises all seven existing link types; F0–F11 pins/conformance pass.
- Dependency lock `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`, unchanged. No dependency or SPT repair.

## Dispositions

| Finding | Resulting behavior | Focused evidence |
|---|---|---|
| FR-1, Medium | Separate contract-known History link vocabulary. Invocations go to Runs, evidence to Evidence, unit relations retain Work/History lookups, tokens/commits remain text. Unknown relations warn with raw values and text targets. Annotation vocabulary remains separate. | Canonical vocabulary equality; all-seven F3 and unknown-relation component probes; compiled destination navigation. |
| FR-2, Low | Newer observed revisions immediately revalidate older active projections for the same project while visible. BigInt compares decimal revisions. One immediate attempt per query/observed target prevents old-response/304 retry loops. Disabled cached projections do not affect snapshot coherence. | Busy/stuck sequences, request bounds, large decimal revisions, hidden/disabled/inactive/foreign-project probes; compiled conditional API sequences. |

Normal intervals remain. Active historical projections also catch up to an observed newer revision without gaining interval polling. The coordinator never rewrites payloads, ETags, revisions or `generated_at`; 304 changes only `last_checked_at`. Persistent divergence remains UPDATING with the visible-time warning, never an inferred backend health/integrity conclusion.

## Validation and scope

The final immutable offline gate passes **73 tests in nine files**, generated-type comparison, typecheck, lint, normal/demo builds and production mock-exclusion checks. It starts with absent `node_modules`, installs 395 packages and disables networking. Carrier: `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, Linux/amd64, Node 22.22.2/npm 10.9.7. Log: `artifacts/fr-offline-gate.log`. Production main chunk: 546.64 kB / 161.79 kB gzip; existing non-blocking advisory remains.

**34 compiled browser checks pass:** 18 D1, 12 core, four focused review-fix checks. Reports: `browser-review-fixes-d1-report.json`, `browser-review-fixes-core-report.json`, `browser-review-fixes-report.json`; screenshots: `screenshots/review-fixes/`. Pinned Playwright 1.59.1 / Chromium 1217 (147.0.7727.15); host Node orchestration is separate from Node 22 build evidence.

Focused browser sequences advance the backend every three simulated seconds for at least 60 simulated seconds, with bounded real event-loop drains for networking/React rendering. Healthy views converge without the persistent warning; an intentionally stuck project returning conditional 304s still warns. Each scenario issues 21 project requests over 20 revision advances. This is synthetic same-origin API and controlled browser time, not live Engine acceptance or wall-clock endurance. Compiled checks exercise the proposed CSP and existing themes/responsive lanes; no browser/CSP errors, remote resources or API writes are observed.

**Negative control:** new focused probes against a disposable archive of frozen `e632cc8`, with only regression tests and the all-seven F3 fixture supplied, yield five expected failures and 12 skipped tests. Failures cover FR-1 known/unknown targets and FR-2 busy convergence, retry bounds and decimal precision. Corrected code passes the complete frontend suite. Log: `artifacts/fr-frozen-negative-control.log`. The additional `frontend-review-findings.test.tsx` probes present on resume are retained in the positive gate; no authorship or independent execution is attributed to the main reviewer.

No Engine source, original running checkout or Python suite was touched. Live authentication, server headers, Host/Origin checks, projection caching, packaging and live-state integration remain unverified here. Server ETags must change when the envelope revision changes; frontend cannot synthesize a newer revision from 304.

## Reproduction and review

```bash
# Isolated AEW-dashboard root; Docker CLI available on PATH.
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh

# From web/, compiled demo on 4173 and test-only production adapter on 4175.
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-d1.mjs
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-core.mjs
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4175 node scripts/browser-review-fixes.mjs

# Runtime/test diff excludes intervening documentation-only commits.
git diff e632cc83135ed98f70804df166d1c88f37a0b674 7c120b4c39a059508e3b095a9bfd5498c1d7be09 -- web/src web/tests web/scripts
git show 7c120b4c39a059508e3b095a9bfd5498c1d7be09
```

Frozen negative-control reproduction uses a new disposable directory under `web/artifacts/` (visible to this Docker daemon). Archive `e632cc8`'s `web/` and contract there, then supply the fixing commit's `tests/core-pages.test.tsx`, `tests/revision-reconciliation.test.tsx` and `src/api/mock/fixtures/F3.json`. Mount the directory read-only, copy it into container-native `/tmp/aew-negative`, install with `npm ci --offline --ignore-scripts`, and run:

```bash
node_modules/.bin/vitest run tests/revision-reconciliation.test.tsx tests/core-pages.test.tsx -t 'FR-1|busy revisions|unchanged high revision|decimal revisions'
```

Use the same immutable carrier with `--network none`; expected exit is 1 with the five assertion failures described above. A setup/install error is not a successful negative control.

Main-line checks this fixing diff and records ACCEPT before core freeze. `artifacts/aew-dashboard-core-7c120b4.tar.gz` includes the static build, review material, provenance, screenshots and validation logs with checksums. The historical archive stays retained. Serve only `static/`, never review fixtures. Editable lessons remain in `frontend-verification-lessons.md` and `frontend-verification-skill-handoff.md` for the user's M6 skill work; neither is an installed or evaluated skill.
