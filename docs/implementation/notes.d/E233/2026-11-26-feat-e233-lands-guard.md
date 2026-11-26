**The lands guard (2026-11-26).** Every `lands` in [`surface-map.yaml`](../../surface-map.yaml) now names an open
register row or `later`, and the surface map's `fields` check fails on one that does not
(`tests/unit/test_surface_map.py`, `lands_problems`): a slice name of the A1 slice plan, or a row that has closed. The
guard reads the register through `tools/register.py`, and its test ablates that read.

The vocabulary's keys were the plan's slices. They are now rows, each named only where the row's own text takes the
work:

| Was | Now | Entries |
|---|---|---|
| A2 | E233 | 44: `work_amend`, thirteen `resolve` choices, 22 planned rows and the `uncovered` uses of eight of them |
| A1a-1 | E233 | `ticket_rework` |
| A1a-2 | E233 | `work reconcile` and its `reconcile` choice |
| A1a-2 | E163 | `plan accept` and its `accept_plan` choice |
| F9-A | E175 | `harness send` |
| later | E248 | `harness interrupt`, whose reason already named the row |
| A4 | later | `lead handoff cancel`, `harness stop`, `integrate reorder`, `history audit`, and `harness send`'s uncovered `--when`, which #588 placed in A4 |
| C5b | later | `evidence ingest`, `integrate reconcile`, `integrate validate` |
| A1b | later | `message unseen` |

No open row says it takes A4 (the shell door closed), C5b (the dead-custodian detector and the engine's own paths)
or A1b (the handoff's acknowledged cursor); E349 and E350 touch part of it (below). So their eight rows are `later`, beside the two that were (`map generate`,
`map select-architecture`); each row's `reason` still says what the plan meant for it. The registry's `version` is 6.

**What remains**
- The dead ends E133 left: built on branch `feat/e233-lead-exits`, in its own pull request.
- **For the designer:** which row, if any, takes over A4, C5b and A1b. Until one does, their eight rows stay
  `later`. Two open rows hold part of this work, and neither was taken as the owner, since neither says it builds the
  home or decides the row:
  - **E349** (the operator endpoint's watcher makes its own commit that ends a lost custodian) is the candidate for
    C5b's dead-custodian detector, which `integrate reconcile`'s reason names. It does not say the detector runs the
    reconcile.
  - **E350** (decision owners against Lead reachability) names `lead handoff cancel`, whose broker placement it
    checks, and `work reconcile`, which is Lead-reachable while E335's table makes it the operator's. It settles who
    may reach them, not their typed home: the first is `later`, the second lands on E233.
- **SYS-06's line** in `systems.yaml` still reads "the eleven dead ends, and the lands guard" on this branch. The
  dead ends' pull request (#612) rewords that line for both, so this one leaves it: two edits of one line would
  conflict. If this merges first, the line is stale until #612 does.
- **When E233, E163, E175 or E248 closes,** the pull request that closes it also edits the surface map (each entry
  that lands there is decided, or moved), which makes it a full-tier pull request.
- **For the designer:** the map's other words still name the dead plan (the door `shell-only (pending A2/A4)`, the
  disposition `undecided: until A2's plan decides it`, the report checks that wait "until A2" or "until A4"). They are
  vocabulary keys and check names that 36 entries and the tests use, so renaming them is a registry change of its own.
- `work_amend` stays proposed and undecided until a real Lead needs it, and `ticket_rework` stays proposed until
  `ticket_start` is shown to carry rework, as the row says.
