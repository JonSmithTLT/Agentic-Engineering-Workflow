# Harness conformance (M3)

What any harness adapter must do for AEW. This is the adapter-neutral contract behind ADR-0009, the suite that checks it, and how a new harness (OpenCode, Codex, Claude Code, …) is added.

- **Code:**
  - `src/aew/harness/` (contract, supervisor, custody bridges, process ownership) and `src/aew/harness/opencode/` (the OpenCode V2 adapter);
  - `tests/helpers/harness_conformance.py` (the scenarios and drivers);
  - `tests/helpers/fake_harness.py` and `fake_agent.py` (the reference driver);
  - `tests/helpers/fake_opencode.py` (a fake OpenCode V2 server) and `opencode_scripted.py` (the live driver's adapter).
- **CI:**
  - `tests/integration/test_harness_conformance.py` runs every scenario against the fake harness **and against the real OpenCode adapter driving a fake V2 server**;
  - `tests/integration/test_opencode_adapter.py` covers the OpenCode-specific watch list (section 5);
  - `tests/integration/test_opencode_lead.py` covers `aew opencode`;
  - `tests/integration/test_lead_session.py` checks Lead custody and bridge parity;
  - `tests/regression/test_m3_harness_adversarial.py` holds the step-2 race and attack regressions.
- **Live lane (opt-in: `pytest --live tests/live`):** the same scenarios against a real OpenCode 2.0.18 server, plus a check that the real server loads the Lead projection, and (step 8) a free model carrying out real launch contracts unscripted (section 6).

## 1. The adapter contract

An adapter is one `HarnessAdapter` instance per run, inside that run's supervisor.

| Method | Obligation |
|---|---|
| `launch(contract, agent_env)` | Start the harness through the supervisor's `ProcessTree`, so every harness process is owned. Check health against the harness actually started (version, required capabilities, the pinned model and effort present), and raise `HarnessIncompatible` on any gap (fail closed). Give every model-controlled process exactly `agent_env`. Deliver `contract.prompt` (preamble + pinned pack + continuation). Return `{session, state_dir, version, …}`. |
| `inspect()` | Report `{alive, exit_code, session}` without side effects. A harness's "done" is only a hint: the supervisor decides the run's status from AEW evidence. Once ended, an optional `reason_code` says why when the adapter can tell (`provider_auth_failed`: the provider rejected the key); the supervisor records it on the run, beside `status` and `reason`. |
| `terminate()` | Stop the harness (idempotent). The supervisor also kills the whole tree afterwards. |
| `send(text, delivery)` / `interrupt()` | Deliver a Lead message mid-run, or stop the current turn. `delivery` is `steer` (at the agent's next step boundary, without interrupting it) or `queue` (after its current turn); `aew harness send --when` chooses it through `aew.harness.delivery.WHEN_DELIVERY` (register E55). Optional: raise `HarnessIncompatible` if unsupported. |
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
- `touch`, `wait_file`, `model_step`, `exit`.

It asserts AEW-side outcomes only. After every scenario, the whole temporary tree is scanned for any credential string.

Two more actions serve the acceptance scenarios: `note` (a remark that stays in the run's own conversation) and `{evidence:<name>}` in any argument (the newest evidence id in the agent's own command output naming `<name>`, the way a model reads an id from its last command).

**Drivers:**

| Driver | Where | How the actions run |
|---|---|---|
| `FakeDriver` | CI | the fake harness: one scripted agent process |
| `FakeOpenCodeDriver` | CI | the production OpenCode adapter against `fake_opencode.py`, a V2 server serving the real 2.0.18 OpenAPI. Its "model" runs each action as a tool call under the session's shell environment when one was set, else the server's own (V2's rule). The policy names a provider secret for the server, so the scenarios prove the agent's shell still lacks it. |
| `OpenCodeDriver` | live lane | the production adapter against real OpenCode 2.0.18. Each action runs through the real session's shell endpoint, in the real curated environment, recorded in OpenCode's real database; `model_step` is a real prompt to a free model. |

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
| `repeated_runs_start_and_end_cleanly_with_private_state` | sequential runs: distinct sessions, private state under each run directory, every supervisor and every harness process (a server) exits |
| `a_reviewer_gets_a_fresh_session_isolated_from_the_implementer` | a reviewer's harness state holds only its own session |
| `an_incompatible_harness_fails_closed` | a failed capability probe → `launch_failed`, no harness process, no credential holder |
| `a_different_effective_model_is_flagged` / `the_pinned_model_is_the_effective_model` | requested versus effective model and effort |
| `a_read_only_role_cannot_change_its_observation` | an executor's mutation → `OBSERVATION_MUTATED`; no record |
| `an_agent_cannot_perform_lead_operations` | no Lead credential in the agent; a forged one is rejected; the seat is held |

A driver declares `capabilities`. A scenario needing one it lacks (for example `effective_override`: forcing a harness to run another model) is skipped visibly for that driver, never silently passed.

**Acceptance (AT-14..AT-17; `acceptance.md`).** The same drivers run the M3 acceptance scenarios (`harness_acceptance.py`), which also need a driver to:
- run the Lead's harness session (`start_lead`): `aew lead session` with a scripted Lead by default, `aew opencode` with a fake TUI for `FakeOpenCodeDriver`;
- show what the harness received as a run's first message (`delivered_prompt`; `None` when the driver runs scripted steps rather than prompting, as live);
- show the run's harness configuration (`projection`);
- revive a superseded run's session from a copy of its state (`revive`): for OpenCode, a new real server on that state, running a command in the old session.

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
  - A generic `aew lead session` harness keeps the operator's environment minus AEW credentials, because a harness may need its provider keys. Keeping provider keys out of the Lead **model's shell** is the harness adapter's job, exactly as for invocations. `aew opencode` does it: the TUI gets an allowlisted environment, which V2 then gives every Lead session's shell, with no provider key unless `--provider-env` passes one (ADR-0009; `test_opencode_lead.py`).
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
5. Run `run_scenario` for every scenario in the harness's lane, and for AT-14..AT-17 (`harness_acceptance.ACCEPTANCE`) with the driver's `start_lead`, `delivered_prompt`, `projection` and `revive`. Add harness-specific tests for what the neutral scenarios cannot reach (section 5).

## 5. Watch list for the OpenCode adapter (designer, 2026-09-27)

Where each concern is verified. "Fake V2" means `tests/integration/test_opencode_adapter.py` (CI); "live" means `tests/live/test_opencode_live.py` on OpenCode 2.0.18.

| Concern | Verified by |
|---|---|
| model catalog loads asynchronously | health polls `/api/model`, then allows a settle window after the catalog first appears. Fake V2: a 3 s catalog delay is waited for; a model or effort variant that never appears fails closed, naming it. Live: every run records `catalog_wait_s` (about 0.6 s on 2.0.18). |
| pinned requested model vs actual effective model | the pin is on the session, the agent and the auxiliary agents. Health checks that the server loaded the agent with that model and variant (fake V2 fails closed when it differs). `collect().effective` comes from assistant messages, and the supervisor's `model_check` compares it with the pin. Fake V2: a mismatch is flagged. Live: a real model step reports the pinned model. |
| queue behaviour around completion boundaries | a turn is over only if AEW's last prompt was delivered, an `idle` follows it, none of AEW's prompts is queued, and all of that holds on two polls. Fake V2: the server goes idle while a queued input is undelivered, then starts it; the run ends only after it is answered (`test_a_queue_input_at_the_turn_boundary_is_answered_before_the_run_ends`, through `adapter.send(text, "queue")`, since `harness send` posts `steer` by default). A mutation test (both guards removed) fails. |
| SSE loss or reconnection | completion is decided from the REST API only; the stream reconnects and is counted (`events_dropped`). Fake V2: every event connection is dropped after one frame; the run still ends correctly with its evidence. |
| OpenCode reporting completion while evidence is absent | the neutral scenario `harness_success_without_evidence_moves_no_state`, CI (fake V2) and live |
| permissions doing something unexpected | the projection is golden-tested; health checks that the server loaded AEW's rules as the winning suffix (fake V2 fails closed when they differ; live passes on 2.0.18). A permission request or form is rejected or cancelled and recorded (fake V2). Found and handled here: V2's defaults protect `.env` files (ask) and allow its own output directories; AEW's rules now deny `.env` reads and allow only the run's own output directories. The engine stays authoritative: read-only mutations are refused at submit (`OBSERVATION_MUTATED` in observations, `WORKSPACE_MUTATED` for a reviewer or verifier in a shared workspace; M3-B6). |
| private server startup/teardown under repeated runs | the neutral scenario `repeated_runs_start_and_end_cleanly_with_private_state`, now also requiring every harness process (the server) to exit, CI and live |
| Lead bridge behaving identically to the invocation bridge | `test_both_bridges_hold_the_same_custody_properties` (section 3) |
| OpenCode subprocesses genuinely receiving only the curated environment | the neutral scenario `agent_processes_receive_only_the_curated_environment`, live inside OpenCode's own session shell, with the provider secret present in the server's environment. The Lead TUI: `test_opencode_lead.py`, plus the V2 behaviour (a `--standalone` TUI gives sessions its own environment) found in the 2.0.18 binary. |
| fresh reviewer DB/session isolation | the neutral scenario `a_reviewer_gets_a_fresh_session_isolated_from_the_implementer`. Live: the reviewer run's private state, read through a fresh private server, lists only its own session. |
| delivering a Lead input to a running session (F9-A MS0, 2026-10-10) | the MS0 probe on 2.0.18, on Windows and on Rocky 8 under bubblewrap (`tests/live/f9a_delivery_probe/`, by hand; [evidence](adr/evidence/f9a-delivery-probe-2026-10-10/probe-results.md)). **`steer`** is admitted at the next step boundary (0.04 to 0.08 s after the step ends, no model request between, no tool or model call aborted, post order kept); **`queue`** only when the loop would end, after the model's final tool-free step, so after the turn. Steer overtakes queue: inputs keep their order within a mode, never across modes. **`harness send` chooses between the two modes** (register E55, slice HS1, 2026-10-10): `--when next-step`, the default, posts `steer`, and `--when turn-end` posts `queue`; `next-step` inputs arrive in the order posted, `turn-end` ones one per turn end, and a `next-step` input posted after a `turn-end` one arrives first. **`turn-end` is unavailable while coordination messaging is off** (`TURN_END_NEEDS_MESSAGING`), so with messaging off no Lead path posts `queue`. **While messaging is on, `harness send` records through the coordination store and still wakes a held session** (F9-A's MS5b; until then it is refused `HARNESS_SEND_NEEDS_STORE`, and a run whose launch snapshot of the switch disagrees with the project's is refused `MESSAGING_SNAPSHOT_MISMATCH`). A re-post of an id to the same session is idempotent (200 with the first item, any new text or delivery ignored); a **409** `ConflictError` means the id belongs to another record. 404s are tagged: `SessionNotFoundError` (session loss) against `MessageNotFoundError` (not yet admitted). The shell tool's foreground timeout is a fixed **120 s** (no configuration key; the model's `timeout` overrides it, 0 disables it). The **step limit restarts at each promoted input**, so `max_steps` is not run-wide (register E54). Fake V2 follows these facts from F9-A's MS4 and MS5 (`test_fake_v2_matches_the_ms0_probe_semantics`); MS5 updates this row with the built `deliver` |
| version/capability probing failing closed | the neutral scenario `an_incompatible_harness_fails_closed` (live: a required operation the real server lacks); fake V2: a V1 server, a doctored OpenAPI, a configuration that was not applied, and an agent loaded with a different model, step limit or rules; unit: doctored copies of the real 2.0.18 OpenAPI |

**Not checked deterministically:** which tools a model sees. `/api/session/{id}/context` returns the conversation, not the tool list. The loaded rules are verified by health; the spike showed a denied tool disappears for the model (`m3-opencode-v2-rebaseline.md` §4 #5). The tools an agent actually called are recorded per run (`tools_called`).

## 6. Live results with real models (M3 step 8)

**What ran.** `tests/live/test_opencode_model_live.py`:
- the production `opencode` adapter (nothing scripted) on OpenCode 2.0.18, with free models, a 40-step limit and a 900 s deadline per run;
- each role receives its launch contract as its first message and does whatever it does; the Lead's steps are the test's (a scripted Lead);
- two scenarios:
  - **lifecycle:** implementer, then a reviewer if it submitted a report, then a verifier if the review passed;
  - **rejection and rework** (designer request, 2026-09-28): a seeded, plausible but wrong first implementation, then real models for every later role (§6.2);
- per-role model routing (`AEW_LIVE_ROUTING`) for the asymmetry trials (§6.3).

Raw records: `eval/m3/live/model-trials.jsonl`. Each record names the fixes that were in the code it ran on.

**Asserted on every run, whatever the models do (AEW's side). All held in every run of every trial:**
- the run ends in a terminal status the supervisor derived from the evidence store, and every process it started exits;
- no AEW credential in any file (the run's own scan and a scan of everything the test left); the provider secret the server holds is in no file;
- the effective model and effort are the pinned ones; no other session exists (no subagent);
- every piece of evidence is attributed to its run, credential and execution profile, and verifies;
- the unit's state and the invocation are as the Lead left them: only the Lead's steps moved state;
- a reader's evidence is never accepted from a workspace it changed (M3-B6).

**The clean specimen (designer, priority 1).** The whole live lane (the conformance scenarios, AT-14..AT-17, two lifecycle trials and two rework trials) ran with the checkout otherwise untouched: 25 passed, 1 skipped by design (the forced-model scenario), and the isolation guard was clean. The earlier guard failures were concurrent edits to the checkout (the operator's own documentation work), not the trials.

### 6.1 Lifecycle

Seven trials: five on 2026-09-28 early (three with bash as the agent's shell, two with Windows PowerShell 5.1, `SHELL` unset), and two in the clean specimen. **Every Ticket reached VERIFIED** through a real implementer, reviewer and verifier, the independent hidden test passed, and every change stayed in scope.

| Trial | Agent shell | Implementer | Reviewer | Verifier | Refusals the model recovered from |
|---|---|---|---|---|---|
| 1 | bash | 86 s, 9 steps | 105 s, 6 steps | 62 s, 6 steps | none |
| 2 | bash | 137 s, 11 | 65 s, 4 | 80 s, 7 | none |
| 3 | bash | 106 s, 16 | 102 s, 7 | 94 s, 11 | verifier: `VALIDATION_FAILED` (cited a check not run through AEW) |
| 4 | PowerShell | 108 s, 10 | 116 s, 5 | 172 s, 15 | reviewer: `VALIDATION_FAILED` (invalid YAML); verifier: `WORKSPACE_MUTATED` (wrote its report into the workspace) |
| 5 | PowerShell | 136 s, 11 | 128 s, 10 | 112 s, 8 | reviewer: `VALIDATION_FAILED` ("missing YAML frontmatter": M3-D2); verifier: `VALIDATION_FAILED` (cited a check not run through AEW) |
| 6 (specimen) | bash | 71 s, 8 | 72 s, 4 | 107 s, 7 | none |
| 7 (specimen) | bash | 139 s, 10 | 89 s, 6 | 107 s, 7 | none |

- The effective model matched the pin in every run. No run had a permission request, a form or another session. Cost was 0 (free models).
- Every implementer ran both checks (`guardrails`, `unit`) before submitting. Readers used only `read`, `glob`, `grep` and `shell`; `edit` is denied to them and was never called.
- A run's first step read 3.5–4.1K input tokens: the contract (6.1–7.3 KB) and system text (about 1.0–1.2 KB), plus OpenCode's own overhead. Whole runs used 8–17K input tokens and 1–6K output tokens.
- Implementers mostly also exported `subtract` from `calc/__init__.py`, reading the goal's "through the public module" that way; one reviewer recorded it as an observation.

### 6.2 Rejection and rework

**The fixture.** A Ticket asks for `safe_div(a, b)` with goals `safe_div(7, 2) == 3.5` and `safe_div(1, 0) is None`. Its first implementation is seeded, by a scripted implementer: `return a // b`, with a test asserting only `safe_div(6, 3) == 2` and `safe_div(1, 0) is None`. It passes its own test and the unit check; it is wrong against the goals. Every later role is a real model. Whether anyone catches the defect is recorded, not asserted. When someone does, the Lead returns the Ticket to implementation through its normal authority: a fresh implementer (a new invocation and credential), then a fresh reviewer and a verifier.

**Asserted whatever the models do:**
- a failing review does not advance the Ticket;
- the rejected implementer's credential is dead (`STALE_AUTHORITY`);
- the rejected attempt's stale failing review cannot be ingested for the corrected work (`GATE_UNSATISFIED`);
- the rework implementer is a new invocation, with its own credential and run;
- at VERIFIED, every gate is bound to evidence evaluated on the corrected snapshot, and none to the rejected attempt's evidence.

**Trials** (reviewer 1 is always a real model; "caught" means its review was `changes_required` with the defect as a required finding):

| # | Code | Routing | Reviewer 1 | Rework | Outcome |
|---|---|---|---|---|---|
| 1 | M3-D2, D3 fixed | all roles `longcat-2.5-preview-free` | **caught**, 52 s, 3 steps: F1 blocker (floor division, `safe_div(7, 2)` returns 3), F2 major (the test cannot detect it) | implementer 94 s; fresh reviewer resolved F1 and F2 (117 s) | **VERIFIED**, correct; verifier 100 s |
| 2 | M3-D2, D3 | implementer `mimo-v2.6-flash-free`; reviewer and verifier `space-bunny-free` at **high** effort | **caught**, 33 s: F1, F2, F3 minor | the implementer fixed the code, but wrote its report into the workspace, submitted it and deleted it: its evidence was stale, and AEW refused to send the work to review | stopped (the scenario did not relaunch yet): **M3-D4 found** |
| 3 | M3-D2..D4 | as 2 | **caught**, 22 s: F1, F2, F3 | the same stale report; the Lead relaunched the implementer (rotated credential, continuation marking its evidence STALE): it re-ran both checks and resubmitted | **VERIFIED**, correct. Verifier: `BRIDGE_ERROR` (**M3-D5**), then wrote its report into the operator's repository (**M3-D6**) |
| 4, 5 | M3-D2..D6 (clean specimen) | all `longcat` | **caught** twice, 89 s and 41 s: F1 blocker, F2 minor | implementers 141 s and 97 s; the fresh reviewers passed the fix but named the findings `F1`, `F2` instead of `INV-0002-review-3#F1`, which the Lead's ingest refused | stopped at REVIEW_PENDING, code correct: **M3-D7 found** |
| 6 | all fixed | all `longcat` | **caught**, 80 s: F1 blocker, F2 major | implementer 172 s; fresh reviewer resolved both by their qualified ids (76 s) | **VERIFIED**, correct; verifier 81 s |
| 7 | all fixed | as 2 | **caught**, 38 s: F1..F5 | implementer 75 s; fresh reviewer 59 s | **VERIFIED**, correct; verifier 60 s |
| 8 | all fixed | all `longcat` | **caught**, 66 s: F1 blocker, F2 major | implementer 101 s; the fresh reviewer first named the findings `F1`, `F2`, was refused at submit with the qualified ids (M3-D7's fix), and corrected them in the same run (116 s) | **VERIFIED**, correct; verifier 81 s |

One further trial on the final code (reviewer 1 caught the defect in 66 s; the rework reached REVIEW_PASSED) was cut off during verification by a time limit in the test harness itself: the CLI call around `harness wait` gave up after 180 s (fixed). It is kept in the records and not counted as an outcome.

**What the trials show.**
- **The independent reviewer caught the seeded defect in every trial (9 of 9, counting the one cut off later)**, from the goals and the code alone, although the implementation passed its own test and the unit check. It named the defect as a blocker every time, and every time also named why the seeded test could not catch it (a major finding in seven trials, minor in two).
- **Rejection and rework ran through normal authority.** The failing review left the Ticket in REVIEW_FAILED; the Lead returned it to RUNNING; the rejected implementer's credential was dead; the rework was a new invocation with a new credential and run; the old failing review could not be ingested again; the fresh reviewer resolved the recorded findings; and at VERIFIED every gate pointed at evidence from the corrected snapshot.
- **Model mistakes were caught by engine checks, not harness permissions,** and each refusal message was enough for the model to correct itself in one step: check citations that were not AEW checks, invalid YAML, a report left in the shared workspace (`WORKSPACE_MUTATED`), a reviewer trying to run a check (`PERMISSION_DENIED`).
- **Human intervention: none.** The Lead's steps were scripted; no step needed an operator.

### 6.3 Model asymmetry (designer, priority 3)

Execution profiles are pinned per invocation, so asymmetry needs no new machinery: the execution policy routes archetypes to profiles, each run's `model_check` confirms the pinned model and effort, and each run records its own usage. The trials above used a fast model for the implementer and a model at high effort for the reviewer and verifier. They were also the first live runs of a pinned effort variant (`space-bunny-free#high`: `model_check` matched it every time).

Observed (three trials of free models; anecdotal, not a controlled comparison):
- the high-effort reviewer found the defect sooner (22–38 s against 41–89 s) and added lower-severity findings;
- the flash implementer left its report stale in two of the three (a process mistake AEW caught; the relaunch continuation repaired it once), and did not in the one trial run after the scratch directory existed (one trial shows nothing either way).

**A controlled comparison belongs in the step-9 dogfood,** with paid models: the same rework fixture, at least three trials each of (a) a cheap implementer with a strong reviewer and verifier and (b) a strong implementer with a cheap reviewer and verifier, measuring defect detection, reworks, interventions, tokens, cost and wall time.

### 6.4 Defects found and fixed

Each has a permanent regression, written and seen failing first. All are in `tests/regression/test_m3_live_findings.py` unless named otherwise.

- **M3-D2: text inputs on Windows.**
  - Found live: a report that Windows PowerShell 5.1 wrote as UTF-8 with a byte-order mark was refused as "missing YAML frontmatter"; the model had to inspect the file's bytes.
  - Found while fixing it: UTF-16 files (PowerShell 5.1's `>`) raised an unhandled `UnicodeDecodeError`; stdin was decoded with the ANSI code page on the direct path and in the Lead broker's client (inside a harness run the curated environment sets `PYTHONUTF8=1`, so no trial was affected); with an explicit credential, `aew submit --file -` read stdin twice and submitted the empty second read (an M3 regression of the M1 path).
  - Now every text input (`--file`, `-`, the bridge client, the Lead broker's client) is read once, as bytes, by `aew.util.read_text_input`. A UTF-8 or UTF-16 byte-order mark is honoured and removed; anything else must be UTF-8 or it is a `USAGE` error.
- **M3-D3: tool names in the run's event log.** V2 names a tool in `session.tool.input.started`; `session.tool.called` carries only the call id and input, so the log recorded `"tool": null`. The adapter now maps call ids to names and logs the name, never the input (`test_tool_calls_are_logged_by_name_never_by_input`).
- **M3-D4: a relaunch did not say that evidence had gone stale.** An implementer's report was evaluated on a workspace state that no longer existed; AEW rightly refused to send the work to review; but the continuation a relaunched run receives listed the report as "pass". It now marks each of the invocation's evidence that was evaluated on a different workspace state as STALE and says to record it again. Evidence that is still current is shown exactly as before.
- **M3-D5: a malformed section crashed submit.** A verifier wrote a check citation as `- direct-interpreter-observation: …`, which YAML reads as a mapping: submit raised `TypeError` (`BRIDGE_ERROR` through the bridge). Any malformed but parseable review or verification section did the same. Each section is now validated against its schema, after the engine's own defaults and before anything reads it (`validate_property`).
- **M3-D6: no named place for files outside the workspace.** The contract said "write report files outside the workspace" and named no place. Models guessed: one left its report in the workspace (`WORKSPACE_MUTATED`), one wrote and deleted it there (stale evidence, M3-D4), and one wrote into the operator's own AEW repository (§6.5). Every run now has a private scratch directory, created for it, named in the contract, the preamble and the system text, and in its environment (`AEW_SCRATCH`); OpenCode's tools may use it.
- **M3-D7: resolved findings were checked only at the Lead's ingest.** A fresh reviewer named the findings it resolved `F1`, `F2` rather than `INV-0002-review-3#F1` as the pack lists them. The review was accepted at submit and refused at ingest, after the reviewer's run had ended, so the Lead would have had to dispatch another review. It is now also checked at submit, naming the ids to use, so the reviewer corrects it in the same run.

**Telemetry added.** The run record's `bridge.outcomes` counts each bridge operation's results by outcome (`ok` or the error code), never its arguments or output. The refusals above were found from it, without reading a transcript.

### 6.5 The operator's filesystem

In rework trial 3 the verifier, looking for a place outside the workspace to write its report, built a path under the **operator's own AEW repository** (its root taken from the Python interpreter path that pytest prints), created directories there, wrote its report, submitted it through the bridge, and deleted the file. Only empty directories remained (they were removed).

- AEW's properties held: the submission went through the bridge and was validated like any other; no credential was exposed; no AEW state moved.
- But this is the first live instance of an agent writing outside its workspace into the operator's files. It is within the documented threat model: OpenCode's permissions are not a filesystem boundary, the agent's shell runs as the operator (M3 plan §2.3, M3-B7), and custody, not the harness, protects AEW's authority.
- M3-D6 removes the cause seen here (no named place to write). It does not stop a model that decides to write elsewhere.
- **For dogfood on real repositories (step 9) and the operator's TUI session,** use scratch clones away from repositories the operator cares about. OS-level isolation (a separate account, a container or a sandbox) is the operator's decision.
- **The guarantee is now stated, never implied** (companion review B2; `AEW-INV-ISO-001`). Every run record and `aew harness status` carry `containment: workdir_separation_only`, and `aew doctor` explains it. Real containment is a post-M3 prerequisite for real-repository dogfood and internal alpha (`future-work.md` F2).

### 6.6 Footprint (designer note; `m3-performance.md` §7)

Each lifecycle trial project ended with one open Ticket at VERIFIED: 16.8–17.8 KB of control state, of which 12.2 KB (about 70%) were that open unit's ended invocations and revoked credentials; the live part was 4.6–5.6 KB. A rework trial project (five invocations) held about 21 KB, 11.6 KB of it terminal records.

**Not covered by step 8:**
- a paid model; tasks where a model loops or needs replanning; the integration verifier and publish (step 9's dogfood corpus);
- the real TUI (the operator's session).
