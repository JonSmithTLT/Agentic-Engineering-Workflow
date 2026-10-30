**The oracle's rebuild (2026-10-30, branch `test/stg13-vertical-oracle`).** The `vertical` instrument is re-derived as
V-01's acceptance oracle, from row V01-01 as it stood at the build's start (the designer's ruling V-UAT-3 and V-UAT-5):
- **The path** is the row's 13 steps (`tests/helpers/vertical/oracle.py`), each citing its A-32 catalog IDs and its
  O-01 action, D-01 route or local surface. Each step's state is derived from the vendored O-01 registry, the
  carrier's admission and the STG-02 server's routes, read by the generated reference's own readers. The ledger
  records the states (`steps`).
- **The frozen instrument is retired:** `IDEAL_PATH`, the proposed `aew settings set` and `aew preflight`, and the
  attempts on them. The surface map's `proposed` list held only those two, so it is empty.
- **The PIN rule** (the operator's decision of 2026-10-24) is in `vertical-uat.md` §4. Each PIN is recorded with its
  step and action, and is an approval within the budget derived from the path. The derivation gives the matrix's
  budgets: V1 3, V2 4, V3 0 or 1, V4 4, plus 1 per raise.
- **This row's earlier two notes are settled here.** The lines that said the Lead is uncontained are re-derived:
  `lead_label` reads the label CS-4 records for each Lead session, and `LEAD_LABEL_WIRED` is true. The Lead's
  minimums stay `none`, since raising one is the operator's.
