# Historical D0 validation at 59081d0 — 2026-10-02

**Historical evidence for contract 0.1.0 at `59081d0136bba947d645c2ec60132e5ca7e12e1a`. Main-line review subsequently returned AMEND.**

Current candidate and validation: [C0 resubmission](c0-review-packet.md) and [amendment validation](validation-c0-amend.md). The counts and shapes below describe the original D0, not current approval or integration acceptance.

## Prerequisite and provenance

SPT fix commit: `ae65ad0408536140a96335e8e76a6245a33ace4a` on
`build/aew-dashboard-tailwind-cache` in the separate SPT worktree.
Final carrier: `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`,
Linux/amd64, Node 22.22.2, npm 10.9.7.

`builder-provenance.json` pins base/image, lock, cache manifest/checksum and
separately staged browser identities. Carrier checksums and the complete
existing SPT import/build smoke with actual Tailwind/Vite compilation passed
on this exact final image. Nothing was published to a registry.

## Frontend offline gate: PASS

`SPT_FRONTEND_IMAGE=<final-id> bash web/scripts/offline-gate.sh` ran with
`--network none` and copied frontend/contract sources into ephemeral native
container storage. `node_modules` did not exist before `npm ci --offline`.

- Pinned subset installed: 395 platform-applicable packages.
- OpenAPI generation matched committed types exactly.
- Typecheck and lint passed.
- Four test files, **26 tests passed**: F0–F11 canonical/runtime conformance;
  artifact version/hash; GET/HEAD boundary; malformed/bounded responses;
  conditional same-origin GET; 304 identity/generation preservation;
  cached failures; initial 304/non-JSON/aborted requests; deterministic hidden
  polling and immediate visible revalidation; suppressed capability requests;
  visible mixed-revision timer/reset; unknown values; safe Markdown/JSON and
  encoded entity links.
- Production build passed its mock-leakage check; separate demo build passed.
- Final browser-script/config lint passed after the final browser probe edits.

Evidence: `web/artifacts/offline-driver-final.log`,
`web/artifacts/offline-gate.log`, `web/artifacts/lint-final.log`;
static outputs: `web/artifacts/offline-gate/dist/` and `dist-demo/`.
Builds are also copied to `web/dist/` and `web/dist-demo/` for local preview.
The demo world bundle exceeds Vite's size advisory; it is excluded from
production and is not a core production dependency/performance finding.

## Compiled browser checks: PASS (D0 scope)

Matched cached Playwright 1.59.1 and separately staged Chromium revision 1217
(147.0.7727.15). Browser artifact checksums are at
`web/artifacts/playwright/SHA256SUMS`. Automation ran in WSL with user-local
Node 24.21.0 and existing browser runtime libraries; the offline install/build
acceptance above ran exclusively in Node 22.22.2. Do not conflate these runtimes.

`DASHBOARD_PRODUCTION_URL=http://127.0.0.1:4174 node scripts/browser-d0.mjs`
ran from `web/`, with compiled demo on port 4173 and production on 4174.
The reproducible report is `browser-d0-report.json`.

Checks cover Overview, both actual theme palettes, realistic Ticket navigation
and deep-link reload, keyboard skip navigation, 390px phone navigation and
panel-confined table overflow, hostile Markdown under CSP, future state warning,
failed-refresh cached content, malformed initial load, and production absence
of demo data, worker registration, API calls and remote assets. The injected
HTTP 500 is recorded separately as an expected network error. There were no
unexpected console/page errors, remote subresource requests or API writes.

The compiled builds ran with the proposed strict self-only script/style/connect
CSP, no unsafe-inline, no-referrer and nosniff headers supplied by Vite preview.
This proves the D0 components under those headers; it does not establish the
security properties of the future AEW serving adapter.

Screenshots:

- [Overview, light](screenshots/overview-light.png)
- [Overview, dark](screenshots/overview-dark.png)
- [Overview, phone](screenshots/overview-phone.png)
- [Ticket detail, dark](screenshots/ticket-dark.png)

## D0 findings and disposition

1. **Fixed:** stored native fetch received an illegal object-method receiver in
   the browser. Default transport now calls `globalThis.fetch` correctly;
   compiled Overview, conditional refresh and failure retention passed.
2. **Fixed:** a demo label survived production tree-shaking through a runtime
   prop. Shell now uses the build-time mode; static leak check and isolated
   production browser checks passed.
3. **Fixed separately in SPT:** npm verification marker invalidated carrier
   checksums; see SPT-UI-005 and the final checksum/full-smoke retests.
4. **Probe correction:** keyboard skip navigation now activates the skip link
   before mobile pointer navigation; it no longer leaves the focused skip-link
   overlay over the menu button during the test.
5. **Probe correction:** explicitly injected HTTP 500 is classified as expected
   network evidence rather than an unrelated console error. Other errors fail.

## Remaining gates and integration checklist

- Main AEW agent reviews `c0-review-packet.md` and the exact canonical contract
  version/hash/commit. Approval stays PENDING until that review returns.
- Review the running mock Overview and Ticket screenshots before expansion.
- After C0, D1–D4 implement Work filtering/tree/table/virtualization, Runs,
  Evidence, Knowledge/decisions, bounded History/integrity and Attention/Queue.
- Later browser acceptance must exercise all real core routes, active list
  virtualization, history pagination, overlays under CSP and capability-specific
  unavailable views. D0 mock previews do not satisfy those feature gates.
- Core freeze requires independent frontend review by the main AEW agent,
  explicit finding disposition, refreshed SPT feedback and integration handoff.
- Real authentication/bootstrap, server headers, Host/Origin enforcement,
  projection cache, Python packaging and live-state integration remain main-line
  ownership. Frontend acceptance and integrated-system acceptance stay separate.

No AEW Python tests were invoked and no Engine/history/control schemas were
changed. The original AEW checkout and its concurrent work were left alone.
