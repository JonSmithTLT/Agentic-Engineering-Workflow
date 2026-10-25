**S12-2, pull request 9 of 10 (2026-10-24): the STG-02 routes, commands and refusals (family 6b).**
The reference gains three families, on one page ([`docs/reference/commands.md`](../../../reference/commands.md)):
`stg02-routes`, `commands` and `command-refusals`, which the designer's second addendum asks for so that the trace pairs
the commands the code admits and the causes it can refuse with mechanically.

- **`stg02-routes`** (22 routes of the vendored HTTP/Problem matrix, and the two `/_test/` routes). Each carries its method
  and `served`, whether the slice's server serves it. The server's dispatch is not a table (`handle` and `_read` are
  `path ==` and `startswith` chains, `COMMANDS` is a constant and the owner read is a regex), so `served` is read from the
  source by two independent detectors (`ast`, and a text reading that shares no code) and tied to the matrix by exact route,
  prefix before one placeholder, or the route's regex. Six routes are served today; a test sends a request to every route of
  the matrix with the owners replaced by spies and reaches an owner through exactly those. A route-shaped string the module
  compares a path with and the matrix does not explain would be an unresolved item (none today), however much of a route
  it is the front of, and so would a `/_test/` literal without the method test the server uses beside it, so the label is
  lower-bound. What neither detector sees is stated and pinned, one probe each: a `match` statement, a regex written at the
  call site, a collection compared by name, a literal handed to a helper, a segment comparison, `endswith`,
  `removeprefix`, a variable, a dict lookup, a concatenation; and `served` is read per route, not per method.
- **`commands`** (10): one record per action of `adopted.registry()`, with its `origin`, its `owner` (`sole_admitting_owner`)
  and `reaches_owner`, whether admission can hand the action to an owner. The registry cannot say that; `Carrier._member`
  does, with two literals (an action whose origin is not the delegated-grant origin is refused before any owner state is
  read, and of the rest one action goes on), read the same two ways. Today only `CONTINUE_ELIGIBLE_WORK` reaches an owner,
  and a test drives a command set for a protected action, a delegated action with a current bound delegation, and that one,
  through the carrier to confirm it. Complete-by-construction for the action set; the registry and the refusal map name the
  same ten actions, tested both ways.
- **`command-refusals`** (72: 69 vendored and 3 code): one record per cause the lookup resolves, with the wire reason it
  maps to and its source (`vendored` is the loaded map, `code` is `SLICE_OWNER_REASONS`). `NOT_MODELLED` is not a third
  source: `Carrier._member` returns it through `refusal` like every other cause. Complete-by-construction, because every
  refusal result is built in the one lookup, which fails closed, and the places that make a result with a `reason_code` are
  a declared set held to the source both ways, in three spellings (a dict literal, a subscript store, a keyword argument).
  The string `"reason_code"` is also read wherever it occurs in the module, by symbol and by what the node is, and the
  occurrences, counted, are a declared set (`OCCURRENCES`) held to the source both ways: a `setdefault`, an annotated or
  augmented store or a `setattr` is an occurrence nobody declared. A computed key and a `**` of a dict built elsewhere
  hold no occurrence of the string and are not seen (pinned, one probe each). The causes the code spells
  (literals given to `refusal`, and the returns of `_delegation` that `_member` hands it through a variable) are read both
  ways and each is a key of some table. A cause no table names, a refusal whose cause cannot be read (a keyword cause, a
  helper that returns something but a constant, a second different origin or action test in `_member`), or a builder
  outside the set makes every refusal record lower-bound.
- **Which of the 72 the slice returns (`emitted_by`, the designer's sixth addendum).** A record is a pair the lookup
  resolves; whether the slice returns it is a separate fact on the record: the sites of the admission path that return the
  pair (`{module, symbol}`), an empty list meaning the slice never returns it. 18 of the 72 are returned (`ORIGIN_NOT_ESTABLISHED`
  for the eight actions whose origin is not the delegated grant, the three delegation causes for each of the two delegated
  actions, `NOT_MODELLED` for `DELEGATED_CANCEL` only, and the three owner causes for `CONTINUE_ELIGIBLE_WORK`); the other
  54 are map entries no path returns. The two detectors read `Carrier._member` as its ordered steps (a test of the origin,
  of a state a helper decides, of the action, then the hand-on to a method) and inventory every `refusal(...)` call of the
  module by name (a call through an alias of `refusal`, or `functools.partial`, is not seen; the battery test below is
  what shows a pair returned that way), and the steps are replayed over the registry's actions, each step taking the actions it refuses and leaving the
  rest for the next. The fact has its own coverage: complete-by-construction while every `refusal` call of the module is
  placed by a step or by the method handed on to and no pair is one the tables lack, else lower-bound with the calls it
  could not place listed. A test drives `Carrier._member` over every action and over the states of a delegation and of the
  owner's work, and the pairs it returns are exactly the 18 read. A cause in a table that no path returns reads as an empty
  list (planted, and `NOT_MODELLED` for the seven other actions in the real tables).
- **What a change to the wire does.** Adding a route, a handler branch, an action, a cause, or a place that builds a refusal
  changes the page and the index: run `python tools/reference.py render` and commit `docs/reference/`.
