# The systems build board

Generated from [systems.yaml](systems.yaml). Do not edit; run `python tools/register.py render` (or `python tools/systems.py render`). Priority comes from [the register's Now list](future-work.md#1-now-the-milestones-and-the-gates-in-order). Count definition: FORMAT.md rule 1.

## Totals

**on_and_used:** 3 — SYS-17, SYS-38, SYS-39

**partly_built:** 18 — SYS-01, SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-08, SYS-09, SYS-11, SYS-13, SYS-15, SYS-16, SYS-18, SYS-19, SYS-20, SYS-21, SYS-25, SYS-48

**built_off:** 4 — SYS-07, SYS-12, SYS-14, SYS-23

**built_not_wired:** 2 — SYS-10, SYS-37

**staged:** 2 — SYS-22, SYS-27

**designed_only:** 19 — SYS-24, SYS-26, SYS-28, SYS-29, SYS-30, SYS-31, SYS-32, SYS-33, SYS-34, SYS-35, SYS-36, SYS-40, SYS-41, SYS-42, SYS-43, SYS-44, SYS-45, SYS-46, SYS-47

**Limit's count / wip_limit:** 14 / 12 — SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-07, SYS-08, SYS-09, SYS-13, SYS-19, SYS-20, SYS-22, SYS-37, SYS-48 (reported, not enforced)

## Finish and switch on soon

**Members:** 11 — SYS-47, SYS-40, SYS-42, SYS-44, SYS-48, SYS-07, SYS-30, SYS-32, SYS-37, SYS-39, SYS-46

### SYS-47 — Relay client certificate (E123)

**Board state:** designed_only

**Who:** Lead (E99 is adopted as A-55, which names E123 as the provider-access owner); operator for the live AIR-85 qualification

**Now:** 13

**Own slices left:** 2 — **Next:** E123: certificate, key and CA fields in the execution policy schema, the client certificate loaded in the relay's TLS context per upstream, mask-and-refuse at launch, no-relay refusal, throwaway-CA tests, and a 429 measurement against a local fake upstream (on the Now list) — E123 — 1-2 PRs (estimate)

### SYS-40 — Lead reports (report_write)

**Board state:** designed_only

**Who:** Lead

**Now:** 27

**Own slices left:** 1 — **Next:** report_write: the tool, the report record kind and its store, the resolver refusals and pack exclusion, the size and count bounds, the show command and the site view, the label, and the Lead's text (small-changes design §4; first in the alpha list, §7 item 5) — E157 — 1 PR (estimate; the designer's reading, small-changes design §6)

### SYS-42 — Lead small change (operator-approved, light review at class 1)

**Board state:** designed_only

**Who:** Lead

**Now:** 30

**Own slices left:** 2 — **Next:** the Lead change stage (item 43's stage) and its class 1 shape; the operator decision and fingerprint; the refusal list and check inputs; the export-and-check; the view rendering; containment widened to the route (CS-4 addendum 14); the light review and the operator-requested review ride in these PRs (small-changes design §2, §6, §8) — E159 — 4-5 PRs (estimate; the designer's reading, small-changes design §6)

### SYS-44 — Lead skills (a lead list in the skill manifest; no MCP servers in the alpha)

**Board state:** designed_only

**Who:** Lead

**Now:** 32

**Own slices left:** 2 — **Next:** the Lead's skills: the `lead` list, per-mode rule lists in `lead_config`, the records and cost measures, the Lead's text and the live tests (skills design (a)); after E127 — E161 — 1 PR (estimate; the designer's reading, skills design (e))

### SYS-48 — Build board and systems generator (E182)

**Board state:** partly_built

**Who:** Lead

**Now:** 39

**Own slices left:** 1 — **Next:** E182 PR 3: state from the code (switch defaults, wired against the as-built reference and the Lead's catalog) and the N = 12 check — E182 — 1 PR (estimate)

### SYS-07 — Project maps in agents' context

**Board state:** built_off

**Who:** Lead (1-2 PRs after first use); decided by the operator

**Now:** not on the Now list

**Own slices left:** 3 — **Next:** maps.pack_slices on for all cards (operator, 2026-11-06, design workspace record 2026-11-06-operator-board-decisions-concurrency-steering-maps-knowledge.md, item 3); each card's added pack size and tokens recorded, not a gate (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 3) — E62 — 1-2 PRs (estimate)

**Switch:** maps.pack_slices

### SYS-30 — Research minimum slice, CNI links and PoCs as linked Tickets

**Board state:** designed_only

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 2 — **Next:** File the build row (BOARD v2 §2: no row yet), with the slice's file scope so its lanes can be computed — row owed — part of 1 register PR (estimate)

### SYS-32 — Independent outage reader (aew read)

**Board state:** designed_only

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 2 — **Next:** E108: the aew read command over the store, reusing the D-01 wire's stamps without the server; the eight served reads not yet built anywhere; the non-writer declaration and tests; the surface-map entry — E108 — 2-3 PRs (estimate; BOARD v2 §2)

### SYS-37 — Register of weaker contexts (E112, G3 addendum 7)

**Board state:** built_not_wired

**Who:** Lead, with G3-C

**Now:** not on the Now list

**Own slices left:** 0 — **Next:** none

### SYS-39 — Integration pipeline (ADR-0004 queue, custody worker, workspaces)

**Board state:** on_and_used

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 2 — **Next:** The offer that switches an existing project's gates.yaml to the default, at the operator's terminal, which replaces the migration — F10 — 1 PR (estimate)

**Switch:** gates.mutating_concurrency

### SYS-46 — The V-01 command wire after I-6 (I-7's O-01 0.9, and the I-1 to I-5 commands in O-01 0.7 and 0.8)

**Board state:** designed_only

**Who:** Lead files the rows (V-01 is placed); builders after I-6

**Now:** not on the Now list

**Own slices left:** 2 — **Next:** File the rows: one per increment after I-6, in the V-01 milestone's order (I-6, then I-7) — row owed — no PR

## Finish, with more to build

**Members:** 19 — SYS-02, SYS-05, SYS-09, SYS-19, SYS-06, SYS-20, SYS-29, SYS-22, SYS-08, SYS-41, SYS-43, SYS-45, SYS-03, SYS-04, SYS-13, SYS-24, SYS-31, SYS-33, SYS-34

### SYS-02 — Agent containment (Linux core on; Windows backend and follow-ons)

**Board state:** partly_built

**Who:** Lead (E118 on the Now list; E100, E92 at Internal alpha; E113 to place); operator places F48 out of HOLD-06

**Now:** 5

**Own slices left:** 12 — **Next:** E118: the contained Lead's saved permissions cleared at start, and the Lead's server moved out of the shell's reach (on the Now list, before first use) — E118 — 1 small PR (estimate; BOARD v2 §0)

**Switch:** containment.mode (execution policy)

### SYS-05 — Harness currency and further harness adapters

**Board state:** partly_built

**Who:** Lead (E35's probe; H-1 to H-3 after CAP-1 PR 3); operator places E149, and E150 follows it; F24 leaves HOLD-06 after the designer's match, then the operator places it (BOARD v2 §3: after first use, unless 429s recur)

**Now:** 6

**Own slices left:** 10 — **Next:** FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): Refuse a launch with no provider key, close the Lead's OpenCode provider, and Lead permission tightening (E156) — E156 — 1 PR (estimate)

### SYS-09 — Capability register (CAP-1 and the base bundle)

**Board state:** partly_built

**Who:** Lead

**Now:** 7

**Own slices left:** 5 — **Next:** The owed lines from CAP-1 PR 2's review: the agent system-text line naming a missing tool, the Lead's results line, the consent prompt, `aew capability fetch` and the setup fetch — STG-15 — 1-2 PRs (estimate)

### SYS-19 — Validation evidence completeness (artifact digests, coverage disclosure, readiness, remote provider)

**Board state:** partly_built

**Who:** Lead (E120, E125); designer for E153's ruling; designer or operator for the two loose ends (BOARD v2 §4)

**Now:** 9

**Own slices left:** 4 — **Next:** E120: what its first PR left owed: the record's section 2 (what a run went without), and E243's project-owned source for the two lists its record now says are not known — E120 — 1-2 PRs (estimate)

### SYS-06 — Typed agent surfaces (the Lead's catalog and transports; role-side MCP servers)

**Board state:** partly_built

**Who:** operator (placing F15.3 and F15.8 out of HOLD-06, after the designer's match); then Lead. Lead for the DESIGNED-status loose end

**Now:** 11

**Own slices left:** 11 — **Next:** FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F15.3: the aew-run role server over the existing run bridge (whoami, check.run and typed submit as in-sandbox MCP tools; the supervisor keeps the credential). Held in HOLD-06 until the designer's match and the operator's placement — F15.3 — 1-2 PRs (estimate, census)

### SYS-20 — G3 trusted operator origin (approvals)

**Board state:** partly_built

**Who:** Lead (STG-03); operator for the root install on a host

**Now:** 12

**Own slices left:** 4 — **Next:** E82: a known-answer test of the SW-02 set fingerprint and a two-member continuation set, tests only, before G3-C — E82 — 1 PR (estimate; census)

### SYS-29 — Resource, model and host policy (wire increment I-6)

**Board state:** designed_only

**Who:** Lead (BOARD v2 §2, on the Now list)

**Now:** 15

**Own slices left:** 3 — **Next:** Move the code's O-01 command wire from 0.2 to 0.8 (I-7's 0.9 follows, BOARD v2 §2: 'O-01 0.2 to 0.8/0.9') — STG-14 — 1-2 PRs (estimate)

### SYS-22 — Specialist skills delivered to runs

**Board state:** staged

**Who:** Lead

**Now:** 23

**Own slices left:** 4 — **Next:** E127: the four skills, the hash manifest, provided_skills passed from the adapter and the dry run, the skills-folder read and edit rules, optional_skills on cards, the Lead's staffing text, the offered and loaded record; serial with CAP-1 PR 3 (SYS-09) as with E123: both change the same binds (future-work.yaml E127, 'after CAP-1 PR 2'). E127 goes first: it is a first-use item, and PR 3 is outside the first-use gate (future-work.yaml (§1 text, at c11a61ea)) — E127 — 1-2 PRs (estimate)

### SYS-08 — Governed stages on the typed Lead surface (StageIntent) and dispositions

**Board state:** partly_built

**Who:** Lead (E137, then E138, E133, E83 by the register's order); designer for D4; operator for placing E6b out of HOLD-10

**Now:** 25

**Own slices left:** 5 — **Next:** E137: the other judgment stages stranded at their last committed step, and the custody worker's registration (suspected); the publish case is fixed — E137 — 1 PR (estimate)

### SYS-41 — Lead consult (spawn a non-mutating agent for the Lead's own question)

**Board state:** designed_only

**Who:** Lead

**Now:** 28

**Own slices left:** 5 — **Next:** consult mode, its gate path, the tool, `consult_show` with the ingest, and the wake (consult design, Placement, PR 1; A-58 CL-R03) — E158 — 1 PR (estimate; the designer's reading, consult design Placement: 2 PRs in all)

### SYS-43 — Plan assessment gate and planner staffing

**Board state:** designed_only

**Who:** Lead

**Now:** 31

**Own slices left:** 4 — **Next:** the `plan_assessment` kind, its schema and the revision binding — E160 — about 1 PR (estimate; the designer's reading, planner design Q3: 3-4 PRs in all)

### SYS-45 — Branch review and document work (ref_review, technical_writer)

**Board state:** designed_only

**Who:** Lead

**Now:** 34

**Own slices left:** 3 — **Next:** the `technical_writer` card and `technical-writing` on `code_reviewer`, as data through the skills batches (skills design (c)) (rides on SYS-22's E136) (rides on SYS-22's E136 batches) — E167 — inside SYS-22's estimate

### SYS-03 — Read-only operator dashboard (server side)

**Board state:** partly_built

**Who:** designer (the HOLD-12 match), then operator (release /attention and E73), then Lead

**Now:** not on the Now list

**Own slices left:** 4 — **Next:** E73: the maps registry reader converges on engine/store.py read_lock_free instead of returning NONE on the first FileNotFoundError — E73 — 1 small PR (estimate)

### SYS-04 — Steering (Crawl/Walk/Run), operator endpoint and notifier

**Board state:** partly_built

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 12 — **Next:** The steering tool's text and the Lead's text say what works today (the designer's ruling, BOARD v2 §1). The code narrows that ruling, so the text must also say: lower succeeds only after the operator has raised the mode at the --dev endpoint, and in a project with no steering.mode every action, lower included, is refused as not configured — row owed — 1 small PR (estimate)

**Switch:** steering.mode

### SYS-13 — Lead-worker coordination messaging

**Board state:** partly_built

**Who:** operator (the BOARD v2 §3 decision and HOLD-09's release), then Lead

**Now:** not on the Now list

**Own slices left:** 8 — **Next:** Steering's progress digest (slot 3, first): harness_wait wakes with a short digest from the worker's live record (runlog.read_live, which has no reader today): files touched, the last command and test result, steps and time; it wakes early on a failing test, an out-of-scope file or a worker's message. It takes SYS-11's live-sample reader — row owed — 1-2 PRs (estimate; the designer's reading, the reset record)

**Switch:** coordination.messaging

### SYS-24 — Lead attachment lifecycle (Q12), custodian outliving the Lead, lease-expiry takeover

**Board state:** designed_only

**Who:** designer (E129's design, the lease-expiry ADR and the HOLD-06/HOLD-17 match), then operator (places E129 and the held members), then Lead; after first use (BOARD v2 §3)

**Now:** not on the Now list

**Own slices left:** 6 — **Next:** Correct the F31 note, which describes an attachment grant and automatic reattach the code does not have (BOARD v2 §6) — row owed — part of the Lead's §6 docs PR (estimate)

### SYS-31 — Bounded unattended mission and the relay's meter

**Board state:** designed_only

**Who:** Lead; operator for E98's paid live runs (BOARD v2 §2)

**Now:** not on the Now list

**Own slices left:** 3 — **Next:** E97: the relay's meter, per-provider request and response usage parsing and binding each paid call to its operation (after I-6); the meter's unit is the profile's declared rate_basis, all counters when undeclared (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 1) — E97 — 2-3 PRs (estimate)

### SYS-33 — Offline install bundle, release signing, upgrade and recovery

**Board state:** designed_only

**Who:** designer (E99's design), then Lead; operator places F18.3 and D2 out of HOLD-17

**Now:** not on the Now list

**Own slices left:** 3 — **Next:** E99's design: the one manifest, the per-target build and the guided install sequence, naming how F18.3 and D2 are absorbed at HOLD-17's exit — E99 — a design, no PR (estimate)

### SYS-34 — Checked launch briefs

**Board state:** designed_only

**Who:** operator places E154 (BOARD v2 §3); then Lead

**Now:** not on the Now list

**Own slices left:** 3 — **Next:** The brief checker (a bounded fact process with planted controls) passing LB01-Q01 to Q22, with the execution policy's bounds (LB01-02.d) — E154 — 1-2 PRs (estimate)

## The operator's open questions

**Members:** 1 — SYS-26

**Decided:** 31 — SYS-01, SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-07, SYS-08, SYS-09, SYS-11, SYS-12, SYS-13, SYS-14, SYS-15, SYS-18, SYS-19, SYS-20, SYS-21, SYS-22, SYS-24, SYS-25, SYS-34, SYS-37, SYS-39, SYS-40, SYS-41, SYS-42, SYS-43, SYS-44, SYS-45, SYS-48

### SYS-26 — Resource and progress supervision (stall detection, run health, weak-worker continuity, dynamic scheduler)

**Decision:** "Freezes in §4 that touch your past decisions (F19, U1)" (BOARD v2 §3); BOARD v2 §4: "freeze; pull U1's stall detection forward if first use repeats the 20-minute hang", decided by the operator or the Lead (placement out of HOLD-15).

## Done

**Members:** 2 — SYS-17, SYS-38

### SYS-17 — Transaction outbox and its consumers

### SYS-38 — ADR-0011 archival and history

## Not counted

**Members:** 16 — SYS-18, SYS-12, SYS-01, SYS-10, SYS-11, SYS-14, SYS-15, SYS-16, SYS-21, SYS-23, SYS-25, SYS-26, SYS-27, SYS-28, SYS-35, SYS-36

**SYS-18 — Ticket revisions:** freeze

**SYS-12 — Discovery layer, D2 (output and text rules):** freeze

**SYS-01 — Evaluation instrument (F19, M4-H):** freeze

**SYS-10 — STG-02 slice producer: the O-01 command route and D-01 reads, with the vendored adopted contract files:** freeze

**SYS-11 — Run cost and usage ledger (with live usage meter):** freeze

**SYS-14 — Knowledge system (Arm B raw-history search; M6b capture, admission and recall):** freeze

**SYS-15 — Operator settings surface and fresh-project configuration:** cut

**SYS-16 — Plan assurance before mutating dispatch (ASSURED):** keep

**SYS-21 — Operator attention (attention spine, observability, fact-owner registry, blocked-on-you):** freeze

**SYS-23 — Declared-but-unenforced policy and role-card fields:** freeze

**SYS-25 — Provider gateway, mutual-TLS client certificate and model-diverse routing:** freeze

**SYS-26 — Resource and progress supervision (stall detection, run health, weak-worker continuity, dynamic scheduler):** freeze

**SYS-27 — Backlog import (SPT remediation backlog):** keep

**SYS-28 — Cross-feature integration activation and plan-driven child materialization:** keep

**SYS-35 — Operator-approved exact-commit push, field diagnostics and SCM/Jira enforcement:** keep

**SYS-36 — Build/test impact analysis (F30):** keep
