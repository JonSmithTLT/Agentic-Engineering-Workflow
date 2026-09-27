# ADR-0009 — Harness boundary, runs, credential custody, and the OpenCode V2 adapter

- **Status:** Proposed (M3 step 0, 2026-09-27). The harness core was implemented in M3 step 2. Finalized at M3 closeout.
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
- `AEW_AGENT_ENDPOINT`, `AEW_AGENT_KEY`, `AEW_INVOCATION`, `AEW_RUN`, `AEW_WORK_UNIT`.

It carries no AEW credential, no provider secret, no harness password, and nothing else from the Lead's shell.

**Why the bridge key is acceptable.** It is a run-scoped capability that every agent process may use (they *are* the agent). It is not the AEW credential, grants only what the engine already authorizes, and is useless once the run ends, rotates or is revoked.

**The Lead is symmetric** (`src/aew/harness/lead_broker.py`, M3 step 3).
- `aew lead session [--acquire] -- <harness command>` holds the Lead credential in memory and serves a **Lead bridge**. `aew opencode` (step 4) is this command with an OpenCode TUI. The credential comes from `AEW_LEAD_TOKEN` in the operator's own shell (removed from the session's environment), or from an in-process `--acquire`.
- The Lead bridge is the same `BridgeServer` (JSON, key challenge, typed exact arguments, redaction, drain) with one operation, `lead.cli {argv, cwd, stdin}`. The CLI routes every Lead-authenticated command there when the session supplies no credential, and the broker runs the same command handler with the held credential.
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

### Pause points (tests)
`AEW_PAUSE=<point>=<file>` holds a process at a named point while the file exists (`faults.pause`, next to the `AEW_FAULT` crash points):
- `harness.bridge.before_engine`: a request past the bridge check, before the engine;
- `harness.watchdog.tick`: a supervisor slow to notice anything.

These make races deterministic: rotation during an in-flight submit, a check spanning a rotation, and a woken supervisor. They are no-ops unless the variable is set in the Lead's environment, which the agent's allowlisted environment never carries.

### OpenCode adapter (V2 2.0.18; M3 step 4)
- **Interface:** a private `opencode-cli serve --stdio --port 0 --hostname 127.0.0.1` per run, driven over HTTP+SSE from the Python standard library. This is the published contract that `@opencode/client` wraps.
- **Rejected alternatives:**
  - `@opencode/client` (needs a JS runtime; a "private generation target");
  - `@opencode/sdk` (embedded core in a JS process, skewed against the installed binary);
  - per-turn `run --format json` (no mid-run delivery, which couples against coordination; signal-only interrupt). `run` stays as the raw-OpenCode dogfood baseline.
- **Health:** at every launch, against that run's own server:
  - version;
  - a **capability probe** of the served `/openapi.json` (required operations and fields);
  - the pinned model and variant present in `/api/model` (polled; the catalog loads asynchronously).

  Any gap fails with `HARNESS_INCOMPATIBLE`.
- **Isolation per run:**
  - private XDG dirs;
  - `OPENCODE_CONFIG_CONTENT` (`snapshots:false`, compatibility plugin disabled, no MCP);
  - `OPENCODE_DISABLE_PROJECT_CONFIG=1`;
  - `OPENCODE_DISABLE_AUTOUPDATE=1`;
  - the shell environment replaced by `PUT /api/session/{id}/environment` with the agent allowlist;
  - `location.directory` = the invocation's recorded workspace as a long path.
- **Permissions:** every rule is allow or deny, never `ask`, because an `ask` blocks forever. The rules are:
  - `edit` for implementers only;
  - `subagent`, `question` and `external_directory` denied;
  - `skill` limited to the card's skills.

  Session-create permissions are appended last, so AEW sends the complete set there.
- **Completion:** execution terminal events, raced with `…/wait`, and reconciled from the message list. Effective model, tokens and cost come from assistant messages.

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
- **Known V2 risks:**
  - no stability policy;
  - `--stdio` is undocumented;
  - `/api/skill` is empty even when skills are exposed;
  - the job object can be escaped through out-of-tree spawners (authority is unaffected).

  These are recorded in the reviewer brief's attack list.
