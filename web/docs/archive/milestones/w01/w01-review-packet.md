# W01 frozen frontend review packet

Date: 2026-10-03. Historical implementation packet. Main-line returned **AMEND (minor)**;
all findings were resolved in `ad9ed21` and main-line recorded **ACCEPT** on
2026-10-03. See the [fixing-diff response](w01-review-fix-response.md) and
[acceptance record](w01-acceptance.json). Live integration remains separate.
Authenticated/live AEW integration and future backend contracts are not accepted by this packet.

Review source commit **`f6c87d3548d110a2f9052f4b1062673fbd99548a`** on
`feat/aew-dashboard-w01`, based exactly on optional frontend
`7e13f3469e085f346b8bd889a5adf66b06532458`. The accompanying final documentation
commit changes evidence/docs only. Review the frozen source, not a moving preview.
The accepted core, original optional worktree and running AEW checkout were preserved.
Nothing was pushed; assurance and CodeQL remain the main owner's changes.

## Reviewable checkpoints and delivery

| Ticket | Implementation | Checkpoint |
|---|---|---|
| W01-01 | Accepted contract registry, provisional registration guidance, generated lab configuration schema/manifest, backend question ledger | `4374817` |
| W01-02 | Shared context/query/cache identity, validated project bootstrap, atomic retirement/reset, late-response guards, compatible revision reconciliation | `4d04514`, refinement `f6c87d3` |
| W01-03 | Requests/Scenarios/Contract tabs, demo-only dynamic lab, actual boundary-parser playground, bounded memory-only pasted input | `efdab07`, sticky-toolbar refinement `f6c87d3` |
| W01-04 | Injectable clock, fourteen manual recipes, composed regression tests, browser/CSP evidence, ordinary polling verification, CI draft | `fc66ef7`, final browser captures `f6c87d3` |

Approved [plan revision 1.1](../../../design/plans/w01-foundation.md) has SHA-256
`799a2cee52e1b8538becd3bf4de3a80618fc3f21290a90891a0439ce4089b825`;
[approval record](../../../design/plans/w01-approval.json) references the operator's explicit
implementation request. Contract acceptance, preview readiness, test success and
independent frontend acceptance remain separate dispositions.

Accepted API **0.1.2** is unchanged: canonical YAML SHA-256
`68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`.
Generated API types and runtime schema are unchanged. F0–F11 conformance remains covered.
No packages were added. Frontend lock SHA-256 remains
`3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`.

Future preview registration requires its own artifact, digest, parser, fixtures and
provisional disposition. Explanations explicitly represent absence; the frontend
must not infer explanations from nearby fields. W01 defines no future domain schema.
Route/ordinal replay matching is an authored harness mechanism only: extra reads can
shift ordinals and require recipe updates. Unmatched requests expose diagnostics.

## Trying it

Local compiled demo: <http://localhost:4191/work?fixture=F1>.
Open **API panel**, then **Scenarios** or **Contract**. Ordinary fixture browsing
retains interval polling. Start a manual recipe to use Next step, Release response,
Reset and Copy scenario link. Reload starts at step zero. Contract editing makes
no requests and cannot replace dashboard data; closing/resetting discards pasted bodies.
The normal compiled production probe at port 4192 uses a synthetic same-origin
adapter, not the AEW API. Existing previews remain separate.

Selected captures: [Scenario replay](screenshots/w01/scenario-replay.png),
[light Contract tab](screenshots/w01/contract-light.png),
[dark Contract tab](screenshots/w01/contract-dark.png),
[phone viewport](screenshots/w01/contract-phone-viewport.png).

## Verification and evidence

[Result and provenance JSON](w01-evidence/result.json),
[offline command log](w01-evidence/offline-gate.log),
[compiled-browser report](w01-evidence/report.json),
[local CI browser report](w01-evidence/ci-browser-report.json), and
[static file SHA-256 manifest](w01-evidence/static-manifest.json) are retained here.
Static production/demo builds and an archive with receipt are retained in ignored
`web/artifacts/w01-handoff/static-builds.tar.gz`; build directories are
`web/artifacts/offline-gate/dist` and `dist-demo`.

The immutable Linux/amd64 SPT image is
`sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`,
Node 22.22.2/npm 10.9.7. Full cache identities and original carrier provenance are
in the result JSON. Playwright 1.59.1 uses staged Chromium revision 1217,
version 147.0.7727.15, with separately staged OS libraries.

From the repository root, the completed offline command was:

```bash
PATH=/tmp/aew-bin:$PATH \
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/offline-gate.sh
```

It used an immutable carrier with **networking disabled and initially absent
node_modules**. Offline install of 395 packages, generated API/lab artifact
consistency, accepted checksum, typecheck, lint, **101 tests in 13 files**, and
separate production/demo builds passed. Production guard rejects mock initialization,
fixture sentinels, replay catalog and lab strings. No Engine suite was run.

Compiled-browser command, from `web/`, with existing preview servers:

```bash
DASHBOARD_BASELINE_URL=http://127.0.0.1:4187 \
/home/jon/.local/bin/node scripts/browser-w01.mjs
```

All **15 check groups** passed under the proposed CSP. Coverage includes all panel
tabs, keyboard/Escape/focus return, both themes, phone layout, exact parser failures
and unknown values, 304/reset semantics, malformed/failed refresh, initial errors,
ETag observations, divergence/hidden time/convergence, capability downgrade,
retired held responses, graph navigation/reload, hostile content, production lab
exclusion and blocked storage, normal polling and bounded F6/F7 worlds. Deliberate
HTTP failures are identified in the report; no unexpected page/CSP/external-request
errors or non-GET/HEAD API traffic passed unnoticed.

Ordinary visibility tests dispatch document visibility events with controlled
visibility state; they do not claim operating-system background-tab integration.
Manual replay time does not substitute for that independent ordinary polling lane.
Normal production uses synthetic responses with service workers blocked; this is
frontend verification, not authentication or live-system acceptance.

The CI runner was also invoked locally against the compiled builds, on its own
owned ports, and passed the same 15 groups:

```bash
W01_DEMO_PORT=4201 W01_PRODUCTION_PORT=4202 \
W01_BROWSER_OUTPUT=output/playwright-w01/ci-smoke \
/home/jon/.local/bin/node scripts/ci-browser.mjs
```

That launcher starts/stops only its own servers. Its local orchestration used the
available user-local Node/browser launcher; the offline build/test lane used pinned
Node 22.22.2. **GitHub execution has not occurred**. Prior failing-iteration traces
remain under ignored `web/output/playwright-w01/`; final report status is PASS.

## Performance investigation and remaining limitations

[Five alternating fresh-context probes per fixture](w01-evidence/performance-probes.json)
retain exploratory wall-clock timings, request routes and rendered-row counts.
Median locator-wait completion was F6 502 ms baseline / 1052 ms candidate and
F7 671 ms baseline / 1037 ms candidate. These are uncontrolled local observations,
not a performance target or a statistically established benchmark.

[Request/resource timings](w01-evidence/timing-probes.json) and
[direct DOM row-insertion observations](w01-evidence/timing-observer-probes.json)
investigate the discrepancy: the locator wait often returned hundreds of milliseconds
after rows existed. In three F7 DOM-observer trials, first-row medians were 478 ms
baseline / 609 ms candidate, rather than the approximately 550 / 1075 ms locator
completion medians. W01 demo cold-start and the deliberately sequential validated
project → capabilities → projections bootstrap add real startup work; request timings
show the new ordering. This investigation does not justify attributing the entire
locator timing difference to rendering or treating the smaller startup cost as zero.
Recheck with controlled live-server latency at integration; no invented threshold
or universal performance claim is made.

Both worlds preserve four initial reads, 21 rendered F6 Work rows and 100 F7
History rows. Production JavaScript totals 576238 bytes, versus 572775 at the frozen
baseline (about 0.60% growth). The existing Vite >500 kB chunk advisory remains a
nonblocking frontend optimization item. No unbounded request/DOM growth was observed.

[Backend question ledger](../../../reference/backend-questions/w01-backend-question-ledger.md) remains OPEN for
bootstrap/auth-generation ownership, scopes, historical snapshots, validators and
future preview contracts. An explicit reset entrypoint exists; the browser does
not claim to detect arbitrary cookie/permission changes. Main-line approval is
required before future scopes or domain previews become live API semantics.

## Integration and independent review

[CI handoff](w01-ci-integration-handoff.md) records stable job IDs
`changes`, `checks`, `result`, exact Node/npm versions and the contract checksum source
`web/docs/c0-approval.json`. Paths include `web/**` and the shared canonical YAML.
The draft is informational until the main owner wires it into the sole required
**assurance** gate and adds JavaScript/TypeScript CodeQL in the F20 merge PR.
Python lanes remain independent of Node. No branch was pushed.

[SPT feedback](../../core/spt-toolchain-feedback.md) retains resolved findings and ticket-ready
improvements. No new SPT blocker or cache repair was required.

Main agent: independently review source commit `f6c87d3` against `7e13f34`, using
this packet as claims/evidence, then disposition any findings before W01 frontend
acceptance. Accepted API 0.1.2 is not reopened by the lab configuration schema.
Live AEW integration, server headers/auth/bootstrap and OS/browser integration
remain separate acceptance work.
