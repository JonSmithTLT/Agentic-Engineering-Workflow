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
