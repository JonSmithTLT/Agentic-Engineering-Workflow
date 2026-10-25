**S12-2, pull request 9 of 10 (2026-10-24): the STG-02 routes, commands and refusals (family 6b).**
The reference gains three families, on one page ([`docs/reference/commands.md`](../../../reference/commands.md)):
`stg02-routes`, `commands` and `command-refusals`, which the designer's second addendum asks for so that the trace pairs
the commands the code admits and the causes it can refuse with mechanically.

- **`stg02-routes`** (22 routes of the vendored HTTP/Problem matrix, and the two `/_test/` routes). Each carries its method,
  its API and `served`, whether the slice's server serves it. The server's dispatch is not a table (`handle` and `_read` are
  `path ==` and `startswith` chains, `COMMANDS` is a constant and the owner read is a regex), so `served` is read from the
  source by two independent detectors (`ast`, and a text reading that shares no code) and tied to the matrix by exact route,
  prefix before one placeholder, or the route's regex. Six routes are served today; a test sends a request to every route of
  the matrix with the owners replaced by spies and reaches an owner through exactly those. A route-shaped string the module
  compares a path with and the matrix does not explain would be an unresolved item (none today), so the label is
  lower-bound.
- **`commands`** (10): one record per action of `adopted.registry()`, with its `origin`, its `owner` (`sole_admitting_owner`)
  and `reaches_owner`, whether admission can hand the action to an owner. The registry cannot say that; `Carrier._member`
  does, with two literals (an action whose origin is not the delegated-grant origin is refused before any owner state is
  read, and of the rest one action goes on), read the same two ways. Today only `CONTINUE_ELIGIBLE_WORK` reaches an owner,
  and a test drives a command set for a protected action, a delegated action with a current bound delegation, and that one,
  through the carrier to confirm it. Complete-by-construction for the action set; the registry and the refusal map name the
  same ten actions, tested both ways.
- **`command-refusals`** (72: 69 vendored and 3 code): one record per cause an action can return, with the wire reason it
  maps to and its source (`vendored` is the loaded map, `code` is `SLICE_OWNER_REASONS`). `NOT_MODELLED` is not a third
  source: `Carrier._member` returns it through `refusal` like every other cause. Complete-by-construction, because every
  refusal result is built in the one lookup, which fails closed, and the places that make a result with a `reason_code` are
  a declared set held to the source both ways. The causes the code spells (literals given to `refusal`, and the returns of
  `_delegation` that `_member` hands it through a variable) are read both ways and each is a key of some table. A cause no
  table names, a refusal whose cause cannot be read, or a builder outside the set makes every refusal record lower-bound.
- **What a change to the wire does.** Adding a route, a handler branch, an action, a cause, or a place that builds a refusal
  changes the page and the index: run `python tools/reference.py render` and commit `docs/reference/`.
