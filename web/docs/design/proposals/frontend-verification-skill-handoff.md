# Frontend verification: lessons and skill-authoring handoff

Written 2026-10-02 from AEW dashboard D0–D4 implementation and independent review. This is source material for an AEW M6 skill, not an installed skill or evidence that the technique improves every target model. The dashboard provides one case study. Its independent review was static; the reviewer did not rerun our tests or browser lanes.

## Intended skill

A focused `frontend-verification` skill should help an assigned agent verify a frontend change and produce reviewable evidence. Invoke it for browser-visible changes, API projection consumption, navigation, refresh behavior or frontend boundary/security changes. A documentation-only edit usually needs document consistency checks, not a browser campaign.

Keep it separate from `frontend-design`: design establishes visual intent; verification checks implemented behavior against that intent and the accepted contracts. The skill supplies technique. Role cards own authority, context packs own current project facts, capabilities expose tools, and the Engine owns transitions and acceptance. Do not embed credentials, workflow permissions, model routing, duplicate project truth or invented approval gates in the skill. Existing explicit review gates still apply.

## Inputs and preflight

Read the current task, ownership boundaries, repository instructions, accepted API/design artifacts and validation scripts. Identify the frozen target/base and permitted test scope. Discover installed tools, pinned packages, carrier image/cache manifests, browser revisions and OS prerequisites before proposing installations. A missing host command does not establish that a container-carried tool is unavailable.

Use repository-native scripts when they supply the required behavior. The stock Playwright skill favors its CLI; this project used pinned Playwright library scripts for reproducible compiled-browser probes. An AEW version should explicitly support that path without silently downloading a different CLI/browser. Do not run unrelated backend suites or restart a workspace containing concurrent work just to validate a frontend.

Separate prerequisites from skill text: SPT owns reproducible tools/cache provenance; a browser artifact is separately staged and matched to the pinned automation package; the skill explains how to discover and use them. Figma is an optional design source when an actual file/node is supplied, not a verification prerequisite.

## Verification sequence

1. Freeze the candidate and distinguish new changes from inherited behavior. Scale checks to the risk: a display-only correction needs a focused probe; transport/coherence/security changes need sequence tests and compiled browser evidence.
2. Run the relevant static/component/contract checks. For an offline acceptance gate, prove absent modules, an immutable carrier identity and disabled networking. Regenerate contract-derived artifacts and check drift. Record package/cache/lock identities.
3. Build normal production separately from demo. Verify the built output excludes fixtures, mock initialization and demo controls. Test production with same-origin projections; identify any fixture adapter as a test harness, not live-system integration.
4. Test public sequences, not only helpers: navigate, reload a deep link, change filters, page a collection, receive updated data, lose connectivity, regain visibility and converge revisions. Use hostile/malformed/unknown inputs and negative controls.
5. Run the compiled UI under the proposed CSP, inspect screenshots and repair visual defects. Verify navigation/focus and viewport overflow through actual interactions. Repeat only affected checks after corrections, unless broader unresolved risks justify more.
6. Export fresh artifacts, verify their contents/checksums and record the exact evidence scope. Keep independent review and integrated-system acceptance separate from implementer test results.

## Contract and semantic honesty

Validate responses before replacing cached data. Check generated types, runtime schemas, contract version/digest and fixture conformance together. Unknown capability names must remain valid where the contract allows them; unknown states/semantic strings should show raw values with explicit warnings. Missing/unsupported capabilities explain unavailable data and suppress requests, rather than showing zero or empty conclusions.

Do not infer workflow health, gates, assurance, evidence currentness, audit integrity, custody or publication legality from client observations. Backend counts/rollups remain backend conclusions. A loaded page is not the entire hierarchy; truncation and bounded scope must be visible. Archived records never become current evidence because the browser refreshed them.

**Lesson from FR-1:** distinct vocabularies can contain similar strings yet describe different objects. History link relations and annotation relations need separate mappings to the accepted contract. Test the entire known relation set, including route destinations: invocation → Runs, evidence → Evidence, credentials without a page → plain IDs. Add an unknown-relation negative control; never infer a target's kind from the spelling of its opaque ID.

## Refresh, cache and revision probes

Check generation time separately from last successful check. A 304 preserves the validated payload, revision and generation timestamp. A failed/malformed refresh retains visibly stale last-known-good content. Initial failure must not pretend nonexistent data is stale.

Test hidden-tab interval suppression and immediate visible/focus revalidation. Exercise coherent, temporarily mixed and persistently divergent responses. Include hidden time in timer tests so only visible divergence counts toward a warning. Do not turn a mixed-revision transport warning into a backend integrity finding.

**Lesson from FR-2:** ordinary independent polling may keep a slow projection behind during sustained activity. Test a moving server revision (for example every 3 seconds for 60 seconds), not just a static pair of mismatched revisions. When a visible projection advances, catch older active projections up immediately. Also test a server that keeps one response pinned: it must still produce the persistent warning. Include request-bound checks to detect retry storms, in-flight deduplication, hidden tabs, disabled capabilities and large decimal revisions.

ETag correctness is a backend integration prerequisite: the full representation includes envelope revision, route/filter/cursor scope and telemetry. The frontend must preserve a 304; it cannot repair a server validator that falsely confirms an old representation.

## Browser and visual checks

Inspect both themes, a desktop/laptop viewport and a phone viewport. Verify panel spacing, readability, meaningful empty/error states, opaque IDs beside titles and long-value wrapping. Measure document overflow; a table may scroll inside its own panel without widening the entire phone page.

Check keyboard skip navigation, focus visibility, navigation/menu controls, native disclosure controls and deep-link reloads. For virtualization, measure actual scroll height and bounded rendered rows under CSP; a unit test of array slicing alone does not prove the layout works. Exercise keyboard scrolling and an accessible alternative. For pagination, demonstrate a later page with an opaque cursor and no fetch-all behavior.

Screenshots are evidence to inspect, not automatic acceptance. This case found flush detail headings through screenshot review despite passing functional checks. Use representative content rather than attractive empty cards; preserve the approved visual brief rather than redesigning it during verification.

## Hostile content and read-only boundaries

Probe raw HTML/scripts, remote images, script URLs, external links, Markdown code fences and hostile JSON/text. Verify escaping, suppression of unwanted resource requests and explicit external navigation. Check the compiled UI under its proposed CSP, including virtualization and disclosures/overlays actually used by the feature.

Inspect network methods/routes/redirect handling and source boundaries. Verify no unintended mutation surface, Engine/storage coupling, credential persistence or remote assets. UI buttons for paging, filtering and appearance are local controls; their presence alone is not a workflow mutation.

A browser probe with zero writes is useful evidence but does not replace source inspection or actual-server security tests. Authentication/bootstrap, Host/Origin validation and live serving headers remain integration scope when assigned elsewhere.

## Toolchain and artifact lessons

- A cache entry for a package tarball does not guarantee offline package-name resolution. In this carrier, pinned-name `npm exec` failed with ENOTCACHED while the exact cached tarball URL worked with networking disabled. Record command, image and error; use the smallest verified invocation adjustment instead of broad dependency upgrades.
- Windows-mounted installation can dominate iteration cost. This project copied inputs to container-native storage and exported bounded artifacts. Timing observations are not controlled performance benchmarks.
- Browser binaries and runtime OS libraries are separate prerequisites from npm installation. Record matched browser/package identities.
- Repeated artifact exports must replace owned generated output directories. Merging exports can retain obsolete hashed bundles even when a fresh build passes.
- Preserve original lockfiles as resolution baselines. Keep prerequisite cache repairs separate from frontend history; consume an immutable validated image.
- Record demonstrated failures, inspection findings and suggestions separately. Retain resolved friction entries with repro, identity, impact, workaround, proposed ticket criteria and retest.

## Evidence template

Record: target/base commit; accepted contract version/digest; builder/platform/package/lock/browser identities; command and environment; PASS/FAIL and counts; exact exercised scope; logs/reports/screenshots; findings and dispositions; missing lanes; independent reviewer status; integrated-system status.

Example from this case before amendment: 61 frontend tests and 18+12 compiled browser checks passed, but main-line static review still found FR-1 and FR-2. These results were implementer evidence, not reviewer-observed tests or integrated-system acceptance. Passing mocks did not satisfy the independent review gate.

A skill must report uncertainty plainly and leave explicit acceptance decisions with the assigned owner. It should not add permission requests for already authorized reversible verification.

## Suggested M6 evaluation

Run target-model A/B comparisons with and without the candidate skill, keeping task/context/tools fixed. Start with a dense read-only dashboard, a small existing-UI edit, and an API refresh/navigation repair. Keep evaluator rubrics/hidden negative controls outside worker-visible skill material.

Evaluate whether the agent finds seeded defects and produces reproducible evidence, preserves role/contract boundaries, uses existing pinned tools, avoids unnecessary installs/test campaigns, and states validation limits correctly. Negative controls should include already-correct content, an unrelated docs-only task, unavailable capabilities, unknown semantics, sustained revision churn, a permanently old projection, missing host tools with a usable carrier, and a tempting backend-meaning inference. Require abstention or escalation to the proper owner where appropriate. This handoff proposes that evaluation; it does not claim the skill is evaluated or production-ready.

## Reusable source material

Use the dashboard's `scripts/offline-gate.sh`, `scripts/browser-d1.mjs`, `scripts/browser-core.mjs`, contract/transport/refresh/component tests, `validation-core.md`, `integration-checklist.md` and `spt-toolchain-feedback.md` as examples. Parameterize project-specific ports, versions, image IDs, routes and contract digests rather than copying them into universal instructions. Retain the independent review as a useful counterexample to treating a green validation report as proof of completeness.
