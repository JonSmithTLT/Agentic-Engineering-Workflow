# Dashboard maps and raw-history search: the contract 0.1.3 change note (v0.1)

- **Status:** **Approved, being built** (operator, 2026-10-10: the whole plan, including the raw-history search route);
  as adopted in contract `0.1.3` at `0c21d9c`; served at adoption: `/history/search`. Proposed 2026-10-10 by the main
  line, as slice S0; the web developer adopted Appendix A unamended (W1, PR #173), and S2 serves the search. A route
  the line does not list is pending until its slice serves it and adds it there. Register F20.8; ledger prefix DMS.
- **Owns:** the main line's proposal for contract 0.1.3: six routes (five maps routes and the conditional
  `/history/search`), two capability keys, the compatibility rule, and the readiness that keeps `main` green whatever
  the web developer amends.
- **Does not own:** the contract file and everything under `web/` (the web developer applies Appendix A, §3.2); the
  maps themselves (F22.1, ADR-0015); Arm B's search engine (F21); admitted-Knowledge search (`knowledge.search`, a
  separate model-facing decision on F21's own sequence).
- **Reads:** the lead developer's plan for this slice (v6, CLEAR after five independent reviews; not in this
  repository); contract 0.1.2 (`docs/design/dashboard-api-v1-provisional.yaml`, SHA-256 `68b46527…d691`); the
  approved [dashboard design note](dashboard-main-line-api-design-v0.1.md) ("the design note"), whose §2 says any
  contract change renews its C0 review; `src/aew/dashboard/`; the maps as merged by PR #143 (`src/aew/maps/`,
  `codebase-map.schema.json`, `map-registry.schema.json`, ADR-0015 and its 2026-10-07 amendment); project maps v0.5
  §2.4, §3.1, §4.9 and T5-INV-01, 04, 06, 07 and 10; Arm B's prototype (PR #148 at `e600529`: `engine/recall.py`,
  `engine/history_ops.py`) and its plan v6 §3.

## 1. Authority

On 2026-10-09, told how far the maps and the knowledge work were from being operational, the operator wrote:

> "i think those also can then be wired into the site so id like to know when i can marry thsoe two hjouses"

The lead developer proposed to "plan the dashboard contract slice now, maps first with search behind its switch", and
the operator replied:

> "oh sure yeah you can plan the dashboard contract as well that would be good"

On 2026-10-10 the operator signed off the CLEAR plan as a whole, with the raw-history search route named explicitly,
which was the condition the plan set before its search slice (S2) is built.

**What this approves.** An operator-facing dashboard route for Arm B's raw-history search, as its own slice. That
route was outside the Arm B prototype PR's scope fence, and it stays behind the same `recall.raw_history_search`
switch: absent while the switch is off, and never model-visible (§5.1). It does not approve admitted-Knowledge search.
The designer's 2026-10-07 ruling on Arm B, "do not activate it as normal model-visible behavior yet", is kept: the
sealed M4-H configuration has the switch off, so the route is absent there. Neither prototype PR is widened: every
change this note needs is made in its own slice after the PR it depends on has merged (§9).

## 2. What changes, and what does not

| # | Decision |
|---|---|
| D1 | **0.1.3, additive.** Existing paths, parameters and response schemas keep their wire shape and their envelope's `schema_version: 0.1.2`; the new responses carry `0.1.3`. A 0.1.2 client keeps working against a 0.1.3 server |
| D2 | **Contract first, through this note.** The web developer applies Appendix A to the contract file; the main line edits nothing in `web/`. S0 lands first, so that no amendment of the additions can turn `main` red |
| D3 | **Six routes:** `/maps`, `/maps/structural`, `/maps/structural/{root}`, `/maps/structural/{root}/inputs`, `/maps/diff`, and `/history/search` (conditional) |
| D4 | Map reads are lock-free: neither the control lock nor the map registry lock; bounded, type-checked, hash-verified reads; freshness computed per request with bounded caches |
| D5 | No map is ever generated from a browser request. "By commit" means the stored maps generated from that commit (`source_revision=`) and freshness against that commit (`against=`), both full object ids only |
| D6 | Size: allowlisted projections with the API's own caps; strings cut at 512 bytes of serialized UTF-8; a typed diff; the inputs list paged by position; ceilings stated and tested |
| D7 | `/history/search` sits behind the **same** switch as the CLI, read from the request's snapshot and failing closed. While off, the route and the `history_search` capability key do not exist, and every response equals today's |
| D8 | Search through the API keeps Arm B's guarantees: every hit authenticated from history, inert text, a fence no content can close (derived per response, so ETags work), the raw-history label and the trust label on every response |
| D9 | The dashboard's search never resets or deletes the shared search substrate, checks the history's root and tail together first, and runs under one 1.25 s deadline |
| D10 | Search never touches `/knowledge`: it lives under History, with its own capability and its own label |
| D11 | **Slices:** S0 (this note and the readiness) → W1 (the web developer adopts the contract) → S1 maps and S2 search, never stacked → S3 (build re-import and acceptance, after the web UI; the operator approves the baseline) |

Nothing served changes in S0. The server keeps answering every 0.1.2 route byte for byte; the six routes stay
pending until S1 and S2 serve them.

## 3. Versioning: 0.1.3 is additive

Every 0.1.2 response schema has `schema_version: const 0.1.2`, and the web client parses envelopes with
`z.literal('0.1.2')` and every response with `z.strictObject`. Bumping every envelope would have to land the server,
the contract, the web side's pins and a new packaged build in one commit across two owners, and the packaged dashboard
would break whenever the server moved first. So the **compatibility rule**, which Appendix A writes into the
contract's `info.description`: a minor version adds new paths and never changes what an existing path returns. An
envelope's `schema_version` is the contract version that defined that response's schema, so the 0.1.2 routes keep
emitting `0.1.2` and the new routes emit `0.1.3`. The packaged 0.1.2 build sees capability keys it does not know
(`maps`, and `history_search` while switched on) and shows the contract's unknown-capability warning without
requesting anything, until S3 imports a build that knows them.

0.2.0 is kept for breaking changes: F28's `network` object in the run label, a projected queue, or anything else that
fails the check below on a served path, including a new optional field on an existing response.

### 3.1 The compatibility check

"Only adds" is not enough on its own: every response object except `Capabilities` is closed
(`additionalProperties: false`) and the client parses strictly, so an added optional property or a new enum value
would break every deployed client. The check therefore compares an **old** contract with a **new** one, element by
element, over a set of **covered paths** (`aew.dashboard.contract.compatibility`):

- **Paths:** each covered path is present and keeps every method it had (`get` and `head`).
- **Responses:** for each covered operation, its responses, and every component reachable from them through `$ref`,
  are **equal** once `description` and `x-` keys are removed from both. The one exception: `Capabilities` may gain
  properties that are exactly `$ref: Capability`, which its `additionalProperties` already admits.
- **Parameters:** every old parameter is present and equal after the same removal; a new one is allowed only if it is
  optional.
- **Never compared:** paths outside the covered set, and components reachable only from them. New paths and their new
  schemas are free.

Where it applies, and with which covered paths:

- **the proposed and accepted contract before adoption:** old = 0.1.2 (the vendored copy, below), covered = every
  0.1.2 path;
- **the packaged build:** old = the build's own contract (read from git at the build's source commit, in the fast lane), new = the accepted
  contract, covered = every path of the build's contract that this server serves or serves conditionally. A path
  absent from the build's contract is exempt: the build never requests it;
- **a later minor version:** old = the adopted contract, covered = the routes served at adoption plus every 0.1.2
  path. An addition whose route was still pending at adoption may change, with the schemas reachable only from
  pending routes: no server has sent that shape, so no client has received it.

The `integrated` value of `Integration.status` (register F20's note) is only an `x-known-values` annotation, which the
check ignores; folding it into 0.1.3 is the web developer's call (§8).

### 3.2 Who edits what

1. **S0 (main line):** this note, with Appendix A: the exact OpenAPI additions as fenced YAML (paths, parameters,
   schemas, the two capability keys, and the `info` rule). The contract file is not touched.
2. **W1 (web developer):** applies Appendix A to `docs/design/dashboard-api-v1-provisional.yaml`, amending the
   additions if the UI needs it, and bumps `info.version` to 0.1.3. In `web/`: `c0-approval.json` (0.1.3 accepted,
   and 0.1.2 moved into `previous_reviews` with `"disposition": "ACCEPT"`, the field the main line reads),
   `contract-version.json`, the parsers (an envelope helper that takes the version), the capability names and the
   fixtures.
3. **C0 renewal:** a fresh-context main-line reviewer checks W1's contract diff against the compatibility rule and
   this note, as the 0.1.2 review was done, and posts the verdict on W1's PR. S1 records any W1 amendment here and
   marks the note adopted (§3.3).

### 3.3 Readiness on the main line

W1 touches the approval record, which runs the full main-line suite. S0 changes main-line tests and constants so that
that run is green whatever W1 amends in the additions:

- **Versions per route.** The accepted contract's version and digest must equal the approval record's, and the
  version must be a `0.1.x` at or above `0.1.2` (`contract.CONTRACT_SERIES = "0.1"`), compared as integers
  (`0.1.10` is above `0.1.2`). A later minor version needs no `contract.py` edit; a `0.2.0` fails on purpose. Each
  served route's envelope version (`projections.ENVELOPE_VERSION`) must equal the `schema_version` const of its
  response schema.
- **Pending routes are derived, never listed.** `pending = contract paths − served − conditional`
  (`server.pending_routes`), so a route W1 renames or adds is pending at once. The sweeps run over served routes, and
  a pending route is tested positively: it answers exactly as this server answers without it, `404 NOT_FOUND` "no
  such route" before authentication when no template matches, or the matching template's own answer
  (`/history/search` matches `/history/{id}`: `401` without a session, otherwise that route's `400`, `403` or `404`).
  `CONDITIONAL_ROUTES` is empty until S2. S1 and S2 each assert that the routes they serve are no longer pending.
- **The 0.1.2 reference is vendored, not read from history.** Every comparison with 0.1.2 uses
  `tests/fixtures/dashboard/contract-0.1.2.yaml`, whose SHA-256 must be the accepted review's. A fast-lane test pins
  its git blob id to the blob at the review's commit (`322301d`), and skips only where a shallow clone lacks that
  commit. Only CI's `core` job (the fast and serial lanes) checks out the full history; the `lanes` job, which runs
  the integration tests, checks out at depth 1. So no test outside the core lanes may read the repository's git
  history. `tests/unit/test_ci_tools.py` lints the usual spellings of one (git's `-C`, `--git-dir` or `cwd=` pointed
  at `ROOT`, a `*_ROOT` constant, `root` or a path derived from `__file__`, or a git wrapper called with one), with
  an allowlist of reasoned exceptions for temporary repositories. A spelling the lint misses still fails loudly: the
  integration shards stop at collection.
- **The packaged build: a rule, not a list.** The build is accepted when its contract digest is the accepted one or
  that of an accepted predecessor (a `previous_reviews` entry with `"disposition": "ACCEPT"`), and the contract at its
  source commit passes §3.1's check against the accepted contract, covering every path of the build's contract that
  this server serves or serves conditionally. The same check guards an early import: once S2 serves
  `/history/search`, a build whose `HistorySearch` differs from the served one fails it.
- **This note against the contract** (`tests/unit/test_dashboard_contract_note.py`). Appendix A must compile as JSON
  Schema 2020-12 and, merged into 0.1.2, pass §3.1's check with every 0.1.2 path covered. Against the accepted
  contract, the mode follows this note's status line:
  - **before adoption**, one-way: the accepted contract compiles and passes the check against 0.1.2. Any W1
    amendment of the additions passes;
  - **the adopted line**, which the first of S1 and S2 to serve a route writes into the status:
    "as adopted in contract `<V>` at `<sha>`; served at adoption: `<routes>`", with the routes this server serves at
    that commit (the other slice appends its routes when it serves them), and with Appendix A updated to the adopted
    shapes;
  - **strict at the adopted version:** while the accepted contract's version equals `<V>`, its paths and components
    must equal 0.1.2 plus Appendix A once descriptions are removed;
  - **a later version** (a 0.1.4): the check against the adopted contract (the vendored 0.1.2 plus Appendix A), covering
    the served-at-adoption routes and every 0.1.2 path. The web developer's 0.1.4 therefore needs no note edit first,
    including a changed `HistorySearch` while `/history/search` is still pending.
- **Done when:** a local dry run of W1 passes the main-line suite twice, once with Appendix A as written and once with
  an amended appendix (a renamed parameter, an added field and a renamed path), both on a scratch copy of the contract
  and of the approval record with 0.1.2 moved to `previous_reviews`. S0's pull request records the results.

## 4. Maps

### 4.1 Routes and parameters

All routes are `GET` and `HEAD` under `/api/v1`, session-authenticated, with envelope `schema_version: 0.1.3`,
`Cache-Control: no-store` and a strong ETag. The capability `maps` is `AVAILABLE` on every project once S1 lands: a
map is optional derived context, so having none is a state of the data, not of the capability.

| Route | Query | Data |
|---|---|---|
| `/maps` | `against` (optional, a full object id) | the registry state and `map_revision`; the selected structural map's summary and its freshness against `against` (default: the authoritative branch head); the architecture reference or null; the number of stored maps; the label |
| `/maps/structural` | `limit` (1 to 50, default 20), `cursor`, `source_revision` (a full object id) | the stored maps, keyset-paged by root; `source_revision=` is "the map of commit H"; a bounded scan (§4.2) |
| `/maps/structural/{root}` | `against`; `section` (one of the eight sections) | one map: summary, `limits`, an inputs summary, freshness, the sections (all or the one asked for), and the cut and dropped counts |
| `/maps/structural/{root}/inputs` | `limit` (1 to 250, default 100), `cursor` | the record's `inputs.metadata`, paged by position |
| `/maps/diff` | `a`, `b` (both required, roots) | a typed comparison of two stored maps |

- **No generation from a request (D5).** A diff is between two stored maps, and "the map of a commit" is a stored map
  whose `source_revision` is that commit. The operator generates maps with `aew map generate`, as today.
- **Ids are checked before any file or git access** (`400 INVALID_REQUEST` otherwise): `{root}`, `a` and `b` are 64
  lower-case hex digits; `against` and `source_revision` are 40 or 64 lower-case hex digits. No ref, revision
  expression, option, short id or path ever reaches git or the filesystem. An unknown commit is not an error:
  freshness says `UNKNOWN`, as the CLI does.
- **Never projected:** the registry entry's storage path, the registry log, the actor of a selection, any absolute
  path. A map is named by its root (its sha256) only.
- **The architecture reference** carries its evidence as an `EntityRef` linking to `/evidence/{id}`, its freshness
  (`CURRENT`, `STALE`, `UNKNOWN` or `UNAVAILABLE`, with at most 50 changed paths), and the engine's note. The
  registry's evidence id is checked against the dashboard's opaque-id rule before any path is built; a malformed id is
  `ARCHITECTURE_UNAVAILABLE`, data with a `200`.
- **Lock-free (D4):** no maps route takes the control lock or the registry lock, and none writes anything; on a
  project without maps, `local/maps/` is never created. `map_revision` appears only in the maps routes' data.

### 4.2 Labels, qualification and size

T5-INV-10 (STALE, PARTIAL and UNKNOWN stay visible through dashboard projections) and T5-INV-04 (an unavailable map is
never shown as an empty one) govern every maps projection: freshness carries its status and its reasons, `/maps` with
no map is `UNAVAILABLE` with `MAP_NONE`, omitted counts travel with every capped list, and every maps response carries
the label "derived navigation context: never authority, and a stale or missing map blocks nothing" (T5-INV-01,
T5-INV-06).

- **Allowlisted, with the API's own caps (D6).** Each section is projected from a per-section allowlist of item fields
  (Appendix A types each list); unknown fields are dropped and counted in `dropped_fields`. Every list is cut to the
  API's cap (the generator's cap, or 100 for parse failures, unsupported entries and LFS pointers, 20 for the caps
  hit, 20 language names per directory row, 100 entries in the language counts), with what is cut added to the list's
  omitted count.
- **Vocabulary fields are checked, not just cut.** `label`, `kind`, `status`, `source`, `runner`, `rule`, `code`,
  `reason`, the caps-hit section and field names and the language names must belong to the installed generator's
  vocabulary (at most 32 bytes each). An item with an unknown value is dropped and counted in `dropped_items`; an
  unknown language name is dropped and counted in `dropped_fields`. Only repository-derived fields (`path`, `name`,
  `target`, `pattern`, `attributes_file`, `extension`, `lfs_pointers` entries) reach the string cut. An item missing
  a field the contract requires is dropped and counted in `dropped_items`.
- **Every kept number is an integer with `0 ≤ n < 2^53`, and every flag a boolean.** Anything else is dropped and
  counted in `dropped_fields`; the contract types each such output with `maximum: 9007199254740991`.
- **Strings are cut by bytes.** Every repository-derived string is cut so that its serialized JSON form is at most 512
  bytes, never inside a UTF-8 sequence or an escape, and ends with the marker ` \[cut]`. `cut_strings` counts the
  cuts, so the UI never parses a string.
- **The diff is typed and linear:** per section `changed`, and per list the `added` and `removed` items (each at most
  the list's cap, `beyond_cap` when the difference lies wholly past it), per counter `from` and `to`, and the envelope
  fields' `from` and `to`.
- **A bounded scan for the list and `source_revision=`:** at most 256 maps and 64 MiB read per request; past either,
  the page carries `scan_incomplete` with `MAP_SCAN_LIMIT`, and the cursor continues.
- **Ceilings:** a full detail at most 2 MiB, a diff 4 MiB, an inputs page 256 KiB, a list page 64 KiB, each tested on
  a generated and a planted worst-case map.
- **Cursors:** `/maps/structural` pages by root and `/inputs` by position in the record's immutable sorted list; neither
  carries a revision, so a control commit never expires a maps cursor, and an inputs cursor is bound to its root.

### 4.3 Errors and reasons

| Status and code | When |
|---|---|
| `400 INVALID_REQUEST` | an id, `against`, `source_revision`, `a`, `b`, `section` or `limit` is malformed, or a parameter is unknown |
| `400 CURSOR_INVALID` | the cursor is invalid |
| `404 NOT_FOUND` | no stored map has that root (for `/maps/diff`, either operand) |
| `422 MAP_ARTIFACT_CORRUPT` | the bounded strict reader refuses a named root: not a regular file, over 16 MiB, a hash mismatch, not canonical, or the schema fails; the remedy is to delete it and generate the map again |
| `500 PROJECTION_FAILED` | a transient read failure; the engine's text goes to the server log only |

`/maps` never refuses because of a map's condition: a missing, corrupt, oversized or unreadable selected map is data
(`UNAVAILABLE` with its reason). The reason codes S1 registers: `MAP_NONE`, `MAP_MISSING`, `MAP_CORRUPT`,
`MAP_REGISTRY_INVALID`, `MAP_UNREADABLE`; `MAP_STALE_GENERATOR`, `MAP_STALE_PATH_LISTING`, `MAP_STALE_METADATA`,
`MAP_CURRENTNESS_UNPROVEN`; `MAP_SCAN_LIMIT`; `ARCHITECTURE_STALE`, `ARCHITECTURE_UNKNOWN`,
`ARCHITECTURE_UNAVAILABLE`.

## 5. Raw-history search

### 5.1 Why an operator route is not model-visible

- **No model can obtain a session.** Every route needs the operator session, minted only after the operator's
  typed-back code at the serving console and held in the server's memory; `require_lead`, `require_invocation` and
  `verify_offer` refuse it, it is never projected into a model or worker environment, and the Lead broker refuses
  `dashboard serve` and `open`.
- **It exists only while the adopted execution policy says `explicit`,** the CLI's switch. The sealed M4-H
  configuration has it off, so the route is absent there too.
- **It adds nothing a model can read:** no pack, resume, guide, catalog row or bridge row.

### 5.2 The switch and "absent"

- The switch is read from the request's own snapshot, with the CLI's semantics (the project file and the execution
  policy count only when they match the committed pins), and it never raises. When the snapshot cannot be read, the
  switch reads as off.
- **Off means absent.** No `history_search` key in `/capabilities` or `/overview`; every `/history/search` request is
  answered exactly as today, through the `/history/{id}` template (authenticated first, so a request without a
  session is `401` whatever the switch says); no file under `local/recall/` is created or opened. For this key,
  absence means "not offered on this project", not `UNKNOWN`.
- **On, but unusable:** `history_search` is `UNAVAILABLE`, and the route answers `403 CAPABILITY_UNAVAILABLE` with the
  same reason, for a v1 project (`MIGRATION_REQUIRED`), a failed FTS5 probe (`FTS5_UNAVAILABLE`), or an invocation
  marker in the server's own environment (`RECALL_NOT_IN_INVOCATIONS`). Otherwise it is `AVAILABLE`.

### 5.3 The response and its guarantees

`GET /history/search?term=…&term=…&kind=…&since=…&until=…&limit=…`: `term` repeated 1 to 16 times (each a phrase, the
terms ANDed, at most 512 characters in all and no control character), `kind` repeated (the history entry kinds and
`evidence`), `since` and `until` in the dashboard's timestamp format, `limit` 1 to 50 (default 10). The server's own
bounds come first: a 2 KiB query (`414 REQUEST_TOO_LARGE`).

- **Authentication is the engine's.** Every field a hit shows or is filtered on comes from the authenticated history,
  never from a substrate row. A tampered substrate can hide a hit, never invent one.
- **Inert text.** Snippets arrive inert (control, format and separator characters escaped), credential-redacted, and
  scrubbed again with the whole body. A snippet is a plain JSON string, never `RichText` Markdown.
- **The fence** is derived, not random, so the ETag works: a token from the query, the history root and the inert
  snippets, with a counter appended while any snippet contains it.
- **Labels:** the raw-history label and the historical trust label are required fields of every response, and every
  hit carries its trust label.
- **Expansion is typed:** `expand.cli` is an argv array the UI renders with escaping; `expand.link` points to
  `/evidence/{id}` or `/history/{id}`, or is null, so there are no dead links.
- **Never destructive (D9).** The dashboard never takes the control lock, so it never resets, discards or deletes the
  shared substrate: a moved, busy, stale, foreign or unusable substrate, or the reached deadline, is a coverage reason,
  never an error. The reasons: `SEARCH_BUILD_BUDGET`, `SEARCH_CANDIDATE_BUDGET`, `SEARCH_TIME_BUDGET`,
  `SEARCH_SUBSTRATE_BUSY`, `SEARCH_SUBSTRATE_REBUILDING`, `SEARCH_SUBSTRATE_STALE`, `SEARCH_SUBSTRATE_FOREIGN`,
  `SEARCH_SUBSTRATE_UNUSABLE`, `SEARCH_HISTORY_MOVED` ("search again"), `SEARCH_HISTORY_UNREADABLE`,
  `SEARCH_UNVERIFIED`.

Errors: `400 INVALID_REQUEST` (the terms, a kind, a timestamp or `limit`, or a repeated non-repeatable parameter),
`403 CAPABILITY_UNAVAILABLE`, `414 REQUEST_TOO_LARGE`, `500 PROJECTION_FAILED`.

## 6. Search and Knowledge stay apart

`/knowledge` and `/knowledge/{id}` are unchanged: they project admitted records. Raw-history search is not Knowledge
and must never look like it. It never reads or writes `/knowledge`'s sources, and no hit has a `Knowledge` kind. It
is a sub-route of `/history` under its own capability. Every response and every hit carries the raw-history label and
the historical trust label. Hits link to `/history/{id}` or `/evidence/{id}`, never to `/knowledge/{id}`. If
`knowledge.search` is built later, it will be a different route over admitted records, on a separate page.

## 7. Conditional requests and polling

Every new route gets the strong ETag computed over the body less `generated_at`, with the route, the project and the
normalized query in its scope. Every envelope carries `control_revision`, so **every control commit changes every maps
and search validator**; a `304` needs an unchanged control revision, an unchanged authoritative head and an unchanged
registry. The search's validator is stable only on a quiescent project with complete coverage. Hence the polling
advice: `/maps` every 30 s or when the page regains focus; the detail, inputs and diff pages on navigation only; search
never polled. Map selections are not outbox events, so F20.7's event endpoint would not signal them.

## 8. What is the web developer's

**What they receive:** this note and Appendix A; the acceptance project variants (S1, S2), a generated and selected
map with an architecture reference, and the search switched on; a live server for `aew dashboard serve --static DIR`
runs.

**What they build:**

- **W1:** the contract, the approval records (0.1.2 kept as an accepted predecessor), envelopes that take a version,
  the parsers, the two capability names and the fixtures. They may amend the additions; S0 keeps `main` green.
- **A Maps page:** the registry state and `map_revision`; the selected map with its freshness badge, reasons and the
  commit it was compared against; the architecture reference, linking to its evidence; the stored maps, paged, with
  "show" and "compare two", and the scan limit shown when reached; the sections as tables, with omitted, cut and
  dropped counts; the inputs list; the typed diff; the label everywhere. Nothing is presented as authority, required
  or blocking; no "run" affordance for test candidates; any copied command built from typed ids only.
- **A search page under History,** shown only while `history_search` is present, labelled "Raw history (not admitted
  Knowledge)": the form (terms, kinds, dates, limit); user-initiated only, never polled and never search-as-you-type;
  results in a raw-history frame with both labels; a coverage banner with its reasons, distinct from "no hits"
  ("results may be incomplete", and "search again" for `SEARCH_HISTORY_MOVED`); the unverified count; the links and
  the copyable command.
- **Browser checks:** hostile map names and hostile snippets render inert; production exclusion; the search page is
  absent with the switch off.

**What they decide:** whether to fold the `integrated` known value into 0.1.3; how the fence is shown (verbatim, or the
exact `fence.open` prefix and `fence.close` suffix stripped and drawn as a frame, the text inside plain either way);
navigation (Maps as its own page and search inside History is the recommendation); any shape changes to the additions
in W1; which frontend commit to propose for S3's import.

## 9. Slices

```text
S0 (this note) ──► W1 (web) ──┬─► S1 (maps) ────┐
                              └─► S2 (search) ──┴─► web UI (web) ──► S3 (import + acceptance)
PR #148 merges ─────────────────► S2
```

- **S0:** this note, the readiness of §3.3, and the register row. Nothing served changes.
- **W1:** the web developer adopts the contract; its full main-line run is green whatever the additions say. If it is
  red anyway, the fault is S0's: the main line fixes it in a new pull request.
- **S1 (after W1):** the five maps routes, the bounded readers, the cursors and reasons, and its routes in the
  adopted line of this note.
- **S2 (after PR #148 and W1):** the conditional route and its additive engine parameters; the CLI's behaviour and
  output stay byte-identical. If #148's merged result lacks something Appendix A needs, the additions are amended in
  0.1.4 before S2 serves the route; meanwhile the route stays pending. #148's result needed no amendment: S2 wrote the
  adopted line with `/history/search`.
- **S3 (after the web UI):** the build re-import under the pinned builder, the acceptance suite extended to the new
  pages, and the operator's approval of the new frontend baseline (the design note's §6.2 rule).

S1 and S2 are independent, one pull request each, never stacked, each with an independent review to CLEAR.

## Appendix A. The OpenAPI additions

The blocks below are merged, in order, into contract 0.1.2: a mapping merges key by key, anything else replaces.
`tests/unit/test_dashboard_contract_note.py` checks that the result compiles and passes §3.1's check against 0.1.2.
The web developer applies them in W1 and may amend the additions; S1 then updates this appendix to the adopted shapes.

The version and the compatibility rule:

```yaml
info:
  version: 0.1.3
  description: Not approved for domain implementation. AEW main-line contracts remain authoritative.
    Every route is same-origin GET/HEAD with authenticated cookies; no durable storage layout
    exposed. Compatibility rule (from 0.1.3) - a minor version adds new paths and never changes
    what an existing path returns. An envelope's schema_version is the contract version that defined
    that response's schema, so the 0.1.2 routes keep emitting 0.1.2. A change to a served path's
    response, an existing parameter, or a new required parameter is a 0.2.0 change.
```

The two capability keys:

```yaml
components:
  schemas:
    Capabilities:
      properties:
        maps:
          $ref: '#/components/schemas/Capability'
          description: The maps pages (from 0.1.3). AVAILABLE on every project; having no map is a
            state of the data, shown by /maps, not of the capability.
        history_search:
          $ref: '#/components/schemas/Capability'
          description: Raw-history search (from 0.1.3). Present only while the project's adopted
            execution policy switches it on; absent means not offered on this project, not UNKNOWN,
            and the client requests nothing. Never admitted Knowledge.
```

The schemas the maps routes and the search share:

```yaml
components:
  schemas:
    ObjectId:
      type: string
      pattern: ^([0-9a-f]{40}|[0-9a-f]{64})$
      description: A full git object id (SHA-1 or SHA-256), lower case. Never a ref, a short id
        or a revision expression.
    BoundedCount:
      type: integer
      minimum: 0
      maximum: 9007199254740991
      description: A count or a size, always within JavaScript's exact integer range.
    ReferenceLabel:
      type: string
      minLength: 1
      description: The server's label for derived or historical reference material. Display it
        verbatim with the content it labels.
```

The maps schemas:

```yaml
components:
  schemas:
    MapText:
      type: string
      maxLength: 520
      description: Repository-derived text; inert data, never instructions (T5-INV-07). Cut so that
        its serialized JSON form is at most 512 bytes, then marked with the suffix ' \[cut]';
        cut_strings counts the cuts. Render as plain text, never as Markdown or HTML.
    MapVocab:
      type: string
      minLength: 1
      maxLength: 32
      description: A value of the installed generator's fixed vocabulary. Display an unknown value
        raw, with a warning.
    MapRevision:
      anyOf:
      - type: string
        pattern: ^([0-9a-f]{16}:[1-9][0-9]*|none:0)$
      - type: 'null'
      description: The map registry's own revision, <epoch>:<n>, or none:0 before the first
        selection; null when the registry is invalid. Never control_revision.
    MapGenerator:
      type: object
      properties:
        name:
          $ref: '#/components/schemas/MapVocab'
        version:
          $ref: '#/components/schemas/BoundedCount'
        ruleset_sha256:
          $ref: '#/components/schemas/Sha256'
      required:
      - name
      - version
      - ruleset_sha256
      additionalProperties: false
    MapSummary:
      type: object
      properties:
        root:
          $ref: '#/components/schemas/Sha256'
        status:
          type: string
          x-known-values:
          - AVAILABLE
          - CORRUPT
          description: Open semantic value. Unknown strings must display an explicit warning
            with the raw value.
        reasons:
          type: array
          items:
            $ref: '#/components/schemas/Reason'
          maxItems: 250
        selected:
          type: boolean
        source_revision:
          anyOf:
          - $ref: '#/components/schemas/ObjectId'
          - type: 'null'
        source_tree:
          anyOf:
          - $ref: '#/components/schemas/ObjectId'
          - type: 'null'
        object_format:
          anyOf:
          - type: string
            x-known-values:
            - sha1
            - sha256
          - type: 'null'
        generator:
          anyOf:
          - $ref: '#/components/schemas/MapGenerator'
          - type: 'null'
      required:
      - root
      - status
      - reasons
      - selected
      - source_revision
      - source_tree
      - object_format
      - generator
      additionalProperties: false
      description: A stored structural map, named by its root (the artifact's sha256) only. The
        record-derived fields are null when status is CORRUPT.
    MapFreshness:
      type: object
      properties:
        status:
          type: string
          x-known-values:
          - CURRENT
          - STALE
          - UNKNOWN
          description: Open semantic value. Unknown strings must display an explicit warning
            with the raw value.
        reasons:
          type: array
          items:
            $ref: '#/components/schemas/Reason'
          maxItems: 250
        against_commit:
          anyOf:
          - $ref: '#/components/schemas/ObjectId'
          - type: 'null'
        against_tree:
          anyOf:
          - $ref: '#/components/schemas/ObjectId'
          - type: 'null'
        metadata_paths:
          type: array
          items:
            $ref: '#/components/schemas/MapText'
          maxItems: 50
        metadata_paths_omitted:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - status
      - reasons
      - against_commit
      - against_tree
      - metadata_paths
      - metadata_paths_omitted
      additionalProperties: false
      description: Computed on every read against the commit named (the authoritative head by
        default); never stored. STALE and UNKNOWN stay visible with their reasons (T5-INV-10).
    ArchitectureFreshness:
      type: object
      properties:
        status:
          type: string
          x-known-values:
          - CURRENT
          - STALE
          - UNKNOWN
          - UNAVAILABLE
          description: Open semantic value. Unknown strings must display an explicit warning
            with the raw value.
        reasons:
          type: array
          items:
            $ref: '#/components/schemas/Reason'
          maxItems: 250
        basis:
          anyOf:
          - $ref: '#/components/schemas/MapVocab'
          - type: 'null'
        observed_commit:
          anyOf:
          - $ref: '#/components/schemas/ObjectId'
          - type: 'null'
        authoritative_commit:
          anyOf:
          - $ref: '#/components/schemas/ObjectId'
          - type: 'null'
        scope:
          anyOf:
          - $ref: '#/components/schemas/MapVocab'
          - type: 'null'
        changed_paths:
          type: array
          items:
            $ref: '#/components/schemas/MapText'
          maxItems: 50
        changed_paths_omitted:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - status
      - reasons
      - basis
      - observed_commit
      - authoritative_commit
      - scope
      - changed_paths
      - changed_paths_omitted
      additionalProperties: false
    ArchitectureReference:
      type: object
      properties:
        evidence:
          anyOf:
          - $ref: '#/components/schemas/EntityRef'
          - type: 'null'
          description: The selected discovery evidence, linking to /evidence/{id}; null when the
            registry holds an id that is not a valid opaque id (ARCHITECTURE_UNAVAILABLE).
        freshness:
          $ref: '#/components/schemas/ArchitectureFreshness'
        note:
          $ref: '#/components/schemas/ReferenceLabel'
      required:
      - evidence
      - freshness
      - note
      additionalProperties: false
      description: A navigation reference. Selection is not truth, and a stale reference blocks
        nothing.
    MapsOverview:
      type: object
      properties:
        map_revision:
          $ref: '#/components/schemas/MapRevision'
        registry:
          type: object
          properties:
            state:
              type: string
              x-known-values:
              - PRESENT
              - NONE
              - INVALID
              description: Open semantic value. Unknown strings must display an explicit warning
                with the raw value.
            reasons:
              type: array
              items:
                $ref: '#/components/schemas/Reason'
              maxItems: 250
          required:
          - state
          - reasons
          additionalProperties: false
        structural:
          type: object
          properties:
            state:
              type: string
              x-known-values:
              - AVAILABLE
              - UNAVAILABLE
              description: Open semantic value. Unknown strings must display an explicit warning
                with the raw value. UNAVAILABLE is never shown as an empty map (T5-INV-04).
            reasons:
              type: array
              items:
                $ref: '#/components/schemas/Reason'
              maxItems: 250
            summary:
              anyOf:
              - $ref: '#/components/schemas/MapSummary'
              - type: 'null'
            freshness:
              anyOf:
              - $ref: '#/components/schemas/MapFreshness'
              - type: 'null'
          required:
          - state
          - reasons
          - summary
          - freshness
          additionalProperties: false
        architecture:
          anyOf:
          - $ref: '#/components/schemas/ArchitectureReference'
          - type: 'null'
        stored:
          type: object
          properties:
            count:
              $ref: '#/components/schemas/BoundedCount'
          required:
          - count
          additionalProperties: false
        label:
          $ref: '#/components/schemas/ReferenceLabel'
      required:
      - map_revision
      - registry
      - structural
      - architecture
      - stored
      - label
      additionalProperties: false
    MapsResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.3
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          $ref: '#/components/schemas/MapsOverview'
      required:
      - schema_version
      - project_id
      - control_revision
      - generated_at
      - data
      additionalProperties: false
    StructuralListResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.3
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          type: object
          properties:
            items:
              type: array
              items:
                $ref: '#/components/schemas/MapSummary'
              maxItems: 50
            next_cursor:
              anyOf:
              - $ref: '#/components/schemas/Cursor'
              - type: 'null'
            scan_incomplete:
              anyOf:
              - type: object
                properties:
                  examined:
                    $ref: '#/components/schemas/BoundedCount'
                  stored:
                    $ref: '#/components/schemas/BoundedCount'
                  reasons:
                    type: array
                    items:
                      $ref: '#/components/schemas/Reason'
                    maxItems: 250
                required:
                - examined
                - stored
                - reasons
                additionalProperties: false
              - type: 'null'
              description: Set when this request reached the scan bound (256 maps or 64 MiB read,
                MAP_SCAN_LIMIT); continue with next_cursor.
            label:
              $ref: '#/components/schemas/ReferenceLabel'
          required:
          - items
          - next_cursor
          - scan_incomplete
          - label
          additionalProperties: false
      required:
      - schema_version
      - project_id
      - control_revision
      - generated_at
      - data
      additionalProperties: false
```

One map's detail: the sections, each projected from its allowlist. Every list item names the fields it may carry; a
counter or a field that fails its type or range check is absent and counted in its section's `dropped_fields`:

```yaml
components:
  schemas:
    MapLimits:
      type: object
      properties:
        tracked_paths:
          type: object
          properties:
            seen:
              $ref: '#/components/schemas/BoundedCount'
            capped:
              type: boolean
          additionalProperties: false
        metadata_bytes:
          type: object
          properties:
            read:
              $ref: '#/components/schemas/BoundedCount'
            limit:
              $ref: '#/components/schemas/BoundedCount'
            capped:
              type: boolean
          additionalProperties: false
        metadata_blob_bytes:
          type: object
          properties:
            limit:
              $ref: '#/components/schemas/BoundedCount'
            skipped:
              $ref: '#/components/schemas/BoundedCount'
          additionalProperties: false
      additionalProperties: false
    MapInputsSummary:
      type: object
      properties:
        path_listing_sha256:
          $ref: '#/components/schemas/Sha256'
        count:
          $ref: '#/components/schemas/BoundedCount'
        read:
          $ref: '#/components/schemas/BoundedCount'
        capped_size:
          $ref: '#/components/schemas/BoundedCount'
        capped_total:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - path_listing_sha256
      - count
      - read
      - capped_size
      - capped_total
      additionalProperties: false
    MapDirectoryRow:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/MapText'
        depth:
          $ref: '#/components/schemas/BoundedCount'
        files:
          $ref: '#/components/schemas/BoundedCount'
        languages:
          type: array
          items:
            $ref: '#/components/schemas/MapVocab'
          maxItems: 20
        languages_omitted:
          $ref: '#/components/schemas/BoundedCount'
        label:
          $ref: '#/components/schemas/MapVocab'
      required:
      - path
      - label
      - languages
      - languages_omitted
      additionalProperties: false
    MapSubmodule:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/MapText'
        object:
          $ref: '#/components/schemas/ObjectId'
      required:
      - path
      additionalProperties: false
    MapUnknownExtension:
      type: object
      properties:
        extension:
          $ref: '#/components/schemas/MapText'
        files:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - extension
      additionalProperties: false
    MapBuildDescriptor:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/MapText'
        kind:
          $ref: '#/components/schemas/MapVocab'
        status:
          $ref: '#/components/schemas/MapVocab'
      required:
      - path
      - kind
      - status
      additionalProperties: false
    MapEntryPoint:
      type: object
      properties:
        label:
          $ref: '#/components/schemas/MapVocab'
        path:
          $ref: '#/components/schemas/MapText'
        name:
          $ref: '#/components/schemas/MapText'
        target:
          $ref: '#/components/schemas/MapText'
        rule:
          $ref: '#/components/schemas/MapVocab'
      required:
      - label
      - path
      additionalProperties: false
    MapTestCandidate:
      type: object
      properties:
        kind:
          $ref: '#/components/schemas/MapVocab'
        path:
          $ref: '#/components/schemas/MapText'
        pattern:
          $ref: '#/components/schemas/MapText'
        files:
          $ref: '#/components/schemas/BoundedCount'
        runner:
          $ref: '#/components/schemas/MapVocab'
        source:
          $ref: '#/components/schemas/MapVocab'
      required:
      - kind
      additionalProperties: false
      description: A candidate only. Never a required check, and never something to run.
    MapGeneratedOrVendor:
      type: object
      properties:
        kind:
          $ref: '#/components/schemas/MapVocab'
        source:
          $ref: '#/components/schemas/MapVocab'
        pattern:
          $ref: '#/components/schemas/MapText'
        files:
          $ref: '#/components/schemas/BoundedCount'
        attributes_file:
          $ref: '#/components/schemas/MapText'
      required:
      - kind
      - source
      - pattern
      additionalProperties: false
    MapSemanticPrerequisite:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/MapText'
        kind:
          $ref: '#/components/schemas/MapVocab'
        source:
          $ref: '#/components/schemas/MapVocab'
      required:
      - path
      - kind
      - source
      additionalProperties: false
    MapCapHit:
      type: object
      properties:
        section:
          $ref: '#/components/schemas/MapVocab'
        field:
          $ref: '#/components/schemas/MapVocab'
        limit:
          $ref: '#/components/schemas/BoundedCount'
        omitted:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - section
      - field
      additionalProperties: false
    MapParseFailure:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/MapText'
        code:
          $ref: '#/components/schemas/MapVocab'
      required:
      - path
      - code
      additionalProperties: false
    MapUnsupported:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/MapText'
        reason:
          $ref: '#/components/schemas/MapVocab'
      required:
      - path
      - reason
      additionalProperties: false
    MapDirectoriesSection:
      type: object
      properties:
        max_depth:
          $ref: '#/components/schemas/BoundedCount'
        rows:
          type: array
          items:
            $ref: '#/components/schemas/MapDirectoryRow'
          maxItems: 200
        rows_total:
          $ref: '#/components/schemas/BoundedCount'
        rows_omitted:
          $ref: '#/components/schemas/BoundedCount'
        submodules:
          type: array
          items:
            $ref: '#/components/schemas/MapSubmodule'
          maxItems: 200
        submodules_omitted:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - rows
      - submodules
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapLanguagesSection:
      type: object
      properties:
        counts:
          type: object
          additionalProperties:
            $ref: '#/components/schemas/BoundedCount'
          propertyNames:
            minLength: 1
            maxLength: 32
          maxProperties: 100
        counts_omitted:
          $ref: '#/components/schemas/BoundedCount'
        unknown_files:
          $ref: '#/components/schemas/BoundedCount'
        unknown_extensions:
          type: array
          items:
            $ref: '#/components/schemas/MapUnknownExtension'
          maxItems: 20
        unknown_extensions_omitted:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - counts
      - counts_omitted
      - unknown_extensions
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapBuildDescriptorsSection:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/MapBuildDescriptor'
          maxItems: 200
        omitted:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - items
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapEntryPointsSection:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/MapEntryPoint'
          maxItems: 100
        omitted:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - items
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapTestCandidatesSection:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/MapTestCandidate'
          maxItems: 100
        omitted:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - items
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapGeneratedAndVendorSection:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/MapGeneratedOrVendor'
          maxItems: 200
        omitted:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - items
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapSemanticPrerequisitesSection:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/MapSemanticPrerequisite'
          maxItems: 100
        omitted:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - items
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapLimitsAndOmissionsSection:
      type: object
      properties:
        caps_hit:
          type: array
          items:
            $ref: '#/components/schemas/MapCapHit'
          maxItems: 20
        caps_hit_omitted:
          $ref: '#/components/schemas/BoundedCount'
        parse_failures:
          type: array
          items:
            $ref: '#/components/schemas/MapParseFailure'
          maxItems: 100
        parse_failures_omitted:
          $ref: '#/components/schemas/BoundedCount'
        unsupported:
          type: array
          items:
            $ref: '#/components/schemas/MapUnsupported'
          maxItems: 100
        unsupported_omitted:
          $ref: '#/components/schemas/BoundedCount'
        lfs_pointers:
          type: array
          items:
            $ref: '#/components/schemas/MapText'
          maxItems: 100
        lfs_pointers_omitted:
          $ref: '#/components/schemas/BoundedCount'
        metadata_unread:
          $ref: '#/components/schemas/BoundedCount'
        non_utf8_names:
          $ref: '#/components/schemas/BoundedCount'
        symlinks:
          $ref: '#/components/schemas/BoundedCount'
        submodules:
          $ref: '#/components/schemas/BoundedCount'
        unknown_extension_files:
          $ref: '#/components/schemas/BoundedCount'
        dropped_fields:
          $ref: '#/components/schemas/BoundedCount'
        dropped_items:
          $ref: '#/components/schemas/BoundedCount'
      required:
      - caps_hit
      - parse_failures
      - unsupported
      - lfs_pointers
      - dropped_fields
      - dropped_items
      additionalProperties: false
    MapSections:
      type: object
      properties:
        directories:
          $ref: '#/components/schemas/MapDirectoriesSection'
        languages:
          $ref: '#/components/schemas/MapLanguagesSection'
        build_descriptors:
          $ref: '#/components/schemas/MapBuildDescriptorsSection'
        entry_point_candidates:
          $ref: '#/components/schemas/MapEntryPointsSection'
        test_candidates:
          $ref: '#/components/schemas/MapTestCandidatesSection'
        generated_and_vendor:
          $ref: '#/components/schemas/MapGeneratedAndVendorSection'
        semantic_prerequisites:
          $ref: '#/components/schemas/MapSemanticPrerequisitesSection'
        limits_and_omissions:
          $ref: '#/components/schemas/MapLimitsAndOmissionsSection'
      additionalProperties: false
      description: Every section, or only the one the section parameter names.
    StructuralDetailResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.3
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          type: object
          properties:
            summary:
              $ref: '#/components/schemas/MapSummary'
            freshness:
              $ref: '#/components/schemas/MapFreshness'
            limits:
              $ref: '#/components/schemas/MapLimits'
            inputs:
              $ref: '#/components/schemas/MapInputsSummary'
            sections:
              $ref: '#/components/schemas/MapSections'
            cut_strings:
              $ref: '#/components/schemas/BoundedCount'
            dropped_fields:
              $ref: '#/components/schemas/BoundedCount'
            label:
              $ref: '#/components/schemas/ReferenceLabel'
          required:
          - summary
          - freshness
          - limits
          - inputs
          - sections
          - cut_strings
          - dropped_fields
          - label
          additionalProperties: false
      required:
      - schema_version
      - project_id
      - control_revision
      - generated_at
      - data
      additionalProperties: false
    MapInput:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/MapText'
        git_oid:
          $ref: '#/components/schemas/ObjectId'
        size:
          $ref: '#/components/schemas/BoundedCount'
        read:
          type: boolean
        sha256:
          $ref: '#/components/schemas/Sha256'
        reason:
          type: string
          x-known-values:
          - capped_size
          - capped_total
          description: Why the generator did not read this input. Open semantic value. Unknown
            strings must display an explicit warning with the raw value.
      required:
      - path
      - read
      additionalProperties: false
    StructuralInputsResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.3
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          type: object
          properties:
            root:
              $ref: '#/components/schemas/Sha256'
            items:
              type: array
              items:
                $ref: '#/components/schemas/MapInput'
              maxItems: 250
            next_cursor:
              anyOf:
              - $ref: '#/components/schemas/Cursor'
              - type: 'null'
            cut_strings:
              $ref: '#/components/schemas/BoundedCount'
            dropped_fields:
              $ref: '#/components/schemas/BoundedCount'
            label:
              $ref: '#/components/schemas/ReferenceLabel'
          required:
          - root
          - items
          - next_cursor
          - cut_strings
          - dropped_fields
          - label
          additionalProperties: false
      required:
      - schema_version
      - project_id
      - control_revision
      - generated_at
      - data
      additionalProperties: false
```

The typed diff. Each changed list carries its `added` and `removed` items, typed as in the detail; each changed
counter its `from` and `to` (a language count's key is `counts.<language>`):

```yaml
components:
  schemas:
    MapDiffOperand:
      type: object
      properties:
        root:
          $ref: '#/components/schemas/Sha256'
        source_revision:
          $ref: '#/components/schemas/ObjectId'
        source_tree:
          $ref: '#/components/schemas/ObjectId'
      required:
      - root
      - source_revision
      - source_tree
      additionalProperties: false
    MapValueChanges:
      type: object
      additionalProperties:
        type: object
        properties:
          from:
            anyOf:
            - $ref: '#/components/schemas/BoundedCount'
            - type: boolean
            - type: 'null'
          to:
            anyOf:
            - $ref: '#/components/schemas/BoundedCount'
            - type: boolean
            - type: 'null'
        required:
        - from
        - to
        additionalProperties: false
      propertyNames:
        minLength: 1
        maxLength: 64
      maxProperties: 128
      description: Counter changes by field name; null where the field is absent on one side.
    MapEnvelopeChanges:
      type: object
      properties:
        source_revision:
          type: object
          properties:
            from:
              $ref: '#/components/schemas/ObjectId'
            to:
              $ref: '#/components/schemas/ObjectId'
          required:
          - from
          - to
          additionalProperties: false
        source_tree:
          type: object
          properties:
            from:
              $ref: '#/components/schemas/ObjectId'
            to:
              $ref: '#/components/schemas/ObjectId'
          required:
          - from
          - to
          additionalProperties: false
        object_format:
          type: object
          properties:
            from:
              $ref: '#/components/schemas/MapVocab'
            to:
              $ref: '#/components/schemas/MapVocab'
          required:
          - from
          - to
          additionalProperties: false
        generator:
          type: object
          properties:
            from:
              $ref: '#/components/schemas/MapGenerator'
            to:
              $ref: '#/components/schemas/MapGenerator'
          required:
          - from
          - to
          additionalProperties: false
        path_listing_sha256:
          type: object
          properties:
            from:
              $ref: '#/components/schemas/Sha256'
            to:
              $ref: '#/components/schemas/Sha256'
          required:
          - from
          - to
          additionalProperties: false
      additionalProperties: false
      description: Only the envelope fields that differ are present.
    MapDirectoriesChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        rows:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapDirectoryRow'
              maxItems: 200
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapDirectoryRow'
              maxItems: 200
          required:
          - added
          - removed
          additionalProperties: false
        submodules:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapSubmodule'
              maxItems: 200
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapSubmodule'
              maxItems: 200
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapLanguagesChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        unknown_extensions:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapUnknownExtension'
              maxItems: 20
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapUnknownExtension'
              maxItems: 20
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapBuildDescriptorsChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        items:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapBuildDescriptor'
              maxItems: 200
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapBuildDescriptor'
              maxItems: 200
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapEntryPointsChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        items:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapEntryPoint'
              maxItems: 100
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapEntryPoint'
              maxItems: 100
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapTestCandidatesChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        items:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapTestCandidate'
              maxItems: 100
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapTestCandidate'
              maxItems: 100
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapGeneratedAndVendorChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        items:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapGeneratedOrVendor'
              maxItems: 200
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapGeneratedOrVendor'
              maxItems: 200
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapSemanticPrerequisitesChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        items:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapSemanticPrerequisite'
              maxItems: 100
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapSemanticPrerequisite'
              maxItems: 100
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapLimitsAndOmissionsChange:
      type: object
      properties:
        changed:
          type: boolean
        beyond_cap:
          type: boolean
        caps_hit:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapCapHit'
              maxItems: 20
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapCapHit'
              maxItems: 20
          required:
          - added
          - removed
          additionalProperties: false
        parse_failures:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapParseFailure'
              maxItems: 100
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapParseFailure'
              maxItems: 100
          required:
          - added
          - removed
          additionalProperties: false
        unsupported:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapUnsupported'
              maxItems: 100
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapUnsupported'
              maxItems: 100
          required:
          - added
          - removed
          additionalProperties: false
        lfs_pointers:
          type: object
          properties:
            added:
              type: array
              items:
                $ref: '#/components/schemas/MapText'
              maxItems: 100
            removed:
              type: array
              items:
                $ref: '#/components/schemas/MapText'
              maxItems: 100
          required:
          - added
          - removed
          additionalProperties: false
        values:
          $ref: '#/components/schemas/MapValueChanges'
      required:
      - changed
      - beyond_cap
      - values
      additionalProperties: false
    MapDiffResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.3
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          type: object
          properties:
            a:
              $ref: '#/components/schemas/MapDiffOperand'
            b:
              $ref: '#/components/schemas/MapDiffOperand'
            identical:
              type: boolean
            envelope:
              $ref: '#/components/schemas/MapEnvelopeChanges'
            sections:
              type: object
              properties:
                directories:
                  $ref: '#/components/schemas/MapDirectoriesChange'
                languages:
                  $ref: '#/components/schemas/MapLanguagesChange'
                build_descriptors:
                  $ref: '#/components/schemas/MapBuildDescriptorsChange'
                entry_point_candidates:
                  $ref: '#/components/schemas/MapEntryPointsChange'
                test_candidates:
                  $ref: '#/components/schemas/MapTestCandidatesChange'
                generated_and_vendor:
                  $ref: '#/components/schemas/MapGeneratedAndVendorChange'
                semantic_prerequisites:
                  $ref: '#/components/schemas/MapSemanticPrerequisitesChange'
                limits_and_omissions:
                  $ref: '#/components/schemas/MapLimitsAndOmissionsChange'
              required:
              - directories
              - languages
              - build_descriptors
              - entry_point_candidates
              - test_candidates
              - generated_and_vendor
              - semantic_prerequisites
              - limits_and_omissions
              additionalProperties: false
            cut_strings:
              $ref: '#/components/schemas/BoundedCount'
            dropped_fields:
              $ref: '#/components/schemas/BoundedCount'
            dropped_items:
              $ref: '#/components/schemas/BoundedCount'
            label:
              $ref: '#/components/schemas/ReferenceLabel'
          required:
          - a
          - b
          - identical
          - envelope
          - sections
          - cut_strings
          - dropped_fields
          - dropped_items
          - label
          additionalProperties: false
      required:
      - schema_version
      - project_id
      - control_revision
      - generated_at
      - data
      additionalProperties: false
```

The five maps paths:

```yaml
paths:
  /maps:
    get:
      operationId: mapsResponse
      description: The registry state, the selected structural map with its freshness, and the
        architecture reference. Lock-free; never generates a map. Poll at most every 30 s, or when
        the page regains focus.
      parameters:
      - &maps-against
        name: against
        in: query
        schema:
          $ref: '#/components/schemas/ObjectId'
        description: The commit freshness is computed against; the authoritative branch head by default.
      - &maps-inm
        name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers: &maps-etag
            ETag:
              schema:
                type: string
              description: Validator computed from the full representation; every control commit
                changes it, as do a map selection and a new authoritative head.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MapsResponse'
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A malformed against, or an unknown parameter.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Session required.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
    head:
      operationId: headMapsResponse
      parameters:
      - *maps-against
      - *maps-inm
      responses:
        '200':
          description: Validated read-only projection.
          headers: *maps-etag
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A malformed against, or an unknown parameter.
        '401':
          description: Session required.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
  /maps/structural:
    get:
      operationId: structuralListResponse
      description: The stored structural maps, keyset-paged by root; source_revision selects the
        maps of one commit. A control commit never expires the cursor.
      parameters:
      - &list-limit
        name: limit
        in: query
        schema:
          type: integer
          default: 20
          minimum: 1
          maximum: 50
      - &list-cursor
        name: cursor
        in: query
        schema:
          $ref: '#/components/schemas/Cursor'
      - &list-source
        name: source_revision
        in: query
        schema:
          $ref: '#/components/schemas/ObjectId'
      - &list-inm
        name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers: &list-etag
            ETag:
              schema:
                type: string
              description: Validator computed from the full representation, with route, project,
                filters, limit and cursor in its scope.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StructuralListResponse'
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: An invalid limit, source_revision or cursor, or an unknown parameter.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Session required.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
    head:
      operationId: headStructuralListResponse
      parameters:
      - *list-limit
      - *list-cursor
      - *list-source
      - *list-inm
      responses:
        '200':
          description: Validated read-only projection.
          headers: *list-etag
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: An invalid limit, source_revision or cursor, or an unknown parameter.
        '401':
          description: Session required.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
  /maps/structural/{root}:
    get:
      operationId: structuralDetailResponse
      description: One stored map, its sections projected from allowlists with the API's caps.
        Fetched on navigation, never polled.
      parameters:
      - &detail-root
        name: root
        in: path
        required: true
        schema:
          $ref: '#/components/schemas/Sha256'
      - &detail-against
        name: against
        in: query
        schema:
          $ref: '#/components/schemas/ObjectId'
      - &detail-section
        name: section
        in: query
        schema:
          type: string
          enum:
          - directories
          - languages
          - build_descriptors
          - entry_point_candidates
          - test_candidates
          - generated_and_vendor
          - semantic_prerequisites
          - limits_and_omissions
      - &detail-inm
        name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers: &detail-etag
            ETag:
              schema:
                type: string
              description: Validator computed from the full representation, with route, project
                and query in its scope.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StructuralDetailResponse'
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A malformed root, against or section, or an unknown parameter.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Session required.
        '404':
          description: No stored map has this root.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '422':
          description: MAP_ARTIFACT_CORRUPT; delete the stored map and generate it again.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
    head:
      operationId: headStructuralDetailResponse
      parameters:
      - *detail-root
      - *detail-against
      - *detail-section
      - *detail-inm
      responses:
        '200':
          description: Validated read-only projection.
          headers: *detail-etag
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A malformed root, against or section, or an unknown parameter.
        '401':
          description: Session required.
        '404':
          description: No stored map has this root.
        '422':
          description: MAP_ARTIFACT_CORRUPT; delete the stored map and generate it again.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
  /maps/structural/{root}/inputs:
    get:
      operationId: structuralInputsResponse
      description: The map's recorded metadata inputs, paged by position in the immutable sorted
        list. The cursor is bound to the root. Fetched on navigation, never polled.
      parameters:
      - &inputs-root
        name: root
        in: path
        required: true
        schema:
          $ref: '#/components/schemas/Sha256'
      - &inputs-limit
        name: limit
        in: query
        schema:
          type: integer
          default: 100
          minimum: 1
          maximum: 250
      - &inputs-cursor
        name: cursor
        in: query
        schema:
          $ref: '#/components/schemas/Cursor'
      - &inputs-inm
        name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers: &inputs-etag
            ETag:
              schema:
                type: string
              description: Validator computed from the full representation, with route, project,
                limit and cursor in its scope.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StructuralInputsResponse'
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A malformed root, an invalid limit or cursor, or an unknown parameter.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Session required.
        '404':
          description: No stored map has this root.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '422':
          description: MAP_ARTIFACT_CORRUPT; delete the stored map and generate it again.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
    head:
      operationId: headStructuralInputsResponse
      parameters:
      - *inputs-root
      - *inputs-limit
      - *inputs-cursor
      - *inputs-inm
      responses:
        '200':
          description: Validated read-only projection.
          headers: *inputs-etag
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A malformed root, an invalid limit or cursor, or an unknown parameter.
        '401':
          description: Session required.
        '404':
          description: No stored map has this root.
        '422':
          description: MAP_ARTIFACT_CORRUPT; delete the stored map and generate it again.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
  /maps/diff:
    get:
      operationId: mapDiffResponse
      description: A typed comparison of two stored maps. Never generates a map. Fetched on
        navigation, never polled.
      parameters:
      - &diff-a
        name: a
        in: query
        required: true
        schema:
          $ref: '#/components/schemas/Sha256'
      - &diff-b
        name: b
        in: query
        required: true
        schema:
          $ref: '#/components/schemas/Sha256'
      - &diff-inm
        name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers: &diff-etag
            ETag:
              schema:
                type: string
              description: Validator computed from the full representation, with route, project
                and both operands in its scope.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MapDiffResponse'
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A missing or malformed operand, or an unknown parameter.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Session required.
        '404':
          description: No stored map has one of the roots.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '422':
          description: MAP_ARTIFACT_CORRUPT for one of the operands.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
    head:
      operationId: headMapDiffResponse
      parameters:
      - *diff-a
      - *diff-b
      - *diff-inm
      responses:
        '200':
          description: Validated read-only projection.
          headers: *diff-etag
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: A missing or malformed operand, or an unknown parameter.
        '401':
          description: Session required.
        '404':
          description: No stored map has one of the roots.
        '422':
          description: MAP_ARTIFACT_CORRUPT for one of the operands.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
```

The search: its schemas and its conditional path. While the switch is off, `/history/search` is not offered and is
answered as `/history/{id}` with the id `search`:

```yaml
components:
  schemas:
    HistorySearchHit:
      type: object
      properties:
        id:
          $ref: '#/components/schemas/OpaqueId'
        kind:
          type: string
          x-known-values:
          - unit
          - annotation
          - audit
          - lead
          - evidence
          description: A history entry kind, or evidence. Never a Knowledge kind. Open semantic
            value; unknown strings display their raw value with a warning.
        at:
          $ref: '#/components/schemas/Timestamp'
        subject:
          anyOf:
          - $ref: '#/components/schemas/OpaqueId'
          - type: 'null'
        source:
          type: string
          x-known-values:
          - engine
          - operator
          - model
          - external
          description: Open semantic value. Unknown strings display their raw value with a
            warning.
        trust:
          type: object
          properties:
            source:
              type: string
            label:
              $ref: '#/components/schemas/ReferenceLabel'
          required:
          - source
          - label
          additionalProperties: false
        truncated:
          type: boolean
        snippet:
          type: string
          maxLength: 400
          description: The authenticated record's matching text, inert and credential-redacted,
            inside the response's fence. Plain text, never Markdown.
        expand:
          type: object
          properties:
            cli:
              type: array
              items:
                type: string
                minLength: 1
                maxLength: 256
              minItems: 1
              maxItems: 8
              description: The command that shows the whole record, as an argv array; render
                each element escaped.
            link:
              anyOf:
              - $ref: '#/components/schemas/EntityRef'
              - type: 'null'
              description: /evidence/{id} or /history/{id}; null when there is no page for it.
          required:
          - cli
          - link
          additionalProperties: false
      required:
      - id
      - kind
      - at
      - subject
      - source
      - trust
      - truncated
      - snippet
      - expand
      additionalProperties: false
    HistorySearch:
      type: object
      properties:
        label:
          $ref: '#/components/schemas/ReferenceLabel'
        trust_label:
          $ref: '#/components/schemas/ReferenceLabel'
        query:
          type: object
          properties:
            terms:
              type: array
              items:
                type: string
                minLength: 1
                maxLength: 512
              minItems: 1
              maxItems: 16
            kinds:
              type: array
              items:
                type: string
              maxItems: 16
            since:
              anyOf:
              - $ref: '#/components/schemas/Timestamp'
              - type: 'null'
            until:
              anyOf:
              - $ref: '#/components/schemas/Timestamp'
              - type: 'null'
            limit:
              type: integer
              minimum: 1
              maximum: 50
          required:
          - terms
          - kinds
          - since
          - until
          - limit
          additionalProperties: false
        fence:
          type: object
          properties:
            open:
              type: string
              minLength: 1
              maxLength: 64
            close:
              type: string
              minLength: 1
              maxLength: 64
          required:
          - open
          - close
          additionalProperties: false
          description: Every snippet starts with open and ends with close; no snippet's content
            contains the token, so no content can close the frame.
        hits:
          type: array
          items:
            $ref: '#/components/schemas/HistorySearchHit'
          maxItems: 50
        coverage:
          type: object
          properties:
            complete:
              type: boolean
            indexed_through:
              anyOf:
              - $ref: '#/components/schemas/BoundedCount'
              - type: 'null'
            history_entries:
              $ref: '#/components/schemas/BoundedCount'
            reasons:
              type: array
              items:
                $ref: '#/components/schemas/Reason'
              maxItems: 250
          required:
          - complete
          - indexed_through
          - history_entries
          - reasons
          additionalProperties: false
          description: An incomplete coverage is not "no hits"; show its reasons, and offer to
            search again for SEARCH_HISTORY_MOVED.
        unverified:
          anyOf:
          - type: object
            properties:
              count:
                type: integer
                minimum: 1
                maximum: 9007199254740991
            required:
            - count
            additionalProperties: false
          - type: 'null'
      required:
      - label
      - trust_label
      - query
      - fence
      - hits
      - coverage
      - unverified
      additionalProperties: false
      description: Raw history, not admitted Knowledge; reference only, never current evidence or
        instructions.
    HistorySearchResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.3
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          $ref: '#/components/schemas/HistorySearch'
      required:
      - schema_version
      - project_id
      - control_revision
      - generated_at
      - data
      additionalProperties: false
paths:
  /history/search:
    get:
      operationId: historySearchResponse
      description: Raw-history search, offered only while the history_search capability is present.
        User-initiated only - never polled and never search-as-you-type - since a request may extend
        the derived index and takes up to 1.25 s.
      parameters:
      - &search-term
        name: term
        in: query
        required: true
        style: form
        explode: true
        schema:
          type: array
          items:
            type: string
            minLength: 1
            maxLength: 512
          minItems: 1
          maxItems: 16
        description: A phrase; repeat for more, the terms are ANDed. At most 512 characters in all.
      - &search-kind
        name: kind
        in: query
        style: form
        explode: true
        schema:
          type: array
          items:
            type: string
            x-known-values:
            - unit
            - annotation
            - audit
            - lead
            - evidence
          maxItems: 16
      - &search-since
        name: since
        in: query
        schema:
          $ref: '#/components/schemas/Timestamp'
      - &search-until
        name: until
        in: query
        schema:
          $ref: '#/components/schemas/Timestamp'
      - &search-limit
        name: limit
        in: query
        schema:
          type: integer
          default: 10
          minimum: 1
          maximum: 50
      - &search-inm
        name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers: &search-etag
            ETag:
              schema:
                type: string
              description: Validator computed from the full representation, with route, project
                and query in its scope; stable only on a quiescent project with complete coverage.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HistorySearchResponse'
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: Invalid terms, kind, timestamp or limit, or a repeated non-repeatable
            parameter.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Session required.
        '403':
          description: Capability unavailable (MIGRATION_REQUIRED, FTS5_UNAVAILABLE,
            RECALL_NOT_IN_INVOCATIONS).
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '414':
          description: The query exceeds the server's bounds.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '500':
          description: Projection refresh failed.
    head:
      operationId: headHistorySearchResponse
      parameters:
      - *search-term
      - *search-kind
      - *search-since
      - *search-until
      - *search-limit
      - *search-inm
      responses:
        '200':
          description: Validated read-only projection.
          headers: *search-etag
        '304':
          description: Representation unchanged. No payload.
        '400':
          description: Invalid terms, kind, timestamp or limit, or a repeated non-repeatable
            parameter.
        '401':
          description: Session required.
        '403':
          description: Capability unavailable.
        '414':
          description: The query exceeds the server's bounds.
        '500':
          description: Projection refresh failed.
```
