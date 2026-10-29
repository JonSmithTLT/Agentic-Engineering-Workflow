**For the oracle's rebuild (2026-10-28).** When CS-4 (#283) merges, these lines no longer describe the Lead:
- `docs/implementation/vertical-uat.md:220-221`, both halves ("Today's Lead has no label on any platform (it is
  uncontained) …"): with CS-4 the Lead is labelled on both platforms, and CS-4 itself raises no minimum;
- `:248`'s premise, "while the Lead is uncontained";
- the same claim in the oracle's helpers: `tests/helpers/vertical/ledger.py:63` and `:119-126`, and
  `tests/helpers/vertical/scripted_operator.py:380-387` and `:410`.

`:226` and `:228`, the Linux and Windows Lead minimums, stay the minimums `tests/unit/test_vertical_ledger.py` pins to
`CONTAINMENT_MINIMUM` until the rebuild raises them. This row's earlier note names `:248`. The rebuild re-derives
these lines; the frozen page is not edited before then.
