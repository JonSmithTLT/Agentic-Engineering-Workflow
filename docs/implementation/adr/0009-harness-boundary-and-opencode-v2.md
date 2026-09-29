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

  A possibly-live run needs `--replace` (`RUN_LIVE`). Its credential dies in the relaunch commit either way, and a best-effort stop request is queued for its supervisor.
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
- When the held credential stops being the current Lead's, the broker closes its bridge.
- Parity with the invocation bridge is tested property by property (`harness-conformance.md` §3).
- With `--acquire`, the seat is released at exit when nothing is in flight; otherwise it stays held and the output says that continuing needs a terminal takeover. The credential is never printed.

**Why custody at all.** The spike showed that anything a harness shell prints is persisted twice, in the harness DB and in shell-output files. A harness permission layer is not secret isolation: an `edit` deny was bypassed through the shell.

**Post-run scan.** When a run ends, the supervisor scans the run directory for any credential string and records `credential_scan`.

**Residual risk (same-UID; documented, not closed).** A same-user process can read another process's memory on Windows (no integrity-level separation), so a deliberately adversarial agent could extract the credential from the supervisor. Custody closes inheritance, printing, transcripts and files, which are the accidental and persistent exposure paths. On Linux the supervisor is **non-dumpable** (`PR_SET_DUMPABLE=0`), so its `/proc/<pid>/{mem,environ}` are unreadable by the agent; a test checks this. This is the ADR-0005 same-UID threat model; it is unchanged.

### Process ownership (`src/aew/harness/procs.py`)
The supervisor owns the harness process tree independently of any harness lease.
- **Windows:** processes are created **suspended**, assigned to a job object with `KILL_ON_JOB_CLOSE`, then resumed, so no descendant can start outside the job, and the job disallows breakaway. `terminate` terminates the job; supervisor death closes the only job handle, and the OS kills the tree.
- **POSIX:** the tree is one process group. A **sentinel** outside the group kills the group when its pipe from the supervisor closes, including on `SIGKILL`. There is no `preexec_fn`, because the supervisor is multi-threaded. A descendant that calls `setsid` escapes (residual; authority is unaffected).
- **Liveness is a heartbeat file's mtime.** A pid is never trusted alone, because pids are reused. Tooling that must act on a pid checks the process start time against the run's custody time (`procs.same_process`).
- OpenCode's `--stdio` lease is used but not relied on.

### Containment label (`AEW-INV-ISO-001`; companion review B2)
What M3 provides is **workdir separation**: each run has its own workspace or observation, private harness state and a scratch directory. It provides **no OS-level filesystem containment**: an agent's shell runs as the operator and can read and write whatever the operator's account can.
- Every run record carries `containment: workdir_separation_only`, and `aew harness status` shows it.
- `aew doctor` reports `containment` as WARN with that explanation.
- Nothing in AEW claims more. Real containment is designed (`docs/design/execution-workspace-and-isolation-design-v0.1.md`) and gates real-repository dogfood and internal alpha (`future-work.md` §1, F2).

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
  - M3-D10: `resume` inside a Lead session said the session held no authority (`lead.whoami`, above).
- **Authored text travels as data** (companion review B1). A Lead writes goals, reasons and reports through `--fields FILE|-` or `--file`, with quoted heredocs, never interpolated into a shell command line. The Lead projection and the role preamble say so. Before this, a shell expanded `$1` inside a goal (`m3-dogfood-report.md` §7).
- **Known V2 risks:**
  - no stability policy;
  - `--stdio` is undocumented;
  - `/api/skill` is empty even when skills are exposed;
  - the job object can be escaped through out-of-tree spawners (authority is unaffected).

  These are recorded in the reviewer brief's attack list.
