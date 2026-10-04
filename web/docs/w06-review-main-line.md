# W06 independent product review (main line)

- **Reviewer:** Claude (Opus 5.5), the AEW main-line lead developer agent, at the operator's request. Not the W06 implementer.
- **Date:** 2026-10-04.
- **Packet:** `web/docs/w06-review-packet.md` at the evidence commit `e7acfc5`.
- **Runtime commit under review:** `d15bc135f23340b7fe4e1f8039290410383d2be0`, tree `340519d85d09f0b8257f7caab084c4d7893c7f9c`. Both match `result.json`.
- **Frontend fixture disposition: CHANGES REQUESTED.**
  - The investigation succeeds end to end on desktop, and the recorded-execution semantics are right throughout.
  - **On a 390 px phone and at 200% zoom, the Events and Fanout table modes cannot be used to select anything (F2, major).** Task 8's lanes/table parity therefore fails on phone, and so does task 5's table mode.
  - One story-fixture conformance defect (F1) and four nits.
  - Re-review needs only F2's and F1's scenarios.
- Backend adoption and live integration were not assessed, and nothing here claims them.

## Build and serving (independent)

- **My own clone** of `d15bc13` in WSL Ubuntu, not the implementer's tree, built with the pinned offline gate.
  - Command: `SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh` (Docker at `/snap/bin/docker`, `--network none`).
  - **PASS:** 19 test files, 164 tests, contract and fixture digests, typecheck, lint, both builds.
- **My `dist-demo` is byte-identical to the implementer's.** `sha256sum -c` against `web/docs/w06-evidence/dist-demo.SHA256SUMS` at `e7acfc5` passes for all 33 files.
- **Served on port 4261** with `scripts/demo-server.mjs` under Node 22.22.2, inside the builder image, with no service worker.
- **An incident to note.** My first container failed to bind 4251 (EADDRINUSE). A demo server from the web agent's own tree (`AEW-web`, started 04:46) was already listening there, so my first pass ran against it.
  - Its bundles are byte-identical to my build (`index-qLGikyFm.js`, `Recorder-CBmiq_PW.js`).
  - I then re-ran **every** desktop script against my own server on 4261. The snapshots match line for line, apart from screenshot paths and browser timestamps, including the focus, clipboard, injection and request-pattern checks.
  - All results below are from my server. I did not touch the web agent's process.
- **Browser:** the pinned Chromium (revision 1217), headless through Playwright, driving the product UI only (clicks, keyboard, selects, browser Back, clipboard).
  - I read fixture source only to diagnose F1 and to understand the fanout scenario, after observing both in the UI. I never read it to discover identities or answers.
  - No developer tools and no Contract Playground were used.
- **Layouts:**
  - desktop 1440×1000;
  - phone 390×844 (touch, mobile);
  - 200% zoom as 720×500 CSS px at device scale 2;
  - light and dark themes.

  The driver and its step files are in `driver/`, and selected screenshots in `screens/`.

## Identities recorded (desktop and phone alike)

| Kind | Values |
|---|---|
| Trace | `TRACE-Clangd`, snapshot `TRACE-SNAP-1`, captured 2026-10-02T16:45:00Z. Project `aew-demo`, revision 42, contract 0.1.0. The chooser lists `TRACE-Alternate` / `TRACE-SNAP-2` with identical work, invocation, run and capture time, unranked, and requires an explicit choice |
| Coverage | invocation, evidence, reviews, transitions and context complete; tools incomplete, with gap `GAP-tools-1` (source `RECORDER-1`). Retention FIXTURE ONLY on every lane. Ordinal 4 is absent: "Ordinal discontinuities alone do not establish missing events" |
| Events | `EV-01`–`EV-09` at ordinals 1–3 and 5–10, with source timestamps 16:16–16:40Z. Observation time "Not supplied" throughout |
| Executions | `EX-Removal`: `CLANGD-INV-Removal` / `CLANGD-R-A2-2` (launched 16:16), captured status completed. `EX-Discovery`: `CLANGD-INV-Discovery` / `CLANGD-R-A2-3` (16:26). `EX-Retry`: `CLANGD-INV-Retry` / `CLANGD-R-A2-4` (16:34). `EX-Helper`: unregistered, no invocation or run. Each detail says "This captured status is not status at the selected event" |
| Evidence via W05 | `REF-EXEC-Failure` leads to `ES-Removal` (CLANGD-E871, `EV-SNAP-Removal`, stale-db-fictional, 16:20Z), reported result fail. Artifact `ART-Removal` rev 1, text/x-log, 186 B, `sha256:0fc83147…3293ca` (supplied; not verified), bytes [0,186), lines 1–5; the excerpt SHA-256 is verified. `REF-EXEC-Discovery` leads to `ES-Discovery` (CLANGD-E875, `EV-SNAP-Discovery`, refreshed-db-fictional, 16:30Z), with `ART-Discovery` rev 1, application/json, 203 B, `sha256:d4a75ebf…937054`, [0,203), lines 1–2 |
| Packet | `PKT-Retry` at locator `LOC-RetryPacket`: source `SRC-Retry`, invocation `CLANGD-INV-Retry`, run `CLANGD-R-A2-4`, snapshot `SNAP-Retry`. Contents: `CLANGD-D42`, `CLANGD-E875`, `J-04`, each INCLUDED. **No J-05.** J-05 is published at 16:40 (EV-09), after preparation at 16:33. Receipts: `RECEIPT-Retry-PREP` (16:33), `-DELIVERY` (16:34, ACKNOWLEDGED), `-CITATION` (16:38, cites CLANGD-E875). "No benefit evaluation supplied." Accounting: TOKENS 1420/4000, BYTES 4200/16000, policy context-v1 |
| Canonical reference | `CLANGD-D42` "Generated protocol definitions remain source-controlled": a reference only, everywhere it appears |
| Relations | `EX-Removal → EX-Retry` registered child invocation. `EX-Retry → EX-Helper` harness launched helper. `EX-Retry → PROCESS-18` process spawned process (terminal reference). `EX-Retry → PROVIDER-19` provider suboperation (terminal reference). `EX-Removal ↔ EX-Discovery` trace correlation, which is correlation only. Each relation shows its supplied source `SOURCE-<kind>` |
| Controls | Profile fictional-investigation-v1, Rocky 8 · clangd 19, projection incomplete. For EX-Retry: filesystem configured, available and active `os_readonly_roots`, mechanism fictional-linux-readonly; process ownership `pid_namespace`; network `not_provided`; authorized UNKNOWN throughout. The other executions are active at `workdir_separation_only` / `process_group`. Receipt `CTRL-RETRY-1`: reported test PASS, validated 16:32Z, age 780 s, with "no expiry rule" |
| Budgets | `BUDGET-<execution>`: 8 executions under fictional-fanout-v1; story 4/1/1, depth 2, incomplete, "No enforcement result supplied". The fanout scenario's `BUDGET-EX-Retry` is **27 / 11 / 1** against 8, and still no enforcement result is shown or inferred |

## Tasks

| # | Desktop | Phone | Notes |
|---|---|---|---|
| 1 | PASS | PASS | Fixed trace, snapshot, project and capture identity are explicit. Coverage, gap and retention are shown, with the ordinal-discontinuity statement. Captured status is labelled as not being status at the event |
| 2 | PASS | PASS | Removal failure (EV-02/EV-03), discovery (EV-04), preparation (EV-05), delivery acknowledgment (EV-06), citation (EV-07), retry outcome (EV-08: "No legal historical transition or causation inferred"), then EV-09. Execution, invocation and run IDs are recorded above. No causation is derived anywhere |
| 3 | PASS | PASS | From EV-03 and EV-04, W05 opens on the reference association with **no source chosen**; I selected the source and artifact explicitly, and the range, digest and canonical reference are shown. Back restores the selected event, its Details tab and focus on the originating link, on both layouts; on phone the Detail pane is also restored. Scroll restoration wasn't separately exercised on desktop, because the story list does not scroll there |
| 4 | PASS | PASS | PKT-Retry is opened from EV-05 and EV-06, with owners and the separate receipt stages as above. J-05 is absent and later. Back to the recorded execution, in-page or browser Back, restores focus to "Inspect packet PKT-Retry", including after packet tab changes. A packet opened from a deep link returns focus to the detail heading, which is a reasonable fallback; N2 is that a stale `packet_tab` stays in the URL |
| 5 | PASS (F1) | **FAIL (F2)** | Hierarchy and table each give relation kind and source. Expansion is explicit and bounded (3 levels / 24 nodes / 80 edges, with loaded/displayed/edges counters). Cycles stop at "Cycle reference · Terminal reference / expansion bound". EX-Helper is unregistered; PROCESS-18 and PROVIDER-19 are terminal. Correlation is listed apart: "Correlation is not parentage, custody or causation." The relation provenance shows an unknown value in the story (F1). **On phone, table mode cannot select an execution (F2)** |
| 6 | PASS | PASS | Engine vocabulary; environment, source and snapshot binding; configured ≠ available ≠ authorized ≠ active ≠ successfully tested; "process_ownership is not a process-containment claim". Missing scenario: "No validation receipt supplied". Stale: "STALE SUPPLIED". Mismatch: rejected with "Validation receipt execution/environment binding mismatch". The age is shown with no expiry inferred |
| 7 | PASS | PASS | Configured quantity and units, scope ("trace-local recorder observation, not a global ledger"), observed/active/unattributed, depth, completeness and enforcement are reported separately. Exceeding the configured quantity (27 vs 8) yields no enforcement claim. "Not a cost ledger, remaining budget, DispatchDecision or enforcement result" |
| 8 | PASS | **FAIL (F2)** | The rest of task 8 passes on both layouts: paging (large scenario, cursor in URL), off-page selection ("Selected event is outside the current results; its supplied detail is resolved separately"), phone Results/Detail switching, explicit trace selection, arrow-key tabs in all three tablists, close-detail focus back to the event, copy link and reload restoring the selection, light and dark themes, 200% zoom with no horizontal page overflow on any page tested. Error states: denied (403), historical-unavailable (410), malformed (rejected), empty (404), unknown (raw value with warning), unordered (ordinals kept, the unordered event listed separately), refresh-error (after a failed trace refresh, an alert plus "STALE / DISCONNECTED — displaying valid previous projection"), hostile (markup shown as text; `globalThis.w06Attack` stays false; no request to the attacker host). **Hidden views make no reads:** controls load only on the Controls tab, receipts only on the Validation receipts tab. **Unavailable mappings don't resolve by resemblance:** in the missing scenario, EV-03 and EV-05 show "Reference LOC-Failure / LOC-RetryPacket unavailable: no exact mapping supplied", with no link. **Table modes fail on phone and at 200% zoom (F2)** |

## Findings

### F2. Major: on a phone and at 200% zoom, every selection button in the Events and Fanout table modes is covered by the next cell

- **Observed:**
  - At 390×844 and at 720×500 (200% zoom), the tables collapse into stacked label/value cards, and the rows overlap.
  - The "Class / registration" cell sits on top of each row's execution button (Playwright: `<td role="cell" data-label="Class / registration">…</td> intercepts pointer events`). Tapping it does nothing.
  - Hit-testing the centre of every table button gives:
    - phone: Fanout table EX-Discovery, EX-Helper, EX-Removal and EX-Retry **all covered**; Events table EV-01 to EV-09 **all covered**;
    - 200% zoom: the same;
    - desktop: all reachable;
    - the trace chooser table: reachable on every layout.
- **Also on the same cards:**
  - the next row's "Execution:" label overlaps the previous row's relationship text;
  - long relationship text is clipped at the right edge ("→ EX-Removal · Source SOU…") with no way to read the rest.
- **Impact:** a phone user can't use table mode at all. That fails task 5's table mode and task 8's lanes/table parity. Lanes mode and the hierarchy remain usable.
- **Fix:**
  - give the stacked cells their natural height (no fixed row height or absolute positioning), so cards don't overlap;
  - wrap long relationship text instead of clipping it;
  - add a regression that hit-tests table buttons at 390 px and at the 200% zoom viewport (the evidence screenshots didn't catch this).
- **Screens:** `screens/F2-phone-fanout-table.png`.

### F1. Minor: the story fixture's relation provenance kind is outside the UI vocabulary

- **Observed:** in the main story, every relation's provenance renders as `RECORDER-1 · Unknown value: recording_source` (Provenance tab of any event, and the Fanout detail). Unknown-value markup belongs to the `unknown` scenario. In the story it tells the reviewer the fixture is non-conforming, in the middle of task 5.
- **Diagnosis** (source read after observing it): the fixtures build every relation with `provenance: [ref('RECORDER-1','recording_source')]`. No accepted reference kind includes `recording_source`, so the renderer falls back to its unknown-value state. The coverage gap uses the same source and displays fine, because it doesn't render the kind.
- **Fix:** either add `recording_source` to the preview's reference-kind vocabulary (with a label), or use an existing kind in the story fixture. Add a conformance test that the story scenario renders no unknown values.
- **Screens:** `screens/F1-story-provenance.png`.

### Nits

- **N1.** "Trace coverage and response metadata" (Provenance tab) shows the coverage as a raw JSON blob, and repeats its Source provenance and Browser observations panels twice.
- **N2.** After returning from a packet opened by a deep link, `packet_tab=<tab>` stays in the URL with no packet open.
- **N3.** On load, the trace projection is requested twice, and `/api/v1/overview` is fetched again when the Controls tab opens. These are harmless, but they're unnecessary reads.
- **N4.** The Controls sub-tabs (Claims & budgets / Validation receipts) aren't reflected in the URL, so a copied link reopens on Claims & budgets.
- **Observation, not a defect:** in the refresh-error scenario, "Refresh event page" succeeds; only "Refresh fixed trace" exercises the failure. As the packet says, that state then persists until the demo server restarts.

## What the records establish (and what the UI rightly doesn't conclude)

- The failure, the discovery and the later passing retry are recorded events with supplied source timestamps. The UI reconstructs no historical state, infers no transition, and draws no causal link between the refreshed compilation database and the passing build.
- PKT-Retry was prepared, delivered (acknowledged) and cited CLANGD-E875. Its benefit was not evaluated, and the UI says so without implying either outcome. J-05 was not in the packet and was published afterward.
- Controls are configured, available and active claims plus one reported test receipt. Nothing is presented as a current Engine guarantee, and authorization is UNKNOWN throughout.
- Budget observations are trace-local and incomplete. An observed count above the configured quantity is not presented as an enforcement result or as a cost-ledger entry.

## Measurements and evidence

I didn't re-measure performance. The packet's figures are implementer observations, and the packet itself says they aren't a timing SLA. The build identity is verified above.
