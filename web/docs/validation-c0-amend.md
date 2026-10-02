# Historical C0 0.1.1 validation at 7b0177b — 2026-10-02

**Historical validation for version 0.1.1 at `7b0177b76a919e019d2051adff8f7616ae6c2fda`. The later main-line review required six mechanical corrections.**

Current candidate and evidence: [0.1.2 review packet](c0-review-packet.md) and [0.1.2 validation](validation-c0-012.md). Counts and shapes below describe the prior candidate; they do not establish current acceptance.

## Frozen contract and baseline

Candidate OpenAPI 3.1 version **0.1.1**, SHA-256
`3da20f18768d34bef9ccf15fcb65c24cefd2ca73cfc77e6cada8a586f88a0dc4`.
The candidate review target is the commit containing this document and the updated packet. Main-line review must name that full commit and this exact digest.

Previous version 0.1.0 at `59081d0136bba947d645c2ec60132e5ca7e12e1a`
received **AMEND** from Claude against engine `main` at `91c0d98`.
The original review is retained in `c0-review-main-line.md`; its disposition and
identity are preserved in `c0-approval.json`. The new candidate is not accepted.

Engine schema/source inspection at `91c0d98` checked evidence snapshot/producer
fields, manifest/archive/annotation structures, unit states and harness
telemetry. No Engine projection adapter was implemented or tested. Assurance
is omitted; queue is unsupported with no model/endpoint; integrity is
unsupported until P2c, with future wire examples separately marked provisional.
Two boundedness proposals require confirmation: parent child truncation and
history detail annotation pagination. See `c0-review-packet.md`.

## Offline acceptance gate: PASS

Command from the isolated AEW worktree:

```bash
PATH="/tmp/aew-bin:$PATH" \
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/offline-gate.sh
```

The immutable Linux/amd64 carrier ran with `--network none`, Node 22.22.2
and npm 10.9.7. The script asserted absent modules in ephemeral native storage
before `npm ci --offline --ignore-scripts` installed 395 packages. No package,
lock or SPT cache change accompanies the amendment. Consumer lock SHA-256:
`3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`.
SPT lock/cache/browser provenance remains in `builder-provenance.json`.

- OpenAPI generation with cached openapi-typescript 7.13.0 matched committed types.
- Typecheck and lint passed.
- **38 tests in five files passed.** Contract/runtime conformance for all
  F0–F11, isolated provisional integrity examples, version/digest pins,
  GET/HEAD-only routes, per-route statuses, backend filters, removed queue
  shapes, path-safe entity IDs versus opaque cursors, decimal revisions,
  unknown values/capability keys, path-free bindings, manual invocations,
  manifest trust labels and list annotations were covered.
- Mock server tests covered default hot-plus-recent work versus explicit
  terminal archive filters; archived lookup; work/evidence/history filters;
  bounded active pagination; cursor scope rejection and hot expiry;
  a 50,000-entry starting history traversal surviving two new entries and
  a revision change, with a fresh traversal seeing both appends; bounded
  annotation paging; stable cursor tokens; ETag changes for telemetry at the
  same control revision and for query variants. These verify the demo server,
  not Engine history indexing or production server behavior.
- Existing transport/refresh/component checks passed: same-origin conditional
  GET, 304 preservation, malformed/failed refresh cache retention, initial
  failures, polling visibility rules, suppressed capability queries, visible
  mixed-revision timer, raw unknown warnings, safe Markdown/JSON and links.
- Production build and its mock-leakage check passed; demo build passed.

Evidence: `web/artifacts/c0-amend-offline-driver.log` and
`web/artifacts/c0-amend-offline-gate.log` (retained local artifacts).
Static outputs: `web/artifacts/offline-gate/dist/` and `dist-demo/`, copied
into `web/dist/` and `web/dist-demo/` for preview. The 1.1 MB fixture-world
chunk exceeds Vite's advisory size; it is excluded from production.

An initial host check found an MSW JSON-response typing issue, fixed before the
final gate. The first offline attempt found a browser-probe line-wrap lint
issue; it was fixed, then the complete gate passed. These are frontend probe
issues, not SPT cache defects. No passing result is claimed for those failed
attempts.

## Compiled browser acceptance: PASS (foundation scope)

Command from `web/`, using the freshly exported builds served on 4173 and 4174:

```bash
PATH="/home/jon/.local/bin:$PATH" \
DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4174 \
node scripts/browser-d0.mjs
```

Pinned Playwright 1.59.1 launched separately staged Chromium revision 1217,
version 147.0.7727.15. WSL automation used user-local Node 24.21.0 and existing
runtime libraries; installation/build acceptance above used Node 22.22.2.
Do not conflate the two runtimes. Browser binary provenance is unchanged.

The proposed strict self-only script/style/connect CSP, without unsafe-inline,
was applied by Vite preview. Checks passed for Overview light/dark palettes,
Ticket navigation/reload, keyboard skip navigation, 390px phone navigation and
panel-confined overflow, hostile Markdown/escaped code, unknown work state and
capability-key warnings, archived-by-ID lookup/reload with an explicit
historical-reference warning, stale cached content after failed refresh and
initial malformed-response errors. Production had no demo data, worker
registration, API calls or remote assets. No unexpected page/console errors,
remote subresources or API writes occurred; deliberate HTTP 500 output is
recorded separately.

Report: `web/docs/browser-d0-report.json`; local execution log:
`web/artifacts/c0-amend-browser.log`. Current screenshots are in
`web/docs/screenshots/`; light Overview and dark Ticket were visually inspected.

Existing owned preview servers were still bound to 4173/4174; fresh startup
attempts correctly failed strict-port checks. The existing servers served the
newly exported static files and the browser validation passed against them.
A sandbox-local curl failure was not treated as evidence that the servers were
absent. No other process was terminated or restarted.

## Remaining gates

- Renewed main-line approval of this exact contract/version/digest/commit,
  including the two explicit pagination/truncation proposals.
- User/designer review of mock Overview and realistic Ticket before expansion.
- D1–D4 domain implementation after C0; Queue remains unavailable pending M4/M5,
  Integrity remains unavailable pending P2c. Do not invent substitutes.
- Future route, virtualization, real list/detail/history, overlay/CSP and
  boundary browser checks appropriate to those implementations.
- Independent main-line frontend review and finding disposition at core freeze.
- Main-line authentication/bootstrap, serving/security headers, Host/Origin
  validation, projection caching, shared reason registry, Python packaging and
  live-state integration.

Only `web/` and the provisional contract were changed. No AEW Python suite was
invoked, and the original AEW checkout and concurrent tests were left alone.
