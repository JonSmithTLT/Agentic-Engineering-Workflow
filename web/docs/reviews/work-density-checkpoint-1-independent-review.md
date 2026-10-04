# Work cleanup checkpoint 1: independent review (main line)

- **Reviewer:** Claude (Opus 5.5), the AEW main-line lead developer agent. Not the implementer.
- **Date:** 2026-10-04.
- **Reviewed:**
  - runtime commit `c899c70d205b9c88cdd0314ef99f580c218e6a5f`, tree `6e53d2ca3f31409ab772907dafde0354fd22406d`, as the packet states;
  - the packet `web/docs/reviews/work-density-checkpoint-1.md` at the evidence commit `ee9342c` (PR #52).
- **Disposition: CHANGES REQUESTED (narrow).** One finding on phone (F1) and one minor finding (F2).
  - Everything else the packet asks a reviewer to check holds.
  - The reorder achieves its measured goal on desktop and on a directly opened phone detail.

## Build and serving

- **Rebuilt in my own clone**, detached at `c899c70`, with the pinned offline gate.
  - `SPT_FRONTEND_IMAGE=sha256:ef83c04e…8407`, `--network none`.
  - Result: **PASS**, 19 files and 167 tests.
- **Byte-identical to the implementer's build:**
  - `dist-demo`: all 33 files match the implementer's `dist-demo.SHA256SUMS` from `ee9342c`;
  - `dist`: all 4 files match `dist.SHA256SUMS`.
- **Served by my own container on port 4261.** The served entry bundle `index-BsnxrV4t.js` matches my build.
- **Browser:** the pinned Chromium (revision 1217), headless through Playwright, driving the product UI only, with no service worker.
- **Layouts:** desktop 1440×1000; phone 390×844 with touch; "200%" as 720×500 at device scale 2.

## F1 (major, phone): choosing a child from Results opens Detail scrolled into the middle of the record

- **Steps (phone 390×844):**
  1. Open `/work?selected=S-0001`.
  2. Inspect children.
  3. In Results, select "Validate projection consistency" (T-0001).
- **Observed:**
  - The URL becomes `…&selected=T-0001&work_pane=detail`, as designed.
  - The page keeps the Results pane's scroll position (`scrollY` 652). The viewport shows T-0001's "Backend blockers and reasons" and its facts.
  - The record's title, kind and state (T-0001, RUNNING) are above the viewport, and focus is on `<body>`.
  - Screenshot: `screens/t2b-phone/02-2-detail-after-select.png`.
- **Why it matters:**
  - This is the checkpoint's own new path ("selecting a Work reference returns to Detail").
  - It undoes the checkpoint's purpose for the most common phone navigation: content that leads at y=439 when the record is opened directly is skipped entirely here.
  - A keyboard or screen-reader user also loses their place.
- **Expected:** the same treatment Inspect children already gets (desktop heading top 103 against a header bottom of 87; phone 307 against 108):
  - entering Detail from a Results selection starts at the top of the detail;
  - focus moves to the record heading, below the sticky header.

## F2 (minor, phone): after browser Back to Results, focus is on a heading off-screen

- **Steps:** after F1's selection, press browser Back.
- **Observed:**
  - The URL returns to `…&work_pane=results`, and the restored scroll (652) shows the rows. That part is good.
  - But focus is on the Results `h1`, at top -324, above the viewport.
  - A keyboard user's next Tab starts from an element they cannot see.
- **Expected, either of:**
  - focus returns to the row link that was selected;
  - the focused heading is brought into view below the header.

## What holds (the packet's reviewer tasks)

- **T-0003 and its blocker; Why state** (desktop and phone):
  - title and BLOCKED lead; then intent; then the supplied `blocked_by` ("Waiting for the cache repair review", `DEPENDENCY_BLOCKED`); then relations;
  - Why state says "Reasons supplied for this record; no explicit binding to this status", "No reasons supplied" and "No explanation supplied for this status". It lists the supplied `blocked_by` separately ("Reason codes are opaque…").
  - It is not an inferred explanation.
- **Inspect children** (desktop and phone):
  - Results is shown with the parent filter S-0001;
  - S-0001 stays selected (`selected=S-0001&parent=S-0001&work_pane=results`);
  - focus is on the Results heading below the sticky header;
  - a status explains that the selected record is outside the loaded page or filter "…this does not mean the record is unavailable".
  - On desktop, Back restores the Results view with the heading in view. Phone Back is F2.
- **Copy and reload (phone):**
  - Copy dashboard link on the Results pane gives `…&work_pane=results`;
  - opening it restores Results;
  - the "Detail · S-0001" switch shows S-0001's detail.
  - A legacy `/work?selected=T-0003`, with no `work_pane`, opens Detail.
- **Invalid pane:**
  - `work_pane=bogus` shows "Unsupported presentation value. No projection request was sent."
  - Only the shell's project, capabilities and overview reads went out, with no Work read.
- **Concealed detail reads stop.**
  - With the phone on Results and S-0001 selected, 12 s of traffic held only `overview`, `capabilities`, `project` and `work?limit=100&parent=S-0001`.
  - There was no detail read for the hidden record.
- **Facts and disclosure:**
  - All 18 projection facts are present for T-0003 (F1, F8, F11), T-0004 (F3, archived) and on the direct `/work/T-0003` page.
  - "Source and browser metadata" is a native disclosure, closed by default. It opens to the source (project, revision, generated, contract) and the browser observations, which keep their "not backend health or provenance" label.
- **Warnings stay outside the disclosure:**
  - F10's backend error ("Could not load this projection… Retry") is visible with the disclosure closed;
  - so are F11's unknown-value warnings ("Unknown value: FUTURE_WORK_STATE", the unknown capabilities).
- **Long and hostile content, dark mode:**
  - F8 T-0003 on phone and at 200% has no page overflow; the title and state lead.
  - On the Results pane, the Work table is wider than the viewport inside its own scroll container, the pattern accepted in W05 and W06.
- **Keyboard (desktop):** Tab order follows the new content order:
  1. Compare invocations, then Copy CLI;
  2. the related record;
  3. Parent, then its Copy CLI;
  4. the three Why buttons;
  5. Inspect relations;
  6. the metadata summary, which Enter toggles.
- **No page errors** in any run.

## Not covered by this review
- **Real browser zoom:** "200%" is a 720-px viewport at device scale 2, as in W06.
- **A refresh failure while data is shown:** F10 covers a load failure only.
- **The unaffected layouts:** I did not re-run a full comparison of Runs and Evidence detail; the implementer's W01–W06 regressions cover those.
- **Physical devices.**

The driver, step files and outputs are in `driver/`, and the screenshots in `screens/`.
