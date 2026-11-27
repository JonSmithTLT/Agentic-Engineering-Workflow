# The wire track: a build plan (STG-14 / I-6 first, then the rest of the wire V-01 needs)

- **Status:** Draft for the operator's discussion (2026-11-27); not approved; nothing is built until the operator
  returns and the designer's session has answered.
- **In the repository:** committed as a draft so that the operator, the designer and the builders discuss one text.
  - It decides nothing. Each question in §7 and §9 is the operator's or the designer's.
  - It changes no register row, board entry or threshold. Those changes are W0's (§6) and the later PRs'.
  - Requirement IDs appear only as IDs (AGENTS.md §7).
- **Read at:** `origin/main` `2db9b762` (#596, E329's scoped bindings). Citations were re-checked at `57f150d9`
  (#631), which added only register notes. Citations in Appendix A are at `eece01e5`.

## The operator's rulings of 2026-11-27, as given

Relayed to the plan's author on 2026-11-27, and quoted as given:
- "start wave 1; build on O-01 0.9's envelope admitting 0.8's 42; lift E181's "after I-6" as long as it does not
  depend on wire work; WIP allowance and batched G3 reinstalls OK."
- The hard constraint: "live UAT at the end of this week — nothing may change behaviour the operator or Lead uses
  before then (commands, refusal codes, defaults, effective modes, what launches read, G3 consent content, Lead-facing
  text, vertical counts)."
- Later the same day: "the wire track is a major change and will NOT start building until the operator is back at
  their dev environment (about 3-4 days) and the designer's session has answered."

**What follows from them:**
- **Timing:** wave 1 (§6) is ready to start on the operator's return, after the designer's session. Only W0, a
  docs-only PR, can land before then.
- **Briefs the designer's answers may re-cut (§6 marks each):**
  - the G3 owner enum (§7 item 3): A1, A2 and F2;
  - how an owner that is not built yet is answered (item 7): A1 and A2;
  - steering's on-switch and lapse target (item 10): B1a and C1a.

## History

- **Revision 1 (2026-11-26 to 27):** the first plan, for STG-14 alone. It was then widened, at the operator's request,
  to the whole wire track, "as hard and as parallel as the dependencies allow". It folds in the wire sizing of
  2026-11-26 (Appendix A).
- **Revision 2 (2026-11-27):** answers an independent review (NEEDS CHANGES, 16 findings) and the rulings above.
  - **Wave 1 is strictly dormant and additive.**
    - B1 is split into B1a, a record nothing reads, and B2, the cut-over.
    - C1 is split into C1a, a store and setting-type table that no launch, `settings show` or digest reads, and C2, the
      cut-over.
    - D1 is dormant.
    - E181-R1 is unmounted by default.
    - A1 neither moves nor re-exports the canonical bytes before A3, and it names the source of the set-level problem
      table.
  - **No wave-1 PR builds on an unmerged one.** The wave-1 engine PRs import nothing from `aew.o01`, and the handlers
    live in B2, C2 and D2 (AGENTS.md §3).
  - **The F lane:** F2 is held unless it leaves the raise's path and the counts unchanged. F3 is added.
  - **Merge rules:** R13 covers the shared schema, package and invariant files. R14 covers the UAT freeze.
  - **E1** waits for the assessor's record.
  - **Escalations restated:** the paid class is now a missing placement, ruled before C2. The steering item is widened
    to the standing default against I6-06.g's lapse.
  - **W0** records rulings instead of asking for them.
  - **Smaller fixes:** the four D-01 routes, the merge order, the D-01 host, test paths, and line citations.
- **Revision 3 (2026-11-27):**
  - Reframed for the operator's later ruling: the wire waits for the operator's return and the designer's session.
  - Prepared to commit as a plan for discussion. The sizing it relies on is now Appendix A.

**Contents:**
1. What governs
2. Every row, classified
3. STG-14 in detail
4. The dependency graph and the critical path
5. The lanes and their files
6. Wave 1, with the builder briefs
7. The designer's agenda
8. The later PRs
9. Risks, contradictions and questions
10. The facts and their owners

Appendix A holds the wire sizing of 2026-11-26, with its corrections.

---

## 1. What governs, and what is true at `2db9b762`

### 1.1 The governing sources

- **STG-14 / I-6:** A-39, `docs/contracts/A-39/I6-PROFILE.md` (revision 3, adopted 2026-10-25), with its wire files
  `action-registry-0.8.json` (42 rows) and `refusal-reasons-0.8.json`. **0.8's schema and OpenAPI are not published in
  the repository;** only 0.9's are (`docs/contracts/A-43/o01-command-0.9.schema.json`, `openapi-o01-0.9.yaml`), and
  `docs/contracts/README.md` (the A-34, A-39 and A-43 rows) says 0.9 carries 0.8's 42 byte-equal and is "the current
  selected command wire". 0.9 changes three carried actions: `SET_STEERING_MODE` gains `mission_ref` (required,
  nullable) and four reasons; `CREATE_PROPOSED_WORK` gains two work kinds and `ASKER_NOT_CURRENT`;
  `CONTINUE_ELIGIBLE_WORK` gains HEB's `WORK_NOT_CURRENTLY_ELIGIBLE`, `HEB_STALE_PREDECESSOR`, `HEB_STATE_UNKNOWN`
  (erratum E-1; verified by diffing the two refusal maps). That last change closes the STG-02 gap STG02-BE-01
  (`src/aew/stg02/commands.py:64-72`, `SLICE_OWNER_REASONS`), which answers Appendix A's Q-R2.
- **Amendments that land on I-6's actions:** A-43 (I-7, above); A-56 SMP revision 4 (a persistent raise: three new
  target leaves, `harness_ref`, `lead_route_ref`, `legality_ref`, in no published wire: SMP says "until convergence
  re-vendors the wire, G3-C's overlay carries the leaves"; register E230, Unscheduled); A-46 U-01 (narrows I6-B2: no
  credential moves); A-52 RHC (the resource-ceilings row).
- **The rest of the wire:** A-19 (O-01 core), A-24/A-25 (selection profile, owner-pin rules, D-01 0.3.4), A-28 (I-1),
  A-34 (I-2, O-01 0.7), A-30 (I-3), A-31 (I-4), A-29 (I-5), A-43 (I-7), A-26/A-37 (G3 wire and profile), A-51 (AP5),
  A-49 (TB01), A-12 (D-01).
- **The binding model (E329, #596):** `docs/design/scoped-control-bindings-amendment-2026-11-25.md`. An operation binds
  the item it read (`aew.engine.approval.prior`, `require_binding`, `refuse_change`; `src/aew/engine/approval.py:20-110`),
  `CHANGED_SINCE_READ` asks for a fresh read, and §5 says "A-33's G3 command approval stays bound to its command-set
  key. A change elsewhere in control state does not consume that approval".

### 1.2 The requirement IDs (STG-14 / I-6)

**The repository's ledger holds none of them, by design.** `grep` of `docs/design/requirements-ledger.yaml` for `I6-`
finds nothing; STG-12's Notes: "No requirement ids or text in the repository: the trace is the design side's"; AGENTS.md
§7 asks a pull request to name the IDs it serves, IDs only. The IDs below are read from the profile's own numbering and
from the register's notes and SYS-29's `serves_claims`; each PR in section 3 names the ones it serves.

- **Fit and ownership:** I6-00, I6-00a, I6-00b, I6-01, I6-01a, I6-01b.
- **NARROW_OR_REVOKE_STANDING_POLICY (P06):** I6-02, I6-02.a to I6-02.e.
- **ISSUE_STANDING_POLICY as a widening (P07):** I6-03.
- **ADOPT_MANIFEST_EDIT (P14):** I6-04, I6-04.a to I6-04.f.
- **Model routes (P04):** I6-05.
- **SET_STEERING_MODE (P08):** I6-06, I6-06.a to I6-06.g (as amended by A-43 I7-00.a/I7-07.c and A-56 SMP-01 to SMP-11).
- **REQUEST_CHARGE_RECONCILIATION (P10):** I6-07, I6-07.a to I6-07.e.
- **Host profiles (P11, P12):** I6-08, I6-08.a to I6-08.d, I6-09.
- **Activation, sets, refusals, display:** I6-10, I6-11, I6-12.
- **Scenarios (each a test):** I6-X01 to I6-X10. **Rulings:** I6-R01 to I6-R04. **Backlog (not built):** I6-B1 to I6-B7.
- **Wire claims (SYS-29 `serves_claims`):** `O01-0.8/<ACTION>` and `O01-0.8/<ACTION>/<REASON>` for the five new types;
  the register notes name `O01-0.8/SET_STEERING_MODE` and `O01-0.8/ADOPT_MANIFEST_EDIT` with `I6-06.a`, `.b`, `.f`,
  `I6-04.a`, `I6-05`. Also from the notes: `IF10-05`, `AEW-FR-10.c`, `AEW-FR-26.b`, `AEW-FR-26.c` (the rate unit,
  2026-11-06 note), and `O01-16`.

### 1.3 What already exists for resource, model and host policy

| Concern | What is built | Where | Fit with I-6 |
|---|---|---|---|
| The steering mode (R-01's record) | Modes, ranks, a standing record and a per-generation override with `rev`, operator raise through the endpoint, Lead `lower`, requests, A1 §1.3 records, the loop's eligibility | `src/aew/engine/steering.py:60-200`, `:490-600` | Close. The override is bound to one generation and falls back on its end (`effective`, `:172-191`), as I6-06.g. **Gaps:** no generation-start record with an R-01-issued version (E230's Work says so: "a generation-start record, which the built engine doesn't have"); `raise_mode` refuses with engine errors, not I6-06.a's reasons; it is reached only through the operator endpoint, never O-01 |
| SET_STEERING_MODE's G3 consent | The G3 bridge: `BINDINGS = {"mode_raise": "SET_STEERING_MODE"}`, owner label `ADC` | `src/aew/harness/g3_adapter.py:37-39`; overlay `src/aew/stg02/g3_overlay.py:1-11` and `src/aew/stg02/overlay/set-steering-mode.json` (carries A-43's target) | A bridge "until O-01 convergence folds it in" (the overlay's docstring). The G3 wire's `ConsumeRequest.owner` enum is `ADC, HEB, IF13, RESOURCE_POLICY_ISSUER` (`g3/aew_g3/g3-wire.schema.json:349-355`), so R01 cannot consume without an A-26 change |
| Settings read (IF-13's definitions, read side) | F46.1's configuration projection with its digest and per-field locators | `src/aew/engine/configuration.py:1-50` (`DIGEST_SCHEME = "aew/config-digest/v2"`), `src/aew/policy/config_paths.py`, `aew settings show` (`src/aew/cli/settings_commands.py`) | The digest is the natural `expected_functional_snapshot`; the locator encoder the natural `setting_path`. There is no write half: F46.2 was merged into STG-14 as a note |
| Settings write | `aew manifest adopt` (Lead credential, `OPERATOR_DECIDED`), now with a scoped `binding` | `src/aew/engine/api.py:1182-1186`; broker classification `src/aew/harness/lead_broker.py:91-96` | The opposite of I6-04: whole-file adopt, instant effect, no revision store, no transition, no consent. The F46.2 note says I-6's `ADOPT_MANIFEST_EDIT` supersedes it |
| Model routes | Routing card > class > archetype > default, provider connections, model ids | execution policy (`src/aew/policy/execution.py`), `src/aew/harness/models.py` | A route is a setting of the definition (I6-05): buildable as a typed path. Nothing checks a route against a standing policy at dispatch |
| Resource limits, standing policy | Execution-policy limits and pricing (`src/aew/schemas/pricing.schema.json`, `src/aew/harness/usage.py`); no issuer, no issued policy decision, no `rate_basis` (`grep -r rate_basis src` finds nothing) | | Under IF10-04 a configuration file is a projection, never an issued policy: **the issuer's records do not exist** |
| Host qualification | Nothing: `grep -ri host_profile src` finds nothing; the host assessor (STG-26) has no register row (E308 Notes; Appendix A.5) | | REVOKE_HOST_QUALIFICATION can only answer `NOTHING_QUALIFIED` until assessments exist |
| Charge reconciliation | `aew usage show` reads only | `src/aew/cli/usage_commands.py:19` | No R-01 exposure record; E97 (the relay meter) and E98 (paid-class qualification) are after I-6 |
| The O-01 route | Only the frozen STG-02 0.2 carrier: one fixture HEB owner (`CONTINUE_ELIGIBLE_WORK`), protected members consumed with no effect | `src/aew/stg02/commands.py:1-30`, `:196-256`; `server.py`; the key ledger `ledger.py` (167 lines) | E356: never extended, retired when I-6's route lands. Its `wire.py` (canonical bytes, set digest), `adopted.py` and `outage*.py` are imported by `g3/aew_g3/wire.py:20-21`, `src/aew/g3client.py`, `src/aew/cli/read_commands.py:20-21` (E108's `aew read`) and `src/aew/capability/status.py:38`, so they must outlive the carrier or move first |

### 1.4 Where this plan departs from the sizing (Appendix A)

1. **0.9 erratum E-1 closes STG02-BE-01** (Appendix A left it as Q-R2): verified above.
2. **E108's `aew read` is built** (`src/aew/cli/read_commands.py`; surface map entry `read`, `surface-map.yaml:223`); the
   sizing's verification list (A.9) said not. It depends on `aew.stg02.outage` and `aew.stg02.wire`, so E356 must keep them.
3. **The oracle needs a driver as well as a carrier.** A step lands only at `REACHES_OWNER` (`LANDED = 3`,
   `tests/helpers/vertical/oracle.py:44-48`, `:206-213`), and a landed step the scripted operator cannot drive is a
   `no_driver` problem that fails the verdict (`scripted_operator.py:205-215`; `test_vertical_path.py:218-227`). The
   ledger says the PIN path is not wired ("No PIN is entered yet (no confirmer exists to observe)", `ledger.py:306`).
   So every G3 step needs the vertical's G3 driver (PR F2 below) before it can land green.
4. **The oracle reads one owner action** (`Facts.owner_action`, `oracle.py:143`, `:213`) from the STG-02 carrier
   only (`code_facts`, `:177-203`). It must read a set, from the new carrier, before the second action lands (PR F1).

---

## 2. Every wire increment and row V-01 needs, classified

Key: **NOW** buildable on adopted design today; **DESIGNER** blocked on the end-of-week session, naming exactly what is
missing; **AFTER x** blocked on another increment; **OPERATOR** needs an operator placement or allowance only.

### 2.1 The rows

| Row / system | What | V-01 step | State | Exactly what is missing |
|---|---|---|---|---|
| **STG-14 / SYS-29** | I-6: the O-01 route at 0.9's envelope with 0.8's 42 admitted, and I-6's five types plus P07 and P11's profile half | 12 setting, 13 raise | **NOW, dormant until the UAT:** the wire (A1), the engine owners (B1a, C1a, D1). **NOW, after the UAT:** the route (A2, additive), its cut-overs (A3, B2, C2, C3, D2). **AFTER the designer's agenda item 1:** REVOKE_HOST_QUALIFICATION (E1), whose record is the one the designer is asked for. **DESIGNER:** REQUEST_CHARGE_RECONCILIATION's consume (R01 not in the G3 owner enum), and the first standing policy's placement before C2 (§9.1, C2) | See section 3 |
| **E356** | Retire the STG-02 producer; move the G3 client's tests | none | **AFTER** STG-14's route (PR A2) and the oracle's repoint (F1); coordinate with `web/src/stg02/` (the web developer's) | - |
| **E181** | D-01 0.3.4 production reads (16 routes), W1 to W5 | 3, 8, 10 (reads) | **NOW** (A-12, A-25 adopted). The operator lifted "After I-6" on 2026-11-27, provided the work does not depend on wire work; W0 records that. R1 needs only the D-01 schema and problem matrix in `aew.stg02.adopted`, which E356 keeps, so it qualifies. Unmounted by default until the UAT. `attachments` waits for F31/ATTACH_LEAD | None. The host is an implementation choice: the dashboard server process, behind a switch, recorded in an ADR with A2's loopback and peer-UID choice |
| **E393** | The four reads E181 does not list (`waiting`, `continuation-state/{work_id}`, `runs/{execution_id}`, `owner-operations`) | 10 (`waiting`, `continuation-state`) | **AFTER** E181's framework. The row says "The designer's session decides the producer's shape"; the shape is D-01 0.3.4's, adopted, so the designer's item is a confirmation, not a design | Confirmation only |
| **E381** | ATTACH_LEAD on the wire | 3 open | **DESIGNER** (decision due on E381, `decisions-due.md:68-72`): the action's design ("proposed, with no row" since STG-03), the ceremony question Q-C1, and the attachment record (F31) it rests on | The L02 design: what the consent binds, whether it stands per unchanged basis (A-56's shape), and its relation to `FUNCTIONAL_UNQUALIFIED` |
| **E382** | REATTACH_LEAD | 10 reopen | **DESIGNER** (waits for E381, `decisions-due.md:150`), then **AFTER** E381 and the reads `attention`, `attachments` (E181) and `waiting`, `continuation-state` (E393) | L03 design; Q-C2 (routine reattach with no consent); Q-D2 (is REAFFIRM_ELIGIBLE_CHILD_GRANTS on the path); Q-O3 (does the seat-resume code stay) |
| **E383** | APPROVE_INTEGRATION | 7 publish | **DESIGNER** (waits for E381's item) and **AFTER** four things: the G3 owner enum gains CNI; the host assessor's qualified record (A-51 AP5-01: held `POLICY_UNAVAILABLE` until one exists; STG-26 has no row); AEV readiness with a trust basis (A-49 TB01); the `packages` and `assurance` reads (I5-08a: held `CONTENT_READ_UNAVAILABLE`, `I4-PROFILE.md:233`) | W09's design (I4-06, I4-B7); the assessor's row; Q-C3 |
| **E390** | DECIDE_WORK_PROPOSAL | 5 plan | **DESIGNER:** WIS is not in the G3 owner enum (E390's Work says so); Q-C3 (the PIN replaces the chat question). The wire branch and its reasons are adopted (0.7) | An A-26 amendment of `ConsumeRequest.owner`; Q-C3 |
| **E391** | CREATE_PROPOSED_WORK | 4 ask | **DESIGNER** for how the Lead reaches it: Q-D3 (do the typed tools submit through O-01) and Q-D4 (what authenticates a successor-origin recipient, CS-07). The branch is adopted (A-29, amended by A-43) | Q-D3, Q-D4 |
| **E392** | DELEGATE_NEW_WORKER (and CONTINUE_ELIGIBLE_WORK's production owner) | 6 work | **DESIGNER** (Q-D3, Q-D4, whether A-52 RHC releases step 6a) and **AFTER** the ADC grant store and a real delegated-grant issuer (today a fixture, `stg02/world.py`, `DELEGATION_ISSUER`) | Q-D3, Q-D4, the ADC grant record's shape (A-05 adopted, no record design in the repo) |
| **SYS-46** | The V-01 command wire after I-6 (I-1 to I-5 and I-7's commands) | - | **OPERATOR/Lead:** its `remaining` says "File the rows ... row owed" (`systems.yaml`, SYS-46 `remaining`); E381 to E393 are those rows in fact, but `systems.yaml` lists `register: []` for SYS-46 and no system lists E181, E381 to E383 or E390 to E393 | A board edit (PR W0) |
| **G3 owner enum** (A-26, no row) | `ConsumeRequest.owner` gains WIS, CNI, AEV, R01 | 5, 7, 13 | **DESIGNER** (the G3 wire is pinned, A-26), then 1 PR and a reinstall of G3 on every host (`g3/README.md` step 1) | The amendment |
| **Host assessor** (STG-26, no row) | IF-13's outside-lineage assessment records | 7 (through AP5-01) | **DESIGNER/OPERATOR:** no row, no size | A row and its design |
| **E97, E98** | The relay meter; the paid-class qualification | none of the 13 steps (mission build items) | **AFTER** STG-14 (their When says so) | - |
| **E308** | IF-13 controller beyond I-6's first handlers | none | Unscheduled, after STG-14 | - |
| **E230** | SMP, a persistent raise | none (lowers V-01's PIN cost only) | Unscheduled; needs a generation-start record (written, dormant, by B1a below) and a wire carrying SMP's three leaves | A re-vendored wire with SMP's leaves |
| **I-7's eleven 0.9 actions** | Research, links, mission | none | Later (SYS-46's second closing work) | - |
| **The other 32 of 0.8's 42** | Protective, seat, judgments, widening | none | Later, by class (Appendix A.7, Inc 11+) | - |

### 2.2 V-01's actions and reads (Appendix A.2 and A.3, with this plan's state)

Actions (10): CONTINUE_ELIGIBLE_WORK (E392 part, AFTER), ATTACH_LEAD (E381, DESIGNER), REATTACH_LEAD (E382, DESIGNER),
REAFFIRM_ELIGIBLE_CHILD_GRANTS (only if Q-D2 says so), CREATE_PROPOSED_WORK (E391, DESIGNER), DECIDE_WORK_PROPOSAL
(E390, DESIGNER), DELEGATE_NEW_WORKER (E392, DESIGNER), APPROVE_INTEGRATION (E383, DESIGNER), ADOPT_MANIFEST_EDIT
(STG-14, NOW), SET_STEERING_MODE (STG-14, NOW on the bridge).

Reads (8 to 9): `attachments` (+ `{id}`), `attention`, `assurance`, `resolve`, `work/{kind}/{id}`, `packages` (E181,
NOW after the operator's OK; `attachments` AFTER F31), `waiting`, `continuation-state` (E393, AFTER E181's framework).

**So only two of V-01's ten actions are buildable before the designer's session: both are STG-14's.** The rest of
wave 1 is the shared machinery every later action needs (the carrier, the vertical's driver, the D-01 framework) and the
engine-side owners that do not depend on the open designs.

---

## 3. STG-14 (I-6) in detail

### 3.1 What I-6 requires, against what exists

| Rule | Required | Built today | Missing |
|---|---|---|---|
| I6-00a, I6-11, I6-12 | 42 actions on the 0.8 wire (0.9 envelope), registry and refusal map byte-equal to the adopted copies, the map complete and fail-closed, one member per subject, compare-and-set per subject | The 0.2 carrier with 10 actions; the map pattern (`stg02/commands.py:83-95`) | The new vendored wire, the generalised carrier, the one-member-per-subject rule, the owner dispatch table |
| I6-01b | Every target names its version; stale is refused under its own name | E329's scoped binding (`approval.prior`) inside the engine | A translation from `ChangedSinceRead` to each owner's stale reason (`MODE_STALE`, `DEFINITION_STALE`, `POLICY_STALE`, `QUALIFICATION_STALE`, `EXPOSURE_STALE`) |
| I6-06 (P08) | R-01's mode record per generation, versioned; `CRAWL` at generation start; I6-06.a's reasons; HEB's seat fact unavailable is a hold; no admission check reads the mode | Section 1.3, row 1 | Generation-start record; version; reasons; the O-01 owner handler; the endpoint's raise re-pointed to build an O-01 set |
| I6-04 (P14), I6-05 (P04), P11's profile half | IF-13's revision store and transitions; one typed setting per member; `TRANSITION_UNSETTLED` holds; `NOT_A_SETTING` for other owners' facts and the containment lane; `LOWERS_ADOPTED_FLOOR`; a route change pins in-flight invocations; `EFFECT_CONFIRMED` never means effective | Read projection, digest, locators | The store, the setting-type table, the transition controller, the handlers for ADOPT_MANIFEST_EDIT and REQUEST_PROFILE_CHANGE, the operator's command, the shared mechanism the operator asked for on 2026-11-14 |
| I6-02, I6-03 (P06, P07), the rate unit note | The issuer's standing policy decisions, revisions, revocation; narrowing rules; the widening as a successor issuance; `rate_basis` and window (designer, 2026-11-06) | Nothing | All of it |
| I6-08, I6-09 (P12, P11) | IF-13's assessment records and their revocation, a revocation identity, re-qualification only by a record naming the revocation | Nothing | The assessment record (minimal), the revocation handler; qualifying stays the assessor's (no O-01 type) |
| I6-07 (P10) | R-01's reconciliation request; held `RESOURCE_WRITER_NOT_QUALIFIED` where no qualified writer exists | Nothing | The handler (always held until E98), and the G3 consume for R01 (DESIGNER) |
| I6-10 | An auto-run step under an unadopted A-05 §5 automation row is held | The steering loop's allow-list (`steering.py:193-200`) | A declaration's row field; held steps. **Note:** the operator decided on R-DEC-04 (2026-10-25) that `RUN` reaches ticket start and review request (A-56's "What the adopted text already decides"), so the loop's eligibility is an adopted decision, not only a code allow-list |
| D-01 reads I-6 lists (Interfaces) | Policies, profile revisions and transitions, the mode, exposures, host assessments | `aew settings show`, `aew lead mode` status | **Not D-01 0.3.4 routes:** a D-01 change is the designer's (I-6 "Not covered"). Locally, STG-14 serves them through `aew settings show` and status lines only |
| STG-14 note 2026-11-14 | Dashboard Save, the settings TUI and the one-command CLI call one AEW-owned mechanism, one operator proof, no Lead seat | Nothing | The mechanism (PR C3); the dashboard's door is the web developer's and Q-D4/Q-C5's |
| STG-14 note 2026-11-15 | A maps opt-out with no seat-free route until I-6's settings write path | `aew manifest adopt` with the Lead credential | Served by PR C3 (a `maps.pack_slices` edit is an IF-13 setting) |

### 3.2 The PRs, in order

Sizes: S one small PR; M a normal PR; L large (split if review needs it). Each PR names its requirement IDs in its
description (AGENTS.md §7) and carries its surface-map entry for any new command (CLAUDE.md "Code").

**A1. The O-01 wire, vendored (S-M).** New package `src/aew/o01/`: `adopted.py` (accessors `registry()`, `refusals()`,
`schema()`, `o01_errors()`, `wire_version()`), vendored copies of `docs/contracts/A-43/{action-registry-0.9.json,
refusal-reasons-0.9.json, o01-command-0.9.schema.json, openapi-o01-0.9.yaml}` (with a `pyproject.toml`
package-data entry `"aew.o01" = ["adopted/*.json", "adopted/*.yaml"]`, or the wheel lacks them), and the owner-handler
protocol (`owners.py`: `Owner.check(intent, state) -> refusal | effect`, `Owner.preview`) with an empty dispatch table.
**Nothing imports `aew.o01` in A1** except its own tests.
- **No move of the canonical bytes before A3.** `canonical`/`set_digest` stay in `src/aew/stg02/wire.py`, which
  `g3_adapter.py:34`, `g3client.py:49-50` and `g3/aew_g3/wire.py:20-21` use on the live raise. A1 neither moves nor
  re-exports them. A2 imports them from `aew.stg02.wire`, and the physical move to `aew.o01.wire` is A3's (or A4's).
- **The set-level problem table:** 0.9 publishes none (`find docs/contracts -name '*problem*'` finds nothing). Its
  source stays STG-01 0.5.4's vendored `src/aew/stg02/adopted/command-set-problems.json`, through
  `aew.stg02.adopted.set_problems()` (`adopted.py:37-38`, `:73`). A2 reads it there, and E356 keeps it. Whether 0.9
  keeps STG-01's set-level problems unchanged is a confirmation for the designer (agenda item 11).
- Admitted set: 0.8's 42 (derived from `action-registry-0.8.json`, never a hand list); 0.9's eleven I-7 actions are
  answered as not served (see risk R7 for the hold reason).
- Tests: `test_the_vendored_o01_wire_is_byte_equal_to_the_adopted_contracts`;
  `test_the_0_9_registry_carries_the_0_8_registry_byte_equal_for_its_42_actions`;
  `test_every_owner_reason_of_every_action_maps_to_an_adopted_code_and_an_unmapped_one_fails_closed`;
  `test_the_vendored_wire_ships_in_the_wheel` (package data); `test_nothing_outside_aew_o01_imports_it_yet`. (The
  golden test of the canonical bytes moves to A3, with the move.)
- Reference: `python tools/reference.py render` (modules.md, interfaces.md for the schemas). Register: a note on STG-14
  naming the slicing and the wire target (Q-W1). Board: W0 below may ride here.
- Evidence: unit tests, CI `assurance` green. No vertical movement.
- IDs: I6-00a, I6-11 (the map), I6-12 (render limits: see A3).

**A2. The O-01 carrier and route (M-L). Before the UAT only as additive; otherwise after it.** `src/aew/o01/carrier.py`,
`ledger.py`, `server.py`: CS-01 to CS-09 and SW-04/06/07/08 generalised from `stg02/commands.py:111-160` and
`stg02/ledger.py`; canonical bytes and set digest imported from `aew.stg02.wire`; set-level problems from
`aew.stg02.adopted.set_problems()`; G3 consume at allocation (`stg02/commands.py:196-225`, as is); one member per subject
before any owner state (I6-11); origin, then owner state, then the activation hold, then at most one effect. Successor
and delegated origins are answered `HELD ORIGIN_NOT_ESTABLISHED` until their origins exist (as STG-02's addendum 5). An
action with no registered owner is never consumed (the requester's preview refuses to ask for a consent: risk R7). The
route listens on loopback only, for the operator's UID by peer check (as the operator endpoint), since every I-6 member
is protected and G3 carries the authority. That host choice is an implementation choice, recorded in an ADR in this PR
together with R1's.
- **The additive condition:** no `aew` command, launch, broker or endpoint starts or calls it. Its entry point
  (`src/aew/process_kind.py`) is registered but not started by default. The dispatch table is empty, so it serves no
  owner. A test pins that the default process tree and every command's behaviour are unchanged. If a builder cannot meet
  that, A2 waits until after the UAT.
- Tests (port STG-02's conformance driver, `stg02/server.py:419-467`):
  - `test_a_set_naming_one_subject_twice_is_invalid_request_before_any_owner_state_is_read` (I6-X07);
  - `test_a_replayed_client_request_key_is_a_lookup_and_never_a_second_effect`;
  - `test_a_protected_member_on_a_host_where_g3_does_not_count_is_held_origin_not_established`;
  - `test_an_action_with_no_owner_here_is_never_consumed`;
  - `test_the_receipt_has_one_result_per_member_in_request_order`;
  - `test_no_aew_command_starts_the_o01_route_by_default`.
- Reference: `docs/reference/commands.md` is generated from STG-02's carrier by
  `tools/reference_families/stg02_commands.py` and `stg02_server.py`. Add `o01_commands.py`/`o01_server.py` readers and
  a section, and run `tools/reference.py render`. Surface map: none (no `aew` command; R5).
- Lands with **F1** already merged, so the oracle reads this carrier (it reads an empty owner set, so no step moves).
- IDs: I6-11, I6-01b, `O01-02`, `O01-09`, `O01-13`, CS-01 to CS-09.

**A3. G3 reads the new wire (S, plus a reinstall). After the UAT.** It changes the live raise's consent content.
- `g3/aew_g3/wire.py` takes the registry and schema from `aew.o01.adopted` instead of `aew.stg02` and the overlay.
- `canonical`/`set_digest` move physically to `aew.o01.wire`, with `aew.stg02.wire` re-exporting them for `aew read`
  until A4.
- The overlay's `SET_STEERING_MODE` row (owner label `ADC`) moves into a single bridge table in `aew.o01`, with its
  equality test against A-43. The designer's ruling on G3-C's C3 stands until the enum amendment.
- `g3client.py` checks a 0.9 `CommandSet`.
- The member line limit in the G3 wire's description (`g3-wire.schema.json:180`, "Derived from the sealed O-01 schema
  by verify_g3.py") is re-derived. I6-12 says the largest I-6 member renders in 29 lines.
- **Operational:** `wire_version` changes from `o01-command-0.2-review-candidate` to `o01-command-0.9-candidate`, so
  every host's G3 service needs a reinstall. The "older service" path already explains it (`g3_adapter.py:47-50`).
  Reinstalls are batched (operator, 2026-11-27): A3 and the enum amendment in one if both are ready.
- Tests:
  - `test_canonical_bytes_and_the_set_digest_are_unchanged_by_the_move` (golden from today's `stg02.wire`);
  - `test_g3_renders_every_i6_member_within_30_lines` (derived from the schema, as `verify_i2.py` does);
  - `test_the_bridge_row_differs_from_a_43_only_in_its_owner_label`;
  - the existing `tests/integration/test_g3_endpoint_adapter.py`, on the new wire.
- IDs: I6-12, G3-03.

**B1a. R-01's per-generation mode record, dormant (S-M, engine only, wave 1).** A new record beside today's steering
state, read by nothing that runs:
- a generation-start record at `CRAWL` with an R-01-issued `mode_version`, written when HEB reports a new current
  generation (I6-06.g; also the prerequisite E230 names);
- a new pure function, `steering.owner_check(state, target) -> reason | None`, that returns I6-06.a's reasons
  (`MODE_STALE`, `MODE_UNCHANGED`, `GENERATION_NOT_CURRENT`, `PROJECT_MISMATCH`, `LEAD_STATE_UNAVAILABLE` as a hold),
  comparing through E329's `approval.prior`.

**It must not change:** `effective` (`steering.py:172-191`), `raise_mode`, `lower`, `_raise_problem` (`:543-551`),
`take_default` (`:108-134`), `g3_adapter.mode_version`/`raise_set`/`moved` (`:69-124`), any refusal code, the surface
map, or Lead-facing text. It imports nothing from `aew.o01`.
- Where the record lives: under `steering` in `src/aew/schemas/control.schema.json` (`:588-600`), a shared file (R13).
- Tests:
  - `test_a_new_lead_generation_gets_a_crawl_record_with_a_version` (I6-06.g);
  - `test_the_owner_check_refuses_a_superseded_mode_version_as_mode_stale`;
  - `test_lead_mode_raise_and_lower_refusals_and_the_g3_raise_target_are_unchanged_by_b1a` (a pin on today's codes and
    `raise_set`'s target);
  - `test_effective_mode_is_unchanged_by_the_generation_record`;
  - an invariant in `tests/helpers/invariants.py` for the new record.
- Reference: `control-keys.md`, `writers.md` (re-render).
- IDs: I6-06.a, I6-06.g (record only).

**B2. SET_STEERING_MODE on the O-01 route, and the cut-over (M). After the UAT, and after agenda item 10.** Two parts:
- **The handler:** R-01's owner handler in `src/aew/o01/owners/r01_steering.py`, calling B1a's `owner_check`.
- **The cut-over:**
  - `raise_mode` and `lower` refuse with I6-06.a's reasons (surface-map refusal lists on `lead mode raise`/`lower`
    change, and `vertical-uat.md`'s problem table is the operator's to amend);
  - `effective` reads B1a's per-generation record, so a new generation lapses to `CRAWL` (I6-06.g, I6-R01). How
    `take_default`'s standing record fits with that is agenda item 10;
  - `g3_adapter.raise_set` builds its target from B1a's `mode_version` and submits through the carrier instead of the
    endpoint's private commit (I6-06.f: one admission path);
  - `aew lead mode raise` keeps its surface. Its typed-code fallback stays where G3 does not count (`choose`,
    `g3_adapter.py:60-66`; G3-11).
- Tests:
  - `test_a_new_lead_generation_starts_at_crawl_and_no_raise_can_name_it_before_its_record` (I6-X04);
  - `test_a_raise_reaches_r01_only_through_the_o01_carrier`;
  - `test_set_steering_mode_refusals_map_to_adopted_codes` (all 16);
  - `test_effect_confirmed_means_the_record_was_written_never_more`;
  - `test_no_admission_check_reads_the_mode` (extend `test_legality_modules_never_import_steering`,
    `tests/integration/test_steering_loop.py:533`).
- **Oracle and evidence:** step 13 moves to `REACHES_OWNER`. With F2 it lands, and the steering variants lose the raise
  fallback. Evidence is a vertical lane dispatch run at the PR head.
- IDs: I6-06, I6-06.a, I6-06.b, I6-06.f, I6-06.g, I6-R01, I6-X04, `O01-0.8/SET_STEERING_MODE`.

**C1a. IF-13's revision store, transitions and setting-type table, dormant (M-L, engine only, wave 1).** New
`src/aew/engine/if13.py` and `src/aew/policy/setting_types.py` (names are implementation choices):
- a profile definition is the project's pinned execution-policy document, plus `project.yaml` where the schema types
  its fields;
- revisions are immutable, each with its consent, reason, path, old value and new value;
- each revision has a transition (`REQUESTED`, `CHECKING`, `EFFECTIVE`, `HELD`, `FAILED`, `UNKNOWN_EFFECT`,
  `SUPERSEDED`; IF13-10/12) with a controller-issued identity;
- the setting-type table derives types and constraints from `src/aew/schemas/execution.schema.json`, reading
  `config_paths`'s encoder for locators. It classifies these as other owners' facts: limits and paid classes (the
  issuer), the `steering` mode (R-01), checks (AEV), grants and floors (ADC), messaging (CNI), and the containment lane
  (the installation).

**It must not change:** `manifest_pin_ok` (`engine/base.py:385`, `api.py:1188`) or any launch's read; `aew manifest
adopt`; `config_paths` (no owner column added to it); `engine/configuration.py`'s projection; `aew settings show`'s
output; or `DIGEST_SCHEME`'s digest. Nothing that runs reads the store. It imports nothing from `aew.o01`.
- Shared files: a schema in `src/aew/schemas/` plus its name in `schemas/__init__.py` (`:30-45`); an invariant in
  `tests/helpers/invariants.py`; `control.schema.json` if the store is control state (R13).
- Tests:
  - `test_an_edit_on_a_revision_that_never_became_effective_is_definition_stale`;
  - `test_an_edit_while_a_transition_is_unsettled_is_held_transition_unsettled`;
  - `test_a_failed_route_transition_never_takes_effect_and_the_next_edit_starts_from_the_effective_revision` (I6-X09,
    store level);
  - `test_a_spending_ceiling_in_the_definition_is_not_a_setting` (I6-X03);
  - `test_the_containment_lane_is_not_a_setting`;
  - `test_an_edit_that_removes_a_required_gate_lowers_an_adopted_floor`;
  - `test_settings_show_and_the_configuration_digest_are_unchanged_by_c1a` (pins today's output and digest on a
    fixture project);
  - `test_launches_read_the_adopted_pin_not_the_store`.
- IDs: I6-04.a to I6-04.d, I6-04.f (store level), IF13-03, IF13-10 to IF13-15.

**C2. ADOPT_MANIFEST_EDIT and REQUEST_PROFILE_CHANGE on the route, and the cut-over (M-L). After the UAT, and after
the paid-class placement ruling (§9.1 C2).** Two parts:
- **The handlers:** IF-13's owner handlers on C1a.
- **The cut-over:**
  - launches and `manifest_pin_ok` read the effective revision, after a migration that makes each project's adopted
    pin its revision 1;
  - `aew manifest adopt` either records a revision with a transition, or is retired (Q-O4);
  - the snapshot is the configuration digest, so `expected_functional_snapshot` binds what `settings show` displays;
  - a route setting (P04) pins in-flight invocations to their revision and is checked at dispatch (I6-05: disclosure,
    no carry-over, no silent substitution, and the paid class as ruled).
- Tests:
  - `test_a_project_adopted_before_c2_has_its_pin_as_revision_1_and_launches_unchanged`;
  - `test_a_route_edit_leaves_a_running_invocation_on_its_route_and_the_next_dispatch_waits_for_effective` (I6-X02);
  - `test_a_failed_route_withholds_its_calls_and_never_falls_back`;
  - one test per reason of the 18.
- **Oracle:** step 12 reaches `REACHES_OWNER`. With F2 and C3's driver it lands, and V4's C13 counters should read 0
  in I6-R02's 1-PIN case.
- IDs: I6-04, I6-04.e, I6-05, I6-09 (P11's profile half), `O01-0.8/ADOPT_MANIFEST_EDIT`.

**C3. One settings mechanism for every door (M). After the UAT.** `src/aew/settings_change.py` (or under `engine/`):
- From a typed `(path, operation, value)`, it builds the `ADOPT_MANIFEST_EDIT` set, previews it (any refusal comes
  before a consent), requests the G3 consent, submits, and reports the owner's receipt and the transition.
- `aew settings set <path> <value>` is its CLI door: a new command with a surface-map entry, `OPERATOR_ONLY` in the
  broker, and refused inside an AEW session.
- The settings TUI and the dashboard Save call the same function (the operator's direction of 2026-11-14). The
  dashboard's door is the web developer's and needs agenda item 5. This PR supplies the mechanism and its availability,
  refusal and confirmed-result shapes.
- Tests:
  - `test_settings_set_needs_no_lead_seat_and_no_lead_credential`;
  - `test_every_settings_door_reaches_the_same_mechanism_and_refusals`;
  - `test_a_dashboard_read_session_grants_no_write`.
- Scripted operator: a driver for step 12 (with F2).
- Register: notes on STG-14 for the retirement of F46.2 and F46.4, and for the maps opt-out (the note of 2026-11-15).
- IDs: I6-04, `O01-16`.

**D1. The resource policy issuer, dormant (M-L, engine only, wave 1).** New `src/aew/policy/issuer.py` and
`src/aew/schemas/standing-policy.schema.json`.
- **What it holds:**
  - issued decisions with revisions and revocation;
  - each decision's ceiling and unit, effective-from, expiry, enforcement (`COOPERATIVE`, `MANDATORY_HARD`), provider,
    account, recipient and scope;
  - the rate unit: `rate_basis` over the usage ledger's counter names (`input`, `cache_read`, `cache_write`, `output`)
    and its window. Undeclared means every counter (the designer's ruling 1 of 2026-11-06). AEW sets no number.
- **It must not change:** `policy/execution.py`, `harness/usage.py` or any admission, dispatch or launch. Nothing that
  runs reads it. It imports nothing from `aew.o01`. The admission-time compare is D2's.
- Tests:
  - `test_a_narrowing_that_widens_any_value_is_not_a_narrowing` (I6-02.b);
  - `test_zero_is_a_valid_deny_all_ceiling`;
  - `test_an_undeclared_rate_basis_counts_every_counter`;
  - `test_a_predecessor_revision_stays_immutable_history`;
  - `test_no_admission_or_dispatch_path_reads_the_issuer_yet`.
- IDs: I6-02.b, I6-02.c, I6-03 (record level), IF10-05.

**D2. NARROW_OR_REVOKE_STANDING_POLICY and ISSUE_STANDING_POLICY (widening) on the route (M). After the UAT.** The
issuer's owner handlers, and I6-02.d's effects at admission and dispatch: a dispatched request that cannot be halted
completes, accounted under its original operation and revision, and is never reported cancelled.
- Tests:
  - `test_a_narrowing_refuses_later_paid_admissions_while_an_unhaltable_request_completes_uncancelled` (I6-X01);
  - `test_a_widening_naming_a_revision_a_narrowing_replaced_is_refused` (I6-03's race);
  - `test_a_reducing_type_is_never_held_by_an_activation_row` (I6-10).
- IDs: I6-02, I6-02.a, I6-02.d, I6-02.e, I6-03, I6-10.

**E1. REVOKE_HOST_QUALIFICATION (S-M). After the designer's agenda item 1.** Its record is the assessment record the
designer is asked to design with the assessor's row, so E1 does not pre-empt it. The work: IF-13's revocation identity
and the handler on the designer's record. With no assessor, every call answers `NOTHING_QUALIFIED`.
- Tests:
  - `test_an_assessment_built_on_evidence_from_before_a_revocation_qualifies_nothing` (I6-X10);
  - `test_a_host_revocation_never_withdraws_g3` (I6-08.d);
  - `test_functional_work_on_no_revoked_assessment_continues` (I6-X06, in part).
- IDs: I6-08, I6-08.a to I6-08.d, I6-R04.

**E2. REQUEST_CHARGE_RECONCILIATION (S). Blocked on the designer.** R-01's handler is always held
`RESOURCE_WRITER_NOT_QUALIFIED` until E98 (I6-07.d). It cannot consume until the G3 owner enum gains R01: build it after
the amendment. No new label is invented.
- Tests:
  - `test_a_locator_to_a_file_the_lead_wrote_lowers_no_exposure` (I6-X05);
  - `test_reconciliation_never_resends_the_call` (I6-07.c).
- IDs: I6-07, I6-07.a to I6-07.e, I6-R03.

**A4 = E356. Retire the STG-02 carrier and server (M). After the UAT, after A3, F1, F3 and E393, and after the web
developer has moved off the routes.**
- **Delete:** `stg02/commands.py`, `server.py`, `ledger.py`, `world.py` and `worlds/`.
- **Keep:** `adopted.py` (the D-01 files and `set_problems`), `wire.py` (a re-export), and `outage*.py` (used by
  `aew read` and `capability/status.py`).
- **Move:** the G3 client's tests, to the real route.
- **Re-render:** `docs/reference/commands.md`.
- **The web developer:** `web/stg02.html` and `web/src/stg02/wire.ts` call the slice's O-01 route and its four D-01
  routes (`waiting`, `runs/{execution_id}`, `continuation-state/{work_id}`, `owner-operations`). Do not change `web/`.
- Tests:
  - the STG-02 conformance cases ported in A2 pass on the real route;
  - `test_no_module_imports_the_retired_carrier`.
- Register: close E356. SYS-29's `as_built` loses the STG-02 records.

**STG-14 total:** A1, A2, A3, B1a, B2, C1a, C2, C3, D1, D2, E1, (E2), A4: 12 to 13 PRs.
- **Before the UAT:** four can be in flight at once (A1, B1a, C1a, D1), all dormant, plus A2 only under its additive
  condition.
- **After the UAT:** A3, B2, C2, C3 and D2 (and A2 if it was held), then A4.
- **The register's estimate** was 1-2 + 3-4 + 1 (SYS-29 `remaining`), which under-counts the owners that do not exist
  (the IF-13 store, the issuer).

---

## 4. The dependency graph and the critical path

`=UAT=` marks the end-of-week live UAT. Everything left of it is dormant and additive; every cut-over is right of it.

```
 WAVE 1 (before the UAT: dormant, additive)          =UAT=   AFTER THE UAT (cut-overs)
 [W0 board/register: records the rulings]
 [A1 wire vendored, unimported] ---------------------------> [A2 carrier, if held] -> [A3 G3 on new wire + reinstall]
 [A2 carrier, additive: not started by default] -----------------------------------^          |
 [F1 oracle: a set of owner actions, + new carrier] ---------------------------------------+   |
 [F3 oracle: + D-01 producer's served routes] ---------------------------------------------+   v
 [F2 vertical G3 driver, raise path untouched] --------------------------------------------+-> [A4 = E356]
 [B1a R-01 record, dormant] -------------------------------> [B2 SET_STEERING_MODE + cut-over] => step 13 (with F2)
                                       (agenda item 10) ---^
 [C1a IF-13 store + setting types, dormant] ---------------> [C2 ADOPT/REQUEST_PROFILE_CHANGE + launch cut-over]
                                 (paid-class placement) ---^        -> [C3 settings set] => step 12 (with F2)
 [D1 issuer, dormant] -------------------------------------> [D2 NARROW + widening]
 [E181-R1 D-01 framework, unmounted] ----------------------> [R2 reads, mounted] -> [R3 = E393's four ports] -> A4
                                                              (F3 before R2)
 DESIGNER session (end of week) ---> [E1 host revocation] (agenda item 1)   [E2 charge reconciliation] (agenda item 3)
   E381's designs, G3 owner enum, Q-D3/Q-D4, the assessor's row
        v
 [successor origin (Q-D4)] --> [CREATE_PROPOSED_WORK E391] --> [DECIDE_WORK_PROPOSAL E390, needs the enum] => steps 4, 5
 [F31 attachment record] --> [ATTACH_LEAD E381] + `attachments` --> [REATTACH_LEAD E382]                  => steps 3, 10
 [ADC grant store + delegated issuer] --> [CONTINUE_ELIGIBLE_WORK real] + [DELEGATE_NEW_WORKER E392]      => step 6
 [host assessor (no row)] + [AEV readiness/TB01] + [packages/assurance reads] + [CNI in the enum]
        --> [APPROVE_INTEGRATION E383]                                                                     => step 7
```

**The critical path to the strict gate** (V1, V2 and V4 green; two V1 cases also need the burn-down's C9 and C11):
1. the designer's session (E381's designs, the G3 enum, the assessor's row);
2. **the host assessor** (unsized, no row);
3. APPROVE_INTEGRATION, which also needs the AEV trust basis, CNI, and the `packages` and `assurance` reads. V1 is then
   green;
4. REATTACH, after ATTACH and the reopen reads. V2 is then green.

The carrier (A) and E181 are on that path only as prerequisites. Both start in wave 1, so they come off it. **The
assessor is the longest pole and the least known.** Appendix A.5 ranks it first among the uncertainties.
Asking for its row at the designer's session is the single largest schedule lever.

**The shortest visible win is STG-14's.** Steps 13 and 12 (the steering variants and V4) land right after the UAT
through B2, C2, C3 and A3. Their wave-1 groundwork (A1, B1a, C1a, D1, F1, F2) is already merged by then. None of it
waits on the designer, except B2's agenda item 10 and C2's placement ruling.

---

## 5. Parallel lanes and their file ownership

One builder per lane. A lane owns its files. A file listed under "shared" is touched by several lanes and is merged by
the rules in §9.2 (R1 to R6, R13).

| Lane | PRs, in order | Owns (new, or mainly its own) | Touches shared | Waits on |
|---|---|---|---|---|
| **A. Wire core** | A1, A2, then after the UAT A3, A4 | `src/aew/o01/__init__.py`, `adopted.py`, `owners.py`, `carrier.py`, `ledger.py`, `server.py`, vendored `src/aew/o01/adopted/**`; `tools/reference_families/o01_*.py`; `tests/unit/test_o01_*.py`, `tests/integration/test_o01_route.py`; after the UAT, `g3/aew_g3/wire.py`, `src/aew/g3client.py`, `src/aew/stg02/wire.py`, and the deletion of `src/aew/stg02/{commands,server,ledger,world}.py` | `pyproject.toml` (package-data), `src/aew/process_kind.py`, `docs/reference/*` (render), an ADR (the route's host, with E) | nothing (A1); A1 merged (A2); the UAT, A2 (A3); A3, F1, F3, E393, `web/` (A4) |
| **B. R-01 steering** | B1a, then after the UAT B2 | `src/aew/engine/steering.py` (B1a adds functions only), `src/aew/o01/owners/r01_steering.py` (B2), `tests/unit/test_steering_generation_record.py` (new); B2 also `src/aew/harness/g3_adapter.py`, `tests/integration/test_steering_loop.py`, `tests/integration/test_g3_endpoint_adapter.py` | `src/aew/schemas/control.schema.json` (`steering`, `:588-600`), `tests/helpers/invariants.py`, `docs/reference/*`; B2 also `src/aew/engine/api.py`, `docs/implementation/surface-map.yaml` | nothing (B1a); the UAT, A2, agenda item 10 (B2) |
| **C. IF-13 settings** | C1a, then after the UAT C2, C3; E1 after the designer | `src/aew/engine/if13.py`, `src/aew/policy/setting_types.py`, `src/aew/schemas/profile-revision.schema.json`, `tests/unit/test_if13*.py`; C2 `src/aew/o01/owners/if13.py`; C3 `src/aew/settings_change.py`, `src/aew/cli/settings_commands.py`, `tests/unit/test_settings_set*.py` | `src/aew/schemas/__init__.py` (`:30-45`), `control.schema.json` (if control state), `tests/helpers/invariants.py`, `docs/reference/*`; C2 also `src/aew/policy/config_paths.py`, `src/aew/engine/configuration.py`, `src/aew/engine/base.py` (`manifest_pin_ok`), `api.py`; C3 also `src/aew/harness/lead_broker.py`, `surface-map.yaml` | nothing (C1a); the UAT, A2, the placement ruling (C2); C2, F2 (C3) |
| **D. Resource policy issuer** | D1, then after the UAT D2 | `src/aew/policy/issuer.py`, `src/aew/schemas/standing-policy.schema.json`, `tests/unit/test_issuer*.py`; D2 `src/aew/o01/owners/issuer.py` | `src/aew/schemas/__init__.py`, `tests/helpers/invariants.py`, `docs/reference/*`; D2 also `src/aew/policy/execution.py`, `src/aew/harness/usage.py`, `api.py` | nothing (D1); the UAT, A2 (D2) |
| **E. D-01 reads** | R1 (framework, unmounted), then R2 (reads, mounted), R3 (E393's four ports) | `src/aew/d01/**` (new), `tests/unit/test_d01_*.py`, `tests/integration/test_d01_*.py` | `src/aew/dashboard/server.py` (the switched mount; SYS-03's file), `src/aew/process_kind.py` (if needed), `docs/reference/*`, the ADR (with A) | nothing (R1); F3 and the UAT (R2); R2 (R3) |
| **F. Vertical instrument** | F1, F2, F3 | `tests/helpers/vertical/oracle.py`, `scripted_operator.py`, `ledger.py`, `report.py`, `tests/acceptance/test_vertical_path.py`, and reuse of `tests/helpers/g3.py` | `docs/implementation/v01-burn-down.md` (its guard is `tests/unit/test_v01_burn_down.py`). Never `vertical-uat.md` (the operator's) | nothing (F1, F2); F1 (F3) |
| **W. Board and register** | W0, then notes per PR | `docs/implementation/systems.yaml`, `future-work.yaml` + `notes.d/`, `decisions-due.yaml`, the burn-down's C4 and C12 rows (with F's guard) | the rendered pages through `tools/register.py render` | nothing |

**No wave-1 PR imports a module another wave-1 PR is adding** (AGENTS.md §3, nothing builds on a moving target).
- B1a, C1a and D1 expose engine functions that return the owner's own reasons. They import nothing from `aew.o01`.
- The handlers that bind them to A1's protocol are B2, C2 and D2, written once A1 and A2 are merged.
- F3 reads E181's producer through a reference reader that tolerates the producer's absence. It does not import
  `aew.d01`.

**Sequential:**
- A1 → A2 → A3 → A4.
- B2, C2 and D2 each come after A2 and the UAT.
- C3 after C2.
- R2 after F3; R3 after R2.
- A4 after A3, F1, F3 and R3.
- Every action marked DESIGNER in §2 waits for the session.

---

## 6. Wave 1: the exact list, in merge order, with the builder briefs

**When.**
- **W0 (docs only)** can land now.
- **Items 2 to 10** are ready to start on the operator's return to their dev environment (about 3 to 4 days), once the
  designer's end-of-week session has answered (the operator, 2026-11-27). No builder starts before both have happened.
- **Before starting,** the Lead re-reads each brief against the session's answers. A brief marked **[designer may
  change: item N]** is re-cut where that answer differs from this plan's assumption:
  - **The G3 owner enum, agenda item 3:** A1's bridge table and owner labels, A2's consume path for R01, WIS, CNI and
    AEV owners, and F2's test G3 service.
  - **How an unbuilt owner is answered, item 7:** A1's owner protocol (its preview hook) and A2's served set and
    preview refusal.
  - **Steering's on-switch and lapse target, item 10:** B1a's generation-start record (`CRAWL`, or the standing mode)
    and C1a's classification of `steering.mode`.
  - **The set-level problem table, item 11:** A2 only.
  - **The others** (W0, D1, E181-R1, F1, F3) do not depend on the session's open items.
- **If the UAT has run by then:** the freeze below still applies until the operator lifts it. Wave 1 stays dormant
  either way, and the cut-overs remain the later PRs.

**The constraint every brief carries (the operator, 2026-11-27).** Before the end-of-week live UAT, no PR may change
anything the operator or the Lead uses. That covers:
- `aew` commands and their output;
- refusal codes;
- defaults;
- effective steering modes;
- what launches read;
- G3 consent content;
- Lead-facing text, including the guides, the projection, hints and tool descriptions;
- the vertical's counts.

Every PR ships a test that pins the part of that list it could touch. Each PR is reviewed under AGENTS.md §1 and merged
one at a time under §4. CI (`assurance`) must be green at the head, and the head is cited in the PR body.

**Merge order:** W0, A1, F1, F2, then B1a, C1a, D1 and E181-R1 in any order (each as it clears review), then F3 (after
F1), then A2 if its additive condition holds; otherwise A2 waits for the UAT. **After the UAT:** A3 (alone, with the
batched reinstall), B2, C2 (after the placement ruling), C3, D2, R2 (after F3), R3, then A4 last. A later PR merges
`main` only when it conflicts.

1. **W0: record the rulings (S, docs only; lane W). Can land now.**
   - **Scope:** record the operator's rulings of 2026-11-27, ask nothing. That includes the later ruling: the wire
     track starts on the operator's return, after the designer's session, and only W0 lands before.
   - **`systems.yaml`:**
     - a `wip_allowance` entry with the operator's words, cap and date ("WIP allowance ... OK", cap 14 to cover SYS-29,
       SYS-46 and E181's system), so `python tools/systems.py check` passes;
     - SYS-29 stays `designed_only` until A1 starts, so the allowance is recorded ahead of need;
     - E181, E381 to E383 and E390 to E393 listed under SYS-46 (`register: []` today), or E181 under its own read-wire
       system.
   - **The register:**
     - E181's When amended to the lift and its condition, cited ("as long as it does not depend on wire work",
       operator, 2026-11-27);
     - a STG-14 note recording that Q-W1 is answered (0.9's envelope, 0.8's 42 admitted), the batched reinstalls, the
       wave-1 list (to start on the operator's return, after the designer's session), and the post-UAT hold list (A3,
       A4, B2, C2, C3, D2, R2, and A2 unless additive).
   - **The burn-down:** C4's state "in flight (#596)" (`v01-burn-down.md:52`) becomes "merged (#596); E329 open until a
     vertical re-measure confirms `revision_args` and `stale_retries` at 0". E329 is still open in the register's §6;
     its Work names those counters as its proof, and the driver's `--expect-rev` is already gone from `hints.py`.
     C12's state notes that the wire track is planned and starts on the operator's return, after the designer's
     session (it is not "started").
   - **Must not change:** any code, threshold or vertical count.
   - **Tests:** `tools/register.py render` committed; `python tools/systems.py check`; `tests/unit/test_v01_burn_down.py`;
     the docs-link and ledger tests.
   - **Evidence:** `assurance` green.

2. **A1: the O-01 wire, vendored and unimported (S-M; lane A). [designer may change: items 3 and 7]**
   - **Scope:**
     - `src/aew/o01/__init__.py`, `adopted.py` (accessors for the registry, refusals, schema, `o01_errors` and
       `wire_version`) and `owners.py` (the owner-handler protocol and an empty dispatch table);
     - vendored copies of A-43's registry, refusal map, schema and OpenAPI under `src/aew/o01/adopted/`;
     - the 0.8 subset of 42, derived from A-39's registry;
     - the `pyproject.toml` package-data line.
   - **Owns:** `src/aew/o01/**`, `tests/unit/test_o01_adopted.py`.
   - **Must not change:** `aew.stg02.*` (no move or re-export of `canonical`/`set_digest`), `g3/`, `g3client.py`,
     `g3_adapter.py`, or any importer. Nothing outside `aew.o01` imports it.
   - **Tests:**
     - `test_the_vendored_o01_wire_is_byte_equal_to_the_adopted_contracts`;
     - `test_the_0_9_registry_carries_the_0_8_registry_byte_equal_for_its_42_actions`;
     - `test_every_owner_reason_of_every_action_maps_to_an_adopted_code_and_an_unmapped_one_fails_closed`;
     - `test_the_vendored_wire_ships_in_the_wheel`;
     - `test_nothing_outside_aew_o01_imports_it_yet`.
   - **Evidence:** `assurance`; `tools/reference.py render` (modules, interfaces), with an absolute `PYTHONPATH`. The PR
     description names `I6-00a`, `I6-11` and `I6-12`.

3. **F1: the oracle reads a set of owner actions, from the STG-02 carrier and the new one (S; lane F).**
   - **Scope:**
     - `Facts.owner_action` (`oracle.py:143`) becomes a set, and `part_state` (`:206-213`) tests membership in it;
     - `code_facts` (`:177-203`) unions the STG-02 carrier's reading with the new carrier's dispatch table when
       `aew.o01` exists, through a reference reader. Today that table is empty.
   - **Owns:** `tests/helpers/vertical/oracle.py` and its tests.
   - **Must not change:** any step's derived state, any count, `vertical-uat.md`.
   - **Tests:** `test_the_oracle_derives_the_same_states_before_and_after_the_repoint` (golden over all 13 steps at
     `main`); `test_an_action_any_carrier_hands_to_an_owner_reaches_an_owner`; `tests/unit/test_v01_burn_down.py`.
   - **Evidence:** `assurance`. A vertical dispatch run is optional; the golden test is the proof.

4. **F2: the vertical's G3 driver, with the raise path untouched (M; lane F). [designer may change: item 3]**
   - **Scope:** a scripted-operator driver that types the PIN at a test G3 service (`tests/helpers/g3.py`'s `make` and
     `PIN`) and records `Ledger.pin_entered` for a step whose wire action **has landed**.
   - **Can it be built without changing today's raise or counts? Yes, provided two things hold:**
     - the driver is used only for a step the oracle derives as landed, and today none of the G3 steps is;
     - it does not make G3 "count" in the vertical's world, so `g3_adapter.choose` (`:60-66`) keeps routing today's
       steering raise through the endpoint's one-time code.

     If a builder finds that standing up the test service makes `g3standing.standing` count for the scenario's project,
     F2 is held until B2, and that is said in the PR.
   - **Owns:** `tests/helpers/vertical/scripted_operator.py`, `ledger.py` (the approval matching that `ledger.py:306`
     says is owed), and tests.
   - **Must not change:** the steering raise's path, `approvals` (empty today: `vertical-uat.md:266`), `pin_reentries`,
     any step state, or `vertical-uat.md`.
   - **Tests:**
     - `test_the_vertical_report_counts_are_equal_before_and_after_f2` (the report run over recorded ledgers);
     - `test_the_driver_enters_a_pin_only_at_a_landed_g3_step`;
     - `test_a_pin_beyond_the_budget_counts_under_pin_reentries`;
     - `test_g3_does_not_count_in_the_vertical_world_until_b2`.
   - **Evidence:** `assurance`, and a vertical dispatch run at the head with counts equal to the last re-measure's
     (`f848983e`), cited.

5. **B1a: R-01's per-generation mode record, dormant (S-M; lane B). [designer may change: item 10]**
   - **Scope:**
     - a generation-start record at `CRAWL` with an R-01-issued `mode_version`, written beside the existing `steering`
       state;
     - `steering.owner_check(state, target)`, returning I6-06.a's reasons. It is a pure function no caller uses yet.
   - **Owns:** new functions in `src/aew/engine/steering.py`, `tests/unit/test_steering_generation_record.py`.
   - **Shared:** `control.schema.json`'s `steering` (`:588-600`) and `tests/helpers/invariants.py`, each appended in its
     own section (R13).
   - **Must not change:** `effective`, `raise_mode`, `lower`, `_raise_problem` (`steering.py:543-551`), `take_default`
     (`:108-134`), `g3_adapter.mode_version`/`raise_set`/`moved`, any refusal code, the surface map, the guides. It
     imports nothing from `aew.o01`.
   - **Tests:**
     - `test_a_new_lead_generation_gets_a_crawl_record_with_a_version`;
     - `test_the_owner_check_refuses_a_superseded_mode_version_as_mode_stale`;
     - `test_lead_mode_raise_and_lower_refusals_and_the_g3_raise_target_are_unchanged_by_b1a`;
     - `test_effective_mode_is_unchanged_by_the_generation_record`;
     - the existing `tests/integration/test_steering_loop.py` and `tests/integration/test_g3_endpoint_adapter.py`,
       green and unedited.
   - **Evidence:** `assurance`; the reference re-rendered (control-keys, writers).

6. **C1a: IF-13's revision store and setting-type table, dormant (M-L; lane C). [designer may change: item 10, for
   `steering.mode`'s row]**
   - **Scope:** `src/aew/engine/if13.py` (revisions, transitions, the I6-04.a checks as functions returning owner
     reasons) and `src/aew/policy/setting_types.py`. The setting-type table derives from `execution.schema.json` and
     uses `config_paths` read-only, for locators. It sits beside `config_paths` and adds no column to it.
   - **Owns:** those modules, `src/aew/schemas/profile-revision.schema.json`, `tests/unit/test_if13*.py`.
   - **Shared:** `schemas/__init__.py`, `invariants.py`, and `control.schema.json` if the store is control state.
   - **Must not change:** `manifest_pin_ok` and every launch read, `aew manifest adopt`, `config_paths`,
     `engine/configuration.py`, `aew settings show`'s output, the configuration digest. It imports nothing from
     `aew.o01`.
   - **Tests:**
     - the store-level I6-X03 and I6-X09 tests and the `TRANSITION_UNSETTLED` test (§3.2);
     - `test_the_containment_lane_is_not_a_setting`;
     - `test_settings_show_and_the_configuration_digest_are_unchanged_by_c1a`;
     - `test_launches_read_the_adopted_pin_not_the_store`.
   - **Evidence:** `assurance`; the reference re-rendered.

7. **D1: the resource policy issuer, dormant (M-L; lane D).**
   - **Scope:** `src/aew/policy/issuer.py` and `standing-policy.schema.json`. They hold decisions, revisions,
     revocation, narrowing rules as functions, and the rate unit (`rate_basis` over the usage counters' names, and its
     window).
   - **Owns:** those, `tests/unit/test_issuer*.py`.
   - **Shared:** `schemas/__init__.py`, `invariants.py`.
   - **Must not change:** `policy/execution.py`, `harness/usage.py`, or any admission, dispatch or launch. It imports
     nothing from `aew.o01`.
   - **Tests:** the four in §3.2, and `test_no_admission_or_dispatch_path_reads_the_issuer_yet`.
   - **Evidence:** `assurance`.

8. **E181-R1: the D-01 framework, unmounted by default (M; lane E).**
   - **Scope:** `src/aew/d01/`: the version header, no-store, nondisclosing 404s, recipient entitlement and the
     problem matrix. It reads the D-01 0.3.4 schema and matrix from `aew.stg02.adopted` (the one owner; no second
     copy), and serves no read yet. It is mounted into the dashboard server only behind an off-by-default switch, or
     not at all in this PR.
   - **Owns:** `src/aew/d01/**`, `tests/unit/test_d01_*.py`.
   - **Shared:** `src/aew/dashboard/server.py` (only the switch), and an ADR that records the host choice (the
     dashboard process for D-01, loopback with peer UID for O-01), shared with A2.
   - **Must not change:** the default dashboard's routes, headers or security surface, `web/`, `aew read`.
   - **Tests:**
     - `test_the_default_dashboard_serves_exactly_todays_routes`;
     - `test_a_d01_route_answers_the_adopted_problem_for_an_unknown_id_without_disclosing`;
     - `test_the_d01_framework_reads_the_schema_from_stg02_adopted`.
   - **Evidence:** `assurance` (W1 and W4 for the framework only).

9. **F3: the oracle reads E181's served routes (S; lane F, after F1).**
   - **Scope:** `code_facts`'s `served` becomes the union of the STG-02 server's reading and the D-01 producer's (a new
     reference reader over `aew.d01`, tolerant of its absence). It counts only a route the producer serves when
     mounted. R1 serves none.
   - **Must not change:** any step state (a golden test, as F1's).
   - **Tests:** `test_a_route_the_d01_producer_serves_counts_as_served`;
     `test_the_oracle_derives_the_same_states_after_f3`.
   - **Evidence:** `assurance`.

10. **A2, only if additive** (§3.2). Otherwise it is the first PR after the UAT. **[designer may change: items 3, 7
    and 11]**

---

## 7. The designer's end-of-week session: the agenda

Each item names what it unblocks and the evidence. Ordered by what it unblocks on the critical path.

1. **The host assessor's row (STG-26) and its first design** (A-51 AP5-01: W09 is `POLICY_UNAVAILABLE` until "the host
   assessor's current capability assessment ... is qualified"; "None exists today, for any profile"). Unblocks E383 and
   so V1's strict cases. Asked as Appendix A's Q-D1. Deliverable: a row, its owner text, and the assessment record's
   shape, on which E1 (REVOKE_HOST_QUALIFICATION) then builds; E1 waits for it.
2. **E381's designs: ATTACH_LEAD, REATTACH_LEAD, APPROVE_INTEGRATION** (`decisions-due.md:68-72`; blocks E382 and E383).
   With them, the ceremony rulings Q-C1 (does an attach consent stand per unchanged basis, A-56's shape, with A-32 L02's
   `FUNCTIONAL_UNQUALIFIED` association), Q-C2 (is a reattach on an unchanged basis routine, as A04 rules for children),
   Q-C3 (is the PIN the plan and publish decision itself, so the chat question goes), and Q-D2 (is
   REAFFIRM_ELIGIBLE_CHILD_GRANTS on the reopen path). Deliverable: the three actions' adopted shapes, and F31's
   attachment record as far as ATTACH needs it.
3. **The G3 wire's owner enum (A-26):** add WIS, CNI, AEV and R01 to `ConsumeRequest.owner`
   (`g3/aew_g3/g3-wire.schema.json:349-355`), retiring the `ADC` label on SET_STEERING_MODE. Unblocks E390, E383, E2
   (charge reconciliation) and removes the bridge. Asked as Q-D5. Deliverable: the amended pinned wire (then 1 PR and a
   reinstall per host).
4. **How the Lead reaches the wire (Q-D3) and what authenticates a successor-origin recipient (Q-D4, CS-07):** do the
   typed tools (`src/aew/surface/contract.py:231-372`) submit through O-01 as the Lead's session origin, and is the
   broker's authenticated session that principal? Unblocks E391, E392 and the origin half of every successor action.
   (Where the routes are hosted is not asked: it is an implementation choice, recorded in an ADR with A2 and R1.)
5. **The dashboard's write door (Q-C5 and the operator's 2026-11-14 direction):** the confirmer is local (G3-01) and a
   website session is never G3 (G3-13). Which AEW endpoint does a dashboard Save call to build the set and ask for the
   consent? The dashboard server is GET/HEAD-only today (SYS-03's purpose). Unblocks F46.4's retirement into I-6.
6. **Where the first standing policy is placed on V-01's path (I6-05, I6-R02, IF10-04; designer and operator)**
   (§9.1, C2). I6-R02 already prices it ("one more [PIN] for each `ISSUE_STANDING_POLICY` the provider needs"), and V4's
   budget assumes the covered case (`vertical-uat.md:257-261`). What is missing is placement: which step issues the
   first policy for the project's provider and account, whether its PIN joins the operator-owned budget, and whether a
   subscription route's dispatch is "paid" at all. Needed before C2 merges; C2 does not merge with the check
   unenforced unless the designer or the operator rules so.
7. **An action this deployment does not yet serve** (risk R7): A-24's seven baseline actions have no
   `UNKNOWN_OWNER_STATE` reason (verified: `CLOSE_ATTACHMENT`, `CONTINUE_ELIGIBLE_WORK`, `DELEGATED_CANCEL`,
   `ISSUE_STANDING_POLICY`, `LIFT_OPERATOR_SUSPENSION`, `REQUEST_PROFILE_CHANGE`, `SUSPEND_GRANT`), and the map "is
   complete and fails closed" (I6-11). How does a deployment answer a member whose owner it does not yet serve, without
   consuming the consent? Unblocks A2's final form (this plan's interim: the preview refuses before any consent).
8. **Re-vendoring the wire with SMP's three leaves** (A-56 SMP-01; the overlay bridge until then) and confirming the
   wire target (Q-W1, with the operator): 0.9's envelope with 0.8's 42 admitted. Unblocks E230 later; not V-01-critical.
9. **D-01 additions I-6 lists** (I-6 "Interfaces"): policies, profile revisions and transitions, the steering mode,
   exposures, host assessments. Not V-01-critical; without them the operator sees them only locally.
10. **The steering configuration and the lapse target (§9.1, C3):** steering is switched on by the execution
    policy's `steering.mode` (`_raise_problem`, `steering.py:543-551`, `SteeringNotConfigured`), and `take_default`
    (`:108-134`) writes that default as a mode record (`"source": "default"`) and makes it the standing mode that
    `effective` (`:172-191`) falls back to when a generation ends. I6-06.f and SMP: "a configuration default is not a
    mode"; I6-06.g: a mode "lapses to `CRAWL` when the named generation ends"; I6-04.c makes the mode R-01's, not a
    setting. Questions: is "steering on" a setting separate from the mode; does the standing-default record stay; is the
    lapse target `CRAWL` or the standing mode? No authority is loosened today (a default never raises, `:126-127`).
    Unblocks B2's cut-over and C1a's classification of that path.
11. **Confirmations only:** E393's producer shape is D-01 0.3.4's (no design needed); E392's ADC grant record shape;
    whether A-52 RHC releases step 6a (Appendix A.2, row 23); whether 0.9 keeps STG-01 0.5.4's set-level
    problem table (`command-set-problems.json`) unchanged, since 0.9 publishes none.

**For the operator (not the designer).** Ruled on 2026-11-27, and recorded by W0: wave 1 is approved, to start on the operator's return to their dev
environment, after the designer's end-of-week session (the later ruling of the same day); Q-W1 (0.9's
envelope, 0.8's 42 admitted); E181's lift, on its condition; the WIP allowance; batched G3 reinstalls. Still open: Q-O4
(do E164's `aew policy route` and E331's terminal adopt ship first and give way, or wait for C2/C3); Q-O3 (does the
seat-resume code stay where G3 does not count); the class ruling Q-C4; with the designer, item 6's PIN budget.

---

## 8. The PRs after the session, sized, with their evidence

From Appendix A.5 and this plan's graph. Each action PR carries: its owner handler, its refusal-by-reason tests
(every reason of its map), its consent rendering test (≤30 lines), its oracle part reaching the owner, its scripted
operator or scripted Lead driver, and a vertical dispatch run at its head.

| Increment | PRs | Size | Evidence it should produce |
|---|---|---|---|
| Successor origin (Q-D4) | 1 | M | `test_a_successor_member_needs_the_brokers_authenticated_session_never_a_body_field` |
| E391 CREATE_PROPOSED_WORK (+ typed tool through O-01, Q-D3) | 1-2 | M | step 4 reaches WIS; V1's `guessed_commands` from C3 should drop where the projection offers it |
| E390 DECIDE_WORK_PROPOSAL (after the enum) | 1 | M | step 5 lands; V1 loses the plan fallback; `pin_reentries` 0, approvals within budget |
| ADC grant store + delegated issuer | 2-3 | L | `test_a_delegated_member_with_a_grant_for_another_intent_is_refused` |
| CONTINUE_ELIGIBLE_WORK real HEB + E392 DELEGATE_NEW_WORKER | 2 | M-L | step 6 lands |
| E181 reads (`work/{id}`, `resolve`, `attention`, `assurance`, `packages`) | 3-4 | M each | W1 to W5 per read; step 8 served |
| E393 (`waiting`, `continuation-state`, `runs/{id}`, `owner-operations`) | 1-2 | M | step 10's two reads stay served after E356 |
| F31 attachment record + E381 ATTACH_LEAD + `attachments` | 2-3 | M-L | step 3 lands; every case loses the open fallback |
| E382 REATTACH_LEAD | 1-2 | M | step 10 lands; V2 green given C5; `pin_reentries` loses the resume code (Q5's answer) |
| Host assessor (STG-26) | unknown | L? | AP5-01 qualified on the Linux lane host |
| AEV readiness with trust basis (TB01) + CNI packages | 2-3 | L | W09's prerequisites |
| E383 APPROVE_INTEGRATION | 1-2 | L | step 7 lands; V1 strict green with C9, C11 |
| G3 enum amendment, after the designer | 1 + reinstall | S | `test_g3_consumes_for_wis_cni_aev_r01`; the bridge test removed |

**Totals:** STG-14 12-13 PRs; the rest of V-01's subset 25-35 PRs (Appendix A.5's 30-45 for the whole V-01 subset, less
what STG-14 and section 6 already carry). The other 32 actions and I-7's eleven are after V-01.

**CI and proof lanes:** every PR: `assurance` green at its head (AGENTS.md §1, §4), the touched tests and neighbours
locally with an absolute `PYTHONPATH` to the worktree's `src`. Action PRs: a `vertical` dispatch run (`vertical.yml`,
shadow, not a gate) at the head, its report cited in the PR body. G3-touching PRs (A3, B2, the enum PR): the integration
test on the real service's rules (`tests/integration/test_g3_endpoint_adapter.py`) and a note that hosts need a reinstall.

---

## 9. Risks, contradictions and questions

### 9.1 Contradictions with the adopted design, already in the code or the register

- **C1. The wire target.** STG-14's Work says O-01 0.8 (42 actions); `docs/contracts/README.md` calls 0.9 (53) "the
  current selected command wire", and only 0.9's schema is published. This plan builds 0.9's envelope with 0.8's 42
  admitted (a superset with no conflict: 0.9 carries 0.8 byte-equal except three amended actions). **Answered by the
  operator, 2026-11-27:** 0.9's envelope, 0.8's 42 admitted. W0 records it on STG-14; STG-14's Work keeps its wording
  until the register's next edit of that row.
- **C2. The first standing policy has no placement on V-01's path (a missing placement, not an unsatisfiable
  invariant).** IF10-04 makes a configuration file "a projection, never an issued policy decision", AEW has no issuer
  yet, and I6-05 holds paid dispatches on a route no current policy covers. The design prices the policy: I6-R02, "one
  more [PIN] for each `ISSUE_STANDING_POLICY` the provider needs", and V4's budget assumes the covered case
  (`vertical-uat.md:257-261`). What is not placed is which step of V-01's path issues the first policy, whether its PIN
  joins the operator's budget, and whether a subscription route's dispatch is "paid" at all. **Needs a ruling before C2
  merges** (agenda item 6; the budget is the operator's). This plan does not narrow I6-05: C2 does not merge with the
  check unenforced unless the designer or the operator rules so. C2 is after the UAT, so there is no schedule cost this
  week.
- **C3. A configuration default is a mode record, and the lapse target is the standing mode, not `CRAWL`.**
  `_raise_problem` refuses `SteeringNotConfigured` when the adopted execution policy names no `steering.mode`
  (`src/aew/engine/steering.py:543-551`). `take_default` (`:108-134`) writes a non-raising default as a mode record
  (`"source": "default"`) and makes it the standing mode; `effective` (`:172-191`) falls back to that standing mode when
  a generation ends. Against: I6-06.f and SMP, "A configuration default is not a mode"; I6-06.g, the mode "lapses to
  `CRAWL` when the named generation ends"; I6-04.c, a steering mode is R-01's, not a setting. No authority is loosened
  (a default never raises, `:126-127`), but the conflict reaches B2's lapse rule and C1a's classification of
  `steering.mode`, which is also the on-switch. Agenda item 10; B1a leaves all of it untouched, and B2 waits for the
  answer.
- **C4. SET_STEERING_MODE's owner label is `ADC`** (`g3_adapter.py:39`, the overlay), not A-39's `R01`: a recorded
  bridge (the designer's ruling on G3-C's C3; the operator, 2026-11-08), not a defect. It ends with agenda item 3.
- **C5. `aew manifest adopt` and E164's `aew policy model allow` write and adopt in one step** with no revision,
  transition or consent; the F46.2 note on STG-14 says that one-transaction write is "contrary to I6-04.b, .d and .e and
  to O01-16", with E164 "the interim terminal lever". C3 supersedes them; whether they are removed then is Q-O4.
- **C6. The Lead's `lower`** changes the mode outside SET_STEERING_MODE, against I6-06.f's "it changes only through this
  type". It is an as-built flag I-6 lists under "Not covered", and the operator's board decision of 2026-11-06 (item 2,
  quoted in STG-14's F15.5 note) keeps it ("while `lower` stays"). Settled; B1a and B2 keep it, with its record.
- **C7. The paid class and the rate unit both need the usage ledger's counters per request,** which E97's meter
  supplies; I6-02.d's "in flight where the call is genuinely interruptible" needs the relay to interrupt. D2 enforces at
  admission and between effects only, and says so.

### 9.2 Risks to running in parallel, and how merges stay green

- **R1. `docs/reference/*` is regenerated by almost every PR.** Never hand-merge it: on a conflict run
  `python tools/reference.py resolve` (CLAUDE.md), with an absolute `PYTHONPATH` to the worktree's `src`.
- **R2. The register and the board.** Notes go in `notes.d/<row>/` files (`tools/register.py note`), never the Notes
  cell; conflicts on `future-work.md` with `tools/register.py resolve`. `systems.yaml` is hand-kept: only lane W edits
  it (W0, then one line per merged PR at most), to avoid parallel edits of SYS-29.
- **R3. `src/aew/engine/api.py`** (the Engine facade) and **`src/aew/errors.py`**: every engine lane adds methods and
  error classes. Each lane appends in its own section with its own banner comment; error codes are reserved up front in
  W0's note (one list: `MODE_STALE` etc. are owner reasons on the wire, not new `AEWError` codes, so most lanes need no
  new error class at all).
- **R4. `docs/implementation/surface-map.yaml` and `src/aew/harness/lead_broker.py`'s classification:** only C3 adds a
  command in STG-14 (`aew settings set`); B2 changes refusal lists on existing entries (B1a changes none). Merge C3
  after B2. Both are after the UAT.
- **R5. The O-01 route is not an `aew` command or typed tool,** so it has no surface-map entry under today's rule; the
  reference's `commands.md` (generated) is its as-built record. If the operator wants the route in the surface map, that
  is a rule change for the surface map's owner, not this track.
- **R6. The vendored O-01 registry and the G3 wire.** One owner each: `aew.o01.adopted` for the registry, schema and
  map (A1), and the pinned `g3/aew_g3/g3-wire.schema.json` for G3, which only the designer changes. A3 is the one PR that
  moves G3 onto the new wire; it merges alone, with the operator told that every host needs a reinstall (the
  `wire_version` changes). Until A3, the G3 service keeps reading STG-02's registry and the overlay, and the endpoint's
  raise keeps working.
- **R7. A consent must never be burned on an owner that is not built.** Every protected member is consumed before owner
  state is read (origin first, I6-11), and A-24's seven baseline actions have no `UNKNOWN_OWNER_STATE`. The interim:
  the requester's preview refuses to request a consent for an action with no owner in the dispatch table (derived from
  that table, never a list). Agenda item 7.
- **R8. The oracle and the vertical.** F1 must land before A2, or the oracle keeps reading STG-02 and every new
  landing reads "not built"; F3 before R2 and A4, or E181's reads read "not built" and E393's drop when A4 retires the
  STG-02 server; F2 before any G3 step lands, or the verdict fails on `no_driver`, and F2 itself must leave today's
  raise path and counts unchanged (§6, item 4). The burn-down's guard
  (`tests/unit/test_v01_burn_down.py`) fails when a cluster names a closed row: the PR that closes a C12 row edits the
  burn-down in the same change (its "How it stays true").
- **R9. The build board's WIP limit.** `systems.md:23` reads "10 / 12"; SYS-29 and SYS-46 are `designed_only`. Starting
  both, plus a system for E181, takes the count to 12 or 13. The operator allowed it on 2026-11-27; W0 records it as a
  `wip_allowance` entry (`systems.yaml:14`: "the operator's words, cap and quoted date"), so `tools/systems.py check`
  passes.
- **R10. `web/` is the web developer's.** E356 removes routes `web/src/stg02/wire.ts` calls. Do not change `web/`; land
  A4 only after the web developer has moved off them, and keep the four D-01 routes STG-02 serves (`waiting`,
  `runs/{execution_id}`, `continuation-state/{work_id}`, `owner-operations`; `stg02/server.py:9-12`) until E393
  replaces them.
- **R11. G3 reinstalls are operator acts on a host** (A3, the enum PR). Batched, as the operator allowed on
  2026-11-27: A3 and the enum amendment in one reinstall if the designer's session lands the enum before A3 merges.
  Neither happens before the UAT.
- **R12. Merge order to keep `main` green** (AGENTS.md §4: one at a time; a red `main` first).
  - **Wave 1, before the UAT:** W0, A1, F1, F2, then B1a, C1a, D1 and E181-R1 in any order, then F3, then A2 only if
    additive.
  - **After the UAT:** A2 (if held), A3 alone (with the batched reinstall), B2, C2 (after the placement ruling), C3, D2,
    R2, R3, E1 (after agenda item 1), then A4 last.
  - Each later PR merges `main` only when it conflicts.
- **R13. Shared schema, package and invariant files** (the review's finding 6): `pyproject.toml`
  `[tool.setuptools.package-data]` (A1 adds `"aew.o01"`; a lane adding package data appends one line);
  `src/aew/schemas/__init__.py` (`:30-45`, the name table; C1a and D1 each append one name); `src/aew/schemas/control.schema.json`
  (`steering`, `:588-600`, B1a; C1a if its store is control state: each adds its own property, never edits another's);
  `tests/helpers/invariants.py` (B1a, C1a, D1: each appends its own invariant function in its own section, as CLAUDE.md
  asks "when a new state appears"). The rule is R3's: append in a section of one's own, resolve a conflict by keeping
  both, and re-run the schema and invariant tests after the merge.
- **R14. The UAT freeze.** Every wave-1 PR carries the pin test named in its brief (§6). A reviewer who finds a change to
  anything on the operator's list (§6, "The constraint") raises it as a major.

### 9.3 Open questions (only the genuine ones)

For the designer: agenda items 1 to 3, 7, 10 (a missing authority boundary, a missing design or a conflict with
adopted text); 6 (a missing placement, with the operator); 4, 5, 8, 9, 11 (shape and confirmations). For the operator:
Q-O3, Q-O4, Q-C4, and item 6's budget. Answered on 2026-11-27: wave 1, Q-W1, E181's lift, the WIP allowance, batched
reinstalls.

---

## 10. The facts each PR consumes, and their owners (derive, don't restate)

| Fact | Owner (the one accessor) | Consumers in this plan |
|---|---|---|
| The action registry: each action's origin, sole admitting owner, protection direction | `docs/contracts/A-43/action-registry-0.9.json`, through `aew.o01.adopted.registry()` (A1); the 0.8 subset from `docs/contracts/A-39/action-registry-0.8.json` | A2's carrier, A3's G3 service, F1's oracle, the reference reader, R7's served set |
| The refusal map | `refusal-reasons-0.9.json` via `aew.o01.adopted.refusals()` | every owner handler; tests enumerate it, never copy it |
| Targets, their fields and the `wire_version` | `o01-command-0.9.schema.json` via `aew.o01.adopted.schema()` | carrier validation, G3 rendering limits, B2/C2/D2's set builders |
| Canonical bytes and the set digest (SW-02) | `aew.stg02.wire` until A3; `aew.o01.wire` from A3 (with a re-export for `aew read` until A4) | carrier, G3 client and service, `aew read` |
| The set-level problem table (`CONFLICT_CHANGED_SET`, `INTENT_ORDER_OR_DUPLICATE`, ...) | STG-01 0.5.4's vendored `src/aew/stg02/adopted/command-set-problems.json`, through `aew.stg02.adopted.set_problems()` (0.9 publishes none; agenda item 11), kept by E356 | A2's carrier |
| The D-01 0.3.4 schema and HTTP problem matrix | `aew.stg02.adopted` (`aew-d01-read-v0.3.4-FULL.schema.json`, `http-problem-matrix.json`), kept by E356 under SYS-03 | E181-R1, R2, R3, F3 (no second copy) |
| What the D-01 producer serves | the producer's own route table, read by a reference reader (F3) | the oracle (`served`) |
| G3 standing (whether G3 counts on this host) | `aew.g3standing.standing` | carrier origin, `g3_adapter.choose` |
| Which endpoint operation is which protected action | `aew.harness.g3_adapter.BINDINGS` | B2 |
| The G3 owner enum | `g3/aew_g3/g3-wire.schema.json` (pinned, designer's) | A3, E2, the bridge |
| The current Lead generation and seat (HEB's fact) | control state `lead` via `aew.engine.lead_ops` / `Kernel` | B1a, B2 (`LEAD_STATE_UNAVAILABLE`) |
| The mode, its record and version | `aew.engine.steering.effective` today; B1a's per-generation record and `mode_version` (read only from B2 on) | B2, the loop, status lines |
| Mode ranks and names | `steering.MODES`, `steering.RANK` | B1a, B2 (the wire's `CRAWL/WALK/RUN` mapped once, in B2) |
| Policy digests (legality, operational) and pins | `Kernel.policy_digests`, `POLICY_PINS` | B1a, C1a (read only) |
| The functional snapshot | `aew.engine.configuration` (`DIGEST_SCHEME`, the digest), unchanged by wave 1 | C2 (`SNAPSHOT_STALE`) |
| Setting paths, types and constraints, and which owner a path belongs to | Locators: `aew.policy.config_paths` (unchanged). Types, constraints and the owning party: C1a's `aew.policy.setting_types`, derived from `src/aew/schemas/execution.schema.json` | C1a, C2, C3, every settings door |
| A binding's prior value and `CHANGED_SINCE_READ` | `aew.engine.approval.prior` / `require_binding` (E329) | B1a, C1a, D1 (translated to owner stale reasons) |
| The usage counters (`input`, `cache_read`, `cache_write`, `output`) | the usage ledger (`src/aew/harness/usage.py`, `run-usage.schema.json`) | D1's `rate_basis` |
| A step's state and the PIN budget | `tests/helpers/vertical/oracle.py` (`STEPS`, `derive`, `pin_budget`) | F1, F2, every PR's evidence |
| Thresholds | `docs/implementation/vertical-uat.md` (operator's) | read only |
| What the code is (routes, modules, writers) | `docs/reference/` via `tools/reference.py` | every PR re-renders |

**What this plan does not build (the designer's session owns it):** the shapes of ATTACH_LEAD, REATTACH_LEAD,
APPROVE_INTEGRATION, CREATE_PROPOSED_WORK and DECIDE_WORK_PROPOSAL (and E392's), the G3 owner enum, the host assessor and its
assessment record (E1 waits for it), the D-01 additions, the dashboard's write door and SMP's wire. STG-14 builds none of them; its carrier admits their
members only as `HELD`/not served, and burns no consent on them.

---

## Appendix A. The wire sizing of 2026-11-26

This appendix is the sizing that the V-01 burn-down and rows E390 to E393 cite as "the wire sizing of 2026-11-26 at
`eece01e5` (its §2 and §3)". Those two sections are A.2 and A.3 here.
- **What it was:** a read-only investigation at `origin/main` `eece01e5` (#598), with #601 read for E381 to E383. It
  decided nothing. Its file:line citations are at `eece01e5`.
- **What changed in reproducing it:** only the numbering. Its sections become A.1 to A.8, and its verification list
  becomes A.9.
- **The wire target:** it sized O-01 0.8's 42 actions. The operator has since answered its Q-W1 (0.9's envelope, 0.8's
  42 admitted).
- **Where this plan corrects it:** §1.4, summarised in A.10.

### A.1 Ceremony: today against the wire

The operator, 2026-11-26: "it seems this wire adds back in a lot of the ceremony around approving items we just removed
like lead attachment etc". And then: "we do NEED an action to attach a lead. Thats good to have. Its just me and the
designer may need to discuss what protected actions should be and what we are protecting against". And: "an agent
pretending to be me can start an aew session...to do what? If they are already me they can already access everything
else bad id think because they have at that point already escaped their sandbox".

#### A.1.1 The unit: V-01's own counters

V-01's A.1 (`docs/implementation/vertical-uat.md:33-35`): "The operator authenticates at most once, says "fix this
one-line bug", and gets the published result. **The operator handles none of AEW's machinery**".

The counters (`tests/helpers/vertical/ledger.py:39-47`) all have a threshold of **0**. They include `credentials`,
`env_vars`, `raw_yaml`, `revisions`, `takeovers`, `seat_operations`, `manifest_adopts`, `pin_reentries` and
`windows_console_challenges`. Three rules decide how a challenge counts:

- **A PIN that confirms a named action, within the path's budget, is an approval, never counted**
  (`ledger.py:296-314`, `Ledger.pin_entered`). The budget is one PIN per G3-protected step on the path
  (`tests/helpers/vertical/oracle.py:271-273`, `pin_budget`; `vertical-uat.md:228-237`). It is the operator's decision
  of 2026-10-24 on F1, which "replaces v2's 'once per endpoint lifetime'". The budgets are **V1 3** (open, plan,
  publish), **V2 4** (plus reopen), **V4 4** (plus the setting), and with steering on **V1 4, V2 6, V4 5**.
- **A per-action typed-back console code on Linux counts under `pin_reentries`** (`ledger.py:336-347`,
  `Ledger.console_challenge`). The operator's answer to the burn-down's Q5 keeps the seat-resume code counted there
  until REATTACH_LEAD lands.
- **A sign-in beyond the first counts under `pin_reentries`** (`ledger.py:328-334`): the startup unlock and the website
  login.

So **the counters cannot see the ceremony the operator is asking about.** By the F1 rule, a PIN at every G3 step is
budgeted, not counted. A straightforward build of the wire scores 0 on `pin_reentries` while asking for 3 to 6 PINs per
scenario. That is why A.1.2 counts raw interactions beside the counters.

#### A.1.2 Interaction counts along V-01's ideal path

"Today" is what the operator does on `main` now, on the path the alpha evaluator runs. "Wire" is a straightforward build
of the contracts: one G3 consent per protected step, as the oracle budgets.

| # | Step (oracle `STEPS`, `oracle.py:96-130`) | Today: what the operator does | Today's counters | Wire: what the operator does | Wire's counters | Change |
|---|---|---|---|---|---|---|
| 1 | init | `aew init` | 0 | the same (no O-01 command: A-39 I6-00, P14 departure row: "as `aew init` is (L10), so it is no O-01 command and costs no PIN") | 0 | none |
| 2 | configure | options on `aew init` (`--check-command --model --provider`, `oracle.py:101-102`) | 0 | the same | 0 | none |
| 3 | open (L01, L02 `ATTACH_LEAD`) | `aew opencode`. A vacant seat is taken with **no challenge**: `opencode_kind = VACANT_START` (`src/aew/harness/opencode/lead.py:419-421`), then `lead_acquire`, which authorizes nothing and records the actor as `{"kind": "session"}` (`src/aew/engine/lead_ops.py:198-219`, called from `src/aew/harness/lead_broker.py:1247`). The first open's tool-consent screen is a setup fixture, recorded and not counted (the burn-down's Q5 answer) | 0 | `aew opencode` **plus one G3 PIN** in the confirmer. The registry has `ATTACH_LEAD` as `PROTECTED_G3` (`action-registry-0.8.json`, A-25 L02), and the consent binds "installation, exact predecessor, successor, Lead, profile, classification, command args hash and one-use owner operation" (A-25 `SELECTION-PROFILE-AND-SUBSTITUTABILITY.md`, the L02/L03 row) | 0 (1 budgeted approval) | **+1 PIN. FLAGGED** |
| 4 | ask (W15 `CREATE_PROPOSED_WORK`) | a chat line | 0 | the same: `CURRENT_SUCCESSOR_GENERATION`, the Lead's own action, with no PIN | 0 | none |
| 5 | plan (W02 `DECIDE_WORK_PROPOSAL`) | a chat "yes" (V1's decision `plan`, `ledger.py:51`); the Lead records the acceptance through its own route (`plan accept`, `src/aew/engine/work_ops.py:758-760`, Lead token) | 0 (1 decision) | **one G3 PIN**, plus the chat question if the Lead still asks it | 0 (1 budgeted approval, 1 decision) | **+1 PIN. FLAGGED.** Net 0 extra interactions if the confirmer replaces the chat question (Q-C3) |
| 6 | work (W10, C17) | nothing | 0 | nothing: `DELEGATE_NEW_WORKER` is successor-generation, and `CONTINUE_ELIGIBLE_WORK` is delegated-grant | 0 | none |
| 7 | publish (W09 `APPROVE_INTEGRATION`) | a chat "yes" (V1's decision `publish`); the Lead publishes through its typed tool (`integration_publish`, `src/aew/surface/contract.py:364-366`: "calling this is your publication decision") | 0 (1 decision) | **one G3 PIN** (plus the chat question, as step 5) | 0 (1 budgeted approval, 1 decision) | **+1 PIN. FLAGGED**, with step 5's caveat |
| 8 | result | nothing (reads) | 0 | nothing (D-01 reads) | 0 | none |
| 9 | exit | the harness's own act | 0 | the same | 0 | none |
| 10 | reopen (L03 `REATTACH_LEAD`) | `aew opencode` resumes the seat. It asks a **typed-back code only when invocations are active or processes are left** (`lead_ops.py:258-265`). Otherwise it resumes with `authorized_by = "operator-tty (seat resume without code)"` (`:257`) | `pin_reentries` +1 when the code is asked (Q5's answer) | `aew opencode` **plus one G3 PIN, every time** | 0 (1 budgeted approval) | The counter improves (−1). The interaction count is the same when work is running, **+1 when nothing is running. FLAGGED (conditional)** |
| 11 | preflight | `aew doctor` | 0 | the same | 0 | none |
| 12 | setting (P14 `ADOPT_MANIFEST_EDIT`) | today's fallback: acquire, export the credential, hand-edit YAML, `aew manifest adopt` (`vertical-uat.md:144-150`). After E331 (unscheduled) it becomes one terminal command with a plain diff confirmation (E331 Work) | `credentials`, `env_vars`, `raw_yaml`, `seat_operations`, `manifest_adopts` (burn-down C13) | one command **plus one G3 PIN per typed setting**. More for a route not yet in the inventory: "one more per further edit … each waiting for the last edit's transition" (A-39 I6-R02) | 0 for the 1-PIN case; **over V4's budget when the route needs more than one edit or a standing policy** (I6-R02) | Fewer than today's fallback. The same count as E331's plan, with a PIN in place of a plain confirmation |
| 13 | raise (P08 `SET_STEERING_MODE`), after each open and reopen | `aew lead mode raise <mode>` at the operator's terminal, then a G3 PIN where G3 counts, or a typed code otherwise (`src/aew/harness/g3_adapter.py:37`, `BINDINGS = {"mode_raise": "SET_STEERING_MODE"}`; `g3/README.md`, "The first real protected action") | 0 (a decision, `vertical-uat.md:151`) | the same PIN. Under A-56 (SMP) the raise **persists for the project** until a change: "the Lead's next session on the same pair runs at `RUN` from its first observation, with no PIN" (`SMP-X01`) | 0 | none now; **−1 per later session once SMP is built** (A-56 is not built: `git grep SMP- -- src` finds nothing) |

**Totals per scenario** (raw interactions beyond typing commands and chat lines):

| Scenario | Today (alpha path) | Wire, straightforward | Wire's `pin_reentries` | Wire's budget |
|---|---|---|---|---|
| V1 | 0 codes, 0 PINs, 2 chat decisions | 3 PINs (open, plan, publish), plus 2 chat decisions unless the confirmer replaces them | 0 | 3 |
| V2 | V1's, plus 0 or 1 resume code (counted, a breach) | 4 PINs | 0 | 4 |
| V4 | V1's, plus today's 5-counter fallback | 4 PINs (or more, I6-R02) | 0, or over budget | 4 |
| V1 / V2 / V4, steering on | plus 1 PIN per raise (built today) | 4 / 6 / 5 PINs | 0 | 4 / 6 / 5 |

**What a straightforward build adds:** the PIN at open (+1, every scenario), the PINs at plan and publish (+2, V1's
path), and the PIN at a reopen with nothing running (+1, conditional). In V1 that is 0 PINs today against 3 on the
wire. The V-01 counters stay green by construction, because the budget is derived from the same G3 steps.

#### A.1.3 Would a straightforward build breach V-01's thresholds?

**Not on the happy path:** `pin_reentries` stays 0 because every PIN is budgeted, and `credentials` stays 0 because a
PIN is "never under `credentials`" (`ledger.py:300-301`). **It breaches on these paths:**

1. **A consent that expires.** An approval lives at most 10 minutes and a consent 15 (A-37 G3-02 item 5, G3-06). An
   `ADOPT_MANIFEST_EDIT` held behind an unsettled transition "needs a new one: one more PIN" (A-39 I6-04.a). That is
   over budget, so it counts under `pin_reentries`.
2. **A model route not in the inventory** (V4). I6-R02 prices it at one PIN per edit, plus one per
   `ISSUE_STANDING_POLICY` the provider needs. V4's budget is 1 PIN for the setting.
3. **A declined or wrong PIN, retried.** It is over the budget (G3-05; `pin_entered` counts any approval beyond the
   budget).
4. **A website sign-in on top of the startup unlock.** It counts as a second sign-in (`ledger.py:328-334`). This
   matters once the dashboard carries commands (A.4.5).
5. **A host where G3 does not count.** A wire action is then held (`ORIGIN_NOT_ESTABLISHED`, G3-11 and G3-12), with no
   code fallback on the wire. So the step is "not landed" and its fallback is counted.

#### A.1.4 What the contracts allow, for each flagged action

| Flagged | Standing policy (`ISSUE_STANDING_POLICY`) | A delegated grant | Successor-generation origin | Session-scoped G3 | Batching in one consent | Contract text that bears on it |
|---|---|---|---|---|---|---|
| `ATTACH_LEAD` (+1) | No: P05 is resource policy only (`IF10-04`) | No: the type's origin is fixed `PROTECTED_G3` in the registry | No: there is no predecessor generation at a first open | **No.** "the startup unlock (S01-31)" and "a website session or click" are "never G3" (A-37 G3-13). The consent is one-use (G3-08) and lives ≤15 minutes (G3-06) | Only with members known at approval, of one origin class (CS-02), at most 8. A raise can't join: it names the generation the attach creates (the same reason A-39 I6-00 gives for P14) | **A-32 L02 already allows a zero-ceremony open, with no protected authority:** "HEB admits an authority-bearing attachment only with competent operator/governing issuer and G3 as applicable … A separate `FUNCTIONAL_UNQUALIFIED` session association has **zero** protected grant/effect authority". Today's `aew opencode` is that functional association. **Design question Q-C1** |
| `REATTACH_LEAD` (+1 when idle) | No | No | No: L03 is protected | No (as above) | No | A-32 L03: "governing ADC issuer/trusted platform rule (ADC-02.l) classifies routine vs trust revocation". A-32 A04: "**no new operator approval solely due to conversation change**", for child grants, through `REAFFIRM_ELIGIBLE_CHILD_GRANTS` (successor origin, "no new G3 per child", A-25). So the children's continuity is already ceremony-free; the reattach itself is not. **Design question Q-C2** |
| `DECIDE_WORK_PROPOSAL` (+1) | No | No: protected | No | No | Several proposals in one set, if pending together | A-32 W01: "no inference from conversation"; W17: "ordinary in-grant delegation preserved, mandatory project scope never inferred". The PIN **is** V1's `plan` decision, so it can replace the chat question rather than add to it (Q-C3) |
| `APPROVE_INTEGRATION` (+1) | No | No: "An external decision covers exactly this promotion and is spent with it" (A-31 I4, competence paragraph, `I4-PROFILE.md:96`) | No | No | Several packages in one set | The burn-down's Q3 (a compatible rebuild) is the same question one step later. The ledger already reads "publish stays a judgement unless a grant covers it" (`ledger.py:49-50`), but no adopted type issues such a grant: `AUTHORIZE_EXTERNAL_EFFECT` is "not blanket tool whitelist" (A-32 A09). Q-C3 |

**The precedent for less ceremony is already adopted:** A-56 (SMP) amended A-39 so that a raise persists per project
until "a change that may affect the run". An attach consent that persists per (project, host, harness, model,
profile), re-asked only on a change, would be the same shape (Q-C1).

#### A.1.5 What each protected action guards against, and who could reach it

**What G3 establishes, from its own text.**
- **G3-00:** G3 holds only where "every agent lineage, **the Lead included**, runs contained, with no route to the
  display or to G3".
- **G3-01:** "Malicious code running as the operator's UID is outside the threat model, and so is a process the
  operator runs as root".
- **The operator's threat model** (2026-10-19, quoted in A-39's header): "design against steered agents and AEW bugs,
  not malicious code run as the operator".
- **On Linux:** both sockets are `SocketUser=` the operator, mode 0600, and the service admits only the operator's UID
  (G3-10). The key belongs to the service's own dynamic UID (G3-09), so a same-UID process cannot sign a consent. It
  can reach `request.sock` and `confirm.sock`, though, and per G3-01 no claim is made against it.
- **AEW's own residuals for a same-UID process** are stated in code, never claimed closed:
  `src/aew/harness/operator_client.py:38-46`, `RESIDUALS`, including "write control state or .aew/ files directly (the
  protected set is not owned by another principal until F18.6)".

**The three adversaries** (the operator's framing):
- **(a) A contained agent.** The broker already keeps it off the operator's commands. `OPERATOR_ONLY`
  (`src/aew/harness/lead_broker.py:123-124`) covers credential-emitting seat commands such as `lead acquire` and
  `lead takeover` (`:82-85`), `manifest adopt`, `authority accept|reject` and `migrate` (`:95-96`), and `lead mode
  raise` (`:108-109`). `LEAD_REACHABLE` (`:129-141`) lists what a Lead session may relay.
- **(b) A same-UID process outside the sandbox.** By G3-01 this is out of model. G3 makes a consent unforgeable (the
  key is not the operator's UID's), but the owners' state is writable by that UID until F18.6, so G3 protects the
  record, not the outcome.
- **(c) A remote caller** (dashboard, app, phone). "a website session or click" is never G3 (G3-13), and the confirmer
  is a local window (G3-01: "the confirmer's display, its input and the PIN"). On the wire, a remote device can request
  a protected action but cannot approve it. That is a question of where the confirmer can run, not of per-action
  challenges (Q-C5).

**Per action.** "Threat" quotes A-32's `owner_text` for the action's `catalog_ids`, or the governing profile. "Who
reaches the unprotected version today" names the route on `main` and who can reach it. "Fresh act each time?" is the
contracts' answer where one exists. Otherwise it is marked **Q** and goes to the class question in A.1.6.

| Action | Class | Threat (contract text) | Who reaches the unprotected version today | Fresh human act each time? |
|---|---|---|---|---|
| ATTACH_LEAD | Seat | L02: "same-UID CLI/terminal alone cannot issue grants"; the consent binds Lead, profile and classification (A-25) | `aew opencode` / `lead acquire`. (a) no: `lead acquire` is in `CREDENTIAL_EMITTING` (`lead_broker.py:82`). (b) yes. (c) no route today | **Q.** L02 itself separates an authority-bearing attach from a `FUNCTIONAL_UNQUALIFIED` association. Nothing in the contracts says the authority-bearing one must recur per session |
| REATTACH_LEAD | Seat | L03: "rehydrate never auto-runs"; A-25: "Successful reattach atomically fences predecessor and establishes exactly one current successor" | `aew opencode` seat resume (`lead_ops.py:244-290`). (a) no: resume needs the operator's terminal (`may_ask`, `:249-251`). (b) yes. (c) no | **Q.** A04 rules out a new approval for the children "solely due to conversation change", not for the seat itself |
| HANDOVER_LEAD | Seat | L05: "ADC issuer or trusted rule, **not outgoing Lead**, classifies routine versus compromise … unqualified host may carry a functional offer/accept but creates **no protected successor grants**" | `lead handoff offer|accept` (`src/aew/cli/commands.py:205-212`): `CREDENTIAL_EMITTING`. (a) no. (b) yes | Per transfer (L05). A handover is rare, so the cost is small |
| TAKEOVER_LEAD | Seat | L06: "an interactive same-UID terminal **does not** establish G3. Functional-only session replacement cannot promote old grants" | `aew lead takeover` with a typed code (`lead_ops.py:385-410`). (a) no. (b) yes | Per takeover. A recovery path, rare by design (it is a breached counter in V-01) |
| CANCEL_PENDING_LEAD_HANDOFF | Seat (reducing in effect) | L13: "cancel requested ≠ confirmed; cannot erase already admitted transfer" | `lead handoff cancel` (`commands.py:218`), which is in `LEAD_REACHABLE` (`lead_broker.py:136`). (a) **yes, the Lead**. (b) yes | **Q.** The registry gives it `REDUCING` and `PROTECTED_G3` |
| CLOSE_ATTACHMENT | Protective | L04: "HEB revokes/fences current AEW Lead generation" | `lead release` (`commands.py:233`): `CREDENTIAL_EMITTING`. (a) no. (b) yes | Contracts: `REDUCING`. A protective reduction "without being blocked solely by agent-writable changes" (AOI-07.f, as quoted in A-39 I6-02.e). Never held (I6-10). Per act, rare |
| SUSPEND_GRANT | Protective | A02: "no self-declared README stop" | nothing (no ADC grant record exists) | Per act; protective, rare |
| REVOKE_LINEAGE | Protective | A01: "preserve independently authorized exceptions" | nothing | Per act; protective, rare |
| STOP_CHILD_NOW | Protective | C03: "HEB actual process/custody stop" | `harness stop` (`src/aew/cli/work_commands.py:483`), Lead-reachable. (a) the Lead, as its own tool | Per act. G3-13: "a local process stop (O01-10)" is never G3, so a local stop stays available outside the wire |
| RELEASE_CHILD_TO_MANUAL | Protective | C04: "**never** transfer a live child to uncontrolled execution" | nothing | Per act, rare |
| CANCEL_CHILD_OPERATION | Protective | C06: "cancel requested ≠ cancellation confirmed" | `invoke cancel` (`work_commands.py:414`), Lead-reachable | Per act. The Lead's own cancel is `DELEGATED_CANCEL` (no PIN) |
| DISCARD_HELD_RESULT | Protective | C14: "retained audit/provenance … not a publication decision" | nothing | Per act, rare |
| NARROW_OR_REVOKE_STANDING_POLICY | Protective | I6-02.e: "admitted on the operator's consent alone" | nothing | Per act, rare |
| REVOKE_HOST_QUALIFICATION | Protective | I6-08.c: "It only reduces" | nothing | Per act, rare |
| DECIDE_WORK_PROPOSAL | Judgment | W01: "no inference from conversation"; W02: "exact decisions and accepted revision" | `plan accept` (`work_ops.py:758`). Who reaches it is not described here | Each plan is a new judgment, so yes by nature. The question is whether the PIN **replaces** the chat question (Q-C3) |
| CANCEL_OR_REPLACE_TICKET | Judgment | W03: "cannot mutate protected stable Ticket identity/goals in place" | `work cancel` (Story/Epic, `work_commands.py:244`) | Per act |
| ANSWER_DECISION_NEED | Judgment | W05: "does not create unrelated grant/effect" | `authority accept|reject` (`commands.py:352-363`): `OPERATOR_DECIDED`. (a) no | Per need |
| APPROVE_INTERFACE_CHANGE | Judgment | W04: "adoption ≠ implementation" | nothing | Per change |
| APPROVE_INTEGRATION | Judgment (external) | W09: "Actual publication/integration owner, current AEV/ADC/HEB prerequisites"; I4: "spent with it" | `integrate publish` / `integration_publish` (`contract.py:364`). Who reaches it is not described here | Per promotion (I4), with Q3 open for a compatible rebuild |
| LIFT_OPERATOR_SUSPENSION | Widening | A03: "Authority-increasing operator action … new G3" | nothing | Per act (A03 says "new G3") |
| ISSUE_STANDING_POLICY | Widening (money) | P05: "External independently comparable policy issuer" | partly, through policy files and `manifest adopt` (`OPERATOR_DECIDED`) | Per issuance; it **is** the standing mechanism |
| REQUEST_PROFILE_CHANGE | Widening | P02: "protected change needs G3" | `manifest adopt` (`commands.py:155`), `OPERATOR_DECIDED` | Per change |
| ADJUST_LEAD_AUTONOMY | Widening | A05: "operator-approved grant/policy future effects, not retroactive review waivers" | nothing | Per change. It is **itself a standing grant**, so one PIN can cover many later acts |
| OVERRIDE_RISK_FLOOR | Widening | A06: "cannot casually waive mandatory independent verification" | `gate waive` (`work_commands.py:526`), Lead-reachable within policy bounds ("Waivers … stay the Lead's: policy bounds a waiver", `lead_broker.py:93-94`) | Per override |
| AUTHORIZE_EXTERNAL_EFFECT | Widening (external) | A09: "exact consent … not blanket tool whitelist" | nothing | Per effect (A09) |
| ADOPT_MANIFEST_EDIT | Widening | P14: "mere file edit not governance"; I6-04.c keeps other owners' facts out | `manifest adopt` (`OPERATOR_DECIDED`) | Per typed setting (I6-R02); I6-B4 would allow two settings per consent |
| SET_STEERING_MODE | Widening | P08: "**no** alteration to ADC grants, risk class, effects, assurance HOLD, caps or mandatory reviews" | `lead mode raise` (`src/aew/cli/operator_commands.py:49`), `OPERATOR_ENDPOINT`. (a) no | **Answered by A-56:** standing per project until a change (SMP) |
| REQUEST_CHARGE_RECONCILIATION | Widening (money) | P10: "not another dispatch or manual force-settled" | nothing | Per request |

**Under (b), what can a Lead session do that an escaped same-UID process cannot?** Tested against the code and the
contracts:
- **Spend through the relay's provider keys:** nothing extra by default. E360: "A provider that does not opt in keeps
  today's custody: AEW reads the key from its path at start". The key is on a path the operator's UID reads. Under
  E360's opt-in managed custody (unscheduled), the key is protected by "a TPM where the host has one, otherwise a host
  key no sandbox can see". Even then, the relay the Lead reaches runs as AEW host code.
- **Act under G3-delegated grants:** no ADC grant records exist yet (A.2, SUSPEND_GRANT and DELEGATE_NEW_WORKER rows).
  The only built G3-delegated state is a steering mode, and `RESIDUALS` says the same UID can write control state
  directly.
- **So on today's host the operator's intuition holds:** under (b), attaching adds nothing an escaped process lacks.
  That changes only once the protected set is "owned by another principal" (F18.6, in `RESIDUALS`), or once the
  relay's key custody is under another principal (E360's opt-in).

**The strongest counter-argument, fairly stated.** Attach is protected against (a) and (c), not (b).
- **The attach is the root of the Lead's authority chain.** It mints the generation that every later grant, raise
  (A-39 I6-06.a names "the current Lead generation") and reaffirmation (A04) hangs from, and its consent binds "Lead,
  profile, classification" (A-25).
- **Contained or automated starts.** Without a human act at the root, a Lead could be started or swapped by something
  that is not the operator at the keyboard: the endpoint's autostart (`src/aew/harness/operator_autostart.py`), a
  scheduled or unattended run (A-42's mission), the auto-runner, or the dashboard backend once it carries commands. A
  silent swap of model or harness under an existing authority is what S01-22 forbids ("Switching context, harness …
  rechecks the applicable authority").
- **Remote callers.** Once a remote surface exists, (c) can submit an attach, and only G3 stops a stolen session token
  from becoming a Lead.
- **Building it unprotected now** means re-adding protection after F18.6.
- **The counter to the counter:** A-32 L02 already provides the unprotected functional association. Today's contained
  Lead runs fine on it. And A-56 shows the designer will accept a standing consent with a re-ask on change.

**Recommendation, framed as a decision for the operator and the designer.**
- **(i) Keep `ATTACH_LEAD` and `REATTACH_LEAD` as the operator's actions** (the operator: "we do NEED an action to
  attach a lead").
- **(ii) Rule whether "protected" means "must originate from the operator's channel" or "a fresh PIN each time".**
- **(iii) If the former,** the designer amends L02/L03 on A-56's pattern: one consent per (project, host, harness,
  model, profile), standing until one of those changes or a trust revocation (ADC-02.l). A reattach on an unchanged
  basis is routine and asks nothing, as A04 already rules for children.
- **(iv) The cost in V-01's terms:** the open's PIN falls to the first session only, and the reopen's PIN goes. V1's
  budget then reads 2 (plan, publish) after the first run, and V2's reads 2, against today's 3 and 4.

#### A.1.6 The classes, for a ruling class by class

| Class | Members (28) | What it guards | Under (a) | Under (b) | Under (c) | Suggested default (not decided) | Cost in V-01's counters |
|---|---|---|---|---|---|---|---|
| **S. The Lead's seat** | ATTACH_LEAD, REATTACH_LEAD, HANDOVER_LEAD, TAKEOVER_LEAD, CANCEL_PENDING_LEAD_HANDOFF (5) | Who holds the Lead's authority, and on which model, harness and profile (L02, L05, L06) | Already stopped by `CREDENTIAL_EMITTING`. G3 adds the binding to the exact Lead, profile and classification | Adds nothing on today's host (`RESIDUALS`) | The real gain: a remote request cannot become a Lead | Operator origin, with a **standing consent per unchanged basis** (A-56's shape); a fresh PIN only on a change, a handover or a takeover | Wire as designed: +1 PIN per open and reopen (V1 3 → with the default, 2 after the first session; V2 4 → 2). `pin_reentries` stays 0 either way, and the reopen's code goes |
| **P. Protective reductions** | CLOSE_ATTACHMENT, SUSPEND_GRANT, REVOKE_LINEAGE, STOP_CHILD_NOW, RELEASE_CHILD_TO_MANUAL, CANCEL_CHILD_OPERATION, DISCARD_HELD_RESULT, NARROW_OR_REVOKE_STANDING_POLICY, REVOKE_HOST_QUALIFICATION (9) | A steered agent stopping or denying the operator's work; a stop claimed but not made (C06: "cancel requested ≠ cancellation confirmed") | The Lead's own stops stay delegated (DELEGATED_CANCEL, `harness stop`) | Nothing | A remote "stop all" must be the operator's | Per act, as designed: rare and protective, never held (I6-10) | 0: none is on V-01's path |
| **J. The operator's judgments** | DECIDE_WORK_PROPOSAL, CANCEL_OR_REPLACE_TICKET, ANSWER_DECISION_NEED, APPROVE_INTERFACE_CHANGE, APPROVE_INTEGRATION (5) | An approval inferred from conversation (W01) or not the operator's | Not described here | Nothing | The confirmer is local only (G3-01), so a phone cannot approve | Per decision as designed, with **the confirmer replacing the chat question**, so the PIN is the decision, not an extra one | +2 PINs in V1 (plan, publish), budgeted. Net 0 extra interactions if the chat question goes |
| **W. Widening authority, money, external effect** | LIFT_OPERATOR_SUSPENSION, ISSUE_STANDING_POLICY, REQUEST_PROFILE_CHANGE, ADJUST_LEAD_AUTONOMY, OVERRIDE_RISK_FLOOR, AUTHORIZE_EXTERNAL_EFFECT, ADOPT_MANIFEST_EDIT, SET_STEERING_MODE, REQUEST_CHARGE_RECONCILIATION (9) | Escalation of the Lead's own authority, spending, effects outside the host | Already stopped by `OPERATOR_DECIDED` and `OPERATOR_ENDPOINT` | Spending and external effects still matter after an escape; the rest add little | As for J | Per act, as designed. Steering already standing under A-56. ADJUST_LEAD_AUTONOMY is itself the standing lever | V4 +1 PIN (the setting; more under I6-R02). The steering variants +1 per raise, falling to 0 on later sessions under A-56 |


### A.2 The 42 O-01 actions

**Key.**
- **Wiring:**
  - **A** is admission: the registry row, the schema branch, the owner handler.
  - **G3** is the consume path. "G3*" means the owner is outside the pinned G3 wire's `ConsumeRequest.owner` enum
    `['ADC','HEB','IF13','RESOURCE_POLICY_ISSUER']` (`g3/aew_g3/g3-wire.schema.json`, `$defs/ConsumeRequest`), so it
    cannot consume without a G3 wire change (A.4.2).
  - **R(n)** is the refusal map, with n owner reasons in `refusal-reasons-0.8.json`.
  - **CAS** names the version the target binds (I6-01b; A-24 SW-07 idempotency through the shared key ledger, A.4.1).
- **V-01:**
  - **needs** means the oracle's 13 steps cite the action (`oracle.py:96-130`), or V01-01 holds it.
  - **later** means no step cites it.
  - **unknown** carries its evidence.
- **Size:** S is one small PR. M is one to two PRs. L is three or more, or an owner that does not exist yet.

"Exists today" is what on `main` does the same act, and is never the wire action itself. The only wire admissions that
exist are in the frozen STG-02 carrier, `src/aew/stg02/commands.py`: `CONTINUE_ELIGIBLE_WORK` against fixture HEB
(`:226-238`), and protected members consumed with no effect (`:196-225`).

| # | Action | Origin, direction | Owner | Exists today | Wiring | V-01 | Size | Dependencies | Open design questions |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CLOSE_ATTACHMENT | G3, REDUCING | HEB | `aew lead release` (`cli/commands.py:233`) | A, G3, R(6), CAS attachment+generation | later (exit is the harness's own act, step 9) | M | the HEB attachment record (F31) | C02/C05's child dispositions on close |
| 2 | SUSPEND_GRANT | G3, REDUCING | ADC | nothing (no ADC grant record) | A, G3, R(6), CAS grant version | later | M | the ADC grant store | none |
| 3 | LIFT_OPERATOR_SUSPENSION | G3, P/I | ADC | nothing | A, G3, R(6), CAS suspension | later | S | #2 | none |
| 4 | ISSUE_STANDING_POLICY | G3, P/I | RESOURCE_POLICY_ISSUER | partly: the execution policy's limits through `manifest adopt` (`commands.py:155`) | A, G3, R(6), CAS predecessor revision | unknown: only V4 with a provider that needs a policy (I6-R02) | L | the issuer's records; E97 meter, E98 qualification; the rate unit (STG-14 note) | I6-B7 (the widening's display) |
| 5 | REQUEST_PROFILE_CHANGE | G3, P/I | IF13 | partly: `manifest adopt` | A, G3, R(6), CAS snapshot | later | M | the IF-13 controller (#39) | none |
| 6 | DELEGATED_CANCEL | delegated grant, REDUCING | HEB | `invoke cancel` (`work_commands.py:414`), `harness stop` (`:483`); in the STG-02 carrier it is `NOT_MODELLED` (`stg02/commands.py:180-181`) | A, delegated origin, R(4), CAS operation | later | M | the delegated-grant issuer (A.4.3) | none |
| 7 | CONTINUE_ELIGIBLE_WORK | delegated grant, P/I | HEB | `stage continue` (`commands.py:296`), `work dispatch` (`work_commands.py:216`); the STG-02 carrier admits it against fixture HEB (`stg02/commands.py:242-256`) | A, delegated origin, R(4) **plus the owner causes the map lacks** (`SLICE_OWNER_REASONS`, `stg02/commands.py:68-72`, gap STG02-BE-01), CAS work revision + attachment + generation | **needs** (step 6) | M | real HEB eligibility (C18 axes); the delegated-grant issuer | **The refusal map lacks HEB's own causes** (STG02-BE-01). A-43's 0.9 adds reasons to this action (erratum E-1). Check whether that closes it |
| 8 | ATTACH_LEAD | G3, P/I | HEB | `aew opencode` → `lead_acquire` (`lead_ops.py:198-219`), no challenge | A, G3, R(8), CAS predecessor generation | **needs** (step 3) | M–L | the HEB attachment state (F31), the attachments read, the oracle repointed (A.4.4) | **Q-C1** (ceremony); L02's functional association |
| 9 | REATTACH_LEAD | G3, P/I | HEB | seat resume (`lead_ops.py:244-290`), with a conditional typed code (`:258-265`) | A, G3, R(8), CAS predecessor + successor | **needs** (step 10) | M | #8; the attention, attachments and continuation reads; #10 | **Q-C2**; keep the resume code? (Q-O3) |
| 10 | REAFFIRM_ELIGIBLE_CHILD_GRANTS | successor, P/I | ADC | implicit: resume moves active invocations to the new generation (`lead_ops.py:284-290`) | A, successor origin, R(15), CAS child + prior grant version; "repeat is refused `PRECONDITION_STALE` (`ALREADY_REAFFIRMED`)" (A-25) | **unknown**: V2's reopen happens with work running (burn-down C7: "the counted takeover … interrupts the implementer"), and A-32 L03 says A04 "reaffirms only eligible child grants before protected effects". The oracle's step 10 does not cite A04 | M | ADC grants; ADC-02.l's routine classification | Is A04 on V01-01's path? (Q-D2) |
| 11 | SWITCH_ACTIVE_WORK_CONTEXT | successor, P/I | HEB | nothing direct | A, successor, R(7) | later | S | the successor origin | none |
| 12 | PREPARE_CONTEXT_HANDOFF | successor, P/I | HEB | nothing (A-32 L11: "do not alias existing `aew lead handoff`") | A, successor, R(6) | later | M | K-01 provenance | none |
| 13 | LEAD_RELEASE_OWN_SEAT | successor, REDUCING | HEB | `lead release` (Lead credential) | A, successor, R(5) | later | S | #8 | none |
| 14 | HANDOVER_LEAD | G3, P/I | HEB | `lead handoff offer|accept` (`commands.py:205-212`) | A, G3, R(13) | later | M | ADC's routine-or-compromise classification | none |
| 15 | TAKEOVER_LEAD | G3, P/I | HEB | `lead takeover`, typed code (`lead_ops.py:385-410`) | A, G3, R(10) | later (a breach in V-01, never on its path) | M | as #14 | none |
| 16 | CANCEL_PENDING_LEAD_HANDOFF | G3, REDUCING | HEB | `lead handoff cancel` (`commands.py:218`) | A, G3, R(9) | later | S | #14 | Why is a reduction of the Lead's own offer G3? (A.1.5) |
| 17 | CREATE_PROPOSED_WORK | successor, P/I | WIS | `work create` (`work_commands.py:122`); the typed tool `ticket_draft` (`surface/contract.py:313`), not projected on an empty project (burn-down C3) | A, successor, R(15), CAS project revision | **needs** (step 4) | M | the successor origin (A.4.3); the burn-down's E373 and Q4 | Q4 (interim `ticket_draft`?) |
| 18 | DECIDE_WORK_PROPOSAL | G3, P/I | WIS | `plan accept` (`work_commands.py:367`, `work_ops.py:758`); named only in a comment at `engine/scope_ops.py:6` | A, **G3***, R(16), CAS proposal revision | **needs** (step 5) | M | E351 (the plan decision kind), Q8; the G3 owner enum | Q-C3 |
| 19 | CANCEL_OR_REPLACE_TICKET | G3, P/I | WIS | `work cancel` (Story/Epic only, `work_commands.py:244`) | A, G3*, R(20) | later | M | WIS revisions | none |
| 20 | ANSWER_DECISION_NEED | G3, P/I | WIS | `authority accept|reject` (`commands.py:352-363`), partly | A, G3*, R(17) | later (E335's owner table routes the decisions on V1's path) | M | E335/E350; I5-08a's content read | none |
| 21 | APPROVE_INTERFACE_CHANGE | G3, P/I | CNI | nothing | A, G3*, R(17) | later | M | CNI links (A-41) | none |
| 22 | DECIDE_DISCRETIONARY_REVIEW | successor, P/I | AEV | `work dispose` (`work_commands.py:302`), partly | A, successor, R(16) | later (E335 makes review acceptances the Lead's) | M | AEV's finding classes | none |
| 23 | DELEGATE_NEW_WORKER | successor, P/I | ADC | `work assign` (`work_commands.py:178`), `invoke create` (`:403`) | A, successor, R(17), CAS grant | **needs** (step 6) | L | ADC grant issuance; **A-52's resource-ceilings row** ("step 6a's implementer, until the resource-ceilings row is adopted as well", A-51 AP5 Not covered); AP5-04 | Is RHC (A-52) enough to release step 6a? |
| 24 | REVOKE_LINEAGE | G3, REDUCING | ADC | nothing | A, G3, R(10) | later | M | ADC lineage records | none |
| 25 | ADJUST_LEAD_AUTONOMY | G3, P/I | ADC | nothing (steering is a different type) | A, G3, R(12) | later | M | ADC grants | Can it carry the "publish if clean" grant the ledger anticipates? (Q-C3) |
| 26 | OVERRIDE_RISK_FLOOR | G3, P/I | ADC | `gate waive` within policy (`work_commands.py:526`) | A, G3, R(20) | later | M | ADC floors | none |
| 27 | AUTHORIZE_EXTERNAL_EFFECT | G3, P/I | ADC | nothing | A, G3, R(21) | later | L | AP5-02, AP5-03, the host assessor | none |
| 28 | REQUEST_HOLD_RESOLUTION | successor, P/I | AEV | nothing as a request | A, successor, R(19) | later | M | AEV holds (I4-07) | none |
| 29 | REQUEST_INDEPENDENT_REASSESSMENT | successor, P/I | AEV | nothing | A, successor, R(16) | later | M | AEV independence row | none |
| 30 | REFER_HELD_RESULT | successor, P/I | HEB | nothing | A, successor, R(18) | later | M | HEB held results | none |
| 31 | APPROVE_INTEGRATION | G3, P/I | CNI | `integrate publish` (`work_commands.py:660`, `integration_ops.py:815`); the typed tool `integration_publish` (`contract.py:364`) | A, **G3***, R(22), CAS readiness version + package digest | **needs** (step 7) | **L** | (1) I5-08a: "held with `CONTENT_READ_UNAVAILABLE` until a selected read shows the package" (`I4-PROFILE.md:233`), so it needs the `packages` and `assurance` reads; (2) **I4-06/AP5: held `POLICY_UNAVAILABLE` until "the host assessor's current capability assessment … is qualified"** (A-51 AP5-01). A-51: "None exists today, for any profile". **The host assessor (STG-26) has no register row** (E308 Notes); (3) AEV readiness with a trust basis (A-49 TB01); (4) the G3 owner enum | Q-D1 (the assessor); Q3 (a compatible rebuild) |
| 32 | STOP_CHILD_NOW | G3, REDUCING | HEB | `harness stop` (`work_commands.py:483`) | A, G3, R(13) | later | M | HEB custody | none |
| 33 | RELEASE_CHILD_TO_MANUAL | G3, REDUCING | HEB | nothing | A, G3, R(13) | later | M | as #32 | none |
| 34 | CANCEL_CHILD_OPERATION | G3, REDUCING | HEB | `invoke cancel` | A, G3, R(13) | later | S | as #32 | none |
| 35 | DISCARD_HELD_RESULT | G3, REDUCING | HEB | nothing | A, G3, R(14) | later | S | HEB held results | none |
| 36 | REQUEST_BACKGROUND_RERUN | successor, P/I | HEB | `work redispatch` (non-mutating, `work_commands.py:223`) | A, successor, R(22) | later | M | IF12-13, no replay | none |
| 37 | ABANDON_INTERRUPTED_EXECUTION | successor, REDUCING | HEB | `stage abandon` (`commands.py:296`), `work reconcile` (`work_commands.py:294`) | A, successor, R(14) | later | S | none | none |
| 38 | NARROW_OR_REVOKE_STANDING_POLICY | G3, REDUCING | RESOURCE_POLICY_ISSUER | nothing | A, G3, R(13), CAS policy revision | later | M | #4 | none |
| 39 | ADOPT_MANIFEST_EDIT | G3, P/I | IF13 | `manifest adopt` (`commands.py:155`, `OPERATOR_DECIDED`, `lead_broker.py:95-96`); E331 and E164 planned | A, G3, R(18), CAS effective revision + snapshot | **needs** (step 12, V4) | **L** | the IF-13 revision store and transitions (I6-04.d; E308 is the rest); a typed settings schema; E331/E164 overlap; the STG-14 note of 2026-11-14 (one settings mechanism for the dashboard, the TUI and the CLI) | I6-B4 (several settings per consent); does E331's terminal adopt survive I-6? (Q-O4) |
| 40 | SET_STEERING_MODE | G3, P/I | R01 | **built through the operator endpoint, not O-01**: `lead mode raise` (`operator_commands.py:49`), the G3 bridge (`g3_adapter.py:37`), the overlay labelled owner `ADC` "because the pinned G3 wire allows only four owners" (`src/aew/stg02/g3_overlay.py:1-10`) | A, **G3*** (bridged today), R(12; 0.9 adds more) | **needs** (step 13, steering) | S–M | the G3 owner enum; A-56 SMP (unbuilt) | Does A-56's persistence ship with it? |
| 41 | REQUEST_CHARGE_RECONCILIATION | G3, P/I | R01 | nothing (`aew usage show` reads only, `cli/usage_commands.py:19`) | A, G3*, R(13) | later | M | E97 meter, E98 | none |
| 42 | REVOKE_HOST_QUALIFICATION | G3, REDUCING | IF13 | nothing | A, G3, R(11) | later | M | the host assessor's records | none |

**V-01 needs 10 actions** (#7, 8, 9, 17, 18, 23, 31, 39, 40, plus #10 if A04 is on the path): the seven the burn-down's
Q7 names, and the three non-G3 ones of steps 4 and 6. **The other 32 are later.**


### A.3 The D-01 reads

D-01 0.3.4 (A-25's OpenAPI) has **20** routes, not 16. E181 lists 16 and leaves out the four STG-02 serves:
`waiting`, `runs/{execution_id}`, `continuation-state/{work_id}` and `owner-operations`
(`src/aew/stg02/server.py:220-240`, "a D-01 route this slice does not serve (16 of the 20)"). Those four are served from
the fixture world, with the real engine state where `--project` is given (`stg02/world.py:126-165`, `EngineSource`),
and **every stamp unqualified** (`stg02/reads.py:1-8`). When E356 retires STG-02, **the four have no production row**
(Q-R1). Two of them are on V-01's path (step 10).

W1 is the provider, W2 the website, W3 the composed journey, W4 runtime security, W5 the useful product (E181). Every
read needs W1 and W4. A read on V-01's path also needs W3. A read the site shows needs W2, and a read the operator acts
on needs W5. "Dashboard today" is the provisional `/api/v1` route that already projects the same owner's records
(`src/aew/dashboard/server.py:248-300`): a source to port, not a D-01 producer.

| Route | Today's source | W-needs | V-01 | Size | Dependencies |
|---|---|---|---|---|---|
| `/v1/read/attachments` | nothing as D-01; the seat is in the engine's `lead` record (`lead_ops.py`) | W1, W3, W4, W5 | **needs** (steps 3 and 10, L01/L07) | M | the HEB attachment record (F31), #8 |
| `/v1/read/attachments/{attachment_id}` | nothing | W1, W4 | needs with the list (nondisclosing 404) | S | as above |
| `/v1/read/attention` | dashboard `/attention` | W1–W5 | **needs** (step 10, U01) | M | E335's owners; A-44 blocked-on-you |
| `/v1/read/assurance/{subject_kind}/{subject_id}` | dashboard `/evidence`, `/work/{id}` (partly) | W1–W5 | **needs** (step 8, U03; and W09's I5-08a read) | M–L | AEV readiness with a trust basis (I4-10, TB01) |
| `/v1/read/resolve` | nothing | W1, W3, W4 | **needs** (step 8, U03) | M | identity resolution over the owners |
| `/v1/read/work` | dashboard `/work` | W1–W5 | unknown (the site's journey; no step cites it) | M | WIS records |
| `/v1/read/work/{work_kind}/{work_id}` | dashboard `/work/{id}` | W1–W5 | **needs** (step 8, L12) | M | as above |
| `/v1/read/work/{work_kind}/{work_id}/packages` | nothing (candidates are in engine state) | W1, W3, W4, W5 | **needs, indirectly**: W09 is held without it (I5-08a) | M | CNI packages, `digest`, `source_closure_ref` |
| `/v1/read/capabilities` | dashboard `/capabilities` | W1, W2, W4 | later (step 11 uses `aew doctor`; "P03's read … stays owed", `oracle.py:124-125`) | M | IF-13 assessments (E308) |
| `/v1/read/coverage` | nothing | W1, W2, W4 | later (E260 builds on it) | M | E260, E108 |
| `/v1/read/holds/{hold_id}/recovery` | nothing | W1, W4, W5 | later | M | AEV-issued hold options |
| `/v1/read/knowledge` | dashboard `/knowledge` | W1, W2, W4 | later | S–M | K-01 |
| `/v1/read/knowledge/{knowledge_id}/versions/{version_id}` | dashboard `/knowledge/{id}` | W1, W2, W4 | later | S | K-01 versions |
| `/v1/read/knowledge/{…}/activity` | dashboard `/activity` (partly) | W1, W2, W4 | later | S | as above |
| `/v1/read/research/claims/{claim_id}` | nothing (RX-01 is not built) | W1, W4 | later | M | RX-01 (A-43's I-7) |
| `/v1/read/runs` | dashboard `/runs` | W1–W5 | unknown | M | HEB runs |
| *(not in E181)* `/v1/read/waiting` | STG-02, fixture + engine (`server.py:220`) | W1, W3, W4, W5 | **needs** (step 10, U01) | M (port) | Q-R1 |
| *(not in E181)* `/v1/read/continuation-state/{work_id}` | STG-02 (`server.py:227-228`) | W1, W3, W4 | **needs** (step 10, C18) | M (port) | the six owner axes (C18) |
| *(not in E181)* `/v1/read/runs/{execution_id}` | STG-02 | W1, W4 | unknown | S (port) | — |
| *(not in E181)* `/v1/read/owner-operations` | STG-02 (`server.py:223`) | W1, W4 | unknown: reconciling an O-01 receipt (A-25 U05/U09/L03) | M (port) | the real O-01 owners |

**V-01's read subset:** `attachments` (and `{id}`), `attention`, `assurance`, `resolve`, `work/{kind}/{id}` and
`packages`, plus `waiting` and `continuation-state` from STG-02. That is 8 to 9 routes.


### A.4 The cross-cutting pieces

#### A.4.1 The real O-01 endpoint (L, 3–4 PRs)

- **Transport.** STG-02's is a loopback HTTP server (`stg02/server.py`), the G3 client requires "the route must be on
  the loopback address" (`src/aew/g3client.py:15-17`), and the dashboard is a separate `/api/v1` server. The choice of
  host process (the dashboard server, its own service, or the operator endpoint) is open (Q-D4).
- **Recipient auth.** The wire's security scheme is an opaque bearer, and "AEW has no session issuer yet"
  (`stg02/server.py:21-23`). Two origins need a real authenticated principal outside the request body:
  successor-generation members need "an authenticated principal outside the request body (CS-07)" (A-25), and the
  Lead's broker session is the natural one. The operator's device session is (c), A.1.5.
- **The G3 signing path.** It is built: the client (`g3client.py`), the service and the confirmer (`g3/`), and consume
  at allocation (`stg02/commands.py:196-225`). It moves to the real carrier as is.
- **Carrier admission.** The CS-01 to CS-09 set checks and the key ledger port from `stg02/commands.py:111-160` and
  `stg02/ledger.py` (167 lines), generalised from one owner handler to a dispatch table of 42 (or 53) owners. The
  registry and schema become 0.8's (or 0.9's), replacing the 10-action vendored registry and the overlay.
- **The refusal map** loads `refusal-reasons-0.8.json` and fails closed (`stg02/commands.py:83-95`'s pattern). Gap
  STG02-BE-01 (owner causes the map does not list) must be settled for CONTINUE_ELIGIBLE_WORK.

#### A.4.2 The G3 wire's owner enum (M, a design amendment, then 1 PR and a reinstall)

`ConsumeRequest.owner` allows HEB, ADC, IF13 and RESOURCE_POLICY_ISSUER only. **WIS, CNI, AEV and R01** own 13 of the
28 protected actions, among them three of V-01's (#18, #31, #40). SET_STEERING_MODE is bridged today by labelling it ADC
(`g3_overlay.py:1-10`, "a bridge until O-01 convergence folds it in"). The fix is A-26's pinned wire, so it is the
designer's. Every host's G3 then needs a reinstall (`g3/README.md`, step 1).

#### A.4.3 The two non-G3 origins (M + L, 3–4 PRs)

- **Successor generation** (12 actions): the Lead's current session as an authenticated principal. The broker already
  authenticates the Lead's typed calls. Wiring it as the wire's origin is M.
- **Delegated grant** (2 actions): "a current proof from the trusted issuer … bound to this exact intent"
  (`stg02/commands.py:227-240`). The issuer is a fixture (`DELEGATION_ISSUER`, `stg02/world.py`). A real ADC grant
  issuer is L, and the same ADC grant store serves #2, #10, #23, #24 and #25.

#### A.4.4 Retiring STG-02 (M, 1–2 PRs; E356)

- **The G3 client's tests** move to the real route (E356).
- **The oracle is coupled to STG-02.** `code_facts` reads `aew.stg02.adopted.registry()`, the carrier's `_member`
  through `tools/reference_families.stg02_commands`, and the server's dispatch through `stg02_server`
  (`oracle.py:177-203`). So the oracle, the reference readers and `docs/reference/commands.md` move in the same PR, or
  every step reads as "not built".
- **The oracle's `REACHES_OWNER`** is true for one action only (`part_state`, `oracle.py:206-213`,
  `facts.owner_action`). With many owners it needs a set.
- **`web/stg02.html` and `web/src/stg02/`** consume the slice's routes (`web/src/stg02/wire.ts:51-61`). That is the web
  developer's to retire, so E356's PR has to wait on, or coordinate with, their change.
- **The vendored adopted files stay,** under SYS-03 (E356).

#### A.4.5 Conformance tests (M, 2–3 PRs, plus a share in each action's PR)

- **The carrier.** Port the STG-02 conformance driver's cases (`stg02/server.py:419-467`, `driver_config`) to the real
  route.
- **Each wire.** Add the designer's case files (`verify_i6.py`/`i6-cases.json` and their I-2 to I-5 peers) as fixtures,
  where the design workspace publishes them. They are not in this repository.
- **The registry and map.** A test that the registry, the refusal map and the schema equal the adopted copies under
  `docs/contracts/A-39` (or A-43), byte for byte.
- **Each action** ships with its refusal-by-reason tests.

#### A.4.6 The dashboard (web/ is the web developer's: described, not planned)

- **The main app** reads the provisional `/api/v1` (`web/src/api/transport.ts:77`). **The `stg02.html` page** reads the
  slice's D-01 and O-01 routes.
- **Once D-01 and O-01 are real,** the site moves its reads to `/v1/read/*`, with the version header and the no-store
  rules, and its commands to O-01 with the G3 request flow. It also faces three changes that are AEW's to supply:
  - **Settings Save:** a Save becomes an `ADOPT_MANIFEST_EDIT` per setting, each with a PIN (the STG-14 note of
    2026-11-14 asks for "one operator proof" shared by the dashboard, the TUI and the CLI);
  - **the website login** counts as a second sign-in in V-01 (`ledger.py:328-334`) unless it is the one sign-in;
  - **the confirmer** is a local window (G3-01), so a remote browser cannot approve (Q-C5).

#### A.4.7 The Lead's typed tools: over the wire, or as they are?

- **Today** the typed tools (`src/aew/surface/contract.py:231-372`) run engine calls with the Lead's held credential,
  through the broker (`lead_broker.py:115-119`, `TYPED_ONLY`).
- **The actions they map to:** `ticket_draft` (W15), `resolve` (stage continue/abandon: C17, C20), `ticket_start`
  (dispatch: C17, W10) and `integration_publish` (W09).
- **Option 1, keep them as they are.** Cost: 0 PRs. Two paths to one effect then exist, and the oracle can never see
  steps 4 and 6 land, because it derives them from the O-01 registry only.
- **Option 2, route them through O-01.** Each successor- or delegated-origin tool submits a command set as the Lead's
  session origin. Cost: M per tool group, 2–4 PRs. One admission path, as I6-06.f already requires of the auto-runner:
  "It submits each step through the same admission path as the Lead's own call". **Recommended for the designer to
  rule (Q-D3).**
- **Under either option,** `integration_publish` cannot stay the Lead's own decision once W09 is G3, so its tool
  becomes "request the operator's approval".


### A.5 The total

| Part | Full (0.8's 42) | V-01 subset |
|---|---|---|
| O-01 endpoint, carrier, key ledger, refusal map (A.4.1) | 3–4 | 3–4 |
| G3 owner enum (A.4.2) | 1 (after a design amendment) | 1 |
| Origins (A.4.3) | 3–4 | 2–4 (the successor origin; the delegated issuer for #7) |
| D-01 producer: framework + 20 reads (A.3) | 8–12 | 5–7 |
| Retire STG-02 (A.4.4) | 1–2 | 1–2 |
| Conformance (A.4.5) | 2–3 | 2 |
| Lead typed tools over O-01 (A.4.7, option 2) | 2–4 | 2–3 |
| Actions: V-01's 10 (#7, 8, 9, 10, 17, 18, 23, 31, 39, 40) | 14–21 | 14–21 |
| Actions: the other 32 | 30–45 | 0 |
| Owners that do not exist yet: the IF-13 revision store, the ADC grant store, R-01's mode record (part of the L sizes above, listed to show the risk) | inside the above | inside the above |
| **Total** | **≈ 65–95 PRs** | **≈ 30–45 PRs** |
| O-01 0.9's eleven more (I-7: research, links, the mission) | +12–18 | 0 |

**What drives the uncertainty, largest first:**
1. **The host assessor (STG-26).** Without it, W09 stays `POLICY_UNAVAILABLE` on every host (A-51), so V1's strict
   case cannot pass. It has no register row, and its size is unknown here.
2. **The ceremony ruling (A.1).** A standing attach consent removes the reattach PIN and changes #8 and #9's design.
3. **The owners that are missing:** ADC grants, the IF-13 controller, CNI's packages and AEV readiness with a trust
   basis. Each is an L hidden inside an action row.
4. **Whether the typed tools route through O-01** (±2–4 PRs, and whether steps 4 and 6 can ever read as landed).
5. **The target wire:** 0.8 or 0.9, and A-56 or the other amendments since (A-49, A-51 to A-58), which add rules to
   the same actions.
6. **The G3 owner-enum amendment,** which is design time and a reinstall on every host.


### A.6 What would feel different once the V-01 subset lands

**For the operator,** on a host where G3 counts:
- **Open.** `aew opencode` opens the confirmer once, showing exactly which Lead, harness, model and profile are being
  attached. One PIN, and the Lead is up, with no resume code, credential or seat command. Under the A.1.5
  recommendation, later sessions on the same setup ask nothing.
- **Plan and publish.** The plan and the publish each arrive in the confirmer, rendered from records, not as a Lead's
  chat question. The operator reads the exact plan revision, package digest and readiness, enters the PIN, and that is
  the decision (G3-03, G3-04). Nothing reaches `main` without it.
- **Reopen.** From a fresh terminal it is one PIN (or none, under the standing option), and the Lead says where things
  stand from the attention, waiting and continuation reads. The "type this code" prompt goes, and so does `takeover`
  as the usual recovery.
- **Changing a model.** A typed setting in the confirmer, old value to new, with no YAML, no acquire and no exported
  credential (I6-04).
- **A steering raise** is unchanged, a PIN, and persists per project once A-56 is built.
- **Every action has a receipt and an owner record** that the dashboard and `aew read` can show, and a refusal says
  which owner refused, under which reason code.
- **The cost:** the confirmer appears 3 to 4 times in a fix-and-reopen day where it appears 0 to 1 times today.

**For the Lead:**
- **One door.** It proposes work, delegates a worker and continues work as its own session-origin actions. It cannot
  record the operator's plan or publish decision. It asks, and waits for the owner's observation, not the operator's
  chat word.
- **No `expect_rev` bookkeeping** once each target names its own version (I6-01b) and the carrier's key ledger makes a
  retry a lookup (A-24 SW-07). That depends on E329 landing the same way (burn-down C4).
- **Refusals carry an owner reason and a reason code** from one fail-closed map, instead of an engine exception's text.
- **Reopen hands it the waiting, attention and continuation reads** from qualified owners, instead of a reconstructed
  `resume`.


### A.7 A proposed order of increments

The burn-down's alpha track and strict items 1 to 9 come first (the burn-down's Q7: the wire track "after alpha when we
align the wires").

| Inc | What | Steps it lands (oracle) | Checkpoint for the strict cases |
|---|---|---|---|
| 0 | **Design rulings:** the ceremony classes (A.1.6), the G3 owner enum, 0.8 or 0.9, the typed-tools route, the assessor's row | — | — |
| 1 | The O-01 endpoint and carrier on the target registry, the key ledger, the refusal map, the conformance harness, **the oracle repointed** from STG-02 to the real registry | none | The oracle derives from the real carrier (every step's state unchanged) |
| 2 | SET_STEERING_MODE on the real route, the first protected owner (it already has one), with the G3 owner enum. **E356: STG-02 retired here**, and the G3 client's tests moved | 13 | No case alone; the steering variants lose one fallback |
| 3 | The D-01 producer: framework, then `attachments`, `attention`, `waiting` and `continuation-state` (ported) | part of 3 and 10 | — |
| 4 | The successor origin; ATTACH_LEAD with the HEB attachment record (F31) | 3 | V3's open, where its path reaches it |
| 5 | CREATE_PROPOSED_WORK and DECIDE_WORK_PROPOSAL (E351, Q8) | 4, 5 | — |
| 6 | The delegated-grant issuer and the ADC grant store; real CONTINUE_ELIGIBLE_WORK; DELEGATE_NEW_WORKER (A-52 adopted) | 6 | — |
| 7 | `work/{id}`, `assurance`, `resolve`, `packages` | 8 | — |
| 8 | APPROVE_INTEGRATION: CNI, AEV readiness with its trust basis, **the host assessor's record** | 7 | **V1's strict cases turn green**, given the burn-down's C9 and C11 for semantic-conflict and evidence-mismatch |
| 9 | REATTACH_LEAD (+ REAFFIRM, if Q-D2 says so) | 10 | **V2 turns green** (and `pin_reentries` loses the resume code) |
| 10 | ADOPT_MANIFEST_EDIT with IF-13's revisions and transitions | 12 | **V4 turns green**; the steering variants, with Inc 2 |
| 11+ | The other 32 actions, by class (A.1.6): the protective ones first, then the seat's, the judgments', the widening ones; then 0.9's eleven | — | — |


### A.8 Questions for the designer and the operator

Each is put as it would be asked, with its evidence.

**Ceremony (A.1)**
- **Q-C1 (designer, operator):** "Does `ATTACH_LEAD`'s protection mean 'originates from the operator's channel' or 'a
  fresh PIN each time'? If the former, may an attach consent stand per (project, host, harness, model, profile) until
  one changes, as A-56 made a raise stand, with A-32 L02's `FUNCTIONAL_UNQUALIFIED` association as the zero-ceremony
  fallback?" Evidence: A.1.2 (+1 PIN at every open); A-32 L02; A-56 SMP-X01.
- **Q-C2 (designer):** "Is a reattach on an unchanged basis a routine transition (ADC-02.l) that needs no new consent,
  as A04 already rules for child grants ('no new operator approval solely due to conversation change')?" Evidence:
  A.1.4; A-32 L03, A04.
- **Q-C3 (designer):** "For `DECIDE_WORK_PROPOSAL` and `APPROVE_INTEGRATION`, is the PIN in the confirmer the
  operator's decision itself, so that the Lead no longer asks in chat, and can `ADJUST_LEAD_AUTONOMY` ever carry a
  standing 'publish if clean' grant, or is every promotion 'spent with it' (I4)?" Evidence: `ledger.py:49-50`;
  `I4-PROFILE.md:96`; A-32 A09.
- **Q-C4 (operator):** "Under the threat model of 2026-10-19 (G3-01: 'Malicious code running as the operator's UID is
  outside the threat model'), which class in A.1.6 is G3 worth its cost for: seat, protective, judgment, widening?"
  Evidence: A.1.5.
- **Q-C5 (designer):** "The confirmer is a local window (G3-01) and a website session is never G3 (G3-13). How does the
  operator approve a protected action from the dashboard on another device, or from a phone?" Evidence: A.4.6.

**Scope and order**
- **Q-W1 (operator):** "Does the build target O-01 0.8 (42 actions, as STG-14 says) or 0.9 (53, which the contracts
  index calls the current selected command wire)?" Evidence: `docs/contracts/README.md`, the A-43 row; STG-14 Work.
- **Q-W2 (operator):** "Which of the 42 does V-01 need? This sizing finds 10: CONTINUE_ELIGIBLE_WORK, ATTACH_LEAD,
  REATTACH_LEAD, CREATE_PROPOSED_WORK, DECIDE_WORK_PROPOSAL, DELEGATE_NEW_WORKER, APPROVE_INTEGRATION,
  ADOPT_MANIFEST_EDIT, SET_STEERING_MODE, and REAFFIRM_ELIGIBLE_CHILD_GRANTS if Q-D2 says so. Are the other 32 after
  V-01?" Evidence: `oracle.py:96-130`.
- **Q-W3 (operator):** "After I-6, is the order of increments A.7's (the steering raise first on the real route, then
  open, ask and plan, work, result, publish, reopen, setting), or the oracle's step order?"
- **Q-O3 (operator):** "Once `REATTACH_LEAD` exists, does seat resume keep its confirmation code
  (`lead_ops.py:258-265`) for the case G3 does not count, or does it go?" Evidence: the burn-down's Q5 answer keeps it
  counted until REATTACH_LEAD lands; G3-11 forbids moving from G3 to the code once G3 is asked.
- **Q-O4 (operator):** "Does E331's terminal adopt and E164's `aew policy route` ship before I-6 and then give way to
  `ADOPT_MANIFEST_EDIT`, or wait for it?" Evidence: STG-14's F46.2 note ("supersedes this operator-session apply");
  E164 is on the Now list.

**What the contracts leave open**
- **Q-D1 (designer, operator):** "W09 is held until 'the host assessor's current capability assessment … is
  qualified' (A-51 AP5-01), and 'None exists today, for any profile'. The assessor (STG-26) has no register row. Which
  row builds it, and does V-01's strict V1 wait for it?" Evidence: A.2 row 31; E308 Notes.
- **Q-D2 (designer):** "Is `REAFFIRM_ELIGIBLE_CHILD_GRANTS` on V01-01's reopen step when work is running at the
  reopen?" Evidence: A.2 row 10; the burn-down's C7.
- **Q-D3 (designer):** "Do the Lead's typed tools submit through O-01 as the Lead's session origin (one admission
  path, as I6-06.f requires of the auto-runner), or stay engine calls?" Evidence: A.4.7.
- **Q-D4 (designer):** "Where does the O-01 route live (its own service, the dashboard server, or the operator
  endpoint), and what authenticates its recipient, since 'AEW has no session issuer yet'?" Evidence: A.4.1.
- **Q-D5 (designer):** "The pinned G3 wire's `ConsumeRequest.owner` allows four owners. Will A-26 gain WIS, CNI, AEV
  and R01, retiring the ADC label on SET_STEERING_MODE?" Evidence: A.4.2.
- **Q-R1 (designer, for the register):** "E181 lists 16 reads. The four STG-02 serves today (`waiting`,
  `continuation-state`, `runs/{execution_id}`, `owner-operations`) have no production row once E356 retires STG-02, and
  two are on V-01's reopen. Which row owns them?" Evidence: A.3.
- **Q-R2 (designer):** "CONTINUE_ELIGIBLE_WORK's refusal map lists only the delegation causes. HEB's own causes are
  gap STG02-BE-01. Does 0.9's erratum E-1 close it?" Evidence: `stg02/commands.py:68-72`.


### A.9 What was verified against the code (at `eece01e5`)

- **STG-14 (I-6), "Designed, not implemented": confirmed.** `git grep` finds none of the five I-6 types in `src/`
  except SET_STEERING_MODE's G3 bridge (`stg02/g3_overlay.py`, `harness/g3_adapter.py`). `git log --grep "I-6"` finds
  register commits only.
- **E181: confirmed open.** No D-01 producer exists outside STG-02's four routes.
- **E356: confirmed open.** `src/aew/stg02/` is present and is the G3 client's O-01 target (`g3client.py:59-60`).
- **E108: confirmed open.** The CLI has no `aew read` (the oracle's walk of the real parser).
- **E97 and E98: open.** The relay records outcomes and no usage (E97's note of 2026-11-24).
- **E351 and E335: open on `main`.** E335 is in flight as #597 (the burn-down's C1).
- **E331 and E164: open.** The CLI has `manifest adopt` and `settings show` only.
- **G3: built and counting.** It counts where the operator installed it (STG-14's 2026-11-10 line). The service and
  confirmer are in `g3/`, and the first bound action is the steering raise (`g3_adapter.py:37`).
- **The oracle at `eece01e5`:**
  - steps 1, 2 and 11 are built and step 9 is outside AEW;
  - ATTACH_LEAD and REATTACH_LEAD are "registry only";
  - CONTINUE_ELIGIBLE_WORK "reaches an owner" (fixture);
  - the other wire parts are "not built";
  - only `waiting` and `continuation-state` of step 10's reads are served.

### A.10 Corrections since the sizing

- **Erratum E-1:** 0.9's erratum E-1 closes STG02-BE-01, which answers Q-R2. It adds HEB's three reasons to
  CONTINUE_ELIGIBLE_WORK's map.
- **E108's `aew read`:** it is built (`src/aew/cli/read_commands.py`) and imports `aew.stg02.outage` and
  `aew.stg02.wire`, so E356 keeps them.
- **The oracle:** a landed step also needs the scripted operator's driver (F2), and the oracle reads one owner action
  from STG-02 only (F1, F3).
- **Q-W1:** answered by the operator on 2026-11-27: 0.9's envelope, 0.8's 42 admitted.
- **E181's "after I-6":** lifted by the operator on 2026-11-27, on its condition.
- **Q-D4's hosting half:** an implementation choice, recorded in an ADR with A2 and R1. Its recipient-authentication
  half stays with the designer.
- **The paid class:** a missing placement, not an unsatisfiable invariant (§9.1, C2).
