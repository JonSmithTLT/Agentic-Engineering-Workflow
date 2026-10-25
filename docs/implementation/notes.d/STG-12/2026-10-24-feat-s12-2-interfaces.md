**S12-2, pull request 8 of 10 (2026-10-24): the interfaces (family 6).**
The reference gains five families, on one page ([`docs/reference/interfaces.md`](../../../reference/interfaces.md)):
`dashboard-routes`, `tools`, `schemas`, `sqlite-tables` and `cli-commands`, each read from its owner.

- **`dashboard-routes`** (22 API routes and two paths that are not the API). The API routes are the keys of
  `aew.dashboard.server.ROUTES` and `CONDITIONAL_HANDLERS` (`/history/search`, answered only while the adopted policy
  switches it on), with each route's query parameters, repeatable parameters, limit bounds and whether it has a precheck.
  They are complete-by-construction because the server calls a route table in one place
  (`ROUTES.get(route) or CONDITIONAL_HANDLERS[route]`) and names the tables in exactly three functions, which a test holds
  to the tree by two independent detectors (`ast` and a text reading). The server also answers a path under `/session/`
  (the one-time URL exchange) and any path outside `/api/` (the static frontend): `_handle` is read for them, and they are
  records of their own, lower-bound. The methods are the `do_` methods of the request handler (`GET`, `HEAD`).
- **`tools`** (16): the Lead's typed tools from `aew.surface.contract.TOOLS`, complete-by-construction because
  `_catalog` is the one constructor (it refuses a duplicate name or an unknown kind, class, status or profile) and nothing
  else builds the table or a `Tool`.
- **`schemas`** (30): one record per entry of `aew.schemas.SCHEMAS`, held equal to the directory's `*.schema.json` files
  in both directions, each flattened by path with its types and unconditional requirements. A `$ref` is resolved through
  the registry the validator itself uses, so a reference to another schema by `$id` is followed. The flattened lists carry
  their own coverage: none has an unresolved item today.
- **`sqlite-tables`** (10): the DDL the modules hold, executed in memory and read back with `PRAGMA`, with scope `store`,
  or `transient` for the one table the product builds in memory to match text. Lower-bound: three modules import
  `sqlite3` and hold no DDL (they open a database another module creates), and they are named. A text reading of the
  table names agrees with the executed DDL.
- **`cli-commands`** (109): one record per command of the live parser, linked to its entry in the surface map's `commands`
  section and anchored at its handler. Nothing of the entry is copied; `test_surface_map` still owns the equality of the
  map with the parser, and this family holds only that every link resolves, both ways.
- **What a change to an interface does.** Adding a route, a tool, a schema file, a table or a command changes the page and
  the index: run `python tools/reference.py render` and commit `docs/reference/`.
