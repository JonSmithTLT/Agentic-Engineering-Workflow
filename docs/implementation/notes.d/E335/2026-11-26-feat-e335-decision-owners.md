**The owners the Lead holds, and their sources** (#597). `aew.owners.PRIMITIVE_OWNERS` (outside the engine, so the
Lead's MCP transport can word text from it) gives the Lead five primitives:

- `review.ingest` and `verify.ingest` (a Ticket's own verification): the two acceptances this row names.
- `work.dispose` (DISPOSE_FINDING, DISPOSE_CLAIM, DISPOSE_ANOMALY): M4-E plan v3 §2.4, operator-approved 2026-10-07,
  "Who disposes: the Lead".
- `stage.resolve` (RESOLVE_STAGE): plan v3 E3, where a replacement Lead resolves an unfinished stage with continue or
  abandon.
- `integrate.reconcile` (FINISH_PUBLISH): a MECHANICAL primitive that finishes a publication whose intent is already
  committed; it is recorded as the Lead's, which the scripted Lead treats as it treats `mechanical`.

#597 first inferred the last three from E350 and briefly left them to the operator. The operator restored them on
2026-11-26: "Yup restore those also are more sensible responses to those failures." The review of #597 confirms that
`owner` grants nothing: every command keeps its own authority checks.

Designer questions (owners left unstated, so the operator's, until answered):

- **`REPLACE_GATE` (`work.gate_replace`) and `ADD_SCOPE` (`work.scope_add`):** their code comments call the choice the
  Lead's (ITEMS 55, addendum 4; the designer's decisions of 2026-11-03, §2), but the owner table is not quoted for them,
  and E350 cannot settle them because they go through the typed `resolve`.
- **`integration_publish`'s tool text:** it called the call the Lead's publication decision while PUBLISH is the
  operator's. #597 derives the text from the owner table (it now says it carries out the operator's publication
  decision); whether the tool should stay Lead-callable at all is E350's (W09's G3 approval).

The decisions the Lead owns but cannot complete from the projection alone (no `choice` or `rationale` offered) are
E388.

**What remains: the Lead guide's opening line still says the Lead makes every decision** (the quick check of #597 at
`860c5c0c`, m2). `src/aew/engine/guide.py`, the first rule of `who` (line 658 at that commit), rendered as line 9 of
`docs/guides/lead-guide.md`: "write and accept plans, … ingest their evidence and make every decision". It says whose
decisions they are without deriving it from the owner table, and it is always sent. #597 leaves it: rewording it moves
the guide's bytes and the pool record's `guide_core` figures (`lead-context-pool.yaml`). The change that makes
`plan accept` and `integrate publish` need the operator's confirmation (E350's interim, branch
`fix/operator-confirms-plan-and-publish`) rewords it, since that change makes "accept plans" and "make every decision"
false and must touch the line anyway; it re-measures the guide and updates the pool record with it.
