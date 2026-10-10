# F4 plan v8: Ticket revisions (E19-B v0.4)

- **Status:** v8, 2026-10-10, lead developer's planning agent. It answers the review of v7
  (`AEW-reviews/plan-f4-v1/REVIEW-v7.md`: Z1), applying the review's fix as proposed.
  - §0.0 maps Z1 to its change.
  - §0.1 to §0.6 keep the earlier maps (Y1 and Y2; X1 to X3; V1 to V7; R1 to R8; N1 to N7 and D1 to D4; M1 to M13 and
    m1 to m10), each amended where a later version changes the answer.

  v1 to v7 are kept unchanged beside this file. Nothing is built before an independent CLEAR review of this plan.
- **In the repository:** committed as written with slice S1, after its independent CLEAR review (v8), as the record
  of the approved plan. Review files and earlier versions named here live outside the repository. A deviation
  found while building a slice is recorded in ADR-0016 or the register row it changes, never by editing this
  text.
- **Baseline:** written against `origin/main` at `0ff0435`; line numbers are at that commit. Checked again before
  finishing: main is at `df839fd`, whose one change (#147, a single-run `harness wait` fix in `harness_ops.py`) touches
  nothing this plan relies on beyond shifting a few `harness_ops.py` line numbers. Since v1's base, #144 changed only
  the invariant oracle's handling of the custodian's role. #145 is docs only: the knowledge system adopted, and the
  designer's 2026-10-09 rulings on tool delivery and reviewer independence (§9.2). Still open: #142 (M4-E E3b) and #143
  (F22.1 PR B). §9.2 names their couplings.
- **Register rows:** F4. Touches F5 (parent coverage, TRA-12), F15.2 (StageIntent binding, TRA-25), F20 (dashboard
  contract, TRA-32), F19 (friction metrics, TRA-31) and F14 (assurance binds revisions, PAD-05; not built here).
- **Governing texts, in order:**
  - the Ticket-revision contract amendment E19-B v0.4
    (`docs/design/workflow-contract-amendment-ticket-revisions-2026-10-06.md`, adopted 2026-10-06, frozen, §13
    implementation-ready). It extends WC v0.7 §7, §8 and invariant 7, and KC v0.4 §12 (overlay
    `ticket-revisions-2026-10-06`);
  - the designer's decisions D1 to D7 of 2026-09-30, where E19-B does not restate or narrow them;
  - the hierarchy design v0.1 §8 to §10 and §20 Scenarios A and E, as amended by both;
  - the register F4 row's build note on the title;
  - the designer's ruling on re-parenting of 2026-10-09 (§10), and the operator and designer handoff of 2026-10-09 §15
    on Ticket parent changes against promotion. The handoff is
    `docs/AEW_Agent_Effectiveness_Research_Adoption_and_Implementation_Handoff_v0.1.md` in the main checkout, being
    ingested as `docs/design/decisions-2026-10-09-agent-effectiveness-adoption.md`. KC v0.4 §9.4 (frozen) governs
    promotion;
  - for sequencing only: Q7 v0.3.1 (`docs/design/q7-m4h-value-gate-experiment-v0.3.1.md`) §2.2, §2.4.3, §6.4, §7, §14.1
    and §16, and the M4-E plan v3.
- **Ledger:** TRA-01 to TRA-33 (TRA-20 and TRA-33 are done), and the F4-tracked rows of other sources: HIR-04 to HIR-07,
  HIR-13 to HIR-21, HIR-24, PAD-05, PAV-43, INV-03, VGX-21, SAI-15 and SAI-17. §6 maps every one.
- **Size:** 16 pull requests (§5): v4's 15, with S2b split into S2b.1 (the inherited-obligations accessor) and S2b.2 (carrying) (V1).
- **Not to be confused with** Q7's task family "F4" (the premise-contrast cells). This plan is register row F4 only.

## 0. Review findings and where this plan answers them

### 0.0 The v7 review (Z1)

| Finding | What changed in v8 |
|---|---|
| **Z1** the matcher's work-unit rule misses aliases and copies of the work map, comprehension loops, and unit parameters with other names | §3.12a, decision 60. The matcher now has three rules, by key:<br>1. calls to `ancestors` and `effective_edges`;<br>2. `min_descendant_class`, `mandatory_gates`, `carried_obligations` and `policy` reads **on any receiver**, except one rooted at the project manifest;<br>3. `parent` and `depends_on` reads, and `parent` loops, **only on work-unit expressions**.<br><br>Work-unit sources now include aliases and copies or merges of the work map (`archive_ops.py:271`, `:765`), `for` statements **and comprehension generators** over it (`archive_ops.py:616`, `dashboard/projections.py:776`), the unit-returning accessors (`H.upstream` included), and parameters annotated `Unit` or `WorkMap` or named `unit`, `u`, `up`, `child`, `anc`, `ancestor`, `parent_unit`, `upstream`, `work` or `hot`. S2b.1 adds and applies the `Unit` and `WorkMap` annotations.<br><br>A fixture case covers each form (alias, merged copy, two comprehensions, a `u` parameter, a `Unit` annotation, a `policy` read on an arbitrary receiver), and each must match. I re-checked `df839fd` with an `ast` walk under the widened rules:<br>- every match is now on the allow-list or in the routed list;<br>- the allow-list is rewritten per function **and per admitted rule and key**, so an entry never admits a whole function;<br>- the new entries are `Archive._join`, `_leave` and `move_hot_subtree`, `Archive.finalize`'s alias, `Archive.rehydrate`'s merged copy, `Archive._edge_targets`'s comprehension and `Projector.overview`'s comprehension.<br><br>No pattern was weakened |

### 0.1 The v6 review (Y1 and Y2)

| Finding | What changed in v7 |
|---|---|
| **Y1** a cached "not capable" verdict can downgrade a confirmer on a capable host, by forgery or staleness | §3.11:<br>- the probe cache may only short-circuit a "capable" verdict, which fails closed at `containment.establish` if it is false or stale;<br>- a "not capable" verdict for a confirmer always comes from a probe the launching command runs itself, in its own process, outside the store lock. Its result and time pass into the transaction in memory, are re-validated there by cheap facts and a 60 s freshness bound, and are recorded on the label;<br>- a cached "not capable" is never used for a confirmer.<br><br>The "a forged cache cannot loosen anything" bullet is corrected: it now holds in both directions only because the cache never decides a downgrade. New tests: `test_a_forged_not_capable_cache_never_downgrades_a_confirmer`, `test_a_repaired_host_contains_the_next_confirmer_despite_a_stale_not_capable_cache`, `test_a_downgrade_label_records_the_in_memory_probe_and_its_time` |
| **Y2** the static test's matcher is unspecified | §3.12a specifies an `ast`-based matcher. It matches:<br>- `Call` nodes to `ancestors`, `H.ancestors`, `hierarchy.ancestors`, `effective_edges` or `H.effective_edges`;<br>- `Subscript` and `.get` reads of `policy`, `min_descendant_class`, `mandatory_gates`, `depends_on`, `carried_obligations` or `parent` on an expression rooted at `state["work"][...]`, or on a unit bound from one (or from the engine's unit accessors, or a `unit` parameter);<br>- loops whose step reads `parent` from such a unit.<br><br>The reviewer's sites are checked, not allow-listed, because none is a work unit: `maps/structural._ancestors`, the keywords and parameters in `cli/work_commands.py` and `engine/api.py`, `surface/contract.py`'s schema keys, and `knowledge/records.py`'s writer. The test's fixture asserts that none matches. The manifest's policy reads no longer match, so v6's allow-list row for them is removed v8: the matcher is widened for Z1 (aliases, copies, comprehensions, parameter names; obligation keys on any non-manifest receiver), and the allow-list admits only named rules and keys. |

### 0.2 The v5 review (X1 to X3)

| Finding | What changed in v6 |
|---|---|
| **X1** V7 runs confirmers uncontained even under the operator's `containment.mode: required` | §3.11, decision 55 (supersedes v5's V7 rule). The confirmer's containment is the stronger of the project's mode and the host's capability, never weaker than the operator adopted:<br>- a capable host forces `required`;<br>- an incapable host under `allow_weaker` runs it uncontained, with the truthful label (F23);<br>- an incapable host under `required` refuses it with `CONFIRMER_CONTAINMENT_UNAVAILABLE`, and `aew doctor` names `allow_weaker` as the operator's choice.<br><br>The host probe comes from the result `aew doctor` and the supervisor's launch already produce, cached under `.aew/local/host/` and keyed by host, bubblewrap, kernel and engine version. It is refreshed outside the transaction and re-validated inside it by cheap facts only; bubblewrap is never spawned inside a Lead transaction. The platform table in §3.11 and the risk table (§13) agree. Tests: `test_a_required_project_refuses_an_uncontained_confirmer`, `test_doctor_names_allow_weaker_as_the_operators_choice`, `test_the_probe_never_runs_inside_the_lead_transaction` v7: the cache may only short-circuit "capable"; a downgrade needs a fresh in-memory probe (Y1). |
| **X2** the static test's allow-list is incomplete | §3.12a writes the full allow-list, each entry with the pattern it matches and its reason. It covers `hierarchy.children`, `children_map`, `descendants`, `depth`, `recompute_parents` and `children_digest`; `work_ops.rollup`, `work_show`, `work_list` and `work_create`; `usage_ops.py:668`; `history_ops` and `history/index.py`; the `archive_ops` lines; the move and promotion code; `work_depend`; `work_tree`; `dependencies.py:87`; the dashboard and resume projections; the manifest's policy reads; and the accessor's own use of `hierarchy.ancestors`. The test keys entries by function name and fails on a stale entry; its patterns are never weakened v7: the matcher is specified as an `ast` matcher rooted at `state["work"]`; the manifest rows are no longer needed (Y2). |
| **X3** two defaults rely on timestamps and on the wrong reference point | §3.2a and §3.5:<br>- events are ordered by the control revision that committed them (from the transition log, or recorded on `revision_events`), never by wall clock;<br>- legacy evidence's lower bound is its producing invocation's dispatch revision;<br>- an equal or unknown order counts as "later";<br>- plan bindings (and waivers) are measured from the plan's own acceptance (or the waiver's) decision revision, not from enablement.<br><br>Tests: the legacy test's `same_second_event_counts_as_later` and `unknown_order_counts_as_later` cases, and `test_a_pre_s4a_plan_is_measured_from_its_own_acceptance` |

### 0.3 The v4 review (V1 to V7)

| Finding | What changed in v5 |
|---|---|
| **V1** `carried_obligations` is read by only part of the code that reads ancestors | §3.12a: one accessor, `hierarchy.inherited(state, wid)`, folds ancestors and every `carried_obligations` entry into each ancestor-derived value. Every existing reader is routed through it, enumerated from the code at `0ff0435`: `gates.effective_class` (execution routing, F4's thresholds, the confirmer card), `gates.effective_obligations` (and its callers, Class 0 eligibility and assurance triggers included), `policy/validation.obligation` (the post-integration mode), `hierarchy.effective_edges` (readiness, `effective_edge_set`, cycle refusal through `waits_for`, non-mutating dispatch inputs), `work_reclassify`'s floor, the pack's inherited context, and the scope and hold checks F4 adds. A static test refuses any other parent-chain walk outside an explicit structural allow-list. Before-and-after tests for a promotion and a Story move compare every one of those values, and the oracle recomputes them independently. The accessor lands in **S2b.1** (a refactor with no behaviour change). Carrying starts in **S2b.2**. S2a's interim refusals stand until S2b.2 |
| **V2** S4a's revisions get no impact hold and no coverage obligation until S8 | §3.8, S4a (decided: refuse rather than move creation forward). Until S8 merges, a revision is refused when it would need either: `REVISION_NEEDS_IMPACT_HOLD` when its changed groups meet acceptance, check_definition or scope and a direct explicit dependent (own edge, or through a parent dependent) has an accepted plan; `REVISION_NEEDS_COVERAGE` when acceptance or check_definition changes on a Ticket that has a parent. Why refuse: creating holds needs S8's upstream bindings, guard and clearing path, and coverage needs S8's gate and closeout rule. Moving them into S4a would double the largest slice, while the refusal is small, fails closed, and touches only operator-enabled projects. S4a's attempt and decision records are already the durable impact record E19-B §7.5 requires |
| **V3** item 49's defaults make bindings depend on when a project was enabled | §3.2a replaces item 49 with an explicit table of every implicit default, each shown to be the conservative value. S2a records every hot Ticket's live digests at enablement (`recorded_digests`) and starts `revision_events`. Legacy evidence compares record-derived groups exactly, and counts a control-derived group as changed when any event touching it (a decision record, or a `revision_events` entry) is later than the evidence. S8 treats a plan with no `upstream_bindings` as bound to every hold-relevant group of each upstream. Each default is tested on a project enabled at S2a and run through the later engines |
| **V4** the coverage-obligation rule for promotion contradicts itself | Stated once, in §3.12: a coverage obligation is the parent's own and is outside the monotonic set. If it names a Ticket that is promoted out, it stays on that parent, re-pointed to record where the Ticket went (the promotion decision and the new unit). It is discharged only by that parent's next independent review bound to its current children digest, and is never dropped. S8 refers to that rule, and its test is `test_a_coverage_obligation_naming_a_promoted_child_is_re_pointed_and_discharged_by_review` |
| **V5** `carried_obligations` and the other new unit keys need registry classification | §3.3. `carried_obligations` is a revision-governed input to the derived `gate_set` and `dependencies` groups. It is read through the accessor and changed only by a promotion or a Story or Epic move. `hierarchy_baseline`, `revision_events`, `revision_refusals`, the `child_promoted_out` history event and `recorded_digests` are bookkeeping |
| **V6** an unsalted content address lets readers test guesses | §3.6 (decided: a per-proposal salt, not a project HMAC key). The withheld file holds a fresh 32-byte random salt and the rationale. Its name, and the attempt record's `rationale_digest`, are SHA-256 over the salt followed by the rationale. Nothing outside the masked directory holds the salt, so the digest cannot test guesses. Why a salt: there is no long-lived key to create, protect, rotate or back up; a project key exposed once (any uncontained host can read it) would open every past digest, while a salt exposes only its own file. The prewritten contract holds: a name is the hash of exactly that file's bytes, and a retry draws a new salt and so a new name |
| **V7** where containment is present but its self-test fails, confirmations are impossible | §3.11 (the lead developer's decision, governed by A22, the operator's F23 decision). The engine's capability check is `containment.supported()` **and** a host self-test (the probe `aew doctor` already runs), evaluated in the launching transaction. If the probe fails (RL8's slirp4netns case, missing bubblewrap, user namespaces off), the host is treated as not supporting containment for confirmers: the confirmer runs uncontained with the truthful weaker label, exactly as on Windows, with the failed probe's reason in the label. Never silently: `aew doctor` reports "confirmers run uncontained on this host: containment self-test failed (<reason>)", and the confirmation's label, `status` and `explain` show it. §13 discloses it. Other runs keep the project's `containment.mode`, unchanged **Superseded by X1 in v6:** the confirmer never runs weaker than the operator's mode (§0.0). |

### 0.4 The v3 review (R1 to R8)

| Finding | What changed in v4 |
|---|---|
| **R1** a prewritten withheld file at a reused attempt path blocks later proposals | §3.6: the withheld file is content-addressed, `.aew/withheld/<T>/<sha256>.yaml`, and the attempt record's `rationale_digest` names it. A failed proposal leaves a file no later proposal collides with: a different rationale has a different name, and the same rationale has the same bytes, which is exactly the prewritten contract. Test: `test_a_proposal_that_fails_after_the_prewrite_never_blocks_the_next` v5: the file also holds a per-proposal salt, so its name is `<digest>.yaml` and the attempt record's field is `rationale_digest` (V6). |
| **R2** the label and the host's capability are read from a run-writable record | §3.11: the engine derives both itself and commits them in the launching transaction, on the invocation's `runs[]` entry, before any agent process exists. It never reads the run directory for them. Where the host supports containment, the launch forces `required`, and a `required` launch either establishes containment or fails, so "contained" is true by construction. Where `containment.supported()` is false, the engine records the platform's weaker label. Test: `test_a_confirmer_that_rewrites_its_run_record_is_still_labelled_by_the_engine` v5: the capability is `supported()` **and** a host self-test; a failed probe makes the confirmer run uncontained with a truthful label (V7). |
| **R3** the pending guard refuses the confirmer's relaunch; the same-change refusal may cover abandoned attempts | §3.7: the pending guard exempts the attempt's own confirmer from the `harness launch` refusal (forced containment still applies). §3.11: `CONFIRMATION_REFUSED_SAME_CHANGE` applies only after `refused_by_confirmation` (a sealed negative record). `confirmation_lost`, `confirmation_abandoned` and generation-aborted attempts bind forward as adverse context (trigger 7 and the confirmer's material), but the same change may be proposed again. Tests: `test_a_crashed_confirmer_is_relaunched_during_pending`, `test_the_same_change_is_proposable_after_an_abandoned_confirmation[lost,generation_change]` |
| **R4** D3's refusal of non-enclosing promotion has no governing basis, and is inconsistent with Story moves | §3.12, governed (lead developer's decision; not a designer question). KC §9.4 promotion is allowed, out of a Story included, as the frozen text (KC v0.4 §9.4) and the operator and designer handoff of 2026-10-09 §15 say: promotion "remains allowed after work starts and preserves original Ticket identity, evidence/history, effective risk/class floor, and inherited non-waivable gates/guardrails". The ancestors it leaves hand their inherited obligations to the new unit as **carried obligations** (class floor, mandatory gates, any ancestor guardrails, inherited dependency edges, declared-scope envelopes, impact holds). The old parent's own closeout and coverage stay that parent's, re-evaluated by the existing rules, and the promotion is recorded in both units' history. Story moves get the same carried treatment. `PROMOTION_NOT_ENCLOSING` is gone; `HIERARCHY_NOT_MONOTONIC` remains for a change that would drop an inherited obligation it cannot carry. S12 does not narrow the frozen operation: `tests/integration/test_hierarchy.py:144` passes unchanged v5: one accessor carries every ancestor-derived value (V1); coverage handling stated once (V4). |
| **R5** TR-14's r1-record baseline fails on projects enabled after earlier moves | TR-14 (S2b) compares against `hierarchy_baseline.parent`, recorded at enablement for every hot Ticket and at creation afterwards. Changes after it are allowed only through a recorded promotion |
| **R6** the format raise and E3/E7 diff checks; the mask's directory must exist | §3.2 and §9.2: the format raise is excluded from E7's runtime declaration check (SAE-07), from E3's stage/primitive equivalence comparisons, and from the store model's event-fidelity rule, and it derives no event. §3.6: `.aew/withheld/` is created at enablement (S2a), and confirmer layouts mask it unconditionally, creating it if absent at layout time |
| **R7** the Lead's harness transcript also holds the rationale | §3.11 and §13. Contained confirmer layouts also mask the Lead harness's session-store paths, taken from the Lead's execution profile through the harness adapter's declared session-store locations; OpenCode's are already in `SECRET_DIRS`. `aew doctor` warns when the Lead harness's store is not covered by a mask and points to `containment.hide`. §13 states the rest plainly: a store the adapter does not declare, and every uncontained host |
| **R8** S2 is too large, and has no Rocky run | S2 is split into three slices (§5): **S2a** enablement, the format raise in the store's commit path, `.aew/withheld/`, downgrade tests and interim hierarchy refusals (a full Rocky 8 run before merge, because it changes `Session.commit`); **S2b** the hierarchy rules and TR-14; **S2c** revision records, the r1 step, invocation and completion binding, TR-1 and TR-2. 15 pull requests v5: S2b is further split into S2b.1 (the accessor) and S2b.2 (carrying), 16 pull requests (V1). |

### 0.5 The v2 re-review (N1 to N7, D1 to D4) and the designer's ruling

| Finding | What changed in v3 |
|---|---|
| **N1** the redo record stores the withheld rationale's bytes | §3.6: the proposing transaction writes the withheld file as a `Session.prewritten` object, which the redo record holds by path and hash only, never by content (`store.py:17-23`). Tests: `test_no_state_file_holds_the_rationale_before_the_seal` (every file under `.aew/state/`, the redo records, `state/log/`, `last_transition` and control state), and the redo path added to the contained-confirmer test v4: the file is content-addressed (R1). |
| **N2** containment is decided per run, not per profile | §3.11 (lead developer's decision): on a host whose containment self-test passes, the confirmer's launch forces `containment.mode: required`, whatever the project's mode. A confirmation is accepted only from a run whose recorded label matches what the host reported it supports at that launch. Recorded in TR-9. Test: `test_a_confirmers_label_must_match_the_hosts_capability` v4: the engine derives and commits the label at launch, never reading the run record (R2). |
| **N3** refusing confirmation without containment breaks E19-B §1 on Windows | §3.11 (lead developer's decision, governed by the operator's F23 internal-alpha decision, ledger IAT: "Windows/WSL dev/test use with weaker truthful guarantees: ALLOWED"). Option (a): on a host without OS containment, the confirmer runs uncontained with a truthful weaker label, recorded on the confirmation and shown in `status`, `explain`, closeout and TR-9. Rationale withholding is still enforced on every engine read path and on the bridge. The residual (an uncontained confirmer's shell can read files) is stated in §13. Nothing forces replacement; `CONFIRMER_NEEDS_CONTAINMENT` is gone |
| **N4** `plan reconfirm` refuses with the binding intact, so a title-only revision cannot use the edge | §3.10: plan binding problems are computed on digests only, never on the revision number. `plan reconfirm` closes a REPLAN_REQUIRED whose latest entry is `via: revision.commit` even when no plan-bound digest changed, and its decision records the rebinding to the new revision. S6's oracle 3 test runs both legs through `work assign` |
| **N5** the format raise rides only on Lead and custody transactions | §3.2: the raise is in the store's commit path (`Session.commit`), for every transaction on an enabled project. Test: `test_an_invocation_submitted_record_raises_the_format` |
| **N6** inherited edges in `dependencies` stale descendants' plans | §3.2's table (S4a row) and ADR-0016 disclose it: on an enabled project, an ancestor's `work depend` marks every descendant's accepted plan `plan_stale` until each is reconfirmed |
| **N7** a pending revision across a Lead generation change | §3.7: fail closed. The transaction that changes the Lead generation (takeover, accepted handoff, release) aborts every pending attempt and ends its confirmer, under §3.11's binding rules. Test: `test_a_generation_change_aborts_pending_revisions` |
| **D1** the unstarted carve-out lets a governing Ticket move | §3.12 and §10 (the ruling, applied strictly, lead developer's decision): AEW has no draft Ticket, so identity governs from `work create`. On an enabled project, `work move` of a Ticket is refused after creation, whatever its state. `_move_archived` is refused for every unit. A Ticket's parent is chosen at creation, and in `ticket_draft`'s own construction step if E5a introduces a pre-identity phase. The "BLOCKED with nothing bound" construction reading is in §11 as a possible future relaxation, not a question |
| **D2** the move refusal lands only in S9 | §3.12: every re-parenting rule lands in S2. Ticket moves are refused there with `REPLACEMENT_PATH_UNAVAILABLE`, which S9 turns into `REPLACEMENT_REQUIRED` naming `aew work replace`. In the §3.2 table v4: the refusals land in S2a and the carry rules in S2b (R8). |
| **D3** promotion re-parents a Ticket out of its Story | Superseded in v4 by R4: promotion is allowed, out of a Story included, and carries the inherited obligations into the new unit (§3.12; handoff §15; KC §9.4). |
| **D4** the monotonic set | §3.12 defines it exactly: effective class; inherited mandatory gates (the non-waivable gates today); ancestor guardrails (none today; joins the set if F5 adds them); inherited dependency edges; ancestor declared-scope envelopes; open coverage obligations; impact holds reaching through an ancestor. Dormant projects keep ADR-0007's rules until enabled, which follows from §3.0 rule 2 and is recorded in ADR-0016 v4: open coverage obligations are the old parent's own and leave the set; impact holds are carried (R4). |
| **Designer ruling on §10** | §10 is now the decided record, with the ruling and its reasoning verbatim. S2a's PR adds it to the repository as `docs/design/decisions-2026-10-09-f4-ticket-reparenting.md`, ingested in the ledger |

### 0.6 The v1 review (M1 to M13, m1 to m10), v2's answers, amended by v3

| Finding | What changed |
|---|---|
| **M1** S4a's interim anti-laundering predicate is not a superset of S5's | §3.9: S4a's interim predicate counts anything that may be adverse (every failing, inconclusive or blocked record of the Ticket, received or ingested; every open finding; every adverse or exceptional state in its history; any queue entry awaiting disposition; any open item E5b adds), and treats lineage as always present. S5 keeps it as a test oracle: `test_the_interim_predicate_is_a_superset_of_open_adverse` |
| **M2** the overlay blocks too little; requirements frozen at proposal | §3.7: the `REVISION_PENDING` guard is on every action that progresses or changes the Ticket, and inside the one lease-granting function, `queue_ops.grant`, so E6a's and E6b's paths inherit it. The commit recomputes everything from live state; requirements never shrink, and growth refuses the commit (`REVISION_REQUIREMENTS_CHANGED`). Test: `test_mutations_during_pending_are_refused_or_refuse_the_commit[...]` |
| **M3** downgrade safety covers pre-F4 engines only | §3.2: the marker carries a format number. Every slice that adds a rule an older engine would ignore raises it, and the engine raises a project's format on its first commit. The control schema allows only formats up to its own, so an older F4 engine refuses the file. Each slice's downgrade test vendors the previous slice's schema |
| **M4** the rationale is readable before the initial determination | §3.6 and §3.11: the Lead's reason and alignment are held in `.aew/withheld/`, outside the attempt record and the transition log. Every read projection redacts them until the initial determination is sealed. Containment masks that directory for every contained run. v3 changes the rest (N1 to N3): the file is a prewritten object, never in the redo record; contained hosts force containment; uncontained hosts run a truthfully labelled confirmer |
| **M5** confirmer shopping through abort, cancel and re-propose | §3.11: one confirmer per attempt. Any outcome other than a positive final record binds forward: aborting after a sealed negative is `refused_by_confirmation`; re-proposing the identical change set is refused; any other change from the same predecessor needs confirmation, and the earlier records are in its confirmer's material and in `open_adverse` until a positive confirmation disposes each one |
| **M6** the checkpoint's own requirements are unmapped | §3.11, S7: `aew revision checkpoint` shows the cumulative diff, the predecessor diff and the parent envelope before the challenge, and records the digest of what it showed. Tests: `test_the_checkpoint_shows_the_cumulative_diff_and_binds_it`, `test_a_checkpoint_waives_no_evidence_finding_or_gate` (§6 TRA-11, §7 row 15) |
| **M7** the reconfirm edge is keyed on an undefined "cause" | §3.10: the edge applies only when the Ticket's latest entry into REPLAN_REQUIRED was `via: revision.commit`. It lands in S4b. Negative test: `test_reconfirm_never_closes_a_classification_replan` |
| **M8** S4b leaves the workspace unspecified, so reassignment is impossible | §3.10, S4b: committing a revision of started work releases the workspace (`released (revised)`), as `--workspace fresh` will. S6 adds `carried` as the alternative. The S4b test continues through the next `work assign` |
| **M9** reactivating a carried worktree skips dependency and input checks | S6: reactivation rechecks readiness and `inputs.current` against the carried worktree's own base and records the new dispatch edges. It refuses `CARRIED_BASE_STALE` when a dependency's integrated commit is not in that base. Test: `test_carry_is_refused_when_its_base_lacks_a_new_dependency` |
| **M10** "current digests" are undefined when inputs change outside a revision | §3.3: current digests are computed live (the current revision record plus control state plus derived obligations). A revision's changed groups are the live digests before the proposal against the proposed ones. Changes made outside a revision are events in the Ticket's revision history. TR-1 compares only the record's own groups |
| **M11** migration does change behaviour, and `aew init` opts every project in | §3.2, §9.3: F4 is dormant on any project that has not been explicitly enabled, and a dormant project behaves byte for byte as today (the existing suite is the proof). Until S12, only `aew migrate --ticket-revisions` or `aew init --ticket-revisions` (both the operator's) enable it. §3.2 lists exactly what changes when a project is enabled, by slice. §9.3: the M4-H configuration is unaffected unless the freeze commit includes S12, and no F4 merge lands between the pre-calibration freeze and the end of counted runs |
| **M12** decision 35 is a design decision, applied inconsistently | Decided by the designer (§10). v4's §3.12 applies the ruling, handoff §15 and KC §9.4: no Ticket moves after creation; promotion allowed wherever the unit sits, carrying inherited obligations; Story and Epic moves carry the same way; every change monotonic over the inherited set; every re-parenting recorded in the revision history. Interim refusals in S2a, the rules in S2b |
| **M13** oracle cases 2 and 3 are proven only on synthetic revisions | §3.5: HISTORICAL's "attempt ended" clause applies only to the attempt-scoped class (`implementation_report`). S6 adds end-to-end tests on the real path (propose, quiesce, commit, REPLAN_REQUIRED, reconfirm, carry, reactivate); §7 rows 2 and 3 now name those tests |
| **m1** decision 18 is a reading | §4.2 (RD1): disclosed as a reading, recorded in ADR-0016. S4b tests the post-integration route (`COMMIT_READY` to `VERIFICATION_FAILED` through `integrate.validate`) |
| **m2** decision 16 departs from D1's table | §4.2 (RD2): disclosed as a departure from the table's text, kept, recorded in ADR-0016, and listed for the designer's information (§11) |
| **m3** "no silent pass" does not hold without a trigger | §3.9: containment that cannot be proven against a parent's declared scope is a confirmation trigger |
| **m4** inherited edges are outside the `dependencies` group | §3.3: the `dependencies` digest is computed over the effective edge set; only the Ticket's own edges are revisable |
| **m5** the confirmer's card and lifecycle are under-specified | §3.11: `card.confirmer` admits only the policy-resolved card. Abort, expiry and cancellation end an active confirmer in the same transaction. With no Lead session, the operator's abort at their terminal is the path |
| **m6** `work depend`'s reason is not an alignment assertion | S4a: `work depend` on a Ticket of an enabled project requires `--alignment` |
| **m7** gaps in the §6 test mapping | Oracle 10 is parametrized over HISTORICAL, INVALIDATED and SUPERSEDED. Oracle 32's third leg names S7's `test_a_non_overlapping_objective_is_refused_by_confirmation`. S1 tests the two set rules for collisions |
| **m8** the coupling with M4-E is incomplete | §9.2 names each coupling: the S1 meta-test and every unit key E5b and E6b add; E6b's `authorization_envelope` stamp, classified in `gate_set`; `work replace` going through `work.create`'s path, so the stamp applies; and the PIC request, which needs no wait because `record_sha256` follows the current revision. Also #143 for packs |
| **m9** replacement is the remaining laundering route | §11 (designer information). S9: `work replace` warns when T has open adverse items, and the parent closeout record lists every replacement made while its subject had open adverse items |
| **m10** §2.9's state rules overlap | §3.10: one ordered rule with explicit precedence; both cases tested |

## 1. What is out of F4, and why

| Item | Why it is out | What stands in |
|---|---|---|
| Story and Epic revision, approved-baseline drift, EDITORIAL/CLARIFICATION/MATERIAL as classes of parent change | F5 (hierarchy design §4 to §7, §12 to §18) | F4 classifies *Ticket* change mechanically through digests (§3.3). HIR-05 and HIR-06 keep their F5 part open |
| Structured requirement-to-child mappings on parents | F5; none exist | A visible parent-coverage review obligation (E19-B §4.4; S8) |
| `ASSURED` and plan assurance binding revision digests (PAD-05, PAV-43) | F14 is not built | The accepted plan binds the revision digests (S4a): the hook F14 binds to |
| Live delivery of a revision to a running invocation | E19-B §11 non-goal | Quiesce and redispatch (S4b) |
| A normal typed-surface tool for revisions | M4-E §2.6 leaves about 250 bytes and one tool of headroom, already planned for | CLI commands relayed by the broker (`LEAD_REACHABLE`); a typed tool after a budget decision once M4-E's surface is measured |
| Story/Epic and integration-scope evidence under revision | Already bound exactly: the parent snapshot (children digest) and the candidate | Children digests include final revisions (S2c); a revision retires the candidate (S4b) |
| Production-grade confirmation on hosts without OS containment | Containment is Linux (M4-B). The F23 internal-alpha decision allows Windows/WSL development with truthful weaker labels | A confirmer runs there with a truthful weaker label and engine-enforced withholding (§3.11); the residual is stated in §13 |
| Designing Story and Epic restructure as such | F5 (parent restructure) | Promotion and Story or Epic moves carry the inherited obligations they leave (§3.12) |
| Notifier events for an expired pending revision | E7's notifier is not built | Attention in `status`, `resume` and the dashboard; S11 adds the event if E7 has merged |

## 2. What exists (against `0ff0435`)

- **A Ticket cannot change after creation.** `work create` writes `work/<T>/ticket.md` (`aew/work-unit/v1`, an open
  schema) and pins it as `unit.record` and `record_sha256` (`engine/work_ops.py:339-372`). The Ticket's inputs live in
  two stores:
  - the record holds the title, body, scope, acceptance (`goal_backwards`, `contract`, `checks`, `inputs`),
    `class0_assertions`, `external_refs`, `parent`, `kind` and `mutating`;
  - control state holds `depends_on`, the current `risk_class`, `role_plan` and the plan pointer.
- **Existing mutators of Ticket inputs** (all recorded Lead decisions):
  - `work depend` changes own edges, only in BLOCKED, READY or REPLAN_REQUIRED (`hierarchy_ops.py:556-601`); on a
    Story, it changes its descendants' inherited edges;
  - `work reclassify` raises the class only (WC §7.4; `work_ops.py:396-437`);
  - `work staff` changes the role plan (ADR-0006);
  - `work move` re-parents (ADR-0007; `hierarchy_ops.py:427-497`);
  - `work promote` follows KC §9.4. A Ticket is moved under a new Story created under the nearest valid ancestor, which
    can skip the Ticket's old Story (`hierarchy_ops.py:499-555`). `PARENT_KINDS` lets a Story sit only under an Epic
    and an Epic under nothing (`hierarchy.py:21`). AT-10, the frozen KC scenario "Ticket promotion"
    (`tests/acceptance/test_at8_at13_hierarchy.py:153`), promotes a Ticket under an Epic to a Story.
  - `_move_archived` moves a finished unit too (`hierarchy_ops.py:449-463`).
- **The redo record** stages every file a transaction writes, with its content (`store.py:350-372`), except
  `Session.prewritten` objects, which it holds by path and hash only (`store.py:17-23`, `:181-186`).
- **Lead generation changes** (takeover, accepted handoff, release) already end generation-bound state in the changing
  transaction: Lead credentials, and the lease's custodian (marked `reconcile`).
- **Evidence binds the snapshot and the plan revision only** (`gates._matches`, `:121-124`; a check also proves its
  definition). The snapshot excludes `.aew/` (`snapshot/fingerprint.py:14`, `:44`), so no evidence binds Ticket inputs.
  Binding fields are engine-owned (`knowledge/evidence.py:37-40`); the evidence schema is open.
- **Ingest refuses a report from another plan, attempt or candidate** (`evidence_ops.require_bound_report`,
  `:369-400`). **Findings** live on the unit and outlive evidence freshness.
- **Dispatch** is one predicate (`DispatchDecision`), decided inside the dispatching Lead transaction, which is a CAS on
  the control revision (`engine/dispatch.py`; `base.lead_txn`, `:345-370`).
- **`work.assign`'s `workspace.free` guard** refuses a Ticket that still holds a live workspace
  (`workspace_ops.py:278-284`). `release_workspace` is called only by `plan accept` from REPLAN_REQUIRED and by cancel.
- **A non-mutating Ticket completes through `work accept`** (RUNNING, REVIEW_PASSED or VERIFIED to DONE, `via:
  accept`), not through `work transition`.
- **Integration (M4-D):** every lease is granted by `queue_ops.grant` (`:216`). Leaving COMMIT_READY retires the queue
  entry (`queue_ops.sync`, `:99-124`). A lease ends only through its own path (`integrate defer`, `integrate reconcile`),
  never on a timeout.
- **Containment (M4-B):** a contained run sees the host read-only, and every run's directory is hidden. Secret masks
  replace chosen paths with an empty tmpfs or an empty file. The stated claim is integrity, not confidentiality
  (`containment/layout.py:1-21`). An uncontained reviewer session has a shell (`opencode/projection.py:97`).
- **StageIntents (E3a):** a Ticket subject is bound as `{state, record_sha256}` (`stage_intents.unit_state`,
  `:105-108`). E3b (#142) runs steps; E3c will add `continue` and `abandon`.
- **Packs** pin `unit.record` and its hash, and a regenerated pack is compared with the recorded hash
  (`context_ops.py:207`, `:245`, `:276-290`). #143 adds the structural map to packs.
- **Completion and closeout records** name the plan, the evidence and the children, never a Ticket revision. Archival
  pins the record, the plans and the stage intents (`archive_ops.pinned_records`, `:67-100`).
- **`aew migrate` is the operator's** (`OPERATOR_DECIDED`, `lead_broker.py:79`). Top-level control keys are closed.
  `V2_ONLY_KEYS` (`base.py:37-38`) is the one list of v2-only keys, and `test_m4_schema_downgrade.py` proves that a
  baseline engine refuses a file carrying one. The unit definition is open.
- **Supersession lineage for Tickets is not built** (no `supersedes` or `superseded_by`; AEW-INV-HIER-005 is
  unchecked).
- **The invariant oracle** has rules 1 to 49 (`tests/helpers/invariants.py`).

## 3. Cross-cutting designs the slices share

### 3.0 Two rules every slice follows

1. **An interim is never weaker than the final rule.** When a slice cannot yet apply a later slice's full rule, it
   refuses, with a reason code naming the slice that lifts the refusal. It never applies a weaker rule. The register's
   F4 notes list every interim refusal while it stands.
2. **Nothing changes on a project that has not been enabled** (§3.2). Every F4 rule, record, field and refusal applies
   only to an enabled project. A dormant project writes no F4 key, no F4 field and no F4 record, and refuses nothing
   new. Until S12, the whole existing test suite runs dormant, so it is the regression proof of this rule. A test
   asserts that no F4 key appears in a dormant project's control state, evidence or records after the walks.
   - In particular, a dormant project keeps ADR-0007's present move and promotion rules until it is enabled, though the
     designer's ruling says "in all cases" (§10). This follows from the rule and is recorded in ADR-0016 (D4).

### 3.1 Applied from adopted designs (cited, not decided)

| # | What | Source |
|---|---|---|
| A1 | Evidence binds field-group digests, not revision numbers | D1; E19-B §5.1 |
| A2 | A revision is allowed in any non-terminal state except while a publishing lease is held. The "publishing lease" is the Ticket's entry's integration lease, which is what publication needs | D2; E19-B §4.1, §8; v0.3 review §2.1, adopted in v0.4's wording |
| A3 | The workspace may carry forward as input only | D3; E19-B §5.4 |
| A4 | REVALIDATE resolves only mechanically or by independent confirmation. A Lead's note is advisory and never satisfies a gate | E19-B §5.3, which narrows D4 |
| A5 | Adverse findings carry forward until resolved, waived through an existing path, or shown inapplicable by attributable evidence | D5; E19-B §6.1 |
| A6 | Mechanical refusals, as against recorded Lead assertions | D6; E19-B §4.1, §4.2 |
| A7 | Replacement for a change of kind, a different parent, a non-overlapping goal, or a DONE/CANCELLED predecessor | D7; E19-B §3 |
| A8 | The anti-laundering trigger: `REVIEW_FAILED`, `VERIFICATION_FAILED`, `VERIFICATION_INCONCLUSIVE` or unresolved adverse evidence; not `BLOCKED` | E19-B §6.2 |
| A9 | The amendment's own impact hold: no F9 dependency, no recursive fan-out | E19-B §7.5 |
| A10 | The title is presentation-only by declaration and never read for acceptance. Misuse makes it acceptance-bearing while the content remains, and is `UNBOUND_FIELD_ESCAPE` | E19-B §2.3; register F4 build note |
| A11 | Dependencies stored in control state are a field group | E19-B §2.3 |
| A12 | Confirmation thresholds use the effective class | E19-B §4.2 |
| A13 | The checkpoint is the operator's; the threshold is in policy only the operator adopts | E19-B §4.3; #103; #118 |
| A14 | Migration is `aew migrate`, the operator's | E19-B §12.1 |
| A15 | Overlays exposed by a typed projection version its contract | E19-B §12.1 |
| A16 | Confirmation is a governed stage that costs a model invocation | E19-B §12.1 |
| A17 | The spec amendment is implemented with an ADR | Review 2026-09-30 §10 |
| A18 | Revision text is untrusted authored input | E19-B §2.4; HIR-19 |
| A19 | StageIntent binding waits for F15.2's journal and its explicit continue | Register F4; M4-E §0 |
| A20 | Promotion preserves the original Ticket's identity and evidence, including for a started Ticket | KC v0.4 §9.4 and its acceptance scenario "Ticket promotion" (frozen) |
| A21 | No change of a committed Ticket's parent: replacement with lineage, whether or not execution began. Promotion is the distinct hierarchy-expansion operation, allowed after work starts and preserving the inherited obligations. Every hierarchy change is monotonic over inherited obligations | The designer's ruling of 2026-10-09 on §10 (verbatim there) |
| A23 | Promotion "remains allowed after work starts and preserves original Ticket identity, evidence/history, effective risk/class floor, and inherited non-waivable gates/guardrails"; fail closed on ambiguous re-parenting | Handoff of 2026-10-09 §15; KC v0.4 §9.4 |
| A22 | On hosts without OS containment, development runs are allowed with truthful weaker labels, never presented as the Linux production guarantee | The operator's F23 internal-alpha decision (`docs/design/decisions-2026-10-07-f23-internal-alpha-threat-model.md`; ledger IAT) |

### 3.2 Enablement and format versions (M3, M11)

- **The marker:** a top-level control key, `ticket_revisions: {schema: "aew/ticket-revisions/v1", format: <int>,
  registry, enabled_rev}`, listed in `V2_ONLY_KEYS`. A project is **enabled** exactly when the key is present.
  - Its presence makes every pre-F4 engine refuse the file (closed top level).
  - Its `format` makes every older F4 engine refuse it: each engine's control schema declares `format: {type:
    integer, minimum: 1, maximum: <its own format>}`.
- **Format numbers.** Each slice that adds a rule an older engine would ignore takes the next number when it merges, so
  parallel slices are numbered in merge order:

  | Slice | What an older engine would ignore |
  |---|---|
  | S2a | enablement and the interim hierarchy refusals (format 1) |
  | S2b.1 | nothing (a refactor: the accessor; no behaviour change, no new state) |
  | S2b.2 | the hierarchy rules: carried obligations, TR-14's promotion exception |
  | S2c | r1 records, invocation binding |
  | S3 | admissibility |
  | S4a | revisions after r1; `work depend` as a revision |
  | S4b | the pending overlay and its guard |
  | S5 | adverse recording and the disposition restriction |
  | S6 | carried workspaces |
  | S7 | confirmation, the checkpoint, the withheld mask, the confirmer's label rule |
  | S8 | impact holds (and their place in the monotonic set) and coverage obligations |
  | S9 | supersession and the closeout rule |
  | S10 | StageIntent revision binding |

  S1, S11 and S12 add no rule an older engine could ignore, so they take no number.
- **Raising a project's format (N5).** The raise is in the store's commit path itself (`Session.commit`). Every
  transaction an engine commits on an enabled project raises `format` to the engine's own when lower: Lead, custody,
  invocation (bridge submissions, check runs), operator (`migrate`, `manifest adopt`, `revision checkpoint`) and endpoint
  transactions alike. The raise is append-only and touches no other data. From then on an older engine refuses the
  project. Test: `test_an_invocation_submitted_record_raises_the_format` (the first commit by a newer engine is a
  bridge submission).
- **The raise is bookkeeping, excluded from every diff-based check (R6):**
  - it derives no transition event;
  - it is excluded from E7's runtime declaration check (SAE-07: a step's committed control-state diff against its
    declared effects);
  - it is excluded from E3's stage/primitive equivalence comparisons, beside the journal's own records;
  - it is excluded from the store model's event-fidelity rule.

  The exclusion is one named path (`ticket_revisions.format`) in the shared diff helper those checks use. Test:
  `test_a_format_raise_on_an_auto_run_step_opens_no_anomaly`.
- **Downgrade tests.** Each format-raising slice vendors the previous slice's `control.schema.json` (S2a vendors the
  pre-F4 one) and asserts it refuses a file at the new format, beside `test_m4_schema_downgrade.py`.
- **Enabling.**
  - Until S12: only the operator enables a project, with `aew migrate --ticket-revisions` (an existing v2 project: one
    transaction, §5 S2a and S2c) or `aew init --ticket-revisions` (a new project). Plain `aew init` and `aew migrate` leave a
    project dormant.
  - S12 makes enabled the default for `aew init` and `aew migrate`.
  - `aew migrate --ticket-revisions` is `OPERATOR_DECIDED`, as `migrate` is.
  - `aew init` runs before any Lead exists, so it is the operator's by construction.
- **What changes when a project is enabled**, by the slice that adds it. Nothing changes on a dormant project.

  | From | Changes on an enabled project |
  |---|---|
  | S2a | `.aew/withheld/` is created. Every hot Ticket's live digests are recorded (`recorded_digests`), and `revision_events` starts. `work depend` on a Ticket is refused (`REVISION_PATH_UNAVAILABLE`, lifted by S4a): dependencies are revision-governed, and the revision path does not exist yet. `work move` of a Ticket is refused (`REPLACEMENT_PATH_UNAVAILABLE`; S9 turns it into `REPLACEMENT_REQUIRED`). Moving a finished unit is refused (`FINISHED_HIERARCHY_FINAL`). **Interim:** every promotion and every Story or Epic move is refused (`HIERARCHY_RULES_PENDING`, lifted by S2b.2), because the carry rules do not exist yet (§3.0 rule 1). This narrows KC §9.4 only on an operator-enabled project, between two adjacent slices |
  | S2b.1 | Nothing: every ancestor-derived value is read through one accessor, with identical results while no `carried_obligations` exist (on every project, enabled or not) |
  | S2b.2 | Promotion is allowed again, carrying the inherited obligations it leaves (§3.12). A Story or Epic move is allowed with the same carry. A change whose obligations cannot be carried is refused (`HIERARCHY_NOT_MONOTONIC`). The old parent's closeout and coverage are re-evaluated by the existing rules, and both units' histories record the change |
  | S2c | New Tickets get r1 records and pointers. Invocations record their revision. Completion and closeout records name the final revision |
  | S3 | Evidence carries `ticket_inputs`. Gates and ingest apply admissibility. Waivers bind digests |
  | S4a | `aew revision propose` works for unstarted Tickets. `work depend` on a Ticket is a revision and needs `--alignment`. Revisions of started work are refused (`REVISION_OF_STARTED_WORK`, lifted by S4b). Revisions that need confirmation are refused (`REVISION_NEEDS_CONFIRMATION`, lifted by S7), and so are those that need a checkpoint (`REVISION_NEEDS_CHECKPOINT`, S7). Revisions are refused while a stage is in flight on the Ticket (`STAGE_IN_FLIGHT`, S10). Until S8, a revision is refused when it would need an impact hold (`REVISION_NEEDS_IMPACT_HOLD`: its changed groups meet acceptance, check_definition or scope, and a direct explicit dependent has an accepted plan) or a parent-coverage obligation (`REVISION_NEEDS_COVERAGE`: acceptance or check_definition changes on a Ticket with a parent) (V2). Accepted plans bind the Ticket's digests (N6): **an ancestor's `work depend` changes every descendant Ticket's `dependencies` digest, so each descendant's accepted plan shows `plan_stale` until the Lead reconfirms it** (today such an edit needs no reconfirmation; it is conservative, and recorded in ADR-0016) |
  | S4b | Revisions of started work quiesce and pend. The pending guard applies |
  | S5 | Received failing reports' findings are recorded at commit. A Lead `not_applicable` disposition is restricted |
  | S6 | Workspaces carry by default |
  | S7 | Confirmation and the checkpoint apply. On a host whose containment works, the confirmer always runs contained; on a host without OS containment it runs with a truthful weaker label, shown wherever the confirmation is |
  | S8 | Impact holds and coverage obligations apply, lifting S4a's two refusals. Plans accepted before S8 count as bound to every hold-relevant group of each upstream (§3.2a) |
  | S9 | `work replace` exists, and the closeout supersession rule applies |
  | S10 | Open stages bind the revision |

### 3.2a Implicit defaults: every one conservative (V3; replaces v4's item 49)

A slice's state can be missing on a project enabled earlier. Each such default must be the conservative value, not
merely the absent one: a default may never make evidence more admissible, a hold or obligation less likely, or a
refusal less likely than the recorded value would. Every row is tested on a project enabled at S2a and then run
through each later engine (`test_implicit_defaults_on_a_project_enabled_at_s2a[<row>]`).

| State (slice that adds it) | When it can be missing | Default | Why it is the conservative value |
|---|---|---|---|
| `recorded_digests` of r1 (S2a) | never: written at enablement for every hot Ticket, and at creation afterwards | (none) | Fixed at enablement, so later control changes cannot move the baseline |
| `revision_events` (S2a) | events before enablement | derived from the existing decision records (`dependency_change`, `hierarchy_change`, `reclassification`, `promotion`) on the unit and on each current or carried ancestor. Each is placed at the **control revision that committed it**, read from the transition log (`state/log`, sealed segments). After enablement, each entry records its committing revision directly (X3) | Deterministic facts already in the canonical record (E19-B §5.5); every such change counts, ordered by revision, never by wall clock |
| `hierarchy_baseline` (S2a) | never: written at enablement and at creation | (none) | Exact |
| a Ticket's r1 pointer (S2c) | Tickets on a project enabled before S2c | implicit r1: `ticket.md` (immutable) with the `recorded_digests` from enablement | No revision path exists before S4a, so r1 is the fact. Its digests were fixed at enablement, not when the pointer is written |
| invocations' `ticket_revision` (S2c) | invocations created before S2c | 1 | No revision can exist before S4a |
| evidence `ticket_inputs` (S3) | legacy evidence | record-derived groups: the `recorded_digests` (exact, because the record is immutable). Control-derived groups (`dependencies`, `gate_set`): changed unless **every** event touching the group was committed at a control revision provably earlier than the evidence. The evidence's lower bound is the revision of its producing invocation's dispatch decision (a record cannot predate the invocation that produced it). An event at that revision or later, or one whose order cannot be established, counts as later (X3) | Every possible intervening change counts as a change, and an equal or unknown order counts as "later" (TRA-17, oracle 27); never UNCHANGED by default, and never dependent on clock resolution or steps |
| plan `ticket_binding` (S4a) | plans accepted before S4a | measured from **the plan's own acceptance**: the control revision that committed its `plan_acceptance` (or latest `plan_reconfirmation`) decision. Record-derived groups: the digests of the record current then (r1, immutable). Control-derived groups: changed if any touching event was committed at that revision or later, or in an unknown order (X3) | A `work depend` between the plan's acceptance and enablement counts, so the binding becomes a problem and the Lead reconfirms; nothing is measured from enablement |
| gate waivers' digests (S3) | waivers granted before S3 | measured from the waiver decision's committing revision, as for a plan: record-derived groups as of then; control-derived groups changed by any touching event at that revision or later (X3) | A later acceptance, check_definition or scope change lapses the waiver |
| `carried_obligations` (S2b.2) | always empty before S2b.2 | empty | Exact: S2a refuses every promotion and every Story or Epic move until S2b.2 |
| plan `upstream_bindings` (S8) | plans accepted before S8 | bound to **every** hold-relevant group (acceptance, check_definition, scope) of each upstream | Any change to the upstream holds the dependent (V3) |
| `revision_impact_holds`, `coverage_obligations` (S8) | before S8 | none | Exact: S4a refuses every revision that would need one (`REVISION_NEEDS_IMPACT_HOLD`, `REVISION_NEEDS_COVERAGE`; V2) |
| `revision_refusals` (S7) | before S7 | empty | Exact: no confirmation exists before S7 |
| `card_acceptance_bearing` (S7) | before S7 | not flagged | Exact: only an independent determination sets it, and none exists before S7 |
| a StageIntent's `ticket_revision` (S10) | intents opened before S10 | the Ticket's current revision | Exact: S4a refuses a revision while a stage is in flight (`STAGE_IN_FLIGHT`) |

`aew migrate --ticket-revisions` stays idempotent and writes each later slice's state from these defaults, so the
defaults and the written values never differ.

### 3.3 The field-group registry and current digests (S1; M10, m4, m8)

A versioned JSON document in the package, `src/aew/schemas/ticket-field-registry.v1.json`. Its identity is
`aew/ticket-field-registry/v1@<sha256 of its canonical bytes>`; every binding cites it.

| Field | Store | Group | Changed by |
|---|---|---|---|
| `acceptance.goal_backwards`, `acceptance.contract` | record | `acceptance` | revision |
| the record's body | record | `acceptance` (free text: fail closed) | revision |
| `external_refs` | record | `acceptance` (free text: fail closed) | revision |
| `acceptance.checks`, `acceptance.inputs` | record | `check_definition` | revision |
| `scope.paths` | record | `scope` | revision |
| `class0_assertions` | record | `gate_set` | revision (Class 0 eligibility rechecked) |
| `risk_class`, `initial_risk_class`, the effective class, the floor, inherited mandatory gates | control, record, derived | `gate_set` | `work reclassify` (raise only); re-parenting (§3.12); never a revision |
| `authorization_envelope` (E6b's stamp, when E6b has merged) | control | `gate_set` (it can influence publication authority, E19-B §2.3) | set by the engine at creation; never a revision |
| the effective dependency edges (own and inherited) | control, derived | `dependencies` | own edges: revision (`work depend` on a Ticket becomes one); inherited edges: an ancestor's `work depend` or a re-parenting |
| `carried_obligations` (S2b.2) | control | an input to the derived `gate_set` and `dependencies` groups, read only through the inherited-obligations accessor (§3.12a). It is revision-governed (E19-B §2.3: it influences gates and dependencies), not bookkeeping (V5) | a promotion or a Story or Epic move only; never a revision |
| `kind`, `mutating` | record, control | `kind` | never (replacement) |
| `parent`, `promoted_from` | record, control | `parent` | never by revision (§3.12) |
| `title` | record, control | `card` (presentation, non-material) | revision |
| `role_plan` | control | `staffing` (engine-defined, non-material) | `work staff` (ADR-0006) |
| `schema`, `id`, `created_at`, `created_by` | record | provenance (not an input) | never |
| state, history, the plan pointer, evidence refs, findings, waivers, invocations, workspace, integration, `blocked_by`, queue, stage intents, E5b's disposition index and anomalies | control | engine bookkeeping (not a revision-governed input) | their own governed paths |
| `hierarchy_baseline`, `recorded_digests`, `revision_events`, `revision_refusals`, `ticket_revision`, `revisions`, `revision_pending`, `revision_impact_holds`, `coverage_obligations` and the `child_promoted_out` history event | control | engine bookkeeping (V5) | F4's own paths |
| any other key in a record | record | `acceptance` (fail closed) | n/a |

- **Material groups** (E19-B §4.3): `acceptance`, `check_definition`, `scope`, `gate_set`, `dependencies` and `kind`.
  `card` and `staffing` are not material.
- **The title:**
  - New titles (on create and revise) are one line of at most 200 characters. The record schema is unchanged, so
    existing records still validate.
  - A per-Ticket override, `card_acceptance_bearing: {since_revision, by}`, makes `card` material and compares it
    wherever `acceptance` is compared.
  - It is set only by an independent determination naming the title (`unbound_field_escape`, from a confirmer or a
    reviewer).
  - It is cleared only by the independent confirmation of a revision that changes the title.
- **Current digests are computed live (M10):** from the current revision record, the control state and the derived
  obligations, at the moment of use. The derived groups (`gate_set`, `dependencies`) are computed through the
  inherited-obligations accessor (§3.12a), so they include `carried_obligations`.
  - **Evidence** binds the live digests at the moment it is sealed.
  - **Admissibility** compares an evidence record's bound digests with the live digests.
  - **A revision's changed groups** are its proposal's digests against the live digests just before it, so a change
    made earlier outside a revision (for example a raise by `work reclassify`) is never attributed to it.
  - **The cumulative diff** (r1 or the last checkpoint, to the proposal) shows everything, including changes made
    outside revisions.
- **Changes outside a revision are events in the revision history:** `work reclassify`, re-parenting, an ancestor's
  `work depend` that changes the effective edges, and `work staff`. `aew revision list` shows them in order between
  revisions, from their existing decision records (each decision records `work_unit`), so drift and the confirmer see
  them. The hot list holds only the decision ids (`unit.revision_events`); archival carries them.
- **Registry moves:** a later registry version lists `moves: [{field, from, to}]`. A group touched by a move counts as
  changed until the evidence is regenerated, or until the engine writes a mechanical revalidation record proving the
  moved field's content unchanged. Tested with a synthetic v2.
- **A meta-test** fails on any record or control-state unit key the registry does not classify. Every M4-E slice that
  adds a unit key therefore classifies it in the same pull request (§9.2).

### 3.4 Canonicalization (S1)

- Text values: exactly E19-B §2.4's v1 set (CR and CRLF to LF, Unicode NFC, trailing spaces and tabs removed). Nothing
  else is folded.
- Lists keep their order.
- Two explicit, versioned set rules:
  - `class0_assertions`: deduplicated and sorted;
  - the effective dependency edges: `{id, kind}` sorted by `id`, deduplicated.

  Both can make two authored values hash the same, so each has a collision conformance test (m7).
- A field with no rule uses its exact stored value.
- Digest per group: SHA-256 over `aew/tfg/v1:<group>\n` plus canonical JSON of the group's canonicalized fields.
- The authored bytes are kept: the raw proposal is stored byte for byte, and the revision record carries the values
  verbatim.

### 3.5 Evidence binding and computed admissibility (S3; M13)

- **`ticket_inputs`, an engine-owned field on every evidence record of an enabled project:** `{registry, revision,
  digests: {<every group>}}`. It is added to `ENGINE_OWNED`, so a submitter cannot supply it. Every group is recorded,
  so a later per-Ticket override can still be compared.
- **The registry's `evidence_classes`** (from D1's table):

  | Evidence | Compared groups | When a compared group changes |
  |---|---|---|
  | `implementation_report` (attempt-scoped) | acceptance, check_definition, scope, dependencies | HISTORICAL |
  | `check_result`, project check | none | UNCHANGED (snapshot, definition and plan bindings still apply) |
  | `check_result`, builtin guardrails | scope, check_definition | INVALIDATED |
  | `check_result`, engine (integration validation) | none | its candidate is retired by the revision |
  | `review` (Ticket scope) | acceptance, check_definition, scope | acceptance or check_definition: INVALIDATED; scope only: REVALIDATE |
  | `verification` (Ticket or integration scope) | acceptance, check_definition | INVALIDATED |
  | `discovery_record`, `research_record`, `plan_proposal` | acceptance, scope | acceptance: INVALIDATED; scope only: REVALIDATE |
  | a review or verification of an execute record | acceptance | INVALIDATED |
  | `revision_confirmation` | its attempt (§3.11) | SUPERSEDED when the attempt ends |

- **The derived states** (never written into a record):
  - **UNCHANGED:** every compared digest equals the live one, under a compatible registry.
  - **REVALIDATE:** only revalidatable groups changed. The record is inadmissible until a revalidation record exists.
  - **INVALIDATED:** an invalidating group changed.
  - **HISTORICAL:** an `implementation_report` whose bound groups changed, or whose attempt has ended. Only
    `implementation_report` is attempt-scoped (M13). A check result is snapshot-scoped and stays UNCHANGED across
    attempts while its bindings hold, which is what oracle case 3 needs.
  - **SUPERSEDED:** a later admissible record of the same gate, kind and card exists, or a revalidation record cites
    this one.
- **The gate rule:** `gates._matches` and `evaluate_evidence_unit.latest` also require the record to be admissible:
  UNCHANGED, or cited by a revalidation record bound to the live digests. Gate status keeps its own vocabulary; a STALE
  gate's detail names the admissibility state and the changed groups.
- **Revalidation records:**
  - mechanical ones are written by the engine, for registry moves only;
  - independent ones are a new review or verification that declares `revalidates: <id>` (S7). The engine checks the
    cited record is in REVALIDATE;
  - a Lead's note is advisory and no gate reads it.
- **Legacy evidence** (with no `ticket_inputs`) is compared group by group, conservatively (§3.2a, V3; TRA-17), and no
  file is rewritten:
  - **record-derived groups** are compared exactly with the `recorded_digests` written at enablement, because the record
    is immutable;
  - **a control-derived group** (`dependencies`, `gate_set`) counts as changed unless every event touching it was
    committed at a control revision provably earlier than the evidence's lower bound: the revision of its producing
    invocation's dispatch decision. The events are decision records before enablement, placed by the transition log,
    and `revision_events` after it. An equal or unknown order counts as later (X3). Wall-clock timestamps are never
    used.

  Legacy evidence is therefore never UNCHANGED by default.
- **Ingest** refuses a review or verification whose compared digests differ from the live ones. The record stays in
  history; S5 keeps its findings.
- **Gate waivers** record the acceptance, check_definition and scope digests, and lapse when one changes.

### 3.6 Records, attempts, the withheld rationale, hot state (S2a, S2c, S4a; M4, M10, R1)

- **Revision record:** `work/<T>/ticket-r<N>.md` (`aew/work-unit/v1`, with additive optional fields `revision`,
  `predecessor: {revision, path, sha256}`, `revised_at`, `revised_by`, `attempt` and `dependencies`, the own-edge set
  at that revision). r1 stays `ticket.md`. `unit.record` and `record_sha256` point at the current revision, so every
  existing reader follows it.
- **Attempt record:** `work/<T>/revisions/RA-<n>.yaml` (`aew/ticket-revision-attempt/v1`), written once at proposal.
  - **It holds:**
    - the expected revision;
    - the proposed fields and the raw proposal's hash (its bytes are at `RA-<n>.proposal`);
    - `rationale_digest`;
    - the computed changed groups, the live digests before the proposal and the proposed digests;
    - the cumulative base;
    - materiality and the count;
    - the triggers with their basis, and the requirements;
    - the mechanical checks, the impact preview, the lineage determination and the open-adverse snapshot;
    - the earlier confirmation records it carries (§3.11);
    - `expires_at`.
  - **It never holds the Lead's reason or alignment text.**
- **The withheld rationale (M4, N1, R1, R6, V6):**
  - The reason and the alignment assertion are written to `.aew/withheld/<T>/<digest>.yaml`, together with a fresh
    32-byte random salt drawn for that proposal (`secrets.token_bytes`).
    - `digest` is SHA-256 over the file's canonical bytes, which begin with the salt. The attempt record's
      `rationale_digest` names the file.
    - Nothing outside the masked directory holds the salt, so a reader of the attempt record cannot test guesses at a
      short rationale against the digest (V6).
    - **Decided: a per-proposal salt, not a per-project HMAC key.** A salt needs no long-lived secret to create,
      protect, rotate or back up. A project key exposed once (an uncontained host can read any file) would open every
      past digest, while a salt exposes only its own file.
  - That directory is used for nothing else, and it is created when the project is enabled (S2a), so it exists before
    any layout is built.
  - **The file is a pre-written immutable object.** The proposing operation writes it before its commit,
    create-if-absent, and the transaction references it through `Session.prewritten(path, sha256)`. The redo record
    `state/txn/<rev>.yaml` therefore holds only its path and hash, never its content (`store.py:17-23`).
  - **Content addressing keeps the prewritten contract (R1).** A path's bytes are deterministic, because the path is
    their hash. If a proposal fails after its prewrite (a stale `--expect-rev`, a refusal raised after the write, a
    crash), the file stays behind unreferenced, which is benign as for ADR-0011's pre-written records.
    - The next proposal draws a new salt, and so writes a different path, even for the same rationale.
    - Attempt numbers are never part of the path.
    - Test: `test_the_rationale_digest_reveals_nothing_without_the_salt` (V6).
    - Test: `test_a_proposal_that_fails_after_the_prewrite_never_blocks_the_next` (a forced failure after the prewrite,
      then two proposals: one with the same rationale, one with a different one; both commit).
  - The proposing transaction's transition record carries the fixed reason "revision proposed (rationale withheld)",
    never the Lead's text (`lead_txn(..., reason=...)` is otherwise written to the transition log). Its summary and refs
    name the attempt only.
  - **Test:** `test_no_state_file_holds_the_rationale_before_the_seal` searches every file under `.aew/state/` (the
    redo records, `state/log/`, the control file with its `last_transition`) and every other `.aew` file except the
    withheld one for the rationale text, between proposal and seal.
  - Every read projection (`revision show`, `revision list`, `work show`, `status`, `resume`, `history`, `explain`,
    decisions, the dashboard) renders `rationale: withheld (RA-n awaiting the confirmer's initial determination)` while
    the attempt has a confirmation obligation and no sealed initial record. After that, or when the attempt needs no
    confirmation, the projections render it. The decision record written at commit carries it in full.
  - From S7, containment masks `.aew/withheld/` with an empty tmpfs for every contained run, of every archetype
    (no role needs it). Confirmer layouts mask it unconditionally, creating the directory first if it is somehow
    absent, because the existing mask mechanism skips paths that do not exist (`_masks` checks `os.path.lexists`; R6).
  - On a host without OS containment, the masked directory is not available. There, withholding rests on the engine:
    every read path redacts, and the bridge gates the release. The residual is that an uncontained confirmer's shell
    could read the file directly. It is stated in §13 and labelled on the confirmation (§3.11).
  - The confirmer receives the rationale only through the bridge operation (§3.11).
  - Archival pins the file.
- **Decisions:** new types `ticket_revision`, `ticket_revision_abort`, `revision_checkpoint` and `supersession`. Every
  committed revision has exactly one `ticket_revision` decision.
- **Hot state on the unit** (bounded by live work; moves cold with the unit):
  - `ticket_revision: {current, path, sha256, recorded_digests (the record's own groups), registry,
    material_since_checkpoint, checkpoint: {revision, decision}, overrides}`;
  - `revisions: [{revision, path, sha256, attempt, decision, material, committed_rev}]`;
  - `revision_events: [decision ids]` (§3.3);
  - `revision_refusals: [{attempt, predecessor, change_digest, outcome}]` (§3.11);
  - from S4b on, `revision_pending`; from S8 on, `revision_impact_holds`, and `coverage_obligations` on parents; from S9
    on, `supersedes` and `superseded_by`.
- **Invocations** record `ticket_revision`, and a confirmer also records `revision_attempt`.
- **Plans** record `ticket_binding` (the revision, plus the live digests of acceptance, check_definition, scope and
  dependencies) and `upstream_bindings` (for own edges to Tickets), at accept and at reconfirm.
- **Transition events:** three derived kinds: `ticket.revision`, `ticket.revision_pending` and `ticket.impact_hold`.

### 3.7 The lifecycle (S4a, S4b; M2, m5)

| Command | Who | What |
|---|---|---|
| `aew revision propose <T> --fields FILE\|- --reason TEXT --alignment TEXT [--workspace carry\|fresh] [--impact] --expect-rev N` | Lead (`LEAD_REACHABLE`) | `--impact` is the same computation without a commit. Otherwise it proposes, and commits in the same transaction when nothing is outstanding |
| `aew revision commit <T> --attempt RA-n --expect-rev N` | Lead | Commits a pending attempt |
| `aew revision abort <T> --attempt RA-n --reason TEXT --expect-rev N` | Lead, or the operator at their terminal | Abandons the attempt |
| `aew revision checkpoint <T> --attempt RA-n --reason TEXT --expect-rev N` | Operator only (`OPERATOR_DECIDED` plus the attribution challenge) | The checkpoint (§3.11) |
| `aew invoke create <T> --revision-attempt RA-n [--card C] [--launch]` | Lead | The confirmer (§3.11) |
| `aew revision list <T> [--stats]`, `aew revision show <T> [--rev N] [--diff predecessor\|cumulative]` | read | History, with events; engine diffs (rationale redacted as §3.6 says) |
| `aew work replace <T> --because kind\|parent\|objective\|follow_up --reason TEXT <create arguments>` | Lead | Replacement (S9) |

- **Revisable fields:** title, body, `scope.paths`, `acceptance.*`, `class0_assertions`, `external_refs` and
  `depends_on` (own edges). The following are refused, each with a reason code:
  - `kind`, `mutating`, `parent` (`REPLACEMENT_REQUIRED`);
  - `risk_class` (raising it is `work reclassify`; no governed lowering path exists);
  - identity and provenance fields, and unknown fields;
  - any declared `changed_groups`, digests or admissibility.
- **Propose** (Lead transaction `revision.propose`, a CAS on `--expect-rev`):
  1. refusals (§3.8);
  2. compute the proposed record, the live and proposed digests, the changed groups, materiality, the count, the
     triggers and requirements (§3.9), the impact preview and lineage;
  3. write the raw proposal, the withheld rationale and the attempt record;
  4. **the fast path:** with no active invocation of the Ticket and no confirmation or checkpoint required, commit in
     the same transaction;
  5. otherwise, set `revision_pending` and, in the same commit, end every active invocation of the Ticket (credentials
     revoked).
- **`revision_pending`** is an overlay on the unit, not a workflow state: `{attempt, expected_revision,
  proposed_sha256, started_at, started_rev, expires_at, status: pending|aborting|expired, obligations, blocking}`.
- **What the pending guard refuses (M2):**
  - every dispatch entrypoint for the Ticket, except the confirmer's;
  - every lease grant for the Ticket's entry. The check is inside `queue_ops.grant`, the one function that grants a
    lease, so `integrate prepare`, E6a's re-lease of a VALIDATED entry and any later path inherit it. A test asserts
    that every lease grant passes through `grant`;
  - `integrate validate`, `integrate publish`, and E6b's custody publication (through `grant` and the publish
    function's own check);
  - `work transition` (every edge except to CANCELLED, which aborts the attempt), `work accept`, `work reconcile`;
  - `review ingest`, `verify ingest`, `verify classify`, and E5b's `work dispose` for the Ticket;
  - `plan accept`, `plan reconfirm`;
  - `work reclassify`, `work staff`, `work move` and `work promote` of the Ticket;
  - `work move` and `work depend` of any ancestor (these change derived groups);
  - `harness launch` of any Ticket invocation, **except the attempt's own confirmer** (R3). A crashed or lost confirmer
    run is relaunched like any invocation (M3-B1; `harness_ops.py:543-546`), with its forced containment and an
    engine-committed label (§3.11). Test: `test_a_crashed_confirmer_is_relaunched_during_pending`.
- **Commit** (`revision.commit`, a CAS on the control revision and on `expected_revision`) checks, against live state:
  - every obligation is met: each revoked run proven ended (`runlog`); the confirmation positive (S7); the checkpoint
    recorded (S7);
  - no lease is held;
  - the proposal's hash is unchanged.

  It then recomputes the digests, the changed groups, the triggers and the requirements from live state (M2). The
  requirements in force are the union of the proposal's and the recomputed ones; they never shrink. If they grew, or if
  the changed groups or the effective class differ, the commit is refused (`REVISION_REQUIREMENTS_CHANGED`) and the
  attempt must be aborted and proposed again.
- **What the commit applies, in one transaction:** the revision record and decision; the pointer, the list and the
  count; the state rule (§3.10); plan binding; the workspace's fate (§3.10, S6); received failing reports' findings (S5);
  impact holds and coverage obligations (S8).
- **Abort:**
  - the attempt record stays, and a `ticket_revision_abort` decision is recorded;
  - an active confirmer is ended in the same transaction (m5);
  - the outcome follows §3.11's binding rules;
  - the old revision stays current;
  - the overlay goes to `aborting` until every revoked run is proven ended. The finalizer of a later commit then
    clears it, and admission returns.
  - No lease is touched.
- **Expiry:** set by `gates.ticket_revision.pending_expiry_s` (operational, default 3,600).
  - Expiry is derived at read: projections show the attempt as expired, with attention.
  - The next Lead commit's finalizer records it, ends an active confirmer and enters the abort path. Admission stays
    blocked throughout.
  - With no Lead session, the operator's `aew revision abort` at their terminal is the path (m5).
  - A timeout never releases a lease and never forces a commit.
- **Cancellation** of the Ticket, or its parent's cascade, aborts a pending attempt in the same transaction.
- **A Lead generation change (N7), fail closed:**
  - The transaction that changes the Lead generation (a takeover, an accepted handoff, a release) aborts every pending
    attempt, as a finalizer, like M4-E's retirement of generation-bound confirmations and envelopes (the M4-E plan's finding R1).
  - It ends each attempt's confirmer. The outcome follows §3.11's binding rules: a confirmer that had been dispatched
    without a positive final record binds forward.
  - The attempt's alignment assertion belonged to the ended generation, and no other Lead may commit it. A new
    generation that wants the change proposes it again, with its own assertion.
  - Revoked runs keep the overlay in `aborting` until they are proven ended, as for any abort.
  - Test: `test_a_generation_change_aborts_pending_revisions[takeover,handoff,release]`.

### 3.8 Mechanical refusals (S4a, S4b)

Each refusal has its own reason code and names what to do instead.

- DONE, CANCELLED or archived: `TICKET_TERMINAL`.
- The entry holds the lease, or the lease is awaiting reconcile: `LEASE_HELD` (`aew integrate defer`; `aew integrate
  reconcile`).
- A kind or parent change: `REPLACEMENT_REQUIRED`.
- Effective class lowered, or an inherited mandatory gate dropped (checked against the recomputed effective
  obligations): `GATE_SHEDDING`.
- Hierarchy refusals (§3.12, from S2a): `REPLACEMENT_PATH_UNAVAILABLE` (S2a to S9), then `REPLACEMENT_REQUIRED`;
  `FINISHED_HIERARCHY_FINAL`; `HIERARCHY_RULES_PENDING` (S2a until S2b.2); `HIERARCHY_NOT_MONOTONIC`.
- A new overlap with protected paths (`assurance.protected_overlap`), or a scope glob containing a comma:
  `GUARDRAIL_POLICY`.
- A dependency cycle: `DEPENDENCY_CYCLE`.
- Scope provably outside a parent's declared scope: `SCOPE_OUTSIDE_PARENT`. When containment cannot be proven, the
  revision is not refused; it becomes a confirmation trigger (§3.9, m3).
- `VERIFICATION_FAILED`: `CLASSIFY_FIRST` (reading RD1, §4.2).
- A pending attempt already exists: `REVISION_PENDING`.
- The project is not enabled: `TICKET_REVISIONS_NOT_ENABLED`.
- Binding refusals (§3.11): `CONFIRMATION_REFUSED_SAME_CHANGE`.
- Interim refusals (§3.0 rule 1): `REVISION_NEEDS_IMPACT_HOLD` and `REVISION_NEEDS_COVERAGE` (S4a until S8; V2),
  `REVISION_OF_STARTED_WORK` (until S4b), `REVISION_NEEDS_CONFIRMATION` and
  `REVISION_NEEDS_CHECKPOINT` (until S7), `STAGE_IN_FLIGHT` (until S10), and `REVISION_PATH_UNAVAILABLE` for
  `work depend` on a Ticket (S2a to S3 only).

### 3.9 Triggers and requirements (S4a computes; S5 and S7 complete; M1, m3)

- **Material:** the change set meets a material group (or `card`, under the title flag).
- **The count:** material revisions since the last checkpoint (r1 is the base). A checkpoint is required when the count
  would exceed `gates.ticket_revision.checkpoint_after` (legality, default 3, an integer ≥ 0). The count and the
  threshold are shown by `--impact`, `status` and `resume`.
- **Independent confirmation is required** when any of these holds (E19-B §4.2):
  1. the effective class at proposal is 2 or more (every revision, presentation-only included: reading RD4, §4.2);
  2. `acceptance` or `check_definition` changes while acceptance-bearing evidence for the Ticket exists, received or
     ingested: any review or verification, any check result for an id in `acceptance.checks`, any execute record;
  3. `acceptance` or `check_definition` changes after a passing review or verification;
  4. the anti-laundering trigger: an adverse outcome or unresolved adverse evidence, plus a change to acceptance,
     check_definition, scope, gate_set or dependencies, plus carried lineage;
  5. the checkpoint is required;
  6. containment of the proposed scope within a parent's declared scope cannot be proven (m3);
  7. an earlier confirmation on this Ticket, from the same predecessor revision, ended without a positive final record
     (§3.11).
- **The interim predicate (S4a until S5; M1):** `may_be_adverse` holds when any of these exists for the Ticket:
  - a record with result `fail`, `inconclusive` or `blocked`, received or ingested, of any kind;
  - an open finding, required or not;
  - a state in its history among REVIEW_FAILED, VERIFICATION_FAILED, VERIFICATION_INCONCLUSIVE, ESCALATED and
    INTERRUPTED;
  - a queue entry in AWAITING_DISPOSITION;
  - an open disposition item or anomaly (when E5b has merged).

  Lineage is taken as present. Trigger 4 then reads "`may_be_adverse` and a change to a material group", which is a
  superset of S5's exact trigger. S5 keeps `may_be_adverse` as a test oracle and asserts the superset property on every
  seeded state: `test_the_interim_predicate_is_a_superset_of_open_adverse`.
- **Lineage (S5), exact:** carried whenever any implementation content exists under an earlier revision of the Ticket:
  a workspace with a non-empty diff against its base, an implementation report, or an integration candidate. It is
  keyed on the Ticket identity, so a fresh worktree cannot reset it. A positive match routes to confirmation and never
  rejects.

### 3.10 The state after a commit (S4a, S4b, S6; M7, M8, m10)

One ordered rule. The first case that matches applies:

1. **Unstarted** (BLOCKED, READY or REPLAN_REQUIRED) with no active invocation: the state is unchanged. Readiness is
   recomputed, and a changed plan-bound group shows as `plan_stale` until the Lead reconfirms or replans.
2. **Started, and nothing live:** no invocation was quiesced, there is no candidate, the plan binding is unaffected,
   and the revision is not material. The state is unchanged; for example, a title fix in REVIEW_PASSED.
3. **Any other started Ticket:** REPLAN_REQUIRED, through a `via: revision.commit` rule on each `(S, REPLAN_REQUIRED)`
   edge (VERIFICATION_FAILED never reaches this point; §3.8). In the same commit:
   - the COMMIT_READY entry is retired by `sync`, VALIDATED included once E6a has merged;
   - the workspace is released (`released (revised)`) when `--workspace fresh` is given, or before S6 always (M8). From
     S6, `--workspace carry` (the default) marks it `carried`.

Both case 2 and case 3 are tested.

- **Plan binding, defined (N4).**
  - The accepted plan records `ticket_binding: {revision, digests}` for acceptance, check_definition, scope and
    dependencies.
  - The binding problem is computed on those four digests only: each recorded digest against the live one (§3.3).
    `revision` is provenance, never compared, so a title-only revision of a READY Ticket leaves its plan bound.
  - A binding problem is resolved by a new plan revision, or by `plan reconfirm`. Reconfirm records a new Lead
    plan-acceptance decision that binds the live digests and the current revision. It keeps the plan revision, which
    keeps unrelated check results current (reading RD2, §4.2).
  - `plan_binding_problem` also keeps today's checks (ancestor plans, `bindings_invalidated`).
- **The reconfirm edge (M7, N4):**
  - `REPLAN_REQUIRED -> BLOCKED|READY via plan.reconfirm` applies only when the Ticket's latest entry into
    REPLAN_REQUIRED was `via: revision.commit`.
  - In that case `plan reconfirm` is accepted **even when no plan-bound digest changed** (a title-only revision of a
    started Ticket). Its decision records the rebinding to the new revision, and today's "nothing to reconfirm"
    refusal (`nonmutating_ops.py:913-916`) applies only outside this case.
  - An entry by `transition`, `verify.classify` or promotion still needs `plan accept` of a new revision. That is
    today's rule: AT-10 closes a promotion's REPLAN_REQUIRED with a new plan.
  - The edge lands in S4b.
  - Tests: `test_reconfirm_never_closes_a_classification_replan` (a classification-caused REPLAN_REQUIRED, then a
    revision, then `plan reconfirm`, is refused); `test_reconfirm_closes_a_title_only_revision_replan`.
- **The next action** follows from the impact: `revision show`, `resume` and the guide list it.

### 3.11 Independent confirmation and the checkpoint: the protections (S7; M4, M5, M6, m5, R2, R3, R7)

- **Admission:**
  - Entrypoint `invoke.create.revision`, scope `revision`, the reviewer archetype, an observation of the authoritative
    commit.
  - `card.confirmer` admits only `gates.ticket_revision.confirmation_cards[<effective class>]` (legality; by default,
    the resolution of the `review_r1` card). A `--card` that differs is refused (m5).
  - **Containment, by host and by the operator's mode (N2, N3, X1; A22; never weaker than the operator adopted):**
    - Containment is decided per run, at launch, by the execution policy's `containment.mode` (`required` or
      `allow_weaker`) and the host's capability (`policy/execution.py:54-57`; `containment.establish`).
    - **The confirmer's mode is the stronger of the project's mode and the host's capability (X1).** The engine never
      runs a confirmer under a weaker mode than the operator adopted (#118's pin; A1):

      | Host capability | Project's `containment.mode` | The confirmer |
      |---|---|---|
      | capable: `containment.supported()` and a passing host self-test | either | forced `required`, so contained |
      | not capable: Windows, or a Linux or WSL host whose self-test fails (`AEW_RL8`'s slirp4netns case, missing bubblewrap, user namespaces off) | `allow_weaker` | runs uncontained, with the truthful weaker label (`job_object` plus `workdir_separation_only` on Windows; `workdir_separation_only` elsewhere) and the probe's `self_test: {ok: false, reason}` (F23) |
      | not capable | `required` | refused: `CONFIRMER_CONTAINMENT_UNAVAILABLE`. The revision cannot be confirmed on this host until the operator restores containment, or adopts `allow_weaker` |

    - **`aew doctor`** reports the confirmer's row for the host:
      - capable: "confirmers run contained";
      - not capable under `allow_weaker`: "confirmers run uncontained on this host, labelled weaker: containment
        self-test failed (<reason>)";
      - not capable under `required`: "confirmations unavailable on this host: containment self-test failed
        (<reason>); adopting `containment.mode: allow_weaker` would run them labelled weaker". That is the operator's
        choice, never the engine's.
    - **Tests:**
      - `test_a_capable_host_always_contains_the_confirmer[required,allow_weaker]`;
      - `test_an_incapable_host_runs_a_labelled_uncontained_confirmer_under_allow_weaker` (a fixture that makes the
        probe fail, and on `AEW_RL8`);
      - `test_a_required_project_refuses_an_uncontained_confirmer` (X1);
      - `test_doctor_names_allow_weaker_as_the_operators_choice` (X1).
    - **The label and the capability are engine-owned (R2). The probe never runs inside the Lead transaction (X1), and
      a downgrade never comes from a file (Y1).**
      - **The host-probe cache** holds the result `aew doctor` and the supervisor's launch already produce
        (`containment.doctor`, `probe.self_test`, `containment.establish`). It lives at
        `.aew/local/host/containment-probe.json`, keyed by:
        - the host's identity (boot id and hostname);
        - the bubblewrap binary's path and hash;
        - the kernel release;
        - the engine version;

        with a time-to-live (default 1 h).
      - **The cache may only short-circuit a "capable" verdict (Y1).** When the cache says "capable" with a valid key
        and time-to-live, the launching command may skip the probe and launch with `required`. That is safe however the
        entry was written: a false or stale "capable" fails closed at `containment.establish`, so no run exists.
      - **A "not capable" verdict always comes from a probe the launching command runs itself (Y1),** in its own
        process, before it takes the store lock, every time it would launch a confirmer weaker. A cached "not capable"
        is never used for a confirmer. It only tells the command to probe now.
        - The probe's result and its time are passed into the launching transaction in memory, never through a file.
        - The transaction records exactly that result, its time and its reason on the run's label.
        - The command also refreshes the cache with the result, which `aew doctor` reads, but the cache never decides a
          downgrade.
        - Bubblewrap is never spawned inside a Lead transaction under the store lock.
      - **Inside the launching transaction,** the engine re-validates the in-memory or cached result with cheap facts
        only: the key still matches (platform, bubblewrap's path and hash, kernel release, boot id), and the result is
        within its time-to-live, or, for a fresh probe, a short freshness bound (default 60 s). A mismatch refuses the
        launch with `CONTAINMENT_PROBE_STALE`; the command then probes again and retries.
      - **What a forged or stale cache can do** (corrected, Y1):
        - A false or stale "capable" cannot loosen anything. It forces `required`, so the launch fails where containment
          cannot be established.
        - A false or stale "not capable" cannot loosen anything either, because it is never used for a confirmer: the
          launching command probes the host itself. A forged downgrade written by an uncontained same-uid process (in
          practice, the Lead's own harness session) therefore yields a contained confirmer on a capable host. A host
          the operator has repaired (user namespaces enabled by `sysctl`, with no reboot or key change) contains the
          next confirmer at once, not after the time-to-live.
        - The residual is the same-uid one every pre-F18.6 boundary carries (`guarantee: dev`): a process that can
          alter the engine's own code or the probe's binary is outside this plan.
      - **Tests:**
        - `test_a_forged_not_capable_cache_never_downgrades_a_confirmer` (a capable host under `allow_weaker`, a cache
          entry written by a same-uid process saying "self-test failed" with a valid key and time: the confirmer runs
          contained, and its label shows the fresh probe);
        - `test_a_repaired_host_contains_the_next_confirmer_despite_a_stale_not_capable_cache` (the cache still says
          "not capable" within its time-to-live, the host now passes: the fresh probe wins);
        - `test_a_downgrade_label_records_the_in_memory_probe_and_its_time`.
      - **The engine commits the capability, the effective mode and the resulting label** on the invocation's `runs[]`
        entry, in the launching transaction, before any agent process exists:
        - where capable, the mode is `required` and the label is `contained`. A `required` launch either establishes
          containment or fails (`containment.establish`), so a run that exists is contained. If the supervisor's own
          self-test then fails (the host changed), the launch fails, and the relaunch's fresh probe sees the failure;
        - where not capable (by a fresh probe only), the outcome is the table's.
      - **It never reads the label or the capability from the run directory,** which "is writable by the run's own
        user" (`runlog.py:42-43`). The supervisor's run record keeps its own copy for diagnostics only.
      - **A relaunch** commits its own entry the same way.
    - **The confirmation is accepted** (at ingest, and again at commit) only when the run that produced it has an
      engine-committed entry. Its label is copied from that entry onto the confirmation, the revision decision and TR-9,
      never from the submitter or the run record. A confirmation from a run without such an entry is refused
      (`CONFIRMER_LABEL_UNVERIFIED`). Test: `test_a_confirmer_that_rewrites_its_run_record_is_still_labelled_by_the_engine`.
    - **The label is shown** on the confirmation record, in `status`, `explain`, `revision show`, the completion and
      closeout records, and TR-9. A weaker label is never presented as the Linux production guarantee (F23).
    - Nothing forces replacement on any host (E19-B §1).
  - At most one confirmer per attempt.
- **Material order (M4):**
  - The confirmer's pack is the engine material only:
    - the predecessor diff and the cumulative diff;
    - the parent's record, the effective obligations, and the envelope and coverage obligations;
    - the registry identity, the open-adverse set and lineage;
    - every earlier confirmation record of the Ticket since its current revision, sealed or abandoned;
    - the revision events.
  - The rationale is in `.aew/withheld/`, which is never in a redo record (§3.6), and which every projection redacts.
    In a contained run the directory is also masked, so the rationale is unreadable from the confirmer's shell and by
    any `aew` command inside its sandbox. In an uncontained run, the engine's read paths and the bridge still withhold
    it, but the confirmer's own shell could read the file. That residual is the weaker label's meaning (§13).
  - The bridge operation `revision.rationale` returns it only to the attempt's confirmer, and only after that
    confirmer's `initial` record is sealed.
  - The confirmation records `containment` from the engine-committed run entry (R2), and `guarantee: dev` while F18.6's
    production principal boundary is absent (as M4-E labels pre-F18.6 boundaries).
  - **The Lead's own transcript (R7).** The Lead typed the rationale into `aew revision propose`, so the Lead harness's
    session store holds it too.
    - A contained confirmer's layout also masks the Lead harness's session-store paths. They are taken from the Lead's
      execution profile, through the harness adapter's declared session-store locations; the OpenCode adapter's are
      already in `SECRET_DIRS` (`layout.py:46-50`).
    - `aew doctor` warns when the Lead harness's store is not covered by a mask, and points to `containment.hide`.
    - The residual (a store the adapter does not declare, and every uncontained host) is stated in §13.
- **Records:** evidence kind `revision_confirmation`, in two phases:
  - **`initial`:** the four determinations of §4.2.1;
  - **`final`:** cites `initial`, and records:
    - the four determinations;
    - per-adverse-item dispositions (`still_applies`, `inapplicable_under_revision`, `resolved`);
    - a disposition for each earlier refusal (`still_applies`, `addressed_by_change`);
    - `unbound_field_escape`;
    - `suspected_failure_classes`;
    - parent obligations raised.

  The commit needs a positive final record.
- **No confirmer shopping (M5):**
  - Ending the confirmer *invocation* for any reason (a cancel, an abort, expiry, a generation change) ends the
    attempt's confirmation path (`confirmation_lost`). The attempt can then only be aborted. A confirmer *run* that
    crashes, or is lost, is not an end: the invocation is relaunched (R3).
  - Any attempt whose confirmer was dispatched and which ends without a positive final record binds forward. It is
    recorded in `revision_refusals` with its predecessor and the digest of its proposed digests (the change digest):
    - aborting, or expiring, after a sealed negative `initial` or `final` record is `refused_by_confirmation`;
    - any other unconfirmed end is `confirmation_abandoned`.
  - A proposal from the same predecessor whose change digest equals that of a `refused_by_confirmation` entry is
    refused: `CONFIRMATION_REFUSED_SAME_CHANGE`. Only a sealed negative determination bars the same change (R3).
    `confirmation_lost`, `confirmation_abandoned` and generation-aborted attempts never bar it. Test:
    `test_the_same_change_is_proposable_after_an_abandoned_confirmation[lost,generation_change]`.
  - Any other proposal from the same predecessor, the same change after an abandoned attempt included, requires
    confirmation (trigger 7). Its confirmer sees every earlier
    record. The refusal stays in `open_adverse` until a positive final record disposes it as `addressed_by_change`.
  - A committed revision closes the predecessor's list. Its refusals stay in the history, and the new revision's
    `open_adverse` keeps any disposed `still_applies`.
- **The checkpoint (M6):**
  - `aew revision checkpoint` renders, at the operator's terminal and before the challenge, the cumulative diff (r1 or
    the last checkpoint, to the proposal), the predecessor diff, the parent envelope, the revision events and the
    count.
  - The `revision_checkpoint` decision records the digest of what was shown, and binds the attempt.
  - The checkpoint then becomes the cumulative base.
  - It changes no finding, gate, waiver or admissibility.
  - Tests: `test_the_checkpoint_shows_the_cumulative_diff_and_binds_it`,
    `test_a_checkpoint_waives_no_evidence_finding_or_gate`.

### 3.12 Hierarchy changes on an enabled project (S2a, S2b.2; S8 adds holds; S9 adds replacement; §10; handoff §15)

These apply on enabled projects only. A dormant project keeps ADR-0007's rules (§3.0 rule 2, D4). The interim
refusals land in S2a and the rules in S2b.2 (R8, V1). Until S2b.2, every promotion and every Story or Epic move on an
enabled project is refused (`HIERARCHY_RULES_PENDING`), which is §3.0 rule 1.

- **A Ticket's parent never changes after `work create`, except by promotion** (D1; the ruling; handoff §15).
  - AEW has no draft or uncommitted Ticket, so the identity governs from `work create`. Even M4-E's `ticket_draft` stage
    runs `work.create` as its first step.
  - `work move` of a Ticket is refused whatever its state: from S2a to S9 with `REPLACEMENT_PATH_UNAVAILABLE`, then with
    `REPLACEMENT_REQUIRED` (`aew work replace <T> --because parent`).
  - The parent is chosen at creation. If E5a adds a construction step before `work.create`, the parent may be corrected
    there, since no identity exists yet. §11 lists a possible future relaxation.
- **Finished hierarchy is final.** `_move_archived` is refused for every unit (`FINISHED_HIERARCHY_FINAL`); a follow-up
  is a new unit (E19-B §3(5)).
- **A revision never changes `parent`** (E19-B §3(2), §11): `REPLACEMENT_REQUIRED`.
- **Promotion is allowed, wherever the unit sits, and carries what it leaves (R4; governed).**
  - **The sources:**
    - KC v0.4 §9.4 (frozen): "Work may be promoted when evidence reveals the original unit is too small", Ticket to
      Story to Epic, with no condition on the parent.
    - The ruling (§10): promotion "remains allowed after work has started".
    - Handoff §15: promotion "remains allowed after work starts and preserves original Ticket identity,
      evidence/history, effective risk/class floor, and inherited non-waivable gates/guardrails".
  - **The new unit is placed as today** (under the nearest ancestor of a permitted kind; `hierarchy_ops.py:520-526`).
    This leaves behind every ancestor that is no longer an ancestor afterwards (for a Ticket in a Story promoted to a
    Story, the old Story).
  - **Carried obligations.** In the promoting transaction, each ancestor left behind hands its inherited obligations to
    the new unit, recorded in control state as `carried_obligations: [{from, decision, min_descendant_class,
    mandatory_gates, guardrails, depends_on, scope_envelope, impact_holds}]`:
    - the class floor (`min_descendant_class`);
    - the mandatory gates, which are today exactly the non-waivable inherited gates;
    - any ancestor guardrails (none exist today; carried if F5 adds them);
    - the ancestor's dependency edges;
    - its declared-scope envelope;
    - impact holds on it (from S8).

    Every ancestor-derived value is read through the one accessor of §3.12a, which folds in the `carried_obligations` of
    the unit and its ancestors exactly as it reads ancestor policy, edges, scope and holds. So every affected Ticket's
    inherited obligations, and every value derived from them, are unchanged by the promotion (V1). The records stay immutable; the carry is
    control state, archived with the unit.
  - **The old parent's own obligations stay its own,** re-evaluated by the existing rules:
    - its children digest changes, so its existing parent reviews go STALE, as for any change of its child set today;
    - **coverage obligations, the one rule (V4):** a coverage obligation is the parent's own and is outside the
      monotonic set. An open one that names a Ticket promoted out stays on that parent, re-pointed to record where the
      Ticket went (the promotion decision and the new unit). It is discharged only by that parent's next independent
      review bound to its current children digest, and is never dropped. Story and Epic moves follow the same rule;
    - its closeout record lists every child that left by promotion, with the decision.
  - **Both units' histories** record the promotion: the old parent's as a `child_promoted_out` event naming the decision,
    the new unit's as `promoted_from`. Each affected Ticket gets a revision-history event (§3.3).
  - **S12 does not narrow the frozen operation.** AT-10 (`tests/acceptance/test_at8_at13_hierarchy.py:153`) and
    `tests/integration/test_hierarchy.py:144` (a Ticket promoted out of its Story) pass unchanged on an enabled project.
- **Story and Epic moves get the same carry.** A moved Story or Epic receives, as its own `carried_obligations`, what
  the ancestors it leaves would have given its subtree. Its descendants' inherited obligations are therefore unchanged.
  The old parent's own closeout and coverage are re-evaluated as above. Moves remain a parent restructure, F5's to
  design further.
- **Monotonic over inherited obligations (D4, R4).** For every hot Ticket a move or promotion affects, the **monotonic
  set** after the change, carried obligations included, must contain the set before it:

  | Element | Today's source | "Contains" means |
  |---|---|---|
  | effective class | `gates.effective_class` | not lower |
  | inherited mandatory gates | ancestors' `policy.mandatory_gates`, which `effective_obligations` makes non-waivable (`non_waivable = sorted(inherited)`) | a superset |
  | ancestor guardrails | none on ancestors today; F5's join the set | a superset |
  | inherited dependency edges | `effective_edge_set` | a superset |
  | declared-scope envelopes | ancestors' declared `scope.paths` | every envelope still applies |
  | impact holds reaching through an ancestor (from S8) | `revision_impact_holds` on an ancestor dependent | each still applies |

  - Coverage obligations and closeout are not in the set. They are the parent's own obligations, not the Ticket's
    inherited ones (handoff §15 lists what promotion preserves). They follow the one rule above (V4).
  - The Ticket's own `acceptance_checks` gate is not ancestor-derived, so it is unaffected.
  - A change whose obligations cannot all be carried is refused with `HIERARCHY_NOT_MONOTONIC`, naming the element. For
    example, a carried dependency edge that would create a cycle (`refuse_cycles`).
- **TR-14 (S2a; the promotion exception in S2b.2; R5):** on an enabled project, every hot Ticket's parent equals its `hierarchy_baseline.parent`, except
  through a recorded promotion.
  - `hierarchy_baseline` is recorded in control state for every hot Ticket at enablement (its parent at that moment, so
    a move made under ADR-0007 before enablement is the baseline), and at creation afterwards.
  - Each promotion updates it, citing the promotion decision.
  - The oracle checks TR-14 after every walk step, and also checks that the monotonic set never shrinks across a step.
- **Tests (S2b.2, with §3.12a's before-and-after tests; the interim refusals in S2a):**
  - `test_a_ticket_never_moves_after_creation[blocked,ready,running,done_archived]`;
  - `test_finished_hierarchy_never_moves`;
  - `test_promotion_and_parent_moves_are_refused_until_the_hierarchy_rules_land` (S2a);
  - `test_promotion_out_of_a_story_carries_every_inherited_obligation` (a Ticket under a Story with a floor, a
    mandatory gate, an edge and a declared scope; the Ticket's effective obligations are unchanged);
  - `test_the_old_parent_re_evaluates_its_closeout_and_records_the_promotion`;
  - `test_a_story_move_carries_what_its_old_ancestors_gave_its_subtree`;
  - `test_an_uncarriable_obligation_refuses_the_change` (a cycle);
  - `test_tr14_baselines_at_enablement_after_an_earlier_move` (R5);
  - `test_a_dormant_project_keeps_adr_0007s_move_rules`;
  - AT-10 and `test_hierarchy.py:144` run enabled and pass unchanged.

  S8 adds `test_a_promotion_carries_an_impact_hold` and
  `test_a_coverage_obligation_naming_a_promoted_child_is_re_pointed_and_discharged_by_review` (V4).

### 3.12a One accessor for every ancestor-derived value (S2b.1; V1)

Carrying obligations is only as complete as the code that reads them. v5 puts every ancestor-derived value behind one
accessor before any obligation is carried.

- **The accessor:** `hierarchy.inherited(state, wid) -> Inherited`. It walks the unit's ancestors, and folds in the
  `carried_obligations` of the unit itself and of every ancestor (empty until S2b.2). It returns:
  - `floors` (each with its source);
  - `mandatory_gates` (each with its sources; these are the non-waivable inherited gates);
  - `guardrails` (empty today);
  - `edges` (the inherited dependency edges);
  - `scope_envelopes`;
  - `holds` (from S8);
  - `chain` (the ancestor and carried-from ids, for context).
- **Every existing reader is routed through it.** Enumerated from the code at `0ff0435`:

  | Reader | Where | What it feeds |
  |---|---|---|
  | `gates.effective_class` | `gates.py:78-80` (its own walk of `policy.min_descendant_class`) | execution-profile routing at dispatch (`workspace_ops.py:90`); F4's confirmation threshold (§3.9 trigger 1); the confirmer card |
  | `gates.effective_obligations` | `gates.py:84-115` | gate evaluation (`evidence_ops.py:169`, `hierarchy_ops.py:89`, `nonmutating_ops.py:626`); assurance triggers and Class 0 eligibility (`assurance_ops.py:77`, `assurance.inherited_elevation`); the pack's inherited obligations (`context_ops.py:43`) |
  | `policy/validation.obligation` | `validation.py:61-89` (its own walk for `post_integration_verifier` and verifier floors) | the post-integration validation mode and binding (`integration_ops.py:428`, `:440`, `:549`; `resume_ops.py:290`; `validation_ops.py:154` and its callers) |
  | `hierarchy.effective_edges` | `hierarchy.py:165-170` | readiness (`dependencies.py:89`); `effective_edge_set` (`dependencies.py:127`) and so dispatch binding (`dependencies.py:161`), attempt edges (`workspace_ops.py:344`, `nonmutating_ops.py:458`, `hierarchy_ops.py:198`), parent acceptance and closeout (`hierarchy_ops.py:105`, `:229`, `:368`) and the move check (`:441`, `:475`); cycle refusal (`hierarchy.waits_for`, `:173-190`); non-mutating dispatch inputs (`nonmutating_ops.py:105`) |
  | `work_reclassify`'s floor | `work_ops.py:424-427` (its own walk) | the refusal and `effective_minimum_at_decision` |
  | `gates.ancestors` | `gates.py:69-75` (a duplicate of `hierarchy.ancestors`) | removed; its callers use the accessor |
  | the pack's ancestor chain | `context_ops.py:37` | context only: the chain shows carried-from ancestors as well, labelled, so the old parent's purpose stays visible |
  | the scope-envelope check (S4a) and the hold guard (S8) | new | built on the accessor from the start |

- **A static test,** `test_only_the_accessor_derives_inherited_obligations`, parses every module under `src/aew` with
  Python's `ast` and walks each function (Y2, Z1). It is not a substring or name search, and it reads only `Load`
  contexts: assignments, keyword arguments, parameters and dictionary-literal keys never match.
  - **Three rules, by key:**
    1. **Calls:** any `Call` whose callee is `ancestors`, `H.ancestors`, `hierarchy.ancestors`, `effective_edges` or
       `H.effective_edges` (exact names; `maps/structural._ancestors` is a different name and never matches).
    2. **Obligation keys on any receiver (Z1):** a `Subscript` or `.get(...)` read of `min_descendant_class`,
       `mandatory_gates`, `carried_obligations` or `policy`, **whatever the receiver is**. These keys belong only to
       work units (and to a `policy` value read out of one), so no tracing of the receiver is needed.
       - The single exception is a receiver rooted at the project manifest: `manifest`, `self.manifest`,
         `self.k.manifest`, `self._manifest[...]`, or a name bound from one of those. Its `policy` entry names the
         policy files, not a unit's policy.
    3. **Ambiguous keys on work-unit expressions only:** a `Subscript` or `.get(...)` read of `parent` or `depends_on`,
       and a `while` or `for` loop whose step reads `parent`, when the receiver is a work-unit expression.
  - **Work-unit expressions (for rule 3), widened (Z1).** Within a function:
    - **Work-map sources:**
      - `state["work"]`, whatever the state's receiver is called (`state`, `ctx.state`, `s.state`, `self.state`,
        `view`);
      - any name bound to one, by alias (`work = state["work"]`, `archive_ops.py:271`);
      - any copy or merge of one (`{**state["work"], ...}`, `dict(state["work"])`, `copy(...)`; `archive_ops.py:765`);
      - any parameter annotated `WorkMap`, or named `work` or `hot`.
    - **Unit sources:**
      - a subscript or `.get` of a work map;
      - a name bound from one;
      - the target of a `for` statement **or of a comprehension generator** over a work map, its `.values()` or its
        `.items()` (`archive_ops.py:616`; `dashboard/projections.py:776`);
      - the results of `H.upstream(...)`, `self.units.unit(...)`, `self.units.view(...)`,
        `self.archive.archived_unit(...)` and `rehydrate(...)`;
      - any parameter annotated `Unit`, or named `unit`, `u`, `up`, `child`, `anc`, `ancestor`, `parent_unit` or
        `upstream`.
    - **Annotations:** S2b.1 adds `Unit` and `WorkMap` type aliases to `hierarchy.py` and annotates every existing
      function that takes a unit or the work map, so new code is recognised by annotation, not only by name.
  - **Fixture (Z1):** `tests/unit/test_accessor_matcher.py` holds small synthetic modules, and asserts that each of
    these forms matches:
    - an alias of the work map (`work = state["work"]`; `work[x].get("parent")` in a loop);
    - a merged copy (`work = {**state["work"], k: v}`);
    - a comprehension generator (`max(u.get("policy", {}).get("min_descendant_class") for u in work.values())`, and
      `[u.get("depends_on") for _, u in sorted(state["work"].items())]`);
    - a parameter named `u`, and one annotated `Unit`;
    - a `policy` read on an arbitrary receiver (`x["policy"]["mandatory_gates"]`).

    It also asserts that none of Y2's false-positive sites matches (the table below), and that a manifest receiver
    never matches.
  - Each match outside `hierarchy.inherited` and the allow-list fails the test, which names the function, the line, the
    rule and the key. The test also fails if an allow-list entry names a function that no longer exists, so the list
    cannot rot.
- **The structural allow-list, in full, re-checked against `df839fd` with the widened matcher (X2, Z1).**
  - Each entry is a qualified function and **only the rules and keys it names**. An entry never admits a whole
    function: `dependency_blockers` may read its own unit's `depends_on`, but its `H.effective_edges` call still fails
    unless routed.
  - Line numbers are at `0ff0435`, unchanged at `df839fd` for every listed function.
  - A new function needs its own entry, with its reason, in review. The patterns are never weakened to admit a reader:
    it goes through the accessor, or it gets an entry here.
  - I re-ran the enumeration with an `ast` walk at `df839fd`. Every rule-1 call, every rule-2 read and every rule-3
    read with a widened work-unit source falls into this table or into the routed list below. No rule-2 read remains
    outside the routed readers; the manifest reads are excluded by receiver.

  | Function (line at `0ff0435`) | Rules and keys admitted | Reason it is structural |
  |---|---|---|
  | `hierarchy.inherited` (new) | all | the accessor itself |
  | `hierarchy.ancestors` (`hierarchy.py:85-90`) | 3: `parent` loop | the chain primitive; called only by the accessor and by entries here |
  | `hierarchy.children_map` (`:37`), `hierarchy.children` (`:44`), `hierarchy.descendants` (`:48`) | 3: `parent` | children: tree structure |
  | `hierarchy.depth` (`:95`) | 1: `ancestors` | counts, for cascade ordering |
  | `hierarchy.recompute_parents` (`:102`, `:135`) | 3: `parent` | derived parent *state* (rollup), not obligations |
  | `hierarchy.children_digest` (`:150`) | 3: `parent` | the child set's identity for parent snapshots |
  | `hierarchy._own_and_ancestor_edges` (today's `effective_edges`, `:165-170`) | 1: `ancestors`; 3: `depends_on` | private to the accessor; every other caller goes through `inherited` |
  | `dependencies.dependency_blockers` (`dependencies.py:87`) | 3: `depends_on` on its own `unit` only | the unit's own edges. Its inherited edges (`:89`) are routed |
  | `work_ops.WorkUnits.ancestor_plan_snapshot` (`work_ops.py:62`) | 1: `ancestors` | ancestor-plan binding; a move or promotion invalidates it and the Lead reconfirms |
  | `work_ops.WorkUnits.rollup` (`:237`) | 3: `parent` | children counts |
  | `work_ops.WorkCommands.work_show` (`:573`), `work_list` (`:587`, `:595`) | 3: `parent` | projections |
  | `hierarchy_ops.Hierarchy._move` (`hierarchy_ops.py:432`), `_move_archived` (`:454`), `work_move` (`:490`) | 3: `parent` | the hierarchy operation itself; carrying and the monotonic check go through the accessor |
  | `hierarchy_ops.Hierarchy.work_promote` (`:516`) | 1: `ancestors` | choosing the new unit's parent; carrying goes through the accessor |
  | `hierarchy_ops.Hierarchy.work_depend` (`:584`, `:600`) | 3: `depends_on` | edits the unit's own edges |
  | `hierarchy_ops.Hierarchy.work_tree` and its `node` (`:625-626`, `:647-648`), `tree_lines.walk` (`:670`) | 3: `parent`, `depends_on` | projection |
  | `archive_ops.Archive.finalize` (`archive_ops.py:271` alias, `:306-307`) | 3: `parent` | archival join |
  | `archive_ops.Archive._entry` (`:489`, `:496`) | 3: `depends_on`, `parent` | bundle links and the index entry |
  | `archive_ops.Archive._join` (`:529`), `_leave` (`:547`), `move_hot_subtree` (`:558`, `:562`) | 1: `ancestors` | summary propagation (archived counts) up the chain |
  | `archive_ops.Archive.move` (`:586`) | 3: `parent` | the archived move's leave |
  | `archive_ops.Archive._edge_targets` (`:616`, comprehension) | 3: `depends_on` | counts edge targets for `archived_refs` |
  | `archive_ops.Archive.archived_unit` (`:750`) | 3: `parent` | rebuilding an archived unit with moves applied |
  | `archive_ops.Archive.rehydrate` (`:765` merged copy, `:766`, `:772`) | 3: `parent` loop | rehydrating an archived chain; `carried_obligations` is archived with its unit |
  | `archive_ops.Archive.archived_child_ids` (`:797`), `archived_children` (`:819`) | 3: `parent` | archived children |
  | `archive_ops.reference_summary` (`:833`) | 3: `parent` | facts kept for edges to archived units |
  | `usage_ops._unit` (`usage_ops.py:668`) | 3: `parent` | usage totals per subtree |
  | `history_ops.HistoryCommands.history_show` (`history_ops.py:126`), `history_list` (`:169`) | 3: `parent` | display, moves applied |
  | `history.index.HistoryIndex._insert` (`index.py:202`), `children` (`:279`), `check` (`:330`) | 3: `parent` | the history index's rows and its children query (history entries, matched only if a widened source reaches them) |
  | `dashboard.projections.Projector._hot_children` (`projections.py:238-239`), `work_item` (`:288`, `:290`), `work_list` (`:320-331`), `history_item` (`:641`), `overview` (`:776`, comprehension) | 3: `parent`, `depends_on` | read projections |
  | `resume_ops.Resume.resume` (`resume_ops.py:372-373`) | 3: `parent`, `depends_on` | projection rows |

  **Routed through the accessor, never allow-listed** (§3.12a's routing table):
  - `gates.effective_class` (`gates.py:80`: rule 1, and rule 2 on `policy` and `min_descendant_class`);
  - `gates.effective_obligations` (`:92-96`: rule 1, and rule 2 on `policy`, `min_descendant_class` and
    `mandatory_gates`);
  - `gates.ancestors` (`:71-74`; removed);
  - `policy.validation.obligation` (`validation.py:69-77`: rule 2 on `policy`, `mandatory_gates` and
    `min_descendant_class`; rule 3 `parent` loop);
  - `dependencies.dependency_blockers`'s `:89` and `effective_edge_set` (`:127`);
  - `hierarchy.waits_for` (`:175`);
  - `nonmutating_ops.Inputs.consumed_inputs` (`:105`);
  - `work_ops.WorkCommands.work_reclassify` (`:424-425`: rules 1 and 2);
  - `context_ops.ContextPacks._hierarchy_context` (`:37`).

  `tests/` is not scanned: the oracle's independent walk is deliberate.
- **Y2's sites are checked, not allow-listed.** The fixture asserts that the matcher flags none of them, because none
  is a work unit and none is a `Load` of an obligation key on a non-manifest receiver:

  | Site | Why it does not match |
  |---|---|
  | `maps/structural._ancestors(...)` (`structural.py:88`, `:285`, `:291`, `:364`, `:393`) | a different callee name; filesystem path ancestors |
  | `mandatory_gates`, `min_descendant_class`, `parent`, `depends_on` keywords and parameters (`cli/work_commands.py:98-99`; `engine/api.py:1048-1059`; `work_ops.py:298-303`, `:317`, `:346`) | keywords, parameters and plain names, not `Subscript` or `.get` reads |
  | schema keys (`surface/contract.py:192`) and dictionary literals (`work_ops.py:347-348`, `:366`; `hierarchy_ops.py:552`; `history_ops.py:439`; `knowledge/manifest.py:113`; `policy/checks.py:30`) | dictionary-literal keys, not reads |
  | the record writer (`knowledge/records.py:75`, `meta["policy"] = policy`) | a `Store`, not a `Load` |
  | the manifest's policy reads (`base.py:50`, `:225`, `:256`, `:268`, `:282`; `api.py:169`; `context_ops.py:210-211`, `:248-249`; `dispatch.py:285-286`; `resume_ops.py:462`; `usage_ops.py:160`; `policy/execution.py:72`; `dashboard/reader.py:87`) | rule 2's single exception: rooted at the manifest |
  | `surface/projection.py:63` (`root / "policy"`) | a path join, not a read |

  If a later change makes one of these match, it is a matcher defect, fixed in the matcher, never by widening the
  allow-list or weakening a pattern.
- **Behaviour.** S2b.1 changes nothing. With no `carried_obligations`, every value is identical, on every project,
  enabled or dormant; the full suite is the proof. S2b.2 then writes carried obligations, and every reader sees them.
- **Before and after tests (S2b.2).** `test_promotion_preserves_every_ancestor_derived_value[ticket_in_story_to_story,
  ticket_in_story_to_epic, ticket_in_epic_to_story]` and `test_a_story_move_preserves_every_ancestor_derived_value`
  compare, for every affected Ticket, before and after:
  - `effective_class`;
  - `effective_obligations` (gates, non-waivable set, sources);
  - `validation.obligation` (mode, sources, verifier required);
  - `effective_edges` and `readiness_blockers`;
  - cycle refusal;
  - assurance triggers and Class 0 eligibility;
  - the resolved execution profile;
  - the reclassify floor;
  - the scope envelopes;
  - the holds (from S8).

  The fixture is a Ticket in a Story with `min_descendant_class: 2`, `mandatory_gates: [post_integration_verifier]`, an
  edge to an unfinished U, and a declared scope. After the promotion the Ticket still validates in verifier mode,
  routes as class 2, uses class-2 thresholds, and waits on U.
- **The oracle** recomputes every one of these values independently of the accessor: its own walk over the ancestors
  and the carried entries, written from the schema. After every walk step it checks that no affected Ticket's value
  shrinks across a move or a promotion.

### 3.13 Guards in the E4 shape

Every new blocker is a pure `query(state, work_id, args) -> Blocker | None`, registered as a dispatch guard through it,
so E4's stage availability composes it without an unmigrated input. This covers the pending overlay, the impact hold,
the plan's revision binding and the revision being current.

## 4. Decided, and readings disclosed

### 4.1 Decided (implementation-level)

Each is a choice inside an adopted design; none loosens an authority boundary.

1. **The registry is a package JSON document with a content-hash identity** (§3.3).
2. **The field table of §3.3:** body and `external_refs` fail closed into `acceptance`; `staffing` is an engine-defined
   non-material group; E6b's envelope stamp is in `gate_set`.
3. **Unknown record keys hash into `acceptance`; unknown control keys fail a meta-test.**
4. **Canonicalization is the v1 set; list order is kept; two explicit set rules, each with a collision test** (§3.4).
5. **Current digests are live; a revision's changed groups are measured against the live state before it; changes made
   outside a revision are history events** (§3.3, M10).
6. **The `dependencies` digest covers the effective edges; only own edges are revisable** (m4).
7. **Evidence records every group's digest; the class table decides which are compared; only `implementation_report`
   is attempt-scoped** (§3.5, M13).
8. **Legacy evidence is bound to r1 digests; no evidence file is rewritten** (§3.5).
9. **`unit.record` points at the current revision; r1 stays `ticket.md`** (§3.6).
10. **The marker key, with a format number that each rule-adding slice raises; the raise is in the store's commit path,
    so every transaction kind raises it** (§3.2, M3, N5).
11. **F4 is dormant on any project not explicitly enabled; S12 alone makes enabling the default** (§3.2, M11).
12. **The rationale is withheld in its own directory, created at enablement. It is written as a content-addressed
    pre-written object, so that no redo record holds it and no failed proposal blocks a later one. It is masked in
    contained runs (unconditionally for confirmers, with the Lead harness's declared session stores), and redacted from
    every projection until the initial seal** (§3.6, §3.11, M4, N1, R1, R6, R7).
13. **The confirmer's containment follows the host. Where `containment.supported()` holds, the launch is forced
    `required`; elsewhere the run carries a truthful weaker label. The engine computes and commits the capability and
    the label in the launching transaction, never reading the run directory, and a confirmation takes its label from
    that entry** (§3.11, N2, N3, R2). This applies the operator's F23 decision (A22), so it is a lead developer's
    decision under governance, not a new question.
14. **One confirmer invocation per attempt, relaunchable during pending. Unconfirmed endings bind forward. Only a
    `refused_by_confirmation` bars the identical change** (§3.7, §3.11, M5, R3).
15. **The checkpoint shows the cumulative diff and binds its digest** (§3.11, M6).
16. **A `revision` command group with a single-transaction fast path** (§3.7).
17. **`work reclassify` and `work staff` keep their own governed paths and are recorded as history events. `work
    depend` on a Ticket of an enabled project is a dependencies-only revision. It needs `--alignment` (m6), keeps its
    `dependency_change` decision, and is refused from S2a until S4a** (§3.2).
18. **Quiesce at proposal, in the commit that sets the overlay** (§3.7).
19. **The pending guard covers every progressing action, and lease grants inside `queue_ops.grant`; the commit
    recomputes, and growth refuses** (§3.7, M2).
20. **A revision is refused while the lease is held; F4 never releases a lease** (§3.8).
21. **The ordered state rule; a revision of started work releases the workspace, or carries it from S6** (§3.10, M8,
    m10).
22. **The reconfirm edge is keyed on `via: revision.commit` and lands in S4b. Plan binding problems are computed on
    digests only; a revision-caused REPLAN_REQUIRED may be reconfirmed with no digest changed** (§3.10, M7, N4).
23. **Expiry is derived at read and recorded by the next commit's finalizer; the operator's abort is the path with no
    Lead session. A Lead generation change aborts every pending attempt** (§3.7, m5, N7).
24. **Unprovable parent-scope containment is a confirmation trigger** (§3.9, m3).
25. **S4a's interim adverse predicate is a tested superset, with lineage taken as present** (§3.9, M1).
26. **Lineage is conservative: any earlier implementation content of the Ticket** (§3.9).
27. **Every invocation records its admitted revision; packs render that revision's record** (S2c).
28. **Late results of a revoked run are refused at write; earlier records stay historical** (S4b).
29. **Failing reports received but not ingested count as adverse, and their required findings are recorded at commit**
    (S5).
30. **No Lead path declares a required finding inapplicable. After E5b, a Lead `not_applicable` disposition is refused
    for an item raised under a revision whose compared groups have changed since** (S5).
31. **Carry keeps the Ticket's worktree; reactivation rechecks readiness, inputs and dispatch edges against the carried
    base** (S6, M9).
32. **The confirmer is the reviewer archetype at scope `revision`, with its card resolved from policy** (§3.11).
33. **Gate waivers lapse when acceptance, check_definition or scope changes** (§3.5).
34. **Impact holds use the dependent's plan's upstream bindings; no binding, no hold. The hold is guarded at dispatch:
    every direct dependent of a revisable Ticket is unstarted, because both edge kinds wait for DONE** (S8).
35. **A coverage obligation is discharged only by an independent parent review bound to a children digest that
    includes the child's new revision** (S8).
36. **`work replace` with a `--because` category; it uses `work.create`'s creation function, so E6b's stamp applies;
    it warns on open adverse items; parent closeout lists such replacements** (S9, m8, m9).
37. **The hierarchy rules of §3.12: interim refusals in S2a, the accessor in S2b.1, the rules in S2b.2** (R8, V1). No Ticket move after creation.
    Finished hierarchy is final. Promotion is allowed wherever the unit sits, and it and Story or Epic moves carry the
    inherited obligations they leave. Old parents re-evaluate their own closeout and coverage. Every change is
    monotonic over the inherited set. These apply the designer's ruling (§10), handoff §15 and KC §9.4, with the lead
    developer's strict reading of "before identity is established" (D1, D2, D4, R4).
38. **Until S10, a revision is refused while the Ticket has an unfinished StageIntent** (§3.8).
39. **No new normal typed tool** (§1).
40. **New guards are E4-shaped queries** (§3.13).
41. **Invariant rules are numbered at merge** (this plan calls them TR-1 to TR-14).
42. **ADR-0016 "Ticket revisions"** (its number taken at merge) holds these decisions and the readings of §4.2 (RD1 to RD4). ADR-0003,
    ADR-0004, ADR-0006, ADR-0007, ADR-0009 (the containment mask) and ADR-0011 get dated amendment sections.
43. **Dashboard: a contract version bump with additive fields; `currentness` is unchanged** (S11).
44. **Friction metrics are derived from records** (S11).
47. **The format raise is bookkeeping:** it derives no event, and one named path is excluded from SAE-07's diff, E3's
    equivalence and the store model's event fidelity (§3.2, R6).
48. **TR-14 baselines at enablement** (`hierarchy_baseline`), not the r1 record (R5).
49. **Every implicit default is the conservative value, listed and tested in §3.2a** (V3; replaces v4's item 49).
    Live digests are recorded at enablement (S2a). Legacy evidence's control-derived groups count as changed by any
    event not provably earlier by control revision (X3). A plan with no `upstream_bindings` is bound to every hold-relevant group.
50. **One accessor for every ancestor-derived value, in its own refactor slice (S2b.1), before any obligation is
    carried; a static test keeps every other reader out** (§3.12a, V1).
51. **Until S8, revisions that would need an impact hold or a coverage obligation are refused, rather than S8's
    machinery moving into S4a** (§3.8, S4a, V2): smaller, fail-closed, and opt-in projects only.
52. **Coverage obligations are the parent's own; one rule for a promoted child: re-pointed on the parent, discharged by
    its review, never dropped** (§3.12, V4).
53. **`carried_obligations` is a revision-governed input to `gate_set` and `dependencies`, read only through the
    accessor** (§3.3, V5).
54. **The withheld file is salted per proposal, not keyed per project** (§3.6, V6).
55. **The confirmer's containment is the stronger of the project's mode and the host's capability.** A capable host
    forces `required`. An incapable host runs the confirmer uncontained and truthfully labelled only under the
    operator's `allow_weaker`; under `required` it refuses (`CONFIRMER_CONTAINMENT_UNAVAILABLE`), and `aew doctor`
    names `allow_weaker` as the operator's choice. The probe runs outside the transaction and is re-validated inside it;
    a cached result may only short-circuit "capable" (decision 58) (§3.11, X1, superseding v5's V7 rule; A22, #118).
56. **The static test's structural allow-list is written out in full** (§3.12a, X2).
57. **Implicit defaults order events by control revision, treating an equal or unknown order as "later"; plan-binding
    defaults measure from the plan's own acceptance** (§3.2a, X3).
58. **The probe cache may only short-circuit "capable"; a confirmer's downgrade always rests on a fresh, in-memory
    probe by the launching command** (§3.11, Y1).
59. **The static test is an `ast` matcher; non-unit names are checked by its fixture, never allow-listed** (§3.12a,
    Y2).
60. **Obligation keys match on any non-manifest receiver; `parent` and `depends_on` match on widened work-unit sources
    (aliases, copies, comprehensions, annotated or conventionally named parameters); allow-list entries admit only named
    rules and keys** (§3.12a, Z1).
45. **The `dependencies` digest, and so the plan binding, covers the effective edges. An ancestor's `work depend` stales
    descendant plans until reconfirmed, and this is disclosed** (§3.2, N6): conservative, and the edge set is what the
    Ticket's work actually depends on.
46. **The ruling's decision record goes into the repository with S2a**, as
    `docs/design/decisions-2026-10-09-f4-ticket-reparenting.md`, ingested in the ledger and listed in `docs/README.md`.

### 4.2 Readings, disclosed (each fail-closed, recorded in ADR-0016; numbered RD1 to RD4 so that they never collide with the v3 review's R1 to R8)

- **RD1, VERIFICATION_FAILED (m1).**
  - E19-B §8 allows a revision in any non-terminal state.
  - WC §8 says that after VERIFICATION_FAILED, only the Lead's classification selects the path. E19-B extends §8 and
    does not remove that rule.
  - Reading: a revision does not commit from VERIFICATION_FAILED; the Lead classifies first (`CLASSIFY_FIRST`), as
    `work promote` already requires.
  - The alternative (commit and leave the state for classification) is equally faithful, but makes the revision
    precede the failure's attribution.
  - The prior adverse outcome still fires §6.2's trigger.
  - Tested on both routes in: Ticket verification, and `integrate.validate` in checks mode (Linux).
- **RD2, reconfirming the plan after an acceptance change (m2).**
  - D1's table lists the accepted plan as "invalidated" after a goal change. This plan lets the Lead reconfirm the same
    plan revision instead.
  - The reason is the intent of the same table: its own row keeps a check result unchanged after a goal change, which
    is possible only if the plan revision survives.
  - No authority is gained: a new plan revision would also be the Lead's own acceptance, and the acceptance change
    after evidence was already independently confirmed (§3.9 triggers 2 and 3).
  - It departs from the table's text, so it is listed for the designer's information (§11).
- **RD3, E19-B §3(2) and re-parenting (M12):** no longer a reading. The designer decided it (§10), and §3.12 applies
  the decision.
- **RD4, confirmation for presentation-only revisions at effective class 2 or more.** §4.2's first trigger is
  unconditional; §11 exempts only human review and the checkpoint debit. S11 measures the friction.

## 5. Slices

Each slice is one pull request. It is independently reviewed, and merged before any slice that depends on it starts
(AGENTS.md rule 3). Tests are named for their guarantee. Each slice also:

- updates the register's F4 notes, including its interim refusals;
- updates the implementation-status row "Ticket revisions (F4)";
- updates the ADR-0016 section it decides;
- updates the ledger status of the TRA rows it completes.

### S1. The field-group registry, canonicalization and digests

- **Covers:** TRA-04, TRA-05; M10 and m4's definitions.
- **Code:** `aew/engine/ticket_fields.py` (pure):
  - the registry loader and its identity;
  - `canonical`;
  - `live_digests(state, work_id)`, over the current record, control state, the effective obligations and the
    effective edges;
  - `changed_groups` with registry moves;
  - `material`.

  Also the registry JSON and its schema. No engine behaviour changes.
- **Tests** (`tests/unit/test_ticket_field_registry.py`, `test_ticket_digests.py`):
  - `test_every_ticket_field_is_classified` (walks both schemas and every unit in the walk fixtures);
  - `test_an_unknown_record_field_hashes_into_acceptance`;
  - `test_canonicalization_is_exactly_the_v1_set[crlf,cr,nfc,trailing_space,trailing_tab]`;
  - `test_wording_case_punctuation_blank_lines_and_interior_spaces_change_the_digest`;
  - `test_the_set_rules_collide_only_what_they_declare[class0_dedup_sort,edges_dedup_sort]` (m7);
  - `test_moving_an_acceptance_condition_into_the_title_or_notes_changes_the_acceptance_digest`;
  - `test_a_registry_move_counts_as_changed_in_both_groups` (synthetic v2);
  - `test_dependencies_in_control_state_and_inherited_edges_are_one_group` (m4);
  - `test_gate_set_follows_the_effective_obligations`;
  - `test_digests_are_platform_independent` (fixed vectors).
- **Docs:** ADR-0016 §1, and its ledger source entry.
- **Size:** medium. **Parallel with M4-E:** yes, now.

### S2a. Enablement, the format raise in the store's commit path, the interim hierarchy refusals

- **Covers:** TRA-07 (parent half: Ticket moves), TRA-21 (hierarchy half, interim), HIR-18 (move half); M3, M11, N5,
  D1, D2, R5 (baseline), R6, R8, V3.
- **The marker and enablement (§3.2):**
  - `aew init --ticket-revisions`;
  - `aew migrate --ticket-revisions`, the operator's, in one idempotent transaction. It writes:
    - the marker;
    - `hierarchy_baseline` for every hot Ticket (its parent at that moment; R5);
    - `recorded_digests` for every hot Ticket (its live digests at that moment, through S1's code; V3);
    - the `.aew/withheld/` directory (R6).

  `work create` writes `hierarchy_baseline` and `recorded_digests` afterwards, and `revision_events` recording starts
  (V3).
- **The format machinery** (§3.2):
  - the raise in `Session.commit` for every transaction kind (N5);
  - the schema `maximum`;
  - the named exclusion of `ticket_revisions.format` from diff-based checks and event derivation (R6).
- **On an enabled project:**
  - `work depend` on a Ticket is refused (`REVISION_PATH_UNAVAILABLE`, lifted by S4a);
  - `work move` of a Ticket is refused (`REPLACEMENT_PATH_UNAVAILABLE`, lifted to `REPLACEMENT_REQUIRED` by S9);
  - moving a finished unit is refused (`FINISHED_HIERARCHY_FINAL`);
  - every promotion and every Story or Epic move is refused (`HIERARCHY_RULES_PENDING`, lifted by S2b.2; §3.0 rule 1).
- **Invariant TR-14, first form:** on an enabled project, every hot Ticket's parent equals its
  `hierarchy_baseline.parent` (S2b.2 adds the promotion exception).
- **Tests** (`tests/integration/test_ticket_revision_enablement.py`, `test_migration.py`, the downgrade tests):
  - `test_a_dormant_project_writes_and_refuses_nothing_new` (every F4 key absent after the walks; M11);
  - `test_enabling_is_the_operators_and_idempotent_and_refused_in_a_lead_session`;
  - `test_a_pre_f4_engine_refuses_an_enabled_control_file`;
  - `test_an_older_f4_engine_refuses_a_newer_format` (each later format-raising slice adds its case; M3);
  - `test_the_first_commit_raises_the_format_and_nothing_else`;
  - `test_an_invocation_submitted_record_raises_the_format` (N5);
  - `test_a_format_raise_on_an_auto_run_step_opens_no_anomaly` (R6; it lands its assertion when E7 merges, and checks
    the shared diff helper's exclusion until then);
  - `test_enabling_creates_the_withheld_directory` (R6);
  - `test_tr14_baselines_at_enablement_after_an_earlier_move` (R5);
  - `test_a_ticket_never_moves_after_creation[blocked,ready,running,done_archived]`;
  - `test_finished_hierarchy_never_moves`;
  - `test_promotion_and_parent_moves_are_refused_until_the_hierarchy_rules_land`;
  - `test_enabling_records_every_hot_tickets_live_digests` (V3);
  - `test_implicit_defaults_on_a_project_enabled_at_s2a[<row>]` (each later slice adds its rows; §3.2a).
- **Docs:**
  - ADR-0016 §2 (enablement, formats, the exclusions, §3.2a's defaults);
  - ADR-0007 amendment (enabled projects: no Ticket moves after creation; finished hierarchy is final; the interim
    refusal);
  - the designer's ruling as `docs/design/decisions-2026-10-09-f4-ticket-reparenting.md`, with its ledger rows
    (decision 46);
  - the operator's guide (enabling, and what changes).
- **Size:** medium. **Format:** 1. **Parallel with M4-E:** yes; couplings in §9.2.
- **Rocky 8:** one full run on `AEW_RL8` before merge, because the slice changes `Session.commit`, the engine's single
  commit path (R8).

### S2b.1. One accessor for every ancestor-derived value (a refactor; V1)

- **Covers:** the precondition for TRA-21's hierarchy half; V1.
- **What it adds:** §3.12a.
  - `hierarchy.inherited`.
  - Every reader in §3.12a's table routed through it: `gates.effective_class`, `gates.effective_obligations`,
    `policy/validation.obligation`, `hierarchy.effective_edges` (and so readiness, `effective_edge_set`, `waits_for` and
    non-mutating dispatch inputs), `work_reclassify`'s floor, and the pack's chain.
  - The duplicate `gates.ancestors` removed.
  - The structural allow-list.
  - The static test `test_only_the_accessor_derives_inherited_obligations`.
- **Behaviour:** none. With no `carried_obligations`, every value is identical on every project. The whole suite,
  dormant and enabled, is the proof, plus `test_the_accessor_matches_the_old_readers` over the walk fixtures (the
  pre-refactor functions vendored into the test as the reference).
- **The oracle:** gains its independent recomputation of the ancestor-derived values (used by S2b.2's monotonic
  check).
- **Docs:** ADR-0016 §2b (the accessor).
- **Size:** medium. **Format:** none (no new state). **Waits for:** S1, and S2a for the scope-envelope hook. **Parallel
  with M4-E:** it touches `gates.py`, `validation.py`, `hierarchy.py`, `dependencies.py` and `work_ops.py`. It must not
  be open while E4 converts the gate-backed guards (§9.2), so it merges before E4 opens, or after E4 merges.

### S2b.2. The hierarchy rules: promotion and moves carry inherited obligations

- **Covers:** TRA-21 (hierarchy monotonicity), INV-03 (part); R4, D3 (superseded), D4, V1, V4.
- **What it adds:**
  - §3.12 in full: `carried_obligations` written by promotions and by Story or Epic moves, and read by every reader
    through S2b.1's accessor;
  - the monotonic check (`HIERARCHY_NOT_MONOTONIC` for an obligation that cannot be carried);
  - the old parent's re-evaluation, the `child_promoted_out` history event, and the closeout record's list of children
    that left;
  - TR-14's promotion exception;
  - revision-history events for re-parenting.

  It lifts `HIERARCHY_RULES_PENDING`. Until S2b.2 merges, S2a's interim refusals stand (V1: no carrying before every
  reader sees it).
- **Invariant:** TR-14 in full, and the oracle's rule that no ancestor-derived value of an affected Ticket shrinks
  across a step (§3.12a).
- **Tests:**
  - the §3.12 list;
  - §3.12a's before-and-after tests (`test_promotion_preserves_every_ancestor_derived_value[...]`,
    `test_a_story_move_preserves_every_ancestor_derived_value`);
  - AT-10 and `test_hierarchy.py:144`, run enabled and unchanged.
- **Docs:** ADR-0016 §2b; ADR-0007 amendment (promotion and moves carry inherited obligations; old parents re-evaluate,
  citing KC §9.4 and handoff §15).
- **Size:** medium. **Format:** raised. **Waits for:** S2b.1. **Parallel:** with S2c.

### S2c. Revision records, the r1 step, invocation and completion binding

- **Covers:** TRA-02, TRA-03 (records), TRA-17 (migration), TRA-22 (field), TRA-29; M10.
- **`aew migrate --ticket-revisions` gains the r1 step** (still one idempotent transaction): every hot Ticket gets its
  r1 pointer, with the `recorded_digests` written at enablement (never recomputed; V3), and every hot Ticket invocation
  gets `ticket_revision: 1`. Archived Tickets read as final revision r1.
  - On a project enabled by S2a, a Ticket without a pointer is read as implicit r1 with its enablement digests (§3.2a).
    The next `aew migrate --ticket-revisions` writes the pointer.
- **On an enabled project:**
  - `work create` writes r1 and its pointer;
  - every invocation-creating entrypoint, and the custodian, records `ticket_revision`;
  - packs render the invocation's admitted revision record;
  - completion records gain `ticket_revision: {revision, path, sha256, digests, registry}`;
  - closeout lists each child's `final_revision`;
  - archival pins revision records.
- **Schemas:**
  - control: the unit and invocation properties;
  - work-unit: additive optional fields;
  - transition: the three derived event kinds, emitted from S4a on.
- **Invariants:**
  - **TR-1:** every hot Ticket of an enabled project has a current revision, its pointer or implicit r1. Its record hash
    matches, its record's own groups match `recorded_digests` where recorded, and its predecessor chain is intact.
    Derived groups are excluded (M10).
  - **TR-2:** every Ticket invocation records a revision, and every active one, other than a custodian or a confirmer,
    records the current revision.
- **Tests** (`tests/integration/test_ticket_revision_records.py`):
  - `test_enabling_gives_every_hot_ticket_r1`;
  - `test_archived_tickets_read_as_final_revision_r1`;
  - `test_completion_and_closeout_name_the_final_revision` (oracle 33);
  - `test_every_invocation_records_its_ticket_revision`;
  - `test_reclassify_and_ancestor_edges_are_revision_history_events`.
- **Docs:** ADR-0016 §2c; ADR-0011 note.
- **Size:** medium. **Format:** raised. **Waits for:** S2a. **Parallel:** with S2b.1 and S2b.2, and with M4-E (textual couplings in
  §9.2).

### S3. Evidence binding and computed admissibility

- **Covers:** TRA-13, TRA-14, TRA-15 (mechanical), TRA-17 (rule), TRA-28 (gate rule), HIR-14, HIR-24, INV-03.
- **What is added:**
  - `ticket_inputs` on every sealed record of an enabled project (`submit`, `check_run`, engine check results, execute
    records), and added to `ENGINE_OWNED`;
  - `aew/engine/admissibility.py`;
  - the gate rule, the ingest refusal and waiver binding (§3.5);
  - `gate show` and `evidence show` print admissibility.
- **Synthetic revisions:** unit tests build r2 states with a test-only helper. The oracle cases are proven end to end in
  S6 (M13).
- **Invariant TR-3:** no gate is CURRENT on evidence whose compared digests differ from the live ones, unless an
  admissible revalidation cites it. The oracle recomputes admissibility from the files, independently of the engine.
- **Tests** (`tests/integration/test_revision_admissibility.py`; unit level):
  - `test_admissibility_follows_the_class_table[<class>-<group>]`;
  - `test_only_implementation_reports_are_attempt_scoped` (M13);
  - `test_legacy_evidence_is_bound_conservatively[record_groups_exact,control_groups_changed_by_any_later_event,same_second_event_counts_as_later,unknown_order_counts_as_later]`
    (oracle 27; V3, X3);
  - `test_a_lead_cannot_supply_ticket_inputs`;
  - `test_admissibility_is_never_written_into_a_record`;
  - `test_a_registry_move_needs_regeneration_or_a_mechanical_revalidation` (oracle 8);
  - `test_ingest_refuses_a_report_bound_to_other_ticket_inputs`;
  - `test_a_waiver_lapses_when_acceptance_changes`;
  - `test_a_reclassify_after_sealing_does_not_change_a_check_results_admissibility` (live digests, M10).
- **Docs:** ADR-0016 §3; ADR-0002 note.
- **Size:** large. **Format:** raised. **Parallel with M4-E:** yes, but not while E4 is open (§9.2). Merge before E4
  opens, or after E4 merges.

### S4a. Revisions of work not yet started

- **Covers:** TRA-01, TRA-03 (decisions), TRA-06, TRA-07 (refusals), TRA-08, TRA-09 (assertion and computation),
  TRA-11 (count), TRA-21, TRA-26 (the impact record; holds refused until S8), TRA-30, HIR-13, HIR-20; M1, m3, m6, V2.
- **The engine module:** `aew/engine/revision_ops.py`:
  - propose (with `--impact`) and the fast-path commit;
  - `list` (with events) and `show` (predecessor and cumulative diffs);
  - the attempt record; the withheld rationale as a salted, content-addressed pre-written object (N1, R1, V6), with
    its redaction in every projection and the fixed transition reason;
  - the decision, the pointer, the list, the count, the events.
- **Scope:** Tickets in BLOCKED, READY or REPLAN_REQUIRED with no active invocation. Others are refused
  (`REVISION_OF_STARTED_WORK`).
- **Requirements:** computed in full, with the interim predicate (§3.9). A revision that needs confirmation or a
  checkpoint is refused.
- **Impact and coverage, until S8 (V2, decided):**
  - The attempt and decision records are the durable revision-impact record of E19-B §7.5 from this slice on.
  - A revision that would need a hold is refused (`REVISION_NEEDS_IMPACT_HOLD`): its changed groups meet acceptance,
    check_definition or scope, and a direct explicit dependent (an own edge, or a parent dependent reaching the Ticket
    through the accessor) has an accepted plan.
  - A revision that would need a coverage obligation is refused (`REVISION_NEEDS_COVERAGE`): acceptance or
    check_definition changes on a Ticket with a parent.
  - **Why refuse rather than build early:** holds need S8's upstream bindings, guard and clearing path, and coverage
    needs S8's gate and closeout rule. Moving them into S4a would double the largest slice. The refusal is a few lines,
    fails closed, and affects only operator-enabled projects between S4a and S8.
- **Also in this slice:**
  - the refusals of §3.8;
  - plan binding to the revision, computed on digests only (§3.10, N4), and `plan reconfirm` rebinding an unstarted
    Ticket's plan (no new state edge; M7);
  - `work depend` on a Ticket as a revision, with `--alignment` required (m6);
  - broker classification of the new commands;
  - `T-0017@r2`, the count and the next action in `status`, `resume`, `work show` and the guide.
- **Invariant TR-4:** every revision after r1 has one `ticket_revision` decision and an attempt record, and no revision
  follows DONE or CANCELLED.
- **Tests** (`tests/integration/test_revision_lifecycle.py`):
  - `test_a_ready_tickets_scope_correction_is_a_new_revision_of_the_same_ticket`;
  - `test_changed_groups_are_computed_never_taken_from_the_lead` (oracle 5);
  - `test_changed_groups_ignore_an_earlier_reclassify` (M10);
  - `test_revision_refused_for_done_cancelled_or_leased[done,cancelled,archived,leased,reconcile]` (oracle 17);
  - `test_kind_or_parent_change_needs_a_replacement` (oracle 32, the refusal half);
  - `test_a_revision_cannot_lower_class_or_drop_inherited_gates` (oracle 14);
  - `test_a_title_only_revision_leaves_a_ready_tickets_plan_bound` (N4);
  - `test_a_pre_s4a_plan_is_measured_from_its_own_acceptance` (X3: a `work depend` between the plan's acceptance and
    enablement makes the binding a problem);
  - `test_an_ancestor_depend_stales_descendant_plans_until_reconfirmed` (N6);
  - `test_protected_scope_and_cycles_are_refused`;
  - `test_unprovable_parent_containment_requires_confirmation` (m3);
  - `test_the_interim_adverse_predicate_refuses_on_a_failing_check` (M1, the v1 scenario);
  - `test_a_revision_needing_an_impact_hold_is_refused_until_s8` (V2: a READY upstream with a dependent whose plan is
    accepted, and an acceptance revision);
  - `test_a_revision_needing_parent_coverage_is_refused_until_s8` (V2);
  - `test_title_fix_is_non_material_and_consumes_no_checkpoint_budget` (oracle 15);
  - `test_the_material_count_is_shown_before_commit`;
  - `test_impact_preview_equals_the_committed_impact`;
  - `test_work_depend_on_a_ticket_is_a_dependencies_revision_with_an_alignment` (oracle 30, m6);
  - `test_revision_text_is_preserved_bytewise_and_never_interpolated` (oracle 35);
  - `test_the_rationale_is_withheld_from_every_projection_and_the_transition_log[revision_show,revision_list,work_show,status,resume,history,explain,dashboard,transition_log]`
    (M4);
  - `test_no_state_file_holds_the_rationale_before_the_seal` (N1);
  - `test_revision_history_is_durable_after_archival` (oracle 34);
  - `test_a_regenerated_pack_matches_after_a_later_revision`;
  - `test_hierarchy_scenario_e_editorial_title_correction`.
- **Docs:** ADR-0016 §4 (including N6's disclosure); ADR-0007 amendment (`work depend` on a Ticket); the CLI
  reference.
- **Size:** large. **Format:** raised. **Waits for:** S3. **Parallel with M4-E:** yes; it adds no dispatch guard.

### S4b. Revisions of work in flight

- **Covers:** TRA-22, TRA-23, TRA-24, TRA-27, TRA-28 (authority); M2, M7, M8, m1, m10, N4, N7.
- **What it adds:**
  - `revision_pending` with quiesce, the guard of §3.7 (including inside `queue_ops.grant`), commit with recompute,
    abort and expiry;
  - the policy key `pending_expiry_s`, classified for E1's meta-test;
  - the ordered state rule and the `revision.commit` edges, with the workspace released (§3.10);
  - the reconfirm edge keyed on `via: revision.commit`, accepted with no digest changed (M7, N4);
  - the generation-change finalizer that aborts pending attempts (N7);
  - COMMIT_READY retirement;
  - the `CLASSIFY_FIRST` refusal;
  - cancellation, cascade and promotion aborting or refusing a pending attempt;
  - projections of the overlay.
- **Invariants:**
  - **TR-5:** while a revision is pending, no invocation of the Ticket is active except its confirmer, no dispatch
    decision for it is committed after `started_rev` except the confirmer's, and no lease is granted to its entry.
  - **TR-6:** no revision transaction changes `queue.lease`, and none commits while the entry holds a lease.
- **Tests** (`tests/integration/test_revision_started_work.py`):
  - `test_dispatch_racing_a_revision_is_quiesced_or_refused_stale[dispatch_first,revision_first]` (oracle 18);
  - `test_no_invocation_survives_its_revision` (oracle 19);
  - `test_pending_expiry_releases_no_lease_and_forces_no_commit` (oracle 20);
  - `test_a_run_that_will_not_stop_blocks_the_commit` (oracle 20);
  - `test_revision_pending_is_an_overlay_with_expiry_and_obligations` (oracle 21);
  - `test_abort_keeps_the_old_revision_and_restores_admission_only_after_runs_end` (oracle 22);
  - `test_a_late_result_of_a_revoked_run_is_refused_and_earlier_records_stay_historical` (oracle 23);
  - `test_mutations_during_pending_are_refused_or_refuse_the_commit[work_accept,transition,ingest,classify,dispose,reclassify,staff,move,promote,ancestor_move,ancestor_depend,lease_grant,publish]`
    (M2);
  - `test_every_lease_grant_goes_through_grant` (M2; a source-level conformance test);
  - `test_commit_ready_revision_retires_the_queue_entry_and_candidate`;
  - `test_a_revision_never_releases_a_lease`;
  - `test_started_work_is_replanned_reconfirmed_and_reassigned` (through the next `work assign`; M8);
  - `test_reconfirm_never_closes_a_classification_replan` (M7);
  - `test_reconfirm_closes_a_title_only_revision_replan` (N4);
  - `test_a_generation_change_aborts_pending_revisions[takeover,handoff,release]` (N7);
  - `test_a_title_fix_in_review_passed_keeps_the_state_and_one_with_a_live_run_replans` (m10);
  - `test_revision_after_a_failed_verification_needs_classification_first[ticket_verify,integrate_validate]` (m1);
  - `test_cancelling_a_ticket_aborts_its_pending_revision`.
- **Docs:** ADR-0016 §5; ADR-0003 amendment (the `revision.commit` edges, the reconfirm edge); ADR-0004 note.
- **Size:** large. **Format:** raised. **Waits for:** S4a, and M4-E's E4 and E3c. One full Rocky 8 run before merge.

### S5. Adverse findings carried forward, and the exact trigger

- **Covers:** TRA-18, TRA-19, TRA-21 (after adverse), TRA-20 (use), HIR-21.
- **`open_adverse(state, T)`:**
  - open required findings, not waived;
  - the latest failing review or verification not followed by a pass for the same gate;
  - unclassified or inconclusive verification outcomes;
  - failing latest check results;
  - post-integration failures awaiting disposition;
  - failing received reports;
  - `revision_refusals` not yet disposed;
  - E5b's undisposed items.
- **The exact trigger and lineage** replace the interim ones. `may_be_adverse` stays as a test oracle (M1).
- **At commit,** required findings of failing received reports are recorded on the unit. Nothing is removed from
  `findings`.
- **The E5b restriction** of decision 30.
- **A "carried adverse" pack section.**
- **Invariant TR-7** (a store-model pair rule): an open required finding never disappears across a revision commit
  except by a later review, a waiver, or an independent record that cites it.
- **Tests** (`tests/integration/test_revision_adverse.py`):
  - `test_open_findings_survive_a_revision` (oracle 9);
  - `test_inadmissible_failing_evidence_still_counts_as_adverse[HISTORICAL,INVALIDATED,SUPERSEDED]` (oracle 10, m7);
  - `test_a_revision_that_changes_the_criterion_cannot_dismiss_its_finding` (oracle 11);
  - `test_blocked_alone_never_triggers_anti_laundering` (oracle 29);
  - `test_adverse_outcomes_trigger_confirmation[REVIEW_FAILED,VERIFICATION_FAILED,VERIFICATION_INCONCLUSIVE,open_finding,received_failing_report,failing_check]`
    (oracle 29);
  - `test_lineage_survives_a_fresh_workspace` (oracle 28);
  - `test_the_interim_predicate_is_a_superset_of_open_adverse` (M1);
  - `test_a_failing_review_received_before_the_revision_keeps_its_findings`;
  - `test_class_reduction_after_adverse_evidence_is_refused`;
  - `test_a_review_pass_never_stops_verification_from_finding_a_goal_defect_after_revision` (HIR-21).
- **Docs:** ADR-0016 §6.
- **Size:** medium. **Format:** raised. **Waits for:** S4b and M4-E's E5b.

### S6. The workspace carried forward as input only, and the oracle cases end to end

- **Covers:** TRA-16, TRA-06, D3; oracles 1, 2, 3; M9, M13.
- **Carry:**
  - `--workspace carry` (the default) marks the worktree `carried`, with its fingerprint and the revision.
  - **Reactivation at `work assign`** (M9):
    - it requires the fingerprint unchanged (`WORKSPACE_MUTATED`);
    - it rechecks readiness and `inputs.current` against the carried worktree's own `base_commit`, not the current
      authoritative commit;
    - it refuses `CARRIED_BASE_STALE` (naming `--workspace fresh`) when a `mutating` dependency's integrated commit is
      not an ancestor of that base;
    - it records the new `ws["dependencies"]` and `carried_from: {revision, fingerprint}`.
  - `plan accept` from a revision-caused REPLAN_REQUIRED keeps a carried worktree.
  - The pack's continuation section is the handover.
- **Invariant TR-8:** a carried worktree has no active invocation, and its fingerprint is the recorded one until it is
  reactivated.
- **Tests** (`tests/integration/test_revision_carry_forward.py`, `tests/acceptance/test_at_ticket_revisions.py`):
  - `test_a_scope_correction_keeps_the_ticket_and_its_workspace_work` (oracle 1, the M3 dogfood §6.6 case);
  - `test_e2e_prior_implementation_proof_never_satisfies_a_revised_ticket` (oracle 2, M13). The real path: propose,
    quiesce, commit, REPLAN_REQUIRED, reconfirm, carry, reactivate. After an acceptance revision, the implementation
    report is HISTORICAL and the review INVALIDATED, and the gates are not CURRENT;
  - `test_e2e_unrelated_current_evidence_survives_a_revision[title_only,scope_only]` (oracle 3, M13, N4). The same
    path, through `work assign`:
    - in the title-only leg, `plan reconfirm` closes the revision-caused REPLAN_REQUIRED with no digest changed;
    - in the scope-only leg, it rebinds the changed scope digest;
    - in both, the plan revision is kept, the carried worktree's fingerprint is unchanged, and the project check
      result stays CURRENT;
  - `test_carry_is_refused_when_its_base_lacks_a_new_dependency` (M9);
  - `test_carried_work_is_input_never_proof`;
  - `test_a_mutated_carried_workspace_is_refused_at_reassignment`;
  - `test_fresh_releases_as_before`.
- **Docs:** ADR-0016 §7; ADR-0003 note (M2's "start fresh" rule amended).
- **Size:** medium. **Format:** raised. **Waits for:** S4b.

### S7. Independent confirmation and the operator's checkpoint

- **Covers:** TRA-09 (paths), TRA-10, TRA-11 (checkpoint), TRA-15 (independent), TRA-19 (routing), HIR-16, PAD-05
  (hook); M4, M5, M6, m5, N2, N3, R2, R3, R7, V7.
- **What it adds (§3.11):**
  - the entrypoint, the card rule, the one-confirmer rule (relaunchable during pending, R3), and §3.11's containment
    table: forced `required` on a capable host; uncontained and truthfully labelled on an incapable host under
    `allow_weaker`; `CONFIRMER_CONTAINMENT_UNAVAILABLE` on an incapable host under `required` (X1);
  - the host-probe cache, which may only short-circuit "capable"; a downgrade always comes from a fresh probe by the
    launching command, passed in memory and recorded on the label (X1, Y1);
  - `aew doctor`'s confirmer row for each case (X1);
  - the capability and the label computed and committed by the engine in the launching transaction (R2);
  - the engine-material pack;
  - the `.aew/withheld/` mask in the containment layout, for every run, and unconditionally for confirmers (R6);
  - the Lead harness's declared session-store paths masked in confirmer layouts, and `aew doctor`'s warning (R7);
  - the bridge operation `revision.rationale`;
  - the two-phase `revision_confirmation` kind;
  - binding forward through `revision_refusals`, and the same-change refusal;
  - `aew revision checkpoint`, with the diffs shown and bound;
  - `revalidates`;
  - the title flag;
  - the policy keys `checkpoint_after` and `confirmation_cards`, legality-classified.
- **Invariants:**
  - **TR-9:** every committed revision that required confirmation cites a positive final record from a non-Lead
    invocation of the policy card. Its initial record was sealed before the rationale was released. Its run has an
    engine-committed launch entry, and the label recorded on the confirmation and the revision decision is that
    entry's (R2).
  - **TR-10:** every committed material revision beyond the threshold cites a checkpoint whose shown-digest matches the
    attempt's cumulative diff.
- **Tests** (`tests/integration/test_revision_confirmation.py`; Linux lanes for containment; harness conformance):
  - `test_confirmer_is_not_the_lead_and_sees_material_before_rationale` (oracle 12);
  - `test_a_contained_confirmer_cannot_read_the_withheld_rationale` (M4; a real bwrap run reads the masked path and
    finds it empty);
  - `test_the_rationale_is_released_only_after_the_initial_determination`;
  - `test_a_confirmers_launch_is_forced_contained_where_the_host_can_contain` (N2; under an `allow_weaker` policy);
  - `test_a_confirmer_that_rewrites_its_run_record_is_still_labelled_by_the_engine` (R2; on an uncontained host the
    confirmer writes `filesystem: contained` into its run record, and the confirmation is still labelled weaker);
  - `test_a_confirmation_without_an_engine_launch_entry_is_refused` (R2);
  - `test_a_capable_host_always_contains_the_confirmer[required,allow_weaker]` (X1);
  - `test_an_incapable_host_runs_a_labelled_uncontained_confirmer_under_allow_weaker` (V7, X1; on `AEW_RL8` with the
    slirp4netns failure, or a fixture that makes the probe fail);
  - `test_a_required_project_refuses_an_uncontained_confirmer` (X1);
  - `test_doctor_names_allow_weaker_as_the_operators_choice` (X1);
  - `test_the_probe_never_runs_inside_the_lead_transaction` and `test_a_stale_probe_key_refuses_and_reprobes` (X1);
  - `test_a_forged_not_capable_cache_never_downgrades_a_confirmer`,
    `test_a_repaired_host_contains_the_next_confirmer_despite_a_stale_not_capable_cache` and
    `test_a_downgrade_label_records_the_in_memory_probe_and_its_time` (Y1);
  - `test_a_crashed_confirmer_is_relaunched_during_pending` (R3);
  - `test_the_same_change_is_proposable_after_an_abandoned_confirmation[lost,generation_change]` (R3);
  - `test_confirmer_layouts_mask_the_withheld_directory_even_if_created_late` (R6);
  - `test_confirmer_layouts_mask_the_lead_harness_session_store` and `test_doctor_warns_on_an_unmasked_lead_store`
    (R7);
  - `test_an_uncontained_host_runs_a_labelled_confirmer_and_still_withholds_the_rationale` (N3: every engine read
    path and the bridge, on Windows and on a Linux host where `containment.supported()` is false; the label is shown in `status`, `explain`
    and closeout);
  - the redo-record and `state/` paths added to the contained-confirmer test (N1);
  - `test_a_card_other_than_the_policy_card_is_refused` (m5);
  - `test_abort_or_expiry_ends_the_confirmer` (m5);
  - `test_abort_after_a_negative_initial_is_a_refusal_and_binds_forward` (M5);
  - `test_cancelling_the_confirmer_ends_the_confirmation_path` (M5);
  - `test_an_identical_change_after_a_refusal_is_refused` (M5);
  - `test_a_different_change_after_a_refusal_needs_confirmation_and_shows_the_refusal` (M5);
  - `test_class_2_confirmation_pack_carries_the_cumulative_diff` (oracle 13);
  - `test_drift_is_measured_against_r1_or_the_checkpoint_and_the_parent` (oracle 26);
  - `test_confirmation_threshold_uses_the_effective_class` (oracle 31);
  - `test_fourth_material_revision_needs_the_operators_checkpoint` (oracle 15);
  - `test_operator_policy_sets_the_threshold_and_a_lead_cannot_loosen_it` (oracle 15);
  - `test_the_checkpoint_shows_the_cumulative_diff_and_binds_it` (M6);
  - `test_a_checkpoint_waives_no_evidence_finding_or_gate` (M6);
  - `test_a_non_overlapping_objective_is_refused_by_confirmation` (oracle 32, third leg; m7);
  - `test_an_independent_revalidation_makes_revalidate_evidence_admissible`;
  - `test_a_lead_note_never_makes_evidence_current`;
  - `test_a_flagged_title_becomes_acceptance_bearing_until_confirmed_removed`;
  - `test_hierarchy_scenario_a_malformed_goal_after_review`.
- **Docs:** ADR-0016 §8; ADR-0006 amendment (the confirmer card and scope); ADR-0009 amendment (the withheld mask);
  ADR-0005 note (the checkpoint's class); the harness contract (the bridge operation).
- **Size:** large. **Format:** raised. **Waits for:** S5.

### S8. The impact hold on direct dependents, and parent coverage

- **Covers:** TRA-12, TRA-26; V2, V3, V4.
- **Lifts S4a's two interim refusals** (`REVISION_NEEDS_IMPACT_HOLD`, `REVISION_NEEDS_COVERAGE`; V2).
- **The impact hold:**
  - Plans record `upstream_bindings` at accept and reconfirm. A plan accepted before S8 has none, and counts as bound
    to every hold-relevant group (acceptance, check_definition, scope) of each upstream (§3.2a; V3).
  - The hold guard reads holds through §3.12a's accessor, so a hold on a parent dependent reaches its descendants,
    carried ones included.
  - A committed revision whose changed groups meet a direct explicit dependent's bound groups creates a hold on it.
    For a parent dependent, the hold blocks its descendants' dispatch.
  - The hold records the upstream Ticket and revision, the changed groups, the binding, its time and its obligation.
  - It clears by the dependent's reconfirm or a new plan, or by mechanical proof. It never fans out.
  - A `revision.impact_hold` query guard enforces it.
- **Parent coverage:**
  - An acceptance or check_definition change opens a `coverage_obligations` entry on the parent, which adds a
    `coverage_review` gate.
  - Closeout refuses while one is open.
  - The closeout record lists the children revised materially after the parent's plan acceptance.
- **The monotonic set gains one row (§3.12):** impact holds reaching through an ancestor, carried by promotions and
  moves. Coverage obligations are the parent's own and outside the set; an open one naming a promoted Ticket follows
  §3.12's one rule: it stays on that parent, re-pointed, until that parent's review discharges it (V4).
- **Invariants:**
  - **TR-11:** a held unit has no dispatch decision after its hold, and every hold names a real own edge.
  - **Also TR-11:** every direct dependent of a non-DONE Ticket is unstarted (the reason a dispatch guard suffices).
  - **TR-12:** no closed parent has an open coverage obligation.
- **Tests** (`tests/integration/test_revision_impact.py`):
  - `test_a_direct_dependent_is_held_without_recursive_fanout` (oracle 25);
  - `test_an_unaffected_dependent_is_not_held`;
  - `test_a_hold_blocks_dispatch_but_leaves_the_state_and_live_runs`;
  - `test_reconfirming_the_dependent_clears_the_hold_and_makes_nothing_current`;
  - `test_acceptance_change_opens_a_parent_coverage_obligation` (oracle 16);
  - `test_closeout_waits_for_a_review_bound_to_the_childs_final_revision`;
  - `test_a_promotion_carries_an_impact_hold` (D4);
  - `test_a_coverage_obligation_naming_a_promoted_child_is_re_pointed_and_discharged_by_review` (V4);
  - `test_a_plan_accepted_before_s8_is_held_by_any_upstream_change` (V3).
- **Docs:** ADR-0016 §9; ADR-0007 amendment.
- **Size:** medium. **Format:** raised. **Waits for:** S4a, and S2b.2 (holds are carried).

### S9. Replacement and supersession lineage

- **Covers:** TRA-07, HIR-17, HIR-18, INV-03; m8, m9, D2 (lifting the interim).
- **`aew work replace`:**
  - it creates T' through `work.create`'s creation function (so E6b's envelope stamp applies when present), with
    `supersedes`;
  - it cancels a non-terminal T with `superseded_by` (refused under a lease), or annotates an archived T;
  - `kind` and `parent` categories are checked mechanically;
  - it records a `supersession` decision;
  - it warns when T has open adverse items.
- **T's evidence never satisfies T''s gates.** T''s packs carry T's open adverse items as labelled reference context.
- **The interim lifted:** a Ticket move's refusal becomes `REPLACEMENT_REQUIRED`, naming `aew work replace <T>
  --because parent`. The refusal itself has stood since S2a (§3.12).
- **Parent closeout** requires every superseded child's replacement to be terminal or under the same parent
  (HIER-005). The closeout record lists each replacement, and flags replacements made while their subject had open
  adverse items (m9).
- **Invariant TR-13:** every Ticket cancelled as superseded names a replacement that names it back, and no parent
  closes with an undisposed superseded descendant.
- **Tests** (`tests/integration/test_ticket_replacement.py`):
  - `test_replacement_is_required_for_kind_parent_or_a_new_objective` (oracle 32);
  - `test_replacement_keeps_supersession_lineage_both_ways`;
  - `test_a_superseded_tickets_evidence_never_satisfies_the_replacement`;
  - `test_a_ticket_move_names_work_replace_once_it_exists` (D2);
  - `test_replacement_under_a_new_parent_keeps_lineage_and_leaves_the_old_ticket_cancelled`;
  - `test_closeout_requires_every_superseded_descendant_disposed`;
  - `test_closeout_lists_replacements_made_over_open_adverse_items` (m9).
- **Docs:** ADR-0016 §10; ADR-0007 amendment.
- **Size:** medium. **Format:** raised. **Waits for:** S4a.

### S10. StageIntent binding to the Ticket revision

- **Covers:** TRA-25.
- **What it adds:**
  - `unit_state` binds `ticket_revision`;
  - a step on a Ticket subject whose revision changed stops with `ticket_revised` (non-runnable, computed);
  - `resume` lists such intents as unsafe to continue;
  - E3c's explicit `continue` rebinds after the rechecks of E19-B §7.4 and records the rebind;
  - `STAGE_IN_FLIGHT` is removed.
- **Invariant:** extends E3's rules: no step commits on a Ticket subject at another revision than its intent's,
  unless a rebind is recorded.
- **Tests:**
  - `test_an_open_stage_is_not_runnable_across_a_revision_until_continued` (oracle 24);
  - `test_continue_rechecks_and_records_the_rebind`;
  - `test_abandon_after_a_revision_undoes_nothing`.
- **Size:** small to medium. **Format:** raised. **Waits for:** S4b and E3c. It is not open beside E3c, E4 or E5a.

### S11. Projections, the dashboard contract and the acceptance suite

- **Covers:** TRA-31, TRA-32, VGX-21.
- **What it adds:**
  - in `aew.dashboard` only: contract 0.2.0, adding `ticket_revision`, `overlays[]` and evidence `admissibility`
    (`currentness` is unchanged), plus the attention reasons. A note goes to the web developer;
  - the notifier event if E7 has merged;
  - `aew revision list --stats`;
  - the acceptance suite completed;
  - a test that §7 names an existing test for each of the 35 cases;
  - `test_revision_hot_state_is_bounded`.
- **Size:** medium. **Waits for:** S7, S8, S9 and S10, and after E5b.

### S12. On by default

- **What it changes:** `aew init` and `aew migrate` enable F4 by default. `--no-ticket-revisions` keeps a project
  dormant; on `migrate`, enabling remains the operator's.
- **Existing tests:** the existing suite runs enabled from here on. Each test whose expectation changes is listed in
  the PR with the governing clause. None is edited silently. Expected cases:
  - `work depend` on a Ticket (E19-B §2.3);
  - every Ticket move (the ruling, §10), for example in `test_hierarchy_walk.py` and `test_m2_compositions.py`;
  - descendants' plans staled by an ancestor's `work depend` (N6).

  Promotion is not narrowed (KC §9.4, handoff §15). AT-10 and `test_hierarchy.py:144` (a Ticket promoted out of its
  Story) must pass unchanged, and a test that either changed would be a release blocker for S12.
- **Closeout:**
  - the implementation-status row becomes "Implemented";
  - every TRA row's ledger status becomes `done:`;
  - register F4 moves to §9.
- **Size:** small to medium. **Waits for:** S11, and the M4-H rule of §9.3.

## 6. Requirement map

| Ledger id | Slice(s) |
|---|---|
| TRA-01 | S4a, S5, S6 |
| TRA-02 | S2c |
| TRA-03 | S2c (records), S4a (decisions) |
| TRA-04 | S1; S7 (title flag) |
| TRA-05 | S1; S4a (ingress corpus) |
| TRA-06 | S4a, S4b, S6 |
| TRA-07 | S2a (parent: the ruling), S4a (kind refusal), S9 (replacement) |
| TRA-08 | S4a, S4b |
| TRA-09 | S4a (assertion, interim predicate), S5 (exact trigger), S7 (path) |
| TRA-10 | S7 |
| TRA-11 | S4a (count, surfacing), S7 (checkpoint shows and binds the cumulative diff; waives nothing: M6) |
| TRA-12 | S8 (F5 keeps structured mappings) |
| TRA-13, TRA-14 | S3 |
| TRA-15 | S3 (mechanical), S7 (independent) |
| TRA-16 | S6 |
| TRA-17 | S2c, S3 |
| TRA-18 | S5 |
| TRA-19 | S4a (interim superset), S5, S7 |
| TRA-20 | done; S7 records suspected classes |
| TRA-21 | S2a, S2b.1 and S2b.2 (hierarchy monotonicity, §3.12, §3.12a), S4a, S5; S8 extends the set |
| TRA-22 | S2c, S4b |
| TRA-23, TRA-24 | S4b |
| TRA-25 | S10 (S4a's interim refusal before) |
| TRA-26 | S8 |
| TRA-27 | S4a, S4b, S6 |
| TRA-28 | S3, S4a, S4b, S5, S7, S8; TR-1 to TR-14 |
| TRA-29 | S2c, S4a, S8, S9, S11 |
| TRA-30 | S4a, S4b, S9 |
| TRA-31 | §7; S11 |
| TRA-32 | S2a, S2c, S3, S7, S11 |
| TRA-33 | done |
| HIR-04, HIR-14 | S3 |
| HIR-05, HIR-06, HIR-15, HIR-16 | S1 and S3 (editorial changes are digest equality), S7 (clarification is independent revalidation); F5 keeps the parent half |
| HIR-07, HIR-17 | S4a, S9 |
| HIR-13, HIR-20 | S4a |
| HIR-18 | S9 |
| HIR-19 | done; S4a re-asserts it |
| HIR-21 | S5 |
| HIR-24 | S3, S9 |
| PAD-05, PAV-43 | S4a (the hook); F14 |
| INV-03 | S3, S5, S9 |
| VGX-21 | S11 |
| SAI-15, SAI-17 | done |

## 7. E19-B §12 oracle cases, by test

| # | Slice | Test |
|---|---|---|
| 1 | S6 | `test_a_scope_correction_keeps_the_ticket_and_its_workspace_work` |
| 2 | S6 | `test_e2e_prior_implementation_proof_never_satisfies_a_revised_ticket` (S3's unit test stays beside it) |
| 3 | S6 | `test_e2e_unrelated_current_evidence_survives_a_revision[title_only,scope_only]` |
| 4 | S1 | `test_every_ticket_field_is_classified`, `test_an_unknown_record_field_hashes_into_acceptance` |
| 5 | S4a | `test_changed_groups_are_computed_never_taken_from_the_lead` |
| 6 | S1 | `test_canonicalization_is_exactly_the_v1_set[...]`, `test_wording_case_punctuation_blank_lines_and_interior_spaces_change_the_digest`, `test_the_set_rules_collide_only_what_they_declare[...]` |
| 7 | S1 | `test_moving_an_acceptance_condition_into_the_title_or_notes_changes_the_acceptance_digest` |
| 8 | S1, S3 | `test_a_registry_move_counts_as_changed_in_both_groups`, `test_a_registry_move_needs_regeneration_or_a_mechanical_revalidation` |
| 9 | S5 | `test_open_findings_survive_a_revision` |
| 10 | S5 | `test_inadmissible_failing_evidence_still_counts_as_adverse[HISTORICAL,INVALIDATED,SUPERSEDED]` |
| 11 | S5 | `test_a_revision_that_changes_the_criterion_cannot_dismiss_its_finding` |
| 12 | S7 | `test_confirmer_is_not_the_lead_and_sees_material_before_rationale`, `test_a_contained_confirmer_cannot_read_the_withheld_rationale` |
| 13 | S7 | `test_class_2_confirmation_pack_carries_the_cumulative_diff` |
| 14 | S4a | `test_a_revision_cannot_lower_class_or_drop_inherited_gates` |
| 15 | S4a, S7 | `test_title_fix_is_non_material_and_consumes_no_checkpoint_budget`, `test_fourth_material_revision_needs_the_operators_checkpoint`, `test_operator_policy_sets_the_threshold_and_a_lead_cannot_loosen_it`, `test_the_checkpoint_shows_the_cumulative_diff_and_binds_it`, `test_a_checkpoint_waives_no_evidence_finding_or_gate` |
| 16 | S8 | `test_acceptance_change_opens_a_parent_coverage_obligation` |
| 17 | S4a | `test_revision_refused_for_done_cancelled_or_leased[...]` |
| 18 | S4b | `test_dispatch_racing_a_revision_is_quiesced_or_refused_stale[...]` |
| 19 | S4b | `test_no_invocation_survives_its_revision`; TR-2, TR-5 |
| 20 | S4b | `test_pending_expiry_releases_no_lease_and_forces_no_commit`, `test_a_run_that_will_not_stop_blocks_the_commit` |
| 21 | S4b | `test_revision_pending_is_an_overlay_with_expiry_and_obligations` |
| 22 | S4b | `test_abort_keeps_the_old_revision_and_restores_admission_only_after_runs_end` |
| 23 | S4b | `test_a_late_result_of_a_revoked_run_is_refused_and_earlier_records_stay_historical` |
| 24 | S10 | `test_an_open_stage_is_not_runnable_across_a_revision_until_continued` |
| 25 | S8 | `test_a_direct_dependent_is_held_without_recursive_fanout` |
| 26 | S7 | `test_drift_is_measured_against_r1_or_the_checkpoint_and_the_parent` |
| 27 | S3 | `test_legacy_evidence_is_bound_conservatively[...]` |
| 28 | S5 | `test_lineage_survives_a_fresh_workspace` |
| 29 | S5 | `test_blocked_alone_never_triggers_anti_laundering`, `test_adverse_outcomes_trigger_confirmation[...]` |
| 30 | S1, S4a | `test_dependencies_in_control_state_and_inherited_edges_are_one_group`, `test_work_depend_on_a_ticket_is_a_dependencies_revision_with_an_alignment` |
| 31 | S7 | `test_confirmation_threshold_uses_the_effective_class` |
| 32 | S4a, S9, S7 | `test_kind_or_parent_change_needs_a_replacement`, `test_replacement_is_required_for_kind_parent_or_a_new_objective`, `test_a_non_overlapping_objective_is_refused_by_confirmation` |
| 33 | S2c | `test_completion_and_closeout_name_the_final_revision` |
| 34 | S4a | `test_revision_history_is_durable_after_archival` |
| 35 | S4a | `test_revision_text_is_preserved_bytewise_and_never_interpolated` |

**Test lanes:** integration and acceptance markers. Containment and the masked rationale run on Linux lanes
(`platform-skips.yaml`). The confirmer runs on the fake harness, plus one OpenCode conformance case for the bridge
operation (pinned fixture). Each slice is checked against CI's cost record (E43).

## 8. Gates (test-enforced)

- A dormant project writes and refuses nothing new (S2a onward; the existing suite runs dormant until S12).
- An older engine refuses a newer project: pre-F4 engines through the marker; older F4 engines through `format`. Each
  format-raising slice adds a case.
- No revision can be proposed before admissibility exists: S4a does not merge before S3.
- No interim is weaker than the final rule (§3.0). S5 tests the superset property of S4a's predicate. Each interim
  refusal is listed in the register.
- No revision commits while a requirement is missing, or after its requirements grew (TR-9, TR-10, and the
  recompute).
- No ancestor-derived value is read outside `hierarchy.inherited` (S2b.1's static test), and no promotion or move
  changes any of them (S2b.2's before-and-after tests and the oracle).
- Every implicit default is the conservative value (§3.2a, tested per row).
- No revision commits that would need an impact hold or a coverage obligation before S8 can create one (S4a's
  refusals).
- No unclassified Ticket field (the S1 meta-test). Every M4-E slice that adds a unit key classifies it.
- No revision transaction touches a lease, and no lease is granted during a pending revision (TR-5, TR-6).
- No active invocation for a non-current revision (TR-2, TR-5).
- The rationale is unreadable by a confirmer before its initial seal (S7, on Linux, with real containment).
- Every §12 case names an existing test (S11).

## 9. Sequencing and parallelism

### 9.1 The order

```
S1 -> S2a -> S2b.1 -> S2b.2
          \-> S2c -> S3 -> S4a -> S4b -> S6
                             |       \--> S5 (+E5b) -> S7
                             |       \--> S10 (+E3c)
                             \--> S8, S9 (each also after S2b.2)
S7, S8, S9, S10 -> S11 (+E5b) -> S12 (+ the M4-H rule)
```

- **Can start now, beside E3b, E3c and #143:** S1, then S2a (with its Rocky run), then S2b.1 and S2c in parallel, then S2b.2 and S3, aiming to merge S2b.1 and
  S3 before E4 opens (both touch the gate functions E4 wraps; §9.2); otherwise they wait for E4 to merge. Then
  S3. Aim to merge S3 before E4 opens; otherwise S3
  waits for E4 to merge.
- **Waits on M4-E:**
  - S4b waits for E4 and E3c;
  - S5 waits for E5b;
  - S10 waits for E3c, and is not open beside E3c, E4 or E5a;
  - S11 waits for E5b, and for E7 for the notifier event.
- **Independent once S4a merges:** S8 and S9. S6 is independent once S4b merges.
- **Sizes:** S1 medium; S2a medium; S2b.1 medium; S2b.2 medium; S2c medium; S3 large; S4a large; S4b large; S5 medium; S6 medium; S7 large; S8 medium; S9
  medium; S10 small to medium; S11 medium; S12 small to medium. Sixteen pull requests.

### 9.2 Couplings with M4-E and the other open work, named (m8)

| Coupling | What it means | Who does what |
|---|---|---|
| **S1's meta-test and every unit key an M4-E slice adds** | Once S1 merges, an E-slice that adds a unit key fails the meta-test until it classifies the key. Known keys: E5b's disposition index and anomaly references (bookkeeping); E6b's `authorization_envelope` stamp (`gate_set`, §3.3) | The E-slice adds the registry line in its own PR. S1's PR documents how (one line, with a review note for authority-relevant keys) |
| **E6b's envelope stamp and `work replace` (S9)** | The stamp is applied at `work.create`. Replacement creates Tickets | S9 calls `work.create`'s creation function. If E6b merges after S9, E6b stamps inside that function, which ADR-0016 names |
| **E6b's PIC request and the revision** | M4-E §2.2 expects F4 to rebind the request to the Ticket revision | Nothing to wait for. A revision at COMMIT_READY retires the queue entry and the request with it (S4b), and `record_sha256`, which the request's subject binding uses, follows the current revision. ADR-0016 states this so E6b's author does not wait for F4 |
| **E6a's `VALIDATED` entries and re-lease** | A new lease path, and a kept candidate | Covered by the pending check inside `queue_ops.grant` and by `sync`'s retirement (S4b). S4b's tests include `VALIDATED` once E6a has merged |
| **E6b's custody publication** | A publication path without a Lead turn | It needs a lease (`grant`), and the publish function checks the overlay (S4b) |
| **E4 and S2b.1's accessor** | S2b.1 routes `gates.effective_class`, `effective_obligations`, `validation.obligation` and `effective_edges` through one accessor; E4 wraps gate-backed guards as queries | S2b.1 is a pure refactor. It merges before E4 opens, or after E4 merges, as S3 does |
| **E4's guard substrate** | F4's new blockers must be queries | §3.13; S4b waits for E4 |
| **E3c's `continue` and `abandon`** | S4b's interim refusal names `abandon`; S10 rebinds through `continue` | S4b and S10 wait for E3c |
| **E5b's dispositions and anomalies** | They are part of `may_be_adverse` and `open_adverse`, and are restricted by decision 30 | S5 waits for E5b; S4a counts them if E5b has merged |
| **E5a's `ticket_start` stage** | It wraps `work assign` | S6's reactivation is inside `work assign`, so the stage inherits it |
| **E5a's `ticket_draft` stage and the ruling's construction phase** | `ticket_draft` runs `work.create` as its first step, so identity exists before any later step | A parent is chosen at `work.create`. If E5a adds a construction step before `work.create`, the parent may be corrected there (§3.12). F4 needs nothing from E5a |
| **E7's confirmation records and notifier** | Confirmations bind the subject record digest, which follows the revision. The notifier table gains an event | Nothing to wait for; S11 adds the event if E7 has merged |
| **E1's policy classification** | The new `gates.ticket_revision` keys | Classified in S4b and S7 |
| **E7's runtime declaration check (SAE-07) and E3's stage/primitive equivalence (R6)** | The format raise adds a control-state change to whatever transaction first commits after an engine upgrade, which an auto-run step or an equivalence comparison would otherwise see as an undeclared effect | S2a adds `ticket_revisions.format` as one named exclusion in the shared diff helper. E3's equivalence comparisons and E7's SAE-07 comparison use that helper, beside the journal's own records. If E7 is built before S2a merges, S2a adds the exclusion there; if after, E7 inherits it. The store model's event-fidelity rule excludes it too |
| **E8's relaunch and the confirmer** | A pre-work relaunch is a relaunch | The confirmer's relaunch is exempt from the pending guard (R3), and each relaunch commits its own engine label (R2) |
| **E6b and E7's operator lists in the broker** | S7 adds `revision checkpoint` | Textual only |
| **#143 (F22.1 PR B, the structural map in packs)** | S2c changes which record a pack renders | Textual only; whoever merges second rebases |
| **#145 (merged as `0ff0435`: the knowledge system adopted; the designer's 2026-10-09 reviewer-independence ruling; F9-A1 as a proposal)** | The ruling defines independence as fresh, bounded context with the implementer's reasoning excluded, and lets a reviewer see a Ticket's unresolved records. The confirmer is consistent with it: a fresh context, engine material, no Lead reasoning before the seal. When F21 builds worker lookup tools, any lookup that reaches Ticket records must apply §3.6's redaction of the withheld rationale. The containment mask already covers file access. F9-A1 defers to "normal Ticket revision rules" and changes nothing here | S7 restates the redaction rule for lookup tools in ADR-0016; F21's slices inherit it |

### 9.3 M4-H (M11)

- Q7 v0.3.1 measures "AEW at one frozen M4 commit" with shipped defaults (§2.2). It anticipates F4: §2.4.3 lists "an
  operator/stakeholder Ticket-revision checkpoint" among operator-only decisions that end an unattended run, and §6.4
  lists revision friction.
- **The guarantee.** Until S12, F4 is dormant on every project not explicitly enabled, and a dormant project behaves
  exactly as before (§3.0 rule 2, proven by the existing suite). So a freeze commit containing any of S1 to S11 leaves
  the M4-H treatment unaffected, because its task projects are created with the shipped default.
- **S12 is the one product change M4-H would see.** Whether the freeze commit includes it is the operator's
  freeze-time choice (Q7 §14.1 item 2). If S12 is not merged by then, it waits until the counted runs end.
- **No F4 merge lands between the pre-calibration freeze (Q7 §7) and the end of the counted runs.** A product change
  in that window forces a re-freeze and discards calibration (Q7 §7).

## 10. Decided: the designer's ruling on re-parenting (2026-10-09)

v2 asked the designer one question: whether E19-B §3(2) also forbids ADR-0007's in-place `work move` of a Ticket, or
only forbids a revision from changing the parent. The operator relayed the answer on 2026-10-09. It is recorded here
verbatim, and goes into the repository with S2a as `docs/design/decisions-2026-10-09-f4-ticket-reparenting.md`,
ingested in the ledger (decision 46).

**The ruling, verbatim:**

> CONFIRMED WITH CLARIFICATION. E19-B §3(2) prohibits changing a committed Ticket's parent through ordinary Ticket
> revision. A move from one existing parent to another requires replacement under the new parent with explicit
> lineage; this applies whether or not execution has begun. An uncommitted/draft Ticket may still have its parent
> corrected before identity is established. KC §9.4 promotion is a distinct hierarchy-expansion operation and remains
> allowed after work has started. Promotion preserves the original Ticket identity/evidence and introduces the larger
> enclosing Story/Epic rather than rewriting the Ticket into a different work unit or treating promotion as arbitrary
> re-parenting. In all cases, hierarchy changes must be monotonic with respect to inherited obligations: no change may
> lower effective class, drop a non-waivable ancestor gate/guardrail, or otherwise use hierarchy movement to escape
> prior obligations.

**The reasoning, verbatim:**

> I would not limit that rule only to "started" Tickets. Otherwise we create an odd loophole where a READY-but-not-started
> Ticket can silently change its inherited purpose/gates under the same identity. Draft/uncommitted construction can
> obviously still correct its parent before the Ticket identity becomes governing. Promotion is the explicit exception
> because it is a different semantic operation.

**How v3 applies it** (§3.12; the lead developer's decisions on the review's D1 to D4):

- **"Before identity is established":** AEW has no draft or uncommitted Ticket, because `work create` establishes the
  identity. So no `work move` of a Ticket is allowed after creation, whatever its state (D1).
- **Finished units:** their hierarchy is final (`_move_archived` refused).
- **Timing:** the refusals apply from S2a on every enabled project, and the carry rules from S2b.2, after S2b.1's
  accessor (D2, R8, V1). A dormant
  project keeps ADR-0007's rules until it is enabled (D4, §3.0 rule 2).
- **Promotion** (v4, R4; governed): allowed wherever the unit sits, after work has started, as KC §9.4 (frozen) and
  handoff §15 require. It carries the inherited obligations of the ancestors it leaves, which is what §15 lists as
  preserved. The old parent's own closeout and coverage are re-evaluated by the existing rules. Story and Epic moves
  carry the same way.
- **"Monotonic"** is the inherited set in §3.12 (D4, R4).

**No designer question is open.** v3's refusal of non-enclosing promotion is withdrawn: it rested on the old parent's
closeout, which is that parent's own obligation, not one the Ticket inherits.

## 11. Designer information (no decision needed)

- **Replacement is the unguarded route (m9).** `work replace --because objective` is a recorded Lead assertion with no
  confirmation, so after a failed review a Lead can leave a finding behind by replacing the Ticket, where a revision
  would need confirmation. E19-B does not forbid it, and cancel-and-recreate exists today. F4 adds a warning, carries
  T's open adverse items into T''s packs as context, and lists such replacements in the parent closeout record.
- **Reading RD2 (m2):** the Lead may reconfirm the same plan revision after an acceptance change, departing from the
  text of D1's table to keep its intent (§4.2).
- **Reading RD4:** at an effective class of 2 or more, a title typo needs a model confirmation. S11 measures the cost.
- **Confirmation on hosts without OS containment** runs uncontained, with a truthful weaker label (§3.11; A22, the
  operator's F23 decision). On such a host, E19-B §4.2.1's material order holds against every engine path, but not
  against the confirmer's own shell. The label says so wherever the confirmation appears.
- **A possible future relaxation of D1 (no decision needed now).** AEW has no draft Ticket, so v3 refuses every Ticket
  move after `work create`. A later design could treat a Ticket as still "under construction" (the ruling's
  pre-identity phase) while it is BLOCKED with nothing bound:
  - no plan ever accepted;
  - no invocation;
  - no evidence;
  - r1 only;
  - no dependents;
  - no publication-envelope stamp.

  Such a Ticket could then have its parent corrected. v3 does not do this; it would loosen a rule, so it is the
  designer's to propose.
- **Replacement under a new parent (`--because parent`)** cancels the old Ticket, and with it the old parent's claim
  on that work. The old parent's closeout records the supersession (HIER-005). This is the lineage the ruling
  requires, and it is the same route m9 describes.

## 12. Operator actions

- **Enabling:** `aew migrate --ticket-revisions` (or `aew init --ticket-revisions`) on a project the operator chooses,
  from S2a on. The table in §3.2 says what changes, and when. Until S12, nothing changes on any other project.
- **Changing defaults:** adopt `gates.ticket_revision` (`checkpoint_after`, `pending_expiry_s`, `confirmation_cards`)
  with `aew manifest adopt`, only to change a default.
- **Rocky 8:** one full run on `AEW_RL8` for S2a (the store's commit path), one for S4b, and one for S12. S7's containment tests run on Linux.
- **The checkpoint:** the operator answers the challenge after reading the diff shown at their own terminal.
- **The M4-H freeze:** the operator's choice of freeze commit decides whether S12 is in the M4-H product (§9.3).

## 13. Risks

| Risk | Mitigation |
|---|---|
| S3 changes what every gate counts | TR-3's independent recomputation after every walk step; the acceptance lane before merge; dormant projects unchanged |
| S12 changes existing tests | Each changed test listed with its governing clause; none edited silently |
| Hot state grows | Small entries; S11's bound test |
| Interim refusals are friction on enabled projects | Fail closed by design; listed in the register; enabling is the operator's choice until S12 |
| **Residual: an uncontained confirmer's shell can read files.** On a host without OS containment (Windows, or WSL or Linux without working bubblewrap, under the operator's `allow_weaker`), the confirmer runs as the operator's user with a shell. It could read `.aew/withheld/RA-n.yaml`, and so the Lead's rationale, before its initial determination. Every engine read path redacts the rationale, and the bridge releases it only after the seal, but neither stops a direct file read | The truthful weaker label on the confirmation, shown in `status`, `explain`, `revision show`, completion and closeout records and TR-9, never presented as the Linux production guarantee (F23). Hosts whose containment works always contain the confirmer (forced `required`; label-match acceptance). The redo record never holds the rationale (N1), so a contained confirmer has no path to it |
| Ticket moves refused on enabled projects | The ruling and handoff §15; replacement keeps lineage; promotion stays available and carries inherited obligations |
| **Residual: the Lead's own harness transcript holds the rationale (R7).** The Lead types the rationale into `aew revision propose`, so its harness session store holds it. A contained confirmer's layout masks the stores the Lead's harness adapter declares (OpenCode's are already in `SECRET_DIRS`). A store the adapter does not declare, for example a project-local log or another tool's directory, stays readable to a contained confirmer. On an uncontained host, every store is readable | The masks; `aew doctor` warns when the Lead harness's store is not covered and points to `containment.hide`; the confirmation's label (§3.11). Stated plainly here because only the operator can close an undeclared store |
| **Residual: on a host that cannot contain, confirmations follow the operator's mode (X1).** Hosts: Windows, or `AEW_RL8` (slirp4netns), or a Linux or WSL host without bubblewrap or with user namespaces off. Under `allow_weaker`, the confirmer runs uncontained, with the Windows residual: its shell can read `.aew/withheld/`. Under `required`, confirmation-required revisions are refused on that host (`CONFIRMER_CONTAINMENT_UNAVAILABLE`) | Under `allow_weaker`, the truthful label carries `self_test: {ok: false, reason}` and is shown on the confirmation, in `status`, `explain`, `revision show` and closeout (F23). Under `required`, `aew doctor` says "confirmations unavailable on this host" and names `allow_weaker` as the operator's choice. The engine never picks a weaker mode than the operator adopted. Restoring containment removes both |
| **An ancestor-derived value read outside the accessor would let a promotion shed it (V1)** | The static test refuses any other parent-chain walk; the before-and-after tests cover every derived value; the oracle recomputes them independently |
| **A format raise surprising a diff-based check** | Excluded by one named path from SAE-07, E3's equivalence and event fidelity (R6); tested |
| Format raises surprise a rollback | Intended: an older engine refuses rather than ignoring authority-carrying state. The refusal names the format |
