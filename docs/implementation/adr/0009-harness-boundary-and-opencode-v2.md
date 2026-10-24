# ADR-0009 — Harness boundary, runs, credential custody, and the OpenCode V2 adapter

- **Status:** Accepted (M3, 2026-09-29). Operator-approved plan: `m3-ambiguity-report.md` (§0, §2.1–§2.3, §2.5–§2.11).
  - Proposed in M3 step 0. The harness core was implemented in step 2, the Lead broker in step 3 and the OpenCode adapter in step 4. Adversarial regressions were added in step 5, acceptance scenarios AT-14..AT-17 in step 6, live model conformance in step 8, and the dogfood ran in step 9.
  - Subject to the M3 independent review (`m3-reviewer-brief.md`), as ADR-0007 and ADR-0008 were for M2.
- **Spec basis:**
  - WC §2 and §17: harness independence.
  - WC §5 and §15.4: bounded invocations from launch contracts; the Lead is reconstructible.
  - WC §8.2: success is never inferred.
  - WC §16.12: adapters are never authorities.
  - WC invariant 21: no transport becomes an authority.
  - KC §3, §5.3 and invariant 22: runtime logs are local; secrets and transcripts are never knowledge.
  - ADR-0003, ADR-0005, ADR-0006.
- **Evidence:**
  - `m3-opencode-v2-rebaseline.md` and `eval/m3/spike/`.
  - The fake-harness conformance tests `tests/integration/test_harness_runs.py` and `tests/regression/test_m3_harness_adversarial.py`, run on Windows and on Linux.
  - The harness conformance suite against the real OpenCode adapter: in CI against a fake V2 server (`tests/integration/test_harness_conformance.py`, `test_opencode_adapter.py`), and in the opt-in live lane against OpenCode 2.0.18 (`tests/live/test_opencode_live.py`).
  - Acceptance scenarios AT-14..AT-17 (`acceptance.md`): `tests/acceptance/test_at14_at17_harness.py` (fake harness; OpenCode adapter with fake V2 server and `aew opencode`), and their live twins on OpenCode 2.0.18 (`tests/live/test_opencode_acceptance_live.py`).
  - Live model conformance (step 8, `harness-conformance.md` §6): real free models in every role through the production adapter, including rejection and rework (`tests/live/test_opencode_model_live.py`, results in `eval/m3/live/`).
  - The paid dogfood (step 9, `m3-dogfood-report.md`): 47 runs with a headless model Lead and every role a real run, on GPT-5.6 Luna and GPT-6 Sol. Every run's credential scan was clean, no run wrote to the AEW checkout, and resume after losing the Lead's harness succeeded 3 of 3.
- **Nature:** an implementation of frozen semantics. It adds no new authority, no new state machine and no new knowledge store.

## Decision

### Boundary
- **AEW owns:**
  - invocation identity;
  - its pins: card, **execution profile** (ADR-0010), pack sha, workspace/observation, expected kind;
  - credentials and **their custody**;
  - run identities;
  - evidence, gates and state.
- **The harness owns** the model loop, tools, sessions, summaries and caches.
- **Rules:**
  - The adapter never commits control state.
  - Agent → AEW traffic uses only AEW engine operations, through the custody bridge.
  - Harness → AEW traffic is telemetry in local run records (KC §5.3), which no gate reads.

### Runs (`src/aew/engine/harness_ops.py`)
- A **run** `R-<INV>-<n>` is one harness execution of an invocation. Control state records it as:

  ```text
  inv.runs[] = {run, harness, token_id, launched_at, kind: dispatch|launch|relaunch, generation}
  ```

- **`--launch` on a dispatch** (`work assign|dispatch|redispatch`, `invoke create`) records run 1 in the dispatch commit. Run 1 adopts the credential that the dispatch issued, which never leaves the process: it is removed from the command's output and handed to the supervisor.
- **Every `aew harness launch`** (Lead, CAS) **rotates** the credential in the same commit that records the new run. The old credential is revoked with reason `rotated: R-…`, and a new one is issued with the same scope (`rotate_invocation_token`). At most one run can act. A credential that was ever printed (a dispatch without `--launch`) dies at the first launch.
- **A rotated credential** presented to the engine is `STALE_AUTHORITY`, naming the rotation. It is never "unknown credential".
- **Launch preconditions**, checked before anything is committed:
  - the invocation is active;
  - it has an execution profile;
  - its harness adapter loads;
  - its workspace, candidate or observation is still live (on relaunch);
  - its pack regenerates to the pinned sha;
  - its latest run is not possibly live.
- **"Possibly live" means:**
  - a supervisor heartbeat within `STALE_AFTER_S` (10 s); or
  - an `unconfirmed` run launched less than 30 s ago, which could still be between its launch commit and its spawn.

  A possibly-live run needs `--replace` (`RUN_LIVE`). Its credential dies in the relaunch commit either way, and a best-effort stop request for its supervisor is recorded in the same commit.
- **A session id is correlation only**, recorded in the local run record.
- **Harness session loss is not INTERRUPTED.** The AEW execution identity (the invocation and its credential) survives and is re-bound by rotation. INTERRUPTED stays tied to authority changes (ADR-0003).

### Run status (local telemetry, `aew/harness-run/v1`)

| status | meaning |
|---|---|
| `unconfirmed` | derived: recorded in control state, but no supervisor ever wrote a record. No process holds its credential. |
| `starting`, `running` | a supervisor holds custody and beats a heartbeat |
| `launch_failed` | custody refused, no credential handoff, or the harness failed to start (health, capability, model) |
| `ended_with_evidence` | the harness exited after this run recorded evidence of an **expected kind** |
| `ended_without_evidence` | exit 0 without an expected output. Check results alone are not the run's output. |
| `crashed` | non-zero exit without an expected output, or a supervisor error |
| `terminated` | stopped by AEW: authority ended (cancelled, interrupted, superseded, revoked, generation changed), a Lead stop, or the profile deadline |
| `lost` | derived: a supervisor took custody and its heartbeat is stale (killed, frozen, machine lost) |

**No status moves AEW state.** The Lead ingests evidence as before (WC §8.2).

### Credential custody (operator requirement; `src/aew/harness/bridge.py`, `supervisor.py`)
**Invariant: no raw AEW credential ever enters a model-controlled process.**

**Handoff.**
- The launching process spawns the **run supervisor** detached (`CREATE_NO_WINDOW` / new session). Its environment is scrubbed of `AEW_*TOKEN`, bridge variables, and any variable whose value contains a credential string.
- The credential is written to the supervisor's **stdin pipe**. It is never passed through argv, an environment variable or a file.
- The supervisor acknowledges custody only after checking against control state that the credential belongs to exactly this run (its invocation, its latest run, its current credential, the current generation).

**The bridge.** The supervisor serves a **run-scoped bridge**:
- a local named pipe (Windows) or an AF_UNIX socket in a private 0700 directory (POSIX);
- guarded by a 256-bit per-run key with the `multiprocessing.connection` HMAC challenge, so the key never crosses the connection.

**Bridge protocol.**
- Requests are **JSON only** (`send_bytes` / `recv_bytes`). The bridge never unpickles, because pickle would let an authenticated client execute code inside the credential holder. A test plants a pickle payload to prove this.
- There are exactly three operations with exact arguments: `whoami{}`, `check.run{check_id}`, `submit{kind, text}`. A request cannot name an invocation, a run or a credential.
- Before each request the bridge re-checks its run's authority against control state; the engine then re-checks the credential under the control lock before writing anything. A refusal for ended authority stops the run.
- Checks run with the **agent's environment**, never the supervisor's, because a check executes code the agent wrote.
- Responses are redacted of credential strings. The supervisor drains in-flight requests before exiting.

**Client routing.** The `aew` CLI routes `check run`, `submit` and `whoami` to the bridge when no credential is supplied and `AEW_AGENT_ENDPOINT` is set. `submit --file` is read by the client in the agent's working directory.

**The agent's environment is an allowlist** (`agentenv.py`):
- OS basics;
- `PATH`, with the running `aew` first;
- `AEW_AGENT_ENDPOINT`, `AEW_AGENT_KEY`, `AEW_INVOCATION`, `AEW_RUN`, `AEW_WORK_UNIT`;
- `AEW_SCRATCH`: a private scratch directory under the run, the named place for files that belong neither in the workspace nor in evidence (M3-D6).

It carries no AEW credential, no provider secret, no harness password, and nothing else from the Lead's shell.

**Why the bridge key is acceptable.** It is a run-scoped capability that every agent process may use (they *are* the agent). It is not the AEW credential, grants only what the engine already authorizes, and is useless once the run ends, rotates or is revoked.

**The Lead is symmetric** (`src/aew/harness/lead_broker.py`, M3 step 3).
- `aew lead session [--acquire] -- <harness command>` holds the Lead credential in memory and serves a **Lead bridge**. `aew opencode` is this command with an OpenCode TUI (below). The credential comes from `AEW_LEAD_TOKEN` in the operator's own shell (removed from the session's environment), or from an in-process `--acquire`.
- The Lead bridge is the same `BridgeServer` (JSON, key challenge, typed exact arguments, redaction, drain) with two operations:
  - `lead.cli {argv, cwd, stdin}`. The CLI routes every Lead-authenticated command there when the session supplies no credential, and the broker runs the same command handler with the held credential.
  - `lead.whoami {}` returns the held authority's generation and session label, never the credential. `aew resume` inside a session uses it, so a session that holds Lead authority is told so, instead of being told to take over (M3-D10).
- **The broker refuses:**
  - credential-emitting commands (`lead acquire|takeover|release`, `lead handoff offer|accept`), refused locally in the session too;
  - dispatch without `--launch`;
  - an explicit `--token`;
  - read-only commands;
  - other projects.
- When the held credential stops being the current Lead's, the broker closes its bridge. (A pending handoff does not; see the 2026-10-04 amendment.)
- Parity with the invocation bridge is tested property by property (`harness-conformance.md` §3).
- With `--acquire`, the seat is released at exit when nothing is in flight; otherwise it stays held and the output says that continuing needs a terminal takeover. The credential is never printed. (Since 2026-10-04 the release also waits until no process the session started is running.)

**Why custody at all.** The spike showed that anything a harness shell prints is persisted twice, in the harness DB and in shell-output files. A harness permission layer is not secret isolation: an `edit` deny was bypassed through the shell.

**Post-run scan.** When a run ends, the supervisor scans the run directory for any credential string and records `credential_scan`.

**Service credentials (ADR-0005, amendment 2026-10-05; built with M6b).** A harness run never receives a service credential; the Lead broker refuses `service issue` as it refuses the Lead's credential-emitting commands, and the agent environment allowlist never carries `AEW_SERVICE_TOKEN`.

**Residual risk (same-UID; documented, not closed).** A same-user process can read another process's memory on Windows (no integrity-level separation), so a deliberately adversarial agent could extract the credential from the supervisor. Custody closes inheritance, printing, transcripts and files, which are the accidental and persistent exposure paths. On Linux the supervisor is **non-dumpable** (`PR_SET_DUMPABLE=0`), so its `/proc/<pid>/{mem,environ}` are unreadable by the agent; a test checks this. This is the ADR-0005 same-UID threat model; it is unchanged.

### Process ownership (`src/aew/harness/procs.py`)
The supervisor owns the harness process tree independently of any harness lease.
- **Windows:** processes are created **suspended**, assigned to a job object with `KILL_ON_JOB_CLOSE`, then resumed, so no descendant can start outside the job, and the job disallows breakaway. `terminate` terminates the job; supervisor death closes the only job handle, and the OS kills the tree.
- **POSIX:** the tree is one process group. A **sentinel** outside the group kills the group when its pipe from the supervisor closes, including on `SIGKILL`. There is no `preexec_fn`, because the supervisor is multi-threaded. A descendant that calls `setsid` escapes (residual; authority is unaffected).
- **Liveness is a heartbeat file's mtime.** A pid is never trusted alone, because pids are reused. Tooling that must act on a pid checks the process start time against the run's custody time (`procs.same_process`).
- OpenCode's `--stdio` lease is used but not relied on.

### Containment label (`AEW-INV-ISO-001`; companion review B2)
*Superseded on Linux by the M4-B amendment below: Linux runs are contained, and every run records a structured label. Windows still has exactly what this section describes.*

What M3 provides is **workdir separation**: each run has its own workspace or observation, private harness state and a scratch directory. It provides **no OS-level filesystem containment**: an agent's shell runs as the operator and can read and write whatever the operator's account can.
- Every run record carries `containment: workdir_separation_only`, and `aew harness status` shows it.
- `aew doctor` reports `containment` as WARN with that explanation.
- Nothing in AEW claims more. Real containment is designed (`docs/design/proposals/execution-workspace-and-isolation-design-v0.1.md`) and gates real-repository dogfood and internal alpha (`future-work.md` §1, F2).

### Pause points (tests)
`AEW_PAUSE=<point>=<file>` holds a process at a named point while the file exists (`faults.pause`, next to the `AEW_FAULT` crash points):
- `harness.bridge.before_engine`: a request past the bridge check, before the engine;
- `harness.watchdog.tick`: a supervisor slow to notice anything.

These make races deterministic: rotation during an in-flight submit, a check spanning a rotation, and a woken supervisor. They are no-ops unless the variable is set in the Lead's environment, which the agent's allowlisted environment never carries.

### OpenCode adapter (V2 2.0.18; `src/aew/harness/opencode/`, M3 step 4)
- **Interface:** a private `opencode-cli serve --stdio --port 0 --hostname 127.0.0.1` per run, started inside the run's process tree and driven over HTTP from the Python standard library (`client.py`). This is the published contract that `@opencode/client` wraps.
- **Rejected alternatives:**
  - `@opencode/client` (needs a JS runtime; a "private generation target");
  - `@opencode/sdk` (embedded core in a JS process, skewed against the installed binary);
  - per-turn `run --format json` (no mid-run delivery, which couples against coordination; signal-only interrupt). `run` stays as the raw-OpenCode dogfood baseline.
- **Binary:** `AEW_OPENCODE_BIN`, else OpenCode Desktop's version-specific `cli\2.0.18\opencode-cli.exe` on Windows, else `opencode-cli` on PATH. None found is `HARNESS_INCOMPATIBLE`.
- **Health, at every launch, against that run's own server** (`capabilities.py`, `adapter.py`). Any gap fails with `HARNESS_INCOMPATIBLE`, naming it:
  - the version (a non-V2 server is refused; the tested version is recorded);
  - a **capability probe** of the served `/openapi.json`: every operation, request field, query parameter, response field, enum value and configuration key the adapter uses;
  - the pinned `provider/model` and effort variant in `/api/model`, polled, because the catalog loads asynchronously; there is never a fallback;
  - **the projection loaded as written:** `/api/agent` (also asynchronous) must show AEW's agent with the projected system text, pinned model and variant, step limit, and AEW's rules as the last, winning part of its permissions.
- **Isolation per run:**
  - the server environment is an allowlist: operating-system basics, `PATH`, `SHELL`, and only the provider variables the execution policy names;
  - private XDG dirs and `TEMP` under `<run>/harness/`;
  - `OPENCODE_CONFIG_CONTENT` (the projection);
  - `OPENCODE_DISABLE_PROJECT_CONFIG=1` and `OPENCODE_DISABLE_AUTOUPDATE=1`;
  - the session's shell environment **replaced** by `PUT /api/session/{id}/environment` with the agent allowlist: no AEW credential, no provider key, no server password;
  - `location.directory` = the invocation's recorded workspace as a long path.
- **Projection** (`projection.py`, golden-tested):
  - One primary agent, `aew`. Its system text states the AEW rules. The pinned model is on the session, the agent and OpenCode's auxiliary agents (title, summary, compaction).
  - Configuration: snapshots, sharing, updates, LSP and formatters off; the compatibility plugin (`~/.claude`, `~/.agents` skills) disabled.
  - **Permissions:** every rule is allow or deny, never `ask`, because an `ask` blocks forever.
    - Anything not named is denied.
    - `subagent`, `question` and `external_directory` are denied, except the run's own OpenCode output directories. V2 saves long tool output there and points the model at it, and V2's own defaults allow the same directories.
    - `.env` and `.env.*` are not readable; `.env.example` is. V2's own default asks, which would block.
    - `edit` for implementers only.
    - Web access only for cards requesting `documentation_lookup`.
    - `skill` only for skills the harness provides for the card. M3 provides none, so card skills are recorded as `unavailable` (WC §16.10) and named in the system text.
  - The complete rule set is sent on session create, where V2 applies it last.
- **Watching:**
  - A turn is over only when the REST API says so, on two consecutive polls: the session is not active, the last prompt AEW sent has been delivered, the newest message is an `idle` after it, and none of AEW's prompts is still queued.
  - The event stream only wakes the poll and feeds telemetry. A lost stream reconnects and changes nothing.
  - A permission request or form is never expected. It is rejected or cancelled and recorded (`permission_rejected`, `forms_cancelled`).
  - A session created by anyone else is recorded as `foreign_sessions`.
  - The server dying is a crash, with the server's exit code.
- **Lead requests:**
  - `aew harness send` is a queued prompt, delivered inside the current turn, never lost at its boundary. It refuses text containing a credential. *(Amended 2026-10-10, below: it takes `--when`, and posts `steer` by default.)*
  - `aew harness interrupt` holds the session after the turn is interrupted, until a `send`, a stop or the deadline.
- **Collected, all non-authoritative:**
  - the effective models from assistant messages (compared with the pin: `model_check`);
  - usage;
  - the tools the agent called;
  - first-step input tokens (the contract plus OpenCode's own overhead);
  - event-stream drops;
  - the skills requested, exposed and unavailable.
- **`aew harness config opencode <INV>|--lead`** prints the exact projection and the environment names, without values.

### The Lead's OpenCode TUI (`aew opencode`, `src/aew/harness/opencode/lead.py`)
- `aew opencode [--acquire] [--provider-env NAME] [--print-config]` is `aew lead session` running `opencode-cli --standalone <repo root>` with the Lead projection (`aew-lead` agent; `/aew-resume`, `/aew-status`, `/aew-ticket`, `/aew-next`, `/aew-handoff`).
- **Why `--standalone`.**
  - A V2 TUI running its own server sends its own environment, minus the server password, as every session's shell environment, and its server inherits the same environment (verified in the 2.0.18 binary).
  - With `--server`, the TUI sends nothing, so the shell would get the server's environment. `aew opencode` refuses `--server`.
- **The Lead model's environment is therefore exactly the TUI's, which is an allowlist:**
  - operating-system basics, `XDG_*`, `SHELL`, `OPENCODE_CONFIG`;
  - `PATH` with `aew` first;
  - the Lead broker's coordinates;
  - the projection.
- It holds no AEW credential and, by default, **no provider key**. The Lead's model uses the credentials OpenCode stores for the operator. `--provider-env NAME` passes a key explicitly and says that the Lead's shell can read it.
- Lead permissions: the operator is present, so unlisted actions `ask`; `aew` and read-only `git` commands are allowed; `edit` and `subagent` are denied.
- Command templates run only fixed read-only commands as inline shell, because V2 runs those outside the permission flow.
- AEW writes nothing into the operator's OpenCode state.

### Harness-neutral contract (`src/aew/harness/base.py`)
- **`HarnessAdapter`, one instance per run inside its supervisor:**
  - `launch(contract, agent_env)`: starts the harness and checks health against the harness actually started;
  - `inspect`, `terminate`, `send`, `interrupt`, `collect`.
- **The contract (`LaunchContract`):** preamble + pinned pack + (on relaunch) a continuation section built only from durable AEW state (earlier runs, this invocation's evidence, workspace changes).
- **Registry:** adapters are registered by name. `AEW_HARNESS_ADAPTERS` (from the Lead's environment) adds site or test adapters. A Codex or Claude Code adapter implements the same protocol, and no engine change is needed.

## Consequences

- OpenCode state is disposable. Destroying a run's directory loses a conversation, not the engineering project.
- A surviving, revived or woken old run holds dead authority: its credential was rotated or revoked, its bridge refuses and closes, and its tree is killed.
- The explicit-credential CLI path (`AEW_INVOCATION_TOKEN`, `--token`) remains for scripted roles and tests.
- **Found by M3 (M3-D1).**
  - **Defect:** M2's executor dispatch pinned its pack before the attempt's output contract was recorded, so no executor pack matched its regeneration.
  - **Fix:** the pack is now built after the contract.
  - **Regression:** every dispatch kind must pin the pack its regeneration produces.
- **M3-B6 confirmed and closed (step 5).**
  - **Probe:** a mutating Ticket's reviewer shares the implementer's live workspace. Its edit and its passing review were both recorded. The review was refused at ingest only as "stale", with no author. A second reviewer, dispatched next, reviewed and passed the edited code. The Ticket then stopped at REVIEW_PASSED, because the implementer's gates had gone stale. The fingerprint-bound gates kept the edit out of integration, but nothing named it.
  - **Fix** (`evidence_ops.py`), with regressions written first (`test_a_reviewer_cannot_mutate_source`, `test_a_verifier_cannot_mutate_source`):
    - a reviewer's or verifier's `submit` and `check run` refuse with `WORKSPACE_MUTATED` when the workspace (or integration candidate) differs from the snapshot the invocation was dispatched for, naming the changed paths;
    - dispatching a reviewer or verifier refuses with `WORKSPACE_MUTATED` while the implementer's pre-review gates are stale, again naming the paths. The Lead returns the Ticket to RUNNING, so that an implementer reports or restores the change.
  - Retiring the implementer at RUNNING→REVIEW_PENDING already ends its authority, so a still-running implementer run is stopped and cannot be relaunched (`test_the_retired_implementers_run_stops_when_review_begins`).
- **Run records are telemetry that a model-controlled process can write** (same user). `aew harness status`, `harness wait` and `aew resume` therefore read a run's evidence from the evidence store (sealed, engine-stamped `producer.run`), never from its record. A run exists only in control state, and no gate reads a record. A forged status can mislead the display for a moment; it cannot move state (`test_forged_run_records_and_harness_success_move_nothing`).
- **Sessions other than the run's own** (a subagent's, however started) are recorded as `foreign_sessions`, from the event stream and from a session listing at the end of each turn, and shown by `aew harness status`.
- **Found by live models (steps 8 and 9)**, each fixed with a regression written first (in `tests/regression/test_m3_live_findings.py` and `test_m3_dogfood_findings.py`; M3-D3 in `tests/integration/test_opencode_adapter.py`):
  - M3-D3: the run's event log did not name the tools called;
  - M3-D4: a relaunch's continuation listed stale evidence as passing;
  - M3-D5: a malformed but parseable review or verification section crashed `submit` through the bridge (`BRIDGE_ERROR`); it is now a validation refusal;
  - M3-D6: no named place for files outside the workspace, after a verifier wrote into the operator's own checkout (`AEW_SCRATCH`);
  - M3-D7: resolved findings were checked only when the Lead ingested the review, after the reviewer's run had ended; `submit` now checks them;
  - M3-D8: after an implementer run, the next action named an ingest instead of the transition to review;
  - M3-D10: `resume` inside a Lead session said the session held no authority (`lead.whoami`, above);
  - M3-D11 (found by CI on PR #5): a Lead session ending while the broker's watchdog was mid-check could be reported "superseded", because `close()` cleared the credential under the check. The check now takes the credential before reading state, and `close()` waits for it. Regression in `tests/regression/test_m3_found_defects.py`.
- **Authored text travels as data** (companion review B1). A Lead writes goals, reasons and reports through `--fields FILE|-` or `--file`, with quoted heredocs, never interpolated into a shell command line. The Lead projection and the role preamble say so. Before this, a shell expanded `$1` inside a goal (`m3-dogfood-report.md` §7). The `--fields` mapping is parsed as YAML or JSON data, not taken byte for byte; the YAML forms that would silently change authored text (a comment after an unquoted value, an unquoted value continued on another line, a repeated key, anchors, aliases, tags) are refused with a hint to quote the value (independent audit I5).
- **Known V2 risks:**
  - no stability policy;
  - `--stdio` is undocumented;
  - `/api/skill` is empty even when skills are exposed;
  - the job object can be escaped through out-of-tree spawners (authority is unaffected).

  These are recorded in the reviewer brief's attack list.

## Amendment 2026-10-01 — Lead run requests are recorded in control state (independent review R1)

The independent M3 review found that a run's supervisor acted on any request file in `<run>/requests/`. Run directories are model-writable (same user), so one agent could stop another run, or deliver a message to an independent reviewer, without the Lead. No AEW state moved, but it contradicted this ADR's own rule that nothing deciding anything reads run records.

- **A request is recorded before it is delivered.** `aew harness stop`, `send` and `interrupt` (and the stop a relaunch sends to the run it supersedes) append `{file, kind, sha256, at}` to the run's entry in `inv.runs[]`, in a commit made under the Lead credential, then write the file. The file carries the payload, so a message's text never enters control state.
- **The supervisor acts only on a recorded request, once.** For each queued file it re-reads control state and requires the name to be recorded for its run, the digest and kind to match, and the name not to have been handled already. Anything else is discarded and logged to the event log as `request_refused` (never to the run record, so a flood of files cannot grow it).
- **No expected revision.** Like the Lead seat operations, these requests name one run and are checked against the state they commit on; work and invocation state do not change.
- **Trust level.** Control state is what the supervisor already trusts to end a run's authority. A same-user process that rewrites `control.yaml` and its checksum is outside the ADR-0005 threat model, as before; this closes the path that needed only an ordinary file write.
- **Teardown tooling** that holds no Lead credential ends a supervisor process directly (`runlog.end_supervisor`), which any same-user process can already do.
- Regressions: `tests/regression/test_m3_independent_review.py`.

## Amendment 2026-10-01 — the capability probe checks types (independent review R2)

`REQUIRED_FIELDS` now lists every response field the adapter reads, including those read only for run telemetry (assistant `content` and `agent`, the message page's `data` and `cursor.next`, tool `name`, idle `type`), and every configuration and permission-rule field it sends. Each carries the JSON type the adapter relies on. A field passes if the served schema still offers that type through `$ref` and `anyOf`/`oneOf`/`allOf`; a field with no declared type passes. Removing a field, or retyping one (for example `Config.AgentEncoded.model` to string only), now fails health as `HARNESS_INCOMPATIBLE`, naming it.

## Amendment 2026-10-01 — a run keeps its heartbeat while it ends (found by CI on `main`)

After PR #7 merged, CI on `main` (Windows) reported a healthy investigator run `lost`. A supervisor ends a run outside its watch loop. It:
1. closes the bridge;
2. stops the adapter (up to `TERMINATE_S`, 20 s);
3. kills the process tree;
4. collects the result;
5. scans the run's evidence and its directory for credentials;
6. writes the final record.

Nothing beat during that. When it took longer than the 10 s staleness limit, `aew harness wait` returned `lost`, although the evidence was already recorded, and its next action proposed a relaunch. A slow real harness shutdown could do the same.

- **Fix.** The supervisor beats from a background thread while it ends, as it already did while the harness starts. The thread stops once the final record is written. It also stops after at most `TERMINATE_S` + 60 s, so a supervisor stuck while ending still goes stale and is reported `lost`.
- **Regression.** `test_a_run_that_takes_long_to_end_is_not_reported_lost` in `tests/regression/test_m3_harness_adversarial.py`, using a new pause point, `harness.supervisor.finishing`. It returned `lost` before the fix.

## Amendment 2026-10-09 — a run beats before its first record (found by CI on PR #132)

CI on Windows reported `lost` for a run that then ended with evidence, in
`test_supervisor_spawns_then_the_launcher_crashes_after_handing_over_custody`. The supervisor wrote its first record
(`starting`) before its first heartbeat. A non-terminal record with no heartbeat reads as `lost`, and writing a run
record wakes every `aew harness wait`, so a waiter was woken into exactly that gap. On Linux the gap is under a
millisecond; on a loaded Windows runner it spans a directory sync, the wake mark's write and rename, and the new
heartbeat file's creation. In the same gap a relaunch without `--replace` was not refused, and `harness send` refused.

- **Fix.** The supervisor beats (and starts its starting-beat thread) before it writes its first record, so a
  non-terminal record always has a heartbeat.
- **Regression.** `test_a_run_is_never_reported_lost_before_its_first_heartbeat` in
  `tests/regression/test_m3_harness_adversarial.py`, using a new pause point, `harness.supervisor.after_custody_record`.
  It returned `lost` before the fix.

## Amendment 2026-10-09 — a run's start has a deadline (independent review of PR #147)

The independent review of PR #147 noted that the starting heartbeat had no limit, unlike the running and ending phases.
A supervisor wedged between its custody acknowledgement and `running` kept its heartbeat fresh, and it checks authority
only once its watch loop runs. A single-run `aew harness wait` on that run read `starting` until the adapter's own
launch timeouts or the wait's `--timeout` ended it.

- **The deadline caps the whole start,** from its custody record to `running`: the contract, the sandbox and its
  self-test, and the adapter's launch (for OpenCode: the server start, health, the catalog and agent checks, the
  session and the first prompt). It is not a per-step timeout; each step keeps its own.
- **Its default is derived, never shorter than the steps it caps** (`supervisor.starting_limit_s`, review of PR #149,
  F1). It is the sum of three parts, read from the same settings and environment overrides the steps use:
  - the sandbox self-test's bounds (`probe.BOUND_S`, 40 s);
  - the adapter's own launch bounds in series (`HarnessAdapter.launch_bound_s`). For OpenCode at its defaults that is
    520 s: the server's address 60, `/api/info` 30, the schema 60, the catalog and the agent projection each 90
    (`AEW_OPENCODE_CATALOG_S`) plus a 30 s request in flight, then four 30 s requests and the event stream's 10 s. An
    adapter that computes nothing declares 240 s;
  - a margin of 60 s for the contract, the bridge and the layout.

  The result is 620 s for OpenCode at its defaults. Raising `AEW_OPENCODE_CATALOG_S` raises it by twice the increase.
  `AEW_RUN_START_S`, in the operator's launch environment, replaces the derived value. The failure reason and the bridge
  refusal name it.
- **Measured.** A run's start (first record to running, OpenCode 2.0.18, real server and sandbox) measured 2.6–3.0 s
  on Rocky 8 and a median of 4.4–4.5 s (7.0 s worst) on a fully loaded Windows host. The catalog fetch adds under
  0.5 s, does not stall when the network hangs, and is bounded inside the adapter by `CATALOG_WAIT_S`/`CATALOG_SETTLE_S`.
  The start deadline bounds a wedged start; it is not a performance budget.
- **At the deadline the starting heartbeat stops,** so the run reads `lost` within the deadline + `STALE_AFTER_S` of
  custody (630 s for OpenCode at its defaults), and a waiter notices within its 2 s re-check. Each phase now has a
  stated bound:
  - running: a heartbeat that stops (supervisor killed, watch loop wedged) reads `lost` after `STALE_AFTER_S` (10 s);
  - ending: the ending heartbeat stops after `TERMINATE_S` + `ENDING_EXTRA_S` (80 s), so `lost` comes within about
    90 s of the end beginning;
  - starting: as above.
- **A run read as `lost` stays ended.** Past the deadline:
  - the run's bridge refuses every request (`HARNESS_LAUNCH_FAILED`), so nothing the agent does counts;
  - a start that comes back ends the run `launch_failed` ("the start took longer than …"), kills its tree, and never
    records `running`;
  - while it ends it does not beat again, so its observed status goes from `starting` to `lost` to `launch_failed`,
    and never back to `starting`.
  A relaunch is not refused as `RUN_LIVE` once the run reads `lost`, as for any lost run, and it rotates the
  credential.
- **Residual, as for the ending phase.** A supervisor that never comes back stays a process until teardown
  (`runlog.end_supervisor`) or the machine's end. It holds a revoked credential once the run is relaunched, and its
  bridge refuses everything.
- **Regression.** `test_a_start_that_wedges_after_custody_reads_lost_within_its_bound_and_never_runs` in
  `tests/regression/test_m3_harness_adversarial.py`, using a new pause point, `harness.supervisor.launched` (after the
  adapter's launch, before `running`). It holds the start past a 3 s deadline, and also holds the ending
  (`harness.supervisor.finishing`). Each part of the fix was removed in turn, and each removal fails the test:
  - an unbounded heartbeat: the wait times out on `starting`;
  - no deadline check before `running`: the run never ends `launch_failed`;
  - a bridge that still serves: the agent's `whoami` succeeds;
  - an ending that beats again: the run reads `starting` again.

  `test_a_run_that_outlasts_the_start_deadline_once_running_is_unaffected_by_it` (same file) guards the other side:
  a run that is running past the deadline keeps its bridge and ends with evidence. A deadline check that ignored the
  status fails it. `test_a_start_deadline_never_cuts_off_the_adapters_own_launch_bounds`
  (`tests/unit/test_harness_units.py`) checks two things in a fresh process. The derived default is at least the
  adapter's bounds plus the self-test's, and grows with `AEW_OPENCODE_CATALOG_S`. `AEW_RUN_START_S` overrides it.

## Amendment 2026-10-09 — the post-run scan reads what the run left defensively, and says when it is incomplete

The post-run scan (above) runs as the operator over a directory the run's own user could write: its `harness/` even
under containment. It now walks that directory iteratively, never entering a link or, on Windows, another reparse point;
reads only regular files, never through a link and never blocking on a FIFO or device; and reads each in overlapping
chunks with its holes skipped, within one budget of bytes and entries per scan (`runlog.credential_scan`). Anything it
could not read is counted in `credential_scan.unscanned`, and then `clean` is false: **clean means scanned and clean.**
A scan that fails outright is recorded as not clean with its error, and the run's final record is still saved. On
Windows the walk opens extended-length paths, so every entry its listing shows is reachable. The scan reads a file's
main data only (not NTFS alternate data streams or extended attributes): it catches a credential written into a file by
mistake, not one a model hides on purpose. Register E33's streaming half closes with this (PR #139).

## Amendment 2026-10-03 — OS filesystem containment and process ownership on Linux (M4-B; F2, E13)

M4-B closes register items F2 (real filesystem containment, the gate before any real-repository dogfood) and E13 (POSIX process ownership). It builds the design approved in `m4-ambiguity-report.md` §2.4, with the designer's correction: the real git metadata is never writable by the agent. The probes behind it are in `docs/research/containment-and-process-ownership-rocky8-research-2026-10-01.md`. It was verified on Rocky Linux 8.10 (kernel 4.18, SELinux enforcing, bubblewrap 0.4.0).

### What F2 claims, exactly
- **Filesystem integrity.** A contained process can write only its role's writable roots. Every other write fails at the OS (`EROFS`), and the host is unchanged.
- **Not confidentiality.** The host stays readable, apart from the masked secrets and other runs' directories (below). `os_readonly_roots` must never be read or reported as "the sandbox hides the host".
- **Not network isolation.** The network namespace is shared: the harness server listens on `127.0.0.1`, and the provider is remote. Labels say so: `network: shared` on Linux (the run shares the host network namespace) and `not_provided` on Windows, where AEW cannot characterize it (network containment design v0.2 §3.1; network containment itself is F28).

### The sandbox (`src/aew/harness/containment/`)
- **One `Layout` per run, from its role** (`layout.py`). The role-to-layout table is exhaustive: an archetype without an entry (the Lead, or a new archetype nobody classified) has no layout, and its launch is refused. Write access exists only for an implementer in a Ticket scope.
- **Bind order is part of the layout:**
  1. The host root, read-only, with private `/dev`, `/proc` and `/tmp`; private PID, IPC and UTS namespaces; `--die-with-parent`.
  2. The project, read-only, so it stays visible wherever it lives.
  3. An empty tmpfs over the directory holding every run, so one run never reads another's harness state. That state is where OpenCode keeps a run's session environment, its bridge key included.
  4. The writable roots: the implementer's Ticket source; this run's scratch, harness state and private git state; and any directory the operator's policy adds.
  5. Read-only re-binds that a broad writable root can never reopen:
     - the repository's git metadata: the common `.git`, the worktree's `.git/worktrees/<id>/` and the workspace's `.git` pointer file;
     - a reader's workspace;
     - the bridge directory;
     - the interpreter behind `aew`.
  6. Secret masks, by type:
     - a directory gets an empty tmpfs: `~/.ssh`, `~/.gnupg`, `~/.aws`, agent tools' own sign-in stores such as `~/.local/share/opencode`, `~/.codex` and `~/.claude`, and others;
     - a file gets an empty read-only file: `~/.netrc`, `~/.git-credentials` and others. Not `/dev/null`, because SELinux refuses a device node bound over a home file.
- **The choke point is the process tree.** `ProcessTree(layout=...)` wraps every spawn of a contained tree in bubblewrap. An adapter keeps calling `tree.spawn(argv)` and cannot start an uncontained process; a tree that requires containment and has none refuses to spawn. The supervisor builds the run's tree only after the layout passed its self-test, before the adapter is loaded.
- **Checks run in the same layout** (`policy/checks.py`), through their own contained tree. The supervisor holds each check's tree while it runs: the run ending kills it, and a check cut short by the run's end records nothing.
- **A killed tree starts nothing more** (independent review, 2026-10-04). `ProcessTree.kill()` closes the tree, and spawn and kill are atomic, so "killed, then started" cannot happen. A run's checks are registered in `procs.CheckTrees`: ending the run marks it ended and kills every registered tree under one lock, a check registered after that is killed on arrival, and the run waits (bounded) for its checks to return before it retires its private git state and records its end.
- **The bridge socket always lives under `/tmp`**, whatever `TMPDIR` says. Each sandbox has a private `/tmp`, so no sandbox sees another run's socket. The run's own socket directory is bound in read-only; connecting to a socket needs no write access.

### AEW's own git runs no configured program (independent review, 2026-10-04)
- **The gap:** AEW's host-side git reads and commits the files an agent wrote: the evaluated snapshot's `git add -A`, the prepare-time commit (`status`, `add`, `commit`), the reviewer's diff, integration merges. Git runs programs its configuration names while doing so: clean, smudge and process filters, external diff and textconv drivers, merge drivers, hooks (`prepare-commit-msg` and `post-commit` run even with `--no-verify`), fsmonitor and signing. The configuration is read-only to a contained agent, but a configured command can point at a script in the workspace, which the agent can edit. AEW would then run agent-controlled code outside every sandbox.
- **The rule:** every AEW git call (`workspace/git.py`) switches those programs off. Every filter, diff and merge driver in the effective configuration gets an empty command (a merge driver becomes `false`, so a custom merge is a conflict for the Lead); `core.hooksPath` points at an empty directory private to the process; fsmonitor and signing are off; `diff`, `log` and `show` run with `--no-ext-diff --no-textconv`. The driver list is cached per directory and configuration environment, and re-read when any input of the last read changes: every file git read, every include target (even an empty or missing one), the system, global, repository and worktree files, and the worktree's `HEAD` (for `includeIf "onbranch:..."`); a read whose inputs were not all known beforehand, or with an include that cannot be resolved, is not cached.
- **Trusted drivers:** `containment.trusted_git_drivers` in the execution policy names drivers AEW's git may run: an installed program agents cannot modify, such as git-lfs. Nothing is trusted by default.
- **Refused, not silently different:** a dispatch whose base assigns, in its committed `.gitattributes` or the repository's `info/attributes`, a filter that configuration defines and policy does not trust is refused with `GIT_DRIVER_UNTRUSTED` (the `git.drivers` guard, on every dispatch route). Without the filter AEW would snapshot and commit those files differently from the project's git. The refusal names the driver, the patterns it applies to, its commands and the file defining them, and both ways forward: trust an installed program, or move a repository script out of reach first. `aew doctor` (`git-drivers`) lists every configured driver and whether AEW runs it, and warns when a trusted one runs a program by a relative path.
- **Tests:** `tests/regression/test_m4b_review.py`: a repository whose configuration routes files through every kind of program, each running a workspace script the agent edits; under plain git they run, under AEW's git none does, and the commit holds the agent's bytes. Also trust, a configuration change while AEW runs, the refusal's text and the dispatch refusal.

### Run-private git state (the designer's correction)
- **The agent's git uses private state.** It gets a private index (seeded from the real one at launch) and a private object store, with the real objects as alternates. The agent's environment sets `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY` and `GIT_ALTERNATE_OBJECT_DIRECTORIES`. `status`, `diff`, `add` and `hash-object` work.
- **The real metadata is read-only.** That covers `HEAD`, the index, refs, `commondir`, `gitdir` and AEW's workspace marker, so `commit`, `checkout --detach`, `branch`, `update-ref` and `stash` fail. AEW stays the only actor that can change repository metadata, so its host-side operations always act on an identity the agent could not alter (the confused-deputy risk).
- **Staging is private scratch.** The work product is the content of the working tree, which AEW commits. Nothing real refers to a private object, so nothing is imported, the engine needs no alternates, and `fsck` stays clean. The private state is removed when the run ends.
- **The implementer's context pack says so:** leave the change as files, and never commit, branch, stash or move `HEAD`.

### Fail-closed launch (`containment` in the execution policy)
- **`mode: required`** (the default on Linux):
  - The supervisor builds the layout and runs the **launch self-test on that exact layout** (`probe.py`) before any harness process exists.
  - A probe inside the sandbox appends to an existing sentinel next to the workspace, creates a sibling there, and creates a file in every writable root. It also asks `access(W_OK)` of every protected path, which a read-only mount refuses without changing anything: the real git metadata, the project's `.aew`, and two markers the host places for the probe only, in the host's temporary directory and in a sibling run's directory.
  - **What the self-test vouches for:** the layout AEW assembled, probed at those points. It is a regression guard against bind-order mistakes and the known ways out, not a proof about every path; what an operator adds is checked separately (`writable`, below).
  - The host then checks the outcome itself.
  - Any failure, a missing bubblewrap, or disabled user namespaces ends the run `launch_failed`, with `CONTAINMENT_UNAVAILABLE` and the reason. No harness process starts.
- **`mode: allow_weaker`:** the run launches labelled `workdir_separation_only`, with the reason recorded.
- **`writable`** adds directories every contained run may write (for example a shared build cache), recorded on each run's label. A root that equals, contains or lies under what containment protects is refused at launch, naming what it would expose and what to list instead (independent review, 2026-10-04): the project's `.aew`, the git directories, the runs directory, this run's bridge directory, the Python environment, a masked secret, or the workspaces root (contains only). For the shared temporary directory, containing it, or reaching one of AEW's own `aew-*` directories in it, is refused; a directory such as `/tmp/cache` is not. **`hide`** masks further secrets.
- **Other platforms:** Windows always runs labelled `workdir_separation_only` (below). On any other platform without containment, an explicit `mode: required` refuses the launch and `doctor` reports FAIL; without it, runs launch labelled weaker.

### Labels
- **Every run record's `containment` is an object** with:
  - `filesystem`: `os_readonly_roots` or `workdir_separation_only`;
  - `process_ownership`: `pid_namespace`, `process_group` or `job_object`;
  - `network`: `shared` on Linux, `not_provided` on Windows, until the network amendment below (2026-10-05, F28) is built; then an object whose `mode` is `proxy_only` by default on Linux, with `isolated`, the relay and the egress allowlist it defines;
  - `mechanism`: `bubblewrap <version>`;
  - the self-test result and the layout.
- **Old records:** a record from before M4-B (the string `workdir_separation_only`) reads as exactly that.
- **Where it shows:** `aew harness status` shows the label, and a check result's `method.containment` says where the check ran.
- **`aew doctor`** builds and self-tests a sandbox live:
  - PASS when contained;
  - FAIL when the policy requires containment and it is unavailable;
  - WARN under `allow_weaker`;
  - on Windows, WARN with the note above.

### Process ownership (E13)
- **The recorded pid is bubblewrap's host pid.** It leads the process group, so the sentinel, `killpg` and `same_process` keep working.
- **Killing it ends the PID namespace**, including a descendant that called `setsid`. The POSIX residual above is closed for contained runs.
- **A pid a contained agent reports is namespace-local.** `procs.host_pid(ns_pid, under=<bwrap pid>)` translates it through `/proc/<pid>/status` `NSpid`, looking only under the run's own bubblewrap processes, and reads it at the run's namespace level, so a process the agent started in a further nested sandbox is placed correctly. A pid nothing under the run has raises `LookupError`: it is never taken for a host pid (independent review, 2026-10-04).

### Residual risk added by this amendment (documented, not closed)
**The harness server's environment is readable from the agent's shell.**
- **Why:** the agent's own environment carries no provider secret and no server password, as above. But the harness server is the agent shell's parent, runs as the same user, and shares its PID namespace whether or not the run is contained. So its environment (the provider key the policy names, and the server password) is one read of `/proc/<parent>/environ` away. No AEW credential is ever there.
- **Status:** closing this needs the server outside the agent's user or namespace. Until then it is stated here, and `test_residual_the_harness_servers_environment_is_readable_from_the_agents_shell` asserts it. The day it stops being true, that test fails and this paragraph changes.
- **Narrowed by design (2026-10-05):** the network amendment below takes the provider key out of the sandbox entirely (the supervisor's relay holds it). Once F28 is built, this residual is the server password only, and the test narrows with it.
- **To investigate:** using OpenCode's stored authentication in the run's private data directory, instead of environment variables.
- **Secret masks are computed at launch.** A secret file or directory created on the host while a run is live is readable from it until the run ends; the next launch masks it.

Windows keeps the M3 model: workdir separation, a job object, and the same-UID residual above. Real-repository dogfood runs on Linux only, by process (`m4-ambiguity-report.md`, M4-B4).

### Tests
- **`tests/integration/test_containment.py`** (Linux) covers:
  - the isolation design's §12 escapes, one per test: absolute path, `..`, symlink, rename, `mkdir`, a temp file outside scratch, Python `open()`, a shell redirect, and another worktree. Each is refused by the OS, and the host stays byte-identical;
  - the confused-deputy attempts on the git metadata, and run-private git;
  - secrets and another run's harness state being invisible;
  - the self-test, against a writable root laid over the host and against an unprotected `.git` pointer;
  - fail-closed launch without bubblewrap;
  - teardown after `setsid`, a double fork, `SIGKILL` of bubblewrap and `SIGKILL` of the owner;
  - a check running inside the layout.
- **`tests/unit/test_containment_layout.py`:** bind order, the exhaustive role table, masks by type and labels.
- **The existing harness suites run contained on Linux.** CI installs bubblewrap, and the setup action lifts Ubuntu's AppArmor restriction on unprivileged user namespaces. Tests whose subject was the uncontained behaviour now assert both: uncontained, a reviewer's edit is detected afterwards (`WORKSPACE_MUTATED`); contained, it is refused where it is made.

## Amendment 2026-10-04 — Lead session custody (independent review of authority and custody)

The Lead's harness now gets what a run's harness already had: process ownership. A credential an `aew` command issues goes only to the operator's terminal. The guarantees the Lead is symmetric with are unchanged; this closes the paths around them.

### The Lead's harness runs in an owned process tree (`procs.run_session_tree`)
- **Windows:** the harness is created suspended, assigned to a kill-on-close job object, and resumed. It keeps the operator's console (a hidden one only when there is none, so no window appears).
- **Linux:** a small reaper process parents the harness and makes itself a child subreaper (`PR_SET_CHILD_SUBREAPER`). A descendant that detaches (`setsid`, a double fork, `nohup ... &`) is re-parented to the reaper, not to init. When the harness exits, or the broker dies (its control pipe closes), the reaper kills every descendant, reaps until none is left, and reports `clean`, `survivors` or `unowned`. It stays in the session's process group and on its terminal; Ctrl-C belongs to the harness. Run supervisors the broker starts for `--launch` are the broker's children, not the reaper's, so runs outlive the session as before.
- **An acquired seat is released only when the tree is `clean`.** Otherwise it stays held, and the output says to continue with a terminal takeover. A process the session left behind can therefore never find the seat vacant.
- **Other POSIX systems** have no subreaper: ownership is `unowned`, and the seat is kept.
- **Residual (documented):** a process started through another service (cron, `at`, a user systemd unit) is not a descendant, and no process ownership reaches it. The Lead's harness runs uncontained, as the operator, so persistence the operator's account allows is outside this boundary. That is the ADR-0005 same-UID threat model.

### Credentials go only to the terminal (`src/aew/cli/credentials.py`)
- `lead acquire`, `lead takeover`, `lead handoff offer` (its offer secret), `lead handoff accept`, and a dispatch without `--launch` (its invocation credential) write the credential to the controlling terminal (`/dev/tty`; on Windows the console), never to standard output. The JSON result says `"(written to your terminal)"` in its place.
- With no terminal and no opt-in, such a command is **refused before it runs**, so no credential is issued that nobody received.
- **`aew --print-credential ...`** puts it on standard output, for a script that keeps it safe (the test suite, the perf tooling, the dogfood driver). A Lead session refuses the flag, in the CLI and in the broker.
- **The takeover prompt** names the requesting process chain (`requested by : aew (pid) <- ... `) and where the credential will go (`this terminal only`, or the requester's standard output under `--print-credential`). It tells the operator to refuse a request they did not start, for example one from an agent's shell.

### Lead broker hygiene
- The broker removes `AEW_LEAD_TOKEN` from its own environment as soon as it reads it. Host-side git builds its environment through `contract.scrub_credentials`, so git and its hooks never inherit a credential, whoever calls them.
- **A pending handoff does not end authority.** The broker closes its bridge only on `StaleAuthority` (takeover, an accepted handoff, release elsewhere). While a handoff is pending, each request reaches the engine, which refuses everything but `lead handoff cancel`; after a cancel the same session continues.

### What AEW trusts from the environment, and why an agent cannot use it
An environment variable changes only the process that reads it. An agent controls the environment of the processes it starts, and none of those holds a credential: custody keeps every credential in a supervisor or broker, whose environment comes from the operator's launch, never from the agent. So an agent's environment can only change what a credential-less command does, and the engine refuses such a command anything that needs authority.

| Variable | Read by | Effect | Why an agent cannot use it against custody |
|---|---|---|---|
| `AEW_LEAD_TOKEN` | any `aew` command; `aew lead session` (then removed) | the Lead credential | never in any harness or agent environment (`CREDENTIAL_ENV` is scrubbed everywhere); a forged value fails verification |
| `AEW_INVOCATION_TOKEN` | role commands outside a run | an invocation credential | as above |
| `AEW_SERVICE_TOKEN` (M6b) | the knowledge service's own process, outside any run | a `service` credential (ADR-0005, 2026-10-05): one closed transaction family, no Lead authority | never in any harness or agent environment (scrubbed with the other credential variables); refused by every operation outside its family and by the store at commit (`TRANSACTION_CLOSURE`); the broker refuses `service issue` |
| *(no dashboard variable)* | — | the dashboard's `operator_session` credential (ADR-0005, 2026-10-05; F20.3) is never carried by a variable, a flag, stdin or a file: `aew dashboard serve` and `open` authorize at a console with a typed-back code and deliver a one-time URL to the terminal (or to stdout with `--print-credential`) | the broker refuses both commands as credential-emitting; `local/dashboard/control.key` locates the running server and authorizes nothing (the code is shown only on the serving console); the credential lives in the browser's `HttpOnly` cookie and the server's memory |
| `AEW_AGENT_ENDPOINT`, `AEW_AGENT_KEY`, `AEW_INVOCATION`, `AEW_RUN`, `AEW_WORK_UNIT` | the `aew` CLI inside a run | which run bridge to call, and its key | the bridge authenticates by key and holds the credential itself; contained runs cannot see another run's bridge or state |
| `AEW_LEAD_BROKER`, `AEW_LEAD_BROKER_KEY` | the `aew` CLI inside a Lead session | route Lead commands to the broker; refuse credential-issuing commands and `--print-credential` locally | unsetting them leaves a command with no credential (refused by the engine). Credentials still go only to the terminal, the takeover prompt names the requester, and the session's processes end before an acquired seat is released |
| `AEW_SCRATCH` | the agent | where scratch files go | no authority |
| `AEW_HARNESS_ADAPTERS` | the launching CLI and the supervisor | extra harness adapters (code it loads) | read from the operator's launch environment; never passed to an agent |
| `AEW_OPENCODE_BIN`, `AEW_OPENCODE_CATALOG_S`, `AEW_OPENCODE_CATALOG_SETTLE_S` | the supervisor (OpenCode adapter) | which OpenCode binary, catalog timeouts (a raised catalog wait raises the derived start deadline with it) | as above |
| `AEW_LAUNCH_ACK_S`, `AEW_RUN_STALE_S` | the launching CLI; status readers | launch acknowledgement wait; supervisor staleness | timing only, and only in the reading process |
| `AEW_RUN_START_S` | the supervisor | replaces the derived deadline that caps a run's whole start, from custody to `running` (amendment 2026-10-09: a run's start has a deadline) | timing only; read from the operator's launch environment, never passed to an agent |
| `AEW_FAULT`, `AEW_FAULT_MODE`, `AEW_PAUSE` | any `aew` process | fault injection and pause points (tests) | effective only in the process that reads them; a credential-less process can fail or pause only itself |
| `AEW_PROFILE` | any `aew` process | write a timing profile to a file | as above |

### Tests
- `tests/integration/test_lead_session.py`: a detached process the Lead's harness leaves behind is dead before the seat is released and never acts; a credential is never issued onto a captured stdout; a pending handoff refuses without ending the session; `--print-credential` is refused in a session; the broker is non-dumpable and the reaper's environment holds no credential (Linux).
- `tests/integration/test_authority.py` (AT-4b, Linux pty): a takeover at a real terminal shows the requester and the destination, writes the credential to the terminal, and puts `(written to your terminal)` on stdout.
- `tests/unit/test_credential_delivery.py`: which commands issue a credential, delivery and refusal, the prompt, the process chain, and git's environment.
- Each guard was shown to fail its test with the mechanism removed, on Windows and on Linux.

## Amendment 2026-10-05 — network containment on Linux (F28; the network containment design v0.2)

The M4-B amendment contains a run's filesystem and processes and leaves its network shared: `network: shared` on
Linux (truthful topology, PR #50) and `not_provided` on Windows, with a documented residual, the provider key the
policy names being readable from the agent's shell through the harness server's environment. This amendment adds the
network dimension and takes the provider key out of the sandbox. Its text is the frozen
`docs/design/network-containment-design-v0.2.md` §3 (ledger NET), probed on Rocky Linux 8.10 (kernel 4.18,
bubblewrap 0.4.0, SELinux enforcing) with OpenCode 2.0.18
(`docs/archive/reviews/architecture-review-2026-10-04/t6-network-containment.md`); the designer accepted the direction
on 2026-10-04 and fixed this text on 2026-10-05. **Designed, not built:** the implementation is register F28, required
before internal alpha and not an M4-C or M4-D blocker. Until it lands, nothing in AEW calls a Linux run
network-contained.

### What F28 claims, exactly
- **A private network namespace.** A model-controlled run, the Lead's harness included, runs under `--unshare-net`:
  the sandbox has `lo` only. No route exists from the run to any network; a connect to anything outside fails at the
  OS, as a forbidden write fails with `EROFS` under F2.
- **Provider traffic through a secretless shim to a supervisor-owned credentialing relay.** The harness's provider
  `baseURL` points at a loopback endpoint inside the sandbox. A small AEW-owned shim, in the run's namespace and owned
  by the run's process tree, forwards the plaintext provider-protocol bytes over a filesystem AF_UNIX socket to a
  reverse relay the supervisor owns outside the sandbox. The relay has a fixed upstream from the execution profile,
  strips or replaces any credential the client sent, adds the real provider credential, speaks TLS to the gateway and
  streams the response back. The sandbox holds at most a non-secret sentinel key where an SDK syntactically needs
  one. The relay accepts no upstream from the sandbox, so the model cannot turn it into a forwarding or SSRF oracle.
- **Provider credentialing and generic egress are separate mechanisms** (the design's §1.1 correction). A
  conventional HTTPS CONNECT proxy cannot add a header inside an end-to-end TLS tunnel, so the production custody
  claim is never header injection into a CONNECT tunnel. Non-provider egress, when policy authorizes any (a
  connected-mode catalog refresh, `models.opencode.ai:443`), goes through a separate supervisor-owned allowlist proxy
  with a bounded `host:port` list and no provider credential. Web fetch, browser and package destinations are never
  implied by a harness tool's existence; each needs its own authorized capability.
- **The supervisor reaches the harness server through the same shim** (host, bound AF_UNIX socket, shim, the
  server's loopback port; about 0.7 ms per request in the probe) where the harness lacks native unix-socket
  transport. The ADR-0005 bridge is unchanged: a filesystem AF_UNIX socket survives the namespace, an abstract one
  does not.
- **Not confidentiality of traffic, and not the server password.** The relay forwards bodies as they are. The
  harness server still runs in the run's PID namespace as the same user, so its own password stays one read of
  `/proc/<parent>/environ` away: that residual remains open, stated in the M4-B amendment's residual paragraph and
  narrowed to it.
- **Not Windows.** Windows has no network namespace; its runs stay `network: not_provided` until a separate backend
  exists.

### Labels
The containment label's `network` becomes an object:
- `mode`: `proxy_only` (the namespace plus the credentialing relay, any further egress only through the allowlist
  proxy), `isolated` (the namespace with loopback and control sockets only, no egress path), `shared` (the host's
  network: truthful topology, no containment guarantee), `not_provided` (AEW cannot enforce or characterize network
  containment on this backend or platform);
- `provider_relay`: `configured` or `none`;
- `egress_allow`: the `host:port` list, only when generic egress exists.

Until F28 is built, Linux M4-B runs are labelled `shared` and are never retroactively described as `proxy_only`.
Once F28 is accepted, Linux model-controlled runs default to `proxy_only` and `shared` becomes an explicit weaker
execution-policy choice. `aew harness status` shows the mode and, for `proxy_only`, the relay and the allowlist; a
check result's `method.containment.network` says where the check's traffic could go.

### The namespace and the shim (`layout.py`, `bwrap_argv`)
`Layout` gains a network mode and the AF_UNIX paths that mode needs; `bwrap_argv` adds `--unshare-net` for
`proxy_only` and `isolated`. The shim runs for the run's lifetime as a sibling the supervisor's process tree owns, not
a wrapper that `exec`s away, and provides only the endpoints configured for that run: the supervisor-to-server leg,
the provider-relay leg and, when authorized, the generic-egress leg. It holds no provider credential, no Lead
credential and no policy authority; ending the run ends it. Codex may use its native `unix://` app-server transport
and omit the server leg once the pinned adapter proves it.

### The credentialing relay (supervisor, outside the sandbox)
For `proxy_only` the supervisor starts one relay per required provider or profile, or an equivalently isolated
multiplexer with the same fixed mapping. The provider key is never copied into the harness, the server or any
model-controlled environment or file; the relay is outside the run's PID and network namespaces and follows the
existing credential-holder custody rules. It is provider infrastructure, not a general web proxy.

### Adapters
OpenCode: the provider `baseURL` is projected to the relay endpoint under `proxy_only`; any SDK-required key inside
the sandbox is sentinel material; `HTTP_PROXY` and `HTTPS_PROXY` are set only for the separate egress proxy when
such egress is authorized; `NO_PROXY` covers the server, bridge and relay loopback endpoints; the real `provider_env`
goes only to the relay. Codex follows the same boundary; its native `features.network_proxy` or sandbox domain rules
are optional defence in depth behind the namespace, never the credential holder or the authoritative label.

### Self-test and readiness
The launch self-test proves the boundary without a provider-specific operation: direct non-loopback egress from
inside the sandbox fails; the bridge answers over its filesystem socket; the supervisor-to-server path through the
shim works; a supervisor-owned local probe upstream succeeds through the relay path; an unauthorized generic-egress
target is refused; the model-controlled environment and readable files hold no provider secret. Provider or gateway
readiness is a separate adapter and `doctor` check against that profile's bounded health or catalog operation,
explicit and fail-closed, never conflated with containment.

### The OpenCode catalog
Offline model availability is bounded by the binary's embedded or seeded catalog. An air-gapped release may carry a
sanitized, checksum-pinned catalog seed produced from a clean disposable instance of the exact supported pin, never
an operator's `opencode.db`; `aew doctor` verifies the seed's fingerprint and that the configured model appears in
the effective catalog. An official offline-catalog mechanism in a later pin is preferred when it exists.

### Project checks and the Lead
Checks default to `network: isolated`, not to the parent run's mode. A check may request `proxy_only` or `shared`
only where the check definition and the execution policy permit, equal to or stricter than the policy's ceiling, and
the effective mode and allowed egress are recorded with the check's evidence. The Lead's harness is model-controlled
execution and defaults to `proxy_only` on Linux once F28 is built: operator ownership of the TUI does not make the
Lead's shell a safe holder of a provider credential; operator UI and attach traffic stay outside the boundary, and a
broader Lead network capability arrives as an explicit bounded capability.

### Frozen designer decisions (2026-10-04)
1. The Linux default after F28 is `proxy_only`; `shared` is an explicit weaker policy mode. 2. The Lead is included.
3. Checks default to `isolated`. 4. The catalog seed is accepted with the qualification above. 5. Provider
credentialing and generic egress are separate mechanisms. 6. Network containment is a pre-internal-alpha requirement,
not an M4-C or M4-D blocker; no internal-alpha security claim calls Linux runs network-contained before its live lane
passes.

### Costs, and what is not shown
The supervisor-to-server path costs about 0.7 ms per request. Unmeasured, and to be proved by the implementation's
conformance lane: a real streamed model turn through the relay against a TLS gateway (the probe's gateway was a local
stand-in), backpressure and cancellation under long streams, IPv6 upstreams, and the shim's lifecycle details.
slirp4netns is not needed and does not work unprivileged on EL8.

### Tests (written with F28)
`tests/integration/test_containment.py` (Linux): the namespace has `lo` only; a direct connect fails at the OS; the
bridge answers across the namespace; the shim carries the supervisor's requests; a `proxy_only` run's server
environment has no provider variable; the relay attaches the credential for its fixed upstream only and replaces any
the run sent; an unauthorized egress host is refused; the self-test fails closed; a check under `isolated` reaches
nothing. `tests/unit/test_containment_layout.py`: `--unshare-net` in `bwrap_argv`, the label object, old records read
unchanged. The M4-B residual test narrows to the server password.

## Amendment 2026-10-06 — Q12: the harness hosts, AEW attaches (designed, not built)

The designer's Q12 decision (decision record [`decisions-2026-10-06-q12-hosting-and-lead-attachment.md`](../../design/decisions-2026-10-06-q12-hosting-and-lead-attachment.md)) settles hosting; register F31 builds what it changes here.

- **The boundary.** AEW and its supervisor own the Lead attachment and its authority, generation creation and
  revocation, broker and project capabilities, the curated environment, the requested and effective execution
  profiles, the harness configuration inputs, capability negotiation, and lifecycle observation and provenance. The
  adapter translates these into the harness's native configuration and lifecycle mechanisms. The harness owns model
  execution and never becomes workflow authority. A launcher or wrapper may set up, launch, supervise and tear down, but
  decides no workflow progression, evidence acceptance, retry, gate or other AEW semantics.
- **The Lead session.** Today `aew lead session -- <harness>` and `aew opencode` tie the Lead broker to the wrapped
  harness process (with `--acquire`, the seat too; with the operator's `AEW_LEAD_TOKEN`, authority outlives it), and a
  superseded session keeps running as a read-only session. Under Q12 an attachment opens and closes (`aew open`,
  `aew close`) while the harness and its conversation keep running; a later attachment re-hydrates from canonical
  project state, which wins over the model's retained context. After `aew close` the model has no AEW project
  authority and no AEW-mediated project access through the detached attachment, AEW's read and query commands included; the harness itself is not
  sandboxed away from the project (decision record §14.4).
- **Native subagents.** A harness's own subagent feature may be used only where the adapter preserves AEW's invocation
  identity, role, custody, execution profile, parent relationship, limits and evidence and provenance; otherwise AEW
  dispatches. No
  native feature may bypass AEW dispatch or create an uncontrolled subagent.

## Amendment 2026-10-06 — one AEW Provider Gateway (F18.8; designed, not built)

The designer's F18.8 decision (decision record
[`decisions-2026-10-06-f18-2-f18-8-hosting-reconciliation.md`](../../design/decisions-2026-10-06-f18-2-f18-8-hosting-reconciliation.md)
§2) composes the credentialing relay of the amendment of 2026-10-05 with the F18 hosting design v0.6's request
gateway into one AEW Provider Gateway. ("The gateway" in the amendment of 2026-10-05 is the upstream provider or
organization gateway the relay speaks TLS to; here the Provider Gateway always carries its full name.)

- **One logical component.** The relay's fixed-upstream credential routing and the F18 request gateway's attestation
  are two responsibilities of one provider-traffic authority boundary, the AEW Provider Gateway. Model-controlled
  traffic reaches the Provider Gateway only through the secretless in-sandbox shim. The Provider Gateway identifies the
  attachment or run and the qualified pin, attests the request surface and denies before egress on a mismatch, and only
  then selects the fixed upstream (the provider or organization gateway), attaches the real provider credential,
  originates TLS or mTLS, observes the response and binds its tool calls single-use.
- **One custodian.** The provider credential's only holder is the Provider Gateway. The custody rules of "The
  credentialing relay" above still hold; F18 adds no second credential store or credentialing proxy.
- **Generic egress stays separate.** The credentialless allowlist proxy never receives a provider credential and cannot
  widen or select the Provider Gateway's fixed upstream.
- **Implementation.** The Provider Gateway may be split internally, but a split must not open a gap between the
  request it attested and the request it credentialed and forwarded. A single composed service is preferred.
- **What governs what.** The amendment of 2026-10-05 keeps governing network containment and fixed-upstream credential
  routing (F28); the hosting design governs attachment-aware attestation and broker binding (F18.8).

## Amendment 2026-10-10 — `harness send` takes `--when`, and posts `steer` by default (register E55)

The F9-A MS0 probe of OpenCode 2.0.18 ([ADR-0017](0017-coordination-messages.md) D8, its
[evidence](evidence/f9a-delivery-probe-2026-10-10/probe-results.md)) found that a `queue` input is admitted only when
the agent's loop would end, after its turn, while `steer` is admitted at the next step boundary. The designer's
decision of 2026-10-10 ([record](../../design/decisions-2026-10-10-f9-steer-vs-queue.md)) and its refinements
([G1 and G2](../../design/decisions-2026-10-10-f9-a-g1-g2.md), [G4](../../design/decisions-2026-10-10-f9-a-g4-rename.md))
replace this ADR's "queued prompt" with two explicit timings. Built by slice HS1 of the F9-A plan's amendment 2:

- **`aew harness send --when next-step|turn-end`.** `next-step`, the default, posts `delivery: steer`: the message
  reaches the agent at its next step boundary, inside the turn, without interrupting a running tool or model call.
  `turn-end` maps to `delivery: queue`, after the agent's turn, and exists only through the F9 message store. The
  mapping is one constant (`aew.harness.delivery.WHEN_DELIVERY`, re-exported by `aew.coordination.layout`), and the adapter interface is
  `send(text, delivery)` (`harness-conformance.md`).
- **The route** is decided under the control lock, before any write, from the project's adopted messaging switch and the
  run's launch snapshot of it:
  - both off (M4-H's treatment): `next-step` is the recorded request file, as before (1 MiB); `turn-end` is refused
    `TURN_END_NEEDS_MESSAGING`, so no Lead path posts `queue`;
  - both on: every send is refused `HARNESS_SEND_NEEDS_STORE` until F9-A's MS5b records it in the store, from which it
    still wakes a held session;
  - they disagree: refused `MESSAGING_SNAPSHOT_MISMATCH`, before any timing's own refusal; the remedy is a relaunch.
    With the project switched on, until F9-A's MS4 writes the run's snapshot, every run reads as launched with messaging
    off, so that refusal says that sending needs messaging switched off rather than advising a relaunch that could not
    help.
  - Every refusal writes nothing: no request file, no control-state entry, no post.
- **The held session** after `harness interrupt` is still woken by a `harness send`: `steer` with the default `resume`
  wakes it, as `queue` did.
- **The completion-boundary rule** (a turn is over only when none of AEW's prompts is still queued) is unchanged and
  stays tested with a `queue` input at the adapter level.

## Amendment 2026-10-10 — the run directory holds the run's live usage (F25 for M4-H, slice L2)

A supervised OpenCode run's directory gains two files beside the run record: `usage.live.json`, the run's live usage
sample (`aew/usage-live/v1`), and `usage.live.state.json`, its meter's own state. Like the rest of the local run
records they are non-authoritative telemetry that no gate reads (`runlog.py`'s docstring says the same):

- the adapter's meter is the live file's only writer: it writes `prompt_state: unsent` before the harness server
  starts, and a failed write refuses the launch;
- a live write never bumps the wake file, unlike a run record's;
- a live file is read with the run directory's guards (`runlog.read_live`: no link followed, a regular file, at most
  16 MiB), and anything else is no sample.

The files are at the run root, outside what a contained run binds back (scratch, harness state, git), so the agent
cannot write them there. Without containment, and in a deployment where the Lead and AEW's supervisors share one uid,
the same-uid residual of this ADR applies to them as to the run record. See
[harness conformance](../harness-conformance.md) §5.2.

## Amendment 2026-10-11 — the Windows containment label (decided, not built; register F48)

The designer's Windows containment decisions (2026-10-11, and 2026-10-12 on isolation between runs and on selecting
the backend) settle the label a contained Windows run carries; register F48 builds it. Until then Windows runs keep
`workdir_separation_only`, as above. Each bullet says which parts are the designer's and which are implementation
choices recorded in register F48.

- **The vocabulary (designer).** `filesystem` gains `os_integrity_label`, with `mechanism:
  mandatory_integrity_control` (Windows Mandatory Integrity Control). *Implementation (register F48):* the run's tree
  labelled Low, `.aew/` and AEW's own state at Medium.
- **Isolation between runs (designer).** The MIC-only label states `runs_isolated_from_each_other: false`: runs at
  one Low level are not isolated from each other.
- **`masked` is an exhaustive read-deny (designer)**, not a best-effort list: every withheld or secret path is
  read-denied, and the self-test proves the denial for each path. AEW applies the NO_READ_UP labels, verifies them
  and can restore the original descriptors (designer). *Implementation (register F48):* verification in `doctor` and
  preflight; a missing label fails closed.
- **Confirmers (designer)** count as capable on Windows when the withheld set's requirements hold (every withheld path
  read-denied and verified). Register F48 further requires the isolated backend below before a Windows label claims
  it.
- **Native and WSL (designer)** are both supported, the backend selected per project or profile, never per run.
  *Implementation (register F48):* the label's `host` field records the profile.
- **The isolated backend (designer).** Isolation between runs and of authority is required for qualification at the
  governed reviewer and verifier boundary and the worker-to-Lead boundary; a truthful "not independent" label is not
  enough. It is delivered by AppContainer workers or per-run restricting SIDs or write-restricted tokens, chosen on
  measured evidence. That backend gets **its own** label value and mechanism, stating only what its self-tests prove.
  Its wording is not written here: it is owed to the designer as a later amendment to this ADR (register F48's item
  in [decisions due](../decisions-due.md)).

Dropping the operator endpoint's `dev` label once a platform is qualified (designer, 2026-10-12) concerns the
endpoint, not this label: ADR-0005's amendment, owed with the slices that build the operator session and qualify
each platform (register F47.3 and F48), records it.

## Amendment 2026-10-21 — the store's path, the control lock and non-writers (STG-05 CS-1: CB-07, CB-09, CBF-1)

This amends the M4-B amendment's bind order (2026-10-03) and how a contained process reaches the control state. It
builds three outcomes of the STG-05 hand-off for CS-1, under the operator's hold exemption for CS-1 only.

### Bind order: ancestors first (`layout.bind_order`)
- **Before:** every writable bind came first, then every read-only re-bind.
- **Now:** the writable binds, the read-only re-binds and the masks of `.aew/local` and the runs directory are applied
  together, by depth, ancestors first. On one path a re-bind comes after a writable bind, and a mask after both.
- **Why:** a bind holds for its whole subtree except where a deeper bind says otherwise. So a read-only re-bind under
  a broad writable root still closes what it protects.
- **A writable bind under a read-only re-bind is applied after it and stays writable.** The Lead's layout needs that
  rule (CS-4).
- **A reader's workspace is the exception.** It must stay read-only whole, so a policy root inside it is left out of
  the reader's layout (review of #231, m3). Before, every re-bind came after every writable bind, so such a root was
  read-only to a reader. An implementer still gets the root.
- **One owner:** `bwrap_argv` emits the order and the store check reasons about it.

### No writable bind may change the store's path (CB-07, ruling R-3)
- **The predicate:** `for_run` checks it on the final layout, for every writable bind `W`, the role's own and the
  policy's alike:
  - `W` is not the store (`<project>/.aew/state`) and does not lie under it;
  - if `W` contains the store, the first directory below `W` on the path to the store is re-bound read-only after `W`.
    That re-bind is a mount point, which cannot be renamed, replaced or removed.
- **Both spellings of the path:** the predicate is checked on the path the engine walks (the project's own
  `.aew/state`, which `Kernel.locate` finds by name) and on the path it resolves to. A symlink on the walked path
  cannot be protected by a re-bind, because a mount lands on the link's target and the link stays renamable. So a
  writable bind over such a link is refused (review of #231, m1).
- **On failure:** a layout that breaks the predicate is refused (`CONTAINMENT_UNAVAILABLE`, reason
  `writable_bind_in_store`, `store_path_writable` or `store_path_symlink`), naming the bind and what it would need
  instead.
- **This is not the operator-root guard.** Run directories live under `.aew/local`, so the guard's own rule would
  refuse every run.
- **The project is required:** a contained run is refused when it has none, since the check needs it.

### The control lock is not in an agent's layout (CBF-1)
- **The mask:** the empty tmpfs that hid the runs directory now covers the project's whole `.aew/local`, plus the runs
  directory if it lies elsewhere. Only the run's own directories are bound back. The mask is applied at its depth in
  the bind order, so no bind above it (the R-2 shape's `.aew` re-bind, a reader's workspace that contains the project)
  shows the host's `.aew/local` again (review of #231, m2). Once the run's own directories are bound back, the mask is
  remounted read-only (`--remount-ro`, which bubblewrap 0.4.0 has; the bind-backs keep their own flags), so a
  contained process cannot make a lock file of its own there (m5). A `.aew/local` that does not exist yet is created
  first, so a lock a host writer creates later is hidden too (m4).
- **The effect:** the control lock (`.aew/local/control.lock`) is not in the sandbox at all, and nothing can create a
  file at that path there. The store (`.aew/state`) stays visible, read-only.
- **`FileLock` opens the lock file for writing only.** The M4-B fallback is gone: it opened an existing lock file
  read-only on a read-only mount and still took `LOCK_EX`, "so a contained reader still serializes with the engine's
  writers". No reader needs the lock now (below), and a process that cannot open it for writing is not one that may
  hold it.

### Non-writers read lock-free (CB-09)
- **The kinds:** `aew.process_kind` lists AEW's entry points and their kinds:
  - **store writers:** the `aew` CLI, and the run supervisor. The Lead broker runs the CLI in its own process
    without declaring, so it is a writer too, as it must be;
  - **non-writers:** the CLI inside a worker's run (`AEW_AGENT_ENDPOINT` set), `aew lead mcp`, and
    `aew dashboard serve`, which reads lock-free and serializes its publication with its own endpoint lock.
- **The rule:** in a non-writer, `ControlStore.read`, `session` and `create` are refused before the lock is opened
  (`PERMISSION_DENIED`, reason `non_writer_process`). Such a process reads only through `read_committed`,
  `configuration.read_committed`, `outbox.LogView` and `outbox.read_transitions`, which take no lock and run no
  recovery, so they work on the read-only store.
- **One opener of the lock:** `ControlStore.control_lock` is the only place AEW opens the control lock, and it refuses
  a non-writer. `read`, `session`, `create` and the log compactor's publish all take it there, and a test refuses a
  `FileLock` on the lock's path anywhere else.
- **The engine's reads choose by kind:** every read the engine makes goes through `ControlStore.current`. That is
  `read` in a writer and `read_committed` in a non-writer, and `Kernel.manifest` makes the same choice. So the CLI's
  reads work inside a worker's run, except the reader git gap below. A first version left the engine's reads on
  `read` and refused every read command in the sandbox (review of #231, B1).
- **The reader git gap, pinned and not fixed here.** A fingerprint read of a fresh or changed workspace runs
  `git add -A` into a throwaway index, which writes or freshens blobs in the object store:
  - **Inside a reader's sandbox,** where the real object store is read-only, `gate show` and `work roles` of such a
    Ticket answer `GIT_ERROR`. The sandbox test pins exactly these (`READER_GIT_GAP`), recognised by their mechanism.
  - **Outside a sandbox** (every worker run on Windows, and any non-writer run uncontained), the same read succeeds by
    writing loose objects into the real repository's `.git/objects`. No test sees that face yet.
  - The designer ruled the outcome (D-CS2-1): a reader never writes the real object store. CS-2 builds it (its outcome
    7), for both faces.
- **What a non-writer writes:** never the store, and never the lock. Under `.aew/local` it writes only the derived
  history index's catch-up, as every reader of archived history does (the dashboard server among them). Every result
  of that index is authenticated against the store's history root, and on a read-only view the index is a private
  copy instead. A command whose purpose is a write there is refused. The commands a non-writer is refused are listed
  with why in the test:
  - `history audit` (the lock);
  - `history compact` (the lock and `.aew/state/log`);
  - `context pack` and `history reindex` (derived data under `.aew/local`).
- **The bridge:** a worker's `whoami`, `check run` and `submit` already go through the run's bridge, where the
  supervisor, a store writer, holds the credential and takes the lock.
- **The declaration is behaviour, not the boundary.** An agent can unset the variable it is judged by. What holds
  regardless is the layout: the read-only store, and the lock outside it.

### Tests
- **`tests/unit/test_containment_layout.py`:**
  - the bind order;
  - the predicate over every role in `WORKSPACE_ACCESS`, through what the run records of its layout;
  - three planted bad binds refused: a workspace that is the project root, a scratch at `.aew`, and a harness
    directory under the store;
  - the second clause's ordering;
  - a symlinked `.aew` under a writable bind refused;
  - the masked-path invariant enumerated over the argv (no bind on or above a mask after it, the read-only remount
    after the bind-backs), every role's layout and the R-2 shape;
  - a policy root inside a reader's workspace left out, and a missing `.aew/local` made and hidden;
  - a run without its project.
- **`tests/integration/test_containment.py`** (Linux):
  - from a worker sandbox the lock is absent, creating it fails with `EROFS`, and the run's bound-back harness
    directory stays writable;
  - every command a worker can run, inside a reviewer's sandbox, either works or is refused for a reason of its own,
    with no crash. Nothing meets the read-only filesystem but the pinned reader git gap (`READER_GIT_GAP`, above), and
    only `WRITER_ONLY` is refused as a non-writer's;
  - a non-writer's lock-free reads work against the store on the read-only bind, and its locked read is refused as a
    non-writer's.
- **`tests/integration/test_non_writer_reads.py`:**
  - the table;
  - the refusals before the lock;
  - the reads against a read-only store, with no `EROFS` or `EACCES`, and a writer's failure there;
  - the CLI inside a worker run: its reads succeed, and a mutation is refused before the lock;
  - `history compact`, `context pack` and `history reindex` refused as a non-writer's before they start;
  - every command a worker can run (each parser leaf, and each surface-map probe, with an in-flight and a finished
    Ticket) on a worked project: a stat snapshot of the whole `.aew` tree is unchanged but the history index's
    catch-up, the lock is not created, nothing crashes, and only `WRITER_ONLY` is refused as a non-writer's;
  - the reader git gap's classifier, on planted cases both ways;
  - the one opener: no code outside `engine/store.py` names the control lock's path, found by import and by literal,
    with a second, text-based detector that must agree on the tree and on planted cases;
  - the entry-point table against the tree, both ways: every module that runs as a process is a row, and every row is
    one;
  - a guard that no code outside the store calls `store.read()` but the manifest reload.

## Amendment 2026-10-23 — a process's identity survives a wall-clock step

This amends **Process ownership** above ("tooling that must act on a pid checks the process start time against the
run's custody time"), and every record that names a process by its pid and start time, including ADR-0004's custody
worker, which registers `{host_pid, started_at}`. It is a correctness fix, found while closing a test race.

### The defect
- **The cause:** on Linux, `procs.started_at` was `/proc/stat` `btime` plus the process's start ticks (`/proc/<pid>/stat`
  field 22) over `SC_CLK_TCK`. `btime` is the wall clock minus the time since boot, so it moves every time the wall
  clock is stepped: by NTP, on a VM, after suspend and resume, and by WSL's clock sync. On WSL Ubuntu, `btime` was
  measured stepping +3 s about every 35 s.
- **The effect:** `procs.same_process(pid, started_by)` required `start <= started_by + 2.0`. After a net forward step of
  more than 2 s it judged a live process gone. A live validation executor could then be recovered, or a live custody
  worker's custodian ended, while it still ran. Teardown could also miss a live supervisor, and a live broker could be
  reported as crashed. The dashboard's and the operator endpoint's locators could likewise read their own process as
  stale.
- **No epoch time can fix it.** For the same process, the stored and the current value differ by the net step. For a
  reused pid, they differ by the later start. The two look the same, so a wider tolerance only defers the misjudgement:
  steps accumulate without bound.
- **Windows** uses `GetProcessTimes`, an absolute creation time, and was not affected.

### The invariant
On Linux a process's identity, its pid together with its start, never changes while the process lives, whatever the
wall clock does. A reused pid, or the same pid after a reboot, is still told apart.

### Decision
- **`procs.start_id(pid)`** names a process in the boot clock's domain:
  - Linux: `linux:<boot id>:<start ticks>`, from `/proc/sys/kernel/random/boot_id` and `/proc/<pid>/stat` field 22.
    The tick count is an integer, fixed for the process's life.
  - Windows: `win:<creation time in 100 ns since 1601>`.

  It is compared for equality only, so no tolerance is involved. An id from another platform or another boot, an id of
  another process, and a malformed id never match. `started_at` stays, for display and for records written before.
- **The comm is arbitrary bytes:** a file name cut to 15 bytes, or whatever `prctl(PR_SET_NAME)` set.
  So every read of `/proc/<pid>/stat` and `/proc/<pid>/status` in `src` is a bytes read, decoded as latin-1, which
  never fails. None is in text mode, which would turn a `\r` into a newline. The status file is split on `\n` alone.
  The kernel escapes only a newline and a backslash in its `Name:` line.
  - A comm that is not valid UTF-8 still has a start id, and its host pid and parent can still be read.
  - A comm that holds a carriage return, or another line break that `str.splitlines` knows, cannot add a line of its
    own, such as a forged `PPid:` (review of #250, M1 and M2).
  - A unit test scans `src` and enforces the rule. Only `/proc/stat` and `/proc/sys/kernel/random/boot_id` may be
    read as text: they are kernel ASCII and hold no comm.
- **`procs.same_process(pid, started_by)`** keeps its two arguments.
  - `started_by` is the record's start id (a string, compared exactly) or, in a record from before start ids, its epoch
    time (a number, the old check).
  - `procs.recorded(start, started)` picks between them for a reader.
  - A start id that is not a string names no process, so it fails closed.
- **Every record that names a process carries a start id beside its pid, from every writer.** Every reader that judges
  the process prefers it.

  | record | where | field | writer | reader |
  |---|---|---|---|---|
  | validation executor | control state, `work.<id>.integration.<slot>.executor` | `start_id` | `validation_ops` (the run's start) | `executor_alive` |
  | custody worker | control state, `invocations.<id>.worker` | `start_id` | `custody_ops.register` | `queue_ops._lost_worker` |
  | operator locator | `local/operator/endpoint.json` | `start_id` | `operator_endpoint` | `operator_client.same_process`, `status` |
  | broker liveness | `local/lead/broker.json` | `start_id` | `broker_liveness.Beat` | `judge` (through the locator's check), `Beat.close` |
  | dashboard endpoint | `local/dashboard/server.json` | `start_id` | `dashboard.service` | `locate` |
  | run record | `run.json` | `supervisor_start_id`, `harness_start_ids` | the supervisor | `runlog.end_supervisor`, the harness test helpers |

  A control-state record omits the field when its writer cannot read the start id; a local record holds `null`. The
  reader then falls back to the record's start time. The broker record's reader refuses a `start_id` that is neither a string nor
  `null`, as it refuses every malformed field.
- **The schema stays `aew/control/v2`, additive.**
  - The custody worker's `start_id` is an optional string, so a state from before it still loads.
  - An engine from before it refuses a state that carries one, because the worker object is closed. That is the fail
    closed of ADR-0004's schema rule and ADR-0012.
  - A test pins both, against the vendored schema of main before this change
    (`tests/fixtures/baseline/control.schema.0f59742.json`).
  - The executor's object is not schema-closed. None of the local records has a schema file: their readers ignore an
    unknown key, so an older reader reads the record by its start time.

### Residuals (documented, not closed)
- **Records written before this change** keep the start-time check, with its misjudgement after a step, until the
  process that wrote them exits. The custody worker's custodian is the longest-lived such record.
- **An unreadable start id** (no `/proc`, an unreadable boot id) leaves the record its writer makes on the start-time
  check. A *reader* that cannot read the id of a record that holds one (an unreadable boot id, or an unreadable
  `/proc/<pid>/stat`) judges the process gone. There is no fallback there: that is the same direction as before this
  change, where an unreadable start time also read as gone (review of #250, N2).
- **A time namespace** (Linux 5.6 and later) shows a process's start ticks relative to its own boot offset. AEW creates
  none (bubblewrap does not), and every writer and reader here is an AEW process on the host.
- **The local records stay forgeable by the same uid**, as before: they only notify or locate, and grant nothing.

### Tests
- **`tests/unit/test_process_identity.py`:**
  - a simulated `btime` step (`/proc/stat` patched where it is read) moves `started_at` but never `start_id`, and
    keeps `same_process` true;
  - a reused pid, another boot, another platform's id and malformed ids read as another process;
  - on Linux, a child whose comm is not valid UTF-8 has the start id that a byte-level parse gives. One whose comm
    also spells a `PPid:` line, after a record separator or a carriage return, still has its host pid read, and still
    descends from its real parent;
  - the guard: no read of a `/proc` file in `src` is a text read but the two allowed files. It follows strings,
    f-strings, `Path(...)` with parts, `/` on a path, a name bound to a path, and a script held in a string. Planted
    reads check it both ways;
  - a record from before start ids keeps its check;
  - one test per reader (executor, worker, locator, broker and its close, dashboard, teardown), with the clock stepped
    after the record was written. The step is simulated on Linux in `btime`, and elsewhere in each epoch start time.
- **`tests/integration/test_process_identity_records.py`:**
  - the custody worker's start id, with the schema tests;
  - a state from before start ids that loads and is judged by its start time, while the run its worker executes
    records its executor's start id;
  - the dashboard's endpoint file;
  - the run record's supervisor and harness processes.

## Amendment 2026-10-23 — the masks: `/run`, the display, the terminal and the sockets (STG-05 CS-2)

This amends the M4-B amendment's sandbox (2026-10-03) and its self-test. It builds CS-2's outcomes 1 to 4 and 6.
Outcome 7, a fingerprint is a read (D-CS2-1), is ADR-0002's amendment of the same date. Outcome 5, the
nested-namespace measurement, is the operator's and is not part of this amendment.

### `/run` is masked whole (CB-03, ruling R-1; `layout.host_masks`)
- **The mask:** every layout, eval's included, puts an empty tmpfs on `/run` at its depth in the one bind order
  (`layout.order`). `/var/run` is masked the same way where it is a directory of its own rather than the usual link
  to `/run`, and so is the GSS-API credential proxy's directory, `/var/lib/gssproxy`, where there is one (designer
  ruling D-CS2-6, `layout.GSSPROXY`): nothing inside needs it. Once what the layout binds back into a mask is there,
  the mask is remounted read-only, so nothing can be made in it.
- **Why whole:** a read-only mount refuses writes, not a socket's `connect`. `/run` holds the host's service sockets:
  G3's, the work-item fact issuer's, the session and system buses, and the operator's runtime directory. A list of
  them would miss the next one.
- **The one host-derived exception** (the operator, 2026-10-24, on CS-2's plan): on a systemd-resolved host,
  `/etc/resolv.conf` links into `/run`. Its first path under `/run` is bound back read-only by that name, with the
  reason "name resolution until CS-3", when the link chain ends at a regular file. The chain is followed as the kernel
  follows it, at most 40 links. Without that file, a contained harness could not resolve its provider's name until
  CS-3 gives it a network namespace of its own. `Layout.run_exceptions` holds each exception with its reason.
- **A project under `/run` is bound back** (operator ruling 2026-10-23: a project under /run is bound back, on five
  conditions, R-1). A project on removable media (`/run/media/<user>/...`) stays usable with its workspace: their binds
  land inside the mask by depth. The conditions, each with its test:
  1. only the layout's own binds of the project and the run's workspace come back, at their resolved real paths, with
     the modes the same layout gives them anywhere else; never an ancestor such as `/run/media/<user>`;
  2. nothing comes back that is a mask itself or lies under `aew-*` (G3's `aew-g3`, the fact issuer's `aew-wis`, any
     later AEW service's), `user`, `dbus` or `systemd` below it (`layout.RUN_PROTECTED`, one tuple: adding to it only
     tightens);
  3. an operator's writable root under `/run`, or containing it, stays refused (the Lead's ruling Q6), like any other
     protected location (`CONTAINMENT_UNAVAILABLE`, naming "the host's runtime directory, masked whole");
  4. the socket inventory runs in the finished sandbox, after every bind-back, so a failing socket inside the project
     tree still fails the launch;
  5. row 2 allows exactly what the layout put there (`Layout.bind_backs`).

  `for_run` refuses a layout that breaks 1 or 2 (`CONTAINMENT_UNAVAILABLE`, reasons `run_bind_back_protected`,
  `run_bind_back_outside_project`, `run_bind_back_not_real`). The label's `layout.bound_back` lists every path inside a
  mask with why: the exceptions with theirs, a project's binds with the ruling.
- **A secret mask in a tree that is masked whole** (`/tmp`, `/run`, a runs mask) is not emitted when the secret is
  hidden with its tree: making its path there would fail on the read-only mask. When it lies in one of the layout's
  binds into that tree (a project under `/run` or `/tmp`, its workspace, the run's own directories), it is the host's
  file there, and its mask is emitted after every bind, before the tree's read-only remount (review of #244, m1).

### The display's credentials and variables (CB-04)
- **Files:** `~/.Xauthority`, `~/.ICEauthority` and the file `XAUTHORITY` names are masked by type, like every
  secret. So are git's credential cache (`~/.cache/git/credential`, `$XDG_CACHE_HOME/git/credential`,
  `~/.git-credential-cache`) and its store helper's file (`~/.config/git/credentials`,
  `$XDG_CONFIG_HOME/git/credentials`).
- **Variables:** `bwrap_argv` unsets `DISPLAY`, `WAYLAND_DISPLAY`, `XAUTHORITY`, `DBUS_SESSION_BUS_ADDRESS` and
  `SSH_AUTH_SOCK` (`layout.DISPLAY_ENV`) in every contained process, whatever its launcher passed. No contained
  environment builder passes one, and `POSIX_KEEP` and `DISPLAY_ENV` are disjoint.

### No controlling terminal (CB-05, ruling R-7)
- **Every contained process starts in a new session** (`--new-session`), so it has no controlling terminal.
- **Why that is enough:** the kernel refuses `TIOCSTI` on a terminal that is not the caller's controlling terminal,
  to a caller without `CAP_SYS_ADMIN` in the initial user namespace. With no controlling terminal, no descriptor a
  contained process holds accepts it. Row 4 checks the property; nothing pushes input anywhere.
- bubblewrap's own processes stay in the caller's process group, so ending the run's process group still ends the
  sandbox.

### The socket inventory (CB-03; designer rulings D-CS2-2 to D-CS2-5; `aew.harness.containment.sockets`)
- **What it finds:** a socket nobody listed. The masks close the doors somebody did list (`/run` whole, the secret
  directories).
- **Where it comes from:** the kernel's table of Unix sockets (`/proc/net/unix`), read by the launcher in its network
  namespace. It holds every bound socket, by path or by abstract name, at a cost of O(sockets + mounts), with no walk
  of the filesystem and no budget.
- **The control:** before reading the table, the launcher binds a listener of its own. A table that does not list it
  is not this namespace's.
- **Reachable** means the same socket file, by device and inode, is at a path inside the sandbox: its own path, or
  any other the sandbox's mount table exposes it at (a bind of it or of a parent, found through
  `/proc/self/mountinfo`). A same-named socket of the sandbox's own, or a mask in its place, does not count. Each
  socket is looked for at its listed path and at that path with its directory resolved on the host (review of #244).
- **The kernel's tables are read as the kernel writes them** (review of #244): as bytes, records split at the newline
  only, mount-table fields at single spaces, octal escapes honoured. A record that does not match the table's fixed
  format fails row 2 closed, with its reason; none is dropped.
- **A socket linked into place:** it is bound under a temporary name and linked to its final name in the same
  directory, as OpenSSH's ControlMaster does (mux.c's `muxserver_listen`). The table lists it under the name that is
  gone, so every socket file in that directory is checked, each taking the worse of its own class and the listed
  one's.
- **An abstract socket** has no file. It is listed with its class under the network label, `shared`, until CS-3 gives
  runs their own network namespace. `required` claims nothing about it, and `aew doctor` shows a failing-class one
  as WARN, naming its class and that CS-3 closes it (D-CS2-5).
- **What it cannot see is named on the label** (D-CS2-3; `sockets.NOT_COVERED`, widened by the review of #244):
  - a socket bound in another network namespace;
  - one bound in another mount namespace, whose path does not resolve here (`unresolved`), or names a different
    socket here;
  - one bound by a relative path (`relative`: reported and counted, not failed);
  - one moved or linked into another directory;
  - one bound after the launch's check: the inventory is as of the launch;
  - one bound through a file descriptor's path (`/proc/self/fd/<n>/...`), which shows as unresolved or unchecked;
  - one whose path the launcher could not check (`unchecked`: recorded, not failed).

  The label also lists the sockets checked at their own paths only, as no mount of their filesystem is known
  (`untranslated`), and the launching user's processes that `/proc` does not let it read (`unreadable_processes`).

  These are accepted for two reasons. The primary controls for the failing classes do not depend on the inventory:
  `/run` masked whole, the private `/tmp`, CS-3's network namespace. And under the threat model, a host process, not
  an agent, would have to put such a socket into an exposed tree.
- **Before this ruling** the probe walked every mount within a 15 s budget. On CI's runners it never finished
  (240k–784k entries at 15 s), and every contained launch failed closed. On the Rocky 8 VM a full walk took 0.6 s for
  542k entries, warm. The walk is a data point now, not a mechanism (D-CS2-4).
- **The classes,** one owner (`sockets.classify`, by name; `sockets.by_executable`, by the listening process's
  executable when that process is the launching user's own), first match wins, the worse of the two kept:
  - **own:** under the run's own bridge directory;
  - **failing:** the display, G3 (`aew-g3*`), any other AEW service (`aew-*`; AEW's runtime directories count only
    directly in a runtime root: `/run`, `/var/run`, `/tmp` or the launching `XDG_RUNTIME_DIR`, so a checkout or a
    reviewer's tree named `aew-*` is no service's), a credential (ssh-agent, gpg-agent,
    git's credential cache, the keyring, the session bus, and the agents' common names and executables: `agent.sock`,
    `*-agent.sock`, `*-agent.socket`, gcr's `ssh`, `1password`, `bitwarden`, `keepassxc`; D-CS2-6) or an escape route.
    An escape route is something that runs commands as the operator, or as root, outside the sandbox: the system bus,
    tmux, screen, an editor server, a container engine, the user service manager (the Lead's rulings on CS-2's plan);
  - **a credential by its holder** (designer ruling D-CS2-6): a listening socket the launching user owns, whose holder
    the launcher cannot identify (no process of the launching user's that it can read holds it), is a credential.
    Where it is reachable the launch fails, and row 2 (and so `aew doctor`) names the socket and the remedy: stop
    that process, move its socket under a masked path, or run in `allow_weaker`. The label lists the launching user's
    processes it could not read;
  - **named by the launching environment:** a socket its `DISPLAY`, `WAYLAND_DISPLAY`, `SSH_AUTH_SOCK` or
    `DBUS_SESSION_BUS_ADDRESS` names is failing wherever it lives. `establish` takes that environment (by default the
    process's own);
  - **reported:** anything else, such as a site's ordinary services (SSSD's pipes among them, which agents need for
    name resolution). It is listed on the label, never refused.

  **The classes are a known list, never complete** (D-CS2-6). A socket that no name and no executable here marks, and
  whose holder is identified, is reported. The primary controls do not depend on the list: `/run` and the other host
  masks, the private `/tmp`, the secret masks, and CS-3's network namespace.

### The self-test records CB-12's rows 2 to 5 on the label (`probe.self_test`)
- **Row 2, `/run` and the sockets:** each host mask is a read-only tmpfs inside, holding only what the layout put
  there, and `/var/run` leads into a mask. The masks checked are the host's runtime trees as they are now
  (`layout.host_masks`), not only the layout's, so a layout that lost its `/run` mask fails. No path socket of a
  failing class is reachable. The row fails closed on a table that cannot be read or parsed, a table without the
  control, and a check inside that errors. Each mask's listing is the probe's own (`masked_tree`), tested on a
  synthetic tree (review of #244, m2). The probe takes its spec on stdin, since one argument is capped at 128 KiB
  (n2).
- **Row 3, the display:** no display credential reads as anything but absent, empty or unreadable. No `DISPLAY_ENV`
  variable reaches the probe, which is handed each of them set, so a sandbox that does not unset them fails.
- **Row 4, the terminal:** read on the started process itself, `tty_nr` is 0 in its own `/proc/self/stat` and
  `/dev/tty` gives `ENXIO`. Whether it leads its session is recorded, not required: under `--new-session` the
  session's leader is bubblewrap's own process in the sandbox (seen on CI's runners and the Rocky 8 VM).
- **Row 5, the binds and masks:** the M4-B checks. A runs mask that is missing inside now fails too.
- **Recorded pass or fail:** each row has its name, `ok`, its reason and its facts. Row 2's facts are:
  - the reachable sockets with their classes and inside paths;
  - the table's size and how many path sockets were checked;
  - the abstract sockets;
  - the residuals;
  - how long the host and the probe took.

  `required` refuses a failing self-test, with the rows in
  the refusal's details. `allow_weaker` launches the run labelled `workdir_separation_only`, with the rows on its
  label. Row 1, the network, is CS-3's.

### The reader git gap is closed
The CS-1 amendment above pins the reader git gap (`READER_GIT_GAP`) and says CS-2 builds D-CS2-1. CS-2 has built it:
a non-writer computes a fingerprint without writing any object, inside a sandbox and outside one (ADR-0002's
amendment of 2026-10-23). `READER_GIT_GAP` is empty, and the worker-surface tests check the real object store by
digest on both faces. That paragraph stays as the record of CS-1.

### What this does not claim
- **Row 2 certifies the sandbox as the run starts.** The inventory is taken by the launch self-test, so a socket
  bound after it is not in it.
- **The residuals above** are named, not closed.
- **Known limits, each host-only** (stated, not fixed, under the operator's ruling of 2026-10-24 on host-only nits;
  deferred as register row F52):
  - **The GSS-API proxy:** its directory is masked where the proxy keeps it by default. Not covered: a proxy set up
    another way. Precondition: root's own configuration of the host. Worst case: its socket is reachable from inside
    and judged by the socket classes alone.
  - **Socket names and the launcher's locale:** not covered: a socket whose name the launcher's locale encodes
    differently. Precondition: the operator's own locale. Worst case: that socket is reachable from inside, and the
    label may not name it.
  - **Shared listening sockets:** not covered: a listening socket shared by several of the launching user's
    processes. Precondition: the operator's own processes. Worst case: that socket is reachable from inside and judged
    as only one of those processes would mark it.
  - **A socket linked into place:** not covered: one whose temporary name another socket in the same directory now
    has. Precondition: the operator's own processes, or root's. Worst case: the launch is refused, naming the other
    socket; where root made that other socket, the linked one is reachable from inside and judged by the socket
    classes alone.
- The claim is still filesystem integrity with the network shared. CS-3 gives runs their own network namespace.

### Tests
- **`tests/unit/test_containment_layout.py`:**
  - the `/run` mask (and `/var/run`, where it is a directory of its own, and `/var/lib/gssproxy`, where it exists)
    after the root bind, in the bind order, and remounted read-only;
  - each exception bound back read-only after the mask, and described with its reason;
  - the `resolv.conf` exception as the first path under `/run` on its chain (POSIX);
  - a project under a masked prefix stays visible, and a writable one writable;
  - the project bind-back's conditions 1 and 2: for an implementer and a reviewer, only the project's and the
    workspace's own binds come back, at real paths, in the order the same layout has without the mask; a bind of
    something else on the media refused; a project under each protected name refused, and one at the mask itself; a
    project named through a symlink bound back at its real path, and a link path refused (POSIX);
  - a mask under a masked tree dropped, and one inside a bind into it emitted before the tree's remount;
  - an operator root under or containing `/run` refused;
  - a layout's JSON round trip giving the same argv;
  - the display files and the `XAUTHORITY` file masked by type;
  - every argv unsetting the display variables and starting a new session;
  - no contained environment builder passing a display variable.
- **`tests/unit/test_containment_sockets.py`**, all on synthetic inputs:
  - each failing class on planted names and nothing else;
  - an unlisted socket reported;
  - the launching environment's sockets, the run's own bridge, and AEW's runtime directories only in a runtime root;
  - the table's and the mount table's parsing as the kernel writes them, and a table or a record that does not
    parse;
  - the abstract names and the executable classes;
  - the inventory's candidates, classes and control;
  - the same-directory rule;
  - the resolved spelling of each listed path, with its class;
  - a listening socket of the launching user's whose holder cannot be identified, and the launching user's
    processes that cannot be read (on synthetic `/proc` entries);
  - the residuals recorded;
  - each socket's filesystem and its path within it.
- **`tests/unit/test_containment_probe.py`**, on synthetic probe output:
  - each row's judgement, passing and failing closed, row 4 included;
  - row 2's fail-closed cases (an unreadable table, one that does not parse, a missing control, a check inside that
    errors);
  - row 2's residuals, its abstract fact, and what the host could not check or read;
  - the probe's own matching on synthetic mount tables: every mount of the socket's filesystem, each spelling, and
    the same file by device and inode only;
  - the probe's own reading of its mount table, and its listing of a masked tree (POSIX);
  - a reachable socket whose holder cannot be identified failing row 2, with the remedy;
  - `aew doctor`'s WARN, and its naming of that socket and the remedy.

  **Proved on synthetic inputs only** (the operator's decision of 2026-10-24 on the review of #244: unit tests, with
  the existing integration tests unchanged): the masks inside a bind into a masked tree, the listing of a masked tree,
  the kernel tables' parsing, each socket's resolved spelling, the unidentified holder and the unreadable processes,
  and the gssproxy mask. The integration tests below exercise them on a real sandbox only as far as they already did.
- **`tests/integration/test_containment.py`** (Linux). Every planted item is synthetic, in the test's own 0700
  directory, and removed in a `finally`. The launching environment is built from scratch.
  - A passing run records rows 2 to 5, with the table's facts printed.
  - An ordinary planted socket is reported and the run starts. One the launching environment names as its agent
    fails the launch.
  - A socket on a read-only bind can still be connected to: the reason for the inventory.
  - A credential-cache socket in its default place is masked, and the run starts (serial).
  - The sandbox's `resolv.conf` resolves to a readable file whenever the host's does.
  - What a harness needs works under the mask: the user database, git status, Python's TLS module, and a name lookup
    wherever the host itself can resolve one.
  - The display's credentials and variables never reach a contained process, and no credential reaches git.
  - Each row fails closed when its protection is taken out of the self-test's argv: `/run`'s mask, a display file's
    mask, the variables' unsetting, a runs mask.
  - A launcher that has a controlling terminal (a pseudo-terminal of the test's own) starts the probe, which has none;
    without `--new-session` it inherits the launcher's, and row 4 fails.
  - A project under a stand-in for `/run`, masked as `/run` is: bound back with its workspace, recorded with the
    ruling, row 2 holding exactly them, the media's other directories absent inside (condition 5), and row 2 failing
    with the mask taken out; a socket inside the project tree that the launching environment names as its agent fails
    the launch (condition 4).

## Amendment 2026-10-24 — a run's own network, the shim and the provider relay (STG-05 CS-3b; F28)

This builds F28 (the network containment design v0.2, §3.1 to §3.6 and §3.8) for workers on Linux, wiring in CS-3a's
egress proxy (#246). It amends the M4-B amendment (2026-10-03), whose runs shared the host's network, and the CS-2
amendment above, whose abstract-socket facts and resolver exception assumed a shared network. F28's own amendment of
the same date (its §7) records the egress policies, ruling R-6, and where the relay puts the credential.

### The network modes (F28 §3.1; `layout`, `netns`)
- **The mode** is the execution policy's `containment.network.mode`, else `proxy_only` on Linux (F28 decision 1).
  `isolated` has no route out; `shared` is the host's network, an explicit weaker choice, labelled for what it is;
  Windows is `not_provided`. A layout of a private mode gets `--unshare-net`: a network namespace of its own, without
  the host's loopback ports or abstract sockets.
- **The label's `network`** is an object: `mode`, `provider_relay` (`configured` or `none`), with the relay its
  `provider_upstream` (and `provider_upstream_proxy` when the operator's proxy carries it), with egress its
  `egress_allow` and `limits` (R-6's stated residual), and at the run's end `decisions`: what the relay and the egress
  proxy decided, counted by outcome. Every label has `provider_relay`: a contained run whose network started no relay
  (integration validation's) says `none`. A record from before CS-3b holds the mode as a string, which `normalize`
  reads as `{mode, provider_relay: none}`.
- **The run's network directory** (`netns.private_dir`): a fresh 0700 directory under the host's `/tmp`, bound
  read-only, with its `shim/` subdirectory bound writable (the one place the sandbox may bind a socket). The relay and
  the egress proxy listen there, 0600. The run's process tree owns it: killing or closing the tree closes both and
  removes the directory. A refused launch removes it, and an integration validation removes it at once, since its
  checks never use the run's routes out.
- **Name resolution:** a private network resolves no names, and the harness needs none: its routes out are the relay
  and the egress proxy, which resolve on the host. CS-2's `/run` exception for `resolv.conf` stays, read and unused
  there; its reason now says so.

### The shim (F28 §3.2; `containment/shim.py`)
- **What it is:** standard library only, its file's text run with `python -I -c` as the self-test's probe is, as the
  harness's parent in the one sandbox (each bubblewrap call has a namespace of its own). It never execs away, passes
  its standard streams to the harness, forwards `SIGTERM`, `SIGINT` and `SIGHUP`, and exits with the harness's status.
  It is not an AEW entry point (`aew.process_kind`): it imports nothing of AEW and never opens the store, so it has no
  `__main__` block and declares nothing.
- **Its legs:** in, `shim/server.sock` to the harness server's `127.0.0.1:4100` (the supervisor reaches the server
  this way); out, `127.0.0.1:4101` to `relay.sock` and, with egress, `127.0.0.1:4102` to `egress.sock`. Bytes move
  both ways as they come, with half-closes passed on. A leg it cannot set up ends it before the harness starts (exit
  70, saying so). It holds no credential and no authority.

### The provider relay (F28 §3.3; `containment/relay.py`)
- **The credential:** each variable the policy's `provider_env` names (proxy variables aside) is a random sentinel
  inside; only the relay knows what it stands for. The relay swaps a sentinel only in a credential header
  (`Authorization`, `X-Api-Key`, `Api-Key`, `X-Goog-Api-Key`); a credential header without one passes as it came.
  Closing the relay forgets the credentials.
- **The upstream** is fixed: the policy's `containment.network.upstreams.<provider>`, else AEW's table of known
  providers (`netns.UPSTREAMS`: `openai`, and `opencode`, the free models). A provider with neither refuses the launch
  (`CONTAINMENT_UNAVAILABLE`, reason `no_upstream`), saying what to set. The operator's HTTP proxy, when the provider's
  variables name one, carries the relay's `CONNECT` to it, unless `NO_PROXY` covers it.
- **Requests:** origin-form only (a request cannot name a host: 400 `not_origin_form`), one per connection
  (`Connection: close` both ways), hop-by-hop headers dropped, `Expect: 100-continue` answered by the relay, a protocol
  upgrade refused (501, naming the http transport AEW sets), a body framed by length or chunks, TLS by the system's
  default verifying context. Each refusal is a fixed answer with a reason code in `X-AEW-Refusal` that says what to do.
- **Streaming:** the response goes back as it comes, one thread per connection, reading the upstream only once the
  client has taken the last chunk (backpressure). A client that goes away closes the upstream connection at once. It
  is counted `cancelled` only when it went before the response's end, by its `Content-Length` or its last chunk:
  OpenCode closes as soon as it has a whole answer, before the upstream's own close arrives (seen in the live lane
  below), and that is no cancelled turn. A body with neither length nor chunks ends only when the upstream closes.

### Egress (F28 §3.4; CS-3a's proxy)
- **When:** under `proxy_only`, when the allowlist names something: the policy's `containment.network.egress_allow`
  and what the harness itself needs (`Harness.EGRESS`; OpenCode's `models.opencode.ai:443`, its catalog). Credentialless,
  `CONNECT` only, R-6 under every policy.
- **Inside:** only `HTTPS_PROXY` (both cases) names it, at `127.0.0.1:4102`; the operator's proxy variables are
  removed, `HTTP_PROXY` stays unset (the provider's `baseURL` is plain HTTP to loopback), and `NO_PROXY` lists loopback.

### OpenCode (F28 §3.5; `opencode/adapter.py`, `projection.relayed`, `client.py`)
- **The projection** points the pinned model at the relay: `providers.<p>.settings` gets `baseURL`
  `http://127.0.0.1:4101<the upstream's path>` and `transport: http` (2.0.18 tries a WebSocket upgrade first
  otherwise), and `providers.<p>.models.<m>.settings.baseURL` the same, since a catalog model with a base URL of its
  own ignores the provider's (all the free `opencode/*` ones; measured on the Rocky VM, 2026-10-24).
- **A model named only by that projection** is listed by 2.0.18 even when its catalog does not offer it, made up from
  the provider's defaults (no family, no release time, its name its id; measured). Such an entry counts as absent, so
  a pinned model the catalog does not offer is still refused at launch, saying why it is listed.
- **The server** listens on `127.0.0.1:4100` inside (`serve --port`, whose announcement must match), and the
  supervisor's client, event stream and meter reach it over the shim's socket file.
- **The agent is told** (the system text, from the run's label): a run on a network of its own gets one line naming
  its mode and what it reaches (the provider, and through `HTTPS_PROXY` the allowlist's hosts), that every other
  connection is refused by design, and to name in its report the `host:port` it needed, so the Lead can ask the
  operator to add it to `containment.network.egress_allow` (#257's review, F3). The upstream and the stated limits are
  not in it.
- **Row 6 before the start:** the server's environment and configuration are checked for every provider variable's
  value; one found refuses the launch (`HARNESS_INCOMPATIBLE`, reason `provider_secret_in_sandbox`), naming the
  variable, never the value. The files a contained run can read hold no key: the provider configuration locations and
  the secret files are masked (CS-1, CS-2).

### Checks (F28 §3.8; `layout.for_check`, `policy/checks.py`)
- A check runs `isolated` unless its definition says `network: shared` and its run's mode is `shared`; it never gets
  the run's relay or egress proxy. Its log says when it ran with no network, and how to ask for one.
- The effective mode is recorded with its evidence (`method.network`), on the run's checks and on integration
  validation's. A definition's digest includes `network` only when it is set, so existing digests are unchanged.

### The self-test's row 1 (F28 §3.6; `probe.self_test`)
- **Under the run's shim, in its namespace:** the probe runs as the harness will, with a probe relay (a credential of
  the probe's own, to an upstream the host holds), an egress proxy with the run's allowlist, and a loopback port and an
  abstract socket the host holds. Row 1 passes only when the namespace is not the launcher's or PID 1's (where
  readable); a direct TCP, UDP and IPv6 connection out fails for want of a route; the host's loopback port and abstract
  socket are unreachable, and the abstract one is not listed inside; only the shim's ports listen inside; the host
  reaches the probe through the shim's socket file; a request through the relay reaches its upstream with the
  sentinel swapped; the egress proxy refuses a destination on no allowlist; and the bridge answers by its path.
- **Row 2 in a private network:** an abstract socket the host holds that is listed inside fails it; on the shared
  network the abstract sockets stay facts, and `aew doctor` warns of a failing class, naming the default mode as what
  closes it.
- `required` refuses a launch whose row 1 fails, and `allow_weaker` starts it labelled `workdir_separation_only`, with
  the rows. On the shared network, row 1 records the mode and claims nothing.

### The live lane (F28 decision 6, NET-19; the Rocky 8 VM, 2026-10-24)
- **The production path:** `tests/live/test_opencode_model_live.py`'s lifecycle on OpenCode 2.0.18 with
  `openai/gpt-5.6-luna#medium` and a real OpenAI key, which the supervisor held. Its implementer, reviewer and verifier
  runs, each `proxy_only` with the relay's upstream `https://api.openai.com/v1`, ended with evidence, with the pinned
  model effective, rows 1 to 5 passing and a clean credential scan. The relay carried 14 streamed model requests (7, 4,
  3). The live test's own checks found the key in no file the runs left, and no file the lane left held its value.
- **The relay against the real upstream** (a real 2.0.18 server on the same model, the relay in front of it, a script
  standing in for the supervisor): a 136 KB streamed answer arrived whole, its first bytes after 0.40 s and the rest
  after 1.76 s; with its client slowed to about 20 KB/s, the same answer arrived whole over 7.8 s, with no timeout and
  nothing lost. An answer interrupted mid-stream (`POST /api/session/<id>/interrupt`, after 59 KB) closed the upstream
  connection and was counted `cancelled` 0.12 s later, with no socket left open. The slow client shows a stream
  delivered intact to a slow reader; the answer fits in the sockets' buffers, so it does not show the upstream held
  back, which the relay does by construction (it reads the upstream only once the client has taken the last chunk).
- **The upstream's IPv6 address** could not be tried: the VM has no IPv6 route.

- **The live lane's counts predate a fix:** at that head the relay counted `cancelled` whenever the client closed
  first, so most finished steps were counted too (6 of run 1's 7). The count now waits for the response's end, as
  the streaming bullet above says.

### ripgrep (the designer's rulings RG-1 and RG-4, and the operator's decision, 2026-10-24)
- OpenCode's glob and grep tools run ripgrep. With none on the `PATH`, 2.0.18 downloads it from github.com, which a
  `proxy_only` run's egress proxy refuses (github.com is on no allowlist), so in the live lane those tools failed in
  two of the three runs, which still ended with evidence. The Rocky VM has no ripgrep.
- **`aew doctor`'s `ripgrep` line (RG-1):** the containment line's own sandbox looks for `rg` on the launching
  environment's `PATH`, from inside, so the line says what a contained run sees, not only what the host has. It
  passes naming where, or warns naming the tools that fail (glob, grep), the cause (the harness cannot download
  ripgrep on a network of its own or offline) and the fix: CAP-1, and until then an `rg` runs can see, naming a host
  `rg` the sandbox cannot see when there is one.
- **No egress widening** for the download (RG-4): the workers' allowlist stays as adopted.
- **The fix is CAP-1** (the operator's decision of 2026-10-24: AEW brings its own tools, through the capability
  register): the register's first slice puts a pinned ripgrep into every contained context, and its provider health
  replaces the `ripgrep` line. RG-2 (binding a host `rg` the sandbox cannot see) is withdrawn for it.

### What this does not claim
- **ripgrep where a run finds none:** AEW bringing ripgrep itself is CAP-1's, right after this. Until then a host
  without ripgrep on a `PATH` runs can see has glob and grep failing in contained runs, and `aew doctor` says so.
- **A card's web capability** (the researcher's `documentation_lookup`, which allows `webfetch` and `websearch`)
  reaches nothing under `proxy_only` unless the policy's `egress_allow` names the hosts: the egress proxy refuses
  every other fetch (403). The system text tells the agent so, and how to ask for a host.
- **The Lead's harness** on `proxy_only` (F28 decision 2, with the any-public egress policy) is CS-4's. Until then
  only worker runs have a network of their own.
- **A check's route out** through the run's egress proxy (`proxy_only` for a check) is not built.
- **R-6's residual** is stated on the label; its check is register row F28.1, deferred.
- **Windows** stays `not_provided`.

### Tests
- `tests/unit/test_provider_relay.py`: the relay over socketpairs, nothing contacted: the sentinel swapped only in
  credential headers; a credential header without one unchanged; hop-by-hop headers dropped and `Connection: close`
  both ways; absolute-form, `CONNECT` and a bad version refused with nothing connected; an upgrade refused; a chunked
  body relayed whole; `Expect` answered and not forwarded; the response streamed; a client going away closing the
  upstream, counted `cancelled` only before the response's end (by length, by last chunk, and a chunked body followed
  however it is split); an unreachable upstream; the operator's proxy's `CONNECT` and its refusal; the label.
- `tests/unit/test_containment_netns.py`: the mode, a check's network, `--unshare-net` and the binds, the upstream and
  its refusal, the allowlist, the operator's proxy, the harness's environment (sentinels, `HTTPS_PROXY` only), the
  label and the counts, a refused start leaving no directory, and the shim's spec.
- `tests/unit/test_containment_probe.py`: row 1 passing, and failing closed on each protection taken out (the
  namespace, each direct connection, the host's port and abstract socket, an extra listener, the relay, the egress
  proxy, the bridge, the server path); row 2's abstract sockets in a private network.
- `tests/integration/test_network_shim.py` (Linux): each leg both ways with half-closes; a leg that cannot be set up
  stopping the harness; a termination reaching the harness.
- `tests/integration/test_containment.py` (Linux): a passing run records rows 1 to 5, with outcome 4's facts; row 1
  failing closed with `--unshare-net` taken out; a shared run's label and row 1; a check's network.
- `tests/integration/test_opencode_adapter.py`: on Linux, the projection's relay settings, the sentinel, the egress
  variables, the label and its counts, the network directory removed at the end; the relay giving the provider each
  key in its sentinel's place (register V1's rotation); a model the catalog lists only from AEW's configuration
  refused; a key that would reach the sandbox another way refusing the launch.
- `tests/integration/test_validation_checks.py` (Linux): a contained check's evidence records `network: isolated`.
- `tests/unit/test_containment_layout.py`, and `test_containment.py`'s `establish` (Linux, the label integration
  validation records): a contained run's label without a relay says `provider_relay: none`.
- `tests/unit/test_opencode_units.py`: the system text's network line for `proxy_only` and `isolated`, without the
  upstream or the limits, and none on the host's network; `test_opencode_adapter.py` on Linux: the line from the run's
  label reaching the server's configuration.
- `tests/unit/test_containment_probe.py`: `aew doctor`'s `ripgrep` line from the containment line's sandbox, passing
  and warning, absent when that sandbox failed; its wording both ways. `tests/integration/test_containment.py`
  (Linux): the probe finding `rg` on a directory the sandbox sees, and not finding one the sandbox masks.
