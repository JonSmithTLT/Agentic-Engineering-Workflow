**The codebase mapping audit (filed 2026-11-25; research input, not adopted design).** An external audit of the
project maps at `308410194b`, dated 2026-11-24, is filed as [research](../../../research/codebase-mapping-audit-2026-11-24.md)
(ledger CMA). It changes none of this row's cells. The operator's routing of its findings to this row:

- **Finding 3, the global 200-directory cap applied before the slice's scope filter** (CMA-05): the generator keeps
  the 200 largest directories, and only then does the slice filter them by the task's scope, so a small task
  directory can drop out before scope selection (the audit reproduced it with 207 rows). This row's "never let an
  omission caused by a cap be read as an absent project element" covers it. It is to be fixed under E293, in
  its own pull request.
- **Finding 1, context** (CMA-03): the audit confirms that the shipped record holds no symbols, definitions,
  references, call edges or source spans, and that its semantic-prerequisites section detects configuration hints
  only. That is the claim this row's profile already limits the structural record to; it adds no work here.
- **Finding 7, context** (CMA-09): neither the shipped investigation skill (labelled unevaluated) nor the
  context-pack rehearsal (scripted workers, no model runs) shows that maps help agents, so the profile claims no
  agent benefit for them.
