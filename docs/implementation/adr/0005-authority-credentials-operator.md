# ADR-0005 — Lead authority, credentials, and operator-authorized takeover

- **Status:** Accepted (M1). Amended for M3 (2026-09-29): credential custody and rotation. Amended 2026-10-05: a fourth credential kind, `service`, for project-scoped service principals (ADR-0013 D9; designed, built with M6b). Amended 2026-10-05: a fifth credential kind, `operator_session`, for the read-only dashboard's browser session (register F20.3; built). Amended 2026-10-06: Q12, the Lead attachment, its generations and the custody of admitted invocations (designed, not built; register F31).
- **Spec basis:** WC §5 (single-authoritative-Lead, crash-safe authority), §6; KC §7.2, §16; decision D-op-3; plan review §1, §3
- **Nature:** Resolves semantic gap A2 by operator decision. The mechanism is an implementation choice.

## Decision

- **Credentials** have the form `aew1.<token_id>.<secret>`, where the secret is 256-bit random. Control state stores only a verifier (`sha256(secret)`) plus scope, issuance, expiry and revocation. Any separate process can verify a presented credential, and the raw secret is never written to disk: packs carry only a placeholder, and a test scans the files for leaked secrets.
- **Lead generation** increases on every acquire, handoff accept or takeover. Each of those atomically revokes every superseded credential. A stale Lead write fails `STALE_AUTHORITY` before any state-dependent answer is given. Every control mutation also requires `--expect-rev` (compare-and-swap).
- **Invocation credentials** are scoped to (invocation, archetype, work unit, generation) and to the operations of the archetype's role table. They are revoked on completion, cancellation, takeover, or a handoff that does not carry them.
- **Takeover** requires out-of-band operator authorization. The engine itself reads a one-time challenge answer from the controlling terminal (`/dev/tty`, or the Windows console). There is no flag, environment variable, stdin input or API parameter that authorizes. Without a terminal it fails with `OPERATOR_AUTHORIZATION_REQUIRED`.

## Consequences and limits

- Credentials guard against accidental cross-role writes and stale writers. They are **not** an OS security boundary: all roles run as the same OS user.
- A same-UID agent that deliberately fakes a pseudo-terminal or patches the process is outside the M1 threat model (accepted by review).
- Designed follow-ups:
  - an operator-issued one-time token held outside the agent's reach;
  - an approval artifact;
  - formal Lead-lease expiry with an atomic new authority epoch.

  The `lead` record is schema-versioned, so these can be added without migrating state.
- Test-runner note: on Windows, CLI test processes use `CREATE_NO_WINDOW`. An earlier `DETACHED_PROCESS` run made console windows flash and put a real operator prompt on the developer's screen.

## Amendment 2026-09-29 — M3: credential custody, stdin handoff and rotation (ADR-0009)

The credential scheme is unchanged: same form, same verifier, same scopes. What M3 adds is where a credential may live, and one way to re-issue it.

- **Custody (operator requirement).** No raw AEW credential ever enters a model-controlled process, whether an invocation's or the Lead's.
  - A harness run's credential is written to its supervisor's **stdin pipe**, never through argv, an environment variable or a file. The supervisor holds it in memory and serves a run-scoped bridge. The agent acts through the bridge and never possesses the credential.
  - The Lead's credential is held by a **Lead broker** (`aew lead session`, `aew opencode`): taken in-process with `--acquire`, or from `AEW_LEAD_TOKEN` in the operator's own shell, which is removed from the session's environment.
  - The broker **refuses credential-emitting commands** (`lead acquire|takeover|release`, `lead handoff offer|accept`) and dispatch without `--launch`, and redacts credential strings from everything it returns.
  - The explicit-credential path (`AEW_INVOCATION_TOKEN`, `AEW_LEAD_TOKEN`, `--token`) remains for scripted roles, tests and the operator's own terminal.
- **Dispatch with `--launch` withholds the credential.** It is removed from the command's output and handed to the run's supervisor. A dispatch without `--launch` still prints it (M1 behaviour), and that credential dies at the invocation's first launch.
- **Rotation is re-issuance, not new authority.** Every `aew harness launch` of an existing invocation revokes its current credential with reason `rotated: R-…` and issues a new one with **the same scope**, in the commit that records the new run (`rotate_invocation_token`). At most one run can act for an invocation.
  - A rotated credential presented to the engine is `STALE_AUTHORITY`, naming the rotation.
  - Oracle rule 17: no evidence postdates the revocation of its own credential. Rule 18: at most one live run per invocation, and while the invocation is active its latest run holds its credential.
- **Takeover is unchanged.** It stays operator-at-terminal; no broker or harness can perform it.
- **Threat model unchanged.** Custody closes inheritance, printing, transcripts and files, the accidental and persistent exposure paths. It is not an OS boundary: a same-UID process can still read the supervisor's memory on Windows (ADR-0009, "Residual risk"). On Linux the supervisor is non-dumpable.
- **Evidence:** the five custody properties, on both the invocation and the Lead side (`harness-conformance.md` §3); AT-17; the step-2 focus cases (`m3-ambiguity-report.md`); the dogfood's credential scans, clean in all 47 runs (`m3-dogfood-report.md`).

## Amendment 2026-10-05 — a fourth credential kind, `service`, for project-scoped service principals (ADR-0013 D9)

ADR-0013 D9 accepted one non-Lead committer: a project-scoped `knowledge_service` principal that may commit a closed
`knowledge.*` transaction family and nothing else. This amendment gives it a credential. The scheme is unchanged:
same form, same verifier, same issuance and revocation fields, same custody rules. The text follows the D9 spike
(`docs/research/knowledge-service-identity-spike-2026-10-04.md`), which proved the boundary on a review branch on
Windows and on Rocky 8.10, the operator takeover through a real pty included; the designer approved the direction on
2026-10-05 and decided the one open question (expiry). **Designed, not built:** the implementation lands with M6b
(register F21). Until then nothing issues a `service` credential.

- **Kind.** `tokens[*].kind` gains `service`, beside `lead`, `invocation` and `handoff_offer`. Same form
  `aew1.<token_id>.<secret>`, same verifier, same `issued_at`, `expires_at`, `revoked_at` and `revoke_reason`.
- **Scope `{service, family, issued_by}`, and no generation.** `service` names the principal
  (`knowledge_service`), `family` the one transaction family it may commit (`knowledge`), `issued_by` the Lead actor
  that issued it (kind, session label, generation). The credential carries no Lead generation because it grants no
  Lead authority: handoff and takeover revoke the `lead` and `handoff_offer` kinds and leave it alone, and the new
  Lead may revoke it. The registry of principals and their families is a table in code (`SERVICE_FAMILIES`), never
  data the credential carries, so no issuance can widen a family.
- **Issued, rotated and revoked only by the Lead.** `aew service issue <principal>` (Lead credential, `--expect-rev`)
  is a Lead transition `service.issue`: it revokes the principal's previous credential (`rotated by the Lead`) and
  issues the new one in the same commit, printing the secret once, to the terminal, as every credential-emitting
  command does (ADR-0009, amendment of 2026-10-04). `aew service revoke` ends it; `aew service show` shows the token
  id, issuance and issuing generation, never the secret. At most one live credential per principal (ADR-0013 oracle
  rule 33). The principal cannot mint, extend or rotate itself: `service.issue` and `service.revoke` are Lead
  transitions, `require_lead` and `require_invocation` refuse a service credential, and it cannot acquire, offer,
  accept, take over or release the seat.
- **One closed transaction family, enforced by the store.** A service credential admits exactly one family.
  `Kernel.service_txn`, beside `lead_txn`, checks the kind, the family and `--expect-rev`, requires a v2 project and
  the manifest pin, and commits once. The control store refuses at commit, before validation and before anything
  touches disk, any transition under a service actor that changes state outside the family: only the family's keys
  (`knowledge` and its counters, `cold` through the one history append, `revision` and `last_transition`) may differ
  between the committed state and the proposed one, every staged or pre-written path must lie under the family's
  directories (`knowledge/`, `history/`), and the op must carry the family prefix. The refusal is
  `TRANSACTION_CLOSURE`; `control.yaml` is unchanged and no redo record is staged. Because the store compares states
  rather than trusting the caller, a bug in a higher-level operation or a hostile call site reaching `Session.commit`
  fails the same way as a command-layer attempt. ADR-0013's oracle rule 29 (the closed service transaction) is
  thereby an enforced property, not only a tested one.
- **A service transaction archives nothing.** It runs none of the Lead transaction's finalizers (archival, and
  from M4-D3 the queue step, which may write `queue` on a project created before the queue existed, a write outside
  the knowledge family that the store would refuse): it appends its own history entries and archives no unit, ends no
  credential and prunes no observation. Finished work waits for the
  next Lead commit, so a service commit is never mistakable for the Lead's in effect.
- **Custody is the Lead's.** No raw service credential enters a model-controlled process. The Lead broker refuses
  `service issue` as it refuses the Lead's credential-emitting commands (ADR-0009); the agent environment allowlist
  never carries `AEW_SERVICE_TOKEN`; the secret is never written to a file (the store holds the verifier); outputs
  are redacted. `AEW_SERVICE_TOKEN` is the explicit-credential path for the service's own process, as
  `AEW_LEAD_TOKEN` is for the operator's shell. Where the capture service's process keeps its credential is an M6b
  decision (an `aew knowledge serve` broker like `aew lead session`, or a supervisor-held stdin handoff as for runs);
  either reuses an existing custody pattern.
- **No mandatory expiry in v1 (designer, 2026-10-05).** `expires_at` exists on the record and stays unused for service
  credentials. A forgotten principal is ended by the Lead (`service revoke`), by the next Lead after a handoff or
  takeover, or by operator policy. A later version may set an expiry without changing the record's form.
- **Threat model unchanged.** The credential is a scoped capability inside this ADR's same-UID model, not an OS
  boundary. What it adds is a second durable committer whose every commit the store confines to one family; what it
  does not add is a second workflow authority, a second state machine or a Lead substitute (ADR-0013 D9).
- **Evidence (the spike, not yet the main line):** `tests/integration/test_service_identity.py` on the review branch:
  issue, rotate and revoke; a knowledge commit that changes nothing outside the family; closure enforced by the store
  whatever layer asked, including a commit straight through `store.session()`; the credential refused everywhere
  outside its family; a cooperative handoff and an operator takeover leave the principal valid and the new Lead able
  to revoke it; the secret in no file, output or agent environment; `MIGRATION_REQUIRED` on a v1 project.

## Amendment 2026-10-05 — a fifth credential kind, `operator_session`, for the read-only dashboard (F20.3)

The dashboard (register F20) reuses AEW's credential system for its browser session rather than adding a second
identity (operator, 2026-10-03). This amendment gives that session a credential; the designer approved it on
2026-10-05 as the fifth kind: project-scoped, read-only, accepted only by the dashboard's HTTP and session boundary,
never by an Engine mutation path, never projected into a model or worker environment, bounded by `expires_at`,
invalidated when the serving process exits, issued only after the operator's typed-back code at a terminal. The
scheme is unchanged: same form, same verifier, same record fields, same lookup. The design is
[`dashboard-main-line-api-design-v0.1.md`](../../design/proposals/dashboard-main-line-api-design-v0.1.md) §4.1 to
§4.4; the code is `src/aew/dashboard/session.py`, `control.py`, `service.py` and `src/aew/cli/dashboard_commands.py`.

- **Kind.** `operator_session`, beside `lead`, `invocation`, `handoff_offer` and `service`. Same form
  `aew1.<token_id>.<secret>`, same verifier, same `issued_at`, `issued_by_generation`, `expires_at`, `revoked_at` and
  `revoke_reason`. `authority.mint` creates the record (it is what `issue_token` now calls); `authority.lookup`
  verifies it (it is what the engine's own `_lookup` now delegates to).
- **Scope `{surface, project, operations, authorized_by}`, and no generation.** `surface` is `dashboard`, `project`
  the project id, `operations` exactly `["dashboard.read"]`, `authorized_by` `operator-tty`. The credential carries
  no Lead generation because it grants no Lead authority: handoff and takeover revoke the `lead` and `handoff_offer`
  kinds and leave it alone (`issued_by_generation` records the generation at issue, for provenance only). It
  authorizes **no engine operation**: `require_lead`, `require_invocation` and `verify_offer` refuse it as they
  refuse every foreign kind, and no transaction ever runs under it. It authenticates a browser to the local dashboard
  server, whose every route is a read.
- **Never in control state.** The record lives only in the memory of the `aew dashboard serve` process, in a table
  with the token table's shape (`SessionTable`), verified by the same lookup the engine uses over its own table:
  the same credential form, the same constant-time verifier comparison, the same expiry rule. Nothing about it is
  written to `control.yaml`, to the history or to any file. `local/dashboard/server.json` and `control.key` hold the
  server's endpoint and the control channel's key, never a verifier or a secret; `local/` is disposable and never
  authority (ADR-0011).
- **Issued only after operator authorization at a terminal.** `aew dashboard serve` authorizes with the typed-back
  challenge code at its own controlling terminal (`operator.authorize`, as takeover does), binds `127.0.0.1` (default
  port 4280; an occupied port is an error, never another port), then mints. `aew dashboard open` asks the running
  server over its local control channel; the server writes a one-time code to **its own console** (naming the
  requester the client reported) and accepts the session request only with that code typed back from the requesting
  terminal, compared in constant time, once, within 300 s. A process without a terminal is refused at the delivery
  rule, or by `open`'s own terminal check **before it contacts the server**, so a requester that cannot type the code
  back never puts a challenge on the operator's console; a server without a console authorizes no `open`. Every
  challenge prompt (takeover's included) says: type the code only into a terminal you opened yourself, never give it
  to an agent or paste it into a chat, because the code is the authorization and a model with a shell could ask for
  it. No flag, environment variable, stdin input, file or API parameter authorizes a session: the key file locates
  the server and authorizes nothing.
- **Delivered once, as a one-time URL.** The command writes `http://127.0.0.1:<port>/session/<code>` to the operator's
  terminal (the credential delivery rules of the 2026-09-29 amendment apply: terminal only, or `--print-credential`
  for a script; refused in a Lead session). The URL carries a single-use bootstrap code of 256 random bits, valid
  ten minutes, not the credential. The browser exchanges it (`303 See Other` to `/`) for the `aew_session` cookie
  (`HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age` to the expiry; no `Secure` on the plain-http loopback origin)
  holding the credential; the server then keeps only the verifier. A used, expired or unknown code is `410 Gone` with
  a page naming no code; a navigation whose `Sec-Fetch-Site` is not `none` or `same-origin`, or whose
  `Sec-Fetch-Mode` is not `navigate`, or that is a speculative prefetch (`Sec-Purpose` or `Purpose: prefetch`), is
  `403` and does not consume the code. The server logs `/session/<redacted>` and sends `Referrer-Policy: no-referrer`.
- **`expires_at` is set and enforced: the first credential kind with a real expiry.** A session lasts the configured
  lifetime (default 24 h, `--session-hours` 1 to 168) and ends when the serving process ends, because the table ends
  with it (`401 SESSION_REQUIRED` on the next request). An expired or displaced session is `401 SESSION_EXPIRED` with a
  `Set-Cookie` that removes the dead cookie; the expired record is kept seven days so that answer stays "expired"
  rather than becoming "unknown" when later mintings purge the table. The table holds at most 32 live sessions; the 33rd displaces the oldest
  (`revoke_reason: "superseded: session limit"`). A later `aew dashboard open` issues a new session; it does not
  extend an old one. No revoke command in v1 (designer, 2026-10-05): the operator stops the server.
- **Custody is the operator's.** The raw secret never enters a model-controlled process: the Lead broker refuses
  `dashboard serve` and `dashboard open` as it refuses the Lead's credential-emitting commands; no dashboard
  environment variable exists (ADR-0009's table); the server redacts credential strings from everything it logs or
  returns, and the control channel's status reports ids and times only.
- **Threat model unchanged.** The credential is a browser-authentication capability inside this ADR's same-UID
  model, not an OS boundary: a process running as the operator can read `.aew/` directly. What it adds is that no
  other origin, tab or page can read the operator's project through the dashboard. The requester shown on the
  serving console is what the requesting process reported about itself; the typed-back code, not that label, is the
  authorization.
- **Evidence:** `tests/integration/test_dashboard_session.py` (F20.3's security acceptance): the bootstrap sets the
  cookie and redirects; no cookie, a forged, truncated, wrong-id or wrong-secret cookie is `401 SESSION_REQUIRED`;
  expiry and displacement are `401 SESSION_EXPIRED` under an injected clock; the one-time URL reused is `410` while
  the first cookie works; an expired code is `410`; a cross-site navigation does not consume the code; stopping the
  server ends every session and removes the endpoint files; one server per project (a second is refused at
  construction and again at start, under the endpoint lock), and cleanup removes only the files that server
  published, holding the lock from the identity read through the deletions; `open` with the console's code
  mints exactly one session,
  with a wrong code, without a terminal, after the timeout or without a server console mints nothing; `serve` and
  `open` without a terminal are refused before anything is minted; a Lead session refuses both; the secret appears in
  no file under `.aew/`, no log line and no response; `serve` at a real pseudo-terminal (POSIX, serial lane).
  `tests/unit/test_dashboard_session_table.py`: the table, and the kind refused by `require_lead`,
  `require_invocation` and `verify_offer`.

## Amendment 2026-10-06 — Q12: the Lead attachment, generations and child custody (designed, not built)

The designer's Q12 decision (decision record [`decisions-2026-10-06-q12-hosting-and-lead-attachment.md`](../../design/decisions-2026-10-06-q12-hosting-and-lead-attachment.md)) governs this amendment; register F31 builds it. Until F31 is built, the
behaviour above stands.

- **Lead authority belongs to an AEW attachment, not to a harness process.** An attachment binds a project, the Lead
  seat, a generation, an effective execution profile and the broker's project capability. The harness and its model
  may exist before an attachment, outlive it and attach again.
- **Every attachment is a fresh generation.** Opening one (`aew open`) is a new generation, as acquire, handoff accept
  and takeover are today. Closing it (`aew close`), or losing it to a harness crash or host loss, revokes the Lead's
  credential and stales the generation; persistent project state is untouched. An old generation never regains
  mutation authority, and its calls get `STALE_AUTHORITY`. A closed attachment leaves the model no AEW project
  authority and no AEW project access (decision record §5; what access covers, §12). A normal model turn ending changes
  nothing.
- **What happens to admitted invocations is the operator's choice (decision record §13).** Above, an invocation
  credential is scoped to the Lead generation and revoked on takeover, and a cooperative handoff interrupts every
  invocation it does not carry; a Ticket waiting on one becomes `INTERRUPTED`. Under Q12, when a Lead attachment ends
  (`aew close`, harness crash, host loss, takeover, or a handoff that does not carry them), the operator chooses at the
  operator terminal:
  - **drain** (the default, whenever no operator choice is made, including a Lead's own `aew close`): each child keeps
    its own narrow credential, finishes within a time limit and hands in; its results are recorded and **held**, and
    nothing moves a Ticket until a current Lead or the operator accepts them. Anything going wrong during the drain
    stops the run at once and reports an error to the operator;
  - **stop now:** the children are stopped and their credentials revoked, as takeover does today;
  - **release to manual:** their credentials are revoked and they keep running inside their supervisor's sandbox and
    limits until their deadline, outside AEW's governance.

  A Lead never chooses stop now or release to manual. The generation an invocation was admitted under stays recorded
  for provenance and grants no Lead authority. How a draining child's credential outlives that generation is F31's
  choice.
- **What does not change.** The credential form, the verifier, compare-and-swap on `--expect-rev`, and takeover's
  out-of-band operator authorization. Held results satisfy WC §5's stale-writer guard because only their acceptance,
  by the current generation, moves a Ticket (decision record §11, for the designer to confirm). WC §8.2's crash rule still marks an invocation `INTERRUPTED`/unknown when its own
  custody is lost (its supervisor or the AEW host is gone); losing only the Lead's attachment is not that (decision
  record §11, the lead developer's reading, for the designer to confirm before F31 is built).
