# Authenticated live production browser checks

The web-owned `scripts/browser-live.mjs` runner accepts an existing loopback server and a private cookie file. It starts no server, launches no fixture adapter, mocks no responses and uses no preview contracts. Run it from `web/` with the locked Playwright installation and Node 22:

```bash
DASHBOARD_BASE_URL=http://127.0.0.1:4280 \
DASHBOARD_SESSION_FILE=/private/scratch/dashboard-session.json \
DASHBOARD_LIVE_OUTPUT=output/live/browser-live.json \
CHROMIUM_PATH=/staged/chromium/chrome \
node --experimental-strip-types scripts/browser-live.mjs
```

`CHROMIUM_PATH` is optional; the default is the locked Playwright Chromium under `artifacts/playwright/browsers/`. Use a separate checkout of the runner tooling; do not modify or rebuild the approved frozen packaging checkout to add these scripts. Record both identities in F20.6. The target must be a root HTTP origin on `127.0.0.1`, with no credential, path, query or fragment. No one-time `/session/` URL is accepted as the target.

## Private cookie-file interface, version 1

The main-line driver exchanges the F20.3 one-time URL and writes the resulting `aew_session` cookie into a private scratch file. The JSON has exactly these keys (placeholders below are not usable credentials):

```json
{
  "version": 1,
  "origin": "http://127.0.0.1:4280",
  "cookie": {
    "name": "aew_session",
    "value": "aew1.<id>.<secret>"
  }
}
```

The file origin must exactly match the normalized target origin, including port. Extra cookies, local-storage values and extra keys are refused. On POSIX the file must belong to the current user and have no group/other access (use 0600); symlinks and non-files are refused, and reads are bounded to 4 KiB. On Windows the driver must restrict the file ACL to the operator; the runner does not claim to audit Windows ACLs. Keep the cookie in memory/private scratch, never command arguments, environment values, committed files or evidence. Delete the scratch file after the run. The opaque cookie authenticates the session; the file itself grants no Engine mutation authority.

## Checks and evidence boundary

Desktop and phone runs verify unauthenticated API refusal, authenticated accepted-project bootstrap, schema/project binding of observed successful UI responses, accepted core navigation using Enter, capability-unavailable presentation, first-page record/detail navigation when supplied, Work copy/reopen, both Appearance modes, document overflow, session-required UI after clearing the test context's cookie, and absence of demo UI/workers. No source IDs are inferred from prose or fictional fixtures. Empty collections are recorded as unexercised record-selection coverage; this runner does not require every real project to contain every record kind.

All traffic is read-only and same-origin. A guard aborts mutations, foreign requests, session-exchange URLs, preview endpoints and fixture queries; any such attempt fails the check. Response bodies are validated in memory and discarded. No screenshots, traces, HAR, request headers, raw browser errors, cookie paths or response bodies are written. A failed run returns nonzero and a fixed stage name; successful output lists exactly the checks performed and omitted coverage.

This is the initial live UI gate, not the whole F20.6 security acceptance. The main line must record the server commit, actual packaged `BUILD.json`, served asset hashes, accepted digest, platforms and results. It must separately exercise expiry/replacement, conditional requests, Host/Origin/CSP negative controls, validator/scope isolation and authorized hostile-content datasets. A PASS here cannot substitute for those checks or independently prove the package's source commit. Use the [approved F20.5 build](../reference/f20-production-baseline.md), not the newest frontend by default; the runner's tooling commit is separately recorded.

## Runner regression, not live acceptance

```bash
node --test scripts/live-inputs.test.mjs
node --experimental-strip-types scripts/verify-live-runner.mjs
```

The second command deliberately owns a **test-only authenticated fixture adapter** serving compiled production assets. It checks desktop/phone success, authentication bypass rejection, malformed-response rejection and credential-free diagnostics. CI runs it after the production build and pinned Chromium installation. These results verify runner behavior, never an Engine session or packaged-server acceptance. The ordinary W01–W06 fixture regressions remain separate.
