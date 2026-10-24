# STG-02 website report

Historical report of first runtime checkpoint `3173362d2cc5f6dde2b49db7103092f903bd2760`, whose independent review returned findings. The corrected runtime was subsequently frozen and reviewed; joint runs 1 and 2 were completed. See [CORRECTION-HANDOFF.md](CORRECTION-HANDOFF.md) and [JOINT-TEST-HANDOFF.md](JOINT-TEST-HANDOFF.md) for those later results and remaining designer decisions. Validation of any later PR head is separate. No independent joint-acceptance verdict is claimed.

## Authority and source

The operator assigned the website handoff and adopted sealed STG-01 v0.5.4. Its archive SHA-256 is `64e65578e9774fd9425c19ceaff30f1a0018ae819baa58d9469ed0c33e8f299f`.
The selected interfaces are D-01 0.3.4 and O-01 `o01-command-0.2-review-candidate`; historical PROPOSED/REVIEW-CANDIDATE labels inside the immutable archive do not undo the operator's adoption.

Work is isolated on `feat/stg02-website`, based on fetched merged main `72035fb13116c769274ed6f1b42e761937fb6f56`. The operator approved a fresh worktree because the old website directory has missing Git worktree registration. Old files and other checkouts are preserved. No backend implementation, branch contents or backend notes have been read. Fetching/checking out merged main is source management, not an implementation oracle.

Reports live in repository-root `docs/stg02/`. The architecture workspace is read-only. Extracted contract material lives in ignored `web/artifacts/stg02/`; no extracted contract bytes have been edited.

## Intake checks actually completed

`check_adopted_inputs.py` independently uses JSON Schema 2020-12 and the sealed schemas; it does not run the sealed oracle. `input-validation.json` records:

- exact outer archive digest and 76 manifest file digests matched;
- 16 integrated response/request bodies passed the relevant adopted schema;
- six inherited waiting/run examples passed D-01 0.3.4 after changing only a copied body's `wire_version` from 0.3.3 to 0.3.4;
- original inherited and sealed files remain unchanged.

This is structural fixture qualification only. It does not establish owner authority, freshness at today's clock, coherent cross-record journey bindings, rendered behavior or real backend interoperability.

The operator's 2026-10-19 field-map clarification is incorporated: A-23 F01 waiting, F32 empty waiting, F03 run progress and F04 run detail have no independent witnesses. They are valid shape examples, not proofs of their qualified source stamps. F05 and F13 carry witnesses, but that still does not qualify today's deployment or our UI. No test treats the four unwitnessed examples as an authority oracle. The independent schema check never asserted otherwise; no implementation rollback is required.

The Windows global Python lacked jsonschema; system WSL Python's jsonschema lacked Draft202012Validator. The existing repository virtual environment provides Draft202012Validator and PyYAML and successfully ran the intake check. No dependency or lock change was made. These failed environment probes are setup failures, not contract failures.

## Journey implementation checklist

| Step | Exact interface | Current evidence |
| --- | --- | --- |
| Waiting, cursor and recipient-scoped closure | `GET /v1/read/waiting` | Derived unqualified waiting over fixture HTTP; supplied source link opens the exact run; shared cursor/closure UI exercised with recorded index pages |
| Run progress and unknown remote effect | `GET /v1/read/runs/{execution_id}` | Fixture HTTP run; model-only UNKNOWN_EFFECT with explicitly supplied field owner/basis/time; no whole-invocation clearance inferred |
| Information-only owner axes | `GET /v1/read/continuation-state/{work_id}` | Full/partial specimens and fixture HTTP; AEV unknown reason stays visible; epoch/validity disclosed |
| Deliberate Continue submission | `POST /o01/v0/command-sets` | Separately supplied designer-fixture delegation request; deliberate checkbox selection; real fixture HTTP 202 and visible ordered per-intent results |
| Reloaded owner observation | `GET /v1/read/owner-operations`, `GET /o01/v0/owner-operations/{owner}/{operation_ref}` | Index specimens and exact receipt owner-operation link; reloading that URL repeats the owner read without dispatch |
| Protected actions held | No dispatch | Text-only G3_unqualified; zero protected action buttons; valid protected request rejected by the client action policy |

## Consumer directive coverage

`00-DESIGN/consumer-expectations.json` is the directive source. The following are author working-tree checks, not independent UI acceptance.

| Directive | Required observable behavior | Planned evidence |
| --- | --- | --- |
| `never_permission` | Information-only explanation; no vector-derived enablement or admission | PASS full/partial screenshots; independent selection required even when owner axes report ok; command preparation does not accept a vector |
| `no_unknown_owners` | Full fixture shows supplied owner facts, with provenance and source time | PASS full continuation specimen on desktop/phone; fixture labels remain unproven observations |
| `show_unknown_owners` | AEV unknown, `SOURCE_UNAVAILABLE`, no fabricated blocked/ok | PASS partial continuation on desktop/phone |
| `list_closed` | Complete only for qualified requested scope on final page | PASS recorded index final page |
| `list_continues` | Supplied Next cursor offered, no complete claim | PASS recorded index first page and next-control presence; manual cursor path helper checked |
| `list_incomplete` | Explicit incomplete coverage; no absence inference | PASS derived waiting and recorded partial-owner index |
| `list_empty_closed` | None in requested scope only | PASS recorded qualified empty index |
| `options_advisory_only`, `no_options_unverified` | Hold recovery is outside this slice; no recovery-option UI or execution | Scope exclusion, not a claimed passing implementation |

## Author checks and state evidence

The compiled fixture suite passed at desktop 1440×1000 and emulated phone 390×1000 in fresh headless Microsoft Edge contexts, service workers blocked and strict CSP intact. Screenshots and `results.json` are in `web/output/stg02/`; original first-layout captures are retained in ignored `web/artifacts/stg02/browser-trial-1/`. These are author working-tree artifacts and will not be relabelled as exact-commit evidence.

| State | Screenshot stem (both `1440-` and `390-`) | Boundary |
| --- | --- | --- |
| Provided | `provided.png` | Recorded full continuation interception |
| Partial / unknown owner | `partial-owner.png`, `partial.png` | Fixture HTTP and recorded partial continuation |
| Stale | `stale.png` | Explicitly derived historical run with unqualified stale stamps |
| Unavailable | `unavailable.png` | Recorded 503 Problem, no retained positive detail |
| Denied / not found | `denied.png` | One nondisclosing 404 result |
| Held / 202 received | `received-held.png` | Fixture command HTTP, no protected controls, ordered intent results |
| Reloaded outcome | `reloaded-owner.png` | Exact owner-operation GET URL before/after reload |
| Closed / continues / incomplete / scoped empty | `index-last.png`, `index-first.png`, `index-partial.png`, `index-empty.png` | Recorded-response list directives |

Pinned offline builder `sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b`, Node 22.22.2/npm 10.9.7, network none: PASS all 236 unit/component tests, artifact checks, typecheck, lint, old production/demo builds, production preview exclusion, generated STG-02 validator drift check and separate STG-02 build. This was a working-tree trial, not the final freeze. The 11 new focused tests include lost-response exact-body replay, no duplicate pending dispatch, no conflict retry, reload without POST and storage-failure refusal.

A preceding host-mounted WSL full run had 235 passes and one unchanged historical-graph test timing out at 5 seconds. That failure remains recorded; the pinned container passed the same test without any test or runtime correction in that area. This is not a claim that retrying fixed a defect. Earlier environment failures included old Python validators, CRLF in a local shell launcher, and cross-session loopback. A same-process-group fixture/browser harness resolved the browser reachability issue. No unsafe-eval CSP relaxation was made; validators are compiled offline.

Initial-checkpoint limitations: physical devices, real browser zoom, live credential/session use and independent acceptance were not exercised; later adversarial checks, corrected-source freeze/review and joint interoperability results are recorded in [CORRECTION-HANDOFF.md](CORRECTION-HANDOFF.md) and [JOINT-TEST-HANDOFF.md](JOINT-TEST-HANDOFF.md). Those later records do not claim production or independent joint acceptance. The isolated validator bundle emits a chunk-size warning, disclosed in `IMPLEMENTATION-NOTES.md`.

## Independent findings and correction checkpoint — 2026-10-20

The full first review is preserved in `reviews/review-3173362.md`. Its F1–F4 are behavior findings, not nits; N1 is documentation only. The operator authorized fixing them before a joint test.

- F1: persist recovery phase and validated retry guidance with the immutable serialized request. All five `never` codes remain terminal after reload; other prerequisites remain explicit and are not assumed satisfied. Persist a non-retryable marker before every POST so a failed terminal-state write cannot enable a repeat after reload. Lost transport response still permits an explicitly requested identical-key/body lookup after a durable recovery update.
- F2: legal empty unavailable/unsupported run bodies retain their supplied outcome and limitations. A present wrong identity remains rejected; continuation cardinality is unchanged.
- F3: reject nested owner/operation/intent contradictions. Persist receipt mappings and check known original request-set/intent/recipient/installation joins for the exact mapped owner-operation pair.
- F4: collection closure now includes its separate supplied collection basis, source qualification/state/time/validity, and an expandable full basis with per-owner closures. This is aggregation provenance, not item authority or independent proof.
- N1: WEB-STG02-002 now distinguishes completed author fixture/rendering work from pending designer triage and real qualification.

Regression evidence is retained under ignored `web/artifacts/stg02/`: first baseline run had 17 failures and five passes; one failure was a test's invalid unsupported limitation value, and an existing storage assertion intentionally needed adapting to the new envelope. A corrected schema-valid read-only baseline reproduced all seven intended failing read cases (two controls passed). No runtime was altered to manufacture these failures. The repaired focused Node 22 run passed 34 tests. Windows-native runner setup failed on Linux-only native bindings; WSL uses the existing Node 22 executable instead, without installing or changing dependencies. Typecheck and lint corrections are author checks, not an independent verdict. Pinned full gate, frozen compiled-browser checks and fresh exact-head review still follow this checkpoint.

The first clean committed-source freeze is retained at `web/artifacts/commit-freeze/run-28d4488c`: source `3173362d2cc5f6dde2b49db7103092f903bd2760`, tree `5fa27cdca3ccbee1daefeb399425659430b6fb29`, full pinned gate PASS, 236 tests. It predates these fixes and cannot qualify them. No remote CI/assurance or joint backend test has been observed for the correction checkpoint.

## Interim decisions

Keep the new slice's client, schema validation, navigation and request state separate from the existing provisional dashboard API. Never translate one wire into the other. Use synthetic fixtures only, exact required version headers and no-store behavior. No real operator credentials or session. Commands must not be generated from the continuation vector. Lost-response reconciliation must retain the exact original request body/key; conflict must never auto-retry. Owner identity is `(owner, operation_ref)`.

See `GAP-ENTRIES.md`, `JOINT-TEST-NOTES.md` and `CONTEXT-FEEDBACK.md`. This report will be updated with measured outcomes rather than converting planned checks into claimed results.
