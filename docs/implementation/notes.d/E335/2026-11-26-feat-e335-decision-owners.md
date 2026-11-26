**Three owners wait for the designer's confirmation** (#597). Only the two acceptances this row names are the Lead's in
`primitives.PRIMITIVE_OWNERS`: `review.ingest` and `verify.ingest` (a Ticket's own verification). `work.dispose`
(DISPOSE_FINDING, DISPOSE_CLAIM, DISPOSE_ANOMALY), `stage.resolve` (RESOLVE_STAGE) and `integrate.reconcile`
(FINISH_PUBLISH) were inferred to be the Lead's from E350, whose four gaps leave them out although their commands are
in `LEAD_REACHABLE`. They are left unstated, so the operator's, until the designer confirms them. The operator, on
2026-11-26: "might as well do the safe default for now". `test_decision_owners` names their commands (`work dispose`,
`stage continue`, `stage abandon`, `integrate reconcile`) as known gaps of their own beside E350's four.

Designer questions:

- **The three above:** the Lead's, the mechanism's (`integrate.reconcile` is MECHANICAL), or the operator's?
- **`REPLACE_GATE` (`work.gate_replace`) and `ADD_SCOPE` (`work.scope_add`):** unstated, so the operator's. Their code
  comments call the choice the Lead's (ITEMS 55, addendum 4; the designer's decisions of 2026-11-03, §2), but the
  owner table is not quoted for them, and E350 cannot settle them because they go through the typed `resolve`.
- **`integration_publish`'s tool text** (`src/aew/surface/contract.py`) tells the Lead "calling this is your
  publication decision", while PUBLISH is the operator's. This sits with E350 (W09's G3 approval) and E352's naming.
