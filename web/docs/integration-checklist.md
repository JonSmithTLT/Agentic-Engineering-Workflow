# Frontend integration checklist

Candidate uses accepted API 0.1.2; this checklist distinguishes frontend evidence from main-line responsibilities. No checked frontend item substitutes for integrated-system verification.

## Frontend candidate evidence

- [x] Overview/Ticket visual review accepted by user on 2026-10-02.
- [x] Immutable SPT prerequisite consumed; lock unchanged and dependencies consumed.
- [x] Accepted canonical contract digest/types/Zod/F0–F11 pins consistent.
- [x] Empty-module offline typecheck/lint/tests/build and production exclusion pass.
- [x] Compiled core browser lanes pass under proposed CSP; local screenshots retained.
- [x] Backend-owned meanings, unknown values, pagination, currentness and freshness preserved.
- [x] SPT feedback retains resolved blockers and ticket-ready open improvements.
- [ ] Main AEW agent independently reviews the frozen frontend target and records findings.
- [ ] Required findings are addressed and the reviewer retests/signs off before core freeze.

## Main/integration line

- [ ] Serve the exported static build with SPA fallback for deep links and same-origin `/api/v1` routing.
- [ ] Implement only the accepted GET/HEAD projections; validate responses against that exact contract. Renew C0 review for changes.
- [ ] Provide real authentication/bootstrap, cookie handling and credential lifecycle.
- [ ] Enforce server security headers/CSP, Host/Origin validation and request boundaries; fixture adapter is not the server implementation.
- [ ] Implement coherent Overview generation, conditional representation validators, bounded cursors/filter semantics and projection caching.
- [ ] Preserve opaque identities and path-free projections; record backend semantic vocabularies/reasons. Unregistered frontend warnings remain until a reviewed registry establishes known values.
- [ ] Advertise integrity AVAILABLE only when the accepted projection is supplied; unavailable/unsupported states retain reasons. Queue needs a reviewed main-line contract first.
- [ ] Integrate Python packaging/static asset delivery without changing the running original checkout here.
- [ ] Repeat browser and security tests against authenticated live state, including deep-link reloads, revision changes, outages, archive pagination and capabilities.
- [ ] Record integrated-system acceptance separately from frontend review and mock validation.

Graph remains optional post-freeze work. Do not expand core contract solely to start that follow-up.
