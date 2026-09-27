# AEW M3 — Ambiguity / implementation report and plan (OpenCode V2 harness adapter)

- **Status:** approved by the operator on 2026-09-27, after the designer's two corrections: re-baseline against V2, and credential custody. The operator's review also made the stdin lease not an AEW invariant and required health to probe capabilities.
- **Accepted M2 baseline:** `adef6405` on `origin/main`. That is the PR #4 merge, performed by the operator on 2026-09-27T03:33Z after independent review. Branch `impl/m3-opencode`.
- **Step 0 is complete:** `m3-opencode-v2-rebaseline.md`. The spike confirmed the candidate interface (a private V2 server, HTTP+SSE from Python) and every required lifecycle operation, so the plan below is unchanged. Spike facts that refine implementation details are listed in that document (§5).
- **Step 1 is complete** (execution profiles; ADR-0010 updated to the implementation). One naming refinement: the invocation pin is `inv.execution_profile`, not `inv.execution`, because a non-mutating Ticket's `unit.execution` already names its attempt record (ADR-0008). The evidence field is `producer.execution_profile`.
- **Step 2 is complete** (the harness core: runs and rotation, the supervisor, process-tree ownership, the custody bridge and CLI routing, `harness launch|status|wait|stop`, `--launch` on the dispatch commands, oracle rules 17 and 18). ADR-0009 is updated to the implementation. **M3-D1**, a pre-existing M2 defect found by the launch preconditions, was fixed with a regression written first (ADR-0009, Consequences).
- **Step 3 is complete.**
  - An adapter-neutral conformance suite (`tests/helpers/harness_conformance.py`, 15 scenarios, run against the fake harness in CI; step 4 adds the OpenCode driver).
  - The Lead custody broker, `aew lead session`, is harness-neutral and shares the invocation bridge's transport; its parity is tested.
  - The supervisor compares requested and effective model and effort (`model_check`).
  - `docs/implementation/harness-conformance.md` covers the contract, scenarios, the adding-a-harness mapping and the designer's step-4 watch list.
  - **Open observation:** `test_an_acquired_seat_is_released_or_held_explicitly` failed once, during roughly 40-way parallel overload (the full suite plus a stress loop), and has not reproduced in 13 targeted runs (up to 24 concurrent workers). The probable cause is the 180 s CLI timeout, since one Lead session makes about ten CLI round trips plus a run launch; that helper's timeout is now 600 s. Re-check if it recurs in CI.
- **Step 4 is complete** (the OpenCode V2 adapter, `src/aew/harness/opencode/`; ADR-0009 updated to the implementation).
  - A private `serve --stdio` per run; health = version, a capability probe of the served OpenAPI, the pinned model and variant in the (asynchronous) catalog, and the projection loaded as written; a curated session environment; completion decided from the REST API only.
  - The conformance suite runs against the real adapter in CI (a fake V2 server that serves the real 2.0.18 OpenAPI) and in a new opt-in live lane against OpenCode 2.0.18: 14 scenarios pass live, and one (forcing a different model) is not drivable live and is skipped visibly.
  - `aew opencode` runs the Lead's TUI through the Lead broker with `--standalone`, because a standalone V2 TUI gives every session its own environment. That environment is an allowlist with no AEW credential and no provider key (the step-3 obligation).
  - `aew harness send|interrupt|config`; `aew resume` reports harness runs (M3-B1: a lost harness is not an interruption) only when runs exist.
  - **Found while building it** (all reported in `m3-opencode-v2-rebaseline.md` §9):
    - agents and commands load asynchronously, like the catalog;
    - the agent's shell is chosen from `SHELL` (else PowerShell on Windows);
    - V2's default rules protect `.env` files and allow its own output directories, and AEW's blanket rules overrode both until fixed;
    - closing an event stream from another thread deadlocked the adapter until fixed. The supervisor now bounds any adapter's `terminate()`.
    - a run's event log was appended from several threads through separate handles, which interleaves lines on Windows; appends are now serialized.
- **Step 5 is complete** (the brief's attack list, M3-B6 and M3-B7; ADR-0009 Consequences).
  - **M3-B6 confirmed and fixed.** A reviewer's edit of the shared workspace was recorded with its passing review, refused at ingest only as "stale", and a second reviewer then passed the edited code. The fingerprint-bound gates kept it out of integration. Reviewers and verifiers are now refused where the edit is made (`WORKSPACE_MUTATED`, naming the paths), and cannot be dispatched for code no implementer reported.
  - **Run records hardened.** A later run could rewrite an earlier run's record, and `harness status`/`wait` showed the forged evidence list. They now read evidence from the evidence store. No state could move either way.
  - Every attack in the brief is a permanent regression:

  | Brief attack | Regressions | Result |
  |---|---|---|
  | continue a superseded session | `test_run_dies_then_lead_relaunches_then_old_process_wakes_up`, conformance `rotation_leaves_the_old_run_without_authority`, live `test_a_revived_superseded_session_has_no_aew_authority` | the old bridge refuses (`STALE_AUTHORITY`); V2 does not persist a session's environment |
  | reuse an ended invocation | `test_broker_alive_then_invocation_cancelled`, `test_the_retired_implementers_run_stops_when_review_begins`, `test_relaunch_preconditions` | run stopped, relaunch refused |
  | run an agent from the wrong worktree | `test_an_agent_in_the_wrong_worktree_still_acts_only_for_its_own_workspace`; the session's location comes only from the invocation (`test_the_projection_reaches_the_server_and_the_session`) | identity, checks and evidence stay bound to the invocation's workspace |
  | submit evidence from a mismatched session or invocation | `test_run_a_cannot_act_as_run_b`, `test_evidence_cannot_claim_another_invocation_run_role_or_credential` | refused; identity is engine-stamped |
  | let a Reviewer mutate source | `test_a_reviewer_cannot_mutate_source`, `test_a_verifier_cannot_mutate_source` | **defect found (M3-B6), fixed** |
  | let an Investigator obtain implementer authority | `test_an_investigator_cannot_obtain_implementer_authority`, conformance `a_read_only_role_cannot_change_its_observation`, projection units | refused |
  | spawn an untracked subagent | `subagent` denied (projection units); `test_a_subagent_session_is_never_invisible`; conformance `stopping_a_run_ends_every_process_it_started` | recorded and shown; every process dies with the run |
  | resume from stale conversational state | `test_a_lead_acting_on_stale_conversational_state_is_refused`, `test_relaunch_delivers_the_same_pack_plus_a_continuation_from_durable_state`, the live revived-session test | CAS refusal; relaunch rebuilt from durable state |
  | change model/role configuration after dispatch | `test_model_and_role_configuration_are_pinned_at_dispatch`, live `test_project_opencode_config_written_by_an_agent_changes_no_later_run` | pins hold; project configuration is ignored and health verifies the loaded agent |
  | forge or reuse correlation metadata | `test_run_a_cannot_act_as_run_b` (forged `AEW_RUN`/`AEW_INVOCATION`, foreign bridge), `test_forged_run_records_and_harness_success_move_nothing` | **display defect found, fixed**; no state moves |
  | use success/exit state to bypass gates | conformance `harness_success_without_evidence_moves_no_state`, `test_harness_exit_without_its_expected_output_moves_no_state`, the forged-record test | gates unmoved |
  | M3-B7 credential exfiltration | the custody tests (step 2 and 3), conformance custody 1-5 on fake and real OpenCode | no credential reachable |
  | capability drift | `test_an_incompatible_server_fails_closed`, doctored-OpenAPI units, live `an_incompatible_harness_fails_closed` | fails closed |
- **Step 2 focus cases** (designer request, 2026-09-27). Each is a permanent regression in `tests/regression/test_m3_harness_adversarial.py`. They pass on Windows (Python 3.13, 16-way parallel, repeated) and on Linux (WSL, Python 3.11).

  | Case | Test | Safe end state asserted |
  |---|---|---|
  | launch commit succeeds, supervisor never spawns | `test_launch_commit_succeeds_but_the_supervisor_never_spawns` | run `unconfirmed`; no process holds the credential; plain relaunch refused (`RUN_LIVE`) inside the grace window; `--replace` rotates |
  | supervisor spawns, AEW crashes | `…_launcher_crashes_before_handing_over_custody`, `…_after_handing_over_custody`, `test_supervisor_crash_takes_the_whole_harness_tree_with_it` | before handoff: `launch_failed`, supervisor exits. After handoff: the run completes without its launcher. Supervisor killed: the OS kills the agent and a detached descendant; the run is `lost`; relaunch rotates |
  | two Leads race to launch the same invocation | `test_two_leads_race_to_launch_the_same_invocation` | exactly one wins, the other gets `STALE_REVISION`; one run and one supervisor; a re-reading third Lead gets `RUN_LIVE`; the dispatch-printed credential is dead |
  | old run alive → rotation → old process immediately submits | `test_old_run_alive_then_rotation_then_old_process_immediately_submits` | with the old watchdog frozen: submit and whoami are `STALE_AUTHORITY`; no evidence from the old run; it ends `terminated: superseded` |
  | rotation while the old run submits | `test_rotation_while_the_old_runs_submission_is_in_flight`, `…_check_is_running`, `test_rotation_racing_submissions_never_admits_evidence_after_revocation` | a request past the bridge check is refused by the engine (`rotated: R-…`); a check spanning the rotation writes neither evidence nor log; unpaused races always satisfy rules 5, 17 and 18 |
  | broker alive → invocation cancelled | `test_broker_alive_then_invocation_cancelled` | submit refused; run `terminated: invocation cancelled`; harness tree dead; its bridge coordinates yield `STALE_AUTHORITY` |
  | broker alive → takeover | `test_broker_alive_then_takeover` (contrast: `test_a_carried_run_keeps_working_across_a_cooperative_handoff`) | takeover: refused, `terminated: invocation interrupted`. Carried handoff: the run keeps its authority |
  | run dies → relaunch → old process wakes up | `test_run_dies_then_lead_relaunches_then_old_process_wakes_up` | the old supervisor is frozen (suspended), observed `lost`, relaunched; on waking, its pending submit is refused (`superseded by R-…-2`); old coordinates, even at the new run's endpoint, are refused |
  | fake harness prints or reads the raw credential | `test_agent_cannot_print_or_read_the_raw_credential` | with the Lead token in the Lead's own env: none in the agent env, `whoami`, `invoke show`, `harness status`, `context show` or `lead show`, nor in any file under the repo, workspaces or run dirs; `credential_scan` clean; every test's teardown rescans the whole tmp tree |
  | model-controlled child inspects its environment | `test_model_controlled_child_processes_inherit_no_secret` | a Python child and a shell see neither credential nor provider secret; Linux: the supervisor's `/proc/<pid>/environ` is unreadable (non-dumpable) |
  | run A uses run B's identity | `test_run_a_cannot_act_as_run_b` | identity fields in a request → `USAGE`; B's endpoint with A's key → `PERMISSION_DENIED`; a spoofed `AEW_RUN`/`AEW_INVOCATION` still acts as A; B's record kind → `PERMISSION_DENIED`; non-JSON and non-bridge operations refused; B unaffected |
  | successful exit, no evidence → state must not move | `test_harness_exit_without_its_expected_output_moves_no_state` (exit 0 and exit 3) | `ended_without_evidence` / `crashed`; control revision, unit state, invocation and its credential all unchanged; relaunch rotates; nothing moves until the Lead ingests |
- **Frozen future design:** `docs/design/AEW_Coordination_Design_v0.1.md` (sha256 `2725b747…`). It is a compatibility constraint only; see §2.11.


## Context

M1 proved that the control engine, authority, evidence, integration and crash recovery are trustworthy. M2 proved hierarchy and non-mutating work. No real harness has been attached yet: roles are scripted CLI drivers (`tests/helpers/aewflow.py`).

M3 attaches OpenCode behind a narrow, harness-neutral boundary. It must show with evidence that:
1. **Portability.** AEW still holds the workflow, knowledge, authority, evidence and resumable state if OpenCode is replaced.
2. **Value.** AEW makes real engineering work better, not merely more elaborate.

**Baseline.**
- M2 was accepted and merged by the operator: PR #4, merge commit **`adef6405`** on `origin/main`, 2026-09-27T03:33Z.
- Work happens on branch `impl/m3-opencode`, created from `origin/main`. The local `main` is stale.
- The first docs commit records the baseline and fixes the stale "M2 awaits re-review" status line.

**Basis.**
- Frozen specs:
  - WC v0.7: §2, §5, §6, §8, §8.2, §9.9, §10, §15, §16.6, §16.10–12, §17, §18, §20, §23;
  - KC v0.4: §3, §5.3, §7, §11, §15, §16, §17, §21, §27.
- ADRs 0001–0008 and their amendments, `testing-and-ci-strategy.md`, and the code on `adef640`.
- The frozen **Live Coordination design v0.1** (`~/Downloads/AEW_Coordination_Design_v0.1.md`, sha256 `2725b747…`). It is committed byte-identical to `docs/design/` as a compatibility constraint, not scope (§2.11).

**Operator decisions (2026-09-27).**
- Free `opencode/*` models for the live tests; a **paid provider for dogfood**. The operator supplies the key as an env var, plus the model and budget, **before step 9**. The plan pauses there if they are missing.
- Real runs on **Windows with the pinned 2.0.18 CLI**. Linux is covered by fake-harness CI.
- After the spike: **stop only if the plan changes**.
- The operator will drive **one TUI session**.
- **Credential custody is required** (§2.3).
- **The stdin lease is not an AEW invariant.**
- **Health probes capabilities.**

---

## 0. V2 re-baseline (designer correction; gates the adapter design)

All earlier concrete OpenCode API details are **non-authoritative** unless confirmed against V2. That covers the M3 brief's examples, the M1 plan's M3 sketch, and my first pass. The facts below come from the installed binary and tag `v2.0.18` source and docs. **The adapter design in §2.5 is frozen only after the step-0 spike.**

### Target version and surface

**Target: OpenCode 2.0.18.** The binary is pinned at `%APPDATA%\ai.opencode.desktop\cli\2.0.18\opencode-cli.exe`. The Desktop auto-updates its `resources\` copy, not the versioned one. The user's Desktop background service on :49374 is never touched.

**Stability reality.** V2 publishes no stability or versioning policy. The OpenAPI (served by the binary at `GET /openapi.json`, 138 operations) is labelled *"Experimental HttpApi surface … 0.0.1"*, and the session, message, permission and event groups are tagged experimental. `@opencode/client` is a "private generation target" generated from that same contract. **There is no official non-JS client.**

**Surfaces compared.** The criteria: supported; covers launch, correlation, location, model/effort, events/results, interrupt/terminate and reconstruction; no new runtime on the offline Rocky 8 target; no skew with the installed binary; mid-run delivery for coordination; disposable state.

| Surface | Verdict |
|---|---|
| **A. HTTP+SSE against a private `opencode-cli serve` process, from Python stdlib** | **Selected (candidate until the spike).** It is the published contract that the JS client wraps, needs no new runtime, and uses the installed binary. |
| B. `@opencode/client` (a Node/Bun shim) | Rejected: the same contract plus a JS runtime and npm packages on the offline target; the client is itself a "private generation target". |
| C. `@opencode/sdk` embedded host | Rejected: bundles the OpenCode core into a JS process AEW would own (native deps: node-pty, watcher, tree-sitter), is version-skewed against the installed binary, and credentials would sit in-process. |
| D. CLI (`run --standalone --format json`, `session export`, `api`) | Kept for diagnostics and as the **raw-OpenCode dogfood baseline**. As the lifecycle interface it has no mid-run delivery, can interrupt only by signal, and permits no pre-launch model or skill inspection. |

### V1 assumptions no longer valid

| V1 assumption | V2 |
|---|---|
| `task` tool / child sessions | `subagent` (foreground/background; children inherit session permissions) |
| todo tools | **none** |
| `bash` / `write` / `patch` / `doom_loop` / `lsp` permission keys | ordered `{action, resource, effect}` rules; `shell`, `edit` (covers write/patch); `doom_loop` and `lsp` are gone |
| `prompt_async`, `/message`, `abort`, `/session/status` | `POST /api/session/{id}/prompt` (returns an inbox item; `delivery: steer\|queue`), `/interrupt?resume=`, `GET /api/session/active` + `Session.Info.outcome` |
| `/event`, `/global/event`, `/doc`, `/global/health` | `GET /api/event` (volatile, no replay), `GET /openapi.json`, `/api/info` |
| messages `{info.role, parts[]}` | typed timeline (`assistant{model{id,providerID,variant}, tokens, cost, finish, content[]}`, `idle{outcome}`) |
| `run --attach/--dir/--variant/--command` | `--server/--standalone`, the cwd, and `model#variant` |
| `agent` / `prompt` / `maxSteps` / `small_model` | `agents` / `system` / `steps` / `agents.title.model` |
| sampling params | not sent |
| `OPENCODE_PERMISSION`, `OPENCODE_DISABLE_CLAUDE_CODE`, `OPENCODE_SERVER_USERNAME` | removed |
| CLAUDE.md fallback / `instructions` | only `AGENTS.md` loads |
| `opencode export` | `session export` |
| V1 plugins, `@opencode-ai/sdk`, Python `opencode-ai` | new plugin API; V1 packages are incompatible |

### V2 behaviour that shapes the design (from source; the spike confirms)

- **An `ask` permission blocks the loop forever** until a reply or interrupt, so every AEW rule is explicit allow/deny, and the supervisor rejects any ask it sees.
- **Session-create `permissions` are appended last** and can override agent rules. AEW sends the complete rule set at session create, and denies `subagent` so that no session is created anywhere else.
- **An agent's configured model is not applied** to API-created sessions, so `model{providerID,id,variant}` is set on create. Assistant messages and `step.started` record the model actually used.
- **Shell env** is `sessionEnvironment ?? server process.env`. `PUT /api/session/{id}/environment` **replaces it wholesale and is held in memory only** (not in SQLite). This is how the agent's shell gets a curated env with no provider keys and no credentials.
- **`serve --stdio`** prints a single `{"url"}` line, lives until stdin EOF, and **deletes `OPENCODE_PASSWORD` from its own env**, so tools cannot authenticate to their own server. Plain `serve` does not strip it.
- **Completion** is detected the way the official `run` does it: subscribe before prompting, with a client-chosen `msg_` id → `session.execution.succeeded|failed|interrupted`. It is raced with `POST /api/experimental/session/{id}/wait` and reconciled from the message list plus `outcome`. `…/log?after=<seq>&follow` replays gaps.
- **Windows shell tool:** a tree-kill (`taskkill /T`) happens only on timeout or interrupt. Descendants of a normally exiting command survive.
- **Skills from `~/.claude` / `~/.agents`:** there is no env switch. The candidate is config `"plugins": ["-opencode.config.compatibility"]` (inferred) plus `skill` permission rules.

### Known gaps (reported, never emulated)

- no stability guarantee;
- `serve --stdio` is undocumented (help/source only);
- no documented isolation recipe;
- `wait`, `log`, export and stats are experimental;
- no non-JS client;
- skill-discovery disable is inferred.

### Step-0 deliverable and spike

**Deliverable: `docs/implementation/m3-opencode-v2-rebaseline.md`** records all of the above plus the results of a disposable spike (`eval/m3/spike/`: a free model, isolated XDG, never the Desktop service). **Any NO is reported explicitly.** The spike must establish:
1. private `serve --stdio` + `OPENCODE_PASSWORD` (the password is stripped from the tool env); fallback to plain `serve`;
2. session create with model+variant, location and permissions; prompt with a client `msg_` id; completion via events + `wait` + messages; effective model, tokens and cost;
3. `interrupt`, then continue; `delivery: queue` and `steer` into a running loop;
4. `PUT /environment` gives the shell exactly the curated env, and nothing from the server env leaks;
5. an unanswered `ask` blocks; auto-reject works; the denies for `edit`, `subagent`, `question`, `external_directory` and `skill` are enforced (the tools are removed);
6. skills and instructions exposed under isolation, plus the compatibility-plugin disable, with a workspace under home;
7. the supervisor's Windows job object (kill-on-close) kills the server and its shell descendants when the supervisor dies; a supervisor launched from an OpenCode shell-tool call survives;
8. the agent's shell cannot reach its own server API (no password);
9. `run --standalone --format json` baseline semantics;
10. latencies; server killed mid-run; `OPENCODE_DB=:memory:`.

**Gate:** if the spike confirms A and every lifecycle operation, proceed. Otherwise stop and report.

**Effect on the HarnessAdapter contract.** It stays harness-neutral. V2 changes the implementation only; `steer` is reserved for coordination and not exposed in M3. If mid-loop delivery fails, `send` is documented as turn-boundary only.

**Effect on disposability.** It improves: each run has private XDG/DB state, so destroying a session is deleting a directory, and reconstruction never reads it.

---

## 1. Already fixed by the frozen contracts

1. **Harness independence** (WC §2, §17, §19.4).
2. **Roles as bounded invocations** from launch contracts. The Lead is the only persistent context and is reconstructible from artifacts (WC §5, §15.4–15.5; KC §15.1).
3. **Adapters are never authorities** (WC §16.12, inv. 21).
4. **Provenance includes model/provider; routing is policy** (WC §9.9, §18; KC §11).
5. **Runtime logs are deletable. Secrets and transcripts are never knowledge** (KC §3, §5.3, §21, inv. 22).
6. **Success is never inferred.** Only ingest and Lead decisions move state (WC §8.2, ADR-0003).
7. **Authority is archetype-keyed and engine-enforced.** Harness permissions are defense in depth. The same-UID threat model is unchanged (ADR-0005/0006).

---

## 2. Architecture (the smallest that satisfies M3)

### 2.1 Boundary

| AEW owns (authoritative) | OpenCode owns (disposable) |
|---|---|
| invocation, card pin, **execution pin** (model/provider/effort), pack sha, workspace/observation, expected kind, credentials and **their custody**, run ids, evidence, gates, state | model loop, tools, sessions, summaries, caches, TUI |

- The adapter never commits control state.
- **Agent → AEW** goes through the `aew` CLI, routed through the run's credential bridge (§2.3).
- **Harness → AEW** is telemetry only, never read by gates.

### 2.2 Run model: invocation 1—n runs 1—n sessions

- **Invocation** (existing). Card, execution profile, pack sha, workspace/observation and expected kind are pinned at dispatch and immutable. A change means a new invocation (coordination §7.1).
- **Run** `R-<INV>-<n>` (new). Control state records `inv.runs[] = {run, harness, token_id, launched_at, kind}`.
  - The first run of a `--launch` dispatch receives the dispatch-issued credential **in-process**, never printed.
  - Every later `aew harness launch <INV>` (Lead, CAS) **rotates** the credential in the same commit: old revoked `rotated: R-…`, new issued with the same scope. At most one run can act (ADR-0005 amendment; re-issuance, no new authority).
- **Session.** Correlation only, kept in the run record.

### 2.3 Credential custody (operator requirement; ADR-0005 amendment)

**Invariant: an agent can exercise exactly its invocation's authorized operations without possessing, or being able to print, the raw AEW credential.** The same holds for the Lead.

**Invocation side.**
- The launching process (the CLI or the Lead broker) writes the credential to the **supervisor's stdin pipe**. It never passes through argv, env or disk. The supervisor holds it in memory only, and scrubs `AEW_*TOKEN` from its own env.
- The supervisor serves a **run-scoped bridge**:
  - a stdlib `multiprocessing.connection` listener (named pipe on Windows, AF_UNIX in a 0700 dir on POSIX);
  - a per-run random `authkey` (HMAC challenge, so the key never crosses the wire);
  - it accepts **structured** requests only: `check.run{check_id}`, `submit{kind, text}`, `whoami`.
- It executes them through the Engine API with the held credential, so **the engine's authority and scope checks stay authoritative**. The bridge adds no authority, and refuses any operation outside the invocation's archetype/card operation set before calling the engine.
- **Before every request**, the bridge re-reads control state: its run must be `inv.runs[-1]` and the invocation `active`. Otherwise it refuses and **closes the listener**. The watchdog closes it on any revocation, rotation, retirement or takeover.
- **Transparent routing.** When no credential is given and `AEW_AGENT_ENDPOINT` is set, `aew check run` / `aew submit` forward to the bridge. `submit --file` is read by the client, and checks run inside the supervisor (cwd = the invocation workspace; env = the supervisor's, which holds no credential). The pack's commands therefore work unchanged; the preamble says "no credential to set".
- **Agent shell env** (`PUT /environment`) contains the OS basics, PATH (including `aew`), `AEW_AGENT_ENDPOINT`, `AEW_AGENT_KEY`, `AEW_INVOCATION` and `AEW_RUN`. It has **no AEW credential, no provider keys and no OpenCode password.**
- **Why the bridge key is acceptable.** It is a run-scoped local capability, deliberately usable by every process the agent starts (they *are* the agent). It is not the AEW credential, dies at run end, rotation or revocation, and grants only operations the engine already authorizes. Hardening by peer-process ancestry is documented as possible, not built.

**Lead side.**
- `aew opencode` takes the Lead credential from the operator: `--acquire` on a vacant seat (acquired in-process), or `AEW_LEAD_TOKEN` in the operator's shell, which it strips from the child env. It holds the credential in memory and runs a **Lead bridge**.
- OpenCode gets `AEW_LEAD_BROKER` plus a key, never the token. Lead-authenticated `aew` commands forward to the bridge, which executes the same handler with the token.
- The Lead bridge:
  - **refuses credential-emitting commands** (`lead acquire|takeover|handoff offer|accept`; takeover stays operator-at-terminal, ADR-0005);
  - requires `--launch` on dispatch commands;
  - **redacts any `aew1.` string** from output.
- Losing the wrapper loses the Lead credential in memory. The operator re-provides it, or takes over at a terminal.

**Tests (fake + live).**
1. An authorized operation succeeds through the bridge.
2. The OpenCode shell and process env contain no raw credential.
3. Arbitrary subprocesses (`env`, `set`, `Get-ChildItem env:`, python) cannot print it.
4. The pattern `aew1\.tk_[0-9a-f]{16}\.` appears nowhere in the OpenCode SQLite DB/WAL, messages, events, run logs or generated config (full scan of run and harness dirs).
5. After rotation or revocation, the old run's bridge refuses immediately and its listener is closed.

The same five, plus the refusal and redaction of credential-emitting commands, are tested for the Lead bridge.

### 2.4 Execution profiles: model / provider / effort (ADR-0010)

- **Policy file.** `.aew/policy/execution.yaml` (`aew/execution/v1`) holds:
  - profiles `{harness, provider, model, effort, max_steps?, deadline_s?}`;
  - routing `archetype → profile`, with card and class overrides;
  - provider-key env **names** (read by the server process only).
- **Unconfigured means refused.** `aew init` writes an unconfigured template; launch refuses until it is configured (the `checks.yaml` pattern).
- **Pin at dispatch.** `_new_invocation` (`engine/workspace_ops.py:42`) pins `inv.execution = {profile, harness, provider, model, effort, selected_by, policy_sha256}`.
  - A Lead override (`--profile` / `--model --effort`) on dispatch is recorded as `selected_by: lead`.
  - `harness launch` has no model flags.
- **Engine-owned evidence stamping.** `submit` and `check run` stamp `producer.execution`, `producer.run` and `producer.credential` (token id), all added to `ENGINE_OWNED`. The self-declared `producer.model` is labelled *declared*.
- **Effective model.**
  - Effort maps to `#variant`. `GET /api/model` must list the pinned variant, or launch refuses; there is never a fallback.
  - The effective model comes from assistant messages and `step.started`; a mismatch is flagged.
  - `agents.title.model` is pinned to the same model. `session.usage.recorded` captures title and compaction usage.

### 2.5 Harness abstraction and OpenCode adapter (ADR-0009)

- **`src/aew/harness/`**
  - `contract.py`: `LaunchContract`, `RunStatus`, `RunResult`, `HarnessHealth`.
  - `base.py`: `HarnessAdapter`, with only `health`, `launch`, `send`, `interrupt`, `terminate`, `inspect`, `collect`.
  - `supervisor.py`: one per run. It owns the process tree, custody and bridge, watchdog, event capture, deadline, collection, and a post-run credential-pattern scan.
  - `bridge.py`: agent and Lead bridges plus the client routing.
  - `runlog.py`: `.aew/local/harness/runs/<run>/` (record `aew/harness-run/v1`, events, prompt, generated config, private OpenCode data). It is deletable.
  - `registry.py`: `opencode`, plus test adapters via `AEW_HARNESS_ADAPTERS`.
- **Process ownership (an AEW invariant, independent of the lease).**
  - The supervisor starts the harness in a **Windows job object with KILL_ON_JOB_CLOSE**, or on POSIX a new process group with `PR_SET_PDEATHSIG` where available.
  - `terminate` kills the whole tree. Supervisor death kills it through the OS mechanism.
  - `--stdio`'s lease and password stripping are **used when present**, not relied on semantically.
  - Recorded pid/pgid let `harness status` reap anything left over. Authority is already dead through rotation.
  - The supervisor is detached from the launching shell (`CREATE_NO_WINDOW` on Windows; `start_new_session` on POSIX).
- **Health = version + capabilities**, checked at every launch against that run's own server, and cached per binary hash:
  - `/api/info` version;
  - `GET /openapi.json` must contain every operation and field M3 uses (session.create with `model/location/permissions/metadata`; prompt with `delivery`/`id`; interrupt; session.active; message list with assistant `model`/`tokens`; permission list/reply; `PUT environment`; model list with `variants`; skill/agent list; event stream);
  - the pinned model and variant are present.

  Any gap fails closed as `HARNESS_INCOMPATIBLE`, naming it.
- **Session setup, per run:**
  1. private `serve`;
  2. health checks;
  3. `POST /api/session {model, location.directory = workspace, permissions, metadata{aew_invocation, aew_run}}` (the metadata is correlation only and never trusted);
  4. `PUT …/environment` with the curated shell env;
  5. subscribe to events;
  6. prompt with a client `msg_` id: the preamble plus the pack;
  7. reject any `permission.asked` and any form;
  8. completion per §0;
  9. collect messages, tokens and cost;
  10. terminate.
- **Isolation, per run:**
  - XDG dirs point at the run's own directory (a shared model-catalog cache is allowed);
  - `OPENCODE_CONFIG_CONTENT` carries the projection with `snapshots: false`, no MCP, and the compatibility plugin disabled if the spike confirms it;
  - `OPENCODE_DISABLE_PROJECT_CONFIG=1`, so workspace `.opencode`, `opencode.json` and `AGENTS.md` never load. This blocks config injection and never presents unaccepted material (KC §7);
  - `OPENCODE_DISABLE_AUTOUPDATE=1`.
- **Projection.** One agent per run: `system` = archetype + card + AEW rules. The model is also pinned on the session. Permissions:

  | action | rule |
  |---|---|
  | `read` / `glob` / `grep` | allow |
  | `edit` | implementer only, else deny |
  | `shell` | allow (the harness permission layer is not a secret boundary; custody is) |
  | `subagent` | deny |
  | `question` | deny |
  | `external_directory` | deny |
  | `webfetch` / `websearch` | only if the card grants it |
  | `skill` | card skills only |

  Missing skills are shown as `unavailable` (WC §16.10). No skills are authored.
- **Rejected:** per-turn `run --format json`, because it would couple against coordination delivery (§2.11).

### 2.6 Lead UX (small, native)

- **`aew opencode`** runs `opencode-cli --standalone` on the authoritative root, with `OPENCODE_CONFIG_CONTENT` = the Lead projection (from `archetypes/lead.yaml`) and the Lead bridge.
  - It writes nothing into the user's OpenCode config.
  - It is idempotent.
  - The Desktop app remains usable read-only.
- **Commands (`agent: aew-lead`):** `/aew-resume`, `/aew-status`, `/aew-ticket <objective>`, `/aew-next <id>` (the next action: dispatch `--launch`, `harness wait`, ingest, advance), and `/aew-handoff`.
  - Shell blocks are used only for fixed read commands, because V2 runs them outside the permission flow.
- **Lead permissions:** `edit` deny, `subagent` deny, `question` allow.
- **`aew harness config opencode --lead|<INV>`** prints the exact projection. It is the inspection/installation command and writes nothing.

### 2.7 Failure semantics (harness state never moves AEW state)

| Case | Run record | AEW state | Recovery |
|---|---|---|---|
| launch failed / incompatible / model or variant missing | `launch_failed` (reason) | unchanged; no process holds the credential | fix, then `harness launch` (rotate) or `invoke cancel` |
| harness crash, server or session gone | `crashed` / `lost` | unchanged | relaunch (fresh session + continuation) or cancel |
| Lead interrupt | `interrupted` | unchanged | `send`, relaunch or cancel |
| revoked / superseded / retired / takeover mid-run | `terminated: invocation_ended`; bridge closed | per the Lead op | none; later requests refused |
| malformed output or ended without evidence | `ended_without_evidence` | unchanged | nudge (`send`), relaunch or cancel |
| supervisor crash | tree killed through the job or pgroup | unchanged | relaunch |
| Lead CLI or TUI crash | runs continue | unchanged | `aew opencode` → `/aew-resume` |
| crash between the launch commit and spawn | `unconfirmed` | recorded, but no process holds the credential | relaunch |

**M3-B1.** Harness session loss ≠ INTERRUPTED. The AEW execution identity (invocation + credential) survives and is re-bound by rotation. INTERRUPTED stays tied to authority changes (ADR-0003). Resume adds an advisory "no live run" note only when runs exist.

### 2.8 Context over the boundary

- The **pack is unchanged** and its sha pinned. Launch regenerates it and refuses unless `matches_recorded`. Section sizes come from its headings.
- The first message is the preamble followed by the pack.
- **Relaunch** gets the same pack plus a **continuation section built only from durable AEW state**: the diff vs. base, this invocation's checks and evidence, and open findings. This is also the slot for future coordination deltas.
- **Every run is a fresh session in a private DB.** A reviewer never shares one with an implementer.
- **Recorded per run:** section bytes, approximate tokens, preamble and system bytes, and first-turn input tokens (OpenCode's own overhead).

### 2.9 Workspaces and observations

- The session `location.directory` comes from the invocation's recorded workspace or observation. No command takes a path.
- The guarantees stay AEW's: live-workspace resolution, `OBSERVATION_MUTATED`, fingerprint-bound gates, and the integration sync refusal.
- **M3-B6.** A mutating Ticket's reviewer and verifier share the implementer's live workspace, and their edits are refused only at ingest, as stale and unattributed.
  - This gets a probe. If confirmed, `submit` refuses with `WORKSPACE_MUTATED` (naming the paths), mirroring M2.
  - The watchdog also terminates the retired implementer's tree at RUNNING→REVIEW.

### 2.10 Observability and performance

- **Run record (harness-neutral):**
  - ids and pins;
  - harness name, version and capability-probe result;
  - requested vs. effective execution;
  - projection sha, tools/permissions exposed, and skills requested/exposed;
  - context composition;
  - workspace;
  - sessions;
  - timeline;
  - outcome;
  - usage per model (non-authoritative);
  - `evidence_submitted` (from the AEW store by credential);
  - AEW-side timings.

  Reasoning text is never stored, only token counts.
- **`AEW_PROFILE=<file>`** records per-operation phase timings: lock, recover, parse, compute, git, commit, render.
- **`tools/perf/control_plane.py`** runs synthetic S/M/L projects (for example 50 / 500 / 3000 units) through `status`, `tree`, `resume`, `context pack`, dispatch, ingest, `gate show` and the CLI fixed cost.
- **Scale regression:** counts of git subprocesses and parses per operation at N vs 4N. Timing-free, so CI-safe.
- Results go in `m3-performance.md`. Only demonstrated pathologies are fixed.

### 2.11 Coordination compatibility (constraint, not scope)

| Future need | M3 extension point |
|---|---|
| address an active invocation | `inv.runs[]` → run record → session |
| deliver a bounded delta | `HarnessAdapter.send`; V2 `delivery: steer`; the continuation section re-delivers pinned deltas after relaunch |
| progress/findings while active | a future `coord publish` is one more structured bridge operation, through the engine |
| interrupt/supersede after a Lead decision | watchdog, bridge closure, `interrupt`/`terminate` |
| communication ≠ evidence; reconstruction without the harness | run records are not evidence; only transcripts are harness-owned |

Rejecting per-turn `run` removes the one choice that would have blocked coordination.

---

## 3. Decisions (no new semantics)

| ID | Tension | Decision |
|---|---|---|
| M3-B1 | WC §8 "session lost" vs ADR-0003 | harness loss ≠ INTERRUPTED; rotation re-binds |
| M3-B2 | M1 prints credentials; OpenCode persists transcripts | `--launch` withholds; stdin handoff to the supervisor; rotation on relaunch |
| M3-B3 | "Lead reconstructible" vs its credential | the Lead session is disposable; the credential lives only in the operator's shell or the wrapper's memory |
| M3-B4 | skills "resolved by the harness" | V2 skills, card-scoped; missing ones visibly unavailable |
| M3-B5 | capabilities vs tools | permission profile as defense in depth |
| M3-B6 | reviewer shares the implementer's workspace | probe → `WORKSPACE_MUTATED` if confirmed |
| M3-B7 | credentials in model-controlled processes | custody bridge (§2.3); a harness permission layer is never treated as secret isolation |

There is no frozen-contract contradiction.

---

## 4. M1/M2 compatibility

- These stay **unchanged**: all M1/M2 tests, probes, both walks, AT-1..13 and the spec pin.
- The only allowed test-helper change is **additive oracle rules**:
  - rule 17: no evidence postdates the revocation of *its own* credential;
  - rule 18: at most one live run per invocation, and the latest run's token is the invocation's while it is active.
- Schemas change additively.
- Dispatch output is unchanged without `--launch`.
- The explicit-credential CLI path (`AEW_INVOCATION_TOKEN`, `--token`) keeps working for scripted roles and tests. Bridge routing applies only when no credential is supplied and an endpoint is set.
- Packs are unchanged. Resume adds a harness section only when runs exist, so the goldens are unchanged.

---

## 5. Implementation steps (`impl/m3-opencode`; tests with each commit; lane suite at each step)

0. **V2 re-baseline and spike** → `m3-opencode-v2-rebaseline.md`, `eval/m3/spike/`.
   - Also: `m3-ambiguity-report.md` (baseline `adef640`), the coordination design into `docs/design/`, the status fix, and the ADR-0009/0010 drafts.
   - **Gate:** stop if the plan changes.
1. **Execution profiles:** policy and schema, the dispatch pin plus overrides, and evidence stamping.
2. **Harness core:**
   - contract/base/registry/runlog;
   - supervisor with process-tree ownership;
   - **custody bridge and client routing**;
   - `harness_ops` (launch, rotation, preconditions), the CLI, and `--launch` on the four dispatch commands;
   - oracle rules 17 and 18.
3. **Fake harness and conformance surface:**
   - `tests/helpers/fake_harness.py`: a real subprocess using the bridge, with scripted behaviours (work, crash, hang, malformed output, no evidence, wrong model, Lead op attempt, observation mutation, **env/credential exfiltration attempts**, untracked child);
   - `harness_conformance.py` (adapter-neutral) and the integration tests, including the **five custody properties**.
4. **OpenCode adapter** (only on spike-confirmed facts):
   - projection (golden-tested), stdlib HTTP/SSE client, capability health, env curation, completion detection, usage and effective model;
   - `aew opencode` with the Lead bridge; `aew harness config`; the commands.
5. **Adversarial regressions** (`test_m3_harness_adversarial.py`): every attack in the brief, plus M3-B6 and M3-B7. Each defect found gets its regression before its fix.
6. **Acceptance:** AT-14 (a Ticket end-to-end via a harness), AT-15 (disposable harness: kill → wipe → fresh → resume → relaunch → complete; old session revival refused), AT-16 (isolated review), AT-17 (credential custody, invocation and Lead).
   - All run with the fake adapter in CI.
   - Their real-OpenCode twins go in a new opt-in **`live` lane** (`tests/live/`, only with `--live`; never in CI assurance). The lane rule, unit test and strategy §2/§9 are updated.
7. **Performance:** `AEW_PROFILE`, `tools/perf/`, the scale regression, and measurements.
8. **Live conformance on 2.0.18 with a free model.**
9. **Dogfood** (§7). **Pause here for the paid provider key, model and budget.**
10. **Docs:**
    - ADR-0009 (harness boundary, V2 adapter, surface evidence), ADR-0010 (execution profiles), amendments to ADR-0005 (custody, stdin handoff, rotation) and ADR-0006 (skills/capabilities → projection);
    - `opencode.md` (install and config), `harness-conformance.md` (including Codex / Claude Code mapping sketches);
    - `m3-dogfood-report.md`, `m3-performance.md`, `m3-reviewer-brief.md`;
    - status table, quickstart, acceptance.md, testing strategy;
    - memory.

    The reviewer brief separates contractual invariants, implementation choices, OpenCode-specific behaviour, future-milestone functionality, and real-model vs deterministic evidence. **Highest-risk areas for the reviewer:**
    - custody bridge bypass and capability leakage;
    - dependence on undocumented `serve --stdio` and the experimental API (capability drift within V2);
    - session-permission override semantics;
    - the agent reaching its own server API;
    - process-tree escape (job breakaway, detached grandchildren);
    - rotation races (a request in flight across rotation);
    - M3-B6.

---

## 6. Test coverage

| Property | Where |
|---|---|
| intended role / context / cwd / model-effort; correlation | conformance (fake + live), AT-14 |
| interrupt, terminate, every §2.7 row leaves state valid | conformance, with the oracle after each step |
| session loss → reconstruction; no revival of superseded authority | AT-15 |
| credential custody (the five properties; invocation and Lead) | AT-17, conformance |
| exit success ≠ completion | conformance |
| the brief's attack list (superseded session, ended invocation, wrong worktree, mismatched evidence, Reviewer mutation, Investigator escalation, untracked subagent, stale resume, model/role change after dispatch, forged correlation, exit-status bypass) + exfiltration + capability drift (a doctored spec fails health) | `test_m3_harness_adversarial.py` (+ live subset) |
| M1/M2 unchanged | whole suite, probes, walks |

---

## 7. Dogfood evaluation (real models)

- **Corpus** (fixtures under `eval/m3/`, plus 1–2 real AEW follow-ups on a scratch clone):
  1. tiny Class 0;
  2. multi-file implementation;
  3. a bug requiring investigation first;
  4. a wrong initial hypothesis → replan;
  5. a review with a seeded defect;
  6. resume after harness loss.
- **Modes.**
  - AEW mode: a headless `aew-lead` through the same API and commands.
  - Raw mode: `opencode run --standalone`, same model and effort (tasks 1, 2, 3, 5 at least).
  - One operator TUI session.
- **Captured:** outcome, hidden-test result, interventions, wall time, tokens and cost, context size, invocations (and which were unnecessary), rework, review findings, and control-plane overhead.
- **Rubric** pre-registered. Poor results and over-orchestration are reported, never hidden.
- **Measured, not pre-built:** if the Class 0 path's LLM post-integration verifier (which only re-runs `unit`) dominates, add a deterministic `checks` adapter for integration-scope verifiers, chosen by execution policy. No gate changes.

---

## 8. Out of scope

- coordination, standups, routing, impact holds;
- a scheduler;
- mutating concurrency above 1;
- a capability resolver (M6);
- model optimization;
- an installer;
- authoring skills;
- an MCP adapter;
- a V1 adapter;
- peer-ancestry bridge hardening.

---

## 9. Verification

- **Local Windows:** `pytest -n auto -m "not serial"` plus `--lane serial` green; `check_assurance.py` passes.
- **CI:** `assurance` green on both OSes.
- **Live:** `pytest --live tests/live` green on 2.0.18.
- **Manual** (the operator's TUI session): `aew opencode --acquire` → `/aew-ticket` → implement/review/verify/integrate → kill OpenCode and wipe its state → `aew opencode` → `/aew-resume` → continue. A credential scan of every OpenCode and run directory is clean.

---

## 10. Critical files

- **New:** `src/aew/harness/{contract,base,registry,runlog,supervisor,bridge}.py`, `src/aew/harness/opencode/{adapter,client,projection}.py`, `src/aew/engine/harness_ops.py`, `src/aew/cli/harness_commands.py`, `src/aew/schemas/{execution,harness-run}.schema.json`.
- **Changed (additively):**
  - `engine/workspace_ops.py::_new_invocation` (pin);
  - `engine/evidence_ops.py::submit`/`check_run` (stamping; M3-B6);
  - `knowledge/evidence.py` (`ENGINE_OWNED`);
  - `engine/authority.py` (rotation; stale-rotated error);
  - `engine/resume_ops.py` (advisory section);
  - `cli/work_commands.py` + `cli/commands.py` (`--launch`, profile flags, bridge routing in `_inv_token`/`_lead_token`);
  - `knowledge/manifest.py` (execution template);
  - `tests/helpers/{invariants,lanes}.py`.
- **Reused:** `_invocation_workspace`, `require_invocation`/`issue_token`/`revoke`, `build_pack`/`context_pack`, `E.scan`, `require_observation_intact`, `run_aew` / `Role` / `sample_project`, and the fault points.
