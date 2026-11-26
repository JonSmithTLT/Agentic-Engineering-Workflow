**The oracle's burn-down plan (2026-11-26, branch `docs/v01-burn-down`).** The vertical re-measure of 2026-11-26 at
`3640b585` (14 failed, 4 passed on Linux; CI runs 45733486683 and 45744120018) is mapped to fixes in
[`v01-burn-down.md`](../../v01-burn-down.md), approved by the operator on 2026-11-26. It holds one table of root-cause
clusters, each with its row and state, the order in two tracks (the alpha gate and the strict gate), and the open
questions for the operator and the designer. `tests/unit/test_v01_burn_down.py` keeps it from going stale: every breach
category the ledger and the oracle define has an entry, every step the oracle derives as not landed names an open
cluster, and a cluster's state agrees with its rows' state in the register.
- **The #213 fixture fix this row's note of 2026-10-30 tracked** has a row of its own, E385, closed by #602.
