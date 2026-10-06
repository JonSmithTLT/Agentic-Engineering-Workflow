# Dashboard main-line API: the design note for F20.2 to F20.6 (v0.1)

- **Status:** **Approved with modifications, being built** (designer and operator, 2026-10-05; the dispositions are
  §7). Proposed 2026-10-05. Register F20.2 to F20.6; ledger prefix DAB. Written by the lead developer of the main AEW
  repository. Nothing here reopens a settled decision (§2); it lists every decision the five slices needed, the
  recommendation for each, the designer's disposition, and the slice plan.
- **Owns:** the Python server behind the frozen dashboard frontend: the `aew.dashboard` package, `aew dashboard
  serve` and `aew dashboard open`, the operator-session credential, and the acceptance of the integrated product.
- **Does not own:** `web/`, `web.yml` and the dashboard branches (the web agent's); contract 0.1.2 itself (any change
  renews its C0 review); the queue (UNSUPPORTED in 0.1.2); engine restructuring (M4-D is changing `engine/api.py`,
  the queue operations, the outbox and the invariants in parallel, so every engine edit here is small and additive,
  §4.15).
- **Reads:** the register rows F20 and F20.1 to F20.6; the M4 report §2.12; contract 0.1.2
  (`docs/design/dashboard-api-v1-provisional.yaml`, SHA-256 `68b46527…d691`, C0 accepted 2026-10-02); the web
  documentation index, the live integration checklist, the W01 backend question ledger and the frontend core
  main-line review; ADR-0005 with its 2026-10-05 `service` amendment (PR #57); ADR-0009's environment-trust inventory;
  ADR-0011 P2c (`cold.first_at`, `cold.unverified_since`); ADR-0012 D3, D4 and D8; the D1 review's F3 finding
  (`--follow` under the control lock); the engine's read paths (`store.read`, `history_ops`, `resume_ops`,
  `work_ops`, `harness_ops`, `outbox`, `authority`, `operator`, `lead_broker`, `bridge`, `cli/credentials`); the
  frontend's transport, read context, routes and its own HTTP demo server (the headers it already serves itself).

## 1. Scope

Five register rows, one PR each, in order: F20.2 (the GET/HEAD projections, validated against the contract), F20.3
(the session), F20.4 (conditional requests), F20.5 (static serving and server security), F20.6 (integrated
acceptance). The frontend is done and frozen; the server has to meet it where it stands. The server reads control
state the way `aew status` and `aew history list` do, through the engine's existing read helpers, and it can change no
engineering state: every route is GET or HEAD, and the credential it issues authorizes nothing in the engine.

## 2. What is already settled

Restated so that the decisions below can be read against them; none is reopened.

- Read-only, same-origin GET/HEAD only, bound to `127.0.0.1` only (an SSH tunnel reaches a remote host).
- Stdlib `http.server`, `jsonschema` for validation, no new runtime dependency (the offline Rocky 8 wheelhouse).
- F20.3 uses AEW's one credential system: the operator starts `aew dashboard serve` at their own terminal and
  confirms presence with the typed-back code takeover uses; that mints a read-only operator credential
  (`aew1.<id>.<secret>`, verifier only) held in the server's memory and never written to control state; the browser
  gets it once, through a one-time URL exchanged for an `HttpOnly`, `SameSite=Strict` cookie; a session lasts about
  a day or until the server stops; `aew dashboard open` issues a new URL.
- F20.4: ETags cover the whole envelope; a valid 304 keeps the cached envelope and advances only `last_checked_at`;
  any change to the envelope or to `control_revision` is a 200.
- F20.3 has its own security acceptance and review: bootstrap, cookie handling, expiry, invalidation when the server
  stops, replay of the one-time URL, each with a negative test.
- Queue state stays UNSUPPORTED in 0.1.2; projecting the M4-D queue is a later contract version with a renewed C0
  review. Any contract change renews its C0 review.
- The contract header's `PENDING_REVIEW` is the web agent's to correct.

## 3. Sources

The governing texts are the contract, ADR-0005, ADR-0009, ADR-0011 and ADR-0012; the register rows and the M4 report
§2.12 set the scope; the web agent's documents state what the frontend needs. Where this note says what the engine
does today, it was read from the code at `559ef0a` (main, 2026-10-05), not from memory: the lock-taking `read`, the
digest-cached parse, the history index and its private-copy fallback, the outbox reader and the wake file, the token
table and its lookup, the terminal authorization, the Lead broker's refusals and the credential delivery rules.

## 4. Decisions

Each item states the question, what the sources already fix, the recommendation (**R**), and the alternative where one
is worth recording.

### 4.1 The operator-session credential

**Question.** How does the dashboard session's credential fit ADR-0005 beside `lead`, `invocation`, `handoff_offer`
and the new `service` kind: its scope, its `expires_at` (the first real use), its revocation, and how it is verified
when nothing is in control state.

**Fixed already.** Same form `aew1.<token_id>.<secret>`, same verifier (`sha256(secret)`), same record fields; held
only in the serving process's memory; nothing in control state; a day or until the server stops.

**R1. A fifth kind, `operator_session`, with no Lead generation and no engine authority.** The record has the shape
of every token record (`kind`, `verifier`, `scope`, `issued_at`, `issued_by_generation`, `expires_at`, `revoked_at`,
`revoke_reason`) and lives in a table the server owns. Its scope is
`{surface: "dashboard", project: <project_id>, operations: ["dashboard.read"], authorized_by: "operator-tty"}`. It
carries no generation, like `service`: it grants no Lead authority, so a handoff or takeover neither revokes it nor
needs to; a dashboard that watches a takeover happen is the point of the dashboard. `issued_by_generation` is recorded
for provenance only.

**R2. The credential authenticates a browser to the local server; it never authorizes an engine operation.** The
engine's reads need no credential today (`aew status`, `aew history list`, `aew work show` take none), and the server
reads the same way. `require_lead`, `require_invocation` and `verify_offer` refuse the kind as they refuse every
foreign kind (an `operator_session` record never reaches control state, so they never see one; the negative test
presents one anyway). A write scope would be a later decision and a renewed security review, as the register says.

**R3. `expires_at` is set at issue and enforced by the same lookup the engine uses.** `issued_at + session lifetime`
(default 24 h; `--session-hours`, 1 to 168). `authority._lookup` already refuses an expired record with
`StaleAuthority("credential expired")`; the server maps that to `401 SESSION_EXPIRED`. This is the first credential
whose expiry is set, so the test that an expired credential is refused moves from "the field exists" to "the field
acts".

**R4. Revocation is the end of the process, expiry, or displacement.** Stopping the server drops the table, so every
cookie is dead on the next request (`401 SESSION_REQUIRED`). Expired records are purged. The table is bounded (32
live sessions); minting a 33rd revokes the oldest with `revoke_reason: "superseded: session limit"`. No `revoke`
command in v1: the operator stops the server. (Alternative: `aew dashboard sessions` and `revoke <id>` through the
control channel of §4.2; cheap to add later, not needed for the acceptance.)

**R5. Verification is the engine's lookup over the server's table.** `authority.lookup(tokens, token)` is factored out
of `_lookup` (which then delegates to it; §4.15): the same regex, the same constant-time verifier comparison, the same
expiry check. `PermissionDenied` (unknown id, bad secret, malformed) is `401 SESSION_REQUIRED`; `StaleAuthority`
(expired, revoked) is `401 SESSION_EXPIRED`. Nothing about verification is new; only where the table lives is.

**Threat model, unchanged.** The same-UID model of ADR-0005: a process running as the operator can read `.aew/`
directly, so the dashboard discloses nothing that process could not read; what the credential adds is that a browser
tab, an iframe or another origin cannot. Custody: the raw secret exists in the serving process between minting and
the one-time exchange, then only as its verifier; it is never written to any file, never printed (the one-time URL
carries a separate bootstrap code, §4.3), and never enters any agent environment (the Lead broker refuses
`dashboard serve` and `dashboard open` as it refuses every credential-emitting command, and `AEW_*` scrubbing
already covers any environment).

### 4.2 Issuing a session: aew dashboard serve and aew dashboard open

**Question.** `serve` proves presence once at start. How does `open` prove it later, and how does it reach the
running server, without a flag, a file or an API call becoming the authorization?

**R6. `serve` authorizes at its own terminal and prints the first URL.** `aew dashboard serve [--port 4280]
[--session-hours 24]` calls `operator.authorize` with a challenge naming the project, the port and the lifetime
("START the read-only dashboard and issue a browser session"), mints the first session, and writes the one-time URL
to the terminal through the credential delivery path (§4.3). It runs in the foreground until interrupted; on exit the
table is cleared. The default port is 4280 (designer, 2026-10-05); when it is occupied the command fails with a message
naming the port and the `--port` flag, and never wanders to another port; `--port 0` is the explicit opt-in for an
ephemeral port, printed in the URL. The Host and Origin checks (§4.14) use the origin actually bound. It writes `.aew/local/dashboard/server.json` (`pid`, `port`, `started_at`, the control endpoint) for
`open` and `status` to find it; `local/` is disposable and never authority (ADR-0011 invariant 4).

**R7. `open` is authorized by the serving process's terminal, not by its own.** `aew dashboard open` connects to the
server's local control channel (a `multiprocessing.connection.Listener` with a random key, the bridge's pattern;
the key in `local/dashboard/control.key`, mode 0600) and asks for a session. The server generates a one-time code
and writes the authorization prompt **to its own console** (the operator's), saying which process asked (the process
chain, as `operator.authorize` does) and that the code is to be typed into the terminal that ran `aew dashboard open`.
`open` reads the answer from its own controlling terminal (the same `/dev/tty` and `CONOUT$` paths `operator` uses, so
a process without a terminal is refused there with `OPERATOR_AUTHORIZATION_REQUIRED`), sends it, and the server
compares it in constant time, with a 300 s timeout and one attempt per request. On success the server mints a new
session and returns the one-time URL, which `open` writes to its terminal. The authorization therefore stays with a
console only the operator sees, and the key file is a convenience, not the authorization: a process that read the key
and forged a request would still face a code it cannot see.

*Alternative, simpler, weaker:* `open` runs `operator.authorize` at its own terminal and the server trusts the key
file. A same-UID process that read the key could then mint a session without a terminal; the disclosure would be no
more than reading `.aew/` directly, but it would make a file the authorization, which ADR-0005 avoids. Recommended
only if the two-terminal flow proves awkward in F20.6; it would be its own decision.

**R8. Both commands are credential-emitting.** They join `credentials.ISSUING` and the broker's `CREDENTIAL_EMITTING`
set: refused inside a Lead session; refused before anything is issued when the process has no terminal, unless
`--print-credential` puts the URL on standard output for a script that keeps it safe (F20.6's browser checks use
exactly that, as the acceptance tests use it today). The result's `session_url` key is delivered like `token` and
`offer` are (`credentials.KEYS` gains it).

### 4.3 The one-time URL and the cookie

**R9. The URL carries a bootstrap code, not the credential.** `http://127.0.0.1:<port>/session/<code>`, `code` 256
random bits, URL-safe; valid for 10 minutes; single use. The server keeps `code -> (pending secret, record)` until the
exchange or the expiry, then only the record's verifier. On `GET /session/<code>` it sets the cookie and answers
`303 See Other` to `/` with `Cache-Control: no-store`. A second use, an expired code or an unknown one is
`410 Gone` with a page saying to run `aew dashboard open` (never a 404 that invites guessing; the body names no code).
The exchange is refused (`403`, and the code is **not** consumed) when `Sec-Fetch-Site` is present and not `none` or
`same-origin`, or `Sec-Fetch-Mode` is present and not `navigate`: a code that leaked into a web page cannot be spent by
a click from it, and the operator can still paste it. The server never logs the `/session/` path's code
(`/session/<redacted>` in its request log), and `Referrer-Policy: no-referrer` keeps the browser from leaking it.

**R10. The cookie is the credential.** `Set-Cookie: aew_session=aew1.<id>.<secret>; Path=/; HttpOnly;
SameSite=Strict; Max-Age=<seconds to expires_at>`. No `Secure` attribute: the origin is `http://127.0.0.1`, and
`Secure` on a plain-http loopback origin is accepted by some browsers and dropped by others, so it would make the
session browser-dependent for no gain on a loopback-only listener (the `__Host-` prefix needs `Secure`, so it is
not used either). The contract's illustrative name `aew_session` is kept. A request whose cookie fails verification
gets `401` with the JSON `Error` body and a `Set-Cookie` that expires the dead cookie. Routes outside `/api/v1/`
(the static build, the SPA fallback) need no cookie: the HTML and assets are public build products, and the data is
behind the API; a document load without a session shows the frontend's "session required" state after its first
`/project` call.

### 4.4 Draft amendment text for ADR-0005

To be landed in F20.3's PR, with its status line updated. Draft:

> ## Amendment YYYY-MM-DD — a fifth credential kind, `operator_session`, for the read-only dashboard (F20.3)
>
> The dashboard (register F20) reuses AEW's credential system for its browser session rather than adding a second
> identity (operator, 2026-10-03). This amendment gives that session a credential. The scheme is unchanged: same form,
> same verifier, same record fields, same lookup.
>
> - **Kind.** `operator_session`, beside `lead`, `invocation`, `handoff_offer` and `service`. Same form
>   `aew1.<token_id>.<secret>`, same verifier, same `issued_at`, `issued_by_generation`, `expires_at`, `revoked_at` and
>   `revoke_reason`.
> - **Scope `{surface, project, operations, authorized_by}`, and no generation.** `surface` is `dashboard`, `project`
>   the project id, `operations` exactly `["dashboard.read"]`, `authorized_by` `operator-tty`. The credential carries
>   no Lead generation because it grants no Lead authority: handoff and takeover revoke the `lead` and `handoff_offer`
>   kinds and leave it alone. It authorizes **no engine operation**: `require_lead`, `require_invocation` and
>   `verify_offer` refuse it as they refuse every foreign kind, and no transaction ever runs under it. It authenticates
>   a browser to the local dashboard server, whose every route is a read.
> - **Never in control state.** The record lives only in the memory of the `aew dashboard serve` process, in a table
>   with the token record's shape. It is verified by the same lookup the engine uses over its own table
>   (`authority.lookup`). Nothing about it is written to `control.yaml`, to the history or to any file; `local/`
>   holds only the server's endpoint, never a verifier or a secret.
> - **Issued only after operator authorization at a terminal.** `aew dashboard serve` authorizes with the typed-back
>   challenge code at its own controlling terminal (`operator.authorize`, as takeover does), then mints. `aew dashboard
>   open` asks the running server, which writes a one-time code to **its** console and accepts the session request
>   only with that code typed back from the requesting terminal. No flag, environment variable, stdin input, file or
>   API parameter authorizes a session.
> - **Delivered once, as a one-time URL.** The command writes a one-time URL to the operator's terminal (the
>   credential delivery rules of the 2026-09-29 amendment apply: terminal only, or `--print-credential` for a script;
>   refused in a Lead session). The URL carries a single-use bootstrap code valid for ten minutes, not the
>   credential. The browser exchanges it for an `HttpOnly`, `SameSite=Strict` cookie holding the credential; the
>   server then keeps only the verifier.
> - **`expires_at` is set and enforced: the first credential kind with a real expiry.** A session lasts the
>   configured lifetime (default 24 h) and ends when the serving process ends, because the table ends with it. A
>   later `aew dashboard open` issues a new session; it does not extend an old one.
> - **Custody is the operator's.** The raw secret never enters a model-controlled process: the Lead broker refuses
>   `dashboard serve` and `dashboard open` as it refuses the Lead's credential-emitting commands; the agent
>   environment allowlist carries no dashboard variable; the server redacts credential strings from everything it
>   logs or returns.
> - **Threat model unchanged.** The credential is a browser-authentication capability inside this ADR's same-UID
>   model, not an OS boundary: a process running as the operator can read `.aew/` directly. What it adds is that no
>   other origin, tab or page can read the operator's project through the dashboard.
> - **Evidence:** `tests/integration/test_dashboard_session.py` (F20.3's security acceptance): bootstrap, cookie
>   handling, expiry, invalidation when the server stops, one-time URL replay, each with a negative test; the kind
>   refused by every engine authority check; the secret in no file, log or output.

### 4.5 History cursors

**Question.** The contract wants History cursors that "pin the starting manifest count and stable seq, survive
appends" and fail as `400`, never `409`. The engine's `aew history list` has no cursor (a limit, newest first, with
`--since`/`--until`). How do the new cursors relate to ADR-0012's revision cursor and to `aew history log`?

**Two sequences, two cursors; they are not the same thing.**
- The **history manifest sequence** (`seq`, ADR-0011) numbers the cold records: unit bundles, annotations, audits,
  Lead records. It is what `/history` and `/history/{id}` project (`History.seq`), what the index orders by, and
  what `cold.root.count` pins.
- The **control revision** (ADR-0012 D3) numbers commits. `aew history log --since R` pages the transition log by
  it; `control_revision` in every envelope is it; `/activity` (§4.10) reads the transition log by it.

A unit's archival is one history entry (seq) made by one commit (revision), so the two advance together but are not
interchangeable, and neither replaces the other.

**R11. A History cursor pins the manifest count at the first page and walks seq downwards.** The first page (no
cursor) reads the current `cold.root.count` as `pin` and returns the newest entries (seq ≤ pin) that match
`kind`/`since`/`until`, newest first, as `aew history list` orders them (invariant 12). `next_cursor` encodes
`{v: 1, route: "history", project, pin, before: <last seq served>, filters: {kind, since, until}, limit}`. Later
pages return entries with `seq < before` and `seq ≤ pin`; entries appended after the first page (seq > pin) never
enter that pagination session, so "later appends never invalidate it or enlarge it" holds by construction, and the
cursor never needs a `409`. `next_cursor` is `null` when the page ends at the oldest matching entry.
`HistoryDetail.annotations_next_cursor` pages a record's annotations the same way (`route: "history-annotations"`,
`subject`, the annotation count as `pin`).

**R12. Cursors are opaque, unsigned and validated against the request.** Base64url of the JSON above. A cursor is
`400 CURSOR_INVALID` when it does not decode, when its `route`, `project`, `filters` or `limit` differ from the
request's, when `pin` exceeds the current count (a history cannot shrink; this is another project's cursor or
corruption) or when `before` is not within `1..pin`. Signing would add nothing here: the cursor selects a page of a
read-only, bounded, public-to-this-session projection; a forged cursor can only choose a different page.
(Alternative: an HMAC with a per-process key, which would also fail every cursor on a server restart.)

**R13. The engine gains an upper seq bound on the index listing; the CLI gains parity.** `HistoryIndex.list` takes
`max_seq` and `before_seq`; `HistoryCommands.history_list` and `aew history list` take `--before SEQ`, so the CLI
can page the same way and the surface stays one. Additive (§4.15).

### 4.6 Hot collection cursors

**R14. A hot cursor pins the control revision and expires with it.** `/work`, `/runs`, `/evidence`, `/knowledge` and
`/attention` are projections of hot state. Their cursor encodes `{v: 1, route, project, rev, filters, limit, after:
<last id served>}`; items are ordered by id (the engine's stable order in `work_list` and `harness_status`), paged by
keyset (`id > after`), so an insertion within a revision cannot skip or repeat an item. A cursor whose `rev` is not the
current revision is `409 CURSOR_EXPIRED` ("restart this bounded query"), as the contract asks; one that fails §4.12's
structural checks is `400`. `/activity` reads the append-only transition log by revision, so its cursor pins the
starting revision and walks downwards like History (`before: <revision>`), and never needs a `409`.

**R15. The `/work` default is hot plus the recent ring, never the whole archive.** As the contract and ADR-0011 R7
require: the default page is the hot units plus `recent` (at most 20 archived units); `state=DONE` or
`state=CANCELLED` selects archived units through the index, proportional to the answer (`archive.archived_units`);
`kind` and `parent` filter the selected scope. Paging never widens the scope.

### 4.7 The event endpoint of ADR-0012 D8

**Question.** ADR-0012 D8 says the dashboard backend "initially serves `GET /api/v1/events?since=R` as a bounded long
poll", and the M4-D triage deferred it to F20.2. Contract 0.1.2 has no such route.

**R16. Not in F20.2. It is a contract addition, so it waits for a contract version and a renewed C0 review.** The
frontend is frozen and polls each projection on its own interval (2 to 10 s) with ETags, which the integration review
found correct for the contract. Serving an unlisted route would put behaviour outside the accepted contract into the
product. The register gets a row for it (F20.7, Unscheduled, "on measured need": the poll intervals are the measure),
with the design fixed enough to build when wanted: the cursor is the revision; the reply says only which revisions
changed which kinds and ids (the outbox's typed events, `aew history log --since R --json` is the same data); the
long poll waits on `local/wake` through the lock-free check of §4.8 and returns within a bounded time (30 s) with
nothing when nothing changed; the frontend then refetches the authoritative projections with their ETags. F20.2
builds the lock-free revision reader D8 will reuse, so nothing is foreclosed.

### 4.8 Reading state without the control lock

**Question.** ADR-0012 D3 says a reader finds the current revision from the cheap authority-file identity and the
cached parse the engine already has, and never repeatedly parses `control.yaml`; invariant 4 says a long-lived reader
uses the identity stat. Today `ControlStore.read()` takes the control lock and runs recovery (roll-forward of an
unfinished transaction, the post-commit checks). The D1 review's F3 finding showed what that costs a follower: one lock
round trip and the whole read path per wake, with writers waiting behind it. A dashboard with four to six projections
polling every few seconds is exactly that follower.

**R17. The server reads the committed state lock-free, through a stat-then-digest cache, and takes no control lock
per request.**
- `ControlStore.read_committed()` (additive, §4.15) reads `control.yaml`'s bytes without the lock, hashes them, and
  returns a copy of the cached parse when the digest is unchanged, else parses (schema-validated, as `_load` does) and
  caches. It runs **no recovery**: it is what the file holds, which under ADR-0001's atomic replace is always one
  complete committed state.
- `ControlStore.control_identity()` returns the file's `(st_mtime_ns, st_size, st_ino)`; the server stats first and
  reads bytes only when the identity changed, so a poll on an idle project costs one `stat`.
- A lock-free reader can observe a committed revision whose staged record files are not yet applied (the window
  between a commit and its apply, which recovery would close). The server treats a record file that is missing or
  whose hash does not match its pin as a failed refresh: `500 PROJECTION_FAILED`, which the contract defines as "keep
  last-known-good content visibly stale", and the next poll succeeds once the apply has happened. It never invents a
  gap and never repairs anything.
- The history index is used as `history_list` uses it (`archive.index(state)`: `sync` to the state's root, with the
  private-copy fallback when the shared index is busy or read-only); the index is derived data, never authority.
- Run records (`runs/<run>/run.json`) are observed telemetry read without any lock, as `harness_status` reads them.
- On Windows, a reader holding `control.yaml` open can make a writer's `os.replace` retry (the store's
  `replace_with_retry` exists for this); the server reads the bytes in one short call and holds nothing open between
  requests, and the stat-first cache makes most polls touch no file but the stat.

### 4.9 Answers to the web agent's W01 questions

- **Q01, bootstrap and authentication changes; the explicit session reset.** Bootstrap is the one-time URL (§4.3): it
  sets the cookie and lands on `/`; the frontend's first `GET /api/v1/project` is the bootstrap read and binds the
  project id. Authentication changes are signalled only by `401` (`SESSION_REQUIRED` when there is no valid session,
  `SESSION_EXPIRED` when it ended); there is no push and no second scope, so nothing else can change. There is no
  reset endpoint: the reset is a new one-time URL (`aew dashboard open`), which is a full navigation and a fresh
  document; the frontend's own `resetReadSession` is a client-side concern and needs no server call. `403` is never
  authentication; it is a capability that is not AVAILABLE for that route.
- **Q02, which inputs affect projections; scope selection.** One server serves one project: the `.aew` root it was
  started in. Every envelope carries that `project_id`. The only request inputs are the contract's query parameters;
  no project, worktree or attempt input exists, and workspaces, worktrees and attempts never alter a projection,
  which reads the authoritative control state and its records. Multi-scope reads are out of scope: a second project is
  a second server on another port.
- **Q03, retained historical snapshots; unavailable history.** The engine keeps no snapshots of past control state:
  the current hot state, and the append-only cold history (ADR-0011). `/history` serves cold records by stable seq
  and id, `/work/{id}` serves an archived unit's record as it stands now (R7). Pinned historical comparisons are not
  offered and nothing in 0.1.2 asks for them. Unavailable history is a capability state, never a silent empty list:
  `history` and `integrity` are `UNAVAILABLE` with `MIGRATION_REQUIRED` on a v1 project (remedy: `aew migrate`) and
  `HISTORY_INDEX_UNAVAILABLE` when the index cannot be synced or read.
- **Q04, ETags.** §4.12: the validator is a strong ETag over the whole representation less `generated_at`, plus the
  request scope (route, project, filters, limit, cursor). A `304` carries the ETag the client sent and no body, so it
  can disclose no revision the client has not seen; a revision change always changes the body, so it is always a
  `200`. The frontend's two diagnostics (a revision change under an unchanged ETag; a `304` with a different ETag)
  are both impossible by construction and are asserted in the conformance tests.
- **Q05, future Journal, context and guarantee schemas.** Main-line M6 owners (F21 for capture and recall, F13 for
  capabilities), each as a contract version with its own C0 review and digest; the server serves nothing of them.
  In 0.1.2, `/knowledge` projects the engine's decision records (`Knowledge.kind: decision`); the engine produces no
  `fact` or `assumption` records today, so none appear.
- **Q06, denied records and diagnostic identities.** There is one scope, the whole project, read-only, so no record is
  denied per session. What is withheld is withheld by **construction, not by filtering**: every projection is built
  field by field from an allowlist, never by passing an engine record through, and the server emits no storage path,
  run directory, environment, provider key, verifier or credential string (`archive_ops.redact` is applied to every
  body as a second layer, and a test scans every response for the credential pattern and for `.aew/` paths). The
  identities disclosed are AEW ids: work units, invocations, runs, evidence, decisions, audits, and token **ids**
  (`tk_…`, which `History.links.tokens` already lists; never verifiers). Error bodies carry a code and a message the
  server wrote; an engine exception's text goes to the server log only, never to the client.

### 4.10 Projections: what each route reads

One snapshot per request: the server reads the state once (§4.8) and builds the response from it, so `/overview` is
"one coherent composite projection from a single control-state read". Different routes polled at different times may
show different revisions; the frontend reconciles them (the core review's FR-2 fix). The sources, by route:

| Route | Engine source | Notes |
|---|---|---|
| `/project` | `project_id`, the manifest's `project.name`, `aew.__version__` | |
| `/capabilities` | §4.11 | |
| `/overview` | the snapshot; `resume_ops.next_actions`, `status_ops.contradictions`, `finished_summary`, `history.audit_status`, `state.recent` | `work`: at most 6 hot units, those with attention first, then most recently changed; `runs`: at most 6 active invocations; `attention`: the first 6 of `/attention`; `activity`: the newest 10 transitions; `counts.work.open`: hot open units, `done`/`cancelled`: archived counts by state; `counts.runs`: active invocations; `recent`: the ring, at most 20 |
| `/work`, `/work/{id}` | `units.view` (hot, or archived as it stands now), the unit record, `units.rollup`, `archive.archived_child_ids`, `archive.archived_units`, `integrated_commits`, `dependencies` | `summary`: the record's goal as plain RichText; `reasons`: `blocked_by`; `related`: `depends_on` as EntityRefs; `updated_at`: the unit's last recorded transition; `children` truncated at 250 with `children_truncated`; `integration` from the unit's integration binding; `has_attention` when the unit appears in `/attention`; `archived` from where it was found |
| `/runs`, `/runs/{id}` | `state.invocations`, `archive.rehydrate` and `rehydrate_invocation` for recent archived units (as `harness_status` does), `runlog.observed_status`, `run_authority_problem` | `runs[].status` is observed telemetry and can change without a revision; `authority` is the engine's text |
| `/evidence`, `/evidence/{id}` | `knowledge.evidence.scan` per hot unit, `held_evidence` from a bundle for an archived `work=` filter, `freshness` for currentness | `bindings.evaluated_snapshot` without `workspace_id`; `producer` curated to the contract's six fields; `body` as markdown RichText |
| `/knowledge`, `/knowledge/{id}` | the decision records (`knowledge.records.read_record`) | `kind: decision`, `state: recorded`, `decision_type` from the record |
| `/history`, `/history/{id}` | `archive.index(state)`: `list` with the seq bound, `by_id`, `by_seq`, `moves`, `annotations`; `history_ops._public` for the path-free entry | moves applied to `parent`; `completion` omitted; `source` always present |
| `/history/integrity` | `history.audit_status(state)`, `cold.first_at`, `cold.unverified_since` | field by field as the 0.1.2 review's integration note says: `backlog` from `unverified.entries`, `oldest_unverified_at` from `unverified.oldest_at` (the P2c dates, no index read), `last_full` without `age_days`, `reasons` from the over-policy findings as coded Reasons (§4.11) |
| `/attention` | engine facts: units in `ESCALATED` and `REPLAN_REQUIRED` (`decision_required`), `REVIEW_FAILED`, `VERIFICATION_FAILED` and `VERIFICATION_INCONCLUSIVE` (`required_finding`), `BLOCKED` with `blocked_by` (`blocker`), `contradictions` and runs observed `lost` or `crashed` (`anomaly`) | `first_seen_at`: the transition that put the unit in that state; the backend decides, the frontend only displays |
| `/activity` | `outbox.read_transitions` over the transition log, newest first | one Activity per transition: `id: R<revision>`, `subject` from the transition's refs, `occurred_at`, `title` from `op` and `summary`, `reason` |

Every value the contract types as a `Timestamp` is the engine's `utc_now` format already; every id fits `OpaqueId`.

### 4.11 Capabilities, health and reason codes

**R18. Capability states are decided by the server from facts, and every reason has a code from one registry.**
`overview`, `work`, `runs`, `evidence`, `knowledge`, `activity`: `AVAILABLE`. `history`, `integrity`: `AVAILABLE` on a
v2 project whose index syncs, else `UNAVAILABLE` with `MIGRATION_REQUIRED` or `HISTORY_INDEX_UNAVAILABLE`.
`action_projection` (which gates `/attention` in the frontend): **`UNSUPPORTED` until F15.1's canonical
`ActionProjection` is its source** (designer, 2026-10-05, overriding the recommendation: no interim semantic twin built
from a slightly different set of engine facts and swapped out later), reason `AWAITS_ACTION_PROJECTION`; `/attention`
answers `403 CAPABILITY_UNAVAILABLE` meanwhile. The engine facts the frontend may still be shown (escalations, failed
gates, blockers, contradictions, crashed or lost runs) reach it through `/overview`'s bounded `attention` list,
`counts.attention` and `Work.has_attention`, which are backend-provided facts, not the action projection; if the
designer prefers those empty too until F15.1, that is a one-line change. `queue`: `UNSUPPORTED`, reason
`NOT_IN_CONTRACT_0_1_2`. `Health`: `UNHEALTHY` on a contradiction or a manifest-pin
mismatch, `DEGRADED` on an over-policy audit finding or a `lost` run, else `HEALTHY`; `observed_at` is the snapshot's
time. The codes the server can emit (`SESSION_REQUIRED`, `SESSION_EXPIRED`, `CURSOR_INVALID`, `CURSOR_EXPIRED`,
`NOT_FOUND`, `CAPABILITY_UNAVAILABLE`, `PROJECTION_FAILED`, `HOST_NOT_ALLOWED`, `ORIGIN_NOT_ALLOWED`,
`METHOD_NOT_ALLOWED`, `REQUEST_TOO_LARGE`, `MIGRATION_REQUIRED`, `HISTORY_INDEX_UNAVAILABLE`, `NOT_IN_CONTRACT_0_1_2`,
`AWAITS_ACTION_PROJECTION`,
`UNVERIFIED_ENTRIES_OVER_POLICY`, `UNVERIFIED_AGE_OVER_POLICY`, `FULL_VERIFICATION_OVERDUE`, `CONTRADICTION`,
`RUN_LOST`, `RUN_CRASHED`, `MANIFEST_PIN_MISMATCH`, `BLOCKED_BY`) live in `aew.dashboard.reasons`, and a test checks
that every code a response carries is registered with a message. The audit's over-policy findings get their codes from
a small additive change: `audit_status` returns `over_policy_detail` (`{code, message}`) beside the existing strings.

### 4.12 Conditional requests and ETags

**R19. The validator is a strong ETag over the representation less `generated_at`, plus the request scope.**
`ETag: "<sha256-hex>"` of `scope + "\n" + canonical_json(body without generated_at)`, where `scope` is the route,
the project id, the normalized filters, the limit and the cursor. `control_revision` is in the body, so a revision
change is always a new validator; telemetry (a run's observed status) is in the body too, so it also changes the
validator at the same revision, as the contract requires. `generated_at` is excluded so that an unchanged
representation can be a `304`; the client keeps the `generated_at` it has, as the contract says it must.
`If-None-Match` is parsed as a list; a strong match on any member is a `304` with the same `ETag` and the full security
headers, no body; `W/` validators and `*` never match (a `*` would let a client get a `304` for a representation it has
never seen). `HEAD` returns `GET`'s headers, `Content-Length` included, without the body. `Vary` is not needed: the
response depends on the cookie only for `401`, and the frontend caches per route and scope on its own.

### 4.13 The static build in the Python package

**Question.** The package must serve the frontend's production build with an SPA fallback, on an offline Rocky 8
host from the wheelhouse, which cannot run Node. `web/dist` is a build product and is ignored by git.

**R20. The production build is committed into the package, with provenance, and imported by a script the main line
owns.** `src/aew/dashboard/static/` holds the build (`index.html`, `favicon.svg`, `assets/*`) and `BUILD.json`,
which binds at least (designer, 2026-10-05): the frontend source commit and its tree id, the contract digest the build
was pinned to, the builder and toolchain identity (the pinned offline builder's image or version record, Node and
npm versions), the digest of `package-lock.json` and `package.json`, the build time, and the SHA-256 of every file.
`tools/dashboard/import_build.py <dist> --source-commit <sha>` copies a build in, refuses anything that is not a
regular file under `index.html`, `favicon.svg` or `assets/`, and writes `BUILD.json`. A fast test checks every hash,
that `index.html` references only files that exist, and that the build contains no demo material (the strings
`check-production.mjs` forbids: the mock service worker, the demo transport marker, fixture initialization). **The
main line produces the build** under WSL with the pinned builder (web agent, 2026-10-05), from a clean detached
checkout of the **explicitly agreed frozen frontend commit** (F20 names `7c120b4`, the core freeze; the commit to build
is agreed with the web agent and the operator before F20.5 and recorded in `BUILD.json`; the newest frontend is never
substituted silently). Where the Node builder is available, CI rebuilds and verifies the committed output
(`tools/dashboard/verify_build.py`: rebuild from `BUILD.json`'s commit with the recorded toolchain, compare every
hash); that job runs where `web.yml`'s checks run and is agreed with the web agent (§6). A rebuild of the frontend is a
new import, a new `BUILD.json`, and a reviewed diff.
`aew dashboard serve --static DIR` serves an unpacked build instead, for the web agent's local runs against live
state; F20.6's acceptance uses the packaged build only.

*Secret scanning (designer, 2026-10-05):* a minified bundle may trip the scan with high-entropy strings. **No
blanket allowlist of the assets directory.** A false positive is allowlisted by its exact finding (fingerprint) or
exact generated file, with review and the rationale recorded in the PR; the scanner is never skipped.

### 4.14 CSP, security headers, Host and Origin rules, request bounds

Checked against the frozen frontend: the CSP below is the one its own preview and demo servers already send and its
browser checks pass under, so it is known to fit the build (no inline script or style, same-origin fetch only,
`data:` images for its icons).

**R21. Headers on every response, static and API alike:**
- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src
  'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`
- `X-Content-Type-Options: nosniff`; `Referrer-Policy: no-referrer`; `Cross-Origin-Resource-Policy: same-origin`;
  `Cross-Origin-Opener-Policy: same-origin`; `X-Frame-Options: DENY` (belt to `frame-ancestors`' braces for older
  user agents); `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
- `Cache-Control: no-store` on `index.html`, the SPA fallback, every `/api/v1/` response and every error;
  `Cache-Control: max-age=31536000, immutable` on `/assets/*` (content-hashed file names).
- Never a CORS header, never `Server`, never a `Set-Cookie` outside the exchange and the `401` expiry.

**R22. Host and Origin: exact, against the origin actually bound** (designer, 2026-10-05). The listener binds
`127.0.0.1` only (no flag changes it). The `Host` header must equal `127.0.0.1:<bound port>` exactly (the port as
bound, so `--port 0` compares against the ephemeral port); anything else, `localhost` included, is `421
HOST_NOT_ALLOWED` before routing, which defeats DNS rebinding. If `Origin` is present it must equal
`http://127.0.0.1:<bound port>`, else `403 ORIGIN_NOT_ALLOWED`. An SSH tunnel therefore uses the same local port as
the server's (`ssh -L 4280:127.0.0.1:4280`), which the printed URL and the `serve` banner say. On `/api/v1/`, a present
`Sec-Fetch-Site` must be `same-origin` or `none`, else `403`. `SameSite=Strict` already keeps the cookie off every
cross-site request; these rules make the refusal explicit and testable.

**R23. Methods and bounds.** `GET` and `HEAD` only; anything else is `405` with `Allow: GET, HEAD`. HTTP/1.1 with
keep-alive; a 10 s socket timeout; a request with a body (`Content-Length` > 0 or `Transfer-Encoding`) is `400`;
request line at most 4 KiB, at most 64 header lines and 16 KiB of headers (`431`), path at most 2 KiB, query at most
2 KiB, cursor at most 1 KiB, `limit` within the contract's `1..250` (`400`), every path id matched against `OpaqueId`
before any lookup (`400`, not `404`), at most 16 requests in flight (`503` with `Retry-After: 1` beyond), responses
bounded by the contract's `maxItems`. Static paths are resolved inside the static root after percent-decoding, with
`..`, backslashes and encoded separators refused (`400`); a path with no extension that is not under `/api/` or
`/assets/` gets `index.html` (the SPA fallback for deep links such as `/work/T-0012`); an unknown path with an
extension is `404`; `/mockServiceWorker.js` is `404`. The request log goes to the server's standard error: method,
path with `/session/` codes redacted, status and milliseconds; never a query string, header or cookie.
*As built (F20.5, review of PR #90):* at most 32 connections are admitted, each a handler thread, counted at accept
before a byte is read; the next gets a prepared `503 SERVER_BUSY` with `Retry-After: 1` and `Connection: close`, and
its input is drained briefly so it reads the answer rather than a reset. The whole request head must arrive within
10 s, however slowly it trickles (the per-read timeout alone would let a slow client hold a connection for ever).
Input that ends before the head does is a client gone, never a request. The log path is percent-encoded and capped at
256 characters; the log is written by one thread from a queue of 1024 lines, a full queue drops lines, and the next
line written reports how many.

### 4.15 Engine edits, kept small and additive

M4-D is changing `engine/api.py`, the queue operations, the outbox and the invariants in parallel. The dashboard
touches the engine in six places, each additive and each with its own unit test, and restructures nothing:

1. `store.py`: `ControlStore.read_committed()` and `control_identity()` (§4.8). `read()` is unchanged.
2. `authority.py`: `lookup(tokens, token, *, archived=None)` factored out of `_lookup`, which delegates to it; the
   kind constant `OPERATOR_SESSION`. `issue_token` is unchanged; the server mints with the same helper it uses
   (`secrets.token_hex(8)`, `secrets.token_urlsafe(32)`, `sha256_text`), through a small `mint(kind, scope, *,
   generation, expires_at)` that `issue_token` then calls.
3. `history/index.py` and `history_ops.py`: `max_seq`/`before_seq` on `HistoryIndex.list`; `--before` on `aew history
   list` (§4.5).
4. `history_ops.py`: `audit_status` returns `over_policy_detail` beside `over_policy` (§4.11).
5. `cli/credentials.py` and `harness/lead_broker.py`: `dashboard serve` and `dashboard open` in `ISSUING` and
   `CREDENTIAL_EMITTING`; `session_url` in `KEYS`; a `write_to_terminal(label, value)` helper the long-running
   `serve` uses for each URL it prints (§4.2, §4.3).
6. `operator.py`: the challenge prompt's text and code factored into `challenge(code, text)` so the server can write
   the same prompt to its console for `open` (§4.2). `authorize` is unchanged.

`cli/main.py` and `cli/commands.py` register the new `dashboard` sub-command through a new `cli/dashboard_commands.py`,
as `history_commands.py` is registered today.

## 5. The slice plan

One branch and one PR per slice, in order, each merged by the operator after the lead developer's review, review
findings fixed in the same PR. Every slice validates every response it serves against the contract in its tests.
Lanes: `tests/unit/test_dashboard_*.py` in `fast`, `tests/integration/test_dashboard_*.py` in `integration`; the pty
test of F20.3 in `serial` (as AT-4b). Windows and Linux both run everything but the pty test (listed in
`platform-skips.yaml`, covered on Linux, with the Windows refusal path tested instead, as takeover is today).

### 5.1 F20.2: the read-only API and conformance

- **Enablement rule (designer, 2026-10-05):** no merged state ever serves project data unauthenticated. F20.2 lands
  the read adapter, the projections and the server class, but **no `aew dashboard` command and no listener outside
  the tests**: the server is started only in-process by the test suite, on an ephemeral `127.0.0.1` port, and refuses
  to start without a session table once F20.3 adds one. `aew dashboard serve` and `open` arrive with F20.3.
- **Files:** `src/aew/dashboard/{__init__,server,reader,projections,cursors,contract,reasons}.py`; the engine edits
  1, 3 and 4 of §4.15; `tests/unit/test_dashboard_cursors.py`, `tests/unit/test_dashboard_contract.py` (the contract loads and
  every `*Response` schema compiles), `tests/unit/test_store_read_committed.py`, `tests/unit/test_history_index_bounds.py`;
  `tests/integration/test_dashboard_api.py` (every route, GET and HEAD, against a project built with
  `tests/helpers/aewflow.py` through the lifecycle to archival: hot and archived units, runs, evidence, decisions,
  annotations, an audit; every body validated with `jsonschema` against the contract; cursors paged to exhaustion;
  History cursors surviving appends; hot cursors expiring on a commit with `409`; `400` on every invalid input;
  `404` by id; `403` on an unavailable capability; a v1 project's capability states; the lock-free read observing a
  commit without taking the lock, asserted by holding the control lock in the test while the server answers).
- **Also:** the `--before` parity on `aew history list`, with its test; the register's F20.2 row notes the lock-free
  reader; the web agent's Q01 to Q06 answers recorded in a note under `web/docs/reference/backend-questions/` are the
  web agent's to file: this PR puts the answers in §4.9 and the operator relays (§6).
- **Acceptance:** every route of 0.1.2 served and validated; no response carries a path, a verifier or a credential
  string (scan test); no request takes the control lock (the lock-held test); the contract digest asserted against
  the accepted record (`web/docs/c0-approval.json`, today `68b46527…d691`), so a contract change fails the suite until
  the record and the server are re-conformed together (the pending header correction changes the digest, §6).

### 5.2 F20.3: the dashboard session

- **Files:** `src/aew/dashboard/session.py` (the table, minting, the one-time codes, the cookie, the control
  channel); `dashboard_commands.py` (`serve` authorizes and prints the URL; `open`; `status`); engine edits 2, 5 and 6
  of §4.15; `docs/implementation/adr/0005-authority-credentials-operator.md` (§4.4's amendment, status line updated);
  ADR-0009's environment-trust table (one row: no dashboard variable exists; the broker's refusal); `tests/unit/
  test_dashboard_session.py` (the table, expiry, displacement, cookie parsing, code consumption);
  `tests/integration/test_dashboard_session.py` (the security acceptance: bootstrap sets the cookie and redirects; a
  request without the cookie is `401`; a forged, truncated, wrong-id or wrong-secret cookie is `401`; an expired
  session is `401 SESSION_EXPIRED` (the clock is injected); the one-time URL used twice is `410` on the second use
  and the first cookie still works; an expired code is `410`; a cross-site `Sec-Fetch-Site` does not consume the code;
  stopping the server kills every session (the next request is `401`); the kind presented to `require_lead`,
  `require_invocation` and `verify_offer` is refused; the secret appears in no file under `.aew/`, in no log line and
  in no response (scan); `serve` without a terminal is refused before anything is minted; `open` without a terminal is
  refused; `open` with a wrong code is refused and mints nothing; `open` with the right code (the code read from the
  server's console substitute) mints exactly one session); the pty test on POSIX (`serial`): `aew dashboard serve`
  at a real pseudo-terminal shows the challenge, accepts the typed code and writes the URL to the terminal, with
  `(written to your terminal)` on stdout; `tests/unit/test_credential_delivery.py` extended for the two commands.
- **Negative controls:** each security test is shown to fail with its mechanism removed (the cookie check, the
  single-use consumption, the expiry check, the table clearing, the `Sec-Fetch-Site` rule), recorded in the PR.
- **Acceptance:** F20.3's own security review, separate from the frontend's; the ADR-0005 amendment landed.

### 5.3 F20.4: conditional requests

- **Files:** `src/aew/dashboard/etag.py`; `server.py` (If-None-Match, 304, HEAD parity); `tests/unit/
  test_dashboard_etag.py` (the validator excludes `generated_at` and includes everything else and the scope; two
  scopes with equal bodies differ; `W/` and `*` never match); `tests/integration/test_dashboard_conditional.py`
  (against live projections: a `304` when nothing changed; a `200` after a commit; a `200` when only a run's observed
  status changed at the same revision; a `200` when `control_revision` alone changed (a commit that changes no
  projected field: an audit record); the `304` carries the same ETag, no body and the full headers; HEAD equals GET's
  headers; the frontend's two diagnostics impossible: a revision never changes under an unchanged ETag, a `304` never
  carries a different ETag).
- **Acceptance:** the contract's ETag and 304 descriptions hold on every route, GET and HEAD.

### 5.4 F20.5: static serving and server security

- **Files:** `src/aew/dashboard/static/` with `BUILD.json`; `tools/dashboard/import_build.py`; `server.py` (static
  routes, the SPA fallback, the header set, Host and Origin rules, bounds, the in-flight limit, the request log);
  `pyproject.toml` (`aew.dashboard` package data: `static/**`); `tests/unit/test_dashboard_static.py` (BUILD.json
  hashes; production exclusion; traversal refused; the fallback for deep links and `404` for unknown files);
  `tests/integration/test_dashboard_security.py` (every header on every kind of response; `421` for a foreign Host;
  `403` for a foreign Origin and for a cross-site `Sec-Fetch-Site`; `405` for every other method; `400` for a body;
  `431`/`414` for oversized headers, line and query; `400` for an invalid id before lookup; `503` beyond the in-flight
  limit; no CORS header ever; `/mockServiceWorker.js` is `404`; the request log redacts `/session/` codes).
- **Depends on:** a production build of the frozen frontend from the web agent (§6).
- **Acceptance:** the compiled frontend loads from the package at `http://127.0.0.1:<port>/` with the session cookie
  and shows live data in a browser; the security tests pass with each mechanism shown to fail when removed.

### 5.5 F20.6: integrated acceptance

- **Files:** `tests/integration/test_dashboard_acceptance.py` (the end-to-end flow through the real CLI as a
  subprocess with `--print-credential`: `serve`, the URL, the exchange, every page's projection fetched with the cookie
  as the frontend fetches them, the contract validated, the security headers present, a `401` after the server stops);
  `docs/implementation/acceptance` entry for the dashboard; `web/docs` is untouched: the acceptance record is the
  main line's, `docs/archive/reviews/dashboard-main-line-acceptance-<date>.md`, separate from the frontend's.
- **Browser checks:** the web agent's compiled browser checks (Playwright, in `web/scripts/`) run against the live
  authenticated server rather than the demo fixtures, driven by the main line with the web agent's scripts unchanged
  (a target URL and a cookie are inputs they already accept, or the web agent adds them: §6). The production
  exclusion, hostile-content, scope and validator isolation and UI task checks named in the integration checklist are
  re-run on the integrated system and their results recorded with the acceptance.
- **Acceptance:** recorded separately from the frontend's acceptance, as the register requires: the record names the
  server commit, the static build's `BUILD.json`, the contract digest, the tests run and their results, on Windows
  and on Linux (the Rocky 8 VM once per the test-run workflow).

## 6. Notes for the web agent

Raised here, relayed by the operator; nothing in `web/` is edited by the main line.

1. The contract header still says `PENDING_REVIEW` under `x-c0-review` while `c0-approval.json` and
   `contract-version.json` say ACCEPTED (the M4 report's "before F20.2" item). **Web agent (2026-10-05):** the header
   is stale; correcting it changes the pinned hash, so the acceptance and digest records are updated coherently,
   preserving the original review, with the wire schemas unchanged. F20.2's conformance tests therefore read the
   digest from the acceptance record rather than hard-coding it, and re-pin when that change lands.
2. F20.5's production build: **the main line rebuilds under WSL with the pinned builder** (web agent, 2026-10-05),
   from a clean detached checkout of the explicitly agreed frozen commit, retaining the production `dist/`, the source
   tree identity and the build hashes. **Operator-approved baseline (2026-10-05):**
   `4f0a710fa4831eefda248dd43cc2e144d1010189` (PR #52 merge), recorded with source/tree, contract and toolchain
   identities in the [web build agreement](../../../web/docs/reference/f20-production-baseline.md). F20
   `7c120b4` remains the historical core freeze. Never substitute newest main or silently advance this baseline.
3. The W01 ledger's answers are in §4.9; when the web agent is satisfied, the ledger rows can record the accepted
   artifact (this note's commit, contract 0.1.2, its digest) as resolved.
4. F20.6 wants the compiled browser checks to run against a live authenticated server. **Web agent (2026-10-05):**
   base-URL inputs exist; an authenticated live mode still needs implementing on the web side: it accepts the target
   URL and a private session-cookie file, starts no fixture servers, keeps credentials out of the evidence, and gives
   the fixture-specific assertions a separate live acceptance path. The demo preview contracts stay excluded from the
   production integration. F20.6 depends on that work; the main line provides the server, the cookie file (0600, in
   the scratch directory, never in evidence) and the acceptance record. The [web handoff](../../../web/docs/reference/f20-live-browser-handoff.md)
   records this missing dependency and ownership; cookie-file format and invocation still need agreement before implementation.
5. The `/history` default order is newest first (seq descending), as `aew history list` orders; `/activity` the same
   by revision. If the frontend assumes ascending order anywhere, say so before F20.2 is reviewed.
6. The `aew_session` cookie name is kept; `401` responses carry a JSON `Error` body (`SESSION_REQUIRED`,
   `SESSION_EXPIRED`); the frontend's "session required" state should tell the operator to run `aew dashboard open`.
7. `action_projection` stays UNSUPPORTED (reason `AWAITS_ACTION_PROJECTION`) until F15.1 is its source, so the
   Attention page shows the capability-unavailable state; `/overview`'s bounded `attention` list and `has_attention`
   still carry engine facts (§4.11). The queue stays UNSUPPORTED with reason `NOT_IN_CONTRACT_0_1_2`.

## 7. Decisions made (designer and operator, 2026-10-05)

The eight questions this note asked, with the designer's dispositions, relayed by the operator.

1. **R7, the `open` flow: approved, the server-console challenge.** The serving process's console is the
   authorization point; the server emits a short-lived single-use code, `open` prompts for it, the server verifies.
   Anything under `local/` may help locate or connect to the server but is never authorization. Loopback alone is
   insufficient because other local processes can reach it.
2. **R4, no per-session revoke in v1: approved, with one constraint.** Server exit invalidates every session; session
   state is process-local, never durable authority. 24 h default expiry and 32 live sessions with oldest-first
   eviction are acceptable for a read-only local dashboard. No revocation subsystem yet.
3. **R16, the D8 event endpoint: deferred.** Not in F20.2; F20.7, Unscheduled, on measured need. Polling is a
   legitimate design path; the contract is not changed before there is a demonstrated consumer.
4. **R20, the committed static build: approved, with stronger provenance and a narrow secret-scan rule.**
   `BUILD.json` binds the frontend source commit, the contract digest, the builder and toolchain identity, the
   lockfile and package digests and every file hash; CI rebuilds and verifies where Node is available; no blanket
   allowlist of the assets directory, only exact findings or exact generated files with review and rationale; the
   scanner is never skipped. The web agent's build provenance requirements (a clean detached checkout of the agreed
   frozen commit, never the newest by default) are in §4.13 and §6.
5. **R18, `action_projection`: UNSUPPORTED until F15.1** (the one disagreement with the recommendation). No
   provisional projection from a different set of engine facts to be swapped later; the frontend tolerates absent
   capabilities and never infers workflow truth. Attention facts the backend already provides may still be shown
   (§4.11).
6. **Default port 4280: approved.** Documented default; occupied means a useful failure and an explicit `--port`,
   never a silent move to another port; `--port 0` is the opt-in ephemeral form; Host and Origin checks use the
   actual bound origin, exactly (§4.14).
7. **The ADR-0005 amendment: approved** as the fifth credential kind. Project-scoped, read-only, accepted only by the
   dashboard HTTP and session boundary, never by Engine mutation paths, never projected into a model or worker
   environment, bounded by `expires_at`, invalidated when the serving process exits, issued only after the R7
   terminal challenge. A credential kind because it authenticates access to sensitive project state; zero workflow
   authority.
8. **The slice plan: approved**, with the enablement rule: F20.2 may land the read adapter and projection code, but
   the user-facing server and `open` path stay disabled until F20.3's authentication lands. No merged state ever
   routinely serves sensitive local project data unauthenticated (§5.1).

## 8. Register and ledger

- Every requirement in this note is in `docs/design/requirements-ledger.yaml` under the prefix `DAB`, tracked by
  F20.2 to F20.6, F20 (the notes for the web agent) and the new F20.7 (the event endpoint).
- The register's F20.2 to F20.5 rows gain a pointer to this note; F20.7 is added under §2 as Unscheduled.
- The status line records the approval of 2026-10-05, and each slice's PR links back to the section it builds. A later contract version (the event endpoint, the queue, the lifecycle timeline) is a new
  version of the contract and a renewed C0 review, not an amendment of this note.
