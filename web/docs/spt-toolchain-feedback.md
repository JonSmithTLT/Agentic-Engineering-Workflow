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
