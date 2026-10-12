**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-02).** Still present:
`PackInputs` (`src/aew/knowledge/context.py:104-134`) has no field for admitted Lead sends or `coordination_inputs`, so
reviewer and verifier packs carry neither. Not covered by an in-flight plan. The Lead's pack-truth slice plan (not in
the repository) changes how a pack states its operational facts (derived from their sources, with one model-facing
truth check) but adds no section; when this row adds the admitted-instruction section, that check covers it like any
other pack text. Owner, priority (P1) and target are unchanged; routing only, under the feature pause.
