# Frontend CI draft and F20 integration handoff

Operator relayed the main AEW owner's CI instructions during W01. The authorized
addition is `.github/workflows/web.yml`; `ci.yml`, `nightly.yml` and CodeQL remain
unchanged for the main owner to integrate/review in the F20 frontend merge PR.

Stable job IDs are `changes`, `checks`, and `result`; display names are `web changes`,
`web checks`, and `web result`. Treat renames as integration-interface changes.
The checksum expected value is read from `web/docs/c0-approval.json`, never embedded
in the workflow.

The workflow runs informationally on PRs, main/frontend pushes, merge groups and
manual dispatch. It is also callable as a reusable workflow. Its internal changes
job checks `web/**`, the shared contract, and its own workflow. Python-only changes
skip web checks successfully; failed change detection, failed checks and canceled
checks fail the result. It uses Linux, Node 22.22.2/npm 10.9.7, locked installation,
contract digest/type/schema consistency, typecheck/lint/tests, production exclusion,
and compiled browser checks. No Python installation, secrets or elevated token
permissions. Screenshots/traces are uploaded on failure only.

Main owner integration responsibilities:

1. Add a reusable-workflow call in `ci.yml` (`uses: ./.github/workflows/web.yml`)
   and include that caller job in `assurance.needs` and its success checks. Keep
   **assurance as the sole required check**; do not require this standalone workflow.
   The workflow's internal result accepts checks skipped only for unchanged paths.
   If moving changes detection into ci.yml instead, preserve the explicit successful
   skip and failed/canceled distinctions in assurance.
2. Keep Python lanes running when the shared contract changes. Do not make Python
   tests depend on Node. Current Python lanes already run on every PR.
3. Add `javascript-typescript` to the existing CodeQL language matrix in the same
   integration PR. No CodeQL permissions are needed in web jobs.
4. Coordinate required-check settings and review on the frozen merge PR. Standalone
   frontend runs before integration are informational, not a completed merge gate.
5. Once the server exists, add Python response conformance against the same accepted
   YAML. Move browser checks to nightly only after observed runtime/flakiness warrants
   it; keep contract/unit/build checks on applicable PRs.

The pinned SPT, empty-modules, network-disabled gate remains separate local offline
reproducibility evidence. Standard-runner npm installation and browser provisioning
are not claimed to be airgap validation. This draft has local parser/script checks and a passing 15-group compiled-browser
run through its owned-server launcher;
GitHub execution is unverified until the operator publishes a branch/PR.

Primary references checked for the draft: [setup-node](https://github.com/actions/setup-node),
[Playwright CI](https://playwright.dev/docs/ci),
[upload-artifact](https://github.com/actions/upload-artifact).
