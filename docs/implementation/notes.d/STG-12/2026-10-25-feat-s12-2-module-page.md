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
  `masked_by_containment`, is a group. Every edge is a lower bound, and the page says so. What the joined records say
  they could not resolve is listed from their own `fact_coverage` (the worker run, the unplaced reads, the writers no
  entry point reaches), grouped, with the number of records that carry each, so a new kind of item is listed without
  an edit. What no record states is counted from the records and listed as not drawn by entry point (the writes and
  reads no entry point reaches, the writes outside `.aew` or unplaced) or only said (the bridge and the network).
  The families the maps read are named by their owners, and a family they cannot read is refused. **A
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
- **Follow-ons, each fixed in this pull request** (quick check of #267 at `5b0d0a93`, merge check of #266 at
  `11c3faaa`):
  - **Q-1 and F-1** (`3e77c537`, widened after the review of this pull request, M-3): one method for the generator's
    bounds and depth guards. One AST walk finds, over every module of the generator, the constants named like a cap, the
    slices (from the end through a name too), the numbers in an ordering (any number: 0, 1, negative, positive-signed and
    float ones included) or in an equality (any number but 0, 1 and -1), the number defaults of functions, async
    functions and lambdas, and the depth tests (`< 1`, `<= 0`, `<= 0.0`, `1 >`, `not depth`, `if depth:`, `depth in
    (0, 1)`), counted per file and text or per function, so a second site of an excused text is a decision. The roles
    reader's two guards have their boundary tests. Not seen, and pinned as such (`UNSEEN_BOUNDS`): a bound spelled
    through a local name or arithmetic; a depth counter not named for depth (`not hops`, `hops == 0`); a number given
    to a call (`range(50)`, `textwrap.shorten(s, 60)`, `deque(xs, maxlen=50)`, `xs[:min(len(xs), 50)]`); a bound with no
    literal at all.
  - **Q-2** (`ff75e40f`): every check of the typing-cycle rule is planted, with the same code typed as its control;
    the Name branch's cycle check, which could not be reached, is removed; its `_level` is held by a chain of
    attributes rooted at a local.
  - **Q-3** (`27b4effb`): a sentence that introduces a list is cut at the last comma outside brackets and code spans.
  - **Q-4** (`358525c9`, and the assertion that holds the page's two sentences in `eea759d8`): the concurrency page and
    its cannot-see list name a receiver whose typing needs itself, with a probe and a planted member.
  - **Q-5** (`772e268c`): one doubling test over the whole render.
  - **N-1** (`15dca05e`): a `setattr` with a computed name is named beside a computed key, with its probe.
- **Open, not for this slice:** an operator or designer decision whether the data-flow map's bridge and network
  boundaries become records (above).
- **Tracked, one point of the last review (M-5, the quick check of #268 at `23830fec`).** This is the series' last
  pull request, so there is no next one to carry it, and the wording sits in a docstring a test reads (`Bounds`, in
  `tests/unit/test_reference_writers_flow.py`), which the quick check was the last run over. The point, verbatim:
  "**M-5 (minor): `Bounds`' docstring and the note state four unseen classes, and read as the whole list; five more
  spellings pass both sweeps unstated.**" The five, none with a live instance: a number as an `or` operand (`n = n or
  50`); a number in a membership test (`len(xs) in (50, 51)`); a number as a dict value (`{"max": 50}`); a number in a
  walrus comparison (`(k := 50) < len(xs)`); a depth tested in a comprehension's `if` or in an `assert`. The fix line,
  verbatim: "end the paragraph with the walk's scope said positively, so the list cannot go stale: "It reads a number in a
  comparison, a parameter default, a slice, a call named in `LIMIT_CALLS` and a cap-named constant, and a depth counter
  tested by its name, and nothing else." Say the same in the note." **What fixes it:** the next change to the bounds
  walk (`Bounds`, `bounds_of` or `UNSEEN_BOUNDS`) or to `Bounds`' docstring states the scope positively, in the words
  of the fix line, and says the same in this note's Q-1 and F-1 bullet. Until then this note says it here: the walk
  reads a number in a comparison, a parameter default, a slice, a call named in `LIMIT_CALLS` and a cap-named
  constant, and a depth counter tested by its name, and nothing else; the four classes above are the ones it was
  written knowing it does not see, and the five spellings listed here are more.
