# M4-E plan v3, amendment 1 (v5): split E7 and E8, and run the independent parts in parallel

- **Status:** v5, 2026-10-10, lead developer. v5 answers round 4 (R4-m1) and v4 round 3 (R3-m1, R3-n1, R3-n2), both in "Round 3 changes" below. v3 answered round 2 of the review
  (`AEW-reviews/m4e-amend1-sequencing/REVIEW.md`, "Round 2": R2-m1 to R2-m5, round-2 nits 1 to 8; §0.0). v2 answered
  round 1 (M1 to M4, m1 to m10, nits 1 to 7; §0.1). v1 and v2 are kept unchanged beside this file. It is an implementation-level sequencing change to the approved plan
  [`docs/implementation/m4-e-plan-v3.md`](m4-e-plan-v3.md) §4 and §8. It needs an independent
  CLEAR before any slice below starts. Checked against `origin/main` = `d975a71` (E1 to E5a merged) and E5b as PR #182
  at `f957d00` (open, read only).
- **In the repository:** after its CLEAR, E7a commits this file as
  `docs/implementation/m4-e-plan-v3-amendment-1.md`, linked from `docs/README.md`, as written. Links here are
  repository paths (nit 7). Plan v3's text is not edited (its header rule); deviations go to register rows (§4 below).
- **Why:** M4-E is M4-H's critical path (Q7 v0.3.1 §16), and §4's rule "each slice merged before the next starts" makes
  it one serial lane. The notifier and the launch-failure codes need nothing still open, and the loop needs only E5b.
- **What does not change:** the scope, the designs, every test §6 names (each now has one slice, §2 below), and every
  §7 gate. E3 is before E5. E2 (merged) is before E6b and every E7 slice. There is no authority-granting action on the
  supervisor event path, and no relaunch without proofs. AGENTS.md §3 holds: no slice starts before the slices it
  depends on have merged.

## Round 3 and 4 changes (v4, v5)

| Finding | Fix |
|---|---|
| R3-m1 a clean close in Run never notifies | `broker_gone` fires while Run is effective whatever the cause, with reason `closed` for a closed record (E7a's events). Test case: `test_notifies_with_no_broker_running[clean_close_in_run]` in E7a. |
| R3-n1 the launcher copies a run-directory code | At `harness_ops.py:207-211` the exception carries `reason_code: unknown` and `reason_code_source: run_record` (E8a's site 4); E8b's eligibility test covers the path. |
| R3-n2 a wedged watchdog keeps beating | The liveness record carries `watchdog_tick_at`; a beat whose tick is older than the wedge threshold is `stale`. Test case: `slow_read_is_not_stale` is joined by `wedged_watchdog_is_stale`. |
| R4-m1 the wedge threshold below a legitimate lock wait (nit after CLEAR: the threshold reads the store's own `lock_timeout`) | The wedge threshold is the store's control-lock timeout plus 2 × `POLL_S`, so a watchdog iteration waiting on the control lock is never stale. The cases are stated by duration: `slow_read_is_not_stale` holds the lock for longer than 3 × `POLL_S` and less than the lock timeout; `wedged_watchdog_is_stale` stops the watchdog loop past the threshold (the test injects a short lock timeout). |

## 0. Changes

### 0.0 From v2 (round 2)

| Finding | Fix |
|---|---|
| R2-m1 E8a and E5b overlap | E8a no longer touches `tests/helpers/invariants.py`. That file checks no run-directory record, so E8a's own test pins the closed code, and no invariant number is taken. §3 now lists what remains shared: `future-work.yaml` (F15.2 against F15.6, different rows, `register.py resolve`) and `implementation-status.md` (different sections). |
| R2-m2 two vocabularies, forgeable source | `reason_code` keeps one case convention, lowercase, as its existing values are. n8's names are written `spawn_race` … `unknown`. The vocabulary depends on the status: the closed launch-failure set only on `launch_failed` records, and the adapter codes, unchanged, on every other status. The two sets are disjoint, so the comparisons to `provider_auth_failed` are unaffected. On the record the code stays telemetry. **Carried to E8b:** eligibility takes the code only from the supervisor's acknowledgement, over its pipe to the launcher (`harness_ops.py:195-215`), or from the launcher's own value at site 4. The relaunch record binds that value at failure time. A code read from the run directory (model-writable, `supervisor.py:321`) is never an eligibility input and counts as `unknown`. E8b updates `contract.py:36-37`'s "never decides anything" comment. |
| R2-m3 false `crash` and `stale` | The beat is written by its own small thread, never by the loop that reads the store. `close()`, and the watchdog's return on supersession, write `closed_at`, and the watcher treats a closed record as a clean end, never a crash. Liveness is judged only for a record whose `generation` is the current Lead generation. Two cases are added to the liveness test. |
| R2-m4 starved custodian ending | Dropped "never while a notifier is running". The commit takes `_engine_lock` only, never `_authorizing`. |
| R2-m5 site 4 has no spool writer | E7a's `launch_failed` event comes from the supervisor process only: sites 1 to 3 (`_refuse`, `_launch_failed`, and `main`'s two pre-supervisor records), written to that run's own spool file. Site 4 (custody never acknowledged) has no supervisor and produces no event. The launching caller gets `HarnessLaunchFailed` synchronously, and the run reads `unconfirmed` in `status`, as today. E7a's appends do not depend on E8a's codes. |
| nit 1 | `lead_broker.py:88` reads "M4-E E6b, E7c and E8b" (§4). |
| nit 2 | E7a updates `docs/README.md:31`'s M4-E row in the same edit as the link (§4). |
| nit 3 | E7d's commit records the endpoint's pid and start time, and re-checks "gone, or not registered within `custody_register_s`" inside its transaction (§1). |
| nit 4 | The LWA-17 note goes in F15.5's row as well as F9's (§4). |
| nit 5 | A run's spool file is deleted once the run is terminal and every line in it is delivered or dropped. A pass scans at most 64 files (§1). |
| nit 6 | The `notify` case is its own test, `test_legality_modules_never_import_notify` (§2). |
| nit 7 | E6a's and E6b's review briefs say that E7b may already be on `main` (§1). |
| nit 8 | Register text writes "M4-E E7a" and so on, never a bare "E7a" (§4). |

### 0.1 From v1 (round 1)

| Finding | Fix |
|---|---|
| M1 `anomaly_high` needs E5b | Removed from E7a. E7b delivers it (E7b starts after E5b merges), with its test case. |
| M2 no broker heartbeat | E7a adds a broker liveness record, `.aew/local/lead/broker.json`, beaten every `POLL_S` (by its own thread since v3, R2-m3). `harness/lead_broker.py` is in E7a's files. Recorded as a deviation from §2.8's "existing heartbeat" in F15.5. **Why not defer:** a broker crash is the case N3 exists for. Deferring it would put it in E7b, which is on the critical path. In E7a it costs one small module and about five lines in the broker, off the path, and E7a still starts now. |
| M3 two request events unassigned | `raise_requested` and `confirmation_requested` are in E7a, derived from `steering.requests` (on main), each with a test case. |
| M4 hidden E7a dependencies | E6a and E6b are left truly unchanged. Every event they would own moves to a new slice, **E7d**, after E6b and E7a: `envelope_ended`, `published_under_pic`, `pic_not_exercised`, the envelope case of the N3 test, the endpoint watcher's half of S2 (ending a lost custodian), and `custodian_lost` from worker liveness. E6a keeps S2's `sync` half. E8b states its dependency on E7a outright, for the relaunch `breaker_tripped`. E7a merges long before E8b can start, because E8b waits for E6a. |
| m1 E7 and E8 tests not mapped | §2 assigns every §6 row for E7 and E8, every test named in E7's own section, and every split test to exactly one slice per case. |
| m2 three of "six" are E2's | The three are mapped to E2's existing tests (§2). E7c owns forged pending, single use, ends with its generation, and `test_confirm_is_stale_when_the_action_moved`. |
| m3 E7b before E7c | E7b never executes an action for which `confirm_before(a)` holds. The loop stops with `loop_stopped` reason `CONFIRMATION_UNAVAILABLE`, recorded in `loop.json` and the spool, with no schema change. E7c replaces that stop with the pending record. The Walk test is split. |
| m4 per-activation executable check | E7a reuses E2's raise check (`notifier_problem`, already built). E7b adds the check at each loop activation in `run`, beside `NOTIFIER_UNAVAILABLE`, as the `[loop_activation]` case of `test_run_needs_an_executable_notifier`. |
| m5 "never relaunch" half | E8a tests the mapping only. "Never relaunch" is E8b's `test_a2[unknown_reason_ineligible]`. |
| m6 E8a shape and files | `reason` stays free text everywhere. The closed code goes in `reason_code`. That field is **new** on the acknowledgement and on `HarnessLaunchFailed`'s details. On the run record it already exists (register V1, `supervisor.py:365-367`, adapter end codes such as `provider_auth_failed` on exited runs), so E8a extends it: a `launch_failed` record always carries a code from the closed enum. A second code field would split one meaning. The four sites, corrected line references, the files, and "no typed-surface change until E8b" are in E8a's row. |
| m7 overlap claims | The file lists are corrected, and every expected shared file is named per parallel pair (§3). E8b runs in parallel under the conflict rule and is expected to conflict. |
| m8 records | §4 lists every doc, register, ledger and code-comment touch, and the slice that lands it. |
| m9 trust and isolation | Added to E7a's row: spool lines are untrusted, capped, schema-checked and rate-bounded; spool and liveness events are labelled `authenticated: false`; `close_fds=True`; delivery on its own thread, never under `_authorizing` or `_engine_lock`; the watcher commits nothing; four new tests. |
| m10 `custodian_lost` | E7a covers the `reconcile` mark only. E7d covers worker gone or never registered. |
| nit 1 overstated gain | §5 states the critical path as it is. |
| nit 2 E7b after E6b | Dropped. E7b waits for E5b and E7a, and runs beside E6a and E6b (justified in its row and in §5). |
| nit 3 unnamed launch-failure event | Named `launch_failed`, with its fields. E8b adds `reason_code`, so the field is never conditional on merge order. |
| nit 4 which breaker | E7a: `validation_breaker`. E8b: the relaunch breaker. Same event name, with `subject` naming the breaker. |
| nit 5 TLS-16 | Only E7c changes anything a tool lists: an output schema (`confirmation_required`). No E7 or E8 slice changes the tool list. |
| nit 6 E9 | E9 waits for E6b and E7c (the last slices to change what the live list shows), not for E7d or E8b. |
| nit 7 link | Repository paths, and the in-repository file name above. |

## 1. The slices

| Slice | Content (plan v3 references) | May start | Files (shared ones are in §3) |
|---|---|---|---|
| **E7a** notifier, spool, liveness | **Spool** (§2.8, §2.7): `.aew/local/events/<writer>.jsonl`, one file per writer (each run's supervisor, the broker), so no two processes append to one file. Bounded and rotated like `tool_calls.py`. A run's file is deleted once the run is terminal and every line in it is delivered or dropped. A pass scans at most 64 files, oldest unread first (nit 5). **Liveness** (M2, R2-m3): a small beat thread in the broker, started and stopped with `_watchdog` and never reading the store, writes `{pid, process_started, generation, beat_at, watchdog_tick_at}` atomically every `POLL_S`, where `watchdog_tick_at` is the time of the watchdog loop's last completed iteration, which the beat thread reads from memory (no store read). `stale` also covers a live beat whose `watchdog_tick_at` is older than the wedge threshold, `store.lock_timeout + 2 × POLL_S`, read from the broker's own engine store (`engine/store.py:274, :278`; 60 s by default), so it follows an injected timeout: a watchdog stuck past any lock wait it can legitimately be in (R3-n2, R4-m1). A slower watchdog iteration, such as a `store.read()` waiting on a held lock, is never stale. `close()`, and the watchdog's return on supersession, write `closed_at`. Local, never control state. **Watcher** in `aew operator serve`: control state through `outbox.wait_for`, the spool, and the liveness record. **Delivery** (decision 1): argv, no shell, the sanitized environment, `CREATE_NO_WINDOW`; on POSIX `start_new_session`; past `timeout_s` the process tree is killed; output past `max_output_bytes` is discarded and counted; the delivery log is `.aew/local/notify/deliveries.jsonl`, keyed once per occurrence. A failure is surfaced in `status` and the dashboard attention, with no workflow effect. The raise-time executable check is already built (E2), and E7a reuses it. **Events:** `generation_ended` (`takeover`, `handoff`, `release` from control state; `crash` when the liveness record's process is gone, by the endpoint locator's own pid-and-start-time check, and the record has no `closed_at`; `stale` when it is alive with no beat for 2 × `POLL_S`; both judged only for a record whose `generation` is the current Lead generation, and a closed record is a clean end, not an event); `broker_gone` while Run is effective, whatever the cause (plan v3 §2.8): reason `crash`, `stale`, or `closed` for a record with `closed_at` (a clean exit of the Lead's harness with the seat still held; not a crash, but the away operator is told) (R3-m1); `raise_requested`, `confirmation_requested` (`steering.requests`); `breaker_tripped` (`validation_breaker`); `custodian_lost` (the lease's `reconcile` mark only); `hard_deadline` (the supervisor's deadline stop, `supervisor.py:314-315`); `launch_failed` (R2-m5: written by the supervisor process to its run's spool file at its three failure records, `_refuse`, `_launch_failed`, and `main`'s pre-supervisor records. A launch whose custody is never acknowledged has no supervisor and produces no event: the launching caller gets `HarnessLaunchFailed` synchronously, and the run reads `unconfirmed`, as today. E7a needs nothing from E8a). **Payload** `aew/notify-event/v1`: plan v3's `{event, project_id, subject, reason, ref, revision, at}` plus `source` (`control_state`, `liveness`, `spool:<writer>`), `authenticated` (false unless derived from control state), and an optional `reason_code` (filled from E8b on). **Trust and isolation (m9):** a spool line is untrusted data. Lines over 4 KiB are dropped and counted. Each line is validated against a closed per-writer event enum (`schemas/spool-event.schema.json`). Strings are capped at 512 characters, with control characters removed. At most 256 new lines per file per pass, and at most 10 deliveries per writer per minute; the excess is dropped and counted in `status`. The liveness record is forgeable by the same uid (§2.1's residual) and only ever notifies. One delivery thread with a bounded queue, `close_fds=True` (no inherited endpoint lock or listener handle), never holding `_authorizing` or `_engine_lock`. The watcher reads with the store's read path and commits nothing. | now | new `harness/notify.py`, `harness/event_spool.py`, `harness/broker_liveness.py`, `schemas/notify-event.schema.json`, `schemas/spool-event.schema.json`; `schemas/__init__.py`; `harness/operator_endpoint.py`; `harness/lead_broker.py` (the beat); `harness/supervisor.py` (spool appends); `engine/status_ops.py`; `dashboard/projections.py`; `schemas/execution.schema.json` (description only); comments in `engine/steering.py` (§4). No control-state schema change, no CLI change. |
| **E8a** launch-failure reason codes | n8's closed enum (written `spawn_race` … `unknown`) in `harness/contract.py`, with one mapping function. **Sites:** (1) `_refuse` (`supervisor.py:268-274`, custody refused): record and acknowledgement; (2) `_launch_failed` (`:276-279`, called from `start` at `:202-209`: an `AEWError` by its code, any other exception, start overdue); (3) `main`'s two pre-supervisor records (`:512-523`: no handoff, malformed handoff); (4) the launcher, `engine/harness_ops.py:195-215`, which copies the code into `HarnessLaunchFailed(..., reason_code=...)` only from the acknowledgement, and sets it itself when custody is never acknowledged. On the path at `harness_ops.py:207-211` (custody acknowledged, no started message, the record read from the run directory) the exception's `reason_code` is `unknown`, with `reason_code_source: run_record` in its details, never the record's code (R3-n1); E8b's eligibility test covers this path. **Shape:** `reason` is unchanged everywhere (its readers at `harness_ops.py:205-215, :352, :458, :656`, `stage_intents.py:312` and `tests/helpers/invariants.py:558` keep working). `reason_code` is as in §0.0, R2-m2: lowercase, with the closed launch-failure set only on `launch_failed` records, the adapter codes unchanged elsewhere, and telemetry on the record. A code is mapped only where a test reproduces the failure that produces it. Everything else is `unknown`, so no failure reaches an allow-listed code (`spawn_race`, `server_start_transport`) by default. `harness runs` and `harness wait` already print the record's `reason_code`. The typed surface (`surface.schema.json`, `projection.py`) is unchanged until E8b. Nothing relaunches. | now | `harness/contract.py`, `harness/supervisor.py`, `engine/harness_ops.py`; `harness/opencode/adapter.py` only where a launch error has a distinguishable cause. No `errors.py` change: `AEWError` takes keyword details. No `tests/helpers/invariants.py` change (R2-m1): it checks no run-directory record, and E8a's own test pins the closed code. |
| E5b | unchanged | building (open PR) | |
| E6a | Unchanged, except that S2's custodian ending ships through `sync` only. The endpoint watcher's half moves to E7d. Its review brief says that E7b may already be on `main`, so every stage and class it declares is at once in the loop's reach (nit 7). | after E5b | |
| E6b | Unchanged; no notification work. Its review brief carries the same E7b note as E6a's. | after E6a | |
| **E7b** the loop | E7's host and trigger, Walk, the runtime declaration check (SAE-07), the envelope (M8.4), the hard deadline (`NO_HARD_DEADLINE`, the `low` anomaly), the `expect_rev` interaction (n5), the endpoint-liveness check (`NOTIFIER_UNAVAILABLE`), the executable check at each activation in `run` (m4), `loop_stopped` (spool), `anomaly_high` (watcher, from E5b's `anomalies`), and the static boundary test. **No confirmation yet (m3):** when `confirm_before(a)` holds, the action is never executed, and the loop stops with `CONFIRMATION_UNAVAILABLE`. **Why it does not wait for E6a or E6b (nit 2):** the loop drives whatever stages exist, and needs E5b only for anomalies and dispositions. PIC is exercised by the custodian, never by the loop. If E7b merges first, its stop-set and execution tests, which run over the live stage catalog, also run in E6a's and E6b's CI. A failure there is a real defect in that slice's declarations, fixed in that slice. They gain no other scope. | after E5b and E7a | new `harness/steering_loop.py`; `harness/lead_broker.py`; `engine/steering.py`; `surface/stage.py` (auto-run attribution); `schemas/execution.schema.json` (`execution.steering.envelope`, classified `operational`); `harness/notify.py` and `schemas/spool-event.schema.json` (two events) |
| **E7c** confirmation | E7's confirmation (M8.2, M8.3): the pending record, `confirmation_required` (closed enum in `surface.schema.json`), `aew confirm` through the endpoint, the committed single-use record `steering.confirmations`, expiry, and generation retirement. It replaces E7b's `CONFIRMATION_UNAVAILABLE` stop with the pending path and adds the `confirmation_pending` event. It extends A1 §6's three capability tests to `confirm`. The corpus gains "stale confirmation". | after E7b | `engine/steering.py`, the loop module, `harness/operator_endpoint.py`, `cli/operator_commands.py`, `harness/lead_broker.py` (`OPERATOR_ONLY`), `schemas/control.schema.json`, `schemas/surface.schema.json`, `harness/notify.py` |
| **E7d** the E6 events | `envelope_ended`, `published_under_pic`, `pic_not_exercised` (control state); the watcher's half of S2: it ends a custodian whose registered worker is gone, or that has none after `custody_register_s`, by the same engine operation `sync` runs. That is the endpoint's **first commit**. It is authority-reducing: it marks the lease `reconcile`, releases nothing, and is attributed to the watcher, never to the operator principal. The commit records the endpoint's pid and start time, as every endpoint-made record does (§2.1). Inside its transaction it re-checks "worker gone, or not registered within `custody_register_s`", so a worker that registers at the deadline is never ended (nit 3). It runs on the watcher thread, takes `_engine_lock` only for that commit, and never takes `_authorizing`. It does not wait for the delivery thread (R2-m4). Also `custodian_lost` from worker liveness. | after E6b and E7a | `harness/notify.py`, `harness/operator_endpoint.py` |
| **E8b** relaunch | The rest of E8: policy, the stage-runner placement (N2c), eligibility, the allow-list, per-platform proofs, credentials, the breaker and its `breaker_tripped` (relaunch scope), the relaunch record, `reason_code` on the `launch_failed` event, and `reason_code` on the typed `run` object (display only). **Eligibility's code source (R2-m2):** only the supervisor's acknowledgement, over its pipe to the launcher, or the launcher's own value when custody was never acknowledged. The relaunch record binds that value at failure time. A code read from the run directory is never an eligibility input and counts as `unknown`. E8b updates `contract.py:36-37`'s comment, because from here the acknowledged code decides. It runs in parallel with E6b, E7b, E7c and E7d under the conflict rule, and is expected to conflict (§3). | after E6a, E8a and E7a | `surface/stage.py` (the `launch_failed` stop), new `engine/recovery.py`, `harness/supervisor.py` (observations, event code), `harness/contract.py` (comment), `engine/harness_ops.py` (the acknowledged code to the stage runner), `schemas/execution.schema.json` (`execution.recovery`), `schemas/control.schema.json` (`recovery`), `schemas/surface.schema.json` and `surface/projection.py` (`run.reason_code`), `harness/operator_endpoint.py` (`relaunch_breaker_reset`), the recovery CLI, `harness/lead_broker.py` (`OPERATOR_ONLY`), `harness/notify.py` |
| E9 | unchanged | after E6b and E7c | |

**TLS-16 (nit 5):** E7a, E7b, E7d, E8a and E8b change neither the normal tool list nor any tool schema. E7c changes
one output schema (`confirmation_required`), not the list. The budget test's exact list is unchanged by all six.

## 2. §6 tests per slice

Every §6 row for E7 or E8, then the tests named only in E7's section, then the split S2 tests and this amendment's new
tests. A test with cases in two slices is one parametrized test, and each case is owned by one slice.

| §6 clause or source | Test | Slice (case) |
|---|---|---|
| A3: mode change does not invalidate an in-flight primitive | `test_mode_change_mid_step_leaves_the_step` | E7b |
| A3: recovery setting changes affect only pending recovery | `test_relaunch_setting_change_reevaluates_pending_recovery_only` | E8b |
| A1 §6: an agent shell cannot invoke the confirmation capability | `test_no_operator_principal_outside_the_endpoint`, `test_pty_and_stripped_env_reach_only_the_endpoint`, live `test_lead_identity_cannot_reach_the_endpoint` (`AEW_RL8`) | E2 (built); E7c adds the `confirm` case to each |
| A1 §6 / CWR: unknown or missing effects need confirmation in Walk | `test_walk_confirms_unknown_or_undeclared_effects` | E7b (`never_executes`); E7c (`pending_and_notified`) |
| A1 §6 / SAE-07: runtime | `test_runtime_excess_opens_an_anomaly` | E7b |
| A1 §6: envelope and deadline exhaustion | `test_envelope_exhaustion_stops_the_loop[deadline,max_actions]` | E7b |
| A1 §6: repetition | `test_repetition_stops_after_n` | E7b |
| A1 §6 / CWR: mode never changes legality | `test_mode_never_changes_a_guard_gate_or_transition` | E7b |
| A1 §3.2: hard deadline reduces authority only | `test_hard_deadline_terminates_and_releases_no_lease` | E7b |
| A1 §4 / decision 1: Run needs an executable notifier | `test_run_needs_an_executable_notifier` | E2 (`raise`, built); E7b (`loop_activation`) |
| A1 §4 / decision 1: a delivery failure is visible and has no effect | `test_delivery_failure_is_visible_and_moves_no_revision` | E7a |
| CWR §11: identical stop sets | `test_stop_sets_identical_across_modes` | E7b |
| CWR §11: zero execution of non-auto-runnable or UNKNOWN | `test_loop_never_executes_judgment_or_unknown` | E7b |
| CWR §11: protected-path overlap | `test_protected_path_overlap_stops_every_mode` | E7b |
| CWR §11: a high anomaly stops every mode | `test_high_anomaly_stops_every_mode` | E7b |
| CWR §11: static boundary | `test_legality_modules_never_import_steering` | E7b |
| CWR §11: static boundary, for the notifier (new, nit 6) | `test_legality_modules_never_import_notify` (the legality, gate, transition, dispatch, plan-assurance, lint, evidence-acceptance and publication modules never import `harness.notify`) | E7a |
| CWR §11: policy drift mid-step | `test_policy_drift_between_steps_is_stale_policy` | E3 (built); E7b (the loop's case) |
| CWR §11: auto-run steps attributed | `test_auto_run_steps_are_attributed` | E7b |
| CWR §9: a confirmation binds the projected action | `test_confirm_is_stale_when_the_action_moved` | E7c |
| §10: no false advance, growing to E7 | `test_no_false_advance[stale_confirmation]` | E7c |
| BRP §9 | `test_relaunch_off_by_default`, `test_changed_binding_is_ineligible`, `test_second_failure_raises_attention_only` | E8b |
| A2 §8 | `test_a2[<each>]`, including `unknown_reason_ineligible` (n8's "never relaunch") | E8b |
| N2c | `test_relaunch_only_at_the_stage_launch_failed_stop` | E8b |
| N3: notification with no broker | `test_notifies_with_no_broker_running` | E7a (`takeover`, `broker_crash`: `generation_ended` and, in Run, `broker_gone`; `clean_close_in_run`: `broker_gone` with reason `closed`, R3-m1); E7d (`envelope_ended`) |
| n8: unmapped failures are `unknown` | `test_unmapped_launch_failure_is_unknown` | E8a (the mapping only) |
| TLS-16 | `test_the_normal_list_..._fits_the_budget` | no E7 or E8 slice changes the list (§1) |
| E7 §, n5 | `test_loop_commit_stales_a_judgment_call_which_is_never_replayed`, `test_two_intents_in_flight` | E7b |
| E7 §, N3 | `test_loop_refuses_run_without_a_live_endpoint` | E7b |
| E7 §, confirmation | `test_a_forged_pending_file_never_executes`, `test_confirmation_is_single_use`, `test_confirmation_ends_with_its_generation` | E7c |
| E7 §, confirmation (m2) | `test_operator_serve_refused_in_a_lead_session`, `test_second_live_endpoint_refused`, `test_raise_ends_with_its_generation` | E2, built as `test_the_endpoint_starts_only_with_dev_and_never_in_a_lead_session`, `test_one_endpoint_per_project_and_a_stale_locator_is_replaced_only_when_its_process_is_gone`, `test_a_raise_lasts_only_for_the_generation_it_was_granted_to` (`test_operator_endpoint.py`); no new test |
| E7 §, notifier bounds | `test_notifier_timeout_kills_the_process_tree`, `test_notifier_output_is_bounded_and_counted`, `test_notifier_environment_is_sanitized` | E7a |
| §2.3 S2 (moved by M4) | `test_dead_custody_worker_marks_reconcile`, `test_unregistered_custodian_marks_reconcile` | E6a (`sync`); E7d (`watcher`) |
| §2.8: once per occurrence (new) | `test_event_delivered_once_per_occurrence[<event>]` | E7a (`generation_ended`, `broker_gone`, `raise_requested`, `confirmation_requested`, `breaker_tripped[validation]`, `custodian_lost[reconcile]`, `hard_deadline`, `launch_failed`); E7b (`anomaly_high`, `loop_stopped`); E7c (`confirmation_pending`); E7d (`envelope_ended`, `published_under_pic`, `pic_not_exercised`, `custodian_lost[worker]`); E8b (`breaker_tripped[relaunch]`, `launch_failed[reason_code]`) |
| m9 (new) | `test_spool_lines_are_capped_validated_rate_bounded_and_unauthenticated`, `test_notifier_child_inherits_no_endpoint_handle`, `test_a_slow_notifier_never_delays_a_challenge` | E7a |
| m9 (new) | `test_the_watcher_moves_no_revision` | E7a; E7d narrows it to `test_the_watcher_commits_only_custodian_endings` |
| M2, R2-m3 (new) | `test_broker_liveness_is_local_and_beats_every_poll`, with the cases `clean_close_is_not_a_crash`, `superseded_is_not_a_crash`, `slow_read_is_not_stale` and `wedged_watchdog_is_stale` (R3-n2) | E7a |
| R2-m4 (new case) | `test_dead_custody_worker_marks_reconcile[watcher_with_busy_notifier]` | E7d |
| R2-m5 (new) | `test_launch_failed_events_come_from_the_supervisor_only[refuse,start,handoff]`, and no event when custody is never acknowledged | E7a |
| R2-m2 (new) | `test_relaunch_eligibility_never_reads_the_run_directory_code` | E8b |
| m3 (new) | `test_confirm_before_actions_never_execute[walk,run]` | E7b; it holds unchanged after E7c |
| m6, R2-m2 (new) | `test_launch_failure_carries_a_closed_reason_code[refuse,start,handoff,launcher]`, `test_launch_failure_reason_text_is_unchanged`, `test_launch_and_adapter_reason_codes_are_disjoint_and_lowercase` | E8a |

## 3. Shared files between parallel slices

The conflict rule is v1's: the later merger merges `main` in, resolves, and the resolution gets its own review check
(AGENTS.md §1). For the register and the ledger, use `register.py resolve`. These are the files each parallel pair is
expected to share:

| Pair | Shared files |
|---|---|
| E7a and E5b | `harness/lead_broker.py` (E5b changes one line), `dashboard/projections.py` (E5b: +15/-1), `schemas/__init__.py` (one line each) |
| E7a and E8a | `harness/supervisor.py`: the same launch-failure paths, with different lines |
| E8a and E5b (#182 at `f957d00`) | `docs/implementation/future-work.yaml` (F15.6 against F15.2: different rows, so `register.py resolve` settles it), `implementation-status.md` (different sections). No code file: E8a leaves `tests/helpers/invariants.py` alone (R2-m1), so no invariant number is contested. |
| E7b and E6a | `harness/lead_broker.py`, `surface/stage.py`, different register rows |
| E7b or E7c, and E6b | `harness/lead_broker.py`, `surface/stage.py`, `harness/operator_endpoint.py`, `cli/operator_commands.py`, `schemas/control.schema.json` |
| E7d and E7c | `harness/notify.py`, `harness/operator_endpoint.py` |
| E8b and E6b, E7b, E7c, E7d | `surface/stage.py`, `harness/operator_endpoint.py`, `cli/operator_commands.py`, `harness/lead_broker.py`, `schemas/control.schema.json`, `schemas/surface.schema.json`, `harness/notify.py`, `errors.py` |

## 4. Records: docs, register, ledger and comments

| What | Change | Lands in |
|---|---|---|
| Register wording (nit 8) | The register already has unrelated rows `E7` and `E8` (`future-work.yaml:2314`). Register text therefore always writes "M4-E E7a", "M4-E E8b" and so on, never a bare slice name. | every slice |
| This amendment | Committed as `docs/implementation/m4-e-plan-v3-amendment-1.md`, linked from `docs/README.md` (`test_docs_links.py`). The same edit brings `docs/README.md:31`'s M4-E row up to date (nit 2): it currently reads "slices E1 to E9" and "E3 under way". It becomes the slice list with this amendment and what has merged. Not a ledger source (it is not under `docs/design/` or `docs/research/`). | E7a |
| Register F15.5 Notes (`future-work.yaml:525-526`) | Records the amendment and its deviations: the split; §2.8's heartbeat premise was false, so E7a adds `broker.json`; `aew/notify-event/v1` gains `source`, `authenticated` and `reason_code`; three of E7's confirmation tests are E2's, by the names in §2; §8's count is now 15 PRs by plan v3's counting (E7 becomes four, E8 two; the E3 and E4 splits made while building are not counted here). "Open:" becomes `confirm` (M4-E E7c), the publication grants (M4-E E6b), the loop (M4-E E7b), the E6 events (M4-E E7d). It also gets the LWA-17 note: M4-E does not carry the broker-notifier clause (nit 4; LWA-17 is `tracked_by: [F9, F15.5]`). Rendered to `future-work.md`. | E7a; each later E7 slice updates "Open:" |
| Register F15.6 Notes | "R5-3 is not built" stays true until E8b. Adds: M4-E E8a put the closed launch-failure codes (n8, written lowercase) on the run record's existing `reason_code`, only on `launch_failed` records, and on the acknowledgement. Run statuses are unchanged, so this is no new failure taxonomy in BRP's sense. Relaunch eligibility (M4-E E8b) reads only the acknowledged code. | E8a |
| Register F9 Notes (`:190`, `:211`) | `:211`: the shared diff helper "E7" is now E7b. `:190`: "the broker's notifier once M4-E's E7 lands". No M4-E slice builds a notifier to the Lead (§2.8: the notifier is the endpoint's, and delivers to the operator). Record that, and see §6. | E7a |
| Register F4 Notes (the F4 plan is not edited, per its header) | Maps the F4 plan's E7 and E8 references: the S11 notifier event (`f4-ticket-revisions-plan.md:147, 1814, 1973, 1993`) is E7a; the SAE-07 exclusion and R6's assertion (`:1342, 1995`) are E7b; the confirmation records (`:1993`) are E7c; the confirmer relaunch (`:1996`) is E8b; the broker operator lists (`:1997`) are E6b, E7c and E8b. | E7a |
| Ledger LWA-17 (`requirements-ledger.yaml:2547`) and F9-A1 decision §6 | Not edited: the statement quotes an adopted decision. The F9 row note above records that M4-E does not carry the clause. | E7a (note only) |
| ADR-0017 (`:342`, "E5a, E7 and F4 S2a") | Not edited: it is ledger-gated, and it states the position at its date. The F9 note carries "E7 is now E7b". | none |
| Plan §8 "11 PRs" | Not edited. Recorded in F15.5, as above. | E7a |
| `schemas/execution.schema.json:61` | "Delivery lands with the steering loop (M4-E E7)" becomes "Delivery: M4-E E7a; the loop: E7b". | E7a |
| Code comments | `operator_endpoint.py:27-28` (`confirm` E7c, relaunch breaker reset E8b); `lead_broker.py:88` (M4-E E6b, E7c and E8b: E8b adds the breaker reset's client command to the operator-only list); `steering.py:21` (E7b); `steering.py:111` (E7a). `harness_ops.py:326`'s "E8" is a different E8 (the dogfood report) and is left alone. | E7a |
| `implementation-status.md` | Each slice updates its own capability section, as usual. | each slice |

## 5. The critical path

- **Before (plan v3):** under §4's one-at-a-time rule, after E5b the order is E6a → E6b → E7 (large: notifier, loop
  and confirmation) → E8 → E9. §8 already let E8 trail, so the M4-H path was E5b → E6a → E6b → E7 → E9.
- **After:** two lanes start when E5b merges, and E9 joins them:
  - E6a → E6b;
  - E7b → E7c;
  - then E9, after E6b and E7c.
- **Running now, beside E5b:** E7a and E8a, both off the path.
- **Tails, after E6b:** E7d (small), and E8b (after E6a, E8a and E7a). M4-E is complete when E9, E7d and E8b have all
  merged.
- **The real gain:** E7's notifier leaves the path entirely, and the loop and confirmation (E7b, E7c) run beside E6
  instead of after it. The path becomes E5b + max(E6a + E6b, E7b + E7c) + E9, where it was E5b + E6a + E6b + E7 + E9.
  §8 had already taken E8 off the M4-H path, so E8's split gains nothing for M4-H. It only lets E8a start early.
- **What this does not gain:** nothing on the path starts before E5b merges. The two lanes are of similar size, so
  the saving is roughly the shorter lane, not half. Each later merger in §3's pairs pays a merge of `main` and a
  re-review. The parallel lanes need two reviewers at once.

## 6. Design questions

None for the sequencing. One gap that predates this amendment, reported because the review asked where it lives:
LWA-17 and the F9-A1 decision (§6) say the Lead learns of replies "once M4-E's E7 lands, [through] the broker's
notifier". Plan v3 never had a Lead-facing notifier: its notifier is the endpoint's, and it delivers to the operator.
Until the designer says otherwise, the Lead learns through the attention and resume projections, as today, and the F9
row records that. Whether F9 should own that clause is the designer's question. It does not block any slice here.
