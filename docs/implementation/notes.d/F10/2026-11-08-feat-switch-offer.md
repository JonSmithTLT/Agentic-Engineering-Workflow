An existing project is now offered a moved default at `aew opencode`'s start: `aew/switch_offer.py`, one owner for
"AEW's default for this switch has moved; does this project want it?". It registers two rows, `mutating_concurrency` 1 to
2 and the bundled price table (F25). Later rows go here too: `maps.pack_slices` (E184's next step) and
`coordination.messaging` (F9), which `aew migrate` can't reach, since it reaches only v1 projects and init writes v2.

Only the operator's own terminal is asked; a Lead session and an agent's own `aew` have no path to it. The code taken
needs typing back, and Enter alone is a remembered no, shown by `aew doctor`. It adopts only its own files (`manifest_adopt`'s
`only=`), and a failed adoption leaves none of them behind. Nothing about it can stop the start.

**Limit.** A 1 typed by hand can't be told from init's 1. The screen shows the value held, and a no is remembered.
