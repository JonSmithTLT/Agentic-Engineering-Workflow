# C0 0.1.2 mechanical correction validation — 2026-10-02

**Frontend checks passed; main-line diff verification and acceptance record remain pending. D1–D4 remain gated.**

Contract version **0.1.2**, SHA-256
`68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`.
The artifact-bearing commit containing this document is the candidate review target.
Diff base: `7b0177b76a919e019d2051adff8f7616ae6c2fda` (reviewed 0.1.1).
The retained review `c0-review-main-line-0.1.1.md` conditionally accepts exactly
R2-1–R2-6 after main-line diff verification. Both previous AMEND reviews are
recorded in `c0-approval.json`; this candidate has no accepted disposition.

## Scope and source checks

A parsed comparison of canonical YAML against the reviewed base found only:
unique GET/HEAD parameter lists; opaque evidence fingerprint/digest items;
history-link documentation and known relations; subtree Ticket count wording;
P2c verified/full/oldest-unverified fields and descriptions; known `lost` status;
version constants and review bookkeeping. No endpoint or unrelated wire shape
was added. The correction map is in `c0-review-packet.md`.

Read-only engine inspection confirmed `git-tree:<hex>` at
`91c0d98:src/aew/snapshot/fingerprint.py` and P2c verified/last_full audit metadata
at `bdabff9:src/aew/engine/history_ops.py`. This is source alignment, not a live
Engine adapter test or a statement about current PR merge status. Frozen
baseline fixtures continue to advertise integrity UNSUPPORTED; integration
advertises AVAILABLE after the P2c merge. The wire keeps `x-provisional: P2c`.

## Immutable offline gate: PASS

From the isolated AEW worktree:

```bash
PATH="/tmp/aew-bin:$PATH" \
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/offline-gate.sh
```

The Linux/amd64 carrier ran with `--network none`, Node 22.22.2 and npm 10.9.7.
It asserted absent `node_modules` in ephemeral native storage, then installed
395 platform-applicable packages offline. Package, lock and cache identities
are unchanged; consumer lock SHA-256:
`3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`.
Builder/cache/browser identities remain in `builder-provenance.json`.

- Generated types matched committed types using cached openapi-typescript 7.13.0.
- Typecheck and lint passed.
- **45 tests in five files passed.** Prior 38 regressions remain; seven added
  checks cover unique GET/HEAD parameter identities with a negative control,
  real opaque evidence values in both validators, commit-hash links and rejected
  completion paths, direct-child versus subtree Ticket counts, P2c metadata and
  nullability, known `lost` rendering and conditional-review bookkeeping.
- F0–F11, bounded mock pages and isolated provisional P2c examples conform to
  both the canonical schemas and Zod; version/digest pins agree.
- Production build and mock-exclusion check passed; demo build passed. The
  roughly 1.1 MB fixture-world chunk triggers Vite's advisory, but it is excluded
  from production. No dependencies or cache workarounds were added.

Evidence: `web/artifacts/c0-012-offline-driver.log` and
`web/artifacts/c0-012-offline-gate.log`; static outputs under
`web/artifacts/offline-gate/`, copied to `web/dist/` and `web/dist-demo/`.
OpenAPI parameter uniqueness is now explicitly checked. Generation and the
Ajv common-keyword subset are not claimed to constitute a complete OpenAPI 3.1
specification-validator run.

## Compiled browser regression: PASS

The existing probe runs against the exported demo/production builds:

```bash
# Run from web/, with demo on 4173 and production on 4174.
PATH="/home/jon/.local/bin:$PATH" \
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4174 \
node scripts/browser-d0.mjs
```

Current status/report: `web/docs/browser-d0-report.json`; execution log:
`web/artifacts/c0-012-browser.log`. Matched Playwright 1.59.1 and separately
staged Chromium 1217 (147.0.7727.15) are reused. Browser automation runs under
user-local Node 24.21.0 with existing WSL libraries; the offline acceptance
above runs under Node 22.22.2.

Scope stays D0 shell/provisional previews: both themes, Overview/Ticket links
and reload, keyboard/mobile navigation and panel overflow, hostile Markdown,
unknown states/capabilities, archived lookup/historical warnings, stale cached
refreshes, malformed initial load, strict preview CSP and production absence
of mock behavior/remote requests/API writes. This does not establish D1–D4,
Engine integration, server authentication or production serving security.
The report records PASS for all 12 checks, with no unexpected page/console
errors, remote subresources or API writes. The injected HTTP 500 remains an
expected network error. No UI layout or browser-probe code changed for this
mechanical correction.

## Remaining gate

Main line verifies only this diff and records the candidate commit, exact
version/digest, reviewer/date and accepted disposition. The frontend agent does
not promote conditional acceptance to a final acceptance record. Then domain
implementation may proceed; independent frontend review at core freeze and
integrated-system acceptance remain separate.

Only `web/` and the provisional YAML changed. The original AEW checkout,
engine/storage/workflow semantics and concurrent tests remain untouched;
no AEW Python suite was invoked.
