# W05 independent product review (main line)

- **Reviewer:** Claude (Opus 5.5), the AEW main-line lead developer agent, at the operator's request. Not the W05 implementer.
- **Date:** 2026-10-04 (UTC; begun late on 2026-10-03 local time).
- **Packet:** `web/docs/w05-review-packet.md` at `3048e58` (evidence commit). **Source under review:** `405c83644abaf8dd3820c5659f304308af1f04ac` (PR #37, `feat/aew-dashboard-w05`).
- **Frontend fixture disposition: CHANGES REQUESTED.** The investigation succeeds end to end on both layouts and the evidence semantics are right throughout; one keyboard-accessibility failure (F2) in a required task and a story-fixture conformance defect (F1) should be fixed first, with two minor UI nits (F3, F4). Re-review needs only F1 and F2's scenarios.
- Backend adoption and live integration: not assessed and not claimed.

## Build and serving (independent)

- **Own clone** of `405c836` in WSL Ubuntu (not the implementer's tree), built with the pinned offline gate: `SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh` (Docker at `/snap/bin/docker`; `--network none`). **PASS:** Node 22.22.2, npm 10.9.7, contract and fixture digests, typecheck, lint, 17/17 test files, production build and exclusion, demo build.
- **The implementer's `dist-demo` is byte-identical to mine** (tree hash of sorted per-file SHA-256: `2d25c15d51176e45…` for both), so the recorded evidence is of this commit.
- **Served** my `dist-demo` with `scripts/demo-server.mjs` under Node 22.22.2 inside the same builder image (`--network host`, port 4250); no service worker.
- **Browser:** the pinned Chromium (revision 1217) driven headless through Playwright, product UI only: clicks, keyboard, selects, browser Back, clipboard. Fixture source was read only to diagnose F1 after finding it in the UI, never to discover identities or answers. No developer tools or Contract Playground.
- **Layouts:** desktop 1440×1000; phone 390×844 (touch, mobile); 200% zoom as 720×500 CSS px at device scale 2; light and dark themes.

## Identities recorded (same on both layouts)

| Kind | Values |
|---|---|
| Journal | J-05 "Refresh compile_commands before judging missing callers" (conditional lesson, CURRENT, work CLANGD-T181, published 2026-10-02T16:40:00Z) |
| Reference associations | `REF-J05-CLANGD-E871` (supporting), `REF-J05-CLANGD-E875` (supporting), `REF-J05-CLANGD-E880` (opposing), `REF-PKT-Retry-E875` (packet); each with `source_id: null`, `snapshot_id: null`, visibility `fictional-authorized` |
| Evidence sources | `ES-Removal` (CLANGD-E871, `EV-SNAP-Removal`, stale-db-fictional, 16:20:00Z), `ES-Discovery` (CLANGD-E875, `EV-SNAP-Discovery`, refreshed-db-fictional, 16:30:00Z), `ES-Counter` (CLANGD-E880, `EV-SNAP-Counter`, refreshed-db-fictional, 16:35:00Z) |
| Producers | `CLANGD-INV-Removal` / run `CLANGD-R-A2-2`; `CLANGD-INV-Discovery` / `CLANGD-R-A2-3`; `CLANGD-INV-Counter` / `CLANGD-R-COUNTER` |
| Artifacts | `ART-Removal` rev 1, text/x-log, 186 B, `sha256:0fc83147…3293ca`, bytes [0,186), lines 1–5; `ART-Discovery` rev 1, application/json, 203 B, `sha256:d4a75ebf…937054`, [0,203), lines 1–2; `ART-Counter` rev 1, text/x-code, 208 B, `sha256:257f12b4…bafd13`, [0,208), lines 1–4 |
| Comparison | A: `CLANGD-INV-Removal` · `SRC-Removal` · `SNAP-Removal` (16:20:00Z) · run `CLANGD-R-A2-2` (launched 16:16:00Z). B: `CLANGD-INV-Retry` · `SRC-Retry` · `SNAP-Retry` (16:38:00Z) · run `CLANGD-R-A2-4` (launched 16:34:00Z). Later: `CLANGD-INV-Later` · `SRC-Later` · `SNAP-Later` · run `CLANGD-R-LATER`, work `CLANGD-T203` |
| Packets and receipts | `PKT-Retry`: `RECEIPT-Retry-PREP` (16:33), `RECEIPT-Retry-DELIVERY` (16:34, acknowledged), `RECEIPT-Retry-CITATION` (16:38, cites CLANGD-E875), no benefit evaluation. `PKT-Later`: PREP, DELIVERY (acknowledged), no citation, no benefit evaluation |
| Canonical reference | `CLANGD-D42` "Generated protocol definitions remain source-controlled" (decision reference; shown as reference only everywhere) |

## Tasks

| # | Desktop | Phone | Notes |
|---|---|---|---|
| 1 | PASS | PASS | From `/knowledge?fixture=F1&view=journal&selected=J-05&panel=evidence`, CLANGD-E871 opens the inspector with **no source chosen**; the association is shown; `ES-Removal` is selected explicitly. Record: verification, claim "Removal broke generated protocol callers; the change was reverted." (result shown as an unknown value: F1). Provenance: bindings, producer, J-04, CLANGD-D42 as reference only. The diagnostic reports `generated/protocol_client.cpp:42: undefined reference to dispatch_protocol`, `build result: FAIL`, removal reverted, missing index references did not establish unused code. |
| 2 | PASS | PASS | ART-Removal: revision 1; full digest labelled *supplied; not verified*; bytes [0,186), supplied lines 1–5; excerpt SHA-256 *verified*. Copy citation names Evidence, association, source, snapshot, artifact, revision, both digests, bytes, lines and a pinned link; **no artifact body**. The pinned link reopened in a fresh browser shows the same source, artifact, revision and range. The page distinguishes excerpt verification, full-artifact integrity (not verified) and claim truth (not established). |
| 3 | PASS | PASS | *Back to originating investigation* restores J-05, the Evidence tab and focus on the originating link (and, on desktop, a 400 px page scroll set before leaving; scroll restoration was not separately exercised on phone, where the return lands on the Detail pane), for E871, E875 and E880. E875: the JSON artifact lists the generated caller `generated/protocol_client.cpp:42` after the refresh. E880: a counterexample comment, fresh data also reports no callers for a genuinely unused helper, so refreshing does not guarantee callers. Roles stay supplied; the UI concludes nothing. Browser Back also restores J-05 with focus on the originating link. |
| 4 | PASS | PASS | The comparison opens with **no run selected** (every run field "Not supplied / unavailable"); runs chosen explicitly. Outcomes: A failed and was reverted; B "the corrected build passed … it does not establish which difference caused it". PKT-Retry's E875 resolves through `REF-PKT-Retry-E875` to `ES-Discovery`; Back returns to the packet's Contents with focus on that link. **PKT-Retry does not contain J-05** (D42, E875, J-04 only); J-05 is published at 16:40, after the retry. |
| 5 | PASS | PASS | See "What the records establish" below. |
| 6 | PASS | PASS | Later-ticket scenario, source `SRC-Later`: PKT-Later includes J-05 as a recall and delivery is acknowledged, but there is no output-citation receipt and "No benefit evaluation supplied". Inclusion and delivery are visibly distinct from benefit. |
| 7 | **FAIL (F2)** | **FAIL (F2)** | Phone List/Detail switching and selected-artifact identity, Back, copied-link reload, light and dark themes, and 200% zoom pass, with no horizontal overflow on any page at 390 px or at 200% zoom. **Keyboard tabs fail in the Evidence reader when an artifact is selected (F2).** Scenarios: partial (incomplete associations, UNAVAILABLE explanation missing), historical-unavailable (410), denied (403), not-found (404), unsupported (no body requested), unknown (raw value with warning), hash-mismatch (**rejected excerpt not shown**), binding-mismatch (rejected; F3), malformed (rejected), hostile (ANSI, bidi and invisibles shown as code-point markers; `<script>` as text), missing (F4), stale and refresh-error (after a failed refresh, the valid prior data stays, marked "STALE / DISCONNECTED — displaying valid prior data"). **Unavailable mappings do not resolve by Evidence ID resemblance:** in later-ticket, CLANGD-E871 and E875 show "no inspection mapping supplied" with no link, although E875 has a mapping in the story scenario. |

### What the records establish (task 5)

- **Established (as supplied records):** the removal on the stale database failed to build and was reverted (E871, ART-Removal); after refreshing `compile_commands` the generated caller appears in references (E875, ART-Discovery); a fresh database can also report no callers for genuinely unused code (E880, ART-Counter); the retry run was prepared, delivered and cited CLANGD-E875 in its output; the retry's record reports the corrected build passed.
- **Unknown:** whether the refresh *caused* the retry's success (the record itself disclaims it); whether the retry's agent attended to anything in the packet beyond the cited E875; whether the excerpts are complete coverage of their sources' artifacts beyond the supplied byte ranges; any benefit of J-05 to the later ticket (delivered, never cited, never evaluated).
- **Distinct, and kept distinct by the UI:** excerpt coverage (byte range), inclusion (packet contents), delivery acknowledgment (receipt), output citation (receipt) and evaluated benefit (none supplied). Neither the E871 diagnostic nor the retry's outcome proves causal benefit.

## Findings

### F2. Moderate: arrow-key tab navigation breaks in the Evidence reader when an artifact is selected

- **Steps:** open `…/evidence/inspect?fixture=F1&evidence_reference=REF-J05-CLANGD-E871&evidence_source=ES-Removal&evidence_artifact=ART-Removal&evidence_revision=1&evidence_tab=record&evidence_case=story&evidence_pane=list`; focus the *Record* tab; press →.
- **Observed:** *Artifacts* becomes selected, but focus moves to the heading "ART-Removal · revision 1". Further →, End and Home do nothing; *Provenance* is unreachable by arrow keys. The same happens pressing ← from *Provenance*.
- **Expected:** focus stays on the newly selected tab (the tabs pattern every other tab list here follows: the reader without a selected artifact, the Journal detail, the packet sections).
- **Likely cause:** the artifact detail's focus-on-render runs when the Artifacts panel mounts with an artifact already selected. Focus should move there only when the user selects an artifact, not when the tab is activated.

### F1. Minor: the story fixtures supply non-canonical result values

- **Observed:** every story Evidence record shows "Reported result: **Unknown value:** FAIL" (E871) or "Unknown value: PASS" (E875, E880).
- **Cause:** the accepted contract's known `result` values are lowercase (`pass`, `fail`, `inconclusive`, `blocked`); the preview fixtures supply `FAIL` and `PASS` (`web/src/api/preview/evidence/fixtures.ts`). The UI behaves correctly; the fixture is wrong, so the main story exercises the unknown-value path instead of the normal one.
- **Fix:** lowercase values in the story; keep uppercase (or another unknown value) only in the `unknown` scenario if that path needs coverage.

### F3. Minor: binding-mismatch shows the same alert twice

- In `evidence_case=binding-mismatch` with ART-Removal selected, the Artifacts panel shows two identical "Could not load this projection / Artifact source binding mismatch" alerts, each with its own Retry button. One alert (or one per distinct failing request, labelled) is expected.

### F4. Minor: contradictory status when no associations are supplied

- In `evidence_case=missing` with ART-Removal in the link, the status reads "Selected artifact: ART-Removal · **outside the displayed page**" while the panel says "No artifact associations supplied" and an alert says the selected identity is unavailable. "Outside the displayed page" implies the artifact exists on another page. Expected wording along the lines of "Selected artifact: ART-Removal · unavailable".

## Notes (not findings)

- **Whole-artifact excerpts.** For all three artifacts the excerpt covers the full supplied size and its verified hash equals the supplied full digest; the UI still says full-artifact integrity is not verified. Defensible, since the size is also supplied; a short "excerpt covers the full supplied byte range" note would read better.
- **Review environment.** The demo server's `stale` and `refresh-error` scenarios keep state across sessions: after their first load, a fresh page load returns 500 with no prior data. Reviewers need a server restart to see the initial state; worth a line in the packet. The handoff also omitted that the pinned builder lives in Ubuntu's own Docker (`/snap/bin/docker`), now acknowledged.
- **Retracted during review:** the Journal reference links' accessible names are correct ("CLANGD-E871 · Removal build failure"); two snapshot tools displayed the `<code>` child separately, which looked like a missing name.
- `stale` and `refresh-error` behave identically in the reader; acceptable, both are "refresh failure retains marked valid data".

## Evidence

Screenshots and accessibility snapshots for every step are in `steps/` beside this file (desktop, `phone-*`, `zoom200-*`, `dark-*`).

---

# Re-review of the corrections (2026-10-04)

- **Source:** `e875e81b417738dfaa9a43990ebfd330db795094` (`web/docs/w05-review-fixes.md`). Rebuilt independently in my own clone with the pinned offline gate (`/snap/bin/docker`, builder `sha256:ef83c04e…`, `--network none`): **PASS**, 17/17 test files. Served with Node 22.22.2 in the builder image; driven headless with the pinned Chromium, product UI only, desktop 1440×1000 and phone 390×844.
- **Frontend fixture disposition: ACCEPT** for `e875e81`, with one condition on the evidence record (below).

| Finding | Desktop | Phone | Observed |
|---|---|---|---|
| F1 | FIXED | FIXED | E871 "Reported result: fail"; E875 and E880 "pass"; no warning. The `unknown` scenario still shows "Unknown value: FUTURE_RESULT". |
| F2 | FIXED | FIXED | ART-Removal preselected; from the focused *Record* tab: → *Artifacts*, → *Provenance*, ← *Artifacts*, Home *Record*, End *Provenance*: focus stays on the tab every time. A fresh pick of ART-Removal focuses its heading on both layouts (re-clicking an already selected artifact leaves focus on its button, which is reasonable). |
| F3 | FIXED | FIXED | binding-mismatch: one alert, one Retry. |
| F4 | FIXED | FIXED | missing: "Selected artifact: ART-Removal · unavailable"; nothing says off-page. |

## Condition: the correction evidence is not of the commit it names

`web/docs/w05-review-fixes-evidence/result.json` records `source_commit: e875e81…`, but the implementer's build output (`web/artifacts/offline-gate/dist-demo`, index.html written 00:09:11 −04:00) predates that commit (00:12:15 −04:00) and differs from a build of it (different asset files, e.g. `Comparison-K5bd7ILs.js` here vs `Comparison-_2d_wyE7.js` there). The browser suite and screenshots in that folder were therefore produced from an uncommitted working tree. My checks above are of `e875e81` itself, so the product disposition stands; before merge, regenerate the evidence folder from a clean checkout of the commit it names (or record the actual source), and make the freeze step build from the committed tree so the two cannot diverge again. In the original round the builds happened to match.
