# W01 / optional-tools fixing-diff response

Prepared 2026-10-03. **All three findings are fixed and retested; main-line fixing-diff verification remains pending.**

Review return: Claude's [W01 AMEND (minor)](w01-review-main-line.md) and
[optional tools ACCEPT with OT-1](optional-tools-review-main-line.md), both dated
2026-10-03. These were static reviews; execution results below are frontend
implementer evidence, not independently rerun reviewer evidence.

Frozen fixing source: **`ad9ed216238f7e3265a4ffb225b4eaef921a6702`**,
branch `feat/aew-dashboard-w01`, compared against packet commit `c1022e8`
(source reviewed at `f6c87d3`). The following documentation commit contains only
review returns, dispositions and evidence. Original optional branch `7e13f34`
and accepted core branch were preserved; OT-1 lands on W01 as the reviewer allowed.

## Finding dispositions

| Finding | Fix | Focused evidence |
|---|---|---|
| W01-1, Medium | Replace `rg` with `grep -Eq`. Only matcher exit 1 means no changes; all other matcher errors abort. Diff errors abort under `set -e`. No false skip is emitted on error. | Actual inline workflow script runs in disposable Git repositories; missing ripgrep still detects web/contract/workflow changes; matcher exits 2/127 and invalid revisions fail with no skip output. |
| W01-2, Low | PR/merge-group detection uses `base...head`; push retains direct before/head comparison. Both use `--no-renames`, preserving the old sensitive path when a file moves outside `web/`. | A Python-only PR behind web changes on main skips; the push counterpart and a move out of web trigger checks. |
| OT-1, Low | Change the lifecycle listener from `beforeunload` to capture-phase `pagehide`; retain cancellation/detachment and persisted `pageshow` reattachment/refetch. | Compiled production canceled-departure focus remains enabled; pagehide suspends focus refresh and persisted pageshow restores it in production and demo. Ordinary visibility/polling and graph navigation/reload still pass. |

`--no-renames` is a small detection tightening found by the requested scratch-repo
probes: rename collapsing can report only the destination path and miss a removed
web path. It introduces no API or frontend semantic change.

Stable CI job IDs, checksum source `web/docs/c0-approval.json`, shared YAML path,
Node/npm pins, security permissions and owner-controlled assurance/CodeQL boundary
remain unchanged. The checks job now runs the six detector probes using Node's
built-in test runner. No package was added.

## Verification scope

[Result/provenance](w01-review-fixes-evidence/result.json),
[offline log](w01-review-fixes-evidence/offline-gate.log),
[detector probes](w01-review-fixes-evidence/ci-paths.log),
[frozen detector negative control](w01-review-fixes-evidence/ci-negative-control.log),
[compiled-browser log](w01-review-fixes-evidence/browser.log),
[browser JSON](w01-review-fixes-evidence/browser-report.json), and
[static manifest](w01-review-fixes-evidence/static-manifest.json) are retained.

- **Offline PASS:** immutable Linux/amd64 carrier, networking disabled, absent
  modules, 395-package install, generated artifacts, accepted contract checksum,
  typecheck, lint, **101 tests**, normal/demo builds and production exclusion.
  Node 22.22.2/npm 10.9.7; same carrier/cache/browser identities as W01.
- **Detector PASS: six probes**, executed with host Node 24.21.0/Git 2.34.1.
  They extract and execute the actual workflow block, not a copied detector.
  The standard GitHub lane runs these too; GitHub itself remains unexecuted locally.
- **Frozen negative control:** the same probes against `c1022e8`'s workflow
  produce **four expected failures and two passes**. Missing ripgrep, behind-main
  PR comparison, rename/direct push handling and matcher errors are independently
  exercised; setup errors do not count as reproduced findings.
- **Compiled browser PASS: 16 groups**, pinned Playwright 1.59.1/Chromium 1217
  under the proposed CSP, including the previous 15 groups plus lifecycle checks.
  Deliberate scenario HTTP failures are explicit; no unexpected console, page,
  CSP, external-request or API-write failures are accepted.

Lifecycle checks dispatch controlled browser events. Canceled departure is tested
in normal production using the synthetic same-origin API and blocked service workers.
Demo MSW has its own beforeunload behavior, so a synthetic canceled departure there
would deactivate the demo worker; this is not used as a production lifecycle probe.
Both builds exercise synthetic pagehide/persisted-pageshow and subsequent focus.
This does **not** claim actual Firefox back-forward-cache eligibility or real
OS navigation/background-tab integration. Existing compiled graph navigation and
reload checks exercise real navigation separately. Earlier failed harness-iteration
traces remain under ignored `web/output/playwright-w01-review-failed-iteration/`.

The SPT carrier intentionally has no Git, observed when the new scratch-repository
probe was first placed in its application unit suite. Probes were moved to the
host/standard-runner CI lane; the immutable offline application gate remains unchanged.
See [SPT feedback](spt-toolchain-feedback.md), SPT-UI-010. This is a tool prerequisite
observation, not a reason to rebuild the carrier. No Engine suite was invoked.

Accepted API 0.1.2 YAML, generated types, runtime schema and dependency lock are
byte-for-byte unchanged from the reviewed branch. No auth, engine, history schema,
assurance gate or CodeQL edits. No branches were pushed.

## Reproduce and verify the fixing diff

From the W01 repository root:

```bash
git diff c1022e8 ad9ed216238f7e3265a4ffb225b4eaef921a6702 -- .github/workflows/web.yml web/src/main.tsx web/scripts/ci-paths.test.mjs web/scripts/browser-w01.mjs

PATH=/tmp/aew-bin:$PATH \
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/offline-gate.sh
```

From `web/`, with Git available:

```bash
/home/jon/.local/bin/node --test scripts/ci-paths.test.mjs

git show c1022e8:.github/workflows/web.yml > artifacts/w01-before-review.yml
CI_PATHS_WORKFLOW=artifacts/w01-before-review.yml \
/home/jon/.local/bin/node --test scripts/ci-paths.test.mjs
# Negative control: expected exit 1, four assertion failures.

W01_DEMO_PORT=4201 W01_PRODUCTION_PORT=4202 \
W01_BROWSER_OUTPUT=output/playwright-w01-review-final \
/home/jon/.local/bin/node scripts/ci-browser.mjs
```

The local Node launcher supplies the staged browser-library environment. CI uses
its separately pinned Node 22 runner setup and installed browser prerequisites.
Static corrected builds remain in `web/artifacts/offline-gate/`; the review-fix
manifest distinguishes them from historical pre-review archives.

Main owner: check the fixing diff, then record the explicit disposition. W01
frontend acceptance remains pending that verification. Optional tools have the
reviewer's ACCEPT with the merge prerequisite addressed here. Backend question
ledger, F20 CI wiring and authenticated/live-system acceptance remain separate.
