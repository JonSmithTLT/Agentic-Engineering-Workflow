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
  - `aew harness send` is a queued prompt, delivered inside the current turn, never lost at its boundary. It refuses text containing a credential.
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

## Amendment 2026-10-09 — the post-run scan reads what the run left defensively, and says when it is incomplete

The post-run scan (above) runs as the operator over a directory the run's own user could write: its `harness/` even
under containment. It now walks that directory iteratively, never entering a link or, on Windows, another reparse point;
reads only regular files, never through a link and never blocking on a FIFO or device; and reads each in overlapping
chunks with its holes skipped, within one budget of bytes and entries per scan (`runlog.credential_scan`). Anything it
could not read is counted in `credential_scan.unscanned`, and then `clean` is false: **clean means scanned and clean.**
A scan that fails outright is recorded as not clean with its error, and the run's final record is still saved. Register
E33's streaming half closes with this (PR #139).

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
| `AEW_OPENCODE_BIN`, `AEW_OPENCODE_CATALOG_S`, `AEW_OPENCODE_CATALOG_SETTLE_S` | the supervisor (OpenCode adapter) | which OpenCode binary, catalog timeouts | as above |
| `AEW_LAUNCH_ACK_S`, `AEW_RUN_STALE_S` | the launching CLI; status readers | launch acknowledgement wait; supervisor staleness | timing only, and only in the reading process |
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
