**The Lead's typed `map` tool (the mapping series' PR A2, O2), branch `feat/f15-8-lead-map-tool`.** One switch-registered
row, `map`, on the typed Lead surface: a `MECHANICAL` query, offered on both profiles while the project's adopted
execution policy has `maps.reads: structural` (the switch that offers a worker's run the same reads; a Lead session
reads it once, into its surface snapshot, as it reads messaging). Its `read` is a worker bridge row's name without its
prefix (`show`, `search`); its other arguments are exactly those rows' (`bridge.MAP_OPERATIONS`), each a string bounded
by the map reads' new engine-free owner `aew.maps.reads` (which `aew.maps.query` now imports), plus `work_id` for
`scope: ticket`, as the CLI's `--work`. No argument names a commit or a root: it reads at the authoritative head. Its
answer is `aew.maps.query.serve` at `service.read_context`, the context `aew map search` and `aew map show --scope
ticket` now read at too, so the answers are the same but for the recipient, which names the route
(`query.TOOL_RECIPIENT`). A read writes no map state, so it never refreshes or selects a map. The core of the guide
carries one line for it while it is offered. The surface map has its entry and probes. The relayed CLI reads stay as
they were, for the operator and for `--commit`.

**Measured with the pool gate's own render** against main c9d99d16, `maps.reads` on as a new project holds it.
- Messaging on: MCP 11,084 B to 11,784 B (+700, the compact row) and guide 9,404 B to 9,473 B (+69). The pool goes
  from 26,684 B to 27,453 B, and the listing from 16 to 17 tools, under the ceiling of 20.
- Messaging off: MCP 11,174 B to 11,950 B (+776, the standard row) and guide 9,184 B to 9,253 B (+69). The pool goes
  from 26,384 B to 27,229 B, and the listing from 15 to 16 tools.
- The 769 B (messaging on) are the new `F15.8_map_tool` allocation, taken from `operator_reserve` (9,438 B to 8,669 B),
  as the operator approved on 2026-11-27 ("yes the map.tool can use some reserved room").
  The 40,000 B cap is unchanged. The row bounds `section` by length rather than listing the eight names, about 190 B
  less a request; `show` with no section lists them.
- With `maps.reads` off, the tool lists, the guide's core and the system text are byte for byte what they were:
  `tests/unit/test_lead_map_catalog.py` compares them with the same surface rendered without the `map` row.

**A limit.** A map read runs inside the broker's serialized section, like `status`. It holds the Lead's other typed
calls for as long as it runs, and in the worst case that is about 17 s, not a couple of seconds (#654's review, m4). A
search makes three git calls, each bounded at 5 s (`query.LISTING_S`): the basis's `resolve`, the freshness check and
the listing. It then runs the 2 s lexical search (`LEXICAL_S`). Resolving the authoritative head first
(`service._default_commit`) adds a little more. In normal use these calls take milliseconds, and a worker's map read
never holds a Lead call, since the supervisor serves it cooperatively. An answer of up to 64 KiB is over OpenCode's
50 KiB output cut, which the readable text already handles.

**A follow-on, if UAT shows contention:** move the read out of the broker's lock. The context
(`service.read_context`: the head, the Ticket's scope) would be built under the lock, and `query.serve` would run
outside it, as `harness_wait` runs. That is a design change, not a fix (#654's review, m4), so it is recorded here
and not made in #654.

**What remains:** `map.symbol`, `map.callers` and `map.callees` over F22.4's facts (PR C). At Internal alpha:
`map.tests_for`, `map.constraints`, `map.changed`, `evidence.show`, `check.suggest`, `tools.presentation`, and the
in-sandbox `aew-run` server with `whoami` and `check.run`.
