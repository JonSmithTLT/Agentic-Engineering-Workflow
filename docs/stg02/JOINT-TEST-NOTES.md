# STG-02 joint-test notes

Status: joint runs 1 and 2 finished, 2026-10-20 local / 2026-10-21 UTC. Run 2 verifies the repaired owner navigation and controlled response-loss recovery. JT-01/JT-02 remain for designer triage. This author record does not claim independent joint acceptance or green remote CI. Run 1's failed owner step and staging/capture limitations remain below.

The website is being built independently from sealed v0.5.4 and recorded fixtures. No backend implementation, branch or private implementation notes have been read. The real backend test follows completion of both fixture implementations.

Record each mismatch here with: gap ID, source/build identity, synthetic recipient/session, request method/path/version, sanitized response status/headers/body identity, expected adopted clause, observed website treatment and reproduction command. Do not include credentials. Classify before changing an interpretation or fixture. Before testing, an empty mismatch list does not establish agreement.

## Reviewed wrapper ready — 2026-10-20

At this earlier readiness checkpoint the joint journey had **not started**; the backend developer controlled its later startup.

- Wrapper source: clean detached `f8dd097cf9f929c1759820b66b4f169cb32fad11`, tree `049b045b70aab420b902bc1873794064f076697b`; independent `Review: CLEAR` in `reviews/review-joint-wrapper-f8dd097c.md`.
- Wrapper SHA-256: `3cb9191d3cb923d7899a0942c65d6f07502e4b0b52b8e5c8c76080e379286a33`.
- App assets: exact frozen `af77308aa48cbc73a73791b58b807c0a9ebdbe55`, STG-02 complete manifest `d6ec95cf93b42beb4a3902039a104734e3c3d1289f023f0be7fd55659b0608a1`.
- Native Python standalone tests: **11 PASS from the clean wrapper snapshot**; Ruff check and format PASS. Original truncation and competing-listener regressions failed before repair and passed afterward. No actual backend requests were used in these tests.
- Listener: `127.0.0.1:4252`, joint mode, upstream `127.0.0.1:4261`, finite lifetime 3600 seconds. Static readiness GET `/stg02` matched frozen HTML SHA-256 `fa33b588f93cef746456215c5788652d98b25d848a9f0d74b2cee4937eb67627`. No JavaScript/browser API read or backend readiness probe was made.
- Initial PID equality check failed because Windows venv Python uses a launcher/child pair. No second server was launched. The child listener and parent command lines were checked against the exact reviewed script/arguments before the static readiness check; evidence records both PIDs. No unrelated process was stopped.
- Remote CI/assurance: **NOT OBSERVED** for this unpublished local checkpoint. This is not a green-CI or joint-acceptance claim.

Launch command, from the website root with the existing Python executable as `$PYTHON`:

```text
$PYTHON -I -B web/artifacts/stg02/joint-wrapper-f8dd097c/source/docs/stg02/serve_recordings.py --mode joint --port 4252 --upstream-port 4261 --web-root web/artifacts/commit-freeze/run-ef8dde21/source/web/artifacts/offline-gate/dist-stg02 --lifetime 3600
```

The actual launch used absolute resolved arguments for those same repository-relative paths, a hidden window, and stdout/stderr captured in the wrapper artifact directory. Source remained clean; no credential was supplied or injected. Readiness/test/provenance records are copied to `evidence/joint-wrapper-f8dd097c/`.

The inputs requested at that checkpoint were subsequently relayed by the operator below. No backend source or private notes were inspected.

## Joint run 1 — identity and method

Operator-relayed backend identity: `7acb60f5cf9c8f74285e3ee4533ab24f8dc12160`, branch `feat/stg02-slice-backend`, independent CLEAR at that exact head, clean tree, unpublished/no CI. Start reported `2026-10-21T00:01Z`, loopback port 4261, 75-minute lifetime. Fresh state label `joint-state-1`, created empty. Operator reported zero command keys/owner operations and two granted fixture entitlements at browser start. Two backend-developer connectivity GETs of waiting (one direct, one via wrapper) preceded the browser and created no command records. The literal start command was relayed later; the flags and path bindings are recorded below with machine-specific prefixes replaced by variables, not reconstructed from implementation.

Synthetic project HEAD: `2aa8958b82567ab5a48a74b5cf1ecbc1c7792123`; T-0001 RUNNING with INV-0001, T-0002 BLOCKED on T-0001. Synthetic recipient `fixture:recipient-operator`, no browser credential. The supplied separate input `continue-eligible-work-7acb60f5.json` matched SHA-256 `07919368eff3305a1a706ae80f72e7c9288a94774af5aed5ecd9897c29d68697` before navigation. Website app/wrapper source identities remain those above; actual running wrapper has independent CLEAR at `f8dd097c`.

The primary journey used a fresh headless Edge context with service workers blocked and no response interception/substitution; the separately described lost-response probe used an explicit response barrier. One actual journey, with each state captured at 1440×1000 and 390×1000 by responsive resizing; these are not two independent participant trials or physical devices. Browser traffic, request bytes, response bodies/hashes, screenshots and state text are under `web/artifacts/stg02/joint-run-1/`. Failed browser environment setup attempts before navigation made no API request; a bounded native headless session then succeeded. No semantic implementation changes were made during this run.

### Run-1 journey observations

| Step | UTC | Actual request/result | Website observation |
| --- | --- | --- | --- |
| 1 Waiting | `00:14:46.414Z` | GET `/v1/read/waiting?limit=25`, 200, partial/unknown; 3 items; all source stamps unqualified | Incomplete membership, supplied CNI collection basis distinct from item stamps; no execution links. JT-01 |
| 2 Run | `00:14:59.810Z` | Typed supplied `fixture:run-continue-1`; GET `/v1/read/runs/Zml4dHVyZTpydW4tY29udGludWUtMQ`, 200 partial | REPORTED_IDLE and UNKNOWN_EFFECT remain distinct; IF12 basis `fixture:if12-provider-timeout-continue-1`, observed `2026-10-20T23:46:01Z`, unqualified/unknown; no whole-invocation clearance |
| 3 Continuation | `00:15:00.075Z` | Typed `fixture:ticket-continue`; GET `/v1/read/continuation-state/Zml4dHVyZTp0aWNrZXQtY29udGludWU`, 200 partial | Information-only notice; six axes unknown; AEV reason SOURCE_UNAVAILABLE, other reasons literal SOURCE_UNQUALIFIED. No action enabled from the vector. JT-02 |
| 4 Deliberate command | `00:15:17.053Z` | POST `/o01/v0/command-sets`, 202, exact separately reviewed request submitted after deliberate checkbox | Header says received/not done; one ordered HEB result ADMITTED with supplied EFFECT_CONFIRMED fixture observation; no live owner guarantee inferred. Operation `op:c3e5f43126facd3fdd2039dc757d34b7` |
| 5 Reload | `00:15:26.447Z` | GET continuation only | POST count stayed 1; no redispatch. Exact owner link recorded from pre-reload receipt and followed after reload; recovery/index reads remained available |
| 5 Owner GET | `00:15:26.693Z` | GET `/o01/v0/owner-operations/HEB/op%3Ac3e5f43126facd3fdd2039dc757d34b7`, 404 | One nondisclosing state, no positive owner outcome. This step did not succeed. JT-03 |
| 5 Owner index | `00:15:26.869Z` | GET `/v1/read/owner-operations`, 200 partial, membership unknown, one item | Same HEB/operation listed, action CONTINUE_ELIGIBLE_WORK, supplied literal detail_path with `op:`; incomplete rather than complete |
| 6 Protected actions | capture `00:15:27.182Z` | No command request | Held G3_unqualified text; zero close/reattach/attach action buttons |

### JT-01 — no supplied waiting-to-run navigation

- Class: **host or profile qualification deficit**, pending designer triage.
- Authority: shared joint brief, expected steps 1→2 mismatch; D-01 item `links` and recipient-qualified targets.
- Observed: waiting items carry `links: []`; website offers no execution link and does not invent one. Run was opened by the brief's separately supplied ID through the form.
- Expected limitation, not a successful connected journey. Recorded for designer decision about pre-qualification navigation; no browser workaround or contract change made.

### JT-02 — unadopted reason is structurally accepted and displayed raw

- Class: **wire defect**, provisional semantic-vocabulary classification for designer triage (not a schema parser failure).
- Authority: shared brief step 3/BE-05 errata E-2 says SOURCE_UNQUALIFIED is an interim backend code, not adopted vocabulary. Selected D-01 `$defs.ContinuationAxis.properties.reason_code` accepts string or null, so structure alone cannot prove adoption.
- Observed: backend sends SOURCE_UNQUALIFIED for ADC/HEB/IF10/R01/WIS with state unknown and qualification unqualified. Website displays the exact string, gives it no invented meaning and does not upgrade it to ok/current or command permission. AEV stays unknown/not_established with SOURCE_UNAVAILABLE and no basis/time.
- Current choice: preserve literal supplied values; designer owns semantic adoption. No vocabulary patch or speculative browser interpretation made.

### JT-03 — encoded owner-operation locator returns 404

- Class: **implementation defect**, backend, confirmed through the operator's relay of the backend developer's trace. No implementation was changed during this run.
- Authority: adopted O-01 GET path `(owner, operation_ref)` identity and shared brief step 5; exact receipt/index names HEB plus `op:c3e5f43126facd3fdd2039dc757d34b7`.
- Browser request at `00:15:26.693Z`: GET `/o01/v0/owner-operations/HEB/op%3Ac3e5f43126facd3fdd2039dc757d34b7`, `X-AEW-O01-Wire: o01-command-0.2-review-candidate`, received nondisclosing 404. Body SHA-256 `8888338abf6df90d3050b898eea561621e0c0fa4925cff1c743c7864ebe1d0c8`; no false positive shown. The same operation appears in index seq7.
- Separate read-only diagnostic at `00:17:31.5455675Z` used the index's literal supplied `detail_path`, not a guessed operation or a changed UI: GET `/o01/v0/owner-operations/HEB/op:c3e5f43126facd3fdd2039dc757d34b7`, same wire version, received 200 with matching owner/operation and supplied EFFECT_CONFIRMED. This HTTP diagnostic narrows URL-encoding behavior but does **not** count as completion of the product-UI owner step. Full diagnostic response is retained in `diagnostic-raw-owner-path.json`.
- Backend developer confirmed via the operator: the operation existed, belonged to the entitled fixture recipient, and was retained. The router validated the still-percent-encoded segment before decoding, so `%` failed the logical operation_ref pattern. The website's encoding and nondisclosing handling were conformant. Backend initially proposed segment decoding and encoded-path tests through its own review after this run; the later run-2 relay clarifies that this changes O-01 only, while D-01 base64url IDs continue rejecting any percent sequence; the tested server remained unchanged. Backend also reported its driver and earlier tests used literal-colon paths; that coverage explanation is owner-reported, not a website audit of backend code.
- Naming crosswalk: the backend relay calls this owner defect JT-02; this website register retains JT-03 because JT-02 already names the interim reason-code issue. They refer to the same encoded-path failure, not two defects.

### Probes

- Unknown ID: browser typed `fixture:joint-unknown-id` at `00:15:27.259Z`; GET `/v1/read/runs/Zml4dHVyZTpqb2ludC11bmtub3duLWlk`, 404, one nondisclosing state and no retained positive run detail. Both widths captured.
- Source outage: completed as expected, details below.
- Entitlement withdrawal: completed for browser read-state handling, with a literal-path diagnostic separating the known owner-router defect, details below.
- Lost response: exact-byte timeout/lost-reply reconciliation verified; stop-only fault causality was not isolated. JT-04 records that limit. No blanket four-probe pass is claimed.

### Outage window and recovery

The backend developer supplied exact engine IDs `INV-0001` and `T-0002`. Their path identities are base64url of the bare ID, not an `aew:` prefix; that prefix belongs to response provenance. Baseline browser reads were 200/partial at `00:19:08.564Z` and `00:19:08.797Z`.

Operator-relayed outage switch: `2026-10-21T00:19:31.8Z`, POST `/_test/engine-outage`, `{"unavailable":true}`, 204 (request interval `.763Z`–`.805Z`). Entitlement stayed granted. Browser refreshed the existing T-0002 view at `00:19:55.983Z` and opened INV-0001 at `00:19:56.134Z`; both returned 503 `owner_unavailable`, retry `when_source_recovers`, adopted headers. The run captures show unavailable state. A later audit during run 2 found that the work capture was taken before the refresh settled and still shows the prior partial body; it cannot prove post-503 clearing. That work UI observation is inconclusive in run 1 and is repeated with a corrected settle condition in run 2. Waiting at `00:19:56.310Z` remained 200 partial/unknown with `partial_source`, `source_unavailable`, `source_unqualified`, not a false complete or an invented empty result.

Operator-relayed restore: `00:20:39.9Z`, `{"unavailable":false}`, 204 (`.888Z`–`.930Z`). Browser recovery reads returned 200/partial at `00:21:26.511Z` for INV-0001 and `00:21:26.748Z` for T-0002. No command POST occurred in this window. No fresh timestamp was treated as a renewed qualified fact.

### Entitlement window and recovery

Operator-relayed withdrawal: `00:22:11.7Z`, POST `/_test/read-entitlement`, `{"recipient_ref":"fixture:recipient-operator","entitled":false}`, 204 (`.691Z`–`.739Z`). Outage remained off. Browser continuation, run, waiting and owner index returned one nondisclosing 404 each at `00:22:43.153Z`, `.338Z`, `.510Z`, `.681Z`; no positive detail remained. The encoded owner request at `.820Z` also returned 404, but JT-03 prevents using that result to prove withdrawal caused it.

Separate literal-path owner diagnostic at `00:23:08.0522073Z` returned 404; the same supplied path had returned 200 before withdrawal. This diagnostic was recorded separately from product-UI completion. Operator-relayed restore: `00:23:30.6Z`, `{"recipient_ref":"fixture:recipient-operator","entitled":true}`, 204 (`.597Z`–`.644Z`). Backend developer reported literal owner GET 200 again. Browser waiting recovery at `00:24:20.022Z` returned 200/partial. No new command was submitted during withdrawal or restoration.

### JT-04 — response-loss staging limit; exact reconciliation verified

- Class: **host or profile qualification deficit**, test-staging scope, not an adopted wire defect.
- The brief requests stopping the wrapper between POST and answer. A second fresh browser context submitted the **same** separately supplied request/key against the same existing backend state. Its response was held at a controlled browser route barrier after an actual HTTP request through the reviewed wrapper; no response body was synthesized or mutated. The real backend returned 202 at `00:24:40.143Z`, identical to the original stored receipt; the UI still displayed no receipt.
- The browser's existing 15-second deadline expired while the barrier was held. The verified owned wrapper was stopped at `00:25:01.5357475Z`, after that deadline, then the browser barrier was released. UI showed unknown/unestablished outcome and enabled only exact-request reconciliation. Therefore this verifies timeout/lost-reply recovery, **not** that stopping the wrapper alone caused the initial loss. The strict stop-before-timeout causal variant remains unverified; it must not be marked a full pass.
- The first restart command misinterpreted a JSON DateTime during UTC subtraction, requested an invalid lifetime of 16340 seconds and was refused by the unchanged wrapper before binding. A reconcile attempt while the wrapper was down produced no backend response and timed out in the driver; it did not reach the backend. These failures are preserved, not counted as successful replays.
- The launcher was corrected to parse the raw JSON `DateTimeOffset`. The same reviewed wrapper restarted at `00:27:37.0849132Z`, keeping its **original** `00:58:28.486345Z` expiry (1852 seconds remaining), with no backend restart/reset or runtime code change.
- Explicit UI reconciliation returned 202 at `00:27:41.138Z`, before stored receipt expiry `00:30:17Z`. Submitted request SHA-256 was `ff92253dcc4fbe638ce31f9d08499a686c501c8c72b94acf9dadb43a01892f57` for original, held replay and reconcile. This is the exact compact JSON sent by the UI, distinct from the pretty-printed input file's hash. Response-body SHA-256 was byte-identical each time: `da4b9601fc2cadd4d57a690ba0e792639fb54589a7991b98811afd282fea2c05`. Receipt observed_at remained `00:15:17Z`, never regenerated by the browser.
- Both widths capture the held/unknown/reconciled states. Bounded browser sessions were closed after capture. Wrapper processes remain bounded by the original expiry. No replacement key, hidden automatic POST retry, newly inferred delegation, owner-operation minting or API interpretation was introduced by the website.

### Backend final ledger — operator-relayed owner observation

At `00:28:13Z`, backend developer reported **one key and one owner operation** in `joint-state-1`: `fixture:key-continue` / HEB `op:c3e5f43126facd3fdd2039dc757d34b7`. Installation `fixture:installation-slice`, recipient `fixture:recipient-operator`; stored/issued `00:15:17Z`; stored receipt observed_at `00:15:17Z`, valid until `00:30:17Z`. The operation's reported retention is until 2026-11-20. These are observed test-host choices, not newly adopted retention guarantees.

Owner-reported log lines: 8 original POST →202/dispatch; 47 held replay →202/lookup; 48 explicit reconciliation →202/lookup. Exactly three command POSTs reached the backend; later lookups created neither key nor operation. The failed reconcile while the wrapper was down did not reach it. Backend log replay times were associated with the browser/probe UTC records above, not claimed as independently timestamped log lines. Its reported 32ms versus 2ms durations are not a timing SLA or proof of dispatch semantics; ledger counts and identical identity/receipt are the relevant evidence. A partial browser index alone cannot establish global operation counts.

### Backend launch command, shared explicitly by the operator

Machine-specific prefixes are replaced by variables. `$BACKEND_ROOT` names the sibling `AEW-stg02-backend` worktree at the exact tested commit; `$PYTHON` names the existing Python in the sibling main repository's `.venv/Scripts/python.exe`; `$SCRATCHPAD` is the operator-local synthetic scratch directory. Its resolved absolute paths are not committed. No tokens file was read.

```text
PYTHONPATH="$BACKEND_ROOT/src" timeout 4500 "$PYTHON" -m aew.stg02.server --port 4261 --state-dir "$SCRATCHPAD/joint-state-1" --project "$SCRATCHPAD/proj6/repo" --tokens "$SCRATCHPAD/tokens.json" --fixture-recipient --test-routes
```

This is a path-normalized transcription of the supplied command, preserving every option and relative synthetic suffix, not a command executed by the website developer. The real backend start was controlled by its owner throughout.

### Evidence and disposition

Durable selected captures, browser traffic, exact request/receipt digests and probe metadata are under `docs/stg02/evidence/joint-run-1/`; full originals and test-driver failures remain in ignored `web/artifacts/stg02/joint-run-1/`. One harness label collision overwrote the initial `05-owner-index` image/text during withdrawal. The original positive index remains visible in the same-page `06-protected` captures taken at `00:15:27.182Z`, backed by original seq7 HTTP; withdrawn index captures were separately renamed before any reuse. This evidence mapping is explicit; no later image is presented as an earlier screenshot.

All six journey steps were attempted and captured at both widths. Owner product navigation did not succeed (JT-03). Unknown-ID, outage and withdrawn-read probes were exercised; exact timeout/lost-reply reconciliation was exercised with the strict stop-only staging limit (JT-04). No expired-receipt probe, real device, real zoom, human-usability study, qualified owner-source guarantee, production adoption or independent joint acceptance is claimed. No website/backend implementation was changed during the run.

Next: backend fixes/reviews its decoding defect, designer triages JT-01/JT-02 and the probe limit, then a new reviewed backend plus a new empty state and fresh wrapper can rerun the failed/limited paths. The website must retain conformant encoding rather than work around the server. Both source implementations remain independent.

## Joint run 2 — reviewed backend correction and fresh state

This is a separate run, not a reinterpretation of run 1. Backend identity, reviews, state initialization and ledger observations below were relayed by the operator; no backend code, private notes or tokens file was inspected.

| Binding | Tested identity |
| --- | --- |
| Backend | `966fc2c610c7b9e26c8d9d9f004139532c956520`, branch `feat/stg02-slice-backend`, reported clean |
| Backend review | CLEAR at `65429ef1`, then exact-head delta CLEAR at `966fc2c6` after a test-name nit; unpublished, no CI |
| App runtime | Unchanged `af77308aa48cbc73a73791b58b807c0a9ebdbe55`, tree `9c92ff8a1479fc9b13633dbf5436354ed93441ec` |
| Wrapper runtime | Unchanged exact-reviewed `f8dd097cf9f929c1759820b66b4f169cb32fad11`, tree `049b045b70aab420b902bc1873794064f076697b` |
| Frozen STG-02 build | Complete manifest SHA-256 `d6ec95cf93b42beb4a3902039a104734e3c3d1289f023f0be7fd55659b0608a1`; HTML `fa33b588f93cef746456215c5788652d98b25d848a9f0d74b2cee4937eb67627` |
| Backend state | `joint-state-2`, fresh and empty at startup: zero keys/operations; two granted fixture entitlements |
| Synthetic project | Unchanged HEAD `2aa8958b82567ab5a48a74b5cf1ecbc1c7792123`, T-0001 RUNNING / INV-0001, T-0002 BLOCKED |
| Recipient | `fixture:recipient-operator`, no browser credential |
| Separate command input | `continue-eligible-work-966fc2c6.json`, SHA-256 `07919368eff3305a1a706ae80f72e7c9288a94774af5aed5ecd9897c29d68697`, byte-identical to run 1 |
| Browser | Headless Edge `155.0.4283.62`, native driver Node `v24.19.0`, service workers blocked; responsive 1440×1000 and 390×1000 |

Backend start was reported at `2026-10-21T00:49Z`, 75-minute lifetime, port 4261. Its only reported pre-browser check was direct GET waiting →200 at `00:49:26.325Z`, with no command. The supplied start command is the path-normalized command above with only `joint-state-1` replaced by `joint-state-2`; all flags and synthetic project bindings are unchanged. The website did not execute it.

The previously owned run-1 wrapper was identified by its command line and retired. A fresh wrapper started `00:50:56.6029675Z`, PID 6384, original expiry `01:50:56.6029675Z`, same script hash and frozen assets, same launch flags above and lifetime 3600. It made no startup upstream request. Its later fault/restart retained this expiry. No app or wrapper implementation changed.

Backend correction scope, as relayed: O-01 owner path segments are decoded exactly once. The D-01 base64url ID rule **does not change**: percent sequences remain invalid there. Earlier run-1 plans suggesting both path families needed decoding are superseded by this correction. The website independently exercised the normal percent-encoded owner path; malformed, double-encoded and slash cases are backend-owner reported tests, not independently repeated website coverage.

### Run-2 journey and probes

All UTC values are on 2026-10-21. Request/response versions, complete sanitized bodies and SHA-256 identities are in `evidence/joint-run-2/traffic.json`. D-01 reads send `X-AEW-Wire-Version: 0.3.4`; O-01 reads/commands send `X-AEW-O01-Wire: o01-command-0.2-review-candidate`.

| Step | Browser response UTC / seq | Result and UI evidence |
| --- | --- | --- |
| Waiting | `00:51:18.329Z`, 1 | 200 partial, incomplete membership, unqualified stamps; no supplied run links. `01-waiting` captures. JT-01 remains |
| Supplied run ID | `00:51:18.671Z`, 2 | 200 partial; REPORTED_IDLE, UNKNOWN_EFFECT with supplied IF12 basis/time; no inferred clearance. `02-run` |
| Continuation | `00:51:18.910Z`, 3 | 200 partial, informational only; all six axes unknown, interim reasons rendered raw. `03-continuation`; JT-02 remains |
| Deliberate selection/submit | `00:51:19.400Z`, 4 | 202, one ordered ADMITTED result, exact HEB operation link, received/not done. `04-selected`, `04-receipt` |
| Reload | `00:51:19.723Z`, 5 | GET only; command POST count remains one. `05-reload` |
| Exact owner operation | `00:51:19.946Z`, 6 | Encoded `/o01/v0/owner-operations/HEB/op%3Ac3e5f43126facd3fdd2039dc757d34b7` →200, matching owner/operation/intent. `05-owner`. Website JT-03 / backend JT-02 corrected for this journey |
| Owner list | `00:51:20.142Z`, 7 | 200 partial, membership unknown, matching operation; no completeness claim. `05-owner-index` |
| Protected actions | `00:51:20.449Z` capture | Held text with no protected controls visible, no POST. The original page is also visible in `05-owner-index`; see capture-driver limitations below |
| Unknown ID | `00:51:20.539Z`, 8 | 404 nondisclosing result, no positive run detail. `probe-unknown-id` |
| Outage | `00:53:40.361Z` / `.548Z`, 16–17 | Run/work 503 owner_unavailable, no positive detail in settled captures; waiting `.735Z`, 18, remains 200 partial with source_unavailable |
| Outage recovery | `00:54:38.773Z` / `00:54:39.004Z`, 19–20 | Run/work 200 partial; source authority not renewed by fetch time |
| Entitlement withdrawal | `00:55:35.652Z`–`00:55:36.165Z`, 23–26; owner settled `00:55:53.529Z`, 27 | Run/work/waiting/index and encoded owner GET each nondisclosing 404; settled captures show no positive detail |
| Entitlement recovery | `00:56:56.549Z` / `.751Z`, 28–29 | Encoded owner 200, waiting 200 partial; no new command |
| Response loss/reconciliation | See below | Controlled withheld response, wrapper stopped before application deadline, exact-body reconciliation returns byte-identical receipt |

The owner read at `00:54:39.233Z` and the restored read re-observe the same owner record. Their newer observed_at values do not establish a new event. Operation identity happens to match run 1 because the supplied key/request/intent are identical; the two runs used separate ledgers and fresh browser contexts. No cross-run receipt was reused.

### Run-2 operator switches

These switch times come from the operator-relayed backend request log, not from browser clock estimates. The website never called the backend's `/_test/` routes.

- Outage armed `00:52:00.164Z`, restored `00:54:13.737Z`, both switch POSTs 204; entitlement stayed granted. Baseline run/work reads were 200 before the switch. The first 503 HTTP responses were seq11/12 at `00:52:18.378Z` / `.532Z`; corrected settled UI captures use seq16/17.
- Entitlement withdrawn `00:55:03.397Z`, restored `00:56:24.764Z`, both switch POSTs 204; outage stayed off. The encoded owner GET was 200 before withdrawal, 404 during it, then 200 after restoration. Unlike run 1, the known route bug no longer confounds this result.

### Run-2 controlled response-loss recovery

A separate fresh browser supplied the same command input, against the same existing `joint-state-2`. A browser route barrier forwarded the actual POST through the reviewed wrapper, with redirects/retries disabled, then withheld the real response from the application. Nothing in its body was synthesized, changed or fulfilled to the UI. This is an instrumented loss experiment, not an uninstrumented TCP interruption.

1. The real held replay returned 202 at `00:56:59.822Z`; the application had no receipt.
2. After both-width held-state capture, the helper recorded the stop-sequence UTC marker `00:57:00.100Z`, **278 ms after the held-response UTC**. Its later elapsed sample was 284 ms, after awaiting the receipt-heading check; these are different sampling instants. It then stopped only the verified owned PID 6384 and aborted the browser route instead of delivering the held response. Exact process-exit time was not separately measured. The unknown-state capture at `00:57:00.325Z` says **Failed to fetch**, not timeout, well before the application's 15-second deadline; exact-request reconciliation is enabled.
3. The same reviewed wrapper restarted `00:57:14.7790062Z`, PID 38236, 3221 seconds remaining to the original expiry. No backend reset, extended hour, code change or substitute API response.
4. Explicit UI reconciliation returned 202 at `00:57:24.247Z`, before receipt expiry `01:06:19Z`. The sent key and exact body match the original; the receipt bytes match both earlier replies. Both widths capture held, unknown and reconciled states. No failed reconcile was attempted while the wrapper was down in run 2; that failure belongs to run 1 only.

Request SHA-256 for original/held/reconcile: `ff92253dcc4fbe638ce31f9d08499a686c501c8c72b94acf9dadb43a01892f57`. Response SHA-256 for all three: `0fd99fb23ae7665cdcb5bba3389a0949ad65090abdcec350a4b0012113fa53c0`. Receipt observed_at stays `00:51:19Z`, valid until `01:06:19Z`. Different run-1/run-2 receipt hashes are expected for different issued times, not a mismatch within a run.

This resolves run 1's stop-after-timeout ordering limitation for the **controlled barrier experiment**. It does not claim that a naturally interrupted, uninstrumented socket was independently exercised. The designer decides whether this staging satisfies the brief; no blanket transport-resilience claim is made.

### Run-2 final owner observation

At `00:57:50Z`, the backend developer reported **one key and one owner operation**, unchanged by the two replays. The key is `fixture:key-continue`, stored `00:51:19Z`, installation `fixture:installation-slice`, recipient `fixture:recipient-operator`. The HEB operation is `op:c3e5f43126facd3fdd2039dc757d34b7`, issued `00:51:19Z`. Its stored receipt remains ADMITTED, observed `00:51:19Z`, never reissued.

The operator relayed these exact backend log lines (written after sending each response):

```text
2026-10-21T00:51:19.400Z POST /o01/v0/command-sets 202 8ms
2026-10-21T00:56:59.820Z POST /o01/v0/command-sets 202 2ms
2026-10-21T00:57:24.236Z POST /o01/v0/command-sets 202 2ms
```

The owner classifies these as original dispatch, stored-receipt lookup, stored-receipt lookup. Durations are recorded observations, not evidence of causality or a performance SLA. Global counts come from the owner's ledger report, not the partial browser index. The four other reported POSTs are the explicitly coordinated probe switches, not commands.

### Capture-driver correction and evidence limits

The first driver waited for an enabled refresh button, which can precede the completed state update. Run-2 `probe-outage-work-503` captured Loading; `probe-entitlement-owner-404` captured the earlier owner view. These images are inconclusive and **not used** to claim settled refusal behavior. Full originals remain locally preserved. This audit also exposed the run-1 work-503 capture problem, corrected explicitly above.

The driver was changed, without changing the app/wrapper, to await a completed outcome/alert and absence of Loading on newly opened reads. A same-view refresh can still satisfy that condition with an earlier outcome, so accepted negative captures use completed **navigation** reads: `probe-outage-run-503-settled`, `probe-outage-work-503-confirmed`, `probe-outage-waiting-partial-settled`, and `probe-entitlement-owner-404-settled` plus the other four refusal views. These establish the resulting unavailable/refused views, not a frame-by-frame latency guarantee for clearing during refresh. No screenshot timing is used as a product SLA.

A reused `06-protected` label was overwritten by a later outage capture. Original seq7 and the preserved `05-owner-index` screenshots still show the initial owner-index page with protected actions held and no protected controls visible. The session records the protected step but does not persist a button count; no numerical count is attributed to that file. The overwritten image is not passed off as that original capture. Separate before-driver-correction JSON snapshots preserve the earlier trace. Browser sessions were closed after captures; one journey resized to two viewports does not count as two participant studies. No physical-device, real-zoom, human-usability, token-authentication or production-source qualification claim.

Selected durable evidence is `evidence/joint-run-2/`, with a complete local SHA-256 inventory and verification record. Raw harness source, first capture attempts and local launcher logs remain under ignored `web/artifacts/stg02/joint-run-2/`. Runtime source snapshots stayed clean and build inventories are rechecked; no new app build is claimed for this documentation-only result.

### Current disposition and next decision

- Six journey steps and four probes were exercised, with missing supplied navigation and interim reason vocabulary explicitly classified rather than worked around.
- The actual encoded owner path now succeeds in the product UI; no frontend URL-encoding change was needed.
- Unknown IDs, outage and withdrawn entitlement produce the expected nondisclosing/unavailable views. Controlled response-loss reconciliation returns the identical stored receipt, and the backend owner reports one operation.
- JT-01 and JT-02 / WEB-STG02-004 and -005 need designer triage. WEB-STG02-006 retains run 1's failure and run 2's explicit controlled-staging limit. No adopted contract was amended.
- No new frontend runtime defect was identified by these checks. This author report is not independent joint acceptance. Backend/website remote CI was not observed; no PR, push or merge is claimed. The designer owns the charter/operator decision after both sides commit their notes.
