# ADR-0009 — Harness boundary, runs, credential custody, and the OpenCode V2 adapter

- **Status:** Proposed (M3 step 0, 2026-09-27); finalized at M3 closeout.
- **Spec basis:**
  - WC §2 and §17: harness independence.
  - WC §5 and §15.4: bounded invocations from launch contracts; the Lead is reconstructible.
  - WC §8.2: success never inferred.
  - WC §16.12: adapters are never authorities.
  - WC invariant 21: no transport becomes an authority.
  - KC §3, §5.3 and invariant 22: runtime logs are local; secrets and transcripts are never knowledge.
  - ADR-0003, ADR-0005, ADR-0006.
- **Evidence:** `m3-opencode-v2-rebaseline.md` and `eval/m3/spike/`.
- **Nature:** an implementation of frozen semantics. It adds no new authority, no new state machine and no new knowledge store.

## Decision

### Boundary
- AEW owns:
  - invocation identity;
  - pins: card, **execution profile** (ADR-0010), pack sha, workspace/observation, expected kind;
  - credentials and **their custody**;
  - run identities;
  - evidence, gates and state.
- The harness owns the model loop, tools, sessions, summaries and caches.
- The adapter never commits control state.
- Agent → AEW traffic uses only AEW engine operations, through the custody bridge.
- Harness → AEW traffic is telemetry in local run records (KC §5.3), which no gate reads.

### Runs
- A **run** `R-<INV>-<n>` is one harness execution of an invocation. `inv.runs[]` in control state records `{run, harness, token_id, launched_at, kind}`.
- The first run of a `--launch` dispatch adopts the credential that the dispatch issued, which never leaves the process.
- Every later `aew harness launch` (Lead, CAS) **rotates** the credential in the same commit: the old credential is revoked with reason `rotated: R-…`, and a new one is issued with the same scope. At most one run can act.
- A session id is correlation only, recorded in the run record.
- **Harness session loss is not INTERRUPTED.** The AEW execution identity (the invocation and its credential) survives and is re-bound by rotation. INTERRUPTED stays tied to authority changes (ADR-0003).

### Credential custody (operator requirement)
**No raw AEW credential ever enters a model-controlled process.**
- The launching process passes the credential to the **run supervisor through its stdin pipe**. The supervisor keeps it in memory only.
- The supervisor serves a **run-scoped bridge**:
  - a local named pipe (Windows) or AF_UNIX socket (POSIX);
  - a per-run HMAC authkey;
  - **structured** requests only: `check.run`, `submit`, `whoami`.
- The bridge executes requests through the engine with the held credential, so the engine's authority checks remain authoritative. Before each request it re-checks that its run is the invocation's latest and that the invocation is active. On any end, rotation or revocation it closes.
- The `aew` CLI routes `check run` / `submit` to the bridge when no credential is supplied.
- The Lead is symmetric: `aew opencode` holds the Lead credential and serves a **Lead bridge**. The bridge:
  - refuses credential-emitting commands;
  - requires `--launch` on dispatch;
  - redacts `aew1.` strings from output.
- **Why:** the spike showed that anything a harness shell prints is persisted twice, in the harness DB and in shell-output files. A harness permission layer is not secret isolation (an `edit` deny was bypassed through the shell).

### Process ownership
- The supervisor owns the harness process tree independently of any harness lease:
  - **Windows:** a job object with KILL_ON_JOB_CLOSE (spike: a hard-killed supervisor took the server and a detached grandchild with it);
  - **POSIX:** a process group, plus `PR_SET_PDEATHSIG` where available.
- OpenCode's `--stdio` lease is used but not relied on.

### OpenCode adapter (V2 2.0.18)
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
  - the shell env replaced by `PUT /api/session/{id}/environment`, which carries no provider keys, no credentials and no OpenCode password;
  - `location.directory` = the invocation's recorded workspace as a long path.
- **Permissions:** every rule is allow or deny, never `ask`, because an `ask` blocks forever. The rules are:
  - `edit` for implementers only;
  - `subagent`, `question` and `external_directory` denied;
  - `skill` limited to the card's skills.

  Session-create permissions are appended last, so AEW sends the complete set there.
- **Completion:** execution terminal events, raced with `…/wait`, and reconciled from the message list. Effective model, tokens and cost come from assistant messages.

### Harness-neutral contract
`HarnessAdapter`: `health`, `launch(contract, credential, run_dir)`, `send`, `interrupt`, `terminate`, `inspect`, `collect`. A Codex or Claude Code adapter implements the same protocol. No engine change is needed.

## Consequences

- OpenCode state is disposable. Destroying a run's directory loses a conversation, not the engineering project.
- A surviving or revived old session holds dead authority: its credential was rotated or revoked, and its bridge is closed.
- The explicit-credential CLI path (`AEW_INVOCATION_TOKEN`, `--token`) remains for scripted roles and tests.
- **Known V2 risks:** no stability policy; `--stdio` is undocumented; `/api/skill` is empty even when skills are exposed; the job object can be escaped through out-of-tree spawners (authority is unaffected). These are recorded in the reviewer brief's attack list.
