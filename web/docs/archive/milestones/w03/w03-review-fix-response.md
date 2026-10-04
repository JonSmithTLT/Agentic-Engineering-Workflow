# W03 fixing-diff response

Original source freeze: `6e83b9516b0ef77c0838b88bd29204ed70e59015`. Independent review: `web/docs/w03-review-main-line.md`, reviewed2026-10-03, all investigation steps established on desktop and phone; four minor changes required. The review is preserved as supplied, including its carrier/validation limitations. The fixing source commit and final commands/results are recorded in `web/docs/w03-followup-evidence/result.json`.

| Finding | Fix | Implementer verification |
|---|---|---|
| 1: phone pane state and ambiguous Stream label | Shared pane buttons have visible pressed styling; Journal uses Results/Detail. Selected ID is visible above both panes and beside Detail. | HTTP demo phone check inspects pressed state and selected ID while Results is visible; W02 protects shared workspace behavior. |
| 2: new record hidden under sticky header | Once the selected Journal entry is available, focus its ID/title heading and adjust document scroll to keep it below the current header geometry. | Phone HTTP task verifies every followed heading is below the header. |
| 3: no focus/announcement after following a relation | Focus the new detail heading with tabindex−1, on selection or reveal, rather than every polling refresh. | Both HTTP layouts verify activeElement is the new ID/title heading through J-02→J-03→J-04→J-05. |
| 4: loadable Journal node described as unresolved | Loadable nodes say not expanded; terminal references say unavailable reference. | HTTP graph check verifies J-04 is not expanded before its explicit expansion. |

Operator additions: a disclosed question-mark type legend, distinct restrained type symbols/edge patterns using existing colors, and spaced/wrapping graph source rows. The legend identifies type only, never truth or applicability. Legend samples use their own class, separate from mounted Journal entries. Evidence remains reference-only; the operator's evidence question was a posture question, not an implementation request.

The new localhost HTTP fixture adapter serves the compiled demo plus accepted and Journal fixture projections with no service-worker adapter import or registration. It preserves strict CSP, read-only methods, conditional requests, per-page fixture headers and existing preview schema. Stateful Scenario Lab recipes remain explicitly available only in the service-worker demo. Normal browsing and Contract Playground remain available. This adds no backend commitment or production Journal registration. See `web/docs/http-demo.md`.

The pinned carrier was found and inspected in Ubuntu WSL's Snap Docker engine; its store is separate from Docker Desktop. See `web/docs/pinned-web-builder.md`. That follow-up fact does not alter what the independent reviewer actually ran.

The designer's future subject/evolution question is assessed in `web/docs/design/w03-topic-evolution-assessment.md`, with W03-Q08 in the backend ledger. Existing seams are adequate for later supplied facets/projections; relation-level reason/provenance needs a new contract version. W03 adds no Topic field, inferred membership or evolution mode.

Independent fixing-diff confirmation remains pending. The reviewer asked for re-checking findings1–4, not repeating the whole completed investigation. Backend adoption and live integration remain separately pending.

Final implementer validation passes the same pinned offline gate (127 tests/15 files, typecheck/lint, artifacts, production exclusion and both builds), six Git detector probes, and41 browser groups:16 W01,10 W02,12 W03 and3 HTTP-mode groups with service workers blocked. The premium static audit has zero findings. An initial follow-up test attempt matched hidden legend samples as Journal entries; giving the samples a separate class corrected that collision. Failed traces/logs remain local and are not counted as validation. Existing chunk-size advisories remain; no new performance improvement is claimed.

## Re-check finding5

The independent re-check confirms findings1–4 are fixed and raises one minor regression: unconditional heading focus removes desktop keyboard users from the results list. The source fix captures whether selection originated from a Journal results link before the detail read completes. Desktop results selections preserve their native focus/scroll position; phone results selections and navigation from within detail still focus the new heading. The selected-ID line is a polite status for Journal. No schema, evidence, graph bounds or polling changes.

The HTTP suite now begins each desktop/phone task with keyboard results selection and checks the two focus policies before repeating relation navigation. A fourth group checks a middle entry on a50-entry page in both stream and table: selection retains link focus, Shift+Tab reaches the preceding entry, and Tab returns to the selected one. Latest source/evidence and actual validation results are in `web/docs/w03-focus-fix-evidence/result.json`. Finding5 confirmation remains pending; the task investigation need not be repeated.

Finding5 implementer validation: the pinned Node22 offline gate passes127 tests/15 files, typecheck/lint, artifacts, production exclusion and both builds. All42 compiled-browser groups pass (16 W01,10 W02,12 W03,4 HTTP-mode groups with service workers blocked). The static premium audit has zero findings. Accepted API, preview schema/digest, generated types and dependency lock remain unchanged.

## Final independent disposition — 2026-10-03

The reviewer re-checked source `7433ddd` through the HTTP demo and returned **ACCEPT**: findings1–5 are fixed with nothing new. Desktop mouse/Enter selection retains list focus and neighbouring Tab navigation; relations after list selection retain heading focus below the sticky header; phone selection focuses the replacing detail. The reviewer also checked that JournalDetail is keyed by entry ID, so the captured navigation origin remounts rather than becoming stale. The supplied append-only review is committed unchanged in `web/docs/w03-review-main-line.md`.

Earlier pending statements above describe the fixing-diff stages and are superseded by this final disposition. This is frontend task-review acceptance only; preview backend schema adoption and live integration remain pending. Merge still requires PR CI and operator action.
