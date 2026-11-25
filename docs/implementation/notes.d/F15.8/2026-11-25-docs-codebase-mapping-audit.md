**The codebase mapping audit (filed 2026-11-25; research input, not adopted design).** An external audit of the
project maps at `308410194b`, dated 2026-11-24, is filed as [research](../../../research/codebase-mapping-audit-2026-11-24.md)
(ledger CMA). It changes none of this row's cells. The operator's routing of its findings to this row:

- **The audit's Phase 2** (CMA-16), a structural-only read subset over the existing bridge (shared status,
  orientation and section queries, CLI parity, Lead discovery and invocation-bound worker reads, no read that changes
  map selection): it stays frozen, pending the operator's decision. Nothing here schedules it.
- **A standalone read adapter** (CMA-13; the audit's Finding 2, §7.3 and Phase 2 acceptance): navigation of a plain
  Git repository by explicit repository and snapshot coordinates, without a Lead session or an initialized AEW
  project, adopting no workflow state and modifying no source. This is new scope, beyond this row's run-bridge
  transport: **an operator decision is pending**. No row is filed for it.
