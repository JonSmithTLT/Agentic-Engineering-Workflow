**Re-triage at `e69313b` (the fresh-context architectural composition audit of 2026-10-11, AX-01).** Still present:
the obligation's sources are only the parent's mandatory gate and the ancestors' minimum class
(`src/aew/policy/validation.py:64-92`), nothing computes the drift between the Ticket's base and the integration base
(no `base_drift` anywhere in `src/aew`), and the integration verifier's pack still gets only the Ticket's own diffstat.
In-flight coverage is partial and unchanged: the vertical path's C4 (F47.4) records the drift for the semantic-conflict
explanation, as the earlier note says; the obligation, its legality-affecting key and the verifier's pack section stay
with this row. Neither the vertical path's A1 nor the Lead's pack-truth slice plan (not in the repository) touches
them. Owner, priority (P1) and target are unchanged; routing only, under the feature pause.
