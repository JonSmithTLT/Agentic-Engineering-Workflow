**The Lead's containment minimums are raised (2026-10-30, branch `test/stg13-lead-minimums`).** The designer's record
of the operator's decision is titled "the operator's decision of 2026-10-30 on the Lead containment minimums". The
values are in `vertical-uat.md` §4, whose table is the owner (`CONTAINMENT_MINIMUM` equals it, pinned).
- **The ratchet.** `tests/unit/test_vertical_ledger.py` keeps every earlier value and still fails if one is lowered.
- **`enforce` and `VERTICAL_MODE` are unchanged.** The raise removes only Linux's "minimum is none" blocker; switching
  to `enforce` stays the operator's decision.
- **Q1(e) conformance (#307 QC's noted item).** The lane's Windows summary now carries the conditions still open
  right after its heading, before any scenario.
