# Harness conformance (M3)

What any harness adapter must do for AEW. This is the adapter-neutral contract behind ADR-0009, the suite that checks it, and how a new harness (OpenCode, Codex, Claude Code, …) is added.

- **Code:**
  - `src/aew/harness/` (contract, supervisor, custody bridges, process ownership);
  - `tests/helpers/harness_conformance.py` (the scenarios);
  - `tests/helpers/fake_harness.py` and `fake_agent.py` (the reference driver).
- **CI:**
  - `tests/integration/test_harness_conformance.py` runs every scenario against the fake harness;
  - `tests/integration/test_lead_session.py` checks Lead custody and bridge parity;
  - `tests/regression/test_m3_harness_adversarial.py` holds the step-2 race and attack regressions.
- **Live lane (opt-in, M3 step 4):** the same scenarios, driven through a real OpenCode private server.

## 1. The adapter contract

An adapter is one `HarnessAdapter` instance per run, inside that run's supervisor.

| Method | Obligation |
|---|---|
| `launch(contract, agent_env)` | Start the harness through the supervisor's `ProcessTree`, so every harness process is owned. Check health against the harness actually started (version, required capabilities, the pinned model and effort present), and raise `HarnessIncompatible` on any gap (fail closed). Give every model-controlled process exactly `agent_env`. Deliver `contract.prompt` (preamble + pinned pack + continuation). Return `{session, state_dir, version, …}`. |
| `inspect()` | Report `{alive, exit_code, session}` without side effects. A harness's "done" is only a hint: the supervisor decides the run's status from AEW evidence. |
| `terminate()` | Stop the harness (idempotent). The supervisor also kills the whole tree afterwards. |
| `send(text)` / `interrupt()` | Deliver a Lead message mid-run, or stop the current turn. Optional: raise `HarnessIncompatible` if unsupported. |
| `collect()` | Non-authoritative facts: `effective` (every `{provider, model, effort}` actually used), `sessions`, usage and context sizes. The supervisor compares `effective` with the pin (`model_check`). |

**What an adapter never does:**
- hold or see an AEW credential;
- commit AEW state;
- write outside its run directory (its private state goes under `state_dir`, inside the run directory);
- load project harness configuration (it would present unaccepted material, KC §7);
- let a harness permission prompt (`ask`) block, since every rule is allow or deny.

## 2. Conformance scenarios

Each scenario is written once, as agent actions:
- `write`, `aew`, `check`, `submit`, `submit_raw`;
- `dump_env`, `child_env`, `scan`;
- `spawn_orphan`, `pid`, `cwd`;
- `touch`, `wait_file`, `exit`.

It asserts AEW-side outcomes only. After every scenario, the whole temporary tree is scanned for any credential string.

| Scenario | Property |
|---|---|
| `authorized_operations_act_through_the_bridge` | custody 1: whoami/check/submit work with no credential; evidence carries the pin, the credential id and the run |
| `agent_processes_receive_only_the_curated_environment` | custody 2–3: the agent, a child and a shell see the bridge and nothing secret (no AEW credential, no provider key, no harness config), even when the Lead's shell holds its token |
| `no_credential_in_any_file_the_run_leaves` | custody 4: harness state (DB, transcripts), run records, packs and workspace are clean; so is `credential_scan` |
| `rotation_leaves_the_old_run_without_authority` | custody 5: after a relaunch, the old run's bridge refuses, even with its own key |
| `harness_success_without_evidence_moves_no_state` | a harness reporting success is not AEW progress (WC §8.2) |
| `malformed_output_is_refused_and_moves_no_state` | malformed, state-forging and wrong-kind submissions are refused |
| `a_crashing_harness_moves_no_state` | non-zero exit → `crashed`; nothing moves |
| `stopping_a_run_ends_every_process_it_started` | a descendant in its own process group dies with the run |
| `repeated_runs_start_and_end_cleanly_with_private_state` | sequential runs: distinct sessions, private state under each run directory, every supervisor exits |
| `a_reviewer_gets_a_fresh_session_isolated_from_the_implementer` | a reviewer's harness state holds only its own session |
| `an_incompatible_harness_fails_closed` | a failed capability probe → `launch_failed`, no harness process, no credential holder |
| `a_different_effective_model_is_flagged` / `the_pinned_model_is_the_effective_model` | requested versus effective model and effort |
| `a_read_only_role_cannot_change_its_observation` | an executor's mutation → `OBSERVATION_MUTATED`; no record |
| `an_agent_cannot_perform_lead_operations` | no Lead credential in the agent; a forged one is rejected; the seat is held |

A driver declares `capabilities`. A scenario needing one it lacks (for example `effective_override`: forcing a harness to run another model) is skipped visibly for that driver, never silently passed.

## 3. Lead custody and bridge parity

- **The session.** `aew lead session [--acquire] -- <harness command>` holds the Lead credential in memory and serves the **Lead bridge**. `aew opencode` is this command with an OpenCode TUI. The CLI routes every Lead-authenticated command to the bridge when the session environment supplies no credential.
- **Parity by construction.** The Lead bridge is the invocation bridge's `BridgeServer` with one operation, `lead.cli {argv, cwd, stdin}`: the same JSON protocol, key challenge, exact typed arguments, redaction and drain.
- **Parity by test.** `test_both_bridges_hold_the_same_custody_properties` runs one scenario against both bridges:
  - the five custody properties;
  - the same transport refusals: non-JSON, unknown operation, identity fields, a foreign key;
  - revocation: the bridge refuses and stays closed.
- **What the Lead bridge also refuses:**
  - commands that would put a credential into the session (`lead acquire|takeover|release`, `lead handoff offer|accept`), refused locally in the session and again by the broker;
  - dispatch without `--launch`;
  - an explicit `--token`;
  - read-only commands (they run locally);
  - another project.
- **Intended differences:**
  - Revoking an invocation also terminates its run; superseding a Lead closes the bridge but leaves the operator's harness running read-only.
  - A Lead session's harness process keeps the operator's environment minus AEW credentials, because a harness needs its provider keys. Keeping provider keys out of the Lead **model's shell** is the harness adapter's job, exactly as for invocations; the OpenCode Lead launcher does it in step 4, and its live conformance checks it.
- **`--acquire`.** The seat is taken in-process and the credential exists only inside the session. At exit the seat is released if nothing is in flight; otherwise it is held, and the output says that continuing needs `aew lead takeover` at the operator's own terminal. The usual path is `AEW_LEAD_TOKEN` in the operator's own shell: it is removed from the session's environment and survives a crashed session.

## 4. Adding a harness

1. Implement `HarnessAdapter` in `src/aew/harness/<name>/`.
2. Register it in `registry.BUILTIN`, or in a site's `AEW_HARNESS_ADAPTERS`.
3. Map the contract:

   | Obligation | OpenCode V2 (step 4) | Codex CLI (sketch) | Claude Code (sketch) |
   |---|---|---|---|
   | private instance, owned tree | `serve --stdio` per run inside the job | `codex exec` / app-server per run inside the job | `claude -p --output-format stream-json` per run inside the job |
   | curated agent environment | `PUT /api/session/{id}/environment` | spawn env + sandbox policy | spawn env; settings `env` |
   | fresh private state | XDG dirs under `state_dir` | `CODEX_HOME` under `state_dir` | `CLAUDE_CONFIG_DIR` under `state_dir` |
   | health / capability probe | `/api/info` + `/openapi.json` + `/api/model` | version + schema of the app-server protocol | version + `--help` capability check |
   | effective model | assistant messages, `session.step.started` | turn events | `system/init` + `result` messages |
   | no project config / skills leakage | `OPENCODE_DISABLE_PROJECT_CONFIG`, compatibility plugin off, `skill` rules | `--config` overrides, no project `AGENTS.md` | `--setting-sources`, no project settings |
   | no blocking prompts | allow/deny rules only | `--ask-for-approval never` | `--permission-mode` with explicit allow/deny |

4. Write a `Driver` that makes the harness perform the scenario actions deterministically, without depending on a model. For OpenCode: the session's shell endpoint runs each action as a command in the real session environment.
5. Run `run_scenario` for every scenario in the harness's lane. Add harness-specific tests for what the neutral scenarios cannot reach (section 5).

## 5. Watch list for the OpenCode adapter (designer, 2026-09-27)

| Concern | Where it is checked |
|---|---|
| model catalog loads asynchronously | adapter health polls `/api/model` with a bounded deadline, so a slow catalog is not reported as missing; step-4 unit test with a delayed fake server and live lane |
| pinned requested model vs actual effective model | pre-validation of `providerID/id#variant` before prompting; `collect().effective` from assistant messages and step events; the supervisor's `model_check` (scenario above) |
| queue behaviour around completion boundaries | step 4: `send` with `delivery: queue` near a turn's end must not be lost or declared complete early; completion is decided only after the session's inbox is empty and the loop is idle |
| SSE loss or reconnection | step 4: losing the event stream never implies completion; the adapter reconciles through `…/wait`, `…/log?after=`, the message list and `session/active`; a fault test drops the stream mid-turn |
| OpenCode reporting completion while evidence is absent | neutral scenario `harness_success_without_evidence_moves_no_state` through the OpenCode driver |
| permissions doing something unexpected | step 4: projection golden test, plus live checks that `edit`, `subagent`, `question`, `external_directory` and `skill` behave as projected. The engine stays authoritative: reviewer and read-only mutations are refused at submit (M3-B6, `OBSERVATION_MUTATED`) |
| private server startup/teardown under repeated runs | neutral scenario `repeated_runs_start_and_end_cleanly_with_private_state` through the OpenCode driver (no leftover server, port or process) |
| Lead bridge behaving identically to the invocation bridge | `test_both_bridges_hold_the_same_custody_properties` (section 3) |
| OpenCode subprocesses genuinely receiving only the curated environment | neutral scenario `agent_processes_receive_only_the_curated_environment` run inside OpenCode's own shell tool; the same for the Lead TUI's shell in step 4 |
| fresh reviewer DB/session isolation | neutral scenario `a_reviewer_gets_a_fresh_session_isolated_from_the_implementer`: a reviewer's private OpenCode DB lists only its own session |
| version/capability probing failing closed | neutral scenario `an_incompatible_harness_fails_closed`; step 4 adds a doctored OpenAPI and a missing model/variant |
