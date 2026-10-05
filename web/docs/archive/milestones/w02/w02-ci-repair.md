# W02 PR browser CI repair — 2026-10-03

PR #28 at `a385d6ba4cb92f07618521a5b31c5374879fdd01` failed its W01
large-world browser check. W02's browser command was never reached. All other
CI lanes passed, but `assurance` failed because the web lane failed.

## Evidence and diagnosis

Run [37133679298](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/37133679298)
retained the W01 report and trace as `web-failure-evidence`. The trace records
a service-worker update rejection on the original replay page at 14.756 seconds,
then F6's new page receiving `/api/v1/project` 404 responses rather than mock
projections. Its rendered state is `LOAD ERROR`, not an oversized Work table.
The timeout is therefore a symptom of missing interception. The original suite
passed twice locally, including after rebuilding with the pinned carrier; the
precise upstream unregister/update race is not deterministically reproduced.

Independent W01 checks previously reused one browser context, accumulating
MSW registrations, replay clients, theme/storage and authored visibility state.
F6/F7 measurements opened further pages in that same context, without attaching
the suite's page-error/console/HTTP observers to them. That omission allowed
measurement-page errors to escape the report even when a table rendered.

## Repair

- Give each independent check a fresh context. Keep navigations, reloads,
  replay steps and lifecycle assertions within a check in the same context.
- Give each candidate/baseline F6/F7 measurement its own context and unchanged
  1440×1000 viewport. Record the same bounded-row and request measurements.
- Attach error/request/response observers to every page in those contexts,
  reject unexpected errors before declaring a check passed, and capture the
  actual failing measurement page's screenshot and trace before closing it.

The existing 30-second wait remains unchanged. No group is skipped, retries are
not added, and no new error suppression is introduced. Runtime application code,
contract 0.1.2, dependencies, CI workflows and Engine sources are unchanged.
This follows [Playwright's test-isolation model](https://playwright.dev/docs/browser-contexts).

## Local validation

See [the recorded result](w02-ci-repair-evidence/result.json). The exact original
carrier supplies Node 22.22.2/npm 10.9.7; no image rebuild or dependency update.

- Network-disabled, empty-module offline gate: accepted contract and generated
  artifacts, typecheck, lint, 117 tests in 14 files, both builds and production
  mock exclusion passed.
- Compiled W01: all 16 groups passed using both the existing Node24 launcher and
  the exact Node22 binary extracted from the original carrier.
- Compiled W02: all 10 groups passed using both runtimes, including the previously
  accepted hot-parent navigation regression.
- Controlled negative baseline: render a bounded table while throwing
  `measurement-page-regression`. The original harness incorrectly passes;
  the repair fails and records the exception plus the baseline F6 screenshot
  and trace. This proves the observation repair, not the exact upstream race.
- Six Git-based CI change-detector probes are run separately from the carrier.

Ignored working evidence lives under `web/output/ci-failure-37133679298`,
`playwright-ci-repair-node22-w01`, `playwright-ci-repair-node22-w02`,
`ci-repair-observation`, and `ci-repair-offline-gate.log`. The original W02
review/evidence packets remain historical records.

Green checks for the pushed PR head remain the acceptance gate. Live backend
integration is not claimed, and merging remains the operator's action.

## Shared execution setup

All browser scripts and `measure-w02.mjs` now accept `CHROMIUM_PATH`. It takes
precedence over the existing staged Linux executable default. W01 also retains
`PLAYWRIGHT_BROWSER_EXECUTABLE` below `CHROMIUM_PATH` in precedence. An invalid
explicit path fails normally; there is no silent fallback to another browser.

For example, from PowerShell with a separate Windows Node/npm installation:

```powershell
$env:CHROMIUM_PATH = 'C:\path\to\chrome.exe'
node scripts/browser-w02.mjs
```

This changes executable selection only. A configurable live-server/session
target remains deferred to F20.6 after F20.3 establishes the cookie interface.

Use Ubuntu WSL for this checkout's Linux Git pointer, dependency links and
Chromium. Windows Git cannot interpret its `/mnt/c/...` worktree pointer.

The existing `/home/jon/.local/bin/node` launcher supplies staged browser
libraries through `LD_LIBRARY_PATH`; direct Chromium invocation without that
environment misleadingly reports missing `libnspr4.so`. A real Playwright
launch passed. The original Snap Docker image store contains the pinned carrier,
while Docker Desktop's separate store does not. Use `/snap/bin/docker` explicitly
and wait for the Ubuntu service to be ready. Sandbox access restrictions are
separate from login/tool availability; Windows and WSL GitHub logins both work
with appropriate execution permissions.

From the repository root in Ubuntu WSL, with that Docker service ready:

```bash
PATH=/snap/bin:$PATH SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh
```

This produces `web/artifacts/offline-gate/dist` and `dist-demo`. It does not
establish live-server acceptance. Native Windows Node22/npm and Windows Chromium
would be a separate installation; `CHROMIUM_PATH` now supports its executable
selection. The fixture-server launcher still needs a separate live-server mode.

## Follow-up CI failure on the merged head

The web lane passed on repair commit `1075f58`, including all 26 browser groups.
Subsequent main-line merges superseded that run before assurance finished.
Run [37138201933](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/37138201933)
on `927e941` again passed all W01 groups, then caught an unexpected Overview 404
in W02's malformed-ID check. The trace shows consecutive deep-link loads only
about 220 ms apart; the presentation guard appeared before the shared Overview
bootstrap completed. The next navigation deactivated the demo worker while
that unrelated common read was still outstanding.

The guarded deep-link cases now wait for F1's supplied `HEALTHY` header value,
which appears only after the common Overview read completes, before replacing
the document. The malformed/historical guards still issue no Work reads; the
valid opaque ID still requests its accepted Work lookup and returns the one
explicitly allowed 404. No sleep, retry, timeout increase or error suppression
is added. W02 also checks unexpected errors/responses before declaring each
group passed. The new failure artifact remains in
`web/output/ci-failure-37138201933`.

Final local validation is recorded in
[the follow-up result](w02-ci-repair-evidence/final-result.json): all 16 W01 and
10 W02 groups pass with exact Node22 and a `CHROMIUM_PATH` wrapper containing
spaces. Both launches record use of the wrapper, and W01 overrides a deliberately
invalid legacy path. An invalid explicit `CHROMIUM_PATH` fails without fallback.
All affected browser scripts pass lint; the offline gate again passes 117 tests
and both builds. The latest pushed head's CI remains the merge prerequisite.
