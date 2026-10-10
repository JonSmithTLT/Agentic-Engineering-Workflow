# AEW Implementation Status

This is operational metadata (WC Appendix C). It does not replace the workflow state of any project that uses AEW. It uses the three states from WC §"Status and authority": **Implemented**, **Staged** and **Designed**. A row is Implemented only when the listed evidence exists and passes on both Windows (Python 3.13) and Linux (Python 3.11). The acceptance IDs are listed in `acceptance.md`.

**Spec set:** `aew-frozen-2026-09-25`.

- **M1** (serial slice) and **M2** (Epic/Story hierarchy, non-mutating Tickets, Investigator/Researcher/Planner dispatch) are accepted and merged. M2: `adef640`, PR #4, after two independent review rounds (`m2-reviewer-brief.md`, `review-response-2026-09-27.md`; ADR-0007, ADR-0008).

- **M3 (OpenCode V2 harness adapter) is accepted and merged:** `169af1d`, PR #5, tag `aew-m3-accepted-2026-10-01`. The plan is `m3-ambiguity-report.md`, and its evidence is `m3-reviewer-brief.md`. The independent review of the freeze (`aew-m3-freeze-2026-09-30`, `9372f44`) did not accept it, over R1 and R2. Those fixes, with B1 from AEW's own review of the same tag, are in `review-response-2026-10-01.md` and were merged by PR #6. The operator accepted M3 on 2026-10-01 on that basis, without a re-review. ADR-0009 and ADR-0010 are accepted, and `opencode.md` is the operator's guide.

- **The M4 prerequisite is done:** hot/cold control state (ADR-0011) is implemented and accepted, with E5 first, by the approved plan `adr-0011-implementation-plan.md`. P1 (E5) #15, P2a #17, P2b #18, P2c #20, P2d #21 and the acceptance gate P3 #24 (`42239e1`, 2026-10-03), after its independent review and re-review fixes.

- **M4 is under way** (mutating concurrency above 1; `m4-ambiguity-report.md`, approved). **M4-A is built:** one dispatch predicate (`DispatchDecision`) over a declared entrypoint registry, enforced at commit; protected conditions; Class 0 eligibility; plan lint; `aew work reclassify`; coverage with a ratchet in CI (E2). **M4-B is built:** OS filesystem containment and process ownership on Linux (bubblewrap per run, run-private git state, fail-closed launch, truthful labels). **M4-C is built** (2026-10-04): per-Ticket worktrees for N > 1 mutating Tickets, the cap as an admission rule, serialized CAS publication. **Next: M4-D**, the integration queue and lease with the transaction outbox (ADR-0012; its first slice, D1, is PR #53).

- Deferred and designed work is tracked in `future-work.md`, and each milestone's plan triages it. All findings of the independent M1 review, and of the focused re-review of its remediation, are resolved (`review-response-2026-09-26.md`), and all three reviewers' probe files pass unchanged as regressions in `tests/regression/`. Since 2026-09-27 CI runs the suite as parallel lanes per OS behind a single `assurance` merge gate; see `testing-and-ci-strategy.md`.

## Capabilities

This is the status table of WC Appendix C, one section per capability: a **Status** paragraph and an **Acceptance evidence / next action** paragraph, each on one line, with blank lines between, so that changes to different capabilities never touch neighbouring lines and merge without conflict (`tests/unit/test_docs_merge.py`). Add a capability as a new section where it belongs: two added at the same place are the one case git still conflicts on. No line records the last update: the history is `git log -- docs/implementation/implementation-status.md`.

### AEW v0.7 design + KC v0.4

**Status:** Implemented (frozen, pinned)

**Acceptance evidence / next action:** Tag `aew-spec-frozen-2026-09-25`, `docs/spec-pin.yaml`, `tests/test_spec_pin.py`

### Persistent Lead + reconstruction

**Status:** Implemented

**Acceptance evidence / next action:** AT-1 (session destroyed mid-flight, caches deleted, `aew resume`, operator takeover, reconcile, completion)

### Crash-safe, stale-writer-resistant control state

**Status:** Implemented

**Acceptance evidence / next action:** AT-4a/4b; ADR-0001, ADR-0005; review probes M1/M8; seeded adversarial walk with the invariant oracle (`tests/regression/`). `project.yaml` and every policy file it names are hash-pinned: an edit outside AEW refuses Lead changes until the operator's `aew manifest adopt` (ADR-0001, amendment 2026-10-06)

### Hot/cold control state (terminal records archived out of the commit point)

**Status:** **Implemented** (accepted at P3, PR #24, 2026-10-03)

**Acceptance evidence / next action:** ADR-0011; `adr-0011-implementation-plan.md`.<br>Built: `src/aew/history/`, meaning the hash-chained manifest (R1), sealed segments, the derived `local/history.sqlite` index, verification, and pre-written records (R8, `Session.prewritten`). Tests: `tests/unit/test_history_manifest.py`, `tests/integration/test_history_store.py`, and real-process kills at each history fault point in `test_store_processes.py`.<br>Archival (P2b): finished units leave the hot state at the commit that finishes them (`engine/archive_ops.py`). Tests: `tests/integration/test_archival.py`, `tests/unit/test_archive_model.py`, and oracle rules 19–23.<br>History surface and audit (P2c): `aew history show|list|links|load|audit|reindex` (`engine/history_ops.py`), audit status in `status`, and the Epic-closeout audit check. Tests: `tests/integration/test_history_surface.py`.<br>Migration (P2d): `aew migrate` (`engine/migrate_ops.py`); a v1 project's Lead mutations are refused until it runs. Tests: `tests/integration/test_migration.py`, and the H1 regression in `tests/regression/test_m3_control_plane_scale.py`.<br>Acceptance (P3): H1–H4 and A1 on Windows, Rocky 8.10 (WSL kernel) and Ubuntu; results in `adr-0011-implementation-plan.md` §7.4 and `eval/adr-0011/perf/`. Hot-state cost now tracks open work, not completed history.

### Explicit raw-history search (register F21, Arm B prototype)

**Status:** **Prototype built; off by default and absent while off; not evaluated**

**Acceptance evidence / next action:** The lead developer's plan v6. `recall.raw_history_search: "off" | explicit` in the execution policy (`"off"` quoted: a YAML boolean is refused with its cause and fix), read from the adopted bytes only (`aew.engine.recall.recall_search_enabled`); off, `aew history search` is not registered (help, usage and argparse's choices unchanged) and no file is created. On, it searches `local/recall/history-fts.sqlite` (ADR-0013 D8's note of 2026-10-07), built only by a bounded search catch-up, `history reindex` and the full audit, never on a commit path; every hit is authenticated and re-matched against the authenticated text, so a tampered substrate can hide a result until it is rebuilt but never invent one. Refused inside an invocation (a discoverability guard). Not model-visible: no pack, resume, guide, surface row, MCP tool or dashboard route; absent from the Q7/M4-H treatment. `tests/integration/test_history_search.py`, `tests/unit/test_history_search_parser.py`. Next: F19's A/B evaluation, after the implementation-readiness package of the knowledge adoption record (`decisions-2026-10-09-knowledge-system-adoption.md` §8; the designs were adopted 2026-10-09)

### The transaction outbox: the transition log as a typed, complete, chained event source

**Status:** **Partly built (M4-D slice D1)**: typed events derived in the store, the 64-event hot bound with an overflow sidecar, the hash chain, `aew history log --since R [--kind] [--follow]`, the `local/wake` signal. Sealing and compaction are D2

**Acceptance evidence / next action:** ADR-0012; ADR-0001 amendment 2026-10-04; oracle rules 24 to 26 (`tests/helpers/invariants.py`, `tests/helpers/store_model.py`); `tests/unit/test_outbox.py`, `tests/integration/test_transition_log.py`

### Command/skill interaction layer

**Status:** Implemented (commands, OpenCode); skills Staged

**Acceptance evidence / next action:** `aew opencode` gives the Lead `/aew-resume`, `/aew-status`, `/aew-ticket`, `/aew-next`, `/aew-handoff` (ADR-0009; `opencode.md`). Skills: see Specialist skills

### AEW Knowledge Contract

**Status:** Implemented (M1 slice + M2 hierarchy)

**Acceptance evidence / next action:** Manifest, logical names, current state, handoff/checkpoint, Ticket/Story/Epic records, plan revisions, provenance, guardrail/build-test policy, `init`/`status`/`resume`, cache loss, existing-authority project

### Ticket/Story/Epic work model

**Status:** Implemented (M2)

**Acceptance evidence / next action:** ADR-0007, ADR-0008; AT-8..AT-13; `tests/integration/test_hierarchy.py`, `test_non_mutating.py`; `tests/regression/test_m2_compositions.py`, `test_hierarchy_walk.py`, `test_m2_review_2026_09_27.py`; oracle rules 6–14. The parent state is derived; closeout and cancellation are Lead decisions; parent gates are evaluated against the parent snapshot; the non-mutating path (dispatch, attempts, observation workspaces, record freshness, `INPUT_STALE`, evidence-only completion); moves, promotion, dependency edits (never changing a started attempt's dependencies); fail-closed ancestor plan bindings on every risk path; attempts bound to the dependencies they were dispatched with; observation integrity rechecked at ingest

### Ticket revisions (register F4)

**Status:** **Partly built (S1 of [the F4 plan v8](f4-ticket-revisions-plan.md))**: the field-group registry, canonicalization and live digests; not yet called by the engine, so no behaviour changes and F4 is dormant everywhere

**Acceptance evidence / next action:** Built: `src/aew/schemas/ticket-field-registry.v1.json` (identity `aew/ticket-field-registry/v1@<sha256>`), `engine/ticket_fields.py` (`canonical`, `live_digests`, `changed_groups` comparing registry versions, `material`); ADR-0016 §1. Every unit key and record field is classified (`test_every_ticket_field_is_classified`, invariant 50). Tests: `tests/unit/test_ticket_field_registry.py`, `tests/unit/test_ticket_digests.py`.<br>Next: S2a (enablement, the format raise in the store's commit path, the interim hierarchy refusals).

### Role archetypes + role-card catalog

**Status:** Implemented (M2 scope)

**Acceptance evidence / next action:** ADR-0006 (+ M2 amendment): investigator/researcher/planner dispatchable with built-in default cards; the executor card and `expected_kind` are pinned at dispatch. Per-card output-contract payload schemas: Designed

### Hierarchical context packs, resume and status

**Status:** Implemented (M2)

**Acceptance evidence / next action:** Hierarchy section in every pack; investigator/researcher/planner packs; parent reviewer/verifier packs with every child's own integrated change; `aew work tree`; resume shows attempts, inputs, acknowledgements and per-parent next actions (AT-11)

### Read-only concurrency

**Status:** Implemented (observation workspaces)

**Acceptance evidence / next action:** One detached observation per read-only invocation; optional `non_mutating_concurrency` policy (AT-12). Shared observations: not used (stricter than WC §8.1 permits)

### Project maps: the structural codebase map (register F22.1, T5-A)

**Status:** **Implemented (F22.1, two pull requests)**: `aew map generate [--commit H] [--select --expect-map-rev E:N]` and `aew map select-architecture EVIDENCE-ID --expect-map-rev E:N` (Lead), `aew map show [--commit H | --root SHA] [--section NAME]` and `aew map diff (--root SHA | --commit H) (--root SHA | --commit H)` (reads). The record (`aew/codebase-map/v1`) is generated from the Git objects of one commit through one tracked read API, stored immutable and content-addressed under `.aew/local/maps/`, and selected in the map registry with its own revision (`<epoch>:<map_revision>`, never `control_revision`); freshness against a commit is computed, never stored. The architecture reference is an existing discovery record, labelled with its evidence's freshness. **In context only behind the execution policy's `maps.pack_slices: structural`, `"off"` by default** (written quoted: YAML reads a bare `off` as a boolean, refused with that cause; packs and the resume view are then byte-identical to a project without maps): the bounded slice in packs of roles whose context names `codebase_map` (today the investigator), pinned in the pack's sources (with the slice itself, so a map removed or damaged after dispatch never changes a regenerated pack or refuses a launch), and the resume row. No pack, gate, transition, dispatch or launch depends on a map. Measured (Windows, `tools/perf/structural_map.py`): 0.67 s at 10,000 paths and 3.0 s at 100,000, four git processes each; no very-large-repository support is claimed beyond 100,000 paths

**Acceptance evidence / next action:** ADR-0015 (and its amendment of 2026-10-07); project maps v0.5 §2, §3, §10, §11; `src/aew/maps/`; `tests/unit/test_structural_map.py` (goldens in `tests/fixtures/maps/`, the no-side-path AST check), `tests/unit/test_map_store.py`, `tests/unit/test_map_slices.py` (the switch and its YAML-boolean refusal, bounds, placement, inert names, pinned regeneration), `tests/integration/test_structural_map_git.py` (Git-object binding, the differential oracle, freshness, edge cases, the partial-clone refusal, the commands), `tests/integration/test_map_context.py` (byte identity with the switch off, pinned provenance, the resume row, architecture selection and its untouched control state, the no-authority walk, a map damaged after dispatch through launch, relaunch and rotation), `tests/regression/test_structural_map_scale.py` (counts at 10,000 paths)

### Plan-driven child materialization

**Status:** Designed

**Acceptance evidence / next action:** Children are created by the Lead; a plan does not generate them

### The read-only dashboard's server (register F20.2 to F20.6)

**Status:** **Partly built (F20.2 to F20.5; F20.6's server half)**: contract 0.1.2's GET and HEAD projections on stdlib `http.server`, each validated against the contract in the tests; a lock-free committed-state reader (`ControlStore.read_committed`); seq-pinned History cursors and revision-pinned hot cursors; `aew history list --before`. The operator session (F20.3): `aew dashboard serve|open|status`, the `operator_session` credential kind (ADR-0005, 2026-10-05) minted after the typed-back code, delivered as a one-time URL, held as an `HttpOnly` cookie, verified by the engine's lookup over the server's in-memory table, dead when the server stops. Conditional requests (F20.4): a strong `ETag` over the representation less the snapshot's time, in the request scope; `If-None-Match` gives `304`, never for `W/` or `*`. Server security and the frontend (F20.5): the production build of frontend commit `4f0a710`, made by the pinned offline builder and committed in the package with `BUILD.json`, served with the SPA fallback; R21's header set on every response; the exact Host and Origin rules; methods and request bounds; the redacted request log. Integrated acceptance (F20.6): the server half is recorded in `docs/archive/reviews/dashboard-main-line-acceptance-2026-10-05.md`; the browser gate waits for the web side's live runner

**Acceptance evidence / next action:** [design note](../design/proposals/dashboard-main-line-api-design-v0.1.md) §4, §5; `src/aew/dashboard/`; `tests/integration/test_dashboard_api.py`, `tests/integration/test_dashboard_session.py`, `tests/integration/test_dashboard_conditional.py`, `tests/integration/test_dashboard_security.py`, `tests/integration/test_dashboard_acceptance.py`

### Backlog import (SPT remediation backlog)

**Status:** Staged

**Acceptance evidence / next action:** AT-13 proves a generic backlog of that shape is representable and executable; importing the real backlog follows M2's acceptance

### Card-level path restriction (`restrict.paths`)

**Status:** Designed

**Acceptance evidence / next action:** Review N1: the schema rejects it (fail closed); in M1, path limits come from Ticket scope + guardrails

### Harness boundary: runs, rotation, credential custody

**Status:** Implemented (M3)

**Acceptance evidence / next action:** ADR-0009, ADR-0005 amendment; AT-14..AT-17 (fake harness and OpenCode, CI and live); the five custody properties on both sides (`harness-conformance.md` §3); `tests/regression/test_m3_harness_adversarial.py`; oracle rules 17 and 18. No raw credential reaches a model-controlled process

### Execution profiles (harness, provider, model, effort per invocation)

**Status:** Implemented (M3)

**Acceptance evidence / next action:** ADR-0010; `tests/unit/test_execution_policy.py`; AT-14 (per-role routing); `model_check` on every run (147 of 147 matched in the dogfood)

### Governed stages on the typed Lead surface: the StageIntent journal (M4-E E3, register F15.2)

**Status:** **Built (E3 of [the M4-E plan v3](m4-e-plan-v3.md): E3a, E3b and E3c)**; the stage tools that use it are E4 and E5

**Acceptance evidence / next action:** Built: the journal in the engine (`engine/stage_intents.py`, schema `aew/stage-intent/v1`). A stage opens its intent by CAS on the caller's revision as its first commit, binding the call, both policy digests, the Lead generation, the subject's state and the planned, declared primitives. Each step commits with its primitive under the key `<SI>:<n>`, recorded by a Lead-transaction finalizer that runs first and refuses a step that repeats or comes out of order, commits a primitive other than the one planned (`step_primitive_mismatch`), replays a judgment (`judgment_replay`), belongs to a superseded generation (`not_owner`: never continued implicitly) or runs under a changed legality digest (`STALE_POLICY`); the operational digest is recorded, never enforced. Opening refuses an undeclared primitive, one that cannot run as one step (`not_a_step`: it commits twice, or shares its op so the commit cannot say which ran) and an effective class below the stage's or a step's (`class_understated`); a stop names the next step (`stop_out_of_order`); a unit, and the project, has at most one unfinished stage. An intent is hot only while ACTIVE; one that ends (COMPLETED, STOPPED_AT_BOUNDARY, REFUSED, ABANDONED) is written immutably under its unit (pointed to, then pinned and linked by its bundle), annotated on an archived unit, or kept in `records/stage-intents/`, and read back without scanning. Invariants 47-49. Tests: `tests/integration/test_stage_intent.py`, `tests/regression/test_m4e_stage_journal_scale.py`, `test_m4_schema_downgrade.py`.<br>**E3b, the executor** (`surface/stage.py`, called by `run_tool` for a tool with a planner): it opens the intent by CAS on the caller's `expect_rev` (a stale one commits nothing), runs the planned primitives from the revision the intent's commit returned, each through its step runner with its step armed, and stops at the first refusal, keeping the committed steps (rules 1 to 3). A later `STALE_REVISION` is retried once only under R5-1's five conditions (a non-judgment step of a non-judgment stage, the legality digest unchanged, authority still held, the action AVAILABLE now with the same arguments); a guard that is not yet a queryable dispatch decision is UNKNOWN and never retries (E4 migrates the guards), and the retry is marked on the intent and in `completed_steps` (rules 4 and 5). A moved legality digest stops it as `stale_policy`, before any retry (rule 6); an assignment made with `launch` records run 1 in its commit (`dispatch.launch`) and its step runner then hands the run to its supervisor, as `aew work assign --launch` does, so a launch that fails after its dispatch committed stops the stage as `launch_failed` with the run standing on the intent and in the result, and a stage never completes over a run that never started (rule 7). A stop it cannot record (a lost seat, a policy edit awaiting adoption) leaves the intent ACTIVE and the result says why; a refusal met while deciding on a retry stops the stage the same way, with its committed steps reported. A step's argument may name an id an earlier step recorded in the journal (`$from`); opening refuses a reference to a step that is not an earlier one or to a field no step records (`malformed_reference`, `reference_not_earlier`), so a bad plan commits nothing. The result carries `stage_intent_id` and `policy_binding`. No stage tool is built yet: the Ticket stages land with E4 and E5; the step runners are `checkpoint` and `work.assign`. Tests: `tests/integration/test_stage_runner.py` (`test_stage_intent_rules[cas,intent_first,first_refusal,stale_retry,no_replay,drift,launch_failed,takeover]`, `test_judgment_bearing_stages_never_retry`, `test_a_supervisor_that_cannot_start_stops_the_stage_as_launch_failed`, `test_a_takeover_before_the_retry_decision_means_no_retry`, `test_a_plan_with_a_bad_step_reference_commits_nothing`).<br>**E3c, resume and resolve** (`surface/stage.py`, `engine/stage_intents.py`; §3.4 rule 8). `resume`, the typed tool and `aew resume` alike, lists every unfinished intent with `safe_to_continue` (every recheck a continue makes passes now; a check that cannot be answered yet, today a guard that is not queryable, counts as passing and is named in `unknown_checks`), each recheck (the policy, the stage contract and plan, the step runners, the subject, a launching step's run, the continue count, the next step's guard), the call a continue endorses (its bound arguments, judgment inputs and classes), the next planned step, the boundary a continue would stop at, and the owning and current generations; `status` and every projection name it as the `RESOLVE_STAGE` decision (no default). The typed `resolve` tool (`choice: continue | abandon`, a rationale that is never blank) and `aew stage continue|abandon` (the same runner and result; Lead-reachable) are the current Lead's explicit choice. **Abandon** ends the intent ABANDONED; committed steps stand. **Continue** re-resolves the stage contract and plan from the surface's catalog, refuses a next step whose dispatch decision refuses it now (`next_step_blocked`), and in one commit rechecks the legality digest (`STALE_POLICY`), the contract (`contract_changed`) and the subject as its last step left it (another primitive moved it: `subject_moved`), then rebinds the intent to the current generation (F18 §14; recorded in `rebound` with the rationale) and runs the remaining steps from the first uncommitted one under rules 3 to 7. A refused continue commits nothing and leaves the intent ACTIVE. Authority is the caller's credential and the revision its `expect_rev` CAS. **The #142 obligations:** a launching last step's run with no supervisor record, or one no longer starting or running, stops the intent as `launch_failed` in the continue's own commit, never COMPLETED, with the run standing (a run that ended is advised to be read, `harness_status` and its report, before any relaunch); the continue never relaunches and never uses the credential lost with the crashed launcher: the relaunch is the Lead's `harness.launch` (`aew harness launch`), which records a new run under a rotated credential. `stage.resolve` is a declared judgment-bearing primitive that no stage may plan. Invariant 51 (each continue is a chained rebind; the latest resolution matches the record). `tests/helpers/stage_equivalence.py` compares end states without the journal's own records (plan v3 M11.5). The normal advertised surface is 5,135 bytes with `resolve` (4,486 before; `resolve` takes 648 (its compact `tool_entry`) of the 771 bytes §2.6 measured for it with E5's dispositions). Tests: `tests/integration/test_stage_resolve.py` (`test_continue_never_completes_a_stage_over_a_run_that_never_started[never_started,ended,live]`, `test_a_continued_launch_relaunches_only_through_harness_launch_with_a_rotated_credential`, `test_takeover_mid_stage_needs_explicit_continue`, `test_continue_after_an_intervening_primitive`, `test_drift_seeded_between_every_substep`, `test_policy_drift_between_steps_is_stale_policy`, `test_a_continued_stage_ends_where_an_uninterrupted_one_and_its_primitives_do`, `test_the_equivalence_view_keeps_real_differences`).<br>Next: E4 (queryable guards). One obligation from E3b's launch handoff (#142 review) remains: **E5a** reconciles `ticket_start`'s catalogued `dispatch.launch` step with the launch now inside the assignment step (plan v3 §1 and E4 put `dispatch.launch` inside the dispatch's commit). Until then it fails closed: `dispatch.launch` is undeclared, so no plan naming it opens.

### The run cost and usage ledger (register F25)

**Status:** **Partly built (slice 1 and slice 2a of [the design v0.2](../design/cost-usage-ledger-design-v0.2.md) §7)**

**Acceptance evidence / next action:** Built: the bounded `aew/run-usage/v1` record and `normalize()` with its trust labels and the closed `token_semantics` enumeration (`harness/usage.py`, `schemas/run-usage.schema.json`); the OpenCode adapter's `usage_record` (with `truncated` from its paging) and the supervisor's `result.usage_record` with the wall time; the adapter's per-version, per-provider semantics mapping, qualified only for OpenCode 2.0.18 with `openai` (`disjoint`, from source; every other provider is `unknown` and never priced); the price table schema `aew/pricing/v1`, its content-addressed snapshots, the derivation with every unpriced reason, `copy_run_usage`, and the projections with `scope`/`archive_complete` (`engine/usage_ops.py`). Tests: `tests/unit/test_usage_record.py`, `test_usage_ops.py`, `test_usage_conformance.py`.<br>**Slice 2a:** the copy (R5) as a Lead-transaction finalizer before archival (`usage_ops.UsageCopy`): every transaction that ends or relaunches an invocation copies its ended runs, and archival copies every run of the units it archives, so a bundle carries complete usage; a run still live stays `provisional` (R6) while its invocation can still copy it, and archival records one still live then with its observed status and absent usage (R5). A malformed run record or price snapshot never fails the transaction: the copy checks every field it reads, and a record that does not parse, nests past the parser's depth or holds a non-finite number is treated as no record. The run directory's reads (`harness/runlog.py`) follow no link, never block on a FIFO or device, and read a record only up to 16 MiB: a record or heartbeat that is not a regular file is none (`tests/unit/test_runlog_reads.py`). `inv.runs[]` and its `usage` are declared in the control schema; invariant 46 (a well-formed record of its own run, at most 2 KiB); a usage copy derives no event. The manifest's optional `policy.pricing` is a classified policy file, every field operational (a price edit never stales a dispatch decision), validated at adoption and read from its pinned bytes. Tests: `tests/integration/test_usage_ledger.py`.<br>**Slice 2b, the doctor:** `aew doctor` reports `policy:pricing` (no table is INFO, never a failure; a named table that is malformed, missing or drifted FAILs), `pricing-snapshots` (FAIL for a snapshot a hot or recently archived usage names that is missing or damaged, and for any file in `.aew/pricing/` that is not the snapshot its name says; bounded to the hot state and the recent ring: a snapshot only an older bundle names is not checked, and `aew usage show --all` will report it unpriced) and `usage-ledger` (hot runs recorded, provisional and missing; WARN when a run's usage is lost) (`usage_ops.pricing_doctor`, `snapshot_doctor`, `ledger_doctor`).<br>Next (slice 2b): `aew usage`, the `status` summary and the H2 re-measure with a 2 KiB usage on every open run; the Lead part waits for the designer (decisions-due, F25).

### Lead-worker coordination messages (register F9, F9-A)

**Status:** **Partly built (MS0, MS1 and MS2 of the F9-A plan v4: the live-delivery probe, the coordination store and thread sealing); off by default and absent while off**

**Acceptance evidence / next action:** [ADR-0017](adr/0017-coordination-messages.md). `coordination.messaging: disabled | enabled` in the execution policy (absent is disabled), read from the adopted bytes only; `surface.presentation: standard | compact` is accepted and changes nothing yet. Enabled, the engine records a Lead message to an active worker (`message_record_lead`, with `expect_rev`) and a worker's reply on its own thread (`message_record_worker`), and reads a thread (`message_thread`): one append-only, hash-chained JSONL file per invocation under `.aew/work/<T>/coordination/`, written under the control lock without a commit (no revision moves), with `MSG-<INV>-<n>` ids, idempotency scoped by sender and generation, replies within the thread, bounded and scoped refs, and the project marker `.aew/coordination/marker.yaml`. `message.send` is a declared primitive listed in `NOT_STEPS`. No surface exists yet: no tool, command, bridge operation or prompt line. Off (the default and M4-H's treatment), nothing is written and `aew init`'s policy bytes and digests are the ones from before F9-A. `tests/integration/test_coordination_store.py`.<br>**MS2 (sealing, 2026-10-10):** every commit that ends a messaged invocation seals its thread with an immutable, content-addressed seal record (`aew/coordination-seal/v1`: the thread's sha256 and size, `damaged` when its chain does not verify to the end, the undeliverable Lead messages and the worker messages no Lead saw), pointed at from the unit, named in the commit's refs, pinned by the unit's bundle and followed to the thread by `history audit --full`: the `Coordination.finalize` finalizer before archival, explicit calls on `lead acquire`, `lead handoff accept` and `lead takeover`, and `Session.commit`'s check, which seals a missed ending by fallback (recording `coordination.seal_fallback`) and refuses one in an archiving commit (`THREAD_UNSEALED`). A sealed thread accepts nothing. Unseen worker replies are held in `coordination_unseen` (at most 20, with an omitted count and range) until `message_mark_shown` records them, and `aew message unseen` recovers the omitted ones. Adopting `enabled` registers the project (`coordination_store`), which recording now needs and an engine before MS2 refuses. Evidence records the Lead messages its invocation had (`coordination_inputs`). `work show` and `history show` gain `coordination`, and the operator reads `aew message thread|list|unseen` exist only while messaging is on or a thread exists, never inside a run; `doctor` reports an ended thread without a seal. Oracle rules 52 to 58. `tests/integration/test_coordination_lifecycle.py`. **MS0 done (2026-10-10):** the live-delivery probe of OpenCode 2.0.18 on both hosts decided the transport, `steer` (ADR-0017 D8, with its [evidence](adr/evidence/f9a-delivery-probe-2026-10-10/README.md)); the probe is `tests/live/f9a_delivery_probe/`, run by hand. Next: MS3 after M4-E's E4

### Filesystem containment for harness runs

**Status:** **Linux: built (M4-B).** Windows: workdir separation only

**Acceptance evidence / next action:** Linux: a bubblewrap sandbox per run from its role, applied to every harness process and check, fail closed with a launch self-test; filesystem integrity, not confidentiality, no network isolation (ADR-0009, M4-B amendment). Windows: `workdir_separation_only`, labelled on every run and in `aew doctor`. Real-repository dogfood stays Linux-only and waits on the gate's remaining conditions (`future-work.md` §1)

### R1 Reviewer

**Status:** Implemented (scripted roles and real models)

**Acceptance evidence / next action:** AT-1, AT-5, AT-16; reviewer packs exclude implementer reasoning. Real models caught a seeded defect 9 of 9 (step 8), 4 of 4 (dogfood T5) and 6 of 6 (model comparison)

### Independent Verifier

**Status:** Implemented (scripted roles and real models)

**Acceptance evidence / next action:** AT-1, AT-3, AT-6; step 8 and the dogfood. It cannot catch a goal met by changing its own inputs (dogfood T4; `future-work.md` O3, F14)

### OpenCode harness adapter

**Status:** Implemented (M3; OpenCode V2 2.0.18, real runs on Windows)

**Acceptance evidence / next action:** ADR-0009; `opencode.md`; conformance in CI against a fake V2 server serving the real 2.0.18 API description, and live on 2.0.18 (`harness-conformance.md` §6); the paid dogfood (`m3-dogfood-report.md`). Linux: CI only

### Specialist skills

**Status:** Staged

**Acceptance evidence / next action:** Cards name skills. M3 exposes none: a run records its card's skills as unavailable (ADR-0006 M3 amendment). Reachable skills come through the capability registry (`future-work.md` D3, F12, F13)

### Host/container tools

**Status:** Designed

**Acceptance evidence / next action:** SPT Epic "Toolchain Readiness" (dogfood)

### Workbench Capability Contract

**Status:** Staged

**Acceptance evidence / next action:** Cards and archetypes carry capability names; authority-sensitive capabilities are enforced. Provider resolution and health come in M6.

### Remote validation provider

**Status:** Designed

**Acceptance evidence / next action:** —

### Work graph / dynamic scheduler

**Status:** Graph Implemented; scheduler Designed

**Acceptance evidence / next action:** AT-2; the scheduler comes in M5

### Concurrent mutation isolation

**Status:** Built (M4-C); the queue is M4-D

**Acceptance evidence / next action:** Per-Ticket worktrees and a serialized, CAS-published integration. The cap is a dispatch guard that reads `gates.yaml` `mutating_concurrency` (default 1, opt-in per project) and counts live workspaces whatever their state (review M2). Several mutating Tickets work at once and integrate one after another; the integration queue and lease arrive in M4-D.

### Controlled integration

**Status:** Implemented

**Acceptance evidence / next action:** AT-2, AT-4a (publish crashes), ADR-0004 (+ 2026-09-26 amendment); review probes B1/B2/M1/M6; `tests/integration/test_worktree_sync.py`

### Verification-failure classification

**Status:** Implemented

**Acceptance evidence / next action:** AT-6

### Validation provenance

**Status:** Implemented

**Acceptance evidence / next action:** AT-1, AT-3; evidence records what/who/when/against/how/result/evidence plus role card

### Plan assurance binding and policy consistency

**Status:** Implemented (UAT 2026-09-30)

**Acceptance evidence / next action:** ADR-0006 amendment 2026-09-30; every plan declares its review and verification (or `none`), and acceptance makes them required gates; cross-file policy contradictions in `aew doctor`, next actions and gates (`aew.policy.consistency`); `tests/regression/test_uat_2026_09_30.py`, `tests/unit/test_policy_consistency.py`. The full plan-assurance design is Designed (`future-work.md` F14)

### Project guardrails

**Status:** Implemented (deterministic subset)

**Acceptance evidence / next action:** Protected/generated paths, Ticket scope, review triggers (optionally naming a card); dependency rules are representable but not enforced

### Build/test impact analysis

**Status:** Designed

**Acceptance evidence / next action:** —

### SCM/Jira enforcement

**Status:** Designed

**Acceptance evidence / next action:** —

### Model-diverse review

**Status:** Staged

**Acceptance evidence / next action:** Expressible as an execution-policy route (ADR-0010) and run in the dogfood's model comparison. Policy and evaluation are later work (`future-work.md` D5)

### Plan assurance before mutating dispatch

**Status:** Partly implemented (M4-A): the dispatch predicate, protected conditions, Class 0 eligibility, plan lint. `ASSURED` and the assurance roles: Designed

**Acceptance evidence / next action:** `docs/design/plan-assurance-and-premise-validation-design-v0.4.md` (adopted 2026-10-01; the Class 0 Workflow Contract amendment with it). M4-A: `engine/dispatch.py`, `engine/assurance.py`, `tests/integration/test_dispatch_conformance.py`, `tests/regression/test_m4_dispatch.py`, AT-9 (KC §26 as amended). Gating dispatch on `ASSURED` needs a Workflow Contract amendment (`future-work.md` F14)

### Lease-expiry automatic Lead takeover

**Status:** Designed

**Acceptance evidence / next action:** Future ADR (ambiguity report A2)
