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

Nothing of this point remains open on this row.
