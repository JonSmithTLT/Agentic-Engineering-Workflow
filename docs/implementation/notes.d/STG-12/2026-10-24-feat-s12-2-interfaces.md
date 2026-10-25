**S12-2, pull request 8 of 10 (2026-10-24): the interfaces (family 6).**
The reference gains five families, on one page ([`docs/reference/interfaces.md`](../../../reference/interfaces.md)):
`dashboard-routes`, `tools`, `schemas`, `sqlite-tables` and `cli-commands`, each read from its owner.

- **`dashboard-routes`** (22 API routes and two paths that are not the API). The API routes are the keys of
  `aew.dashboard.server.ROUTES` and `CONDITIONAL_HANDLERS` (`/history/search`, answered only while the adopted policy
  switches it on), with each route's query parameters, repeatable parameters, limit bounds (its own, or the server's
  default) and whether it has a precheck. They are complete-by-construction because three things are held to the tree,
  each by two independent detectors (`ast` and a text reading): the functions that name a route table are the three
  declared; the one call out of a table is `ROUTES.get(route) or CONDITIONAL_HANDLERS[route]`; and every read of the
  request path (`url.path`, `h.path`) in `_handle` and `_respond` is a declared one, by form and by what consumes it
  (nine, counted). A route served by a hand-written branch, an early return, a test on the raw target or a third table
  would read the path or name a table in one of those two functions, so it is a difference (the review's four plants are
  controls). Chosen against the review's options: the recogniser is extended, not the label lowered. What it does not
  see: a test of the path inside a function those two call (`_admit`, `_conditional`, `_exchange`, `_static`,
  `match_route`), and a read replaced by another of the same form and consumer. The server also answers a path under
  `/session/` (the one-time URL exchange) and any path outside `/api/` (the static frontend): `_handle` is read for them,
  and they are records of their own, lower-bound, each with the attribute of the server it is answered only while it is
  set (the session store, the static root). The methods are the `do_` methods of the request handler (`GET`, `HEAD`).
- **`tools`** (16): the Lead's typed tools from `aew.surface.contract.TOOLS`, complete-by-construction because
  `_catalog` is the one constructor (it refuses a duplicate name or an unknown kind, class, status or profile). The pin
  sees `Tool(` call sites, resolved by where the callee was imported from: `TOOLS` is assigned once from a `_catalog(...)`
  call, every `Tool(` call of the contract is an argument of it, and no other module calls `Tool`. It does not see a
  `Tool` made by `_replace` or `_make`, an alias of `Tool`, a mutation of `TOOLS` from another module or a second
  catalog (one probe each). The finders are functions of the generator with planted right, wrong and missing controls.
- **`schemas`** (30): one record per entry of `aew.schemas.SCHEMAS`, held equal to the directory's `*.schema.json` files
  in both directions, each flattened by path with its types and unconditional requirements (1,591 paths). A `$ref` is
  resolved through the registry the validator itself uses, so a reference to another schema by `$id` is followed. A
  required key that `properties` does not declare is typed as a validator would type it, by the matching
  `patternProperties` schema or else the `additionalProperties` schema; 25 paths in four schemas (`codebase-map`,
  `control`, `evidence`, `plan`) have no type because the schema gives them none. Every keyword is classified (walked,
  constraint-only, annotation, or unwalked); one that is unwalked or unclassified, and array-form `items`, is an
  unresolved item of its schema. The flattened lists carry their own coverage: none has an unresolved item today.
- **`sqlite-tables`** (10): the DDL the modules hold, executed in memory and read back with `PRAGMA`, with scope `store`,
  or `transient` for the one table the product builds in memory to match text. Lower-bound, because DDL built at run time
  is unseen whether or not a module imports `sqlite3`. Three modules import `sqlite3` and hold no DDL, and they are
  named: this reading cannot show that they create no table (the three open a database `aew.history.index` creates). A
  text reading of the table names agrees with the executed DDL.
- **`cli-commands`** (109): one record per command of the live parser, linked to its entry in the surface map's `commands`
  section and anchored at its handler. Nothing of the entry is copied; `test_surface_map` still owns the equality of the
  map with the parser, and this family holds only that every link resolves, both ways. A command whose handler cannot be
  anchored is named, not anchored at the parser. The parser is built with both of its switches on, and a test pins that
  these are all of its parameters.
- **What a change to an interface does.** Adding a route, a tool, a schema file, a table or a command changes the page and
  the index: run `python tools/reference.py render` and commit `docs/reference/`.
