# Frontend verification lessons for an AEW/SPT skill

Editable working notes, 2026-10-02. Prepared from the AEW dashboard implementation and main-line reviews. This is material for the user to extend before creating/evaluating a skill; it is not an installed skill, a new authority policy, or evidence of skill effectiveness.

## Purpose and boundaries

Help an LLM verify that a frontend faithfully presents its accepted backend contract, stays within its authority, and works in a real browser. The eventual skill supplies techniques. Assigned roles, approved requirements, Engine semantics and project approval gates remain authoritative. It must not create its own workflow transitions, credentials, routing policy or duplicate project facts.

Use it for interactive frontends with meaningful state, failure handling, browser constraints or integration boundaries. Keep simple visual edits proportional: reuse relevant existing checks rather than rebuilding a verification program for every text/style change.

## Establish exactly what is being verified

Record the source commit, accepted contract version/hash, builder image identity, dependency lock, browser revision and relevant environment. Separate the target under review from the live working folder. Preserve the original checkout and concurrent tests when working in isolation.

Distinguish:

| Claim | Evidence needed |
|---|---|
| Compiles offline | Empty modules, immutable builder, network disabled, offline installation and recorded build/check results |
| Conforms to wire contract | Accepted artifact identity, generated-type consistency, runtime validation and representative contract-valid responses |
| Works in a browser | Compiled UI interactions, real browser revision, failures/security/layout checks and retained reports/screenshots |
| Independently reviewed | Actual reviewer, frozen commit, review scope, findings and disposition |
| Integrated system accepted | Real backend/authentication/serving/security/live-state tests on the integrated revision |

These claims do not substitute for one another. A fixture API is useful evidence for frontend behavior, not proof of Engine behavior. Static review is useful independent evidence, not witnessed execution of the implementer's tests.

## Verify meanings, not just matching shapes

Generate types from the accepted canonical artifact and validate incoming data at runtime. Check companion artifacts together. Generator success alone does not prove the whole OpenAPI specification is valid: operation parameter uniqueness required a separate check in this project.

Inventory semantic vocabularies by field. Similar words do not imply the same vocabulary. The independent review found that History link relations were incorrectly checked against annotation relations: normal dependencies, invocations, tokens and evidence were marked unknown even though the contract recognized them. Add a fixture covering every recognized relation, verify the vocabulary against the canonical artifact, and inspect each destination route. Unknown relations must retain a raw warning and must not invent target types.

Opaque IDs are not paths or parseable domain facts. Cursor identity is distinct from record identity. Filters and pagination must be bounded and backend-owned; check cursor scope changes, reloads, invalid values, terminal-state history access and annotation pagination separately.

Do not calculate workflow legality, assurance, currentness, integrity, backend health or queue conclusions. A loaded-page hierarchy is not the complete project graph. Missing capabilities explain unavailability and suppress requests; they do not mean zero records. Explicitly label demo data and historical references.

## Test public sequences and realistic time

Shape-valid happy fixtures are insufficient. Exercise transitions through the public transport/query/UI path:

- First load succeeds; conditional 304 follows; malformed or failed refresh follows. The 304 changes only last-check time; malformed data must not replace good content. Initial failure has no stale data to show.
- Revisions briefly differ and then converge. Continuous visible divergence warns after 30 seconds, pauses while hidden, and clears on convergence. A busy healthy project must remain distinguishable from genuinely stuck projections.
- Hide the document; verify interval requests stop. Show it; verify immediate revalidation and resumed intervals. Disabled/inactive projections must stay suppressed.
- Change filters or pages while requests are in flight; navigate away/back; reload a deep link. Verify no foreign cursor reuse, stale identity substitution or lost bounds.
- Refresh a large virtualized page with fewer rows. A previously scrolled window must clamp to real rows rather than become blank.
- Downgrade a capability after data has loaded. Inspect both request suppression and the visible freshness state; hidden cached data must not create a false mixed-revision warning.

FR-2 was missed by the original tests: each polling cadence was locally correct, but `/project` could lag forever while the Lead committed frequently. Test revisions advancing every 3 seconds for 60 seconds, with unequal polling cadences. Older active projections should revalidate when a newer revision is observed. Pair this with a server that keeps one projection old, so catching up cannot merely suppress the warning. Include a guard against repeated immediate refetches when the server will not converge.

Use fake time for long deterministic sequences and real compiled browser checks for actual integration of timers, DOM visibility and query behavior. Compare numeric decimal revisions without losing precision. Backend ETags must cover the envelope revision; otherwise a valid 304 preserves an old revision indefinitely. Record that as a backend integration requirement, not a client workaround that rewrites generation time or revision.

## Browser and visual checks

Inspect compiled output under the proposed production CSP. A permissive development server can conceal style/script incompatibilities. Measure virtualization using actual scroll height and DOM row bounds; asserting a class name is insufficient. Exercise keyboard scrolling and an accessible complete-loaded-page alternative.

Visit every core route and reload opaque-ID detail URLs. Inspect light/dark themes, desktop and phone layouts, navigation collapse, focus/skip navigation, disclosure panels and wide table overflow confined to its panel. Check long IDs, hashes and expanded JSON. Use local assets.

Retain screenshots and inspect them. This caught flush detail headings and inconsistent panel spacing after functional checks passed. Screenshots document appearance, not interaction correctness. Preserve historical screenshots separately from current candidate evidence.

Accessible-name probes must evolve with intended UI changes. Adding ticket IDs to title links correctly changed their accessible names; update the probe to require the ID and title rather than weakening it to any matching text.

## Content and read-only security

Use hostile Markdown with raw HTML, scripts, images, dangerous links and literal code. Check that HTML/scripts cannot execute, remote images/subresources are not fetched, code/JSON remain escaped text, and allowed external navigation is explicit. Combine unit renderer tests with browser request/error capture and source inspection.

Inspect the full transport boundary: allow-listed same-origin reads, cookie-compatible credentials, refused redirects, runtime response validation, conditional caches and aborted responses. Record unexpected console/page/CSP errors and non-GET/HEAD API requests. Intentional failure-fixture errors should be identified separately, not silently ignored globally.

Verify normal production excludes fixture modules, demo controls and MSW initialization. Exercise the normal compiled build against a test-only same-origin fixture adapter as well as the demo build. Keep review fixtures outside the static served directory. Server authentication, Host/Origin validation, headers, packaging and live projection caching remain integration responsibilities.

## SPT and environment lessons

Use the project's pinned tools and existing scripts before proposing downloads or global installs. An offline-friendly skill needs an alternative to a default `npx ...@latest` workflow. Package cache, browser binaries and browser OS libraries are separate prerequisites; record their identities separately.

Build into container-native storage when Windows bind mounts make dependency installation slow; export evidence and static outputs. Observed timings are not controlled performance benchmarks. Replace owned generated build directories during export: merging builds retains obsolete hashed assets even when the fresh build itself is correct.

A cached package tarball does not imply cached registry metadata. Pinned-name offline Prettier execution failed here, while the exact cached tarball URL worked with networking disabled. Preserve the reproduction and successful retest in SPT feedback. Do not blame the carrier for command mistakes such as using an incorrect working directory. Do not respond to routine friction with unneeded dependencies or broad lock upgrades.

## Evidence, review and handoff

Record commands, commit/environment, outcomes, scope and missing lanes. Keep passing counts attached to the checks actually run. Do not call selected tests a full Engine suite, browser fixtures live integration, or a static reviewer a witness to execution.

Keep a stable-ID feedback log with demonstrated failures separate from inspection findings and improvement suggestions. Include impact, reproduction, evidence, workaround, proposed acceptance criteria, fix and retest. Retain resolved entries. Non-blocking improvements need not hold delivery hostage.

Freeze an independently reviewable commit and package its static build, accepted contract, provenance, screenshots, evidence and integration checklist. Verify archive checksums and scope boundaries. Record the actual review return intact; link each finding to a narrow fix and a meaningful regression. Conditional or minor amendment is not ACCEPT until the reviewer checks the fixing diff and records it.

## How to turn these notes into a skill later

Keep runtime instructions focused; move executable helpers and examples into supporting files. Prefer existing project scripts rather than duplicating them. The skill should discover the project contract, tool identities and authority boundaries instead of hardcoding AEW dashboard facts.

Evaluate on the target LLMs with skill/no-skill comparisons. Include a busy healthy project, a truly stale projection, unknown semantic values, mismatched relation vocabularies, hostile content, a constrained offline environment and a small edit where excessive testing should be avoided. Keep evaluator-only expectations separate from worker-visible instructions. This dashboard's results are useful examples, not controlled evidence that the skill improves another model.

## User additions

Add other projects, model-specific behavior, missed checks, preferred evidence formats and successful/failed examples here before drafting the skill.
