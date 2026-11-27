The shared schedule and paired report now live in `aew_eval.walk` and
`aew_eval.paired`. The operator approved this lift on 2026-11-26 in question
3 of the F19 proposal. The skill evaluation still uses the same walker and
report through its existing entrypoints. The move carries the functions as
they are, so the budget stops, counted attempts, pairing, blind packets and
grade aggregation keep their existing semantics.

**What remains.** The feature-cell role-run arm, designer decisions and
comparison work retain the boundaries in the F19 rollout notes.
