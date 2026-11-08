**Built, first part** (2026-11-07, the operator's one-off builder for "built, and not switched on"):
- Every worker archetype names `codebase_map`: implementer, reviewer, verifier, investigator, researcher, planner and frontier advisor. So with `maps.pack_slices: structural`, every worker's pack carries the bounded slice. The Lead's archetype doesn't: its resume row already carries the map.
- `aew init` generates the authoritative head's map and selects it, as the operator's init. This amends ADR-0015 D4 on 2026-11-07: a selection grants nothing. Anything that stops it is one labelled line in init's report, never a failed init.
- The switch stays `"off"` here. Turning it on at init, and regenerating at each integration publish, is the next step.

**What the slice adds to each card's pack, as a record, not a gate.** Measured on AEW's own repository at f398f258: 168 directories, with the slice framed as the pack joins it, in characters (UTF-8 bytes are within 4 of these):
- no scope declared, the worst case at the 40-row and 20-hint bound: **3,427** characters;
- one package (`src/aew/maps/**`, `tests/**`): **2,337**;
- a typical Ticket (`src/aew/engine/**`, `tests/**`): **2,333**;
- the whole source (`src/**`): **2,099**.

At characters ÷ 4 that is about **525 to 857 tokens per request**, about 583 for a typical Ticket. No tokenizer is installed, so the token figures are approximate.

The slice's body doesn't depend on the role. Two cards with the same scope add the same bytes: the implementer, reviewer and verifier take the Ticket's declared paths, and an investigation's cards take its own scope. Trimming the slice per role would be new work, filed as its own row if wanted.
