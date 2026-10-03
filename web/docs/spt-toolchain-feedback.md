# SPT toolchain feedback

D0 prerequisite observations, 2026-10-02. This log retains resolved findings so tickets can distinguish evidence from suggestions. Image/lock/cache identities and exact evidence paths are in `builder-provenance.json` and `validation-d0.md`. Initial image ID was `sha256:1d330086f23c0795c60abadfd96f9120848f21e22178aa5e59da2541208d7b23`; its checksum problem led to a separately rebuilt final carrier. Both are Linux/amd64, Node 22.22.2, npm 10.9.7; Tailwind 4.2.4, Vite 8.0.10. Final validated carrier: `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`; fix commit `ae65ad0408536140a96335e8e76a6245a33ace4a`. SPT repair branch: `build/aew-dashboard-tailwind-cache`, based on `3bf796be69313638d9d0261dfeeba31d0d60e6a9` (`python-whl-1.2`, the existing frontend carrier baseline).

## SPT-UI-001 — Missing Tailwind Vite adapter

- Date/category/classification: 2026-10-02 / cache / demonstrated missing dependency and inspection finding.
- Identity: original SPT lock in the repair baseline; matching Tailwind 4.2.4 existed but `@tailwindcss/vite` and its closure did not. Final identities are in the provenance record.
- Expected: cached dependencies support Tailwind's official Vite integration. Observed: adapter unavailable in the lock/cache; plain React/Vite smoke did not test Tailwind compilation.
- Reproduction/evidence: inspect `requirements/frontend/package-lock.json` for `node_modules/@tailwindcss/vite`; compare with the baseline using `git show`. Run `FRONTEND_NODE_IMAGE=<image-id> bash examples/frontend-npm-smoke/run-frontend-npm-smoke.sh`.
- Impact/stage: blocking SPT prerequisite and AEW D0 Tailwind build.
- Workaround: none committed in AEW; a separate SPT dependency repair adds exact `@tailwindcss/vite@4.2.4`.
- Proposed improvement/acceptance: offline install succeeds; Vite loads the adapter and actual output CSS contains `.underline` and `text-decoration-line:underline`; existing import/build checks pass.
- Status/fix/retest: RESOLVED in the separate SPT repair. Offline smoke passed on the first repaired image; final carrier retest is recorded in the validation artifact. Official integration: https://tailwindcss.com/docs/installation/using-vite.

## SPT-UI-002 — Cache resolution discarded the lock baseline

- Date/category/classification: 2026-10-02 / script / inspection finding; broad re-resolution was a risk, not an independently reproduced historical failure.
- Identity: original fetch script at the SPT baseline; requirements used broad `*` ranges. Final lock identity is recorded in provenance.
- Expected: refresh adds the adapter using the committed lock as its resolution baseline. Observed: script copied only package.json to an empty temporary directory before resolving.
- Reproduction/evidence: inspect `data-bundles/fetch/fetch-frontend-npm-cache.sh`; baseline contains no copy of package-lock.json. Compare baseline/current `packages` records after refresh.
- Impact/stage: blocking predictable prerequisite provenance; unrelated upgrades would violate the agreed lock scope.
- Workaround: none in AEW. Fetch now seeds package-lock.json when present.
- Proposed improvement/acceptance: unchanged dependencies retain the same full lock records, no removals, only the new direct dependency and necessary closure. A Node base override allows a digest-pinned fetch/build.
- Status/fix/retest: RESOLVED. Comparison found 1,005 existing dependency records unchanged, 25 new adapter/closure records, no removals; only the root dependency declaration changed.

## SPT-UI-003 — WSL Docker command selected a nonworking stub

- Date/category/classification: 2026-10-02 / environment / demonstrated environment friction, not an image defect.
- Identity/platform: WSL Linux/amd64; PATH selected Docker Desktop's WSL stub. Windows client 29.8.1 reached Desktop engine 29.8.1; the WSL socket separately reached engine 29.8.0. Do not mix those image stores.
- Expected: `docker version` reaches the WSL daemon. Observed: PATH's `docker` reported WSL integration unavailable although `/var/run/docker.sock` existed. Recheck showed a Linux CLI could reach that socket.
- Reproduction/evidence: `command -v docker; docker version`; compare `/tmp/aew-docker-cli -H unix:///var/run/docker.sock version`. Commands and outputs were captured during D0 setup.
- Impact/stage: initially blocked container access, resolved before prerequisite validation. No VSCode/WSL restart and no interaction with the user's running AEW test.
- Workaround: temporary Linux Docker CLI in `/tmp/aew-bin/docker`, extracted from `docker:29-cli`; subsequent work uses that WSL daemon.
- Proposed improvement/acceptance: environment guidance checks client platform, socket access, daemon identity and image-store ownership; documents native CLI setup without requiring a workspace restart.
- Status/fix/retest: WORKAROUND VALIDATED / documentation ticket remains open. Native CLI 29.8.2 successfully built and ran Linux containers. Recheck environment before calling this a blocker on another machine.

## SPT-UI-004 — Playwright npm cache does not carry browser artifacts

- Date/category/classification: 2026-10-02 / documentation / inspection finding and demonstrated separate staging requirement.
- Identity: cached Playwright 1.59.1 declares Chromium 147.0.7727.15, revision 1217; initial global CLI browser was a different revision and was not used as acceptance evidence.
- Expected: a complete offline browser-validation procedure names package, browser binaries and runtime libraries separately. Observed: npm cache supplies packages; browser downloads/runtime libraries are separate.
- Reproduction/evidence: inspect `node_modules/playwright-core/browsers.json`; run `SPT_FRONTEND_IMAGE=<immutable-id> bash web/scripts/stage-browsers.sh` from the AEW repository. See `web/artifacts/browser-stage.log` and `web/artifacts/playwright/SHA256SUMS`.
- Impact/stage: browser checks require staging; does not block offline npm/build acceptance.
- Workaround: separate checksummed browser artifact with matching package version, plus existing user-local Linux runtime libraries. No browser payload added to the npm carrier.
- Proposed improvement/acceptance: SPT docs specify browser/package revision matching, archive/checksums, platform and OS-library prerequisites; a network-disabled browser can launch and exercise the compiled UI.
- Status/fix/retest: STAGING IMPLEMENTED in AEW `web/scripts/stage-browsers.sh`; reusable SPT documentation ticket remains open. Matched browser probe results are in `validation-d0.md`.

## SPT-UI-005 — Carrier cache verification invalidated a checksum

- Date/category/classification: 2026-10-02 / image and script / demonstrated failure.
- Identity: first repaired carrier `sha256:1d330086f23c0795c60abadfd96f9120848f21e22178aa5e59da2541208d7b23`; same lock and dependency versions as the final carrier.
- Expected: generated cache checksums verify after image construction. Observed: Dockerfile's `npm cache verify` updated `_cacache/_lastverified`; `sha256sum -c SHA256SUMS` reported that file FAILED. All other entries matched.
- Reproduction/evidence: `docker run --rm --network none <initial-image> sh -c 'cd /opt/spt-frontend; sha256sum -c SHA256SUMS'`; `SPT-dashboard-toolchain/artifacts/dashboard-prerequisite/offline-checksums.log`.
- Impact/stage: blocking immutable carrier validation, discovered before D0 acceptance.
- Workaround: none in AEW. SPT checksum generation excludes npm's mutable verification marker and log directory; actual cache contents, indices, package manifests and lock remain checksummed.
- Proposed improvement/acceptance: regenerated carrier passes all listed checksums after its cache-verification build step; offline Tailwind and AEW gate remain green.
- Status/fix/retest: RESOLVED in separate SPT prerequisite. Final checksum result is in `offline-checksums-final.log`; final image identity is recorded in provenance.

## SPT-UI-006 — Broad dependency smoke is slow on Windows bind mounts

- Date/category/classification: 2026-10-02 / environment / demonstrated friction and improvement suggestion.
- Identity/platform: repaired Linux carrier over `/mnt/c` Windows bind mounts, broad 976-installed-package SPT smoke versus AEW's 395-installed-package subset. Exact versions/identities are in provenance.
- Expected: repeated offline validation is practical. Observed: full SPT `npm ci` took about three minutes and import probes spent additional minutes reading the bind mount; smaller AEW install took about 59 seconds. These observations are not controlled performance benchmarks.
- Reproduction/evidence: broad `examples/frontend-npm-smoke/run-frontend-npm-smoke.sh` writes modules into a Windows-mounted output directory; compare AEW's `web/scripts/offline-gate.sh`, which uses ephemeral container storage for modules. Logs retain actual durations.
- Impact/stage: non-blocking D0 iteration cost.
- Workaround: AEW gate copies frontend source into the container, installs into ephemeral native storage, and exports only logs/build artifacts. Carrier/cache identity remains fixed.
- Proposed improvement/acceptance: offer an SPT smoke mode installing into container storage, preserving the full checks and exporting bounded evidence; measure both modes on the same host/image with cold/warm runs before claiming a speedup.
- Status/fix/retest: OPEN SPT improvement ticket; AEW gate implementation is present and independently validated.

## SPT-UI-007 — Connected fetch emitted untriaged audit findings

- Date/category/classification: 2026-10-02 / cache / observed tool output requiring triage; no exploit or frontend exposure was reproduced.
- Identity: lock `12c896ba7ef48d304c1a919bb67c68b84d7c7c570a2b9ac2f7064bd376946805`, npm 10.9.7, full SPT dependency pack after adapter resolution. Final carrier provenance is recorded separately.
- Expected: cache maintenance evidence distinguishes advisory output from application exposure. Observed: connected fetch reported 49 findings (1 low, 34 moderate, 13 high, 1 critical), without a retained structured advisory inventory. These counts describe that fetch's output, not a verified vulnerability assessment of AEW's smaller subset.
- Reproduction/evidence: `artifacts/frontend-npm-fetch/frontend-npm-fetch.log` in the SPT worktree. A separate connected `npm audit --json` against the exact lock can collect advisory identities; it was not run as part of the offline gate.
- Impact/stage: no demonstrated build failure; maintenance triage remains open. Do not resolve it with unrelated lock upgrades inside the narrowly scoped prerequisite.
- Workaround: AEW declares and installs only its consumed subset; this does not establish that every consumed dependency is advisory-free.
- Proposed improvement/acceptance: retain advisory JSON and registry/time identity, compare baseline with the repaired lock, identify affected runtime versus development dependencies in downstream subsets, and record dispositions or separate validated fixes for any applicable advisories.
- Status/fix/retest: OPEN / not triaged; no broad dependency changes or audit-fix operation performed.

## C0 amendment retest — 2026-10-02

- Identity/platform/versions: same final immutable Linux/amd64 carrier
  `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`,
  Node 22.22.2/npm 10.9.7, Vite 8.0.10, Tailwind/adapter 4.2.4. Lock/cache
  identities remain those in `builder-provenance.json`; no dependency repair
  or refresh was needed for the C0 amendment.
- SPT-UI-001/002/005: resolved status retained. The amended consumer installed
  offline from empty modules, regenerated OpenAPI types, typechecked, linted,
  passed 38 tests and compiled both actual Tailwind/Vite builds in the same
  carrier with networking disabled. Full-carrier checksum/import validation
  remains the original prerequisite evidence; it was not rerun or relabeled
  as current full-toolchain verification.
- SPT-UI-003: temporary native CLI access to the WSL daemon was revalidated by
  generation and full consumer gate. No workspace restart was required. The
  PATH-selected stub was not rechecked, so that original observation remains
  historical rather than a newly asserted current failure.
- SPT-UI-004: unchanged matched browser artifact launched and passed compiled
  browser checks. Staging was not repeated; browser revisions remain pinned.
- SPT-UI-006: ephemeral native-storage install reported 11 seconds in the
  first passing amendment iteration and 6 seconds in the final iteration. This is a run observation, not a controlled performance claim.
- SPT-UI-007: no connected audit or dependency changes were performed; advisory
  triage remains open. No new SPT build blocker was demonstrated.
- Reproduction/evidence: use the commands in `validation-c0-amend.md`; logs are
  `web/artifacts/c0-amend-offline-gate.log` and `c0-amend-browser.log`. The final
  candidate's generator/typecheck/lint/test/build/browser retests are PASS;
  main-line C0 approval remains pending independently of these tool results.

## SPT-UI-008 — Type generation does not prove OpenAPI operation validity

- Date/category/classification: 2026-10-02 / documentation and script /
  demonstrated validation gap, not a dependency-cache or image failure.
- Identity: unchanged final immutable carrier
  `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`,
  Linux/amd64, Node 22.22.2/npm 10.9.7, openapi-typescript 7.13.0. Lock/cache
  identities are retained in `builder-provenance.json`.
- Expected/observed: generation produces types from the proposal; comprehensive
  API-document validity needs a separate check. Version 0.1.1 had duplicated
  operation parameters yet generated successfully. Main-line R2-1 identified
  the invalid GET/HEAD lists. Existing response-schema tests did not check them.
- Reproduction/evidence: generate types from contract at `7b0177b` in the carrier;
  count `(name,in)` pairs for each operation on `/work`, `/evidence`, `/history`
  and `/history/{id}`. Retained review: `c0-review-main-line-0.1.1.md`.
- Impact/stage/workaround: blocked C0 acceptance, not SPT install/build. R2-1
  deduplicates both methods; focused conformance now tests uniqueness and a
  failing duplicate-parameter control. The amended offline gate passes.
- Proposed improvement/ticket acceptance: SPT guidance separates generator
  success from complete OpenAPI 3.1 validation; evaluate a cached specification
  validator with known-invalid duplicate-operation fixtures and a valid control.
  Preserve offline reproducibility and report the validator's exact scope.
- Status/fix/retest: FRONTEND BLOCKER RESOLVED by R2-1 in the 0.1.2 candidate;
  SPT documentation/validator improvement remains OPEN and non-blocking. No
  new package or SPT script change accompanies this narrowly scoped correction.

## C0 0.1.2 retest — 2026-10-02

Same immutable image, dependency/cache/lock and separately staged browser
identities; no repair or refresh needed. The offline consumer gate installed
395 packages from absent modules, regenerated types, typechecked, linted,
passed 45 tests and built production/demo with networking disabled. Native
storage installation reported 4 seconds in this run, not a controlled benchmark.
Resolved entries remain retained; Docker access used the validated native CLI
without a workspace restart. Full-carrier checksum/import acceptance remains
original prerequisite evidence and was not relabeled as a new full-toolchain
run. Browser and local evidence are recorded in `validation-c0-012.md`.

## D1 consumer retest — 2026-10-02

Same immutable carrier, cache, lockfile and separate browser artifacts; no new SPT repair or frontend dependency. Empty-module offline install, generated types, typecheck, lint, 51 tests and both builds passed. Compiled browser checks passed with the matched staged Chromium (18 checks). Docker access again worked using the native temporary CLI without restarting the workspace; the earlier PATH-stub observation is retained as environment friction rather than a present build blocker. Browser OS libraries remain a separate environment prerequisite. Full carrier acceptance is the prerequisite evidence, not a newly repeated full-toolchain run. See `validation-d1.md` for commands and scope. The frontend bundle-size advisory is documented there as a frontend optimization candidate, not a demonstrated SPT failure. Resolved findings and ticket-ready non-blocking entries remain retained.

## SPT-UI-009 — Offline package execution lacks registry metadata

- Stable ID/date/category/classification: SPT-UI-009 / 2026-10-02 / cache / demonstrated friction; proposed documentation or cache improvement.
- Identity/platform: immutable carrier `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, Linux/amd64, Node 22.22.2/npm 10.9.7, Prettier 3.8.3. AEW lock `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`; cache manifest `d6356958ad38cd52e4383f869a9a05b20b44fa98be22ce0240bd3b182521980f`; cache checksum identity is retained in `builder-provenance.json`.
- Expected/observed: a pinned formatter present in the cache can be invoked offline. `npm exec --offline --yes --package=prettier@3.8.3 -- prettier --version` exits 1 with ENOTCACHED for the registry package metadata, despite the exact package tarball being cached.
- Reproduction: `docker run --rm --network none <immutable-image> npm exec --offline --yes --package=prettier@3.8.3 -- prettier --version`. Evidence: `artifacts/spt-ui-009-metadata-failure.log`. The failure repeats in a new disposable container.
- Impact/stage: non-blocking D2–D4 formatting friction; frontend install/typecheck/lint/tests/build remain green. No SPT repair or new frontend dependency was necessary.
- Workaround/retest: invoke `npm exec --offline --yes --package=https://registry.npmjs.org/prettier/-/prettier-3.8.3.tgz -- prettier --write <files>` in the same carrier with networking disabled. PASS; `artifacts/core-formatter-retest.log` and `artifacts/core-format-final.log`. The URL selects the cached artifact; it does not enable networking.
- Proposed improvement/ticket acceptance: document the supported exact-artifact execution pattern and add an offline one-off-tool smoke test; alternatively stage sufficient metadata for pinned-name execution without weakening lock preservation. Reproduction must either pass by supported command or produce an actionable explanation. No broad cache refresh is required by this frontend task.
- Status/linked fix: OPEN SPT improvement; verified downstream invocation workaround, no prerequisite source fix. Retest result retained above.

## Core consumer retest — 2026-10-02

Unchanged immutable image, lock and browser identities. The final offline gate installs 395 packages from absent modules, verifies generated types, typechecks, lints, passes 61 tests and builds normal production/demo with networking disabled. Compiled browser validation covers the original D1 lane plus new core routes; current evidence and exact scope are in `validation-core.md`. No SPT image was rebuilt, no dependency was added, and no new full-carrier acceptance is claimed. Resolved entries remain retained and open improvements remain ticket-ready.

## FR-1 / FR-2 consumer retest — 2026-10-02

Same immutable carrier, cache, lock and separate browser identities. Final offline gate: absent modules, 395-package offline install, type generation/compare, typecheck, lint, 73 tests and normal/demo builds PASS. Compiled browser lanes: 18+12+4 checks PASS. Frozen pre-fix negative control: five expected failures, not a toolchain failure. See `frontend-core-review-fix-response.md` and retained `artifacts/fr-*` logs. SPT-UI-009's exact cached-tarball formatter workaround was reused with networking disabled. No SPT rebuild, dependency addition or full-carrier re-acceptance was needed.

Environmental observations: native Docker access and staged browser access worked on retest without restarting the workspace. One automatic-approval usage-limit rejection prevented a prior probe from executing; it cleared on continuation and is not evidence of an SPT image defect. A disposable `/tmp` source bind appeared empty to the Docker daemon; staging the same frozen test source under ignored `web/artifacts/` resolved it. Keep these as local environment observations, as an observed setup issue without a retained standalone setup log, rather than inventing an image/cache blocker. All resolved entries remain retained; existing ticket-ready improvements remain non-blocking.
