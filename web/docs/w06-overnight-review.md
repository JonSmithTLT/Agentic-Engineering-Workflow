# W06 implementer review and future architecture notes

Date: 2026-10-04. Scope: operator-authorized overnight correctness review and architecture assessment. This is implementer review, not independent acceptance. W06 frontend fixture acceptance remains PENDING. No Engine work records or backend commitments are created.

## Corrective work

| Finding | Evidence | Disposition |
|---|---|---|
| R1: child expansion Retry targeted an already loaded root | `FanoutHierarchy` cleared `pending` in `finally`, then used `pending || trace.root_execution` for Retry. `expand` returns immediately for a loaded root. A failed child therefore could not be retried through the error action. | Fixed in runtime commit `adebe3abf723adca3e262414cd3de9c8060481fe`: retain the exact failed child identity independently of the busy state. Regression test simulates a child 503 followed by success and checks that Retry reissues the child read, without refetching the root. Clean committed-source freeze required before publishing updated evidence. |
| R2: execution-table off-page selection lacks an explicit note | `EventResults` reports an off-page or unavailable selected event. `ExecutionResults` retains selection/detail but has no equivalent membership note for a selected execution absent from its current table page. | Confirmed by code inspection; add the equivalent supplied-selection distinction and a paging regression before completing the overnight review. Preserve selection, focus and separate detail resolution. |
| R3: disclosed Controls execution-list failures are not surfaced | `ControlsHost` validates the execution page, but its render path displays `query.error` and `t.error` without displaying `rows.error`. A rejected/failed execution-list projection can therefore appear as an empty chooser. | Confirmed by code inspection; surface a recoverable execution-list error and distinguish a successfully empty list from an unavailable projection. Verify through the product UI. |

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

Recovery-fix verification: the clean offline gate at `adebe3a` passed all 164 tests, typecheck, lint, artifact checks and both builds. The browser freeze is **NOT complete**. W01's “Graph navigation and reload retain replay context” check failed twice against the same immutable build with unexpected accepted-API 404s (`work/S-0001`, `overview` or `capabilities`) around full-document navigation/reload. Do not dismiss this as a flake, suppress console errors or publish the correction as fully verified. Investigate document/service-worker handoff and outstanding reads using the recorded network trace. Existing PR 39's web checks passed for the published `68b09a2` head; the local recovery correction has not been pushed.

Reproduction artifacts are in the ignored clean checkout `web/artifacts/commit-freeze/run-k5u9h1Vo/`: `ci-browser.log`, `ci-browser-recheck.log`, and `source/web/output/playwright-w01[-recheck]/failure-trace.zip`. The main frontend's `pagehide` listener cancels queries, but a rapid reload occurs after the first visible S-0001 text in the test; determine whether reads outlive the old worker client or whether the test is navigating before required content has settled. Keep actual startup/navigation failures visible. Preserve these traces until the root cause is established.

Complete R2/R3, verify their failure/paging paths and regenerate the exact committed-source evidence after runtime corrections. Inspect PR 39 CI without treating queued checks as failures. Review feedback from an independent reviewer remains separate from these implementer findings. Once concrete corrective work and the architecture note are complete, do not invent stretch features or expand W06's accepted scope.
