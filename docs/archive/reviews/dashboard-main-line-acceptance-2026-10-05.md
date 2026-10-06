# Dashboard main-line integrated acceptance (F20.6), 2026-10-05

- **Status:** **server half ACCEPTED; browser gate PENDING.** The browser gate is the web side's authenticated live runner against this server. F20.6 stays open in the register until it is run and recorded here.
- **What this records:** the integrated product, meaning the Python server, its session and its packaged frontend build, exercised against authenticated live state. It is recorded separately from the frontend's own fixture acceptance (`web/docs/`), as register F20 requires. The design note's [§5.5](../../design/proposals/dashboard-main-line-api-design-v0.1.md) sets the scope.
- **Server:** the main line's `aew.dashboard` at the F20.6 commit of branch `impl/f20-6-acceptance`, whose tree holds the following:
  - F20.2 (PR #67);
  - F20.3 (PR #71);
  - F20.4 (PR #87, merged);
  - F20.5 (PR #90, at `759b9cc`).

  The F20.6 PR names its own commit.
- **Contract:** 0.1.2, SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`, the digest `web/docs/c0-approval.json` accepts.

## The static build (`src/aew/dashboard/static/BUILD.json`)

| Identity | Value |
|---|---|
| Frontend source commit | `4f0a710fa4831eefda248dd43cc2e144d1010189` (the [agreed baseline](../../../web/docs/reference/f20-production-baseline.md)) |
| Repository tree / `web/` tree | `5b75034f65c3aed78ae1eb086024defe284adaa5` / `348aa372634c88b261e972c363a3ffaf9078b55c` |
| Builder | `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, Node v22.22.2, npm 10.9.7, `web/scripts/offline-gate.sh` from a clean detached checkout (the whole gate passed: 167 frontend tests, the production-exclusion check) |
| `web/package.json` / `web/package-lock.json` | `a131d0a6…2382` / `3cab231b…b0b2` |
| Built | 2026-10-06T02:24:21Z |
| `index.html` | `93e488747a1550df7d04164083938407efd975e2e7e50de0a52161aced25511b` |
| `favicon.svg` | `4b36423b9612fe050b423cc3f1d30c20168a5dfdad3957da144c7f1306e78c08` |
| `assets/index-JdX3sJkV.js` | `80d0ef8fd2a34ddfda2d9c503ce76c9670b8373eeebd7f20074b9fce1b58e221` |
| `assets/index-DWAoQmdF.css` | `943bfd7e426f03b1b1ce65c0fbac788d0aa334855d49a58479810b6eed53adcd` |

The served bytes are these files. `test_the_frontend_is_served_from_the_package_with_its_types` and the acceptance walk compare every response with the file, and `test_build_json_binds_every_file_by_its_hash` checks every hash against `BUILD.json`.

## Server-side acceptance

`tests/integration/test_dashboard_acceptance.py` runs against the acceptance project (`tests/helpers/dashboard_world.py`). The project holds an Epic and its plan decision, an integrated (archived) Ticket, an open Ticket, a Ticket whose title is hostile content, and an audit.

| Check | How | Result |
|---|---|---|
| The product end to end through one session | **Session:** no session gives `401`. The one-time URL is followed as an address-bar navigation (`303`, `HttpOnly`, `SameSite=Strict` cookie). **Frontend:** the packaged `index.html` and its bundle load byte-identical, with their cache policy. Nine deep links reload to the SPA fallback. **Projections:** 18 reads in the pages' order (the bootstrap `/project` first). Each is validated against the contract, carries R21's headers, and is replayed with `If-None-Match` to a `304` carrying the same validator. `/attention` is the capability's `403`. | Pass (Windows, Linux) |
| The real CLI | `aew --print-credential dashboard serve --port 0` runs at a pseudo-terminal and the typed-back code is answered. The same walk then runs over the URL it prints. `SIGINT` ends the command, after which nothing listens and the endpoint files are gone. | Pass on Linux (`serial`; skipped on Windows, where a console would appear on the desktop) |
| Session expiry | With an injected clock past the session's hours, the read is `401 SESSION_EXPIRED` and the dead cookie is cleared. A conditional request is `401` too, never a `304`. The page still loads to show the session-required state. | Pass |
| Server stop | Stopping the server ends every session. A new server on the same project answers the old cookie with `401 SESSION_REQUIRED`: sessions are process-local and never durable. | Pass |
| Scope and validator isolation | A second project's server shows only its own records. One server's cookie is `401` on the other, and one server's validator never confirms the other's representation. Within a server the validator is bound to path, project and query (F20.4's suite). | Pass |
| Hostile content | Markup, a script breakout, an event handler, a bidi override and an ANSI escape in a unit's title come back as the exact JSON string under `application/json`, `nosniff` and the CSP. No HTML response ever carries project text: every HTML response is the build, unchanged. | Pass (server side; display is the browser gate's) |
| Production exclusion | The builder gate's `check-production.mjs` passed. `test_the_build_contains_no_demo_material` applies that script's own patterns to the committed build. `/mockServiceWorker.js` and `BUILD.json` are `404`. | Pass |
| The browser handoff tools | `tools/dashboard/session_file.py` exchanges a one-time URL, read from stdin, for the runner's session file: the agreed format, owner-only (0600, or an ACL granting only the user with nothing inherited), the credential never printed, spent or foreign links refused. `tools/dashboard/acceptance_project.py` builds the acceptance project for the browser run. | Pass |

**Security negative controls** are recorded with each slice. In every case each mechanism was removed in turn, the slice's suites were re-run, and the code was restored:

- F20.3's session controls, in PR #71;
- F20.4's ten conditional-request controls, in PR #87;
- F20.5's twenty header, origin, bounds, traversal and log controls, in PR #90.

The acceptance suite adds no new mechanism. It exercises those mechanisms together.

**Runs:**

| Platform | Command | Result |
|---|---|---|
| Windows 11 (developer host), Python 3.13 | the dashboard suites, `test_credential_delivery`, `test_register`, `test_requirements_ledger`, `test_spec_amendments`, `test_docs_links` (`-n 6`) | 616 passed, 2 skipped (the two POSIX pty tests, as listed) |
| Rocky Linux 8.10 VM (kernel 4.18, SELinux enforcing), Python 3.11.13 | the same set (`-n 4`), then the two pty tests (`-p no:xdist`) | 616 passed; then both pty tests passed (2 passed, 21.8 s), F20.6's real-CLI walk included |
| CI (Windows and Linux matrix, `assurance`) | the full suite | on the PR |

Driving `serve` at a pseudo-terminal found one server defect, fixed in PR #90: the request log wrote synchronously to the terminal, so a terminal that stops reading stalled every request. It also found one test-harness hazard, fixed here in both pty tests: a runner launched in the background inherits SIGINT ignored, so the child now restores the default before it becomes `aew`.

A browser check against the packaged build and live state (Overview, a deep-linked Work record, History and Runs, with no console errors under the CSP) is in PR #90. It was a manual check, not the gate.

## The browser gate (pending)

The web side's runner is `web/scripts/browser-live.mjs`, on branch `feat/f20-authenticated-browser`. It is implemented and verified locally, but not yet published. It checks desktop and phone navigation, supplied record details, Back, Work copy and reopen, themes, and session refusal, against real same-origin responses, with service workers blocked and no fixture servers. The main line provides the server, the project and the private session file:

1. `python tools/dashboard/acceptance_project.py <empty scratch dir>` builds the project and prints its record ids.
2. `aew -C <dir>/repo dashboard serve` runs at the operator's terminal on the default port 4280, with the typed-back code. The URL is written to that terminal.
3. `aew -C <dir>/repo dashboard open` gives a further URL (confirmed with a code shown at the serving console). Paste it into `python tools/dashboard/session_file.py <private scratch>/session.json`.
4. From a separate checkout of the runner's branch, in `web/`, run `DASHBOARD_BASE_URL=http://127.0.0.1:4280 DASHBOARD_SESSION_FILE=<private scratch>/session.json CHROMIUM_PATH=<staged chromium> node --experimental-strip-types scripts/browser-live.mjs`. The packaging baseline stays `4f0a710`.
5. Record here the runner's commit, the server commit, `BUILD.json`'s commit and the results. Delete the session file. The file, the cookie, and any URL, header, trace or storage state never enter evidence.

Until then the integration checklist's browser-side items (hostile-content display, scope and validator isolation in the UI, UI task checks on the integrated system) are **NOT RUN**.

## Limitations and notes

- The engine's terminal integration status `integrated` is not among contract 0.1.2's `Integration.status` `x-known-values`, so the Work page shows it as an unknown value with a warning. That is correct behaviour under the contract. Adding the value is a contract change (renewed C0), noted under F20 for the web developer.
- `tools/dashboard/verify_build.py`, the CI rebuild of the committed build where Node runs, is not built. §4.13 leaves that job to be agreed with the web agent.
- The real-CLI path is tested on POSIX only. On Windows the same walk runs through the in-process service, whose console is substituted, as F20.3's tests do.
