**S12-2, pull request 10 of 10 (2026-10-25): the module page, the two generated maps, the `AGENTS.md` record rule, and
the follow-ons of the reviews of #266 and #267.**
The slice's last pull request adds no record: `index.json` is byte-identical to `main`'s (the same `digest`), so the
final counts are the counts of #266's merge.

- **Final counts** (`python tools/reference.py counts`): 1043 records, 394 complete-by-construction and 649 lower-bound,
  77 unresolved items. By family: cli-commands 109, command-refusals 72, commands 10, concurrency 14,
  configuration-states 6, control-keys 92, dashboard-routes 24, entry-points 6, guards 11, layout 59, modules 177,
  reason-rules 56, schemas 30, sqlite-tables 10, states 17, stg02-routes 24, tools 16, transitions 94,
  usage-live-states 3, writers 213.
- **The module page** ([`modules.md`](../../../reference/modules.md)): the import graph of `src/aew` by package, each
  module's imports and importers (the inverse of its records' `imports`, computed from them), the packages that import
  from one another, and the dynamic imports the graph cannot follow. Static and lower-bound, as its records are.
- **The data-flow map** ([`data-flow.md`](../../../reference/data-flow.md)): which process (an entry point) writes or
  reads which entry of `.aew`, drawn from the records alone. A write is a `writers` record's (entry point, entry)
  pair. A read is a function the layout names as a reader that another record also reaches from entry points (a writer
  item, or a lock-free member of the concurrency family). The one trust boundary the records state, the layout's
  `masked_by_containment`, is a group. What no record states is counted from the records and listed as not drawn: the
  writes and reads no entry point reaches, the writes outside `.aew` or unplaced, and the bridge and the network. **A
  record gap for the designer and the operator:** no record attributes a bridge call or a served route to the process
  that makes or serves it, and which entry points run contained is not a fact of the records, so those boundaries are
  prose in an entry point's `reason` and are not drawn. A record that stated them would be new scope.
- **The state-transition maps** ([`state-transitions.md`](../../../reference/state-transitions.md)): one diagram per
  machine. The Ticket machine's states and edges (operation, guard, reason); the configuration and live-usage state sets
  as states only, because the code records no edge table for them (their records say so).
- **The record rule** (`AGENTS.md` section 7, the operator's decision of 2026-10-23): a pull request that adds a
  reference record names the requirement IDs it serves in its description, IDs only; a record that serves none says
  "none" with a line on why; the IDs never go in the generated reference. The pull request carries `operator-merge`,
  because it changes `AGENTS.md`.
- **Follow-ons, each fixed in this pull request** (review of #267 at `5b8e62e4`, merge check of #266 at `11c3faaa`):
  - **Q-1 and F-1** (`3e77c537`): one method for the generator's bounds and depth guards. One AST walk finds, over every
    module of the generator, the constants named like a cap, the slices, the numbers in an ordering or an equality (0,
    1 and negative numbers included), the integer defaults and the depth tests (`< 1`, `<= 0`, `1 >`, `not depth`),
    counted per file and text or per function, so a second site of an excused text is a decision. The roles reader's
    two guards have their boundary tests. Not seen, and pinned as such: a bound spelled through a local name or
    arithmetic.
  - **Q-2** (`ff75e40f`): every check of the typing-cycle rule is planted, with the same code typed as its control;
    the Name branch's cycle check, which could not be reached, is removed; its `_level` is held by a chain of
    attributes rooted at a local.
  - **Q-3** (`27b4effb`): a sentence that introduces a list is cut at the last comma outside brackets and code spans.
  - **Q-4** (`358525c9`): the concurrency page and its cannot-see list name a receiver whose typing needs itself, with a
    probe and a planted member.
  - **Q-5** (`772e268c`): one doubling test over the whole render.
  - **N-1** (`15dca05e`): a `setattr` with a computed name is named beside a computed key, with its probe.
- **Open, not for this slice:** an operator or designer decision whether the data-flow map's bridge and network
  boundaries become records (above).
