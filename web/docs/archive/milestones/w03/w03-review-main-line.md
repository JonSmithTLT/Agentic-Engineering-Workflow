# W03 independent task review

Status: REVIEWED. This is a frontend task review only. It does not adopt the Journal preview 0.1.0 backend schema and does not claim live integration.

- **Reviewer:** the main-line AEW lead-dev agent (Claude Code), at the operator's request on 2026-10-03. The reviewer did not take part in implementing W03.
- **Reviewed source commit:** `6e83b9516b0ef77c0838b88bd29204ed70e59015`, the source freeze in `web/docs/w03-evidence/result.json`. Branch head `190fcd1` adds only evidence and docs.
- **Preview SHA-256:** `72f0cb0b1a675bf809f4b1f3026a322cfc0e8da20f5e6c3f53e162f2bda48df8`. This is the value recorded in `result.json`; the reviewer did not recompute it.
- **Build reviewed:** the existing compiled demo build `web/artifacts/offline-gate/dist-demo`, built at 14:24 −04:00 by the implementer's offline gate. Its file-list SHA-256 (the hash of `sha256sum` lines in sorted path order) is `5a12a5f811f7183227c5e855446b51a190e9dd903aace58f32d0174bdca35d39`.
- **Commands actually rerun:** none of the gate commands. The pinned carrier `sha256:ef83c04e…` is no longer in the local Docker engine, so the offline gate could not be rerun as pinned validation, and no other Node version was used as a substitute. The demo was served with `node node_modules/vite/bin/vite.js preview --mode demo --host 127.0.0.1 --port 4252 --strictPort` from `web/`.
- **Browser:** Chrome for Testing 147.0.7727.15 (the staged revision 1217), run headless and driven through Playwright over CDP. The Claude desktop app's built-in browser pane could not be used, because it refuses service-worker registration and the demo's mock layer needs one. That is an environment limitation, not a W03 defect.

| Layout | Hypothesis J-02 | Failed removal J-03 | Discovery J-04 | Lesson J-05 | Supporting E871/E875 and opposing E880 | Canonical D42 | Partial graph and plural Ticket references | Outcome |
|---|---|---|---|---|---|---|---|---|
| Desktop 1440×1000 | Established | Established | Established | Established | Established | Established | Established | All steps established; findings 3 and 4 |
| Phone 390×844 | Established | Established | Established | Established | Established | Established | Established | All steps established; findings 1–4 |

## Method

All interaction went through visible UI only: clicking by visible text and role, pressing keys, screenshots, and the rendered page text. The reviewer did not inspect fixture source, did not use the API panel, Demo scenario selector, Contract tools or browser developer tools to find answers, and did not call the API directly. The Journal scenario stayed on its default, `story`. Browser console access was used once, only to diagnose why the built-in pane rendered blank (the service-worker rejection); nothing in the record below came from it.

## Desktop (1440×1000)

1. **Knowledge → Journal → J-05**, "Refresh compile_commands before judging missing callers" (applicability CURRENT).
   - **Claim:** refresh the compilation database before using missing clangd references as evidence that a function is unused.
   - **Conditions:** clangd 19 with generated protocol callers; refresh compile_commands for the evaluated revision.
   - **Limitation:** fictional example; no live AEW learning.
   - **Why retained:** the supplied fictional failure/fix pair.
2. **Provenance → `J-02 · related_to` → Summary.** The mistaken hypothesis: missing index references were read as absence of callers (UNCHECKED).
3. **`J-03 · contradicted_by`.** The failed removal: deleting the function broke generated protocol callers, and the change was reverted. J-03's own Provenance shows `J-02 · originated_from` rather than a mirrored relation. That is supplied data and is displayed as supplied.
4. **`J-04 · followed_by`.** The new discovery: refreshed compile_commands exposed generated callers the previous index had omitted.
5. **`J-05 · contributed_to`.** Back to the conditional lesson in step 1.
6. **Evidence.**
   - Supporting: `CLANGD-E871` (removal build failure) and `CLANGD-E875` (refreshed database reveals callers).
   - Opposing: `CLANGD-E880` (a fresh database can also confirm genuinely unused functions).
   - Each is labelled "evidence_reference; supplied reference, no lookup interface". The page states that the roles are supplied and do not independently establish acceptance or applicability. The reviewer did not verify the evidence.
7. **Canonical reference.** `CLANGD-D42` is listed under Canonical references as a decision_reference with no lookup interface, and the page states that canonical decisions remain references to their authoritative records. Journal entry J-06 (`J-06 · references`) says it "does not replace the decision or confer new authority". The advisory-versus-authority distinction is clear.
8. **Origin graph.**
   - Opening "Explore bounded origin graph" and expanding J-05 shows 4 journal nodes and 7 terminal references, each marked "Terminal / unavailable reference".
   - The edge source for `J-05 / relations.4.applies_to / CLANGD-T203` shows the response provenance (revision 42, contract 0.1.0) and states "No edge-specific explanation or receipt supplied".
   - "Show relation list" lists the 11 references and states there is no crawl or completeness claim. "Show graph" toggles back.
   - Partiality is stated in three places.
   - The plural Ticket references are readable:
     - `CLANGD-T181` is the origin work.
     - `CLANGD-T203` is "potential applicability".
     - `CLANGD-T207` is a recall reference with "no delivery or benefit receipt supplied".
   - Nothing in the view presents applicability or recall as a benefit.

Keyboard: after a relation is followed, the next Tab reaches the new record's Summary tab, so the sequential focus point is kept (see finding 3). Clicking an edge source and toggling the list both keep focus on the control.

## Phone (390×844)

The same flow, steps 1–8, was repeated at 390 px.

- Selecting J-05 opens the detail with Close detail and the Stream/Detail switch.
- The J-02 → J-03 → J-04 → J-05 chain through Provenance gives the same Summary content as on desktop.
- The Evidence roles, the D42 edge source and the relation list match desktop.
- The graph scrolls inside its own frame, and Fit to width is available.

**Step 9.** From J-03 on the Evidence panel:

- **Stream** shows the results with the stream's filters.
- **Detail** returns to J-03 with the Evidence panel kept (`panel=evidence`).
- **Close detail** clears the selection and returns focus to the J-03 row link in the stream. The next Tab moves to the following row.

Selection and focus stay usable.

## Findings

All four are minor. None stopped any step from being established through the UI.

1. **Phone: the Stream/Detail switch has no visible active state.** Both buttons look the same whichever view is shown (compare the Journal/Records switch, which marks its current tab). The label "Stream" also collides with the "Display: Stream" option inside the results panel, which means something different. **Suggested fix:** a pressed or current style (with `aria-pressed` or `aria-current`), and distinct wording such as "Results" / "Detail".
2. **Phone: following a relation leaves the new record's ID line under the sticky header.** The page keeps its scroll position near the Provenance list, so after navigation the "J-0n · type" line and the top of the title are hidden. The reader has to scroll up to confirm which record is now shown. **Suggested fix:** scroll the detail heading into view below the sticky header after a relation is followed.
3. **Desktop and phone: no programmatic focus or announcement after a relation is followed.** `document.activeElement` becomes `body`; the Tab order recovers, as described under Keyboard. A screen-reader user gets no sign that the detail changed to another record. **Suggested fix:** move focus to the new detail heading (`tabindex="-1"`) or announce the change in a polite live region.
4. **Graph wording: journal records are labelled "unresolved reference".** J-04, J-03, J-02 and J-06 appear on the same results page, but in the expanded graph each is labelled "journal · unresolved reference" until it is expanded. That can read as "record missing". **Suggested fix:** use wording such as "not expanded", keeping "unresolved" for references that cannot be loaded.

## Not covered

- The review was not done by a human on a real touch device. Phone width was emulated in a desktop-class headless browser.
- Keyboard use was spot-checked (Tab after relation navigation, and focus after close), not swept across the whole page.
- Dark mode, the non-`story` Journal scenarios, paging and production exclusion were outside the task. They remain covered only by the implementer's automated evidence.
- The pinned offline gate was not rerun (see header).

## Confirmation

The reviewer did not use developer tools or fixture-source inspection in place of the UI to answer any step.

## Disposition

**Changes required (minor).** All nine task steps were established through the UI on both layouts, and the provisional, supplied-reference, partial-graph and authority boundaries read correctly. Findings 1–4 are small UI fixes. Under the project's fix-findings-in-the-PR rule, they should be fixed on this branch before merge rather than deferred. A re-check of those four points is enough after the fixes; the full task review does not need repeating. Frontend acceptance does not adopt the preview backend schema or claim live integration.

## Re-check of findings 1–4 (2026-10-03)

- **Reviewed:** fixing source `2e29a7124738a19a89116a969c5979982badd8ec` (head `d3cd9b6` adds only evidence). The reviewer read the source diff from `190fcd1` to `2e29a71` and re-checked each finding in the UI.
- **Served by:** the operator's running service-worker-free HTTP demo (`scripts/demo-server.mjs`, `http://127.0.0.1:4249`), in the Claude desktop app's built-in browser, which the worker-free mode now makes usable.
- **Layouts:** desktop 1440×1000 and phone 390×844 (emulated).
- **Measurement:** focus and positions were read in the page (`document.activeElement`, bounding boxes) to measure focus and scroll, not to find any task answer.

| # | Finding | Result |
|---|---|---|
| 1 | Phone Stream/Detail switch has no active state; "Stream" collides with Display | **Fixed.** The switch reads "Results" / "Detail · J-05", the current one is visibly marked (`aria-pressed` kept), and "Selected: J-05" is shown. |
| 2 | Phone: the followed record's ID line is under the sticky header | **Fixed.** After J-05 → `J-02 · related_to`, the heading "J-02 · The function might be dead code" is at 553 px, below the 108 px header, and carries the ID. |
| 3 | No focus or announcement after following a relation | **Fixed.** Desktop and phone: the new detail heading (`tabindex="-1"`) receives focus once the entry loads (about 0.5–1.5 s on the HTTP demo; until then focus is on `body`). On desktop it sits at 102 px, below the 87 px header. |
| 4 | Graph labels loadable journal records "unresolved reference" | **Fixed.** Unexpanded journal nodes read "journal · not expanded"; work, evidence and decision references read "unavailable reference". |

**New finding 5 (minor, introduced by the fix for 3; desktop keyboard).** The heading-focus effect runs on every selection, not only after a relation is followed. On desktop, where the list and the detail are both visible, choosing an entry from the list moves focus out of the list to the detail heading. Shift+Tab from there goes to the *last* entry in the list ("A lesson with no publication timestamp", J-07), not the entry just chosen. With 50 entries per page, a keyboard user browsing the list loses their place on every selection. The page also scrolls (86 px here).

**Suggested fix:** move focus to the heading when the detail replaces the results (the phone layout) or when the navigation started inside the detail (a relation, the graph, Jump to ID). On a desktop list selection, leave focus on the selected link (`aria-current` already marks it) and announce the change politely if wanted. Re-check: the same three navigations on desktop and phone, plus Shift+Tab after a desktop list selection.

The operator additions (the type legend, the wrapping source controls, the HTTP demo mode) raised no concern. The demo-only fetch headers sit behind `import.meta.env.MODE === 'demo'`, and `check-production.mjs` now also rejects their names. The legend's symbols are `aria-hidden` and the type name stays in text, so they add no screen-reader noise.

**Disposition of the re-check: changes required (minor), finding 5 only.** Findings 1–4 are fixed. The task review itself does not need repeating.

## Re-check of finding 5 (2026-10-03)

- **Reviewed:** fixing source `7433ddd` (head `ac928bd` adds evidence). The diff makes two changes:
  - the detail captures, at mount, whether focus was on a results link, and skips the heading focus for a list selection at desktop width (`min-width: 1024px`);
  - the "Selected" line becomes a `status` live region for the Journal.
- **Remount check:** `JournalDetail` is keyed by entry id, so the origin is captured fresh on every selection rather than going stale.
- **Served by:** the HTTP demo at `127.0.0.1:4249`, in the built-in browser. Focus and positions were measured in the page as before.

| Check | Result |
|---|---|
| Desktop, a list selection by mouse (J-04) | Focus stays on the J-04 link after the entry loads; Shift+Tab reaches J-06 (the previous entry) and Tab reaches J-03 (the next). The list keeps its keyboard position. |
| Desktop, a list selection by keyboard (Enter on J-03) | Focus stays on the J-03 link. The "Selected: J-03" line is a `status` region, so the change is announced. |
| Desktop, a relation followed after a list selection (J-03 → `J-04 · followed_by`) | Focus moves to the "J-04 · The compilation database was stale" heading, at 102 px below the 87 px header. Finding 3's fix still holds. |
| Phone 390×844, a list selection (J-02) | Focus moves to the "J-02 · The function might be dead code" heading, at 289 px below the 108 px header (the detail replaces the results). |

**Disposition: ACCEPT.** Findings 1–5 are fixed and no new concern was found. This is frontend task-review acceptance only. It does not adopt the preview backend schema or claim live integration.
