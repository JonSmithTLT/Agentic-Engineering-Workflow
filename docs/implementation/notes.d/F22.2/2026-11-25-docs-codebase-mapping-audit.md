**The codebase mapping audit (filed 2026-11-25; research input, not adopted design).** An external audit of the
project maps at `308410194b`, dated 2026-11-24, is filed as [research](../../../research/codebase-mapping-audit-2026-11-24.md)
(ledger CMA). It changes none of this row's cells. The operator's routing of its findings to this row, as
constraints on the semantic substrate when it is built:

- **Finding 4** (CMA-06): the structural map's CURRENT is never reused for semantic facts. It deliberately ignores
  ordinary blob identities, so a source-body edit leaves it CURRENT. Each semantic unit carries its own source,
  configuration and dependency basis, negative dependencies included (a new header earlier on the include search
  path changes resolution though the header used before did not change), and a missing or untracked resolution
  closure narrows the claim rather than keeping it current.
- **Finding 5** (CMA-07): bounded sections are not a global resource bound on generation. The reader materializes
  the full path listing and the refresh deadline does not preempt all work. Facts are sharded per unit, immutable,
  behind a rebuildable index, and extraction runs outside dispatch with cancellation and resource limits; dispatch
  uses the facts available and reports their state.
