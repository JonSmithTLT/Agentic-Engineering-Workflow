**A budget gave up the recovery section before optional recall: found and fixed.** The review of pull request #621
(register E198's follow-on, stacked on #614) reproduced this at #614's head `c2f0db5d`, as a minor:
- The recovery section is kept or omitted whole. When it did not fit a context budget it was omitted, and the room it
  left funded a historical record below it, so source and evidence was given up before optional recall, against the
  order the budget states.
- For a replacement implementer (a 1,486-character recovery section and one 466-character historical record) that
  happened across 638 budgets, 6,138 to 6,775; for each of the other three producing roles, across 82 to 92 budgets.
- `tests/unit/test_context_budget.py` built no pack with a recovery section, so its sweep could not see it.
- Production passes no budget today, so no dispatched pack was affected.

**Fixed in #621,** with the reviewer's suggested fix: in `assemble` (`src/aew/knowledge/context.py`), a tier that
gave anything up leaves no room for the tiers below it. The sweep's packs now carry a recovery section half the time,
and `test_room_a_whole_section_could_not_use_never_funds_a_lower_tier` holds, for each producing role at every budget,
that a historical record is in the pack only when nothing of the source and evidence was cut. The same rule lets a
consumed record's open questions be kept or omitted as whole lists (the note of this day on E198).

**What remains, as a tracked minor (the quick check of #621, its m4): the same thing within one tier.** The rule
stops room passing from a tier to the tiers below it, not between sections of the source-and-evidence tier. A section
that is cut, or omitted because it is kept whole or not at all, still leaves its unused room to the sections after
it, so a later, smaller section is kept while an earlier one is given up.
- Measured in that check: failure evidence with one 1,500-character line was cut to 2 of its 3 lines while the
  open-questions section after it was kept whole, in 812 budgets; a planner's 8-item list was omitted whole while
  lines of a 40-row codebase map after it were kept, in 2,008 of 4,436 budgets (103 before lists were kept whole).
- The recovery section is placed the same way, before the codebase map, so the same code applies to it; that case
  was not measured.
- **The suggested fix:** in `assemble`, a section that is cut or omitted also leaves no room for the later sections of
  its own tier; and `random_inputs` in `tests/unit/test_context_budget.py` gains a long line and a codebase map, so
  the sweep sees it.
- **Owner:** nobody today. It is not fixed in #621, by the Lead's decision to make no further change to shared
  budget behaviour there. This row's next slice, the next pull request that changes the recovery section or the
  recitation, is what fixes it. Production passes no budget today, so no dispatched pack is affected.
