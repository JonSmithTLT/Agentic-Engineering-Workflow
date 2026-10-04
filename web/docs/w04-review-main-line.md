# W04 independent product-UI review record

Disposition: **changes required (minor)**. See "Findings" and "Disposition" at the end.

- **Reviewer and date:** the main-line AEW lead-dev agent (Claude Code), on 2026-10-03 at the operator's request. The reviewer did not take part in implementing W04.
- **Source:**
  - Source commit: `2f271c0e7f1524ecfe95bfb4b6786c820677cc86`, the `source_commit` in `web/docs/w04-evidence/result.json`. The branch head is `71a02a3`, which adds only evidence.
  - Preview digest: as recorded in `result.json`. The reviewer did not recompute it.
- **What was served:**
  - The operator's running worker-free HTTP demo, `scripts/demo-server.mjs` on `127.0.0.1:4249` (pinned Node 22 launcher).
  - It served the compiled `dist-demo`, built at 18:33 −04:00. Its `index.html` timestamp is two minutes before the 18:35 commit of `2f271c0`, so the build was taken from the working tree just before that commit. The reviewer did not rebuild it.
  - The gate was not rerun.
- **Browser:** the Claude desktop app's built-in browser (Chromium). The worker-free mode makes it usable.
- **Layouts:** desktop 1440×1000, and phone 390×844 emulated in that browser.
- **Method:**
  - Product UI only: clicking by visible label, real key presses, screenshots, and the rendered page text.
  - In-page JavaScript was used only to measure: the focused element, scroll offsets, horizontal overflow, label association and the clipboard fallback's field.
  - It was never used to find a task answer.
  - No fixture source, API, Contract or Scenario panels were opened. The Investigation scenario stayed at `story`.

| Layout | Steps actually performed | Invocation / source / snapshot / run / packet IDs observed | Starting context and differences established | Recorded outcomes | Preparation / delivery / citation / benefit availability | Canonical references | Usability failures / unresolved questions |
|---|---|---|---|---|---|---|---|
| Desktop failed-removal → retry | 1–5, 7 | A: SRC-Removal / CLANGD-INV-Removal / SNAP-Removal (captured 2026-10-02T16:20Z) / CLANGD-R-A2-2 (launched 16:16Z), work CLANGD-T181. B: SRC-Retry / CLANGD-INV-Retry / SNAP-Retry (16:38Z) / CLANGD-R-A2-4 (16:34Z), same work. Packets PKT-Removal, PKT-Retry | Configuration differs only in source revision (`stale-db-fictional` vs `refreshed-db-fictional`). Work revision `plan-3`, environment Rocky 8 · clangd 19, model, provider, profile, capability and prompt id, version and digest are the same. Card id is unavailable on both. Created at differs (16:15 vs 16:32) | A: "Removal broke generated protocol callers; the change was reverted." B: "…generated callers were identified and the corrected build passed. The record reports success; it does not establish which difference caused it." | PKT-Removal: preparation RECEIPT-Removal-PREP (16:15Z, RECORDED); no delivery, citation or benefit supplied. PKT-Retry: preparation RECEIPT-Retry-PREP (16:33Z), delivery RECEIPT-Retry-DELIVERY (16:34Z, ACKNOWLEDGED), citation RECEIPT-Retry-CITATION (16:38Z, "Output explicitly cites CLANGD-E875"), no benefit evaluation. Each receipt is bound to its packet, source, invocation, run and snapshot | CLANGD-D42 "Generated protocol definitions remain source-controlled" (decision reference; reference only) in both packets | Findings 1, 2, 3 |
| Phone failed-removal → retry | 1, 2, 3–4 (contents, receipts), 7 (Change, tabs, Back) | As on desktop | As on desktop | As on desktop | As on desktop | As on desktop | Finding 3 (chooser on a phone); finding 1 as on desktop. Back to comparison works correctly on phone |
| Desktop later-ticket inclusion | 6, 7 | B changed to SRC-Later / CLANGD-INV-Later / SNAP-Later (17:20Z) / CLANGD-R-LATER; packet PKT-Later; work CLANGD-T203 | Changing B kept A and its run and cleared B's previous run, as it should. Swap moved each side's source and run together | PKT-Later includes J-05 as historical recall ("Published 2026-10-02T16:40:00Z"), followed through the J-05 link to the Journal and back | Preparation RECEIPT-Later-PREP (17:00Z); delivery RECEIPT-Later-DELIVERY (17:01Z, ACKNOWLEDGED); no output citation; no benefit evaluation | CLANGD-D42 | Finding 2 (also on browser Back from the Journal: focus restored, scroll at top) |
| Phone later-ticket inclusion | Change B to SRC-Later and its packet, on the same flow as desktop (not repeated end to end) | As on desktop | As on desktop | As on desktop | As on desktop | As on desktop | None beyond finding 3 |

## Investigation answers

1. **The sources, chosen explicitly.**
   - A is SRC-Removal (failed removal); B is SRC-Retry (corrected retry). Both belong to work CLANGD-T181, "Investigate missing callers".
   - Runs are optional and start as "Invocation only — no run selected". The runs chosen, CLANGD-R-A2-2 and CLANGD-R-A2-4, went into the URL only when selected.
2. **The outcomes and starting context.**
   - The removal failed and was reverted; the retry's corrected build passed.
   - The only configuration difference is the source revision (stale vs refreshed compilation database).
   - The page states "Differences do not establish causation", and the retry summary declines to say which difference caused success. No causal claim was made.
3. **PKT-Removal.**
   - Current constraint: CLANGD-D42. Mistaken hypothesis: J-02 ("missing index references suggest dead code"). Both are at `stale-db-fictional` and both are excerpts ("not the entire authoritative record").
   - There is a preparation receipt and no delivery receipt.
   - The absence is shown as "No delivery receipt supplied." The page does not say that this leaves delivery unknown rather than disproved; see finding 1.
4. **PKT-Retry.**
   - It contains CLANGD-E875 ("Refreshed compile_commands reveals generated callers"), J-04 ("The compilation database was stale") and CLANGD-D42, all INCLUDED and all excerpts.
   - Selection: "Explicitly selected by the fictional context policy".
   - Accounting: 1420/4000 tokens and 4200/16000 bytes, under policy `context-v1`, triggered by WORK_START.
   - Prepared at 16:33Z.
   - **J-05 is absent.** The retry's preparation (16:33Z) predates J-05's publication (16:40Z).
5. **Delivery and citation, each shown separately.**
   - Delivery was acknowledged at 16:34Z; a citation of CLANGD-E875 was recorded at 16:38Z; no benefit evaluation was supplied.
   - The page says "No attention or influence is inferred", and the reviewer infers none.
6. **SRC-Later and PKT-Later.**
   - The packet includes J-05 as historical recall, and delivery was acknowledged at 17:01Z. There is no output citation and no benefit evaluation.
   - **Neither inclusion nor acknowledgment proves benefit.** Inclusion means the router put J-05 in the prepared packet. Acknowledgment means the delivery mechanism reports the packet was received. Neither says the model read, used or relied on J-05. Only an output citation would show it was used, and only a benefit evaluation would show the outcome improved. Neither was supplied, and the page's "Included in context references do not establish delivery, use, or benefit" says the same.
7. **Controls.**
   - Change: focus returns to the Change button.
   - Optional runs: explicit, and kept in the URL.
   - Swap: carries each side's source and run together, and focus stays on Swap.
   - Tabs: work.
   - Show differences: persists in the URL.
   - Back to comparison: correct on phone; desktop has finding 2.
   - Copy dashboard link: in this browser the clipboard is blocked. The UI correctly falls back to "Clipboard unavailable. Select and copy this link." with the link in a field. Loading that link restored both sources, B's run, the References tab and Show differences.

## Findings

1. **A missing receipt reads as "not supplied", never as unknown** (both layouts; content). The Receipts tab says "No delivery receipt supplied" or "No output citation receipt supplied", and nothing on the page says that a missing receipt does not establish the event did not occur. The packet requires this ("Missing receipts never establish that an event did not occur") and task 3 asks it to be established through the UI. A reader can take PKT-Removal's missing delivery receipt as "not delivered". The stage legend ("Prepared ≠ delivered ≠ …") separates stages but doesn't cover absence. **Suggested fix:** one line under each empty stage, or once on the tab, such as "Not supplied by this projection: whether it happened is unknown."
2. **Desktop: Back to comparison loses focus and scroll** (desktop only; it works on phone). Returning from a packet leaves focus on `body` and scrolls the page to the top. This reproduced three times, with and without switching inspector tabs, and still held 3 s later. On phone, the same action returns focus to "Inspect PKT-…" and scrolls back to it. On a 1440 px desktop, the reader lands at the top of a long comparison, far from the References row they left. Browser Back from the Journal restores focus to the packet heading but also leaves scroll at the top. **Suggested fix:** use the phone's restoration path on desktop: focus the originating Inspect button and scroll it into view.
3. **The source chooser doesn't show summaries** (both layouts; worse on phone). Task 1 asks to identify the failed removal and the retry "through their supplied summaries". The chooser's rows show source, invocation, work, status and snapshot time, but no summary. The reader has to pick by ID and then check the comparison, and the IDs only happen to be descriptive here. On phone, the table is 829 px wide in a 324 px scroll frame, so work, status and snapshot time need sideways scrolling, though the select buttons are visible. **Suggested fix:** show the supplied summary (truncated) in the row, or as a second line under the source ID. On phone, consider a stacked row layout.

No other concerns:
- Labels are correctly associated: the run selectors and the Show differences checkbox each have one label. The browser tool's own tree mislabelled them, which the reviewer checked and did not count.
- The page never scrolls sideways at 390 px.
- Packet focus lands on its heading.
- Every "reference only" and "excerpt" disclosure is present.
- Canonical CLANGD-D42 is a reference to an authoritative record, never authority itself.

## Not covered

- Real touch devices: the phone width was emulated.
- The non-`story` Investigation scenarios: partial, missing, denied, stale, hostile and the rest.
- Paging in the large fixture.
- Polling and 304 behaviour.
- Dark mode.
- A full keyboard sweep: keyboard use was spot-checked with Enter on Inspect.
- The worker-backed adapter: only the HTTP demo was used.

These rest on the implementer's automated evidence.

## Disposition

**Changes required (minor).** Every investigation task was established through the UI on desktop, and the key steps on phone. The provisional, reference-only, excerpt, supplied-accounting, no-causation and no-benefit boundaries read correctly. Findings 1–3 should be fixed on this branch before merge under the project's fix-in-PR rule. Finding 1 is the substantive one because it concerns how absence is understood. A re-check of the three findings is enough afterwards.

This disposition gates frontend fixture acceptance only. It does not adopt the preview backend schema and does not claim live integration.

## Re-check of findings 1–3 (2026-10-03)

- **Scope:** the same reviewer re-checked the three findings against the fix response (`w04-review-fix-response.md`).
- **Source:** fix commit `2808149` (`source_commit` in `w04-review-fixes-evidence/result.json`); evidence freeze `f304fcc`; branch head `dc89af1`. The reviewer did not recompute the preview digest.
- **What was served:** the same worker-free HTTP demo on `127.0.0.1:4249`. Its `dist-demo/index.html` was built at 19:13 −04:00, three minutes before the 19:16 fix commit, so it was built from the working tree just before that commit. The reviewer did not rebuild it.
- **Method:** as for the original review. Product UI by visible label. In-page JavaScript only for measurement (the focused element, scroll offsets, rects, overflow) and for reading the rendered tab panel's text.

| Finding | Re-check performed | Result |
|---|---|---|
| 1. A missing receipt reads as "not supplied", never unknown | Desktop: SRC-Removal / SRC-Retry → References → Inspect PKT-Removal → Receipts | **Fixed.** The tab opens with "Missing receipts mean the event is unknown in this projection; they do not establish that it did not occur." Each empty stage keeps its exact text ("No delivery receipt supplied.", "No output citation receipt supplied.", "No benefit evaluation supplied."). |
| 2. Desktop: Back to comparison loses focus and scroll | Desktop at 1440×1000: Inspect PKT-Removal → Receipts → Back. At 1440×600, so the page really scrolls: Inspect PKT-Retry with the page scrolled to its maximum (446) → Back. Then the J-04 Journal link at scroll 672 → browser Back. Phone 390×844: Inspect PKT-Retry at scroll 888 → Back | **Fixed.** Measured 3 s after each return: <br>• 1440×1000: focus on "Inspect PKT-Removal", scroll 46 → 46. <br>• 1440×600: focus on "Inspect PKT-Retry", scroll 446 → 446, the button at top 463 px, below the sticky header (bottom 87 px). <br>• Journal round trip: focus on the J-04 link, scroll 672 → 672. <br>• Phone (no regression): focus on "Inspect PKT-Retry", scroll 888 → 888, the button inside the viewport. |
| 3. The chooser shows no summaries; the phone table scrolls sideways | Desktop and phone: Change A / Change B choosers | **Fixed.** <br>• Every row shows its supplied summary under the source, including both CURRENT-INV rows. The failed removal ("Removal broke generated protocol callers; the change was reverted.") and the corrected retry are identifiable by summary alone. <br>• At 390 px each row stacks into a 324 px card with labelled cells (Invocation, Work, Status, Snapshot / captured UTC) and keeps `row` and cell semantics. <br>• The page has no horizontal overflow; the only overflowing element is the table header, apparently visually hidden in this layout. |

**Disposition: ACCEPT.** Findings 1–3 are resolved, and the earlier investigation answers still hold. This disposition is frontend fixture acceptance only. It does not adopt the preview backend schema and does not claim live integration.
