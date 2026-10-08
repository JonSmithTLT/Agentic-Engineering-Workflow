# M4-E plan v3: governed stages on the typed Lead surface

- **Status:** v3 (second revision, after the v3 review), 2026-10-07, lead developer. The operator approved M4-E (2026-10-07), subject to an independent CLEAR
  review of this plan; nothing is built before that review is CLEAR. v2 answered the v1 review (`AEW-reviews/plan-m4e-v1/REVIEW.md`: B1, B2, M1 to M12, m1 to m5) and
  recorded the operator's authority decisions Q1 to Q3 (§3). v3 answers the v2 review
  (`AEW-reviews/plan-m4e-v2/REVIEW.md`: N1 to N6, n1 to n8). §11 maps every finding of both reviews.
- **In the repository:** committed as written on 2026-10-08, after its independent CLEAR review, as the record of the
  approved plan. A deviation found while building a slice is recorded in the ADR or register row it changes, never by
  editing this text. So far: E1's review (PR #130, finding 1) made a check's `timeout_s` and `guardrails.notes`
  legality-affecting, against §2.5's table, because both are inputs to a check's definition digest (ADR-0010,
  amendment 2026-10-07).
- **Register rows:** F15.4 (digest separation), F15.5 (steering and the operator capability), F15.2 (governed stages),
  F15.6 (bounded recovery: R5-1 and R5-3 only). F15.3 (role server) is M6; F15.7 (deferred recovery rows) is
  Evaluation.
- **Governing texts:** typed Lead surface v0.2 (§3.3 to §3.6, §4.4, §10 to §12); the pre-F15.2 amendment set v0.1 and
  its release gates; A1 (steering authority and envelope), A2 (launch-failure recovery safety), A3 (policy binding and
  digests); Crawl/Walk/Run steering v0.1; bounded recovery v0.1 (R5-1, R5-3); the idea note v0.4 §13, §16, §17; Q7
  v0.3.1 §2.2, §2.4, §16; the F18 hosting design v0.6 §2.1 to §2.3, §14, §20.7, §21 (development-mode rule), §24.2;
  the ADR-0004 amendment on advance publish-if-clean (HSD-22, HSD-23).
- **Baseline:** `origin/main` at `14aef49` plus #118 (policy pin, CLEAR, not yet merged). E1 starts only after #118
  merges.

## 0. What is out of M4-E, and why

| Item | Why it is out | What stands in |
|---|---|---|
| Run-health projection H1, RHN-09 (Run's notifier fed by STALLED/UNRESPONSIVE) | No M4-E stage consumes health (PFS §1); H1/U1 are not built | The notifier's M4-E events (§5, E7) |
| F15.7's deferred recovery rows | Evaluation | `recovery:` keys other than `relaunch_launch_failed` are refused by schema (BRP-08) |
| Role server (F15.3) | M6 | |
| Browser write-side confirmation | CWR §9 | Dashboard stays read and attention |
| **Remote (no-terminal) operator confirmation** | Operator Q3 (2026-10-07): needs its own authentication, replay and presentation design | Local confirmation at the operator endpoint (§2.1), plus the argv notifier for attention |
| **Production enforcement of the operator principal** (F18.6: a distinct Lead-host identity, supervisor-owned protected state) | F18.6 is the F18 production-hosting track, not before M4-H (F18 v0.6 §24.2) | M4-E builds the F18 operator endpoint and labels every record it produces `guarantee: dev` until F18.6's check passes (§2.1) |
| Anomaly *detection* beyond the sources in §2.4, and F17's consequential-observation obligation | F17 is not adopted; the designer's 2026-10-01 decision makes F15 depend only on the generic `requires_disposition` property | The minimal anomaly record and its five sources (§2.4) |
| "Anomaly catch at least the primitive baseline" (§10 hard gate) | A behavioural measure of M4-H/F19, not an M4-E unit test | M4-E's tests prove the stop and predicate paths on seeded anomalies |
| The reported stage-efficiency metrics (TLS-27, VGX-21: steps per Ticket, refusals, reads between mutations) as computed numbers | M4-H computes them | E5a adds the broker's per-call typed-tool log they are computed from (§4 E5a); M4-H combines it with the harness transcripts |
| **A1 structural absence in production** (PFS-04 release gate 1, SAE-01 to SAE-03) | Needs F18.6 | Met in M4-E **only as `guarantee: dev`**; their ledger and register status stays open ("dev only; production needs F18.6"), never done (§2.1) |
| Ticket-revision binding of a StageIntent (TRA-25) | F4 is not built | The intent binds the unit's `record_sha256` and state now; TRA-25's revision binding lands with F4 |

## 1. What exists (corrected against `14aef49` and #118)

- **The surface:** catalog and runner (`aew.surface`), `StageResult`, the tri-state `ActionProjection`, the broker's
  `lead.tool`, the `aew-lead` MCP transport, seven built normal tools (`status`, `resume`, `work_show`, `explain`,
  `harness_status`, `harness_wait`, `checkpoint`), CLI parity (`aew lead tool`), surface profiles. Five mutating stages
  plus `integration_publish` are catalogued as `DESIGNED` and refused before the runner (`surface/contract.py:171-210`).
- **Effective-class promotion is built** (`surface/classify.py:27-36`, TLS-01). M4-E records the effective class on
  the intent; it does not rebuild promotion (m1).
- **Primitive specs:** `engine/primitives.py` declares the dispatch entrypoints, `harness.launch`, the integration
  primitives and `checkpoint`. `work.create`, `plan.propose`, `work.transition`, `review.ingest`, `verify.ingest`
  (Ticket scope) and `dispatch.launch` have no spec and default to undeclared `JUDGMENT_BEARING`.
  `dispatch.launch` is its own registered internal entrypoint: run 1 of a dispatch made with `--launch`, inside that
  dispatch's transaction, covered by the dispatch's decision (`dispatch.py:97-98`), stamped on the run's provenance
  (`:324-326`) and pinned by `test_dispatch_conformance.py`. `harness.launch` is the separate command with its own
  decision (`:90-92`). Both stay; nothing is renamed.
- **Policy digests:** `Dispatch._policy_digests` hashes the gates, guardrails and checks files (not execution policy),
  and `finalize` refuses a commit whose decision was made under a different digest (`dispatch.py:276-308`). #118 pins
  every policy file the manifest puts in force (gates, guardrails, checks, execution, and any other `policy` entry) in
  control state's `policy_sha256`; any edit is an `INTEGRITY_ERROR` until the operator adopts it.
- **Integration (M4-D):** the queue and lease (`queue_ops.py`; entry states `QUEUED`, `LEASED`, `DEFERRED`,
  `AWAITING_DISPOSITION`), the `integration_attempt` custodian, the one-head-move rebuild under the same lease
  (`integration_ops.py:474-536`, `rebuilds_used`), checks-mode validation (`validation_ops.py`, contained, Linux only,
  with a transient allow-list and a project circuit breaker), and publish by CAS with reconcile. Publication needs a
  live lease (`_publishing_lease`), so today the lease is held from prepare until the Lead publishes. **There is no
  `VALIDATE_ONLY`.** In verifier mode, publication needs integration-scope `verify ingest` (status `validated`), which
  no catalog tool records.
- **Defaults:** `post_integration: {verification: true}` and `validation` defaulting to `verifier`
  (`knowledge/manifest.py:40`, `policy/validation.py`). So shipped default policy integrates in verifier mode.
- **Operator paths:** `aew.operator.authorize` (terminal challenge), the dashboard's control channel (F20.3: code shown
  at the serving console, typed at the requesting terminal), the broker's `OPERATOR_CONFIRMED`, `OPERATOR_DECIDED`
  and `OPERATOR_ATTRIBUTED` refusals (`lead_broker.py:70-147`). `operator.py:9-13` records the accepted M1 residual: a
  same-UID agent that fabricates a pseudo-terminal.
- **Not built:** anomaly records (`ActionProjection.anomalies` is always `[]`), `requires_disposition` (hard-coded
  `False` in the dashboard), per-finding dispositions, the StageIntent journal, queryable transition and ingest guards.
- **Normal surface budget,** measured as the test measures it (compact JSON of the whole `{"tools": [...]}` list): the
  7 built tools take 4,006 bytes; all 13 catalog rows built would take 11,227 bytes, against the 12,000-byte, 16-tool
  limit (`tests/unit/test_surface_mcp.py:72`).
- **Integration validation is a Lead command:** `integrate validate` takes the Lead token and runs the checks in the
  calling process (`validation_ops.py:212`, `_run`, `_commit_txn` at `:512`). The integration verifier's report
  reaches the engine only when the Lead runs `verify ingest`. A launch failure reaches the caller synchronously, as the
  launch's acknowledgement (`supervisor.py:225-236`), and its reason is free text.

## 2. Cross-cutting designs the slices share

### 2.1 Operator authority: the F18 operator endpoint (operator Q2)

**Three layers, each doing one job (operator, 2026-10-07):**

| Layer | Question it answers | Mechanism |
|---|---|---|
| F18 operator principal | Who is authorized? | The operator-only supervisor endpoint, authenticated by the operator's security principal (peer credentials) |
| Terminal challenge | Did that human intend this exact action? | A one-time code shown at the endpoint's console and typed at the requesting terminal |
| Bindings | What does the approval apply to? | The current Lead generation, revision, legality digest and policy pins, recorded with the operation |

A terminal challenge is not the boundary, and neither is a Lead credential: the Lead credential is never used to
authenticate the operator.

**The endpoint (E2):**
- `aew operator serve`, run by the operator in their own terminal: a supervisor-side service, one per project. It is
  attachment-independent and may be long-lived (HRC-01 allows attachment-scoped or socket-activated supervisor-side
  services).
- **POSIX:** an AF_UNIX socket in a directory created 0700 by the service, owned by the service's uid. The locator
  (`.aew/local/operator/endpoint.json`: path and the service's pid) locates and never authorizes. Each connection's
  peer credentials (`SO_PEERCRED` on Linux) must equal the operator principal, which is the uid that runs the service.
- **Windows:** a named pipe. Windows is a development platform with truthfully weaker labels (F23); every operation
  is `guarantee: dev`.
- **Protocol:** one JSON request per connection, `{op, args}`, never pickle, bounded size, one challenge at a time
  (the dashboard control channel's rules, F20.3). The operations are:
  - `confirm`, `mode_raise`, `grant_envelope`, `revoke_envelope` and `relaunch_breaker_reset` (E8), each with the
    peer check and the challenge;
  - `ping`, which needs no challenge and returns only liveness and the guarantee label.
- **Client commands:** `aew confirm`, `aew lead mode raise`, `aew operator grant-publication`,
  `aew operator revoke-publication` and `aew recovery breaker reset`. They only send requests and have no engine path
  of their own.
- **One endpoint, never from a Lead session (P1):**
  - `aew operator serve` refuses to start inside a Lead session: when the broker environment is present, or when its
    process chain contains a Lead session's broker or harness (the check `refuses_locally` already makes, plus the
    process-chain check `operator.challenge` already prints).
  - It refuses to start while another endpoint for the project is live (the locator's pid answers `ping`). The
    locator is created exclusively, and a stale one is replaced only after its pid is proven gone.
  - Each operation's record names the endpoint's pid and start time, so a record from a second endpoint is
    detectable.
  - These checks are dev-grade. A same-uid Lead with a shell can still run endpoint code in its own Python process,
    one of §2.1's residuals.
- **Engine entry:** the engine methods for these operations take an `OperatorPrincipal` value that only the endpoint
  constructs, after the peer check and the challenge. No CLI parser, broker relay, typed tool or recovery `cli` escape
  can construct one. A static test pins this: the module that constructs `OperatorPrincipal` is imported only by the
  endpoint.
- **Broker:** the five client commands and `operator serve` join `OPERATOR_ONLY` (never relayed, never a typed tool);
  the fail-closed classification test covers them.
- **A mode raise lasts only for the Lead generation it was granted to (P2).**
  - An endpoint `mode_raise` record binds the current Lead generation, as Q2 requires.
  - When that generation ends (crash, takeover, handoff, release), the effective mode falls back to the highest mode
    that needs no raise: the adopted default if it is not a raise, else the previous non-raised mode, else absent.
  - A new generation runs in `run` only after a fresh `aew lead mode raise` at the endpoint. The endpoint notifies
    `generation_ended` (§2.8), so the operator knows a fresh raise is needed.
  - This matches the publication envelope, which also ends with its generation (§2.2).
- **Every autonomy increase goes through the endpoint, including one made by adopting policy (N1).**
  - **What counts as a raise:** an adopted policy whose `execution.steering.mode` moves rightward (`crawl` < `walk` <
    `run`), or from absent to `walk` or `run`. Absent to `crawl` is not a raise: Crawl auto-executes nothing without
    a confirmation.
  - **Effect:** a raise adopted that way does not change the effective mode. The effective mode is always the mode
    in the latest A1 §1.3 record: an endpoint `mode_raise`, a Lead lowering, or the adopted default when that default
    is not a raise. Until the operator runs `aew lead mode raise <mode>` through the endpoint, the previous effective
    mode stays. The `status` command and the projection show "policy default `run`; effective `walk`; raise pending
    at the operator endpoint".
  - **Same rule for the sealed manifest:** M4-H's sealed manifest selecting `run` therefore takes effect only through
    the endpoint record. The pre-run operator steps (§10) include it.
  - `manifest adopt` keeps its #103/#118 terminal challenge for the policy bytes. The mode itself is never raised by
    it.
- **The endpoint also delivers notifications** (§2.8), so it must be running for unattended Run.

**The guarantee label.** Every record the endpoint produces carries `principal: {uid, method, guarantee}`:
- `guarantee: dev` whenever the operator principal cannot be shown distinct from the Lead-host principal. That covers
  Windows, any POSIX host where the Lead session's effective uid (recorded on the Lead generation at session start,
  E2) equals the service's uid, and every host until F18.6's protected-set ownership check exists.
- In M4-E, that means every record is `guarantee: dev`. The label is how the operator's rule holds: "it does not
  satisfy A1/F18 production authority and must not silently become the permanent mechanism".
- `aew operator serve` refuses to start on a host where the principals collapse unless the operator passes `--dev`
  explicitly (F18 §2.3: development bypasses are explicit and labelled). `status`, `doctor` and the dashboard show the
  endpoint's guarantee.
- A test pins that nothing in M4-E can produce `guarantee` other than `dev`, so that a later production label needs
  F18.6's check and its own review.
- The register's F15.5 and F18.6 rows record the dependency: A1 production authority requires F18.6.

**What M4-E does and does not meet.** In M4-E, and on the M4-H host as set up today, the real Lead runs as the
operator's uid. It can reach the endpoint socket, and the peer check passes. The barriers left are the challenge code
on the endpoint's console, the endpoint's refusal to start in a Lead session or alongside a live endpoint, and the
committed confirmation record (E7). None of those is a security boundary against a same-uid process. **The same-uid
residuals, stated in full:**
- running the endpoint's code in the Lead's own Python process (bypassing the CLI refusals) and answering its own
  challenge through a pty;
- reading or injecting into the operator's terminal device;
- killing the operator's endpoint and starting another after the stale-locator check;
- writing control state or `.aew/` files directly, because the protected set is not yet owned by another principal
  (F18.6).

So PFS-04 release gate 1 and SAE-01 to SAE-03 (A1's structural absence) are met **only as `guarantee: dev`**:
- their ledger and register status stays open, reading "dev only; production needs F18.6", and is never marked done;
- §7's gates say the same.

**Hardening the dev endpoint.**
- At start, `aew operator serve` calls `prctl(PR_SET_DUMPABLE, 0)` on Linux. That blocks a same-uid process from
  reading the challenge code through `ptrace` or `/proc/<pid>/mem`; Rocky 8's default `yama.ptrace_scope` is 0.
- The code is held only in that process's memory, never written to a file or to the requester's terminal.

**The negative test (operator Q2).** The operator asked for the test to run from the real Lead identity. In M4-E the
real Lead identity *is* the operator's uid, so a test from it can only show the residual. The plan therefore runs two
tests:
- **The stand-in, live on `AEW_RL8`:** run as a second local user standing in for a separated Lead host
  (`aew-lead-probe`, created once by the operator with sudo, §10). As that user, `aew confirm`, `aew lead mode raise`
  and `aew operator grant-publication` cannot reach the socket (directory 0700). With the directory deliberately
  opened for the test, the endpoint refuses the connection on the peer check before any challenge is shown. This
  proves the mechanism F18.6 will rely on. It does not prove the real Lead is excluded. That production exit criterion stays open until F18.6, as F18 already decides.
- **The real Lead identity (same uid), adversarial (A1 §6 test 1):** from inside a real `aew lead session` (the
  harness's own shell, broker environment stripped, a pty present through `script -qc`), the test checks four things:
  - the client reaches only the endpoint;
  - the challenge code never appears on the requester's pty;
  - `ptrace` attach and `/proc/<endpoint pid>/mem` reads of the endpoint fail;
  - every record the endpoint writes is `guarantee: dev`.

  It records the residual channels it cannot close on a same-uid host, such as reading the operator's terminal device
  or injecting keystrokes into it. They are recorded as residuals, not claimed as a boundary.

### 2.2 The publication authorization envelope (operator Q1)

**The operator's grant is a standing, bounded envelope, not a project-wide Ticket grant.**

**Envelope record** (`records/authorizations/<PA-n>.yaml`, cold, immutable once written; hot state keeps only the
active envelope's id, its counters and its status):

| Field | Meaning |
|---|---|
| `project_id` | the project |
| `run_manifest` | the sealed M4-H run manifest's path and SHA-256, verified when granted and re-verified at every exercise |
| `task_input_sha256` | the original task input's hash, read from the sealed manifest |
| `lead_generation` | the Lead generation the grant is for (the current one when granted) |
| `target_ref` | the authoritative ref publication may move (the project's integration ref when granted) |
| `expires_at` | an absolute UTC time; the operator gives a duration of at most 72 h |
| `max_publications` | the maximum number of successful publications; `published` counts up |
| `legality_digest`, `policy_pins` | the legality identity (E1) and #118's pins at grant time |
| `principal` | §2.1's record, `guarantee: dev` in M4-E |
| `granted_at`, `granted_rev` | when and at which revision |

**Granting.** The operator runs `aew operator grant-publication --manifest <sealed run manifest> --for <duration>
--max <n>` through the endpoint (E6). The Q7 manifest's pre-grant is that command, run by the operator before the
counted run starts. The manifest is the input, and the envelope record is the result. The scripted responder never
grants (Q7 §2.4.1). At most one envelope is active per project; a new grant supersedes the old one, and so does
`revoke-publication`.

**The Ticket belongs to the sealed run.** While an envelope is active, `work.create` stamps `authorization_envelope:
<PA-n>` on every Ticket the envelope's Lead generation creates. Tickets that existed before the grant, or that another
generation created, carry no stamp and can never use the envelope.

**What the task-input hash proves, and what it does not (n3).** AEW never sees the Lead's first prompt: the M4-H
harness types it into the Lead's session. So AEW cannot compare `task_input_sha256` with the task the Lead actually
received. What AEW can check:
- at grant, the operator passes `--task <file>`, and the grant refuses unless its SHA-256 equals the sealed manifest's
  `task_input_sha256`;
- every publication record carries that hash, so the M4-H evaluation can join each publication to its sealed task.

"Belongs to the sealed run" therefore rests on the generation stamp plus the active-envelope window. That is a reading
of Q1, listed in §9.

**The Lead's request** is per Ticket: `ticket_prepare(…, publish_if_clean: true)`. It records a **conditional
publication authorization request** on the integration attempt. The request binds §17's inputs:
- the Ticket's `record_sha256` and state (the Ticket revision once F4 exists, TRA-25);
- `commit_ready_seq` and the queue entry;
- the accepted plan and its assurance bindings;
- the obligations digest (`validation.obligation_binding`) and the legality digest;
- the Lead generation;
- the authorization conditions: §17's predicate, by version id `pic/v1`.

H (the authoritative head) and M (the candidate) are bound at lease acquisition. A request grants nothing (A1 §1.2):
it supplies the Ticket-specific bindings that exercising the operator's bounded authority needs.

**Usability check (`envelope_usable`), evaluated at every exercise inside the publish transaction.** All must hold:
- the envelope is active;
- `now < expires_at`;
- `published < max_publications`;
- the current Lead generation equals the envelope's (HSD-23);
- the sealed manifest still hashes to the recorded digest;
- the Ticket carries the envelope's stamp;
- the integration ref equals `target_ref`;
- the current legality digest and pins equal the envelope's.

Any failure makes the envelope unusable for this exercise; §2.3's not-exercised path follows.

**The publication count is crash-safe (n4).**
- **Reserved at begin:** the transaction that moves the integration to `publishing` under PIC reserves one
  publication (`reserved += 1`) and refuses if `published + reserved` would exceed `max_publications`.
- **Settled on every path:** `_finish_publish` converts the reservation to `published += 1` in the commit that
  records `integrated`. The reconcile path that confirms a CAS which landed before a crash does the same. A reconcile
  that proves the CAS did not land releases the reservation.
- So a crash between the CAS and the count can never let publications exceed `max_publications`.

**When the envelope ends.**
- A generation change, expiry, manifest mismatch, exhaustion or revocation ends the envelope (`status: ended`, reason
  recorded).
- A held result never publishes (HSD-22): under F31 drain, the custodian's held result waits for the current
  generation.
- Steering never synthesizes a grant or a request (A1 §5), and Run never makes a non-publishable projection
  publishable.

### 2.3 Integration without holding the lease across Lead think time (B2)

**Three outcomes after validation, each with its own entry state:**

| Situation | What happens | Queue entry state |
|---|---|---|
| Clean; a request exists and `envelope_usable` holds (§2.2) | The engine publishes in the same custody, under the same lease, with no Lead turn between (below) | Retired: the Ticket goes DONE |
| Clean, and no request, or the envelope is unusable | **`VALIDATE_ONLY`**: the validation result is recorded, the lease is released, the candidate is kept, and the Lead decides | **`VALIDATED`** (new) |
| Not clean (any §17 clause fails) | Recorded, not exercised; the lease is released after reconcile proves it safe; independent entries continue | `AWAITING_DISPOSITION` (existing) |

`VALIDATED` (no grant used) and `AWAITING_DISPOSITION` (something needs a decision) are distinct, and the projection
names them differently.

**`VALIDATE_ONLY` is new engine work (E6).**
- **The kept candidate.** A `VALIDATED` entry keeps its candidate and the validation run's identity: candidate,
  snapshot, check-set digest, obligation binding and H. It holds no lease.
- **The unleased-candidate rule changes.** Today `_require_integrable` treats an unleased open candidate as legacy and
  replaces it; that rule becomes "replace unless the entry is `VALIDATED`".
- **Publishing later.** `integration_publish` on a `VALIDATED` entry asks for a fresh lease grant (the
  `integrate.prepare` decision recomputed, FIFO among runnable entries; if another entry holds the lease, the call
  stops `unavailable` with the holder named). Under that lease:
  - if H is unchanged and every bound input matches, the Lead's call is the publish judgment, and publication runs as
    today (`publishing`, CAS, reconcile on a crash);
  - if H moved, the existing single rebuild runs under the new lease and validation reruns, and the entry returns to
    `VALIDATED`, because a candidate the Lead has not seen validated is not published on the old call;
  - a second move, a conflict or a refusal goes to `AWAITING_DISPOSITION` as today.

**Who drives integration after `ticket_prepare` (N2; designer, 2026-10-07): the integration custodian, not the
Lead.** Mechanical integration lifecycle work must not masquerade as Lead judgment, and must not run on the Lead's
credential (designer, 2026-10-07). M4-D already has the actor for it: the lease's custodian, the
`integration_attempt` custody invocation (`execution: engine`, no harness, model, role or credential;
`queue_ops.py:9-12`, `grant` at `:216-241`). Checks-mode evidence is already recorded "produced by the engine under
the lease's custodian invocation". E6a gives that custodian a process to run in.

| Question | Answer |
|---|---|
| Process | A **custody worker**: a short-lived engine process (`aew integrate custody <IA-n>`) spawned by whichever process committed the lease grant, right after that commit. It is spawned detached: a new session on POSIX (`setsid`); `DETACHED_PROCESS` plus `CREATE_NO_WINDOW` on Windows. Its environment is sanitized: the run bridge's curated keep-list minus every `AEW_*` broker or credential variable, so it inherits nothing of a Lead session (T1). It registers `{host_pid, started_at}` on the custodian in its own first commit (S2), the same pattern as the validation executor (`validation_ops.executor_alive`). It is never the broker, the MCP process or the model's shell |
| Principal | The custodian, not the Lead, admitted through `custody_txn` (S1, below): the custodian invocation is `active`, holds the lease and belongs to the current generation, and the caller presents the custody credential (S1). No Lead token is held or used. Same-uid, this is dev-grade like every pre-F18.6 boundary (§2.1) |
| Attribution | Every commit records `actor: custodian <IA-n>`, the lease, the `ticket_prepare` StageIntent that requested the attempt, and, where it publishes, the PIC request and the envelope |
| Trigger | The worker starts with the lease. It then waits on the outbox (`wait_for`) for the integration verifier's run to end in verifier mode |
| Authority | It adds none, and makes no judgment. It runs the policy-resolved validation, routes the result mechanically, ends its own lease (custody release is the custodian's, as today), and executes a publication only when the Lead's advance request and the operator's envelope already authorize it |
| End | The worker exits when its custodian completes. If the custodian ends for another reason (the existing M4-D3 rule: a takeover or an uncarried handoff ends it, with the lease marked `reconcile`), the worker exits without committing. Reconciliation stays the existing `integrate reconcile` path. A dead or never-registered worker ends the custodian through S2's check, which marks the lease `reconcile`; nothing is released by time alone |

**How the custodian commits (S1).** The existing contracts do
not express this. The engine's only write path is `Kernel.lead_txn`, which requires the Lead credential
(`base.py:306`). M4-D's custodian has no credential (operator, 2026-10-04). So a custodian that commits needs a new
admission path. It was escalated, and decided below:

- **One named transaction, `Kernel.custody_txn(custodian, op)`,** admitting only this allow-list:
  - the validation pin and commit;
  - routing a verifier report to `VALIDATED` or `AWAITING_DISPOSITION`, without accepting it;
  - the custodian's own lease release;
  - the PIC publish (`publishing`, then `_finish_publish`).

  Nothing else, so no Ticket transition outside these and no dispatch.
- **Admission, checked inside the transaction:**
  - the custodian invocation is `active` and holds the lease;
  - the lease's generation is the current Lead generation;
  - the caller presents the custody credential (below);
  - for a publish, the PIC request, `envelope_usable` and the §17 predicate all pass in the same transaction.
- **The functions are refactored, not reused unchanged:** `_pin`, `_commit_txn`, `release`, `integrate_publish` and
  `_finish_publish` take a principal (the Lead or the custodian) instead of a token, and every existing Lead path is
  unchanged.
- **Docs:** the ADR-0004 amendment records the new admission path.

**Decided (operator and designer, 2026-10-07): a narrowly scoped custody credential.** A pid and start time are
lifecycle identity, not authorization for control-state mutation. They stay as liveness data (S2).

- **The M4-D wording is amended** (in the ADR-0004 amendment, E6a) from "the custodian has no credential" to: *the
  integration custodian holds no Lead, role, model or harness credential. It may hold one engine-issued custody
  credential restricted to the closed integration-custody transaction family.*
- **Minted** when the integration-attempt invocation acquires the lease, in the granting commit.
- **What it binds**, at minimum:
  - the integration-attempt invocation;
  - the queue entry;
  - the integration attempt;
  - the lease;
  - the Lead generation;
  - the closed allowed-operation set.

  Control state stores only its hash, with ADR-0009's credential-record pattern.
- **Verification:** on every commit, `Kernel.custody_txn` verifies those bindings independently, plus that the
  custodian is active and owns the lease, plus every operation-specific invariant.
- **The closed operation family:**
  1. policy-resolved integration validation;
  2. routing and recording validation output;
  3. releasing its own lease, only through the existing safe-release and reconciliation rules;
  4. mechanically exercising an already-granted `PUBLISH_IF_CLEAN` in checks mode, when the complete governing
     predicate still holds.

  The `register` step (S2) is part of item 2's bookkeeping, under the same credential.
- **No judgment authority:**
  - routing a verifier report is not accepting it on the Lead's behalf;
  - the credential does not authorize publication by itself;
  - checks-mode publication still needs the operator's envelope, the exact §17 bindings, clean deterministic
    validation, current legality, head and lease state, and every other publication invariant.
- **Delivery:**
  - **Generated inside the granting transaction (V1).** The plaintext is generated there, and only its hash is
    committed with the grant.
  - **Held in memory only until the spawn:** the granting process keeps the plaintext until the spawn that follows the
    commit, writes it to the worker's pipe, then drops it. It is never argv, the environment, a file or a log. If the
    spawn never happens, `custody_register_s` ends the custodian (S2), which revokes the credential.
  - **The pipe never outlives the read (V2):**
    - it is created non-inheritable except for that one child: close-on-exec plus `pass_fds` on POSIX; an explicit
      `STARTUPINFO` handle list on Windows;
    - the worker reads the credential and closes the pipe before it spawns anything (the policy's check commands).
      The integration verifier is launched by the Lead's `ticket_prepare` stage, never by the worker, which has no
      dispatch in its closed family (W1);
    - the worker passes the credential to no child.
  - It is never inherited by or exposed to a Lead, verifier, worker harness, model process or shell. A test asserts
    it appears in no child environment, run record, log or bridge.
- **Revocation:** immediate, in the same transaction, when:
  - the custodian dies (including S2's lost-worker check);
  - the Lead generation changes;
  - the attempt is cancelled or reconciled;
  - the lease ends.
- **Guarantee:** the same-uid development topology stays `guarantee: dev`. The credential neither weakens nor replaces
  the F18 production principal boundary.
- **Tests:**
  - `test_custody_credential_bindings_checked_every_commit`;
  - `test_custody_credential_refused_outside_the_closed_family`;
  - `test_custody_credential_revoked_on_each_trigger[custodian_death,generation,cancel,reconcile,lease_end]`;
  - `test_custody_credential_never_reaches_a_model_or_harness_process` (including every check process the worker starts and
    the integration verifier the Lead's stage launches, V2, W1);
  - `test_custody_credential_grants_no_publication_without_the_envelope_and_predicate`.

**A lost custodian is noticed (S2).**
- **The worker registers itself** in its own first commit (`custody_txn` op `register`), recording
  `{host_pid, started_at}`.
- **`sync` and the endpoint's watcher** (§2.8) end the custodian when:
  - the registered worker is gone; or
  - no worker registered within `gates.post_integration.custody_register_s` (operational in §2.5, default 60) of the grant, which covers a failed
    spawn.
- **Ending the custodian marks the lease `reconcile`**, exactly as M4-D does today when a custodian stops being
  active. Nothing is released by time alone, and `integrate reconcile` settles it.
- **The notifier gains `custodian_lost`** (§2.8).
- **Tests:** `test_dead_custody_worker_marks_reconcile`, `test_unregistered_custodian_marks_reconcile`.

**`aew integrate custody` is never the Lead's (S3, T1).** It is never relayed, and it is refused when the broker environment is present. The refusal is keyed on the environment only, not the process chain, because the worker is legitimately spawned by the broker's process with that environment stripped. The real guard is S1's admission check: a Lead-shell run cannot prove it is the custodian's worker, so it commits nothing. Tests: `test_broker_spawned_custody_worker_registers`, `test_lead_shell_custody_run_commits_nothing`.

**A lease granted by `integration_publish` on a `VALIDATED` entry (T3).** The Lead's own stage publishes under
that lease. The worker registers and then waits, never racing the Lead's publish:
- if the head is unchanged, the Lead's publish completes, and the worker exits when its custodian completes;
- if the head moved, the existing single rebuild runs inside the Lead's stage, and the worker runs only the checks-mode
  revalidation of the rebuilt candidate, routing it back to `VALIDATED` (verifier mode: the stage launches the
  verifier, and the worker routes its report).

The worker never publishes on such a lease: PIC is not in play, because the Lead's call is the judgment. Test:
`test_custody_worker_never_races_the_leads_publish`.

**What the custodian does, by validation mode:**

| Mode | `ticket_prepare`'s expansion (the Lead's stage) | Then the custodian |
|---|---|---|
| `checks` | `verify.ingest` (Ticket scope), `work.transition` VERIFIED→COMMIT_READY, `integrate.prepare` | Runs `integrate.validate` (`POLICY_RESOLVED`, existing spec) under its lease, through the existing `_pin`, `_execute` and `_commit_txn`, then applies §2.3's outcome table in the commit transaction: PIC publish, `VALIDATED`, or `AWAITING_DISPOSITION` |
| `verifier` | the same three steps, then `invoke.create.mutating` (the integration verifier, the custodian's child as today) and `dispatch.launch` | When the verifier's run ends, it routes the submitted report without accepting it. A clean report goes to `VALIDATED`; anything else, including a failed or timed-out run, goes to `AWAITING_DISPOSITION`. **It never ingests the report as accepted** (§2.3, verifier mode). The Lead accepts and publishes later through `integration_publish(verification_evidence)` |

- **"Clean" for routing** is decided mechanically from the report: every claim `pass`, no required finding, nothing
  open under clauses 6 and 7. Routing is not acceptance.
- **Validation has no typed tool,** so no tool slot is spent and the Lead never runs it. The recovery CLI keeps
  `aew integrate validate` for operators and recovery.
- **What is new:** the custodian, its lease, its child verifier and its engine-produced evidence all exist in M4-D's
  contract. Only the custodian's commit path is new (S1, above), decided by the operator and the designer, not in code. The
  build never falls back to the Lead credential.

**Exercising PIC: the custodian, not the steering loop.** In checks mode, the predicate is evaluated, and the publish
begun, inside the custodian's `_commit_txn` for a clean validation result. That transaction moves the integration to
`publishing` under the same lease. The CAS and the finish run through the existing `_finish_publish` and
`integrate reconcile` paths. Steering mode never gates PIC (A1 §5; CWR §10). The custody worker lands in E6a, before
the loop (E7), so E6 is testable end to end without E7.

**The §17 predicate in code.** Each clause is a function with its own test, evaluated in order, and the first failure
is recorded as the not-exercised reason:
1. `integrate.prepare`'s `DispatchDecision` for the Ticket is still allowed;
2. the obligation binding and the legality digest are unchanged since the request;
3. the authoritative head equals H;
4. every required integration check passes (the checks-mode overall result; PIC is checks mode only);
5. no required finding remains;
6. no finding or observation that policy marks `requires_disposition` is open (§2.4);
7. no open anomaly of severity `high` concerns the Ticket or the integration (§2.4);
8. no override, waiver, conflict or unexpected policy branch was required (no waiver recorded since the request, no
   execution override on the integration, no conflict, no admission refusal).

**Validation modes covered: checks mode only (designer, 2026-10-07).**
- **The decision:** in M4-E the engine never accepts an integration verifier report on the Lead's behalf.
  `PUBLISH_IF_CLEAN` authorizes conditional publication; it does not authorize the engine to manufacture an
  evidence-acceptance judgment.
- **In verifier mode:** a clean report goes to `VALIDATED`. The model Lead takes one turn to read and accept it, and
  publishes through `integration_publish(verification_evidence)`, with a fresh lease and revalidation if the head
  moved. M4-H still works.
- **If M4-H shows that turn or rebuild is materially harmful,** a bounded pre-authorization for clean-verification
  acceptance is designed explicitly then. Authority is not widened to save latency.

**Accepting the post-integration verification on the normal surface (B2.5).** `integration_publish` gains an optional
`verification_evidence` argument. In verifier mode without a usable PIC, the Lead's call accepts the named report
(`verify.ingest.integration`, judgment `accept_verification`) and then publishes, as one stage. This follows the frozen
decision 1 of the typed surface: acceptance and the dependent step stay one typed stage. It is a stage with a
StageIntent.

**Rebuild rule (m5).** PIC survives exactly the existing single rebuild (designer, 2026-10-01). After a head move, the
rebuilt candidate is validated again under the same lease, and the predicate is re-evaluated against the new H. A
second move means not exercised, and the entry goes to `AWAITING_DISPOSITION`.

### 2.4 Anomalies and `requires_disposition` (M3)

**`requires_disposition`** (designer, 2026-10-01: a generic policy-level property).
- **Policy key:** `gates.requires_disposition: {review_severities: [...], unrequired_verification_results: [...]}`.
  It is legality-affecting (E1). The default is empty, so existing behaviour is unchanged. M4-H's sealed manifest pins
  its value (§9).
- **What it marks:**
  - a non-required review finding whose severity is listed;
  - a verification claim result that is listed (e.g. `inconclusive`) and is not already a gate failure.

  Required findings are unchanged: they must be resolved, not disposed of.
- **The disposition record:**

  | Field | Value |
  |---|---|
  | `subject` | the finding or claim id, and its evidence id |
  | `choice` | `accept_risk`, `follow_up` (with a Ticket id) or `not_applicable` |
  | `rationale` | free text |
  | `by` | the Lead generation |
  | `at`, `rev` | when and at which revision |

  It is recorded in the Ticket's record (cold with the unit), with an index in hot state while the Ticket is live.
- **Who disposes:** the Lead, through the normal `resolve` tool (§2.6) or `aew work dispose` on the CLI.
- **Who consumes it:**
  - `review.ingest` and `verify.ingest` refuse to advance past an undisposed marked item (a gate input:
    `DISPOSITION_REQUIRED`);
  - the projection shows it as a `decisions_required` entry;
  - the §17 predicate checks it (clause 6);
  - the steering loop stops on it.

  The primitive and stage paths share the guard, so stage/primitive equivalence holds.

**The minimal anomaly record:**
- **Storage:** the hot `anomalies` key holds only open anomalies; disposed ones move to the subject Ticket's cold
  record on disposal (ADR-0011: bounded hot state). The fields are `id` (`AN-n`), `source`, `severity` (`high` or
  `low`), `subject`, `detail`, `opened_at`/`rev` and `disposition`.
- **Projection:** open anomalies appear in `ActionProjection.anomalies[]`.
- **Routing (n6): only the new automatic paths stop. No existing flow gains a gate.** A `high` anomaly is an open
  obligation that:
  - stops the steering loop in every mode;
  - fails §17 clause 7, so PIC is not exercised;
  - makes the subject's projected actions `auto_runnable: false`, with their availability unchanged, and shows the
    anomaly in `decisions_required`.

  It adds no primitive guard. The existing refusals these sources come from (`WORKSPACE_MUTATED`,
  `OBSERVATION_MUTATED`, the contradiction checks) are unchanged, and the Lead can still act by explicit judgment. So
  stage/primitive equivalence holds, and no M1 to M3 acceptance or regression test changes. E5b runs the full suite
  and lists any test that does change as a finding against this plan. The Lead clears the obligation through
  `resolve`.
- **Sources in M4-E, every one an existing signal, now recorded:**

  | Source | Severity |
  |---|---|
  | `WORKSPACE_MUTATED` and `OBSERVATION_MUTATED` | high |
  | A live control-state contradiction (`contradictions()`) | high |
  | A side-effect declaration violation observed at runtime (E7: a staged primitive whose committed control-state diff touches a class it did not declare) | high |
  | A harness run ended by its hard deadline (`TERMINATED`) | low |
  | A validation infrastructure failure that reached its bound, or a circuit-breaker trip | low |

  Nothing else is detected in M4-E (§0).

### 2.5 Policy classification and the two digests (M6)

- **Scope:** every policy schema the #118 pin covers (gates, guardrails, checks, execution), not execution policy
  alone. A3 §8's "policy schema must classify every field" is read as all of them.
- **Encoding:** every property in those schemas carries `"x-aew-class": "legality_affecting" | "operational"`. A
  meta-test walks each schema, `$defs` included, and fails on any property without one. A schema loader check refuses
  an unclassified property at run time too. Container objects are classified by their leaves.
- **Classification of every existing field** (and the fields E2 to E8 add):

  | Field | Class | Reason |
  |---|---|---|
  | `gates.*` except the five fields below | legality | gates, obligations, waivers, concurrency caps |
  | `gates.post_integration.validation_deadline_s` | operational | a stop bound; changing it never makes an illegal action legal |
  | `gates.post_integration.custody_register_s` (new) | operational | a liveness bound; ending a custodian only marks reconcile |
  | `gates.history_audit.max_unverified_entries`, `.max_unverified_age_hours`, `.max_full_age_days` | operational | reported as backlog in `status` (`history_ops.py:15`, `:48`); they refuse nothing |
  | `gates.requires_disposition.*` (new) | legality | gates progression |
  | `guardrails.*` | legality | scope, protected paths and triggers decide legality |
  | `checks.checks.*.command`, `.cwd`, `.configured`, `baseline_failures` | legality | the check's definition is what validation proves |
  | `checks.checks.*.timeout_s`, `.description` | operational | stop bound; presentation |
  | `execution.containment.mode`, `.trusted_git_drivers`, `.writable`, `.hide` | legality | they can refuse a dispatch or change what a run can touch |
  | `execution.routing.*`, `execution.profiles.*` (harness, provider, model, effort, `max_steps`) | legality | they select the executor of a policy-resolved dispatch (ADR-0010) |
  | `execution.profiles.*.deadline_s` | operational | the A1 §3.2 hard deadline: authority-reducing only |
  | `execution.provider_env`, `.harness`, `.configured` | legality | they decide whether and how a run can launch |
  | `*.description`, `*.schema`, `guardrails.notes` | operational | presentation and versioning |
  | `execution.steering.mode` (new) | operational | A3 §6 |
  | `execution.steering.envelope.*` (new: `loop_deadline_s`, `max_auto_actions`, `repetition_n`) | operational | A3 §2.2 |
  | `execution.notify.*` (new: `command`, `timeout_s`, `max_output_bytes`) | operational | operator decision 1 |
  | `execution.recovery.relaunch_launch_failed`, `.breaker.*` (new) | operational, snapshotted per recovery decision | A3 §5 |

- **`legality_digest`:** SHA-256 over canonical JSON of `{file: {json-pointer: value}}` for the legality-classified
  leaves of every pinned policy file, read from the pinned bytes (#118). `operational_digest` is the same over the
  operational leaves.
- **`finalize` mapping:** `Dispatch.finalize` compares `legality_digest`, not the per-file hashes. The per-file hashes
  stay in `dependency_digests` for attribution. A `validation_deadline_s` change no longer stales a dispatch decision
  (PFS-04).
- **Adoption is never relaxed:** classification never weakens #118's pin. Every field, operational included, changes
  only by the operator's adoption. While an edit is pending adoption, an in-flight stage stops at `INTEGRITY_ERROR`
  (not `STALE_POLICY`) and continues after adoption. After adoption, a legality change stops it with `STALE_POLICY`,
  and an operational change takes effect at the next safe boundary (A3 §4) and is recorded. The notifier's argv runs
  supervisor-side, so it is never editable without adoption.

### 2.6 The normal advertised surface stays inside the budget (M7)

Measured with `aew.surface.mcp.tool_entry` at #118's head. The only new normal tools are `steering` (E2) and `resolve`
(E3). `resolve` covers stage continue and abandon (E3) and finding and anomaly dispositions (E5), so it is one tool,
not two.

| Change | Slice | Bytes |
|---|---|---|
| 13 catalog rows built (today's 7 plus the 6 designed) | E5, E6 | 11,227 |
| Trims, presentation only, semantics unchanged: drop the optional `annotations.title`; the `expect_rev` description to "your last result's revision (CAS)"; free-text descriptions to "free text"; the `execution` description to "overrides execution policy; makes the call judgment-bearing"; the `work_id` description to "e.g. T-0012" | E2 (first slice that adds a tool) | −1,099 (the reviewer's version measured −1,275; the figure kept is the conservative one) |
| `steering` | E2 | +667 |
| `resolve` | E3 (dispositions added E5) | +771 |
| `ticket_prepare.publish_if_clean` | E6 | +100 |
| `integration_publish.verification_evidence` | E6 | +113 |
| **Projected normal surface** | | **about 11,746 bytes, 15 tools** |

All figures are measured the way the test measures them (compact JSON of the whole `{"tools": [...]}` list, wrapper
included). The two new tools were measured with exactly these entries, `expect_rev` already trimmed:

```json
{"name":"steering","description":"Lower your steering mode, or ask the operator to raise it or to confirm a pending action. Requests grant nothing.","inputSchema":{"type":"object","properties":{"expect_rev":{"type":"integer","minimum":0,"description":"your last result's revision (CAS)"},"action":{"enum":["lower","request_raise","request_confirmation"]},"mode":{"enum":["crawl","walk","run"]},"action_ref":{"type":"string","minLength":1},"rationale":{"type":"string","description":"free text"}},"additionalProperties":false,"required":["expect_rev","action"]},"annotations":{"readOnlyHint":false,"destructiveHint":false,"idempotentHint":false,"openWorldHint":false}}
{"name":"resolve","description":"Settle what resume or a stop lists: continue or abandon an unfinished stage; dispose of a finding or anomaly.","inputSchema":{"type":"object","properties":{"expect_rev":{"type":"integer","minimum":0,"description":"your last result's revision (CAS)"},"subject":{"type":"string","minLength":1,"description":"a stage intent, finding or anomaly id"},"choice":{"enum":["continue","abandon","accept_risk","follow_up","not_applicable"]},"follow_up":{"type":"string","pattern":"^[A-Z]+-[0-9]+$"},"rationale":{"type":"string","description":"free text"}},"additionalProperties":false,"required":["expect_rev","subject","choice","rationale"]},"annotations":{"readOnlyHint":false,"destructiveHint":false,"idempotentHint":false,"openWorldHint":false}}
```

The added arguments were measured as `"publish_if_clean": {"type": "boolean", "description": "publish if clean, under
the operator's grant"}` and `"verification_evidence": {"type": "string", "minLength": 1, "description": "the
integration verification you accept"}`. The runner validates which `steering` and `resolve` arguments each `action`
or `choice` needs, and refuses a mismatch as a transport input error (frozen decision 8).

- **The test:** the budget test gains an exact expected tool list per slice and stays at under 12,000 bytes and at
  most 16 tools.
- **Headroom:** about 250 bytes and one tool. Any further normal tool, or growth past 11,900, stops for a budget
  decision before the slice that needs it (§9).

### 2.7 Control-state additions (M11)

New hot keys follow the `queue` precedent (M4-D): optional, v2-only (`V2_ONLY_KEYS`), absent meaning empty, schema
`additionalProperties: false` extended. No migration is needed, and no ADR-0011 amendment, because every key is
bounded by live work and moves cold with its unit.

| Key | Holds (hot) | Bound | Cold home |
|---|---|---|---|
| `stage_intents` | nonterminal intents only | at most two in flight (the Lead's call, plus one auto-run by the loop), plus intents awaiting `resolve` | `work/<T>/stage-intents/<SI-n>.yaml` when terminal; `records/stage-intents/` for a `ticket_draft` that created no unit |
| `anomalies` | open anomalies | open items only | the subject's cold record on disposal |
| `steering` | `{effective: {mode, source record, rev}, override: {mode, generation, rev}, requests: [...], confirmations: {CF-n: accepted, unconsumed}}`; never pending (unaccepted) confirmations | bounded by open requests and accepted, unconsumed confirmations | `records/steering/<date>.jsonl`, append-only, for decided items and confirmation records |
| `authorization` | the active envelope's id, counters and status | one | `records/authorizations/<PA-n>.yaml` |
| `recovery` | the relaunch breaker's window | fixed size | the relaunch record on the invocation |
| Lead generation gains `host_uid` (POSIX) | | | |

The `status` and dashboard projections read them. The dashboard's hard-coded `requires_disposition: false` is
replaced by the real value (through `aew.dashboard`'s read API, never `web/`). The dashboard contract gets a note for
the web agent if a projection's shape changes; this plan changes no contract.

**Some records stay out of control state, so they never move the revision (n5).** Each of these is derived or
operational, grants nothing, and is bounded and rotated:

| Record | Where it lives |
|---|---|
| Notifier deliveries | `.aew/local/notify/deliveries.jsonl` |
| Pending confirmations | `.aew/local/steering/pending/<CF-n>.json` |
| The loop's own state (running, stopped and why) | `.aew/local/steering/loop.json` |
| The event spool (§2.8) | `.aew/local/events/*.jsonl` |

- **Why pending confirmations can live outside control state:** a pending confirmation is a request and grants
  nothing. The **acceptance** is what grants. The endpoint commits it into control state the moment the operator
  confirms (E7, P1): a single-use confirmation record, `steering.confirmations[CF-n]`, consumed by the loop's execution
  commit. The loop never executes on the strength of a local file. That commit moves the revision, which is correct:
  it is the operator's authority arriving.
- **What still moves the revision:** the loop and the custodian commit only when they execute an action. Those commits
  are real progress, and they stale the model's `expect_rev` by design.
- **How the Lead sees it:** the Lead's next call returns `STALE_REVISION` with the current projection. A
  judgment-bearing call is then re-issued by the Lead after it reads the projection. That is the Lead re-judging, not
  an automatic replay: §3.4 rule 5 forbids only the runner retrying.
- **The bound** on in-flight intents is therefore two. E7 tests the interaction (§6).

### 2.8 Notification that does not depend on the broker (N3)

- **Who delivers:** `aew operator serve` (§2.1). It is attachment-independent and supervisor-side, so events that
  matter most while no Lead or broker is alive still reach the operator.
- **Sources it watches:**
  - control state, through the outbox's `wait_for`;
  - the event spool, where the broker (the loop), each custody worker and each run's supervisor append event lines (a supervisor
    already writes its run's records; it appends `hard_deadline` and launch-failure events);
  - the Lead generation's liveness, through the broker's existing heartbeat and generation records.
- **Events:**

  | Event | Derived from |
  |---|---|
  | `generation_ended` (crash, takeover, stale) | control state |
  | `envelope_ended` (expiry, exhaustion, generation, manifest, revoke) | control state |
  | `published_under_pic`, `pic_not_exercised` (with the failed clause) | control state |
  | `anomaly_high` | control state |
  | `confirmation_pending`, `raise_requested`, `confirmation_requested` | spool and control state |
  | `loop_stopped` (with the reason) | spool |
  | `hard_deadline` | supervisor spool |
  | `breaker_tripped` | control state |
  | `custodian_lost` (worker gone or never registered; lease marked `reconcile`) | control state and liveness |
  | `broker_gone` (no heartbeat for 2 × `POLL_S` while Run is effective) | liveness |

  Each event is delivered once per occurrence; the delivery log keys it.
- **Delivery:** the operator decision 1 notifier (E7: argv, no shell, sanitized environment, bounds), run by the
  endpoint process.
- **Run requires the endpoint:** unattended Run needs the endpoint running. Raising to `run` happens at the endpoint,
  and at each loop activation in `run` the broker checks that the endpoint is alive (its locator's pid answers a
  `ping`). If it is not, the loop does not auto-run and stops with `NOTIFIER_UNAVAILABLE`.

## 3. The operator's decisions (2026-10-07)

**Morning:**
1. **Unattended-Run notifier (E7): the generic argv notifier.**
   - An operator-configured argv, no shell, run supervisor-side.
   - A JSON event on stdin; a sanitized environment with no credential inheritance.
   - Bounded time and output.
   - It must be configured and executable before unattended Run is enabled.
   - A delivery failure is recorded and surfaced in `status` and the dashboard's attention, with no workflow effect.
2. **`PUBLISH_IF_CLEAN` confirmed.**
   - The idea note's §17 governs the predicate and bindings.
   - A1 governs grant ownership: the Lead may request, and only the operator capability grants.
   - The one-head-move rebuild rule applies; otherwise the governed non-publication/disposition path.
   - No further design text is needed before E6.
3. **Steering default: none.** A missing `steering.mode` keeps legacy/manual behaviour, and M4-H's sealed manifest
   selects its mode.

**Afternoon (the v1 review's authority questions):**

- **Q1 (B1): standing grant plus per-Ticket request, strengthened.**
  - **What the operator grants:** a standing publication authorization envelope, not a project-wide Ticket grant.
  - **What it binds to, at least:** the project, the sealed M4-H manifest digest, the original task/input hash, the
    current Lead generation, the permitted integration target/ref, an expiry, a maximum number of successful
    publications, and the applicable policy/legality identity.
  - **The Lead's role:** it requests `PUBLISH_IF_CLEAN` for an exact Ticket, with §17's bindings.
  - **The engine's check:** it proves that the Ticket belongs to the sealed run and that the request falls inside the
    envelope, before §17 can be exercised.
  - **When it stops:** a held result never publishes. A generation change, expiry, manifest mismatch or exhaustion
    makes the grant unusable.
  - Built as §2.2.
- **Q2 (M2): reuse the adopted F18 operator-principal boundary.**
  - **Through the endpoint:** `confirm`, autonomy increases and unattended-publication grants go through the F18
    operator-only supervisor endpoint, authenticated by the operator security principal. They are then bound to the
    current Lead generation, revision and policy.
  - **The terminal challenge** is human-intent confirmation, not the boundary. A Lead credential does not authenticate
    the operator.
  - **The Lead host** must be unable to reach or use the endpoint, and the negative test runs from the real Lead
    identity.
  - **Same-UID development hosts** are labelled `guarantee: dev`. That label does not satisfy A1/F18 production
    authority and must not silently become the permanent mechanism.
  - Built as §2.1.
- **Q3: remote confirmation deferred.** Local confirmations wait at the authenticated operator surface, with the argv
  notifier for attention. Run plus the bounded standing grant covers M4-H's unattended path. Remote approval needs its
  own design and stays off M4-E's critical path.

Related decisions that bound this plan: F22.1's map stays on the investigator archetype, and U3 moves to after M4-H
data (neither changes a slice).

## 4. Slices

Each slice is one PR (E5 is two), independently reviewed, and merged before the next starts. The order follows the
amendment set (PFS-03): A3 first, then the A1 capability before any confirmation or mode surface, then the journal
before any mutating stage, and A2's proofs inside the slice that can enable relaunch. Each slice's tests are in §6.

### E1. Digest separation (A3), F15.4. After #118 merges.

- §2.5 in full: `x-aew-class` on every property of the four schemas, the meta-test and loader check,
  `legality_digest` and `operational_digest` from the pinned bytes, and `finalize` on `legality_digest`.
- `DispatchDecision.dependency_digests` gains both digests. Every staged action (E3) and every dispatch records both,
  the revision, the Lead generation and any authorization digest (A3 §3).
- `history` and `explain` show both digests (A3 §9: "history records both digests").
- Docs: ADR-0010 note (policy binding), the execution-policy reference, the register's F15.4 row.
- **Size:** medium. The classification table is most of the review surface.

### E2. The operator endpoint, mode raise and lower, and the Lead's requests (A1 §1), F15.5 (part).

- §2.1: `aew operator serve`, the socket and pipe, the peer check, the challenge at the endpoint console, the
  `OperatorPrincipal` value, the `guarantee: dev` label, `--dev`, the locator, and `status`/`doctor` rows.
- The Lead generation records `host_uid` at session start (POSIX).
- **Steering mode state:**
  - The policy default `execution.steering.mode` (schema plus classification).
  - The effective mode `steering.effective`, always the mode of the latest A1 §1.3 record (§2.1, N1). An adopted
    default that is a raise does not change it. `status` shows a pending raise.
  - The session/generation override in `steering.override`. It ends at a generation change, falling back to the
    adopted default only if that default is not a raise beyond the last endpoint-authorized mode (CWR-05, CWR §5).
  - With `steering.mode` absent, the mode commands refuse with `STEERING_NOT_CONFIGURED`: legacy/manual, not a
    fourth mode (decision 3).
- **Raise:** `aew lead mode raise <walk|run>`, operator only, through the endpoint. To `run` it requires an executable
  notifier (§3, decision 1). E2 lands the notifier's configuration schema and its "configured and executable" check:
  the argv's first element resolves to an executable file. E7 lands delivery.
- **Lower:** `aew lead mode lower <crawl|walk>` is a Lead command (`LEAD_REACHABLE`), and the normal `steering` tool
  has `action: lower`. Raise and lower are separate commands, so the broker's path-based refusal refuses raise only
  (M1).
- **Requests:** `steering` `action: request_raise` and `action: request_confirmation` record a request (with rationale)
  in `steering.requests`, raise attention, and grant nothing. E7 adds notification.
- **Endpoint hardening and tests:** `PR_SET_DUMPABLE 0`, the stand-in live test, and the same-uid adversarial test
  with its recorded residuals (§2.1). The ledger and register rows for PFS-04 gate 1 and SAE-01 to SAE-03 are updated
  to "dev only; production needs F18.6".
- **Mode-change record** (A1 §1.3): operator principal or Lead, previous and new mode, Lead generation, both digests,
  effective revision. It is cold in `records/steering/`.
- `steering` is a single-transaction tool like `checkpoint` (one commit, so no StageIntent; typed surface §3.4).
- The §2.6 trims land here, with the budget test's new tool list.
- **No consumer yet:** no loop reads the mode until E7. E2's tests prove the records, the refusals and the endpoint
  (M10). `confirm` lands in E7 and the envelope grant in E6, both after E2, so the amendment order holds.
- **Size:** medium.

### E3. The StageIntent journal and R5-1, F15.2 and F15.6 (R5-1).

- **The intent (`SI-n`):**
  - **When it opens:** by CAS on `expect_rev`, as the stage's first commit (§3.4 rules 1 and 2).
  - **What it binds:**
    - the call: tool, bound arguments and judgment inputs, base and effective class (recorded from `classify`);
    - the state it started from: the starting revision, `legality_digest`, `operational_digest`, the Lead generation,
      and for a Ticket stage, the unit's `record_sha256` and state (TRA-25's revision binding waits for F4);
    - the plan: the planned primitive sequence, and the idempotency key per step (`<SI>:<step>`, so a continued
      stage never repeats a committed step);
    - the obligations digest for stages that accept evidence.
  - **What it records as it runs:** each completed step (primitive, class, revision, refs), and the stop boundary or
    `completed`.
  - **Where it lives:** hot while nonterminal, cold when terminal (§2.7).
- **Runner rules:** §3.4 rules 3 to 7 (first refusal stops, judgment never replayed, policy drift is `STALE_POLICY`,
  launch failure after dispatch is `launch_failed`).
- **R5-1, all five conditions (M5):** one retry after `STALE_REVISION`, only when:
  - the step's class is `MECHANICAL` or `POLICY_RESOLVED`;
  - the stage's effective class is non-judgment;
  - the legality digest is unchanged;
  - the authority (generation and lease, where held) is still valid;
  - the projection, recomputed at the current revision, still shows the action `AVAILABLE` with the same arguments.

  The retried step carries `retried_after_stale_revision` on the intent and in `completed_steps`.
- **`resume`** lists nonterminal intents with:
  - `safe_to_continue`: each recheck below passes now;
  - the policy and guard status;
  - the next planned step and boundary;
  - the owning generation.
- **Continue or abandon:** a replacement Lead uses `resolve` (`choice: continue | abandon`, with rationale), or
  `aew stage continue|abandon` on the CLI.
  - **Continue** rechecks the revision, the legality digest, authority and gates, and re-resolves the stage contract,
    then rebinds the intent to the current generation (F18 §14). It resumes from the first uncommitted step.
  - **Abandon** closes the intent without undoing committed steps.
  - An intent owned by a stale generation is never continued implicitly.
- **Equivalence comparisons** exclude the journal's own records (`stage_intents`, the intent's revision bump and the
  cold intent file) when comparing stage and primitive end states (M11.5).
- Docs: the typed surface's as-built note, and the register.
- **Size:** large.

### E4. Queryable transition and ingest guards (§3.6; idea note §13), F15.2. One guard per commit.

- **The query substrate:** each guard below becomes a pure `query(state, work_id, args) -> Blocker | None`. The
  execute path calls the same function, so query/execute equivalence is by construction, and a test also checks it per
  guard on seeded states.
- **Stage availability** composes per step:
  - step 1 is queried on the current state;
  - a later step's guard is queried on the current state, with inputs that earlier steps of the same stage produce
    declared `produced_by` in the stage contract and taken as satisfied;
  - any other unmigrated input makes the stage `UNKNOWN` (frozen decision 3).
- **Migrated, per stage (M4):**

  | Stage | Primitives and guards |
  |---|---|
  | `ticket_draft` | `work.create` (schema and lint validation as the guard); `plan.propose` (plan validity) |
  | `ticket_start` | `work.assign` (existing decision); `dispatch.launch` (run 1 of the assign made with `--launch`, covered by the assign decision; no separate query); `work.transition` ASSIGNED→RUNNING (`implementer_active`, produced by assign and launch) |
  | `ticket_request_review` | `work.transition` RUNNING→REVIEW_PENDING (`ready_for_review`); `invoke.create.mutating` per required review card (existing decision), each with `dispatch.launch` covered by that decision |
  | `ticket_request_verification` | `review.ingest` (report binding, `DISPOSITION_REQUIRED`); `work.transition` REVIEW_PASSED→VERIFY_PENDING (`review_current`); `invoke.create.mutating` per verification card, each with `dispatch.launch` |
  | `ticket_prepare` | `verify.ingest` (Ticket scope); `work.transition` VERIFIED→COMMIT_READY (`all_gates_current`); `integrate.prepare` (existing decision); in verifier mode, `invoke.create.mutating` (integration verifier) with `dispatch.launch`. The custodian's `integrate.validate` in checks mode is not a stage step (§2.3) |
  | `integration_publish` | `verify.ingest.integration` (verifier mode); `integrate.publish` (lease, binding, publication blocker) |

- `explain` covers every migrated guard.
- `ticket_request_verification` and `ticket_prepare` stay `JUDGMENT_BEARING`: migration gives them `AVAILABLE` or
  `BLOCKED`, never `auto_runnable` (m2).
- **Size:** large and incremental.

### E5. The four Ticket stages, F15.2. Two PRs: E5a `ticket_draft` and `ticket_start`; E5b the two request stages and dispositions.

- **Specs:** every primitive a stage expands to gets its full `PrimitiveSpec` in the slice that first stages it, with
  the declaration-conformance test (SAE-07) in that same slice:
  - E5a: `work.create`, `plan.propose`, `work.transition`, and `dispatch.launch` (`MECHANICAL`, effects
    `control_state+credential+harness_process`, idempotency `expected_revision`, guard covered by the dispatch's
    decision; the provenance it stamps is unchanged);
  - E5b: `review.ingest`, `verify.ingest`.
- **E5a, the per-call typed-tool log (n7):** the broker appends one line per typed-tool call to
  `.aew/local/lead/tool-calls.jsonl`: tool, arguments digest, effective class, `ok`, boundary and error code, revision
  before and after, StageIntent id, duration. It is bounded and rotated, and never control state. M4-H computes TLS-27
  and VGX-21's reported metrics from it together with the harness transcripts.
- **Policy-resolved card sets:** every card the effective gates require (review triggers, risk class, `review_r1`, the
  verification gates). Each card is launched, and every invocation and run is returned in the `StageResult`.
- **E5b, dispositions:** §2.4's `requires_disposition` key, the guard, the disposition record, `resolve`'s disposition
  choices, `aew work dispose`, the projection's `decisions_required`, and the dashboard flag.
- **E5b, anomalies:** §2.4's anomaly record and its first sources (`WORKSPACE_MUTATED`, `OBSERVATION_MUTATED`,
  contradictions), and `anomalies[]` in the projection. E7 and E8 add their sources.
- **Conformance:**
  - stage/primitive equivalence on the fake harness for each stage;
  - `lead_mcp` channel conformance;
  - the seeded false-advance corpus begins here (§6) and grows with each later slice.
- **Size:** medium each.

### E6. Integration on the surface and the publication envelope, F15.2 and F15.5. Two PRs.

- **E6a, `VALIDATE_ONLY` and the stages:**
  - §2.3's `VALIDATED` entry state, the kept candidate, the fresh-lease path, and the unleased-candidate rule change;
  - `ticket_prepare` (queue- and lease-aware), with its per-mode expansion (§2.3);
  - the custody worker for the lease's custodian (§2.3): checks-mode validation, verifier-report routing (never
    acceptance), the custodian's own lease release to `VALIDATED` or `AWAITING_DISPOSITION`, attributed to the
    custodian, never using the Lead credential, with a test that it adds no
    authority (it commits nothing once the generation is stale);
  - `integration_publish`, with `verification_evidence`, as a stage;
  - specs for `verify.ingest.integration` and `integrate.publish` already exist and are completed (side effects,
    guard id).
  - Docs: an ADR-0004 amendment for `VALIDATED`/`VALIDATE_ONLY`. It is ledger-gated, so the ledger rows land with it.
- **E6b, PIC:**
  - §2.2's envelope: `aew operator grant-publication`/`revoke-publication` through the endpoint, the envelope record,
    the Ticket stamp at `work.create`, `ticket_prepare.publish_if_clean`, the request record, and
    `envelope_usable`;
  - §2.3's eight-clause predicate, the exercise in the custodian's checks-mode validation commit, the
    not-exercised path, and the rebuild survival; never a verifier-report acceptance (designer, 2026-10-07);
  - the `PUBLISH_IF_CLEAN` record on publication: envelope id, request, predicate result per clause, H, M, the task
    hash, and the crash-safe `reserved`/`published` count (§2.2);
  - `--task <file>` checked against the manifest's `task_input_sha256` at grant.
  - Docs: the ADR-0004 amendment's PIC section, and the register.
- **Size:** large: two PRs, each medium to large.

### E7. The steering loop, confirmation and the notifier (CWR §7; A1 §2 to §4), F15.5.

- **Host and trigger (M8.1):**
  - The loop runs in the Lead broker (`LeadBroker`), the supervisor-side process that holds the Lead credential and
    serves the Lead's tools. It never runs in the MCP process or the model's shell.
  - Two things wake it: the commit of any Lead tool call, and a revision change seen by the broker's existing poll
    (`POLL_S`), which covers a run ending, a validation committing and a confirmation recorded.
  - Each tick runs CWR §7 steps 1 to 7. An auto-executed action runs as a normal stage call with `expect_rev`, a
    StageIntent, and attribution to the steering mode, the policy digests and the override's generation.
  - With `steering.mode` absent, the loop does not run.
- **Walk:**
  - It auto-runs an action only when every declared side effect of every step is in `{control_state}`.
  - A step with an unknown, missing or new effect class, or a declaration that fails validation, needs confirmation
    (A1 §2).
  - In practice every dispatching stage needs confirmation in Walk.
- **Runtime declaration check (SAE-07):** each auto-run step's committed control-state diff is compared with its
  declaration. An excess opens a `high` anomaly and stops the loop. E5's tests already prove conformance for workspace,
  process and ref effects (§6).
- **Confirmation (M8.2, M8.3):**
  - When `confirm_before(a)` holds, the loop writes a pending confirmation to `.aew/local/steering/pending/` (not
    control state, §2.7), appends a spool event (so the endpoint notifies, §2.8), and the tick ends. Nothing
    blocks: the Lead keeps working, and its results carry the pending item in the projection.
  - The pending record is `{ref: CF-n, action, arguments, subject, projected_rev, legality_digest, subject
    record_sha256 and state}`.
  - `StageResult.stopped.boundary` gains `confirmation_required`, a schema change to `surface.schema.json`, closed
    enum.
  - The operator runs `aew confirm CF-n` through the endpoint. It is accepted only if the same action with the same
    arguments is still projected `AVAILABLE` and `auto_runnable`, the subject's record digest, state and the
    legality digest are unchanged, and the mode still requires confirmation. Otherwise it fails `STALE` and the loop
    re-projects.
  - **On acceptance, the endpoint commits the confirmation record** (P1) into control state,
    `steering.confirmations[CF-n]`. It binds:
    - the operator principal and the endpoint's pid and start time;
    - the action, its arguments digest and its subject;
    - the subject's record digest and state, and the legality digest;
    - the Lead generation it was accepted for (R1);
    - the revision it was accepted at;
    - `consumed: false`.
  - **How the loop uses it:**
    - That commit's revision change wakes the loop.
    - The loop executes the action only against an unconsumed record whose bindings still match the live projection.
    - It marks the record consumed in the same transaction as the action's first step, so a record is used once.
    - A pending file in `.aew/local/` without a committed record is never acted on.
  - **Expiry:** an unconsumed record whose bindings no longer match is retired as stale on the next tick. When its
    Lead generation ends, an unconsumed record is retired in the same transaction, like a mode raise and the
    publication envelope (R1). Retired
    and consumed records move to `records/steering/`.
  - **Tests:**
    - `test_a_forged_pending_file_never_executes`;
    - `test_confirmation_is_single_use`;
    - `test_confirmation_ends_with_its_generation` (R1);
    - `test_operator_serve_refused_in_a_lead_session`;
    - `test_second_live_endpoint_refused`;
    - `test_raise_ends_with_its_generation` (P2).
- **Envelope (M8.4):**
  - The operational policy keys `execution.steering.envelope`:
    - `loop_deadline_s`, default 3,600;
    - `max_auto_actions` per loop activation, default 50;
    - `repetition_n`, default 2.
  - Admission is the existing concurrency gates; the loop never widens them.
  - A token or cost budget is not applicable in M4-E: AEW records no per-run spend yet, and M4-H's caps are enforced
    by the Q7 harness. The plan says so rather than inventing one.
  - The repetition key is `(action, arguments digest, subject, subject state)` with no revision change in between.
  - Each exhaustion stops the loop with attention and a notification. It is not a workflow transition.
- **Hard deadline:**
  - The invocation hard deadline is the pinned profile's `deadline_s`, which the supervisor already enforces as
    `TERMINATED` (`supervisor.py:240-272`).
  - In `run`, the loop refuses to auto-start a run whose resolved profile has no `deadline_s`, stopping with
    `NO_HARD_DEADLINE` (A1 §3.2: set before unattended execution begins).
  - Expiry terminates and revokes the run and requires reconciliation. It releases no lease, advances nothing and
    relaunches nothing. A `low` anomaly is recorded.
- **Interaction with the Lead's `expect_rev` (n5):** §2.7. Tests:
  - `test_loop_commit_stales_a_judgment_call_which_is_never_replayed`;
  - `test_two_intents_in_flight`.
- **Notifier (M8.6, N3):**
  - **Configuration:** `execution.notify: {command: [argv], timeout_s: ≤30 (default 10), max_output_bytes: ≤65,536}`.
  - **Who runs it:** the operator endpoint (`aew operator serve`, §2.8), never the broker. It runs with no shell,
    `CREATE_NO_WINDOW` on Windows, and the sanitized environment: the run bridge's curated keep-list minus every
    `AEW_*` variable and every provider-key variable.
  - **Event sources:** the broker and the supervisors append to the event spool; the endpoint also derives events
    from control state and from Lead liveness (§2.8).
  - **Input:** stdin carries `aew/notify-event/v1`: `{event, project_id, subject, reason, ref, revision, at}`.
  - **Events:** §2.8's table.
  - **Tests:**
    - `test_notifies_with_no_broker_running` (a generation ends, an envelope ends);
    - `test_loop_refuses_run_without_a_live_endpoint`.
  - **Bounds:** past `timeout_s` the process tree is killed; output past `max_output_bytes` is discarded and counted.
  - **Failure:** a non-zero exit, a timeout or a spawn failure is a delivery failure. It is recorded in the delivery
    log (§2.7), surfaced in `status` and the dashboard's attention (through `aew.dashboard`), and has no workflow
    effect.
  - **Executable check:** done at raise to `run` (E2, at the endpoint) and at each loop activation in `run`. Adopting
    a policy whose default is `run` never raises the mode (§2.1), so the check at the endpoint's raise covers it.
- **Static boundary test:** legality, gate, transition, dispatch, plan-assurance, lint, evidence-acceptance and
  publication modules never import steering.
- **Size:** large.

### E8. R5-3, one pre-work relaunch (A2), F15.6. Last; default off.

- **Policy:**
  - `execution.recovery.relaunch_launch_failed: 0 | 1`, default 0. At 0, today's Lead-mediated behaviour is
    unchanged.
  - Every other `recovery:` key is refused by schema (BRP-08, F15.7).
  - The setting is snapshotted at the recovery decision. A change before the relaunch commits re-evaluates that
    pending recovery, not `STALE_POLICY` (A3 §5).
- **Where it runs (N2c): the stage runner in the Lead broker, at the `launch_failed` stop.**
  - **Why there:** a launch failure reaches the caller synchronously, as the launch's acknowledgement. A relaunch
    needs a new `harness.launch` `DispatchDecision` committed in a Lead transaction, and it mints a credential. Both
    grant authority, so they cannot happen on the supervisor's event path, which idea note §16 reserves for
    authority-reducing reactions.
  - **How it runs:** the runner evaluates eligibility there, under the broker's Lead credential. When eligible it
    commits the relaunch as the stage's next step, attributed to the recovery policy snapshot, the stage's
    StageIntent and the relaunch record.
  - **Scope:** only launches made through a stage or the loop. A launch from the recovery `cli` escape is never
    relaunched automatically.
  - **The supervisor's part** stays authority-reducing: it records the termination and the no-side-effect
    observations that the proof reads.
- **Launch-failure reason codes (n8):** E8 replaces today's free-text launch-failure reasons
  (`supervisor.py:225-236`) with a closed enum carried on the acknowledgement and the run record, plus the free-text
  detail:
  - `SPAWN_RACE`, `SERVER_START_TRANSPORT`, `CONTAINMENT_REFUSED`, `CREDENTIAL_DENIED`, `CONFIG_ERROR`,
    `QUOTA_EXHAUSTED`, `AUTH_FAILED`, `PROVIDER_OUTAGE`, `INCOMPATIBLE_CONFIG`, `UNKNOWN`.
  - Unmapped failures are `UNKNOWN`, which fails closed.
  - The launch allow-list is its own set in the recovery module, not the validation module's `V.TRANSIENT`.
- **Eligibility (BRP-04, BRP-06), all required:**
  - the reason is on the allow-list;
  - the invocation is still active, and its dispatch decision digest and base binding are unchanged;
  - there is no attempt increment and no Ticket state change;
  - no blocked report, finding, open anomaly or required disposition exists for the subject;
  - it is the first relaunch for this invocation; a second failure raises attention and nothing more.
- **Allow-list (initial, narrow):** `SPAWN_RACE`, and `SERVER_START_TRANSPORT` before the supervisor delivered the task
  prompt.
- **Termination proof per platform (A2 §2):** every applicable custody mechanism must agree.
  - **Linux:** the supervisor's record of exit, the process group or bwrap PID namespace empty, the harness server
    gone, and the run's sentinel released.
  - **Windows:** the job object empty, the supervisor's record of exit, and the server gone.
  - Anything unobservable makes the run ineligible.
- **No-side-effect proof per channel (A2 §4):**

  | Channel | Required observation |
  |---|---|
  | Run log | no tool event beyond startup |
  | Bridge | no `check.run`, no `submit`, no authorized project action |
  | Evidence directory | no output |
  | Workspace | the fingerprint equals the dispatch's base binding |
  | Refs | unchanged |
  | Network | not observable while `network: shared`, so the run is eligible only if the supervisor's own record shows the task prompt was never delivered (no model turn could have reached the network) |

- **Credentials:** the old credential is revoked, and the revocation is confirmed through the normal mechanism. Only
  then is a new credential minted and bound to a new run id.
- **Breaker:** 3 eligible failures in 5 minutes, per harness and provider endpoint, project-wide when the cause is
  shared. Tripping it disables relaunch for that scope and raises attention and a notification. It resets only by
  `aew recovery breaker reset` through the operator endpoint (`relaunch_breaker_reset`), which reuses M4-D5's breaker
  structure with a scope key.
- **The relaunch record** binds the failed run id, the termination proof, the revocation reference, the
  no-side-effect proof, the reason code, the breaker state and the new run id (A2 §7).
- **Size:** medium to large.

### E9. Live check, F15.2.

OpenCode 2.0.18 spawns `aew-lead` over MCP and lists the normal tools, matching §2.6's list, on `AEW_RL8`. No
provider key is needed for spawn and list. This closes the last TLS-26 item.

## 5. Idea note §16 (m3)

Already met, and reused rather than rebuilt:
- the supervisor drops a run's credential at run end;
- the broker's watchdog revokes on a generation change;
- lease reconciliation covers a dead custodian.

E7's hard deadline runs on those paths: terminate, revoke, reconcile, all authority-reducing. E8's relaunch grants
authority, so it does not run on the event path. It runs in the stage runner at the `launch_failed` stop, under the
Lead credential (E8, N2c). On the event path the supervisor only records what the proofs read.

## 6. Tests per slice (M12)

Every test the designs name, mapped to a slice and a test name. The test files are `tests/unit/test_policy_classes.py`,
`test_operator_endpoint.py`, `test_stage_intent.py`, `test_guard_queries.py`, `test_stages_*.py`,
`test_integration_pic.py`, `test_steering_loop.py`, `test_relaunch.py`, and the matching integration and live tests.

| Design clause | Slice | Test |
|---|---|---|
| A3 §9: health threshold changes do not stale (no health in M4-E: an operational stand-in, `validation_deadline_s`, `deadline_s`) | E1 | `test_operational_change_never_stales_a_decision` |
| A3: steering mode change does not invalidate an in-flight primitive | E7 | `test_mode_change_mid_step_leaves_the_step` |
| A3: gate/authority change does stale | E1 | `test_legality_change_is_stale_policy` |
| A3: recovery setting changes affect only pending recovery | E8 | `test_relaunch_setting_change_reevaluates_pending_recovery_only` |
| A3: every field classified; new unclassified field fails | E1 | `test_every_policy_property_is_classified`, `test_an_unclassified_property_fails_validation` |
| A3: history records both digests | E1 | `test_history_records_both_digests` |
| A3/#118: an operational edit pending adoption stops at INTEGRITY_ERROR, not STALE_POLICY | E1 | `test_pending_adoption_is_integrity_not_staleness` |
| A1 §6: an agent shell cannot invoke the confirmation capability | E2 (endpoint), E7 (confirm) | `test_no_operator_principal_outside_the_endpoint` (static), `test_pty_and_stripped_env_reach_only_the_endpoint` (adversarial), live `test_lead_identity_cannot_reach_the_endpoint` |
| A1 §6: a model Lead cannot raise its mode | E2 | `test_raise_is_refused_from_a_lead_session_and_the_typed_surface` |
| A1 §6: a Lead can lower its mode | E2 | `test_a_lead_lowers_its_mode` |
| A1 §6: a model Lead cannot grant PIC | E6b | `test_the_lead_requests_but_cannot_grant_pic` |
| A1 §6 / CWR: unknown or missing effect classes need confirmation in Walk | E7 | `test_walk_confirms_unknown_or_undeclared_effects` |
| A1 §6 / SAE-07: observed effects never exceed declarations unnoticed | E5a, E5b, E6a (per staged primitive), E7 (runtime) | `test_declared_effects_cover_observed_effects[<primitive>]`, `test_runtime_excess_opens_an_anomaly` |
| A1 §6: budget, envelope and deadline exhaustion stop auto-run | E7 | `test_envelope_exhaustion_stops_the_loop[deadline,max_actions]` |
| A1 §6: repeated no-progress actions stop | E7 | `test_repetition_stops_after_n` |
| A1 §6 / CWR: changing mode never changes legality | E7 | `test_mode_never_changes_a_guard_gate_or_transition` |
| A1 §3.2: hard deadline reduces authority only | E7 | `test_hard_deadline_terminates_and_releases_no_lease` |
| A1 §4 / decision 1: notifier failure visible, no workflow effect; Run needs an executable notifier | E2, E7 | `test_run_needs_an_executable_notifier`, `test_delivery_failure_is_visible_and_moves_no_revision` |
| CWR §11: identical stop sets across modes | E7 | `test_stop_sets_identical_across_modes` |
| CWR §11: zero execution of non-auto-runnable or UNKNOWN actions | E7 | `test_loop_never_executes_judgment_or_unknown` |
| CWR §11: protected-condition overlap stops every mode | E7 | `test_protected_path_overlap_stops_every_mode` |
| CWR §11: a high-severity anomaly stops every mode | E7 | `test_high_anomaly_stops_every_mode` |
| CWR §11: static boundary | E7 | `test_legality_modules_never_import_steering` |
| CWR §11: policy drift mid-step is STALE_POLICY | E3, E7 | `test_policy_drift_between_steps_is_stale_policy` |
| CWR §11: every auto-run step in stage and history records | E7 | `test_auto_run_steps_are_attributed` |
| CWR §9: a confirmation binds the projected action | E7 | `test_confirm_is_stale_when_the_action_moved` |
| TLS-14 / §3.4 rules 1 to 8 | E3 | `test_stage_intent_rules[cas,intent_first,first_refusal,stale_retry,no_replay,drift,launch_failed,takeover]` |
| BRP-03 / M5: judgment-bearing stages never retry, including a non-judgment step inside one | E3 | `test_judgment_bearing_stages_never_retry` |
| TIS-32: mixed-mode walks with a primitive between crash and continuation | E3 | `test_continue_after_an_intervening_primitive` |
| TIS-34: policy drift seeded between each substep | E3 | `test_drift_seeded_between_every_substep` |
| TLS-26 / F18 §14: takeover mid-session; stale-owner intent | E3 | `test_takeover_mid_stage_needs_explicit_continue` |
| TIS-35: bounded hot state and cold latency for intents and anomalies | E3, E5b | `test_terminal_intents_leave_hot_state`, `test_cold_intent_read_latency` |
| §10: query/execute equivalence per migrated guard | E4 | `test_guard_query_matches_execute[<guard>]` |
| §10: stage/primitive equivalence | E5a, E5b, E6a | `test_stage_matches_primitives[<stage>]` (fake harness) |
| §10: PrimitiveSpec coverage for every staged primitive | E5a to E6a | `test_every_staged_primitive_is_declared` |
| §10: no false advance in the seeded corpus | E5a, growing to E7 | `tests/corpus/false_advance/` (the seeded states: stale evidence, unmigrated guard, pending disposition, high anomaly, moved head, second move, unusable envelope per clause, stale confirmation); `test_no_false_advance[<case>]` |
| §17 predicate, per clause; not exercised goes to AWAITING_DISPOSITION | E6b | `test_pic_clause[<1..8>]` |
| Envelope usability, per condition | E6b | `test_envelope_unusable[<expiry,exhausted,generation,manifest,stamp,ref,legality,revoked>]` |
| PIC survives exactly one rebuild | E6b | `test_pic_survives_one_rebuild_only` |
| VALIDATE_ONLY releases the lease; later publish revalidates on a moved head | E6a | `test_validate_only_releases_and_revalidates` |
| HSD-22/23: a held result never publishes | E6b | `test_held_result_never_publishes_under_pic` |
| BRP §9: policy 0 keeps Lead-mediated behaviour; changed dispatch or base binding ineligible; second failure stops | E8 | `test_relaunch_off_by_default`, `test_changed_binding_is_ineligible`, `test_second_failure_raises_attention_only` |
| A2 §8: live old process prevents relaunch; stale heartbeat alone insufficient; revoke before mint; project tool event ineligible; workspace mutation ineligible; unknown reason ineligible; credential/config/quota/security never relaunch; breaker; new run id and credential | E8 | `test_a2[<each>]` |
| TLS-26: live OpenCode MCP spawn and list | E9 | live `test_opencode_spawns_aew_lead_and_lists_normal_tools` |
| TLS-16: normal surface budget per slice | E2 onward | `test_the_normal_list_..._fits_the_budget` (exact list per slice) |
| N1: an adopted raise changes nothing until an endpoint record exists | E2 | `test_adopted_raise_waits_for_the_endpoint` |
| N2: the custodian validates, routes and releases; never the Lead credential; nothing once the custodian ends | E6a | `test_custodian_runs_checks_validation_after_prepare`, `test_custodian_routes_but_never_accepts_verifier_reports`, `test_custody_worker_holds_no_lead_credential`, `test_custody_worker_commits_nothing_after_its_custodian_ends` |
| N2c: relaunch happens only from the stage runner at `launch_failed`, never from a supervisor or the recovery `cli` | E8 | `test_relaunch_only_at_the_stage_launch_failed_stop` |
| N3: notification with no broker | E7 | `test_notifies_with_no_broker_running` |
| N5: the endpoint is not dumpable; the same-uid residuals are recorded | E2 | `test_endpoint_is_not_ptrace_readable`, `test_same_uid_residuals_are_recorded` |
| n4: publication count is crash-safe | E6b | `test_publication_count_survives_a_crash_between_cas_and_count` |
| n8: unmapped launch failures are `UNKNOWN` and never relaunch | E8 | `test_unmapped_launch_failure_is_unknown` |

## 7. Gates (test-enforced)

- No normal mutating stage without a durable StageIntent (E3 before E5).
- No mode-raising, confirmation or grant surface reachable except through the operator endpoint, including raises by
  policy adoption (E2 before E6b and E7).
- No `guarantee` other than `dev` for operator records until F18.6. PFS-04 release gate 1 and SAE-01 to SAE-03 are
  therefore met **only as `guarantee: dev`** in M4-E, and their ledger and register rows stay open.
- No authority-granting action on the supervisor event path. The relaunch is in the stage runner.
- No automatic relaunch without termination and no-side-effect proof (E8).
- Operational policy changes never produce `STALE_POLICY` (E1).
- §10's hard gates and CWR §11's conformance list as mapped in §6. Any false advance is a release blocker.

## 8. Sequencing and size

- E1 starts after #118 merges. F22.1 PR B and the Arm B prototype touch none of these files.
- **Critical path to a measurable stage surface:** E1, E2, E3, E4, E5a, E5b.
- **To an unattended M4-H arm:** E6a, E6b, E7. E6 is testable without E7: the custody worker lands in E6a.
- E8 can trail. E9 closes the list.
- **Sizes:** E1 medium; E2 medium; E3 large; E4 large (incremental); E5a and E5b medium; E6a and E6b medium to large;
  E7 large; E8 medium to large; E9 small. That is 11 PRs.
- Each slice is checked against CI's cost record (E43): stage tests must not push a lane past §8's budgets.

## 9. Lead-developer choices, for information

These are implementation choices inside decisions already made. They are listed so the operator can object, not
because they need an answer. None loosens an authority boundary.

**Settled by the designer (2026-10-07), recorded here:**
- PIC is checks mode only. The engine never accepts a verifier report on the Lead's behalf (§2.3).
- `--dev` and `guarantee: dev` on a same-uid host are F18's adopted contract, not a new choice (§2.1).
- The stand-in negative test proves the peer-credential mechanism only. The real-Lead exclusion stays open until
  F18.6 (§2.1).
- Mechanical integration work runs as the lease's custodian, never on the Lead's credential (§2.3).

**My choices:**
- `requires_disposition` defaults to empty, so existing behaviour is unchanged; M4-H's sealed manifest pins its value
  (§2.4).
- The normal surface stays within 12,000 bytes and 16 tools (§2.6).
- An envelope's expiry is at most 72 h, with one active envelope per project (§2.2).
- The loop and notifier defaults are in E7.
- "The Ticket belongs to the sealed run" rests on the generation stamp and the envelope window, with the task hash
  checked against the task file at grant (§2.2).

## 10. Operator actions the build needs

- Merge order: #118 before E1.
- `AEW_RL8`: create `aew-lead-probe` for E2's live stand-in test. sudo is the operator's.
- Before an M4-H run, from the operator's terminal:
  - `aew operator serve --dev` (it also delivers notifications);
  - `aew lead mode raise run`, which is how the sealed manifest's mode takes effect (§2.1);
  - `aew operator grant-publication --manifest <sealed manifest> --task <task file> --for <duration> --max <n>`.

## 11. Review findings and where this plan answers them

**Designer (2026-10-07), applied after the v3c review:** §2.3's custody worker replaces the broker-hosted driver, verifier-mode PIC is out, and §9 is information only.

**v1 review (answered in v2, kept in v3):**

| Finding | Answer |
|---|---|
| B1 grant model | §2.2 (operator Q1), E6b |
| B2 VALIDATE_ONLY, PIC exercise, modes, acceptance tool, rebuild | §2.3, E6a, E6b |
| M1 Lead-side rights; lower vs raise | E2 (separate commands, `steering` tool), §2.6 |
| M2 structural absence | §2.1 (operator Q2), E2; away confirmation deferred (Q3, §0) |
| M3 anomalies, `requires_disposition` | §2.4, E5b, E7; §0 for what is out |
| M4 E4 scope and PrimitiveSpec coverage | E4's table, E5's spec rule (`dispatch.launch` kept and specified, N4) |
| M5 R5-1's five conditions | E3 |
| M6 digest composition, classification, #118 | §2.5, E1 |
| M7 byte budget | §2.6 (measured; schemas included) |
| M8 E7 specifics | E7, §2.8 |
| M9 E8 requirements and proofs | E8 |
| M10 E2 independently testable | E2 (no `confirm` or grant in E2) |
| M11 journal storage and fields | §2.7, E3 |
| M12 per-slice tests | §6 |
| m1 to m5 | §1, E3, E4, §5, §0, §2.3 |

**v2 review (answered in v3):**

| Finding | Answer |
|---|---|
| N1 adoption raises the mode without the endpoint | §2.1 (effective mode from A1 §1.3 records only), E2, §6, §10 |
| N2 engine actions with no named actor | §2.3 (the custodian's custody worker: process, principal, trigger, per-mode expansion), E4, E6a; E8 in the stage runner, §5 |
| N3 notifier dies with the broker | §2.8 (delivery from the endpoint, event spool, `broker_gone`), E7 |
| N4 `dispatch.launch` | §1, E4, E5a (kept, specified, not renamed) |
| N5 stand-in negative test; dev-only gates | §0, §2.1 (dev-only statement, `PR_SET_DUMPABLE`, residuals), §7 |
| N6 §9 ungated | §9 (each item names its gated slice and the consequence of a no), §7 |
| n1 classification | §2.5 (`history_audit` fields, "four fields") |
| n2 schemas, measurement | §1, §2.6 |
| n3 task hash | §2.2, §9 |
| n4 publication count | §2.2, §6 |
| n5 loop commits stale `expect_rev` | §2.7, E7, §6 |
| n6 anomalies gate existing flows | §2.4 (no primitive guard) |
| n7 metrics log | §0, E5a |
| n8 launch reason codes | E8 |

**v3 review (answered in v3, second revision):**

| Finding | Answer |
|---|---|
| P1 same-uid barriers overstated; acceptance had no durable home | §2.1 (one endpoint, never from a Lead session; the full residual list), §2.7 and E7 (the endpoint commits a single-use confirmation record; the loop acts only on it), tests in E7 |
| P2 a raise outliving its generation | §2.1 (a raise ends with its generation), E7's test |
| m1 budget figures | §2.6 |
| m2 §2.1 list formatting, client commands | §2.1 |
| m3 envelope-ending bullets | §2.2 |
| R1 (v3b review) confirmations not bound to the generation | E7 (generation binding, retired at generation end, test) |

**v3d review (custody worker):**

| Finding | Answer |
|---|---|
| S1 the custodian cannot commit; admission unpinned | §2.3: `custody_txn` with an allow-list and pinned admission; the proof of identity (process identity or custody credential) decided 2026-10-07: the scoped custody credential |
| S2 a dead or unstarted worker goes unnoticed | §2.3: worker registration, `sync` and endpoint checks, `custodian_lost`, tests |
| S3 `aew integrate custody` reachable from the Lead shell | §2.3: `OPERATOR_ONLY`, test |

**v3e review:**

| Finding | Answer |
|---|---|
| T1 a broker-spawned worker refuses itself | §2.3: detached, sanitized-environment spawn; refusal keyed on the environment; S1 is the real guard; test |
| T2 option (b) changes an operator decision; stale table wording | §2.3: the escalation is the operator's and the designer's; table updated |
| T3 the worker on a `VALIDATED` re-lease | §2.3, test |
| T4 `custody_register_s` unclassified | §2.5, §2.3 |
| U1 (v3f review) option (a)'s first registration | Superseded: option (a) was not adopted; the custody credential proves `register` (S1 decision) |

**Operator and designer decision (2026-10-07):** the scoped custody credential (§2.3), which closes S1.

**v3h review:**

| Finding | Answer |
|---|---|
| V1 when the credential is generated vs minted | §2.3: generated inside the granting transaction, with the hash committed there and the plaintext held until the spawn |
| V2 the pipe leaking to the worker's children | §2.3: non-inheritable pipe, read and closed before any spawn; test extended |
| V3 the stale U1 row | §11: marked superseded |
| W1 (v3i review) wording implied the worker launches the verifier | §2.3: reworded; the verifier is the Lead stage's |
