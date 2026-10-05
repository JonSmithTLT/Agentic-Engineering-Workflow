# W06 independent-review corrections

The original independent review is preserved in `web/docs/w06-review-main-line.md`. Its **CHANGES REQUESTED** disposition against runtime `d15bc135f23340b7fe4e1f8039290410383d2be0` is superseded by the **ACCEPTED** independent re-review of correction source `55c48ec`, preserved in `web/docs/w06-re-review-55c48ec.md`. This is frontend fixture acceptance only.

Final correction source: `55c48ec5054a4b6830722978b36bfc4e0d55ff60`. Presentation changes are in `9cd4188`; subsequent commits correct the regression driver's preserved-tab handling and ensure the restored table is fully loaded before geometry checks and screenshots.

| Finding | Correction and verification |
|---|---|
| F2: narrow Events/Fanout table actions overlap | Stacked cells override the inherited 36px height with natural height and normal wrapping. Browser checks hit-test and click every story selection, verify detail identity and complete cell content at 390px and 720px, and capture both tables through HTTP and worker adapters. |
| F1: story recorder provenance renders unknown | The shared preview reference presentation recognizes supplied recording/relation source kinds as terminal references. No wire model or accepted parser changed. Every story Events/Fanout selection's Provenance panel is checked for unknown-value warnings; the unknown scenario still exercises the warning behavior. |
| N1: duplicated response panels/raw coverage | Coverage is rendered as labeled supplied lane/completeness/retention/gap information. Event and execution response metadata have separately named disclosures. Both responses remain inspectable without repeating their panels by default. |
| N2: packet tab survives direct-link return | Direct-link return clears the packet tab, cursor, section and disposition along with its locator. The in-history return retains existing focus/position restoration. Browser verification covers the direct-link return. |
| N4: Controls activity absent from copied links | Recorder Controls activity is an allowlisted, validated presentation parameter. Copy/reload restores Validation receipts; disclosed comparison hosts retain independent local activity state. Browser verification covers copied receipt links. |

## N3: read assessment, deferred optimization

The initial trace read discovers the fixed snapshot, and the bound reader makes its own validated read under that snapshot identity. They intentionally own separate payload/validator contexts. Eliminating the second read safely requires an explicit validated representation handoff, rather than sharing a validator across contexts. No transport or cache-isolation behavior was changed as part of these presentation corrections.

The accepted dashboard provider owns `/overview` on its existing cadence independently of the disclosed Controls reader. Opening Controls does not add an overview query in ControlsPresentation. Changing that shared cadence would extend this correction beyond the recorded-execution findings. This harmless-read nit remains documented for a future targeted assessment; it does not alter the two scenarios requested for re-review.

## Re-review

The reviewer completed F2 at 390px and the 720px CSS layout used for 200% zoom in both themes, selecting every story Events/Fanout and cycles Fanout entry and checking hit targets, clipping, overlap and overflow. F1 was checked across every story event/execution; the unknown fixture still warns. N1/N2/N4 are fixed and N3's deferral was accepted. All 24 desktop step files and the phone round trip from the first review passed. See `web/docs/w06-re-review-55c48ec.md` for the independent record; `web/docs/w06-evidence/` contains implementer verification. Backend adoption and live integration remain unclaimed.

## Committed-source verification

Clean detached commit `55c48ec5054a4b6830722978b36bfc4e0d55ff60` passed the pinned offline gate (164 tests/19 files), W01–W05 and HTTP-demo regressions, 22 W06 groups, the strict premium audit, CI path probes and freeze-script syntax. Complete source/build hashes remained unchanged afterward. The new table screenshots show fully loaded restored pages. Superseded diagnostic runs are not acceptance evidence. The independent reviewer rebuilt this exact commit with the pinned gate and verified byte-identical demo output before acceptance.
