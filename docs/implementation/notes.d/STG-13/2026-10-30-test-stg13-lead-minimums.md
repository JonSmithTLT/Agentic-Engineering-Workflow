**The Lead's containment minimums are raised (2026-10-30, branch `test/stg13-lead-minimums`),** as the designer's
record of the operator's decision of 2026-10-30 has it. The values are in `vertical-uat.md` §4, whose table is the
owner (`CONTAINMENT_MINIMUM` equals it, pinned).
- **The ratchet.** `tests/unit/test_vertical_ledger.py` keeps every earlier value and still fails if one is lowered.
- **With no worker run the Lead is judged alone.** Containment is not exercised only with neither a worker run nor
  a Lead label (review of #308, m1).
- **`enforce` and `VERTICAL_MODE` are unchanged.** The raise removes only Linux's "minimum is none" blocker; switching
  to `enforce` stays the operator's decision.
- **Q1(e) conformance (#307 QC's noted item).** The lane's Windows summary now carries the conditions still open
  right after its heading, before any scenario.
