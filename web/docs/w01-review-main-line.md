# W01 frontend foundation: main-line review

| | |
|---|---|
| Reviewed | Source `f6c87d3` against `7e13f34` on `feat/aew-dashboard-w01` (W01-01 to W01-04); docs commit `c1022e8` read for the claims |
| Claims read | `w01-review-packet.md`, `design/w01-ci-integration-handoff.md` |
| Contract and lock | Unchanged: contract 0.1.2 (`68b46527…d691`) and the lock (`3cab231b…b0b2`); `package.json` adds two scripts and no dependencies |
| Reviewer, date | Claude, the main AEW agent, 2026-10-03 |
| **Disposition** | **AMEND (minor).** The production read path and the demo-only lab are sound. One Medium finding in the CI draft (W01-1) must be fixed before I wire it into `assurance`. One Low (W01-2) is in the same file. The optional-tools finding OT-1 (`optional-tools-review-main-line.md` on the graph line) is still present here and can be fixed on this line. |

## How this review was done

Static review of the committed diff, read through `git` from the main repository, as for the core. I did not rerun the offline gate (101 tests), the 15 browser check groups or the local CI runner: those are the frontend's evidence. I checked GitHub's runner image documentation and the action versions directly.

Read in full:
- `api/read-context.ts`, the `api/transport.ts` diff, `client/queries.ts`, `client/clock.ts`, the `client/revisions.ts` and `client/dashboard.tsx` diffs, the `main.tsx` diff;
- `api/mock/browser.ts`, `lab/validation.ts`, the production guard;
- `.github/workflows/web.yml`, `scripts/check-contract.mjs`, `scripts/ci-browser.mjs`, the browser launcher's Chromium path.

The lab's replay engine and UI were checked for what reaches production, not line by line.

## What I found sound

- **Read sessions.** Every query and cache key carries mode, dataset, contract, project, snapshot, authorization generation and a per-session serial (`ReadContext.key`).
  - A response for a retired or replaced context is dropped as an abort and is not logged.
  - The first `/project` binds the session to its project, and any later projection from another project is refused.
  - Reset cancels, removes and replaces atomically.
  - Revision reconciliation groups by that context, so two sessions never reconcile with each other.
- **Bootstrap order.** Project, then capabilities, then projections, and a project load error is shown before the capability gate. The extra round trip at startup is measured and disclosed, not hidden.
- **The manual clock cannot reach production.** Only the demo lab calls `setReadClock` and `notifyReadClock`. In production `readClock.manual` is always false, so polling, focus refresh and reconciliation behave as before.
- **The lab is demo-only.**
  - `main.tsx` imports it only under `MODE === 'demo'`.
  - The production guard rejects its strings (`W01_REPLAY_CATALOG`, "Manual replay", "Contract Playground"), and each of those appears only in lab sources.
  - Pasted contract input is capped at 256 KiB, kept in memory, parsed with the accepted parsers, and never becomes dashboard data.
- **The contract check is right.** `check-contract.mjs` hashes the canonical YAML and requires the same digest and version in `c0-approval.json` (`ACCEPTED`) and in `contract-version.json`. A contract change without a renewed C0 review fails it. This is the single source we agreed on.
- **The CI draft matches what we agreed** in its overall design:
  - stable job ids `changes`, `checks` and `result`, which I'll wire into `assurance`;
  - `contents: read` and no secrets;
  - Node 22.22.2 and npm 10.9.7, with `npm ci --ignore-scripts`;
  - the shared YAML in the path filter;
  - failure evidence uploaded only on failure;
  - the browser launcher uses the Chromium path the install step fills (`artifacts/playwright/browsers`).

  The action majors (`checkout@v7`, `setup-node@v7`, `upload-artifact@v7`) are the current ones and match `ci.yml`.

## Findings

### W01-1 (Medium): the change detector uses `rg`, which GitHub's Ubuntu runners do not have, so every web change would be skipped silently

`.github/workflows/web.yml`, job `changes`:

```bash
if rg -q '^(web/|docs/design/dashboard-api-v1-provisional\.yaml$|\.github/workflows/web\.yml$)' "$RUNNER_TEMP/web-changed-paths.txt"; then
```

- **`rg` is missing.** ripgrep is not in the Ubuntu 24.04 runner image's software list (checked on 2026-10-03).
- **`set -e` doesn't catch it.** A command that is not found inside an `if` condition just makes the condition false, so the step succeeds with `web=false`.
- **The whole chain then passes without checking anything.** `checks` is skipped, and `result` accepts "skipped" because `web=false`. Once wired into `assurance`, a PR that changes `web/` would pass without running a single web check.
- **The local run didn't use this job.** The local CI runner exercised `ci-browser.mjs`, not `changes`, and GitHub has not run the workflow yet.

**Fix:**
- Use `grep -Eq` (always present).
- Make detection fail closed. If the diff or the match errors (exit status other than 0 or 1), fail the job or set `web=true`; never let it set `web=false`.

**Retest:** in a scratch repository, or with the step's script run locally:
- a path list containing `web/x` gives `web=true`;
- one without it gives `web=false`;
- a forced matcher error fails the step or gives `web=true`.

### W01-2 (Low): the PR diff is two-dot, so a PR behind `main` can be marked as changing `web/`

`git diff --name-only "$BASE" "$HEAD"` compares the base branch's current tip with the PR head. If `main` has gained web changes since the PR branched, they show up as this PR's changes. The result is a false positive: extra web jobs, never a missed one.

**Fix:** `git diff --name-only "$BASE...$HEAD"` (the merge base) for `pull_request` and `merge_group`. Keep the two-dot form for `push` (`before` to `sha`).

## Integration notes for the F20 merge PR (mine, not findings)

- **When `ci.yml` calls this workflow** (`workflow_call`), its own `pull_request`, `push` and `merge_group` triggers would run it a second time on every PR. In the merge PR, keep `workflow_call` and `workflow_dispatch` only, or rely on the standalone triggers and have `assurance` read the run some other way. I'll propose the first.
- **`ubuntu-latest` moves to Ubuntu 26.04 in November 2026** (runner-images announcement). Playwright's `--with-deps` handles the OS packages, so it may need nothing, but first runs after the move should be watched.
- **The production guard lists `scenario-config`**, which appears nowhere in `src/`. That's harmless.

## Gate

W01-1 and W01-2 (and OT-1) are small. Once they're fixed and retested, a diff limited to them is accepted without another full review, and W01 is accepted as a frontend foundation. The backend question ledger stays open, and live integration (authentication, headers, bootstrap ownership, live state) remains separate acceptance work under F20.
