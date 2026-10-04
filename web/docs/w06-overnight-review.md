# W06 implementer review and future architecture notes

Date: 2026-10-04. Scope: operator-authorized overnight correctness review and architecture assessment. This is implementer review, not independent acceptance. W06 frontend fixture acceptance remains PENDING. No Engine work records or backend commitments are created.

## Corrective work

| Finding | Evidence | Disposition |
|---|---|---|
| R1: child expansion Retry targeted an already loaded root | `FanoutHierarchy` cleared `pending` in `finally`, then used `pending || trace.root_execution` for Retry. `expand` returns immediately for a loaded root. A failed child therefore could not be retried through the error action. | Fixed in runtime commit `adebe3abf723adca3e262414cd3de9c8060481fe`: retain the exact failed child identity independently of the busy state. Regression test simulates a child 503 followed by success and checks that Retry reissues the child read, without refetching the root. Verified in the clean committed-source freeze of `d15bc135f23340b7fe4e1f8039290410383d2be0`, including all regressions. |
| R2: execution-table off-page selection lacks an explicit note | `EventResults` reports an off-page or unavailable selected event. `ExecutionResults` retains selection/detail but has no equivalent membership note for a selected execution absent from its current table page. | Fixed in `d15bc135f23340b7fe4e1f8039290410383d2be0`; the expanded browser suite verifies the off-page note, separate detail resolution, retained list focus and close-focus restoration. |
| R3: disclosed Controls execution-list failures are not surfaced | `ControlsHost` validates the execution page, but its render path displays `query.error` and `t.error` without displaying `rows.error`. A rejected/failed execution-list projection can therefore appear as an empty chooser. | Fixed in `d15bc135f23340b7fe4e1f8039290410383d2be0`; list errors show a recoverable result, valid empty associations are labeled, and a browser check verifies 503 → Retry → explicitly selected Controls. |

Follow-ups must not overwrite evidence with a build from an uncommitted tree. The current review packet names its frozen runtime explicitly; update that identity, manifests, screenshots and commands after corrections, with a documentation-only evidence commit afterward. Preserve prior W05 acceptance and the unrelated local handoff file.

## Architectural seams to preserve

The current W06/Journal/Investigation/Evidence separation supports later exploration through explicit projections, but it should not be promoted into one backend model merely because the UI can traverse it.

1. **Subjects and evolution:** Journal's supplied component facet and reference/relation rendering provide presentation seams for a later backend-supplied subject facet. The existing kinds and strict schemas must not quietly gain inferred topic membership, contradiction, supersession or refinement. A future contract needs supplied relation-level reason/source/provenance and explicit derived-versus-curated grouping labels.
2. **Receipt reuse:** `ControlsPresentation` is reusable outside the recorder, and packet stages already remain distinct. These domain meanings should stay independent of comparison layout. A later accepted projection may adapt them to Journal or retrieval views; it must preserve preparation, delivery acknowledgment, citation and evaluated benefit rather than compress them into a generic used/beneficial edge.
3. **Cross-reference identity:** Execution manifest locators and Evidence reference associations preserve origin record/item, source/snapshot and target identity. A future Knowledge Capture & Admission presentation should reuse this distinction between a canonical Evidence ID and its particular supporting binding. Do not turn IDs into storage paths or authorization credentials.
4. **Read lifecycle:** Readers already isolate contracts, cases, project, fixed snapshot and ownership, and cancel obsolete requests. Future views should compose this lifecycle rather than introduce a separate polling/cache convention. Any extraction of shared hooks needs cross-preview isolation, refusal, 304 and cancellation tests; there is no measured need to do that refactor during W06.
5. **Owner vocabulary:** T3 events and G7/F7 budgets require accepted adapters. Engine containment fields are pinned, while receipt/currentness extensions remain provisional. Vocabulary mapping belongs at the projection boundary; the browser must not reimplement fallback logic, authorization or enforcement.
6. **Bounded exploration:** The current trace metadata contains a bounded execution-binding inventory, sufficient for its fixture validation. This is not a scalable backend ownership/availability contract. T3 owners must settle whether a live projection supplies bounded ownership descriptors per page/detail, rather than lifting the fixture inventory into an unbounded trace response.

## Deferred density review

The existing “Dashboard page-density and progressive-disclosure review” in `docs/implementation/future-work.md` remains Unscheduled, with frontend UX ownership pending assignment and Work as its starting page. A feature inventory and desktop/phone task review must precede cleanup-ticket proposals. This assessment does not redesign Work, create tickets or imply that a busy page is inherently wrong.

## Overnight continuation

Final verification: clean runtime commit `d15bc135f23340b7fe4e1f8039290410383d2be0` passed the pinned offline gate (164 tests/19 files), W01–W05 and HTTP regressions, 17 W06 browser groups, the strict premium audit, and bounded-page measurements. Source and complete production/demo build hashes stayed unchanged afterward. Frozen evidence is in `web/docs/w06-evidence/`; independent product-UI acceptance remains PENDING.

The intermediate `adebe3a` freeze failed W01's “Graph navigation and reload retain replay context” check twice. The test waited for a breadcrumb ID that exists before bootstrap/detail reads complete, then reloaded and immediately closed the new client after checking only its URL. The trace recorded aborted API requests receiving 404 during that handoff. The revised test waits for the represented record's “Intent and context” heading before and after reload. It retains all console/network error assertions and passes in the final freeze; no error filtering or timing sleep was added. No production startup behavior or backend contract changed.

Intermediate reproduction artifacts remain in the ignored `web/artifacts/commit-freeze/run-k5u9h1Vo/` checkout, including both failure traces. They are not acceptance evidence. The initial test compilation option error was corrected before its successful 164-test gate.

All three concrete review corrections are implemented and verified. Subsequent overnight follow-ups should check PR 39 CI and new independent feedback; do not invent stretch features or expand scope. Existing architecture/adoption questions and the density review stay deferred to their owners.

## Independent review follow-up

The operator supplied the independent changes-requested review of d15bc13. F1/F2 and nits N1/N2/N4 were corrected and verified from clean committed source `55c48ec5054a4b6830722978b36bfc4e0d55ff60`; N3 retains the separately owned discovery/bound read contexts and accepted overview cadence. See `web/docs/w06-review-main-line.md` and `web/docs/w06-review-corrections.md`. The independent disposition is unchanged until re-review. No backend/live acceptance is claimed.
