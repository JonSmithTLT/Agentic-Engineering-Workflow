# Verification and committed-source evidence

From `web/`, run `npm run check:docs`, `node scripts/check-contract.mjs`, `npm run check:scenario`, and the Journal, Investigation, Evidence and Execution `scripts/*-artifact.mjs` checks with `node --experimental-strip-types`. Then run `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` and `npm run build:demo`. Regenerate accepted types only to verify drift; do not change the accepted contract.

The [pinned offline gate](pinned-web-builder.md) runs the locked install and these checks with networking disabled. CI's reusable `.github/workflows/web.yml` performs frontend checks, builds and compiled browser regressions; `.github/workflows/ci.yml` owns overall assurance. CI's locked network installation and the offline carrier are different reproduction paths.

UI changes require appropriate compiled browser suites. W01–W06 suites and `browser-http-demo.mjs` support `CHROMIUM_PATH`; the HTTP suite blocks service workers. Use pinned Playwright's staged Chromium and its OS libraries. `bash scripts/stage-browsers.sh` is a separate connected staging step. See each suite for its URL/port inputs rather than assuming a live backend. Documentation-only changes need link/catalog/protected-byte checks and affected script checks; they do not create new UI acceptance evidence.

## Freeze procedure

Commit the runtime correction first. From the repository root, supply its **full commit SHA** and the immutable builder image:

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/freeze-committed-build.sh <full-commit-sha>
```

The script creates a clean detached shared clone, builds that committed tree, checks cleanliness afterward and records source/tree and complete build manifests. Use the retained clone/builds for screenshots and browser checks. Never label working-tree output as evidence of a commit. Record runtime identities, commands, result files, screenshot hashes and unchanged source/build trees after checks.

`freeze-w05-evidence.sh` and `freeze-w06-evidence.sh` extend the procedure for their workflows. Read their required environment inputs before running them; W06 needs an explicitly frozen W05 baseline. A baseline measures the stated workflow, not an invented timing SLA. Independent product task review remains a separate gate; passing tests alone does not establish it.

Historical commands and results are under [milestone archives](../archive/README.md). Do not edit their frozen logs or manifests to match a later environment.
