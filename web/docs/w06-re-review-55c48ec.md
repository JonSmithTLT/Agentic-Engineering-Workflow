# W06 independent re-review (main line)

- **Reviewer:** Claude (Opus 5.5), the AEW main-line lead developer agent. Not the W06 implementer.
- **Date:** 2026-10-04.
- **Reviewed:**
  - correction source `55c48ec5054a4b6830722978b36bfc4e0d55ff60`, tree `96021ffadbb182482c03d823909ce81dd371a51b` (matches `result.json`);
  - `web/docs/w06-review-corrections.md` at the evidence commit `0051035`;
  - against my review of `d15bc13` (`w06-review-main-line.md` in this folder).
- **Frontend fixture disposition: ACCEPTED.**
  - F2 and F1 are fixed; N1, N2 and N4 are fixed.
  - N3's deferral is reasonable as argued (separate validated read contexts; the overview cadence belongs to the shared provider).
  - The full first-review run shows no regression.
- Backend adoption and live integration were not assessed, and nothing here claims them.

## Build and serving

- **My own clone, detached at `55c48ec`.** The pinned offline gate passed: 19 files, 164 tests (`--network none`, builder `sha256:ef83c04e…8407`).
- **My `dist-demo` is byte-identical to the implementer's.** `sha256sum -c` against `dist-demo.SHA256SUMS` at `0051035` passes for all 33 files.
- **Served by my own container on port 4261.** I confirmed the served `index-MUerYzgJ.js`, `Recorder-BrfT7VEn.js` and `index-DWAoQmdF.css` match my build.
- **Browser:** the pinned Chromium (revision 1217), headless through Playwright, driving the product UI only.

## F2 (major): narrow Events and Fanout tables. **Fixed**

- **Method:** for every selection entry in the story Events table (EV-01 to EV-09), the story Fanout table, and the cycles Fanout table (EX-Discovery, EX-Helper, EX-Removal, EX-Retry):
  - hit-tested the button's centre;
  - **clicked it**;
  - checked that the detail opened for that ID;
  - checked for clipped text, overlapping cells and page overflow.
- **Coverage:** at 390×844 (phone, touch) and 720×500 at device scale 2 (200% zoom), each in light and dark themes.
- **Result:** every entry is reachable and opens its own detail, in every layout and theme. There are 0 clipped elements, 0 overlapping cells and no page overflow; the relationship text wraps in full.
- **Desktop (1440 px):** all entries are reachable as well. Long relationship text is not wrapped there, but the table sits in a horizontally scrollable container (`table-scroll`, `overflow-x: auto`), so all of it can be reached, the same pattern accepted in W05.
- No page errors.

## F1 (minor): story provenance kind. **Fixed**

- **Story scenario:** the Provenance panels of every event (EV-01 to EV-09) and every execution show **0** unknown-value warnings. Relation provenance now reads `RECORDER-1 (recording source; reference only)`.
- **Unknown scenario:** it still warns (26 unknown-value warnings across its events' Details and Provenance), so the warning behaviour is intact.

## Nits

- **N1. Fixed.** Coverage is labelled text: lane, completeness, retention, then gap with explanation and source. No raw JSON. Two separately named disclosures appear (Event response metadata, Execution response metadata); each opens its own Source/Browser panels, and nothing repeats by default.
- **N2. Fixed.** A deep-linked packet (`…&execution_locator=LOC-RetryPacket&packet_tab=receipts`) returns to `…&execution_tab=details` with no packet parameters left.
- **N3. Deferred, as argued.** The read pattern is unchanged: the trace is read twice on load, and `/api/v1/overview` loads alongside Controls. It's harmless and documented.
- **N4. Fixed.** Copying a link from the Validation receipts sub-tab gives `execution_control_tab=receipts`, and reloading it reopens on Validation receipts.

## Regression

I re-ran all 24 desktop step files and the phone round-trip file from the first review against the corrected build:
- every step ran, with no errors and no page errors;
- every focus, clipboard, injection (`w06Attack` stays false) and request-pattern result is identical, including the hidden views making no reads;
- the only snapshot differences are the intended ones (F1 provenance, N1 metadata, N2 and N4 URLs).

The driver and step files are in `driver/`, plus the re-review scripts `rr-f2.mjs` and `rr-f1.mjs`.
