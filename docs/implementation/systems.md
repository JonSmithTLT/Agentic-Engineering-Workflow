# The systems build board

Generated from [systems.yaml](systems.yaml). Do not edit; run `python tools/register.py render` (or `python tools/systems.py render`). Priority comes from [the register's Now list](future-work.md#1-now-the-milestones-and-the-gates-in-order). Count definition: FORMAT.md rule 1. Switch defaults are checked against the code's tables; board_state and built remain hand-kept. A PR that closes a row named in a slice, or changes what counts, re-runs `python tools/systems.py check` against current main before it merges (no merge queue).

## Totals

**on_and_used:** 3 — SYS-17, SYS-37, SYS-38

**awaiting_signoff (built, awaiting your sign-off):** 1 — SYS-39

**partly_built:** 18 — SYS-01, SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-08, SYS-09, SYS-11, SYS-13, SYS-15, SYS-16, SYS-18, SYS-19, SYS-20, SYS-21, SYS-25, SYS-48

**built_off:** 4 — SYS-07, SYS-12, SYS-14, SYS-23

**built_not_wired:** 1 — SYS-10

**staged:** 2 — SYS-22, SYS-27

**designed_only:** 19 — SYS-24, SYS-26, SYS-28, SYS-29, SYS-30, SYS-31, SYS-32, SYS-33, SYS-34, SYS-35, SYS-36, SYS-40, SYS-41, SYS-42, SYS-43, SYS-44, SYS-45, SYS-46, SYS-47

**Waiting on your sign-off:** 1 — SYS-39

**Limit's count / wip_limit:** 13 / 12 — SYS-02, SYS-03, SYS-04, SYS-05, SYS-06, SYS-07, SYS-08, SYS-09, SYS-13, SYS-19, SYS-20, SYS-22, SYS-48

**Operator allowance:** up to 14 — Until the operator’s root G3 session closes SYS-20 and SYS-37, I allow 14 counted systems. No new system starts while this allowance stands; it lapses when both close. — 2026-11-10 (only the cap and staleness are checked; the words' conditions are not checked)

**Switch defaults not read from the code:** 4 — SYS-02, SYS-04, SYS-11, SYS-12 — SYS-02: containment.mode (execution policy); SYS-04: steering.mode; SYS-11: policy.pricing (project manifest); SYS-12: MODES["O-CMD"] and MODES["O-SECRET"] in tests/helpers/discovery/modes.py (mirrored in vertical-uat.md §8.3; a test holds the two equal). A test-tooling constant outside the checked policy tables, so its default stays hand-kept

**Hand-kept wiring (no reference record):** 5 — SYS-04, SYS-06, SYS-07, SYS-08, SYS-22 — SYS-04: lead_text; SYS-06: lead_text; SYS-07: pack; SYS-08: lead_text; SYS-22: pack

## Finish and switch on soon

**Members:** 11 — SYS-47, SYS-40, SYS-42, SYS-44, SYS-48, SYS-07, SYS-30, SYS-32, SYS-37, SYS-39, SYS-46

### SYS-47 — Relay client certificate (E123)

**Board state:** designed_only

**Who:** Lead (E99 is adopted as A-55, which names E123 as the provider-access owner); operator for the live AIR-85 qualification

**Now:** 13

**Own slices left:** 2 — E123: certificate, key and CA fields in the execution policy schema, the client certificate loaded in the relay's TLS context per upstream, mask-and-refuse at launch, no-relay refusal, throwaway-CA tests, and a 429 measurement against a local fake upstream (on the Now list) (E123); The gate's live qualification of the forced request fields against the provider (AIR-85), a live run before a provider that requires a client certificate is used (row owed) — **Next:** E123: certificate, key and CA fields in the execution policy schema, the client certificate loaded in the relay's TLS context per upstream, mask-and-refuse at launch, no-relay refusal, throwaway-CA tests, and a 429 measurement against a local fake upstream (on the Now list) — E123 — 1-2 PRs (estimate)

**Wired:** none

### SYS-40 — Lead reports (report_write)

**Board state:** designed_only

**Who:** Lead

**Now:** 27

**Own slices left:** 1 — report_write: the tool, the report record kind and its store, the resolver refusals and pack exclusion, the size and count bounds, the show command and the site view, the label, and the Lead's text (small-changes design §4; first in the alpha list, §7 item 5) (E157) — **Next:** report_write: the tool, the report record kind and its store, the resolver refusals and pack exclusion, the size and count bounds, the show command and the site view, the label, and the Lead's text (small-changes design §4; first in the alpha list, §7 item 5) — E157 — 1 PR (estimate; the designer's reading, small-changes design §6)

**Wired:** none

### SYS-42 — Lead small change (operator-approved, light review at class 1)

**Board state:** designed_only

**Who:** Lead

**Now:** 30

**Own slices left:** 2 — the Lead change stage (item 43's stage) and its class 1 shape; the operator decision and fingerprint; the refusal list and check inputs; the export-and-check; the view rendering; containment widened to the route (CS-4 addendum 14); the light review and the operator-requested review ride in these PRs (small-changes design §2, §6, §8) (E159); first configuration (E119's `aew init`) proposes `review_triggers` entries with their levels and each check's `inputs:` list, for the operator to adopt (small-changes design §2, §8) (E166) — **Next:** the Lead change stage (item 43's stage) and its class 1 shape; the operator decision and fingerprint; the refusal list and check inputs; the export-and-check; the view rendering; containment widened to the route (CS-4 addendum 14); the light review and the operator-requested review ride in these PRs (small-changes design §2, §6, §8) — E159 — 4-5 PRs (estimate; the designer's reading, small-changes design §6)

**Wired:** none

### SYS-44 — Lead skills (a lead list in the skill manifest; no MCP servers in the alpha)

**Board state:** designed_only

**Who:** Lead

**Now:** 32

**Own slices left:** 2 — the Lead's skills: the `lead` list, per-mode rule lists in `lead_config`, the records and cost measures, the Lead's text and the live tests (skills design (a)); after E127 (E161); deliver delegation-handoffs, which is not among E136's eleven: unevaluated, alpha only, labelled (2026-11-06-operator-Lead-leeway-Lead-change-planner-and-tooling.md item 6) (E161) — **Next:** the Lead's skills: the `lead` list, per-mode rule lists in `lead_config`, the records and cost measures, the Lead's text and the live tests (skills design (a)); after E127 — E161 — 1 PR (estimate; the designer's reading, skills design (e))

**Wired:** none

### SYS-48 — Build board and systems generator (E182)

**Board state:** partly_built

**Who:** Lead

**Now:** 39

**Own slices left:** 1 — Derive serves and lanes (E182's later work). (row owed) — **Next:** Derive serves and lanes (E182's later work). — row owed — not sized (estimate)

**Wired:** none

### SYS-07 — Project maps in agents' context

**Board state:** built_off

**Who:** Lead (1-2 PRs after first use); decided by the operator

**Now:** not on the Now list

**Own slices left:** 3 — maps.pack_slices on for all cards (operator, 2026-11-06, design workspace record 2026-11-06-operator-board-decisions-concurrency-steering-maps-knowledge.md, item 3); each card's added pack size and tokens recorded, not a gate (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 3) (E62); An architecture_map pack section, or drop the pack promise of `aew map select-architecture`; wire or remove KNOWLEDGE_NAMES and resolve_knowledge (BOARD v2 §4 loose ends) (row owed); F22.2 and F22.3, the semantic layer and sibling indexes, after their benchmark (census: P-DEC-03) (F22.2) — **Next:** maps.pack_slices on for all cards (operator, 2026-11-06, design workspace record 2026-11-06-operator-board-decisions-concurrency-steering-maps-knowledge.md, item 3); each card's added pack size and tokens recorded, not a gate (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 3) — E62 — 1-2 PRs (estimate)

**Switch:** maps.pack_slices — default: off — checked against src/aew/policy/execution.py:STRING_SWITCHES

**Wired:** cli:map generate, cli:map select-architecture, cli:map show, cli:map diff, dashboard:/maps, dashboard:/maps/structural, dashboard:/maps/structural/{root}, dashboard:/maps/structural/{root}/inputs, dashboard:/maps/diff, pack, tool:resume

### SYS-30 — Research minimum slice, CNI links and PoCs as linked Tickets

**Board state:** designed_only

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 2 — File the build row (BOARD v2 §2: no row yet), with the slice's file scope so its lanes can be computed (row owed); The inquiry record and its completion by answer (A-40), the link-record store with five kinds listed from both ends (A-41), the PoC as a linked Ticket proposal (A-50 PL01), on I-7's commands (O-01 0.9) and the shared read wire, after I-6 (row owed) — **Next:** File the build row (BOARD v2 §2: no row yet), with the slice's file scope so its lanes can be computed — row owed — part of 1 register PR (estimate)

**Wired:** none

### SYS-32 — Independent outage reader (aew read)

**Board state:** designed_only

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 2 — E108: the aew read command over the store, reusing the D-01 wire's stamps without the server; the eight served reads not yet built anywhere; the non-writer declaration and tests; the surface-map entry (E108); G4: O02-Q01 to O02-Q08 run host by host on Linux once containment holds there (E108) — **Next:** E108: the aew read command over the store, reusing the D-01 wire's stamps without the server; the eight served reads not yet built anywhere; the non-writer declaration and tests; the surface-map entry — E108 — 2-3 PRs (estimate; BOARD v2 §2)

**Wired:** none

### SYS-37 — Register of weaker contexts (E112, G3 addendum 7)

**Board state:** on_and_used

**Who:** Lead, with G3-C

**Now:** not on the Now list

**Own slices left:** 0 — none — **Next:** none

**Wired:** none

### SYS-39 — Integration pipeline (ADR-0004 queue, custody worker, workspaces)

**Board state:** awaiting_signoff

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 2 — The offer that switches an existing project's gates.yaml to the default, at the operator's terminal, which replaces the migration (F10); AEW's git wrapper never acts on the wrong repository from inside a git operation (E225) — **Next:** The offer that switches an existing project's gates.yaml to the default, at the operator's terminal, which replaces the migration — F10 — 1 PR (estimate)

**Switch:** gates.mutating_concurrency — default: 2 — checked against src/aew/knowledge/manifest.py:DEFAULT_GATES

**Wired:** cli:integrate prepare, cli:integrate publish, cli:integrate validate, cli:integrate reconcile, cli:integrate defer, cli:integrate reorder, cli:integrate requeue, cli:integrate custody, cli:integrate breaker status, cli:integrate breaker reset, tool:integration_publish, tool:ticket_prepare

### SYS-46 — The V-01 command wire after I-6 (I-7's O-01 0.9, and the I-1 to I-5 commands in O-01 0.7 and 0.8)

**Board state:** designed_only

**Who:** Lead files the rows (V-01 is placed); builders after I-6

**Now:** not on the Now list

**Own slices left:** 2 — File the rows: one per increment after I-6, in the V-01 milestone's order (I-6, then I-7) (row owed); I-7's commands at O-01 0.9, and the I-1 to I-5 commands the move to 0.8 carries (row owed) — **Next:** File the rows: one per increment after I-6, in the V-01 milestone's order (I-6, then I-7) — row owed — no PR

**Wired:** none

## Finish, with more to build

**Members:** 19 — SYS-02, SYS-05, SYS-09, SYS-19, SYS-06, SYS-20, SYS-29, SYS-22, SYS-08, SYS-41, SYS-43, SYS-45, SYS-13, SYS-03, SYS-04, SYS-24, SYS-31, SYS-33, SYS-34

### SYS-02 — Agent containment (Linux core on; Windows backend and follow-ons)

**Board state:** partly_built

**Who:** Lead (E118 on the Now list; E100, E92 at Internal alpha; E113 to place); operator places F48 out of HOLD-06

**Now:** 5

**Own slices left:** 11 — E118: the contained Lead's saved permissions cleared at start, and the Lead's server moved out of the shell's reach (on the Now list, before first use) (E118); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E100: change mode()'s win32 branch so an explicit required refuses the launch on every platform (E100); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E92: forward plain http:// requests through the contained egress under the same R-6 host check (E92); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E113: a headless contained OpenCode Lead, so the live lane exercises containment (E113); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): CS-4 addendum 12: the Lead credential's input as a hidden prompt, never a command-line value (map v1.20:87; no register row found) (row owed); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): CS-4 addendum 13: an AEW-projected, display-only status plugin in the Lead's TUI (map v1.20:87; no register row found) (row owed); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): CS-4 addendum 14: the Lead edits a class 0 change in that Ticket's workspace only (map v1.20:87; no register row found) (row owed); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F48: the Windows containment backend, restored as its own row by the hold match (main 5308bd8c) (F48); Windows network containment, with the Lead's usage on Windows (E222); ProcessTree.active() with a group holding only a zombie, for checking (E247); run_session_tree's std handles on Windows (E250) — **Next:** E118: the contained Lead's saved permissions cleared at start, and the Lead's server moved out of the shell's reach (on the Now list, before first use) — E118 — 1 small PR (estimate; BOARD v2 §0)

**Switch:** containment.mode (execution policy) — default: required on Linux; allow_weaker on Windows, even when required is set explicitly — not read from the code

**Wired:** cli:harness launch, cli:check run, cli:opencode, cli:lead session, cli:doctor, cli:harness status

### SYS-05 — Harness currency and further harness adapters

**Board state:** partly_built

**Who:** Lead (E35's probe; H-1 to H-3 after CAP-1 PR 3); operator places E149, and E150 follows it; F24 leaves HOLD-06 after the designer's match, then the operator places it (BOARD v2 §3: after first use, unless 429s recur)

**Now:** 6

**Own slices left:** 9 — E35's probe: whether OPENCODE_DISABLE_PROJECT_CONFIG also excludes .opencode/ plugins and the remote .well-known layer (on the Now list, before first use) (E35); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E35's seams: HarnessAdapter.capabilities(), LaunchContract skills/tools_allowed/native_sandbox, explicit execute and browser denies, the 'nothing else loaded' conformance scenario, tool_output limits (on the Now list) (E35); H-1: qualify OpenCode 2.1.4, with the C1 compaction re-probe, a TESTED_VERSIONS entry and a token_semantics row (on the Now list; CAP-1 PR 3 has merged) (E35); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): H-2 (OpenCode qualification, absorbed F18.11) and H-3 (patch releases without a PR per release, absorbed E17 with H-1's part 2; H-3's bundle import); shares its bundle import with F18.3 (SYS-33) (E35); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E149: the 429 re-drive in the turn-end path, with the relay classifying a 429 and setting x-should-retry; once placed (E149); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E150: turn-ending continuation for workers, after E149 (E150); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E152: measure ruling 11's W1 workaround (measurement only, before any patch to the harness) (E152); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F24.1, the Codex runtime-semantics probe, the first slice of any Codex adapter work (F24.2, Claude Code headless, after it); held in HOLD-06 (F24); default_binary finds OpenCode Desktop 2.2.6's copy (E235) — **Next:** E35's probe: whether OPENCODE_DISABLE_PROJECT_CONFIG also excludes .opencode/ plugins and the remote .well-known layer (on the Now list, before first use) — E35 — 1 PR (estimate)

**Wired:** cli:harness launch, cli:harness config, cli:opencode, cli:doctor

### SYS-09 — Capability register (CAP-1 and the base bundle)

**Board state:** partly_built

**Who:** Lead

**Now:** 7

**Own slices left:** 5 — The owed lines from CAP-1 PR 2's review: the agent system-text line naming a missing tool, the Lead's results line, the consent prompt, `aew capability fetch` and the setup fetch (STG-15); Card-capability resolution: map the cards' snake_case names to the register's capability ids and replace the 'workbench resolution pending' pack line (STG-15); The stale package docstring (capability/__init__.py:8-10), in BOARD v2 §6's docs PR (row owed); Later: MCP servers and SPT's records (A-54, SPB), host placement and network; designed only (STG-15); The tool-consent prompt, CAP-1's follow-on, with `aew capability fetch` (E171) — **Next:** The owed lines from CAP-1 PR 2's review: the agent system-text line naming a missing tool, the Lead's results line, the consent prompt, `aew capability fetch` and the setup fetch — STG-15 — 1-2 PRs (estimate)

**Wired:** cli:capability list, cli:capability check, cli:capability import, cli:capability add, cli:capability remove, cli:capability host-copies, cli:doctor

### SYS-19 — Validation evidence completeness (artifact digests, coverage disclosure, readiness, remote provider)

**Board state:** partly_built

**Who:** Lead (E120, E125); designer for E153's ruling; designer or operator for the two loose ends (BOARD v2 §4)

**Now:** 9

**Own slices left:** 4 — E120: what its first PR left owed: the record's section 2 (what a run went without), and E243's project-owned source for the two lists its record now says are not known (E120); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): artifact_digests, always empty: populate or drop (BOARD v2 §4 loose end) (row owed); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): working_diff, never called: keep or remove (BOARD v2 §4 loose end) (row owed); A project-owned source for E120's two lists (E243) — **Next:** E120: what its first PR left owed: the record's section 2 (what a run went without), and E243's project-owned source for the two lists its record now says are not known — E120 — 1-2 PRs (estimate)

**Wired:** cli:check run, dashboard:/evidence/{id}

### SYS-06 — Typed agent surfaces (the Lead's catalog and transports; role-side MCP servers)

**Board state:** partly_built

**Who:** operator (placing F15.3 and F15.8 out of HOLD-06, after the designer's match); then Lead. Lead for the DESIGNED-status loose end

**Now:** 11

**Own slices left:** 11 — FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F15.3: the aew-run role server over the existing run bridge (whoami, check.run and typed submit as in-sandbox MCP tools; the supervisor keeps the credential). Held in HOLD-06 until the designer's match and the operator's placement (F15.3); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F15.8: the aew-run read half (map.* reads, evidence.show, check.suggest as bridge operations; tools.presentation). Waits on typed map and evidence reads (F15.8); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): aew-knowledge as its own capability namespace over the shared transport library: part of F15.3's text, so held with it in HOLD-06; what it serves waits on K-01's increment (F15.3); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): typed Lead rows for maps, history, settings, usage and g3, reachable today only untyped through the shell rule `aew *` (row owed); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): BOARD v2 §4 loose end and §6 stale text: drop the catalog's unused DESIGNED status and correct the contract.py docstring that says rows stay DESIGNED (row owed); E122: the next step while the Lead waits. Waiting is one blocking request, never a polling loop (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 3) (E122); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): The Lead's request-economy text remains owed after E139's worker-pack fixes (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 3) (E162); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): Lead text fixes, and a typed `plan accept` (E162); The Lead's tool budget, decided before E158 (E231); The Lead's exits: the eight dead ends, and the lands guard (E233); The worker route's size check (E241) — **Next:** FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): F15.3: the aew-run role server over the existing run bridge (whoami, check.run and typed submit as in-sandbox MCP tools; the supervisor keeps the credential). Held in HOLD-06 until the designer's match and the operator's placement — F15.3 — 1-2 PRs (estimate, census)

**Wired:** cli:lead mcp, cli:lead tool, lead_text

### SYS-20 — G3 trusted operator origin (approvals)

**Board state:** partly_built

**Who:** Lead (STG-03); operator for the root install on a host

**Now:** 12

**Own slices left:** 4 — E82: a known-answer test of the SW-02 set fingerprint and a two-member continuation set, tests only, before G3-C (E82); G3-C: owners consume a G3 consent once at allocation, ATTACH_LEAD included, and consult the register of weaker contexts (STG-03); The G3 install on a Linux host: root runs g3/install.sh and sets the PIN (STG-03); G3 on Windows (E223) — **Next:** E82: a known-answer test of the SW-02 set fingerprint and a two-member continuation set, tests only, before G3-C — E82 — 1 PR (estimate; census)

**Wired:** cli:g3 request

### SYS-29 — Resource, model and host policy (wire increment I-6)

**Board state:** designed_only

**Who:** Lead (BOARD v2 §2, on the Now list)

**Now:** 15

**Own slices left:** 3 — Move the code's O-01 command wire from 0.2 to 0.8 (I-7's 0.9 follows, BOARD v2 §2: 'O-01 0.2 to 0.8/0.9') (STG-14); The nine rows' actions and handlers across their owners (IF-13, the resource policy issuer, R-01), with surface-map entries; P11's migration half and U10 wait for U-01 (STG-14); Provider profiles declare rate_basis (which counters the limiter counts) and its window; I-6's ceilings in that unit and period (designer-decisions-2026-11-06-rate-limit-unit.md, ruling 1) (STG-14) — **Next:** Move the code's O-01 command wire from 0.2 to 0.8 (I-7's 0.9 follows, BOARD v2 §2: 'O-01 0.2 to 0.8/0.9') — STG-14 — 1-2 PRs (estimate)

**Wired:** none

### SYS-22 — Specialist skills delivered to runs

**Board state:** staged

**Who:** Lead

**Now:** 23

**Own slices left:** 3 — E142: serve security-review and c-review (on the Now list) (E142); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E136: the other eleven skills as optional_skills, batched (on the Now list) (E136); E135: the evaluation runner, and qualification before anything beyond the personal alpha (E135) — **Next:** E142: serve security-review and c-review (on the Now list) — E142 — 1 PR (estimate)

**Wired:** pack

### SYS-08 — Governed stages on the typed Lead surface (StageIntent) and dispositions

**Board state:** partly_built

**Who:** Lead (E137, then E138, E133, E83 by the register's order); designer for D4; operator for placing E6b out of HOLD-10

**Now:** 25

**Own slices left:** 5 — E137: the other judgment stages stranded at their last committed step, and the custody worker's registration (suspected); the publish case is fixed (E137); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): E138: record the escaping exception's class where it can be read, with a stage result when steps committed (E138); E133: typed exits from REVIEW_PASSED, VERIFIED and COMMIT_READY, and the verifier-mode publish; it waited on E130, which has merged (E133); E83: declare the auto-run set (ticket_start and ticket_request_review, under RUN only) and test that classify.auto_runnable's set equals it (E83); FROZEN by the reset of 2026-11-06 (design workspace record 2026-11-06-operator-reset-finish-and-switch-on.md): designer decision D4: what a listed unrequired verification result marks, before that half of requires_disposition can mark anything (row owed) — **Next:** E137: the other judgment stages stranded at their last committed step, and the custody worker's registration (suspected); the publish case is fixed — E137 — 1 PR (estimate)

**Wired:** cli:lead mcp, cli:lead tool, cli:stage continue, cli:stage abandon, cli:work dispose, lead_text

### SYS-41 — Lead consult (spawn a non-mutating agent for the Lead's own question)

**Board state:** designed_only

**Who:** Lead

**Now:** 28

**Own slices left:** 5 — consult mode, its gate path, the tool, `consult_show` with the ingest, and the wake (consult design, Placement, PR 1; A-58 CL-R03) (E158); the bounds and the allow-list, the isolation tests, the resume lists and the Lead's text (consult design, Placement, PR 2) (E158); `aew policy model allow <provider/model>` and a profile add, operator-decided, with their surface-map entries (consult design, later pointer); first configuration proposing a profile per named provider (E164); an operator-requested review or verification on a consult or branch review: the obligation-adding request record, its non-waivable mark, its owed dispatch in `next`, the operator's removal (small-changes design §8) (row owed); `--model` held to profiles plus the allow-list, always bounded (E165) — **Next:** consult mode, its gate path, the tool, `consult_show` with the ingest, and the wake (consult design, Placement, PR 1; A-58 CL-R03) — E158 — 1 PR (estimate; the designer's reading, consult design Placement: 2 PRs in all)

**Wired:** none

### SYS-43 — Plan assessment gate and planner staffing

**Board state:** designed_only

**Who:** Lead

**Now:** 31

**Own slices left:** 4 — the `plan_assessment` kind, its schema and the revision binding (E160); the assessor entrypoint for Tickets and parents, its pack and the anti-shopping rule (E160); the gate on the class paths and its dispatch refusal, the planner-review credit, the findings' source kind with the waiver refusal, and the operator's dismissal (E160); the Lead's staffing text (one passage beside E127's staffing line) and engine enforcement of `requires_distinct_invocation_from` (E160) — **Next:** the `plan_assessment` kind, its schema and the revision binding — E160 — about 1 PR (estimate; the designer's reading, planner design Q3: 3-4 PRs in all)

**Wired:** none

### SYS-45 — Branch review and document work (ref_review, technical_writer)

**Board state:** designed_only

**Who:** Lead

**Now:** 34

**Own slices left:** 3 — the `technical_writer` card and `technical-writing` on `code_reviewer`, as data through the skills batches (skills design (c)) (rides on SYS-22's E136) (rides on SYS-22's E136 batches) (E167); raw-body retrieval of any record, CLI and site, with its surface-map entry (skills design (c)) (E170); a review of a named ref: ref pinning and merge-base at dispatch, the `ref_review` kind and its freshness, the archetype's new kind, the `branch_reviewer` card and its skill-fit check (skills design (d)) (E168) — **Next:** the `technical_writer` card and `technical-writing` on `code_reviewer`, as data through the skills batches (skills design (c)) (rides on SYS-22's E136) (rides on SYS-22's E136 batches) — E167 — inside SYS-22's estimate

**Wired:** none

### SYS-13 — Lead-worker coordination messaging

**Board state:** partly_built

**Who:** operator (the BOARD v2 §3 decision and HOLD-09's release), then Lead

**Now:** 40

**Own slices left:** 7 — Steering's progress digest (slot 3, first): harness_wait wakes with a short digest from the worker's live record (runlog.read_live, which has no reader today): files touched, the last command and test result, steps and time; it wakes early on a failing test, an out-of-scope file or a worker's message. It takes SYS-11's live-sample reader (row owed); MS4+MS6: worker reply/read/wait, launch snapshot, one Lead wake and local told-ID consumption (E175); MS5: live delivery and continuation (E175); MS5b: finality, both timings, recorded harness send and default-on (E175); MS7: separately approved real-provider qualification; not a default-on gate (E175); Standalone off/compact surface.presentation policy remains deferred until F19 thaws with a named consumer (row owed); A typed harness_interrupt (E248) — **Next:** Steering's progress digest (slot 3, first): harness_wait wakes with a short digest from the worker's live record (runlog.read_live, which has no reader today): files touched, the last command and test result, steps and time; it wakes early on a failing test, an out-of-scope file or a worker's message. It takes SYS-11's live-sample reader — row owed — 1-2 PRs (estimate; the designer's reading, the reset record)

**Switch:** coordination.messaging — default: disabled — checked against src/aew/policy/execution.py:STRING_SWITCHES

**Wired:** tool:message_send, cli:message thread, cli:message list, cli:message unseen, cli:harness send

### SYS-03 — Read-only operator dashboard (server side)

**Board state:** partly_built

**Who:** designer (the HOLD-12 match), then operator (release /attention and E73), then Lead

**Now:** not on the Now list

**Own slices left:** 4 — E73: the maps registry reader converges on engine/store.py read_lock_free instead of returning NONE on the first FileNotFoundError (E73); E94: the web package refresh (S3); the packaged build still names contract 0.1.2's digest while the served contract is 0.1.3. The web developer's (E94); E148: a containment reader so the site shows a run's provider route; the run label now carries relay_family (E143's follow-on) but nothing in src/aew/dashboard reads it. The web developer's to place (E148); the probe's diagnostic on a host with no LISTENING row for its own listener (E236) — **Next:** E73: the maps registry reader converges on engine/store.py read_lock_free instead of returning NONE on the first FileNotFoundError — E73 — 1 small PR (estimate)

**Wired:** cli:dashboard serve, cli:dashboard open, cli:dashboard status, dashboard:/overview, dashboard:/project, dashboard:/capabilities, dashboard:/work, dashboard:/runs, dashboard:/evidence, dashboard:/knowledge, dashboard:/history, dashboard:/activity, dashboard:/maps

### SYS-04 — Steering (Crawl/Walk/Run), operator endpoint and notifier

**Board state:** partly_built

**Who:** Lead

**Now:** not on the Now list

**Own slices left:** 12 — The steering tool's text and the Lead's text say what works today (the designer's ruling, BOARD v2 §1). The code narrows that ruling, so the text must also say: lower succeeds only after the operator has raised the mode at the --dev endpoint, and in a project with no steering.mode every action, lower included, is refused as not configured (row owed); Only if the operator decides it (BOARD v2 §3): hide request_raise and request_confirmation from the normal catalog until a grant path exists; lower stays (row owed); Confirmation: E7c as planned, or re-pointed at G3 per A-37; `aew confirm` (HOLD-19); E6b publication grants and E8b breaker reset and relaunch at the endpoint; E7d's events (HOLD-19); F18.6, the principal proof, so operator records can carry more than guarantee: dev (F18.6); Scheduler priority: a Ticket field, three levels, the derived unblock count (E227); The scheduler on: the switch-on chain after E123 (E228); A priority floor, the operator's setting (E229); A steering raise that persists for the project (SMP, A-56) (E230); A console window for a Linux background endpoint (E232); Push wake measured on Windows (E240); The conversational Lead's docs follow-ons (E249) — **Next:** The steering tool's text and the Lead's text say what works today (the designer's ruling, BOARD v2 §1). The code narrows that ruling, so the text must also say: lower succeeds only after the operator has raised the mode at the --dev endpoint, and in a project with no steering.mode every action, lower included, is refused as not configured — row owed — 1 small PR (estimate)

**Switch:** steering.mode — default: absent — not read from the code

**Wired:** tool:steering, cli:operator serve, cli:operator ping, cli:lead mode raise, cli:lead mode lower, lead_text

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
