# W03 review packet

## Disposition

Operator approved plan1.1 and implementation on2026-10-03. This is a demo-only Journal preview0.1.0 PROVISIONAL, independent of accepted API0.1.2. Original implementer evidence is in `web/docs/w03-evidence/`. The independent reviewer completed all desktop/phone task steps and required four minor fixes, recorded unchanged in `web/docs/w03-review-main-line.md`. See `web/docs/w03-review-fix-response.md` and `web/docs/w03-followup-evidence/` for the fixing diff and operator additions. Independent fixing-diff confirmation and backend/live integration remain pending; no Engine suite was invoked.

The source freeze is recorded in `web/docs/w03-evidence/result.json`. Review the diff from mergedW02 `43c5a8f961ff18f9249d62c0ad7f8790f2b33eaf` through that source commit. Evidence additions after the source freeze do not change the reviewed implementation.

Latest re-check: findings1–4 are confirmed fixed; finding5 requires preserving desktop results focus. See the preserved review, updated fix response and `web/docs/w03-focus-fix-evidence/result.json` for this focused fixing diff. Frontend acceptance remains pending finding5 confirmation.

## Implementation boundaries

Journal is the demo Knowledge default, with accepted Records retained. Production Knowledge and accepted detail routes continue unchanged. Two panes, Summary/Evidence/Provenance, 50-entry cursor pages and no automatic detail/graph prefetch. An origin graph/list adapter reuses W02 limits and carries supplied field-level source attribution. Publication/component/evidence roles are explicit; raw prompts are rejected. Prompt digest display establishes identity metadata, not trust/authenticity.

Plural fictional Ticket references demonstrate origin (`CLANGD-T181`), potential applicability (`CLANGD-T203`) and recall (`CLANGD-T207`). They are terminal supplied references: the preview invents no accepted lookup interface, delivery acknowledgment or benefit receipt. Actual primitive lookup and wider reuse/context UI require the backend ledger and W07.

Shared changes are constrained to parameterized read policy/query keys, a Journal workspace variant, a graph reader adapter and safe copy parameters. Native Jump form validation is explicitly application-owned (`noValidate`); the existing Playground textarea owns resizing. Global scrollbar styles inherit current theme tokens. Check Work/Runs regressions and production exclusion.

W02 browser scenarios now isolate independent document lifetimes in fresh contexts, while preserving the stateful graph-continuation scenario. The phone polling scenario uses an explicit phone viewport. Console, page and unexpected HTTP failures remain fatal. An initial service-worker update rejection was retained locally; a separate run disrupted by rebuilding served assets was discarded. Final suites ran against one frozen compiled build.

The W03 paging check waits for50 mounted entries and a changed first ID, rather than accepting the transient disappearance of the prior page. Full-page screenshots reset scroll position so the shared sticky header is captured at the document top. These are harness corrections; failed paging-transition attempts remain local and do not count as passing validation.

Validation: the pinned Node22.22.2 offline gate passes locked installation without network access, artifact checks, typecheck/lint, 127 tests and both builds with production exclusion. All 16 W01, 10 W02 and 12 W03 compiled-browser groups pass, as do six change-detector probes. The premium static audit has zero findings; DESIGN frontmatter was parsed and concrete tokens checked with existing tooling, not the unavailable official lint CLI. Automated UI traversal is not independent acceptance.

Two warm samples per scenario compare frozen W02 with W03. Work F6 remains 21 rendered records and four API reads with no detail prefetch; DOM nodes increase from536 to539, and measured demo transfer increases by4912 bytes. The 10000-entry Journal mounts50 entries,599 DOM nodes and four bootstrap/collection reads with no detail prefetch. Timing samples are noisy and establish no speed improvement or service-level target. Existing chunk-size advisories remain. See `web/docs/w03-evidence/measurements.json`.

The density concern is register E16 in `docs/implementation/future-work.md`, Unscheduled, owner pending assignment. No cleanup/Engine records were created.

## Independent task review — required

Run the compiled demo and repeat this task in a desktop window and at390px phone width. Use the UI only: do not inspect fixture source or use the API/Scenario/Contract developer tools to discover the answers. Resizing the window is sufficient. The implementer's automated traversal is supporting evidence, not this independent disposition.

1. Open Knowledge → Journal. Select “Refresh compile_commands before judging missing callers” (`J-05`). Establish its conditions and limitations.
2. In Provenance follow `J-02 · related_to`. Establish the mistaken hypothesis in Summary.
3. Follow its supplied `J-03 · contradicted_by` relation. Establish the failed removal.
4. Follow `J-04 · followed_by`. Establish the new discovery.
5. Follow `J-05 · contributed_to`. Establish the conditional lesson.
6. Inspect Evidence: supporting `CLANGD-E871`, `CLANGD-E875`; opposing `CLANGD-E880`. Record their supplied roles and the absence of an accepted lookup interface, rather than claiming independent evidence verification.
7. Inspect canonical reference `CLANGD-D42` and the advisory-versus-authority distinction.
8. Expand the origin graph; inspect one edge source, toggle the relation list, and establish that the view is partial. Identify the plural Ticket references without treating applicability/recall as benefit.
9. On phone, switch Stream/Detail, return to results and close detail. Confirm selection and focus remain usable.

Record sourceIDs, steps, outcomes and usability failures in `web/docs/w03-review-main-line.md`, using `web/docs/w03-independent-task-review-template.md`. No timing target. A failure to establish a step through UI is a review finding.

## Reproduction

From `web/`: `node --experimental-strip-types scripts/journal-artifact.mjs`, typecheck/lint/test, production/demo builds, and `node scripts/browser-w03.mjs`. Browser scripts accept CHROMIUM_PATH and retain the existing staged default. W01 and W02 suites must also pass. Use the pinned offline gate described in the project toolchain docs; do not characterize another Node version as pinned validation.

See `web/docs/design/w03-backend-question-ledger.md` for remaining owners and integration gates. Canonical artifact and fixture manifest are under `web/docs/design/`. Production must not register Journal or initialize its handlers/schemas/fixtures.
