# The systems build board

Generated from [systems.yaml](systems.yaml). Do not edit; run `python tools/register.py render` (or `python tools/systems.py render`). Priority comes from [the register's Now list](future-work.md#1-now-the-milestones-and-the-gates-in-order). Count definition: FORMAT.md rule 1. Switch defaults are checked against the code's tables; board_state and built remain hand-kept. A PR that closes a row named in a slice, or changes what counts, re-runs `python tools/systems.py check` against current main before it merges (no merge queue).

## Totals

**on_and_used:** 4 — SYS-17, SYS-20, SYS-37, SYS-38

**awaiting_signoff (built, awaiting your sign-off):** 10 — SYS-08, SYS-09, SYS-13, SYS-19, SYS-32, SYS-39, SYS-40, SYS-47, SYS-48, SYS-53

**partly_built:** 16 — SYS-01, SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-07, SYS-11, SYS-15, SYS-16, SYS-18, SYS-21, SYS-25, SYS-43, SYS-45, SYS-51

**built_off:** 3 — SYS-12, SYS-14, SYS-23

**built_not_wired:** 0 — none

**staged:** 2 — SYS-22, SYS-27

**designed_only:** 16 — SYS-24, SYS-26, SYS-28, SYS-29, SYS-30, SYS-31, SYS-33, SYS-34, SYS-35, SYS-36, SYS-41, SYS-42, SYS-46, SYS-49, SYS-50, SYS-52

**Waiting on your sign-off:** 10 — SYS-08, SYS-09, SYS-13, SYS-19, SYS-32, SYS-39, SYS-40, SYS-47, SYS-48, SYS-53

**Limit's count / wip_limit:** 9 / 12 — SYS-02, SYS-04, SYS-05, SYS-06, SYS-07, SYS-22, SYS-43, SYS-45, SYS-51

**Switch defaults not read from the code:** 4 — SYS-02, SYS-04, SYS-11, SYS-12 — SYS-02: containment.mode (execution policy); SYS-04: steering.mode; SYS-11: policy.pricing (project manifest); SYS-12: MODES["O-CMD"] and MODES["O-SECRET"] in tests/helpers/discovery/modes.py (mirrored in vertical-uat.md §8.3; a test holds the two equal). A test-tooling constant outside the checked policy tables, so its default stays hand-kept

**Hand-kept wiring (no reference record):** 5 — SYS-04, SYS-06, SYS-07, SYS-08, SYS-22 — SYS-04: lead_text; SYS-06: lead_text; SYS-07: pack; SYS-08: lead_text; SYS-22: pack

## Finish and switch on soon

**Members:** 20 — SYS-02, SYS-05, SYS-09, SYS-22, SYS-42, SYS-43, SYS-45, SYS-13, SYS-04, SYS-07, SYS-08, SYS-19, SYS-30, SYS-32, SYS-39, SYS-40, SYS-46, SYS-47, SYS-48, SYS-53

### SYS-02 — Agent containment (the Linux core; its follow-ons are SYS-49's)

**Board state:** partly_built

**Who:** designer (E118's mechanism), then Lead (E118)

**Now:** 5

**Own slices left:** 1 — E118: the Lead's server moved out of the shell's reach, after the designer's choice of mechanism (on the Now list, before first use). Its other two parts are built: every contained start clears the Lead's saved permissions, and the login seed checks the credential table's columns first (E118's note of 2026-11-24) (E118) — **Next:** E118: the Lead's server moved out of the shell's reach, after the designer's choice of mechanism (on the Now list, before first use). Its other two parts are built: every contained start clears the Lead's saved permissions, and the login seed checks the credential table's columns first (E118's note of 2026-11-24) — E118 — 1 small PR (estimate; BOARD v2 §0), after the designer's choice

**Switch:** containment.mode (execution policy) — default: required on Linux; allow_weaker elsewhere, Windows included, unless required is set explicitly, which then refuses every launch — not read from the code

**Wired:** cli:harness launch, cli:check run, cli:opencode, cli:lead session, cli:doctor, cli:harness status

### SYS-05 — Harness currency on the pin (OpenCode); qualification and further adapters are SYS-50's

**Board state:** partly_built

**Who:** Lead (H-1); operator (H-1's live re-probe and the real default-flow run)

**Now:** 6

**Own slices left:** 1 — H-1: the C1 compaction re-probe on the pinned OpenCode 2.2.6 (its TESTED_VERSIONS entry and token_semantics row are in place; no evidence the re-probe ran) (E35) — **Next:** H-1: the C1 compaction re-probe on the pinned OpenCode 2.2.6 (its TESTED_VERSIONS entry and token_semantics row are in place; no evidence the re-probe ran) — E35 — 1-2 PRs (estimate)

**Wired:** cli:harness launch, cli:harness config, cli:opencode, cli:doctor

### SYS-09 — Capability register (CAP-1 and the base bundle)

**Board state:** awaiting_signoff

**Who:** operator (the real contained run with all six tools, then the sign-off)

**Now:** 7

**Own slices left:** 0 — none — **Next:** none

**Wired:** cli:capability list, cli:capability check, cli:capability import, cli:capability add, cli:capability remove, cli:capability host-copies, cli:doctor

### SYS-22 — Specialist skills delivered to runs and the Lead

**Board state:** staged

**Who:** Lead

**Now:** 24

**Own slices left:** 1 — the Lead's skills (E161), built: the `lead` list and its skills, delegation-handoffs among them, the per-mode rules, a copy in a folder of each start's own, the Lead's text and the exposed skills in its record. Left: the operator's live checks, tests/live/test_lead_skills_live.py on Windows (the absolute `skills` path, a colliding id, the listing's and a loaded body's cost, and which skills were loaded) and a real Lead run; the Lead's record does not count loads, since its server ends with its TUI, so the live test counts them (E161) — **Next:** the Lead's skills (E161), built: the `lead` list and its skills, delegation-handoffs among them, the per-mode rules, a copy in a folder of each start's own, the Lead's text and the exposed skills in its record. Left: the operator's live checks, tests/live/test_lead_skills_live.py on Windows (the absolute `skills` path, a colliding id, the listing's and a loaded body's cost, and which skills were loaded) and a real Lead run; the Lead's record does not count loads, since its server ends with its TUI, so the live test counts them — E161 — no build PR; the operator's live session

**Wired:** pack

### SYS-42 — Lead small change (operator-approved, light review at class 1)

**Board state:** designed_only

**Who:** Lead

**Now:** 30

**Own slices left:** 2 — the Lead change stage (item 43's stage) and its class 1 shape; the operator decision and fingerprint; the refusal list and check inputs; the export-and-check; the view rendering; containment widened to the route (CS-4 addendum 14); the light review and the operator-requested review ride in these PRs (small-changes design §2, §6, §8) (E159); first configuration (E119's `aew init`) proposes `review_triggers` entries with their levels and each check's `inputs:` list, for the operator to adopt (small-changes design §2, §8) (E166) — **Next:** the Lead change stage (item 43's stage) and its class 1 shape; the operator decision and fingerprint; the refusal list and check inputs; the export-and-check; the view rendering; containment widened to the route (CS-4 addendum 14); the light review and the operator-requested review ride in these PRs (small-changes design §2, §6, §8) — E159 — 4-5 PRs (estimate; the designer's reading, small-changes design §6)

**Wired:** none

### SYS-43 — Plan assessment gate and planner staffing

**Board state:** partly_built

**Who:** Lead

**Now:** 31

**Own slices left:** 2 — the gate on the class paths and its dispatch refusal, the planner-review credit, the findings' source kind with the waiver refusal, and the operator's dismissal (E160); the Lead's staffing text (one passage beside E127's staffing line) and engine enforcement of `requires_distinct_invocation_from` (E160) — **Next:** the gate on the class paths and its dispatch refusal, the planner-review credit, the findings' source kind with the waiver refusal, and the operator's dismissal — E160 — about 1 PR (estimate; same source)

**Wired:** none

### SYS-45 — Branch review and document work (ref_review, technical_writer)

**Board state:** partly_built

**Who:** Lead

**Now:** 35

**Own slices left:** 2 — the site's half of the raw-body read (skills design (c)); the CLI half is built, `aew record body` with its surface-map entry, for a work unit's record, an evidence record, a plan revision and a decision record (E170's notes of 2026-11-26 and 2026-11-27) (E170); a review of a named ref: ref pinning and merge-base at dispatch, the `ref_review` kind and its freshness, the archetype's new kind, the `branch_reviewer` card and its skill-fit check (skills design (d)) (E168) — **Next:** the site's half of the raw-body read (skills design (c)); the CLI half is built, `aew record body` with its surface-map entry, for a work unit's record, an evidence record, a plan revision and a decision record (E170's notes of 2026-11-26 and 2026-11-27) — E170 — 1 small PR, the web developer's (estimate; the designer's reading, skills design (e))

**Wired:** none

### SYS-13 — Lead-worker coordination messaging

**Board state:** awaiting_signoff

**Who:** operator (MS7, the real recorded exchange and sign-off)

**Now:** 40

**Own slices left:** 1 — MS7: operator real-provider qualification and sign-off (E175) — **Next:** MS7: operator real-provider qualification and sign-off — E175 — not sized

**Switch:** coordination.messaging — default: disabled (a new project: enabled) — checked against src/aew/policy/execution.py:STRING_SWITCHES

**Wired:** tool:message_send, cli:message thread, cli:message list, cli:message unseen, cli:message lost, cli:harness send

### SYS-04 — Steering (Crawl/Walk/Run), operator endpoint and notifier

**Board state:** partly_built

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 1 — The scheduler on: the measured RUN trial, folded into Session B (the operator, 2026-11-11: "yeah thats the better plan that sounds like session B SHOULD be validating that"); PR 4 has merged (E228) — **Next:** The scheduler on: the measured RUN trial, folded into Session B (the operator, 2026-11-11: "yeah thats the better plan that sounds like session B SHOULD be validating that"); PR 4 has merged — E228 — a measured trial inside Session B (estimate)

**Switch:** steering.mode — default: crawl — not read from the code

**Wired:** tool:steering, cli:operator serve, cli:operator ping, cli:lead mode raise, cli:lead mode lower, lead_text

### SYS-07 — Project maps in agents' context

**Board state:** partly_built

**Who:** Lead (F22.2 and F22.3 after their benchmark); decided by the operator

**Now:** not on the Now list

**Own slices left:** 1 — F22.2 and F22.3, the semantic layer and sibling indexes, after their benchmark (census: P-DEC-03) (F22.2) — **Next:** F22.2 and F22.3, the semantic layer and sibling indexes, after their benchmark (census: P-DEC-03) — F22.2 — many PRs, unsized (estimate)

**Switch:** maps.pack_slices — default: off (a new project: structural) — checked against src/aew/policy/execution.py:STRING_SWITCHES

**Wired:** cli:map generate, cli:map select-architecture, cli:map show, cli:map diff, dashboard:/maps, dashboard:/maps/structural, dashboard:/maps/structural/{root}, dashboard:/maps/structural/{root}/inputs, dashboard:/maps/diff, pack, tool:resume

### SYS-08 — Governed stages on the typed Lead surface (StageIntent) and dispositions

**Board state:** awaiting_signoff

**Who:** operator (the real Lead run, then the sign-off)

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Wired:** cli:lead mcp, cli:lead tool, cli:stage continue, cli:stage abandon, cli:work dispose, lead_text

### SYS-19 — Validation evidence completeness (artifact digests, coverage disclosure, readiness, remote provider)

**Board state:** awaiting_signoff

**Who:** operator (adopt the project's declaration, exercise the real flow and sign off)

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Wired:** cli:check run, cli:integrate validate, cli:status, cli:doctor, cli:harness status, cli:harness wait, dashboard:/evidence/{id}

### SYS-30 — Research minimum slice, CNI links and PoCs as linked Tickets

**Board state:** designed_only

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 2 — File the build row (BOARD v2 §2: no row yet), with the slice's file scope so its lanes can be computed (row owed); The inquiry record and its completion by answer (A-40), the link-record store with five kinds listed from both ends (A-41), the PoC as a linked Ticket proposal (A-50 PL01), on I-7's commands (O-01 0.9) and the shared read wire, after I-6 (row owed) — **Next:** File the build row (BOARD v2 §2: no row yet), with the slice's file scope so its lanes can be computed — row owed — part of 1 register PR (estimate)

**Wired:** none

### SYS-32 — Independent outage reader (aew read)

**Board state:** awaiting_signoff

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 1 — G4: O02-Q01 to O02-Q08 run host by host on Linux once containment holds there (E108) — **Next:** G4: O02-Q01 to O02-Q08 run host by host on Linux once containment holds there — E108 — a per-host run, no PR (estimate)

**Wired:** cli:read

### SYS-39 — Integration pipeline (ADR-0004 queue, custody worker, workspaces)

**Board state:** awaiting_signoff

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Switch:** gates.mutating_concurrency — default: 2 — checked against src/aew/knowledge/manifest.py:DEFAULT_GATES

**Wired:** cli:integrate prepare, cli:integrate publish, cli:integrate validate, cli:integrate reconcile, cli:integrate defer, cli:integrate reorder, cli:integrate requeue, cli:integrate custody, cli:integrate breaker status, cli:integrate breaker reset, tool:integration_publish, tool:ticket_prepare

### SYS-40 — Lead reports (report_write)

**Board state:** awaiting_signoff

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Wired:** tool:report_write, cli:report show

### SYS-46 — The V-01 command wire after I-6 (I-7's O-01 0.9, and the I-1 to I-5 commands in O-01 0.7 and 0.8)

**Board state:** designed_only

**Who:** Lead files the rows (V-01 is placed); builders after I-6

**Now:** not on the Now list

**Own slices left:** 2 — File the rows: one per increment after I-6, in the V-01 milestone's order (I-6, then I-7) (row owed); I-7's commands at O-01 0.9, and the I-1 to I-5 commands the move to 0.8 carries (row owed) — **Next:** File the rows: one per increment after I-6, in the V-01 milestone's order (I-6, then I-7) — row owed — no PR

**Wired:** none

### SYS-47 — Relay client certificate (E123)

**Board state:** awaiting_signoff

**Who:** operator (AIR-85, then the sign-off)

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Wired:** cli:doctor

### SYS-48 — Build board and systems generator (E182)

**Board state:** awaiting_signoff

**Who:** operator (the sign-off)

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Wired:** none

### SYS-53 — Per-operation revision check (replacing the project-wide expect_rev)

**Board state:** awaiting_signoff

**Who:** operator (the real run, then the sign-off)

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Wired:** none

## Finish, with more to build

**Members:** 8 — SYS-29, SYS-41, SYS-51, SYS-06, SYS-24, SYS-31, SYS-33, SYS-34

### SYS-29 — Resource, model and host policy (wire increment I-6)

**Board state:** designed_only

**Who:** Lead (BOARD v2 §2, on the Now list); its brief is owed

**Now:** 15

**Own slices left:** 4 — Retire the STG-02 producer when I-6's real O-01 route lands, and move the G3 client's tests to the real route (E356); Move the code's O-01 command wire from 0.2 to 0.8 (I-7's 0.9 follows, BOARD v2 §2: 'O-01 0.2 to 0.8/0.9') (STG-14); The nine rows' actions and handlers across their owners (IF-13, the resource policy issuer, R-01), with surface-map entries; P11's migration half and U10 wait for U-01 (STG-14); Provider profiles declare rate_basis (which counters the limiter counts) and its window; I-6's ceilings in that unit and period (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 1) (STG-14) — **Next:** Retire the STG-02 producer when I-6's real O-01 route lands, and move the G3 client's tests to the real route — E356 — 1 PR (estimate), with I-6's route

**Wired:** none

### SYS-41 — Lead consult (spawn a non-mutating agent for the Lead's own question)

**Board state:** designed_only

**Who:** Lead

**Now:** 28

**Own slices left:** 5 — consult mode, its gate path, the tool, `consult_show` with the ingest, and the wake (consult design, Placement, PR 1; A-58 CL-R03) (E158); the bounds and the allow-list, the isolation tests, the resume lists and the Lead's text (consult design, Placement, PR 2) (E158); `aew policy model allow <provider/model>` and a profile add, operator-decided, with their surface-map entries (consult design, later pointer); first configuration proposing a profile per named provider (E164); an operator-requested review or verification on a consult or branch review: the obligation-adding request record, its non-waivable mark, its owed dispatch in `next`, the operator's removal (small-changes design §8) (row owed); `--model` held to profiles plus the allow-list, always bounded (E165) — **Next:** consult mode, its gate path, the tool, `consult_show` with the ingest, and the wake (consult design, Placement, PR 1; A-58 CL-R03) — E158 — 1 PR (estimate; the designer's reading, consult design Placement: 2 PRs in all)

**Wired:** none

### SYS-51 — Typed surface follow-ons (worker-side role servers, typed Lead rows, Lead text fixes)

**Board state:** partly_built

**Who:** operator (placing F15.3 and F15.8 after first use, and the frozen Lead text work); then Lead

**Now:** 33

**Own slices left:** 9 — FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F15.3: the aew-run role server over the existing run bridge (whoami, check.run and typed submit as in-sandbox MCP tools; the supervisor keeps the credential). Held in HOLD-06 until the designer's match and the operator's placement (F15.3); F15.8's map reads, unfrozen by the operator after E293 (2026-11-25: "unfreeze 15.8 after E293"): the shared query module, `aew map search` and the worker bridge rows map.show and map.search are built (the mapping series' PR A), and so is the Lead's typed map tool under maps.reads (PR A2); outline, symbol, callers and callees over F22.4's facts (PR C) remain (F15.8); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F15.8's other items: evidence.show, check.suggest, tools.presentation and the in-sandbox aew-run server (F15.8); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): aew-knowledge as its own capability namespace over the shared transport library: part of F15.3's text, so held with it in HOLD-06; what it serves waits on K-01's increment (F15.3); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): typed Lead rows for maps, history, settings, usage and g3, reachable today only untyped through the shell rule `aew *` (row owed); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): BOARD v2 §4 loose end and §6 stale text: drop the catalog's unused DESIGNED status and correct the contract.py docstring that says rows stay DESIGNED (row owed); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): The Lead's request-economy text remains owed after E139's worker-pack fixes (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 3) (E162); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): Lead text fixes (E162); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): a typed `plan accept` on the Lead's MCP server, with its surface-map entry (E163) — **Next:** FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F15.3: the aew-run role server over the existing run bridge (whoami, check.run and typed submit as in-sandbox MCP tools; the supervisor keeps the credential). Held in HOLD-06 until the designer's match and the operator's placement — F15.3 — 1-2 PRs (estimate, census)

**Switch:** maps.reads — default: off (a new project: structural) — checked against src/aew/policy/execution.py:STRING_SWITCHES

**Wired:** cli:map search

### SYS-06 — Typed agent surfaces (the Lead's catalog and transports)

**Board state:** partly_built

**Who:** Lead (E231's next part, E233, E367, E368)

**Now:** 44

**Own slices left:** 4 — The Lead's tool budget, decided before E158 (E231); The Lead's exits: four of E133's eleven dead ends are left, each waiting on a decision (the plan route, the wait at RUNNING, the queue disposition), and a project with no execution profile offers no dispatch. The lands guard is E233's other pull request, in the row's notes (E233); The Lead's system text and tool list made true and smaller, with a Lead-text truth test, after the guide's core plus pointers (the operator, 2026-11-25) (E367); Worker packs as a core plus pointers, with a size budget and the rest of the pack-truth extensions (the operator, 2026-11-25). Its false lines are fixed, with their truth tests (the operator, 2026-11-26: "ship truth fixes now"). The Lead's plan, not an operator ruling: the rewrite is written as a draft and held unmerged until it can be measured; whether it waits for the refined F19 is the operator's to confirm (E368) — **Next:** The Lead's tool budget, decided before E158 — E231 — a decision, then 0-1 PR (estimate)

**Wired:** cli:lead mcp, cli:lead tool, lead_text

### SYS-24 — Lead attachment lifecycle (Q12), custodian outliving the Lead, lease-expiry takeover

**Board state:** designed_only

**Who:** designer (E129's design, the lease-expiry ADR and the HOLD-06/HOLD-17 match), then operator (places E129 and the held members), then Lead; after first use (BOARD v2 §3)

**Now:** not on the Now list

**Own slices left:** 6 — Correct the F31 note, which describes an attachment grant and automatic reattach the code does not have (BOARD v2 §6) (row owed); E129's design: starting AEW in one step (not yet designed) (E129); F31 / F18.5 / F18.7 / F18.9: attachment record and states, aew open and aew close, the custodian surviving the attachment's end, detached-child disposition (F31); E50 inactivity expiry (E50); Lease-expiry automatic takeover: a future ADR (ambiguity report A2) before any build (row owed); A context-aware Lead hand-off to a fresh session with resume; the threshold computed from the declared limit, window and request rate (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 4) (row owed) — **Next:** Correct the F31 note, which describes an attachment grant and automatic reattach the code does not have (BOARD v2 §6) — row owed — part of the Lead's §6 docs PR (estimate)

**Wired:** none

### SYS-31 — Bounded unattended mission and the relay's meter

**Board state:** designed_only

**Who:** Lead; operator for E98's paid live runs (BOARD v2 §2)

**Now:** not on the Now list

**Own slices left:** 3 — E97: the relay's meter, per-provider request and response usage parsing and binding each paid call to its operation (after I-6); the meter's unit is the profile's declared rate_basis, all counters when undeclared (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 1) (E97); E98: R-01's qualification of the paid class on a host and provider, judged by live paid-provider runs (BOARD v2 §2: operator for E98's paid live runs) (E98); The mission: preflight, spend cap, held questions and report, built on the steering Run envelope and I-7's mission commands (row owed) — **Next:** E97: the relay's meter, per-provider request and response usage parsing and binding each paid call to its operation (after I-6); the meter's unit is the profile's declared rate_basis, all counters when undeclared (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 1) — E97 — 2-3 PRs (estimate)

**Wired:** none

### SYS-33 — Offline install bundle, release signing, upgrade and recovery

**Board state:** designed_only

**Who:** designer (E99's design), then Lead; operator places F18.3 and D2 out of HOLD-17

**Now:** not on the Now list

**Own slices left:** 3 — E99's design: the one manifest, the per-target build and the guided install sequence, naming how F18.3 and D2 are absorbed at HOLD-17's exit (E99); E99's build: the bundle, the preflight, the root step calling g3/install.sh, the PIN step and the self-tests (E99); U-01 (A-46): per-release format declarations, refusal by name, operator-terminal migration with a recorded restore point, rollback and move (row owed) — **Next:** E99's design: the one manifest, the per-target build and the guided install sequence, naming how F18.3 and D2 are absorbed at HOLD-17's exit — E99 — a design, no PR (estimate)

**Wired:** none

### SYS-34 — Checked launch briefs

**Board state:** designed_only

**Who:** operator places E154 (BOARD v2 §3); then Lead

**Now:** not on the Now list

**Own slices left:** 3 — The brief checker (a bounded fact process with planted controls) passing LB01-Q01 to Q22, with the execution policy's bounds (LB01-02.d) (E154); The `brief` group's registry lines in their own PR, before F4's S3 binds evidence to a registry identity (E154); The pre-F4 `brief` correction and the release adding the two lists, with its format value and U01-05 migration step (needs U-01's migration path) (E154) — **Next:** The brief checker (a bounded fact process with planted controls) passing LB01-Q01 to Q22, with the execution policy's bounds (LB01-02.d) — E154 — 1-2 PRs (estimate)

**Wired:** none

## The operator's open questions

**Members:** 1 — SYS-26

**Decided:** 38 — SYS-01, SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-07, SYS-08, SYS-09, SYS-11, SYS-12, SYS-13, SYS-14, SYS-15, SYS-18, SYS-19, SYS-20, SYS-21, SYS-22, SYS-23, SYS-24, SYS-25, SYS-29, SYS-34, SYS-37, SYS-39, SYS-40, SYS-41, SYS-42, SYS-43, SYS-45, SYS-47, SYS-48, SYS-49, SYS-50, SYS-51, SYS-52, SYS-53

### SYS-26 — Resource and progress supervision (stall detection, run health, weak-worker continuity, dynamic scheduler)

**Decision:** "Freezes in §4 that touch your past decisions (F19, U1)" (BOARD v2 §3); BOARD v2 §4: "freeze; pull U1's stall detection forward if first use repeats the 20-minute hang", decided by the operator or the Lead (placement out of HOLD-15).

## Done

**Members:** 4 — SYS-17, SYS-20, SYS-37, SYS-38

### SYS-17 — Transaction outbox and its consumers

### SYS-20 — G3 trusted operator origin (approvals)

### SYS-37 — Register of weaker contexts (E112, G3 addendum 7)

### SYS-38 — ADR-0011 archival and history

## Not counted

**Members:** 19 — SYS-12, SYS-01, SYS-03, SYS-11, SYS-14, SYS-15, SYS-16, SYS-18, SYS-21, SYS-23, SYS-25, SYS-26, SYS-27, SYS-28, SYS-35, SYS-36, SYS-49, SYS-50, SYS-52

**SYS-12 — Discovery layer, D2 (output and text rules):** freeze

**SYS-01 — Evaluation instrument (F19, M4-H):** freeze

**SYS-03 — Read-only operator dashboard (server side):** keep

**SYS-11 — Run cost and usage ledger (with live usage meter):** freeze

**SYS-14 — Knowledge system (Arm B raw-history search; M6b capture, admission and recall):** freeze

**SYS-15 — Operator settings surface and fresh-project configuration:** cut

**SYS-16 — Plan assurance before mutating dispatch (ASSURED):** keep

**SYS-18 — Ticket revisions:** freeze

**SYS-21 — Operator attention (attention spine, observability, fact-owner registry, blocked-on-you):** freeze

**SYS-23 — Declared-but-unenforced policy and role-card fields:** freeze

**SYS-25 — Provider gateway, mutual-TLS client certificate and model-diverse routing:** freeze

**SYS-26 — Resource and progress supervision (stall detection, run health, weak-worker continuity, dynamic scheduler):** freeze

**SYS-27 — Backlog import (SPT remediation backlog):** keep

**SYS-28 — Cross-feature integration activation and plan-driven child materialization:** keep

**SYS-35 — Operator-approved exact-commit push, field diagnostics and SCM/Jira enforcement:** keep

**SYS-36 — Build/test impact analysis (F30):** keep

**SYS-49 — Containment follow-ons (Windows containment, CS-4 addenda 12 to 14, a headless contained Lead):** keep

**SYS-50 — Harness qualification and further adapters (E35's seams, H-2, H-3, rate-limit resilience, F24):** keep

**SYS-52 — Coordination follow-ons (a typed harness_interrupt, the presentation policy):** keep
