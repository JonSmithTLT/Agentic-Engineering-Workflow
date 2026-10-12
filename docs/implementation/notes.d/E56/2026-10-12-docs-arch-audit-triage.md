**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-06).** Still present:
nothing outside `src/aew/engine/disposition_ops.py` (`_follow_up`, `:480-487`) reads a disposition's `follow_up`, so
the follow-up Ticket has no back-link and its cancellation opens nothing. Not covered by an in-flight plan: the
vertical path's typed `resolve` keeps the existing `follow_up` choice (F47.1) but adds no link. Priority (P2), owners
and target are unchanged; routing only, under the feature pause.
