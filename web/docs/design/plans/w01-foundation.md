# W01 — Reliable Preview and Verification Foundation

**Plan revision:** 1.1  
**Disposition:** APPROVED FOR IMPLEMENTATION  
**Approval reference:** operator message beginning “PLEASE IMPLEMENT THIS PLAN: W01 — Reliable Preview and Verification Foundation”, including both main-line review refinements.  
**Approved:** 2026-10-03 (operator local date)  
**Implementation baseline:** `7e13f3469e085f346b8bd889a5adf66b06532458`  
**Branch/worktree:** `feat/aew-dashboard-w01` / `AEW-dashboard-w01`  
**Digest record:** [w01-approval.json](w01-approval.json); SHA-256 covers this recorded plan artifact, not a claim that the chat itself was hashed.

## Summary and boundaries

Deliver W01-01 through W01-04 as one reviewable increment: preview-contract registry,
isolated read sessions, Scenario Lab/Contract Playground, deterministic regression
evidence. Use the existing API panel with Requests, Scenarios and Contract tabs.
Scripted scenarios advance manually; ordinary demo browsing retains normal polling.

Create an isolated worktree from the baseline above. Preserve the accepted core,
existing previews and main AEW checkout. Add no packages; keep the dependency lock
unchanged. Accepted API 0.1.2, digest, generated types and wire semantics stay unchanged.
W01 establishes infrastructure for later preview schemas without defining Journal,
context, guarantee or other future domain contracts. No Engine suite or live-system
acceptance is included.

## W01-01 — Contract registry and question ledger

Establish one registry identifying a contract by version, canonical artifact, digest,
runtime parser and fixtures. Register accepted 0.1.2; preserve F0–F11 conformance.
Future previews require separate versioned artifacts, runtime schemas, matching
fixtures and provisional disposition.

Preview contracts that expose explanations must explicitly represent “no explanation
supplied”; frontend code may not synthesize one from adjacent fields. This does not
define a future Why schema.

Version lab scenario configuration separately from API responses. Generate its JSON
Schema from Zod using the existing package and check generated consistency. It is
harness configuration, not an AEW API contract.

Maintain a backend question ledger for bootstrap/authorization identity, supported
scopes, historical snapshots, conditional validators and future preview ownership.
Unanswered questions remain live blockers. Contract acceptance, preview readiness
and frontend test success are separate states.

## W01-02 — Isolated read sessions

A shared context covers transport, query keys, explicit graph reads and revision
reconciliation. Identity comprises live/demo dataset (fixture/scenario in demo),
contract, project established by validated bootstrap, snapshot defaulting to live,
and a credential-free opaque session/authorization generation.

Add no scope parameters to accepted requests. Bootstrap `/project` before dependent
projections, bind subsequent envelopes to it and reject mismatched projects without
replacing valid content. Shared query-key construction and transport validators use
compatible context identity. Revision catch-up never crosses incompatible dataset,
project or snapshot contexts.

Reset retires the old generation, cancels requests, removes query/payload/validator/
diagnostic data, remounts projection-dependent UI and starts fresh bootstrap without
previous-data placeholders. Retired responses cannot commit even when fetch ignores
cancellation. Supply an explicit integration reset entrypoint; do not claim automatic
cookie/permission-change detection.

Valid 304 preserves payload, revision and generation time, updating only last-check
time. Initial 304 fails. ETag inconsistencies remain browser observations.

## W01-03 — Scenario Lab and Contract Playground

Requests retains the bounded 200-entry log, exact validation paths and ETag/revision
observations, adding non-secret context identity.

Scenarios retains F0–F11 and versioned recipe/fixture/seed/step/expected-observation
catalogs. Controls: Next step, Release response, Reset, Copy scenario link. Display
current step, held requests and manual replay labeling. Reset creates a fresh session.

Recipes cover valid load/304; initial 304; mismatched validators; failed/malformed
refresh; initial HTTP/network failure; capability downgrade/suppression; transient
and persistent mixed revisions including hidden pause; late response after session
switch; future semantic values; hostile content; large Work and History worlds.

Match by route plus per-route ordinal, not cross-route arrival order; release held
responses explicitly. This is exclusively test-harness matching, not API semantics.
Extra harmless requests may shift ordinals: diagnose them and update recipes rather
than constraining production behavior.

Contract selects registered schemas, loads fixtures or parses pasted JSON through
the real boundary parser. Input limit 256 KiB; issue display limit 100. Editing sends
no requests or projection replacements. Distinguish syntax/shape acceptance and
known-field unknown semantics. Successful parsing is not semantic understanding.
Input remains component memory only and is discarded on clear, close or reset;
never put bodies in logs, storage or URLs.

Scenarios and Contract load dynamically only in demo builds. Production keeps the
observational Requests panel.

## W01-04 — Replay and verification

Inject clock/scheduler behavior for replay; ordinary browsing uses real time/native
visibility. Manual replay disables interval polling and advances only through authored
steps. Explicit refresh/visibility steps use real transport/query paths. Normal polling
checks remain separate.

Scenario links contain only catalog version, recipe, fixture and seed. Reload starts
at step zero without cached payloads or partial execution.

Preserve 2/5/10-second Overview/list/detail intervals, hidden interval pause, immediate
visible revalidation, manual/focus-only historical refresh, 30-second accumulated
visible divergence warning, convergence reset, and bounded newer-revision catch-up.

## Verification and acceptance

Test composed paths for cross-context payload/validator/graph separation, identical
IDs, retired late 200/304, cached-content preservation, honest initial load failure,
capability downgrade/coherence exclusion, busy convergence versus genuinely stuck
projections, repeatable replay/reset, unexpected-request diagnostics, exact validation
paths, accepted unknown strings and explicit missing-explanation guidance.

Run compiled browser/CSP checks for all tabs, keyboard/focus/Escape, both themes,
desktop/phone, ordinary polling separately from replay, graph navigation/reload,
hostile content and bounded large-list/history rendering. Capture intentional failure
cases explicitly; do not globally ignore console/page/CSP errors. No unexpected
external requests or non-GET/HEAD API traffic.

Use the immutable Node 22 SPT carrier, staged matching Playwright assets, empty
modules and networking disabled. Check offline installation, generated consistency,
typecheck, lint, tests and production/demo builds. Reject production lab/replay/fixture/
MSW leakage. Retain JSON report, commands/logs, screenshots and failure traces with
commit/contract/lock/cache/image/browser identities and verification scope. Compare
F6/F7 rendering/request behavior to the frozen baseline; investigate regressions.

## Delivery and review

Reviewable checkpoints: registry/artifacts/ledger; context isolation/tests; panel/replay;
recipes/browser/offline evidence. Deliver frozen packet, unresolved integration
questions and SPT feedback. Nonblocking toolchain findings remain documentation;
blockers get separate minimal fixes/retests.

Main AEW agent independently reviews the frozen change and dispositions findings
before W01 frontend acceptance. No authenticated scope, real API or future backend
contract acceptance is claimed.

## Subsequently authorized CI draft

During implementation the operator relayed main-owner authorization for a frontend
`web.yml` draft on this branch. Stable job identifiers, checksum sourced from
`web/docs/c0-approval.json`, shared-contract path filter, standard Linux Node/npm,
locked install, browser checks and failure-only screenshot upload are required.
CI is informational until F20 integration. The main owner edits assurance and CodeQL;
assurance remains the sole required check. The offline SPT gate remains separate.
This addition does not authorize publishing branches or changing the main owner's gates.
