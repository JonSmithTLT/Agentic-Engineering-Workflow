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

## Optional Work graph consumer retest — 2026-10-02

Same immutable carrier, cache, lock and staged browser identities; no SPT repair or new dependency. Offline gate: absent modules, 395-package offline install, generated-type consistency, typecheck, lint, 78 tests and production/demo builds PASS. Seven compiled graph browser check groups PASS, including CSSOM/SVG under CSP, bounded pagination, keyboard/pointer pan and responsive layouts. See `validation-work-graph.md` for commands, identities and precise scope. Exact cached-tarball formatter invocation from SPT-UI-009 worked again with networking disabled. Docker and separately staged Chromium worked without restarting the workspace. These are downstream consumer checks; original full-carrier acceptance remains prerequisite evidence. No new demonstrated SPT blocker; resolved entries and remaining ticket-ready suggestions are retained.

## Optional developer tools consumer retest — 2026-10-02

Unchanged immutable image, cache, lock and staged browser identities. Offline gate installs 395 packages from absent modules, compares generated types, typechecks, lints, passes 85 tests and builds production/demo with networking disabled. Optional compiled browser checks are recorded in `optional-developer-tools.md`; normal production is separately probed with synthetic same-origin responses. SPT-UI-009’s exact cached formatter invocation remains effective. No SPT rebuild or new dependency, no new full-carrier acceptance claim. MSW’s blocked-storage initialization behavior is demo-library friction documented in the optional packet, not a demonstrated SPT image/cache defect. Existing resolved and ticket-ready entries remain retained.

## Header/sidebar polish consumer retest — 2026-10-02

Same immutable carrier/cache/lock and separately staged Chromium; no toolchain fix required. Offline gate and 85 tests pass; four focused compiled layout checks pass. Evidence and exact scope are recorded in `optional-developer-tools.md`. Cached tools remain sufficient for this CSS change; no new SPT blocker or full-carrier acceptance claim.

## W01 consumer retest — 2026-10-03

Same immutable carrier, cache, frontend lock and separately staged Playwright
1.59.1/Chromium 1217; no dependencies or image repair. Empty-modules offline gate
passes installation, API/lab generated-artifact checks, typecheck, lint, 101 tests
and separate normal/demo builds. Fifteen compiled-browser groups and the local CI
launcher pass. See [frozen W01 packet](w01-review-packet.md) and its retained logs.
These are downstream frontend checks; full-carrier acceptance remains the original
prerequisite evidence.

SPT-UI-003/004 environment retest: native Docker access works using the temporary
CLI with the required sandbox socket permission, without a workspace restart.
The user-local Node launcher sets LD_LIBRARY_PATH for separately staged libnspr4,
libnss3 and libasound2. Direct archive-Node invocation without that environment
failed to launch Chromium (missing libnspr4); using the launcher passes. This is
a separate browser-runtime prerequisite, not an image/cache defect or present
build blocker. Keep the existing browser-artifact/preflight documentation proposal
open: its acceptance should show the pinned executable plus required library
resolution before browser verification, with actionable missing-library output.
No source fix or SPT rebuild is linked to this retest.

The standard-runner web.yml draft is separate from local offline reproducibility.
No GitHub execution or real API acceptance is claimed. The existing bundle-size
advisory remains frontend optimization feedback. Resolved entries are retained;
nonblocking SPT improvements stay ticket-ready and do not delay independent review.

## SPT-UI-010 — Repository CI probes require Git outside the Node carrier

- Stable ID/date/category/classification: SPT-UI-010 / 2026-10-03 / documentation / demonstrated environment prerequisite; documentation improvement.
- Identity/platform: unchanged Linux/amd64 carrier `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, Node 22.22.2/npm 10.9.7. Frontend lock `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`; cache manifest/checksum identities remain in builder-provenance.json.
- Expected/observed: repository change-detection regression probes need Git to create scratch history. Git is absent from the Node carrier; placing the probes in the offline application suite failed with `spawnSync git ENOENT`. This does not contradict the carrier's frontend install/build scope.
- Reproduction/evidence: `docker run --rm --network none <immutable-image> sh -c 'command -v git'` returns no executable; initial probe setup stack/log retained in `w01-review-fixes-evidence/git-prerequisite.log`. No package/cache resolution failure occurred.
- Impact/stage/workaround: initial review-fix test setup blocker, resolved without an image change. Repository CI probes run separately on the host and standard GitHub runner; application unit tests/offline consumption do not depend on Git.
- Proposed improvement/ticket acceptance: document the carrier's executable prerequisites and distinguish application build/test consumption from repository/CI verification. Consumers needing Git receive an actionable prerequisite check or explicit separate lane; do not add Git to every carrier without a stated scope need.
- Status/linked fix/retest: downstream blocker RESOLVED in `ad9ed21` by separating `scripts/ci-paths.test.mjs`; six host probes PASS and offline 101-test gate PASS. SPT documentation improvement OPEN and nonblocking; no SPT source fix or rebuild.

## W01 review-fix consumer retest — 2026-10-03

Same carrier/cache/lock/browser identities; absent modules and network-disabled
application gate pass generated artifacts, typecheck/lint, 101 tests and both
builds. Six separate Git-based CI probes pass; frozen pre-fix detector yields
four expected failures. Compiled-browser lane passes 16 groups. Exact cached
formatter invocation from SPT-UI-009 still works. No new image/cache failure or
full-carrier acceptance claim. Main-line fix verification and live integration
remain pending; resolved entries are retained.

## W01 frontend acceptance — 2026-10-03

Claude verified the fixing diff and recorded ACCEPT at `ad9ed21`; W01 is accepted
as a frontend foundation. This was static independent review, not an independent
rerun of the 101 tests, six detector probes or 16 browser groups. Historical
validation records retain their at-run dispositions. Same toolchain identities;
no new test/build run or SPT change accompanies this acceptance record. Open SPT
documentation improvements remain nonblocking; F20 CI wiring, backend questions
and live-system acceptance remain separate. See `w01-acceptance.json`.

## SPT-UI-011 — Local sandbox permissions are distinct from carrier/browser readiness

- Stable ID/date/category/classification: SPT-UI-011 / 2026-10-03 / environment / demonstrated execution-environment friction; documentation suggestion, not an SPT image defect.
- Identities: Linux/amd64 carrier `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, Node22.22.2/npm10.9.7; frontend lock `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`; cache manifest `d6356958ad38cd52e4383f869a9a05b20b44fa98be22ce0240bd3b182521980f`, checksums `9b6b6030d1958c80ec6b284e03a46cc3b050cde0ad008f5157c13520b0bf3246`. Browser Playwright1.59.1/Chromium1217, host launcher Node24.21.0 with staged libraries.
- Expected/observed: existing artifacts are installed, but sandbox Docker socket access reports permission denied; Chromium reports Crashpad `setsockopt: Operation not permitted` and exits SIGTRAP; a host Git probe can fail `spawnSync git EPERM`. The same commands pass under authorized execution permissions. This is distinct from missing browser binaries, missing libraries or an absent image.
- Reproduce: `docker image inspect <immutable-ID>`; `node scripts/measure-w02.mjs`; `node --test scripts/ci-paths.test.mjs` from web/. Permission profile affects reproduction; initial failures are recorded in session tool output, not a retained standalone failure log. Current successful checks are in `w02-evidence/`.
- Impact/stage/workaround: initial local validation launch blocker, resolved using the available authorized execution path. Offline container networking remains disabled. No image/cache/package repair, permission broadening of the Docker socket, or browser package upgrade was needed.
- Proposed improvement/ticket acceptance: document separate checks for artifact existence, OS libraries, daemon/socket access and sandbox process permissions; preserve the exact failure and permission profile; report environment restriction rather than reinstalling tools. A runbook should correctly triage all four and run a permission-authorized retest without weakening socket permissions.
- Status/fix/retest: RESOLVED for this session; documentation suggestion OPEN, no SPT fix link. Immutable image inspect, empty-module offline gate, six Git detector probes and 25 compiled-browser groups pass. Keep SPT-UI-003/004/009/010 and all resolved observations retained.

## W02 consumer retest — 2026-10-03

Same immutable carrier/cache/lock and separately staged browser; no dependencies or SPT image repair. Offline 395-package install, accepted API and generated-artifact checks, typecheck/lint, **116 tests**, normal/demo builds and production mock exclusion pass. Six host/CI Git probes and 25 compiled-browser groups pass. Source freeze `0e64b31`; packet `w02-review-packet.md`. Exact cached formatter procedure remains effective. Host tests directly on the Windows-mounted dependency tree encountered worker startup timeouts; that failed attempt is not counted as validation. The required Node22 Linux-container gate passes; moving implementation validation into that carrier avoids treating host filesystem timing as an application failure. No new carrier/cache blocker or full-toolchain acceptance claim.

Main PR #26 integration is consumed; W02's web.yml change adds its compiled browser lane while keeping the merged gate/triggers. GitHub execution and live AEW integration are not claimed. The production chunk-size advisory predates W02; measured artifact sizes and bounded F6/F7 samples are retained for later optimization, with no fabricated performance target. Independent frontend review remains pending.

## W02-1 consumer retest — 2026-10-03

Source fix `7a18fa3` consumes the same immutable Node22 carrier, cache, lock and staged Chromium1217. Empty-module network-disabled gate passes 117 tests, artifact checks, typecheck/lint and both builds; compiled browser reports cover 10 W02 and 16 W01 groups. No new SPT repair or dependencies. The first browser regression capture reset the inspector graph before its link click; moving capture after navigation passes, with failed trace retained under W02 review-fix evidence. This is a browser harness observation, not a carrier defect. Lead fixing-diff review and green PR CI remain pending; live integration is not claimed.
