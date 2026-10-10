# Agent effectiveness: the ordered implementation delta (2026-10-09)

- **Status:** living implementation plan; the lead developer's planning pass of 2026-10-09, which the
  [agent-effectiveness adoption](../design/decisions-2026-10-09-agent-effectiveness-adoption.md) asks for in its §16
  (ledger AEA-44). **Nothing in it is built.** It has no authority of its own: the adoption record and the designs it
  names govern, and the register rows named here track the work.
- **Inputs:** the adoption record (designer and operator direction, 2026-10-09; ledger AEA) and the research it accepts
  with three revisions, the [agent-effectiveness synthesis](../research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md)
  (ledger AES; its thread notes, corpus evidence and probes are not in this repository). The tree is `origin/main` at
  `0ff0435`, with these open pull requests: #143 (F22.1 PR B, the structural map in context), #148 (the F21 Arm B
  prototype) and #142 (M4-E E3b); the [M4-E plan v3](m4-e-plan-v3.md); and F4's Ticket-revision plan, being drafted.

## 1. The rules this plan applies

1. **No new machinery.** Every item lands on an owner that already exists (record §1, §13). The four new register rows,
   F15.8, F15.9, F35 and F36, are work items the record directs *inside* existing owners (the run bridge, the typed
   Lead surface, the pack generator, the role report and supervisor), not new components.
2. **M4-H's treatment does not move (Revision B).** Q7 v0.3.1 is adopted and design frozen; its M4 commit and
   treatment bundle are frozen at preregistration (its §14.1, item 2), and a change to a treatment-defining artifact
   after calibration has begun forces a re-freeze (its §7). Once the bundle is frozen, later merges are not in it;
   before then, an item that lands is in the commit, so it must not be in the behaviour. Every item below that changes
   what a model sees therefore ships **off and absent by default**, with a test that output is byte-identical while
   off, as #143 (`maps.pack_slices`) and #148 (`recall.raw_history_search`) already do.
   This plan proposes **none** of them for M4-H's treatment, so no preregistration amendment is needed. If one is
   proposed later, it follows Revision B: name the treatment change, amend the preregistration, re-freeze, before
   running. The operator's M4-H decision of 2026-10-07 (role packs are not broadened; `codebase_map` stays on the
   investigator; wider map serving earns itself through later evaluation) stands.
3. **The main lane keeps its priority.** M4-E, F25's telemetry, F19's evaluator/arm-host split and F15.5/F15.6 are
   M4-H's prerequisites (Q7 v0.3.1 §16). The items here are parallel lanes on spare capacity; none is a prerequisite
   of M4-H and none is waited for.
4. **Nothing builds on unmerged work** (AGENTS.md §3). An item that needs an open pull request starts after it merges.
5. **Defaults are earned by measurement** (record §12). Pre-gate runs qualify the lane and its instrumentation only
   (record §9); treatment-effect claims come from post-gate runs.

## 2. Classification of every item

The six classes are the record's §16. "Delta" names the item in §3 that does the work.

| Item (source) | Classification | Register row | Delta |
|---|---|---|---|
| R8: no new component; improve the pack generator (record §2, §4; synthesis §2) | implementation-local refinement | F35 | D5 |
| R9: extend the typed role surface (record §2, §5; synthesis §3) | existing item — priority/sequence change | F15.3, split to F15.8 | D7 |
| R2-B: recitation plus the bounded handoff note (record §2, §6; synthesis §4) | implementation-local refinement | F36 | D6, D11 |
| E1: the completion-impact nudge (record §2, §7; synthesis §5) | existing item — priority/sequence change | F30 (first slice), F22.3 | D8 |
| E2: delta-first Lead attention (record §2, §8; synthesis §5) | implementation-local refinement | F15.9 | D9 |
| The simplest system, five things (record §2; synthesis §12) | existing item — no change (the sum of the rows above) | F34 | all |
| Revision A, workspace-bounded lexical fallback | existing item — no change (WCR-08 already requires it), applied to F15.8 | F15.8 | D7 |
| Revision B, M4-H treatment | existing item — no change (Q7 v0.3.1 §7 and §14 already require it), applied to every item | F19 | §1 rule 2 |
| Revision C, the bounded session-database reader | existing item — priority/sequence change (operator-approved, record §10.2) | F19 | D2 |
| Serving policy, rendering convention, budget and orientation knobs, criteria repeated, anchors first (record §4) | implementation-local refinement | F35 | D5 |
| Knowledge on demand until Arm B is measured (record §4) | existing item — no change (KAD-11) | F21 | D12 |
| Stale or partial derived context visibly qualified (record §4) | existing item — no change (project maps v0.5 §11.2) | F35, F22 | D5 |
| Reviewer and verifier independence (record §4, §14) | existing item — no change (KDR-03 to KDR-05); the filter's placement is implementation-local | F35, F21 | D5 |
| Worker read tools on the `aew-run` bridge (record §5, §10.1) | existing item — priority/sequence change | F15.8 | D7 |
| Operation names (record §5) | implementation-local refinement | F15.8 | §4 item 1 |
| `tools.presentation` (record §5) | implementation-local refinement, with an F19 probe | F15.8, F19 | D7, D14 |
| R2-B non-goals (record §6) | existing item — no change | F36 | — |
| Laguna not currently available; capability-class lanes (record §9) | existing item — no change (F32 and F18.13 notes) | F32, F18.13, F19 | D3 |
| The lower-bound pre-M4-H fixture (record §9, §10.3) | F19 probe | F19 | D3 |
| Raise T5-D (record §11) | existing item — priority/sequence change | F22.3 | D4 |
| Raise the R2 handoff note (record §11) | implementation-local refinement (no earlier row) | F36 | D6 |
| Raise the F19 metric reader (record §11) | existing item — priority/sequence change | F19 | D2 |
| Reviewer layout row (record §11; synthesis §2) | implementation-local refinement | F35 | D5 |
| The Lead's structural map in `resume` (record §11) | existing item — no change (F22.1 PR B, #143) | F22.1 | D1 |
| Refine F30, F9/F20/M5, the execution-profile schema, serving policy and independence filter (record §11) | implementation-local refinement | F30, F15.9, F9, F20.7, F11, F35, F36, F15.8 | D5 to D11 |
| Ingest F9-A1 (record §11) | existing item — no change: already ingested (PR #145, ledger LWM); its adoption is the decisions-due item | F9 | — |
| `knowledge.search` and `knowledge.get` after Arm B (record §11) | existing item — no change (F21's sequence), hosted by F15.8 | F21, F15.8 | D12 |
| The five probes (record §12; synthesis §9) | F19 probe | F19 | D14 |
| Non-goals (record §13; synthesis §10) | existing item — no change | F34 | — |
| Ticket parent changes against promotion (record §15) | editorial contract clarification | F4, E19 | D15, D16 |
| Archetype schema: `context.orientation` (synthesis §7) | implementation-local refinement | F35 | D5 |
| Execution-profile fields (synthesis §7) | implementation-local refinement | F35, F15.8, F36 | D5, D7, D11 |
| Evidence schema: `handoff_note`, `self_review.related_surfaces`, `surface_sha256` (synthesis §7) | implementation-local refinement | F36, F30 | D6, D8 |
| `bridge.OPERATIONS` read rows and the stdio server (synthesis §7) | existing item — priority/sequence change | F15.8 | D7 |
| The `changes` catalog addition (synthesis §7) | implementation-local refinement; the record's §8 is the designer and operator's direction to add it | F15.9 | D9 |
| H1: `repetition` and `observed_through` (synthesis §7) | implementation-local refinement | U1 | D10 |
| The E19 re-freeze lines (synthesis §7) | editorial contract clarification | E19 | D16 |
| Synthesis §8 steps 1 to 7 | the order of §3 below | — | D1 to D14 |

## 3. The ordered delta

D1 to D8 may proceed before M4-H, each off by default and outside its treatment; D9 to D13 wait for the gates named;
D14 runs after M4-H; D15 and D16 are independent of the rest.

### D1. F22.1 PR B lands as planned

- **Owner:** F22.1 (#143, open). **Class:** existing item — no change.
- **Depends on:** #143's independent review and CI.
- **New work:** none from this adoption. #143 already carries the structural slice and the Lead's `resume` map row
  behind `maps.pack_slices`, off by default (R8's arm B).
- **Sequencing change:** none.
- **Done when:** #143 merges at `Review: CLEAR`; F22.1 closes in §9.
- **Probe:** `r8-pack-arms` arm B, after M4-H.
- **Before M4-H:** yes, as planned; its switch stays off for M4-H.
- **Operator or designer action:** none.

### D2. The F19 session-database reader and the metric functions

- **Owner:** F19. **Class:** existing item — priority/sequence change (Revision C; operator approval with bounds,
  record §10.2).
- **Depends on:** nothing in the product. F19's slices 1 to 3 are built; the evaluator/arm-host split (an M4-H
  prerequisite) is independent of it.
- **New work:** an evaluator-side reader in `eval/aew_eval/` that, after a run completes, opens that run's retained
  harness session database read-only, extracts only the fields its experiment's preregistration names, and feeds named,
  versioned metric functions in a new `eval/aew_eval/metrics.py` (orientation cost, repeated reads and tool n-grams,
  repository-wide searches, missed related surfaces, Lead reads); the run record names the metric versions and the
  database's retention expiry. The corpus probes behind the synthesis are outside the repository: they are drafts, and
  each function is re-derived here with its own tests.
- **Sequencing change:** raised; it is the instrumentation every probe needs, and the lower-bound lane (D3) starts on
  it.
- **Done when:** tests prove that the reader opens read-only and never writes; that it refuses a preregistration that
  names no fields or no retention window; that fields outside the allow-list are never read; that nothing under
  `src/aew` imports it (AEW's runtime never consumes the database); and that each metric function is pinned by name and
  version on fixtures.
- **Probe:** it is the substrate of D3 and D14.
- **Before M4-H:** yes. Evaluation only; it changes no treatment.
- **Operator or designer action:** none beyond the approval given; the retention window is set per experiment at
  preregistration, as F19's other pinned values are.

### D3. The lower-bound qualification lane

- **Owner:** F19, with F32 for the profiles. **Class:** F19 probe.
- **Depends on:** D2; a seeded fixture; a qualified lower-bound profile (F32's qualification through the pinned
  harness).
- **New work:** choose the fixture in the record's order (a sanitized public repository of several hundred files with
  more than one plausible search root, else a synthetic one; the Q7 repository only for a repository-integration probe
  that genuinely needs it, recorded in `exposure.yaml`); seed the eight behaviours of synthesis §13.4; preregister with
  `purpose: qualification`; run the lower-bound profile raw first. A profile that shows none of the eight behaviours is
  replaced by the next-cheaper one. Laguna is not currently available and gates none of this; the frontier, mid and
  lower-bound classes are pinned with exact provider, model, harness and effective profile at preregistration.
- **Sequencing change:** new; it runs before M4-H, by the designer's confirmation (synthesis §13.4).
- **Done when:** the lane's preregistration is sealed and its raw runs show which behaviours occur and that the metrics
  detect them. Its results are qualification and instrumentation evidence only; no pre-gate experiment id is reused for
  a treatment-effect experiment.
- **Probe:** it qualifies D14's lanes.
- **Before M4-H:** yes. Q7's sealed tasks stay unexposed.
- **Operator or designer action:** none new. Which concrete free or inexpensive model, and the lane's budget, are
  preregistration values the operator pins (record §10.3).

### D4. F22.3: the test relationship and constraint locator indexes (T5-D)

- **Owner:** F22.3. **Class:** existing item — priority/sequence change.
- **Depends on:** F22.1's structural core (PR A, built). It does not need #143.
- **New work:** as the row and project maps v0.5 §9 and §16 T5-D define it: the bounded test relationship index (its
  structural half without semantic facts, saying so), the constraint locator index, the public-surface projection and
  the untrusted-string projection tests; each index with its own freshness. Plus the typed answers D7 serves
  (`map.tests_for`, `map.constraints`) under the maps' answer contract (terminal state, coverage, freshness, evidence
  locators).
- **Sequencing change:** **Unscheduled** becomes **M4 candidate**, a parallel lane like F22.1.
- **Done when:** T5-D's slice is built with those tests; no index makes a test required or changes a pack; F22.3
  closes.
- **Probe:** R8's arm C, R9's test and constraint questions, E1 (D14).
- **Before M4-H:** yes. Building an index changes no model's context.
- **Operator or designer action:** none.

### D5. F35: context-pack serving

- **Owner:** F35, in `ContextPacks` and `knowledge/context.py`. **Class:** implementation-local refinement.
- **Depends on:** nothing for parts (a) to (c) and (e); part (d) and the slice's rendering wait for #143 to merge.
- **New work:**
  - (a) the derived-section rendering convention: source, revision, freshness and coverage or limitations in the
    section heading, one item per line with an expansion reference, a degraded section as one labelled line;
  - (b) the execution profile's `context.budget_chars`, `context.orientation_max_chars` and `context.orientation`
    (minimal, standard or explicit) passed to `assemble`, the wiring E29 left for a measured budget; the criteria
    repeated last under `explicit`, a mode that becomes anyone's default only if evaluation supports it;
  - (c) the per-role, per-tier serving-policy table as archetype data (mandatory, opportunistic, on-demand,
    prohibited), with a conformance test per role;
  - (d) the reviewer's layout row: the directories of the diff, from the structural map;
  - (e) the pack's independence filter: prohibited rows for reviewers and verifiers, who keep the canonical same-Ticket
    material and lose the current implementer's reasoning and private working state, with sentinel tests. The
    knowledge request-binding half is F21's role matrix (KDR-03 to KDR-05).
- **Sequencing change:** new row, **M4 candidate**, a parallel lane.
- **Done when:** with every new field unset, every pack is byte-identical to today's (tested); each knob and the table
  are tested per role; a sentinel implementer note never reaches a reviewer's or verifier's pack; Knowledge never
  enters a pack (Arm B not measured).
- **Probe:** `r8-pack-arms` (A to E), after M4-H.
- **Before M4-H:** yes, off by default; not in M4-H's treatment.
- **Operator or designer action:** none.

### D6. F36, part 1: the bounded handoff note

- **Owner:** F36. **Class:** implementation-local refinement. The R2 recommendation it builds came from research that
  is not in this repository; the record's §6 is its governing text here.
- **Depends on:** nothing.
- **New work:** an optional `handoff_note` in the role report (evidence schema), worker-authored, at most 2 KiB, a
  claim that may cite paths and evidence ids; delivered to a replacement invocation's pack as delimited reference data
  labelled as its predecessor's claim; never read by a gate, a transition or dispatch; not a field any Knowledge
  capture template admits, so it never becomes Knowledge automatically. The card text that tells a worker about it and
  the pack delivery are both behind one switch.
- **Sequencing change:** new row, **M4 candidate**, a parallel lane.
- **Done when:** its conformance tests pass (no authority path reads it; a replacement invocation receives it bounded
  and labelled; an over-size note is refused at submit as other schema violations are); with the switch off, cards and
  packs are byte-identical.
- **Probe:** `r2b-coherence` arm "note", after M4-H.
- **Before M4-H:** yes, off by default.
- **Operator or designer action:** none.

### D7. F15.8: the `aew-run` read half

- **Owner:** F15.8, split from F15.3. **Class:** existing item — priority/sequence change (operator approval, record
  §10.1).
- **Depends on:** the run bridge (built, `bridge.OPERATIONS`); F22.1's structural core (built); D4 for
  `map.tests_for` and `map.constraints`; E12 (`aew evidence show`, decided 2026-10-06, not built) for `evidence.show`.
- **New work:** the role-side server inside the sandbox over the existing bridge, the credential staying with the
  supervisor; `whoami` and `check.run` as tools; read rows for map search (exact resolution first, then a
  workspace-rooted lexical fallback), `map.symbol`, `map.callers` and `map.callees` (`NOT_SUPPORTED` until a semantic
  extension covers the language), `map.tests_for`, `map.constraints`, `map.changed`, `evidence.show` and
  `check.suggest`; one result envelope across them; the profile's `tools.presentation`; raw tools untouched.
- **Sequencing change:** pulled ahead of M6a (it was M6); **M4 candidate**, a parallel lane. F15.3 keeps typed `submit`
  and the `aew-knowledge` namespace rules.
- **Done when:** no request can name an invocation, run or credential, and the credential is never inside the sandbox
  (the bridge's existing invariant, extended to every new row); the envelope is a closed schema and each operation's
  terminal states are tested; a lexical search outside the authorized workspace is refused, and a worker never has to
  pass a root (Revision A); with the switch off, the run's harness projection is byte-identical.
- **Probe:** `r9-intent-surface` (raw-first, neutral, typed-first), after M4-H; the lower-bound lane may use it as an
  assisted arm before, as qualification only.
- **Before M4-H:** yes, off by default.
- **Operator or designer action:** none (approved).

### D8. F30's first slice: the completion-impact nudge (E1)

- **Owner:** F30, fed by F22.3. **Class:** existing item — priority/sequence change.
- **Depends on:** F22.1 (built) for the generated, vendored and co-change relations; D4 for tests and constraint
  locators; M4-E E5b (`ticket_request_review`) for the pre-review hook.
- **New work:** `aew impact --changed` on demand: at most eight high-confidence related-but-untouched surfaces with the
  omitted count, uncertainty and coverage first, each relation kept only while its effective false-positive rate stays
  under 10%; the worker's dispositions in `self_review.related_surfaces` (addressed, unaffected or unsure) and
  `surface_sha256`; the reviewer's pack renders the same surface by hash; then the hook before `request_review`, behind
  a switch.
- **Sequencing change:** F30's first slice is defined and brought ahead of the full impact evaluation.
- **Done when:** the command and the report field are tested on seeded changes; no gate, transition or dispatch reads a
  disposition (advisory, never a gate because something is related); off by default, cards and packs are unchanged.
- **Probe:** `e1-completeness-nudge`, after M4-H: false positives per relation and the dismissal rate decide whether it
  stays on demand.
- **Before M4-H:** the command, yes; the hook only after E5b, off by default.
- **Operator or designer action:** none.

### D9. F15.9: the Lead's `changes` query (E2)

- **Owner:** F15.9, on the typed Lead surface's catalog. **Class:** implementation-local refinement.
- **Depends on:** M4-E E3 (the StageIntent journal; E3a merged, E3b in #142) and E4 (the guards); ADR-0012's outbox
  reader (built); U1 for the second cursor (D10), optional at first.
- **New work:** the catalog row (read class), `since_revision` against the outbox's committed transitions plus the
  projection's derived deltas, the always-present section (decisions required, blockers, supervision candidates when
  F9-C exists), one line per item with an expansion reference, a size cap. `status` and `resume` are unchanged.
- **Sequencing change:** targeted **M5** with F11 and F9; it may be built after E4.
- **Done when:** a test replays a sequence of commits and shows every material change appears exactly once since the
  cursor; the full view is unchanged; it is not in the normal advertised Lead surface (it is catalogued like the
  generic `cli` action, under a non-default surface profile) until its probe reports.
- **Probe:** `e2-delta-first` inside F9-D's harness.
- **Before M4-H:** buildable after E4, never advertised in M4-H's treatment.
- **Operator or designer action:** none. The catalog addition is the record's §8 direction.

### D10. U1/H1: `repetition` and `observed_through`

- **Owner:** U1 (the health projection, **M4 candidate**). **Class:** implementation-local refinement.
- **Depends on:** U1 itself (not built; out of M4-E, plan v3 §0).
- **New work:** when U1 is built: a `repetition` field (drift read from trajectory shape, which today's telemetry
  supports) and the telemetry watermark returned as `observed_through`.
- **Sequencing change:** none to U1.
- **Done when:** U1's own tests cover both fields.
- **Probe:** `r2b-coherence` reads `repetition`; `e2-delta-first` uses the watermark.
- **Before M4-H:** as U1 is scheduled; health is not part of M4-H's treatment unless U1 is.
- **Operator or designer action:** none.

### D11. F36, part 2: the recitation

- **Owner:** F36. **Class:** implementation-local refinement.
- **Depends on:** D6 (it restates the latest note); D10 (its trigger reads health); M4-E E3 and E4.
- **New work:** the supervisor assembles the recitation at zero model cost from canonical and derived state (the goal
  or active criterion, the remaining criteria, plan tasks, changed files against the planned scope, checks performed,
  open findings and blockers, the latest note) and delivers it through the run's inbox, recorded like `harness send`,
  when `recitation.calls`, `recitation.elapsed_s` or `recitation.every` (operational) is crossed; trivial Tickets never
  cross it. Never a Lead action: it costs no Lead tokens.
- **Sequencing change:** new; after D6 and D10.
- **Done when:** tests show it carries only derived state, is bounded, is recorded, and never fires below the
  thresholds; off by default.
- **Probe:** `r2b-coherence` arms "recite" and "recite plus the Lead's view", after M4-H.
- **Before M4-H:** buildable, off by default.
- **Operator or designer action:** none. Under F9-A (once adopted) it becomes a durable instruction message.

### D12. F21 after Arm B: knowledge on the read surface

- **Owner:** F21, hosted by F15.8. **Class:** existing item — no change.
- **Depends on:** Arm B's measured A/B result (the prototype is #148, open, CLI-side only and refused inside
  invocations); D7.
- **New work:** `knowledge.search` and `knowledge.get` as read rows on the same bridge, under the role matrix's request
  binding (the reviewer-independence filter, KDR-03 to KDR-05).
- **Sequencing change:** none.
- **Done when:** F21's readiness package and Arm B's gate say so.
- **Probe:** R8's arm D; R9's history questions.
- **Before M4-H:** no. Knowledge is not injected into any pack before Arm B's evaluation earns it.
- **Operator or designer action:** none new.

### D13. F9 once F9-A1 is adopted

- **Owner:** F9. **Class:** existing item — no change.
- **Depends on:** the decisions-due adoption of F9-A1 (already ingested, PR #145).
- **New work:** none now. On adoption: the recitation becomes an F9-A instruction; the worker-published `working_note`
  is F9-B's; F9-C's supervision candidates ride `changes`; `e2-delta-first` runs inside F9-D.
- **Before M4-H:** not scheduled.
- **Operator or designer action:** the existing F9-A1 adoption item, unchanged.

### D14. The post-gate probes

- **Owner:** F19. **Class:** F19 probe.
- **Depends on:** M4-H's gate; D2; each probe's own items (D1 and D4 to D11).
- **New work:** preregister `r8-pack-arms`, `r9-intent-surface`, `r2b-coherence`, `e1-completeness-nudge` and
  `e2-delta-first`, one factor each, with the capability class as a blocking variable; report raw against assisted per
  class and the cost per correctly accepted outcome across classes; the primary measure is the independently verified,
  correctly accepted outcome.
- **Done when:** each probe reports; only then may an aggressive mode (typed-first, explicit orientation, the nudge
  before review, delta-first) become a default, by its own register change.
- **Before M4-H:** no.
- **Operator or designer action:** none new; budgets are preregistration values.

### D15. F4: the designer's ruling on parent changes

- **Owner:** F4. **Class:** editorial contract clarification.
- **Depends on:** F4's plan (being drafted).
- **New work:** the plan builds the record's §15: a revision may not move a committed Ticket to another parent, even
  before work starts (a replacement with explicit lineage does); a draft may correct its parent before its identity
  governs; KC §9.4 promotion stays a separate operation that keeps the Ticket's identity, evidence, class floor and
  inherited gates; ambiguous re-parenting fails closed until the implementation text is updated. It is consistent with
  the adopted amendment, which already requires a new Ticket when the parent changes (TRA-07).
- **Done when:** F4's plan cites it and its tests cover the refusal and the draft correction.
- **Before M4-H:** independent of it.
- **Operator or designer action:** none; the ruling is the designer's, recorded.

### D16. E19: the re-freeze lines

- **Owner:** E19 (the WC/KC re-freeze). **Class:** editorial contract clarification.
- **New work:** the lines synthesis §7 lists (locations as labelled locators in the implementer pack, independent
  review excluding implementer working state, the handoff note as a bounded claim for a successor) and record §15,
  folded into the re-freeze; the decisions-due E19 item now names them.
- **Operator or designer action:** the existing E19 item, extended.

## 4. Implementation-local choices

Each is the simplest conservative option consistent with the governing texts; any of them can be revisited in the
pull request that builds it.

1. **The locate operation is `map.search`.** Project maps v0.5 §7 freezes `map.search(text|pattern)` as the locator, so
   the record's `map.find` takes that name, with exact resolution first and Revision A's workspace-rooted lexical
   fallback beneath it; a hit stays a candidate (§7.4). `map.tests_for`, `map.constraints` and `map.changed` are new
   names for T5-D's indexes and the worktree diff.
2. **One switch per item, off and absent by default**, with a byte-identity test while off, the pattern of #143 and
   #148.
3. **A3 classes.** A field that changes what a dispatched role receives (`context.*`, `tools.presentation`, the read
   half's switch, the handoff note's delivery) is `legality_affecting`, as #143 classes `maps.pack_slices`, so a
   change fails closed; the recitation's timing thresholds are `operational`. The synthesis proposed all of them
   operational; this is the more conservative reading of A3, reversible by an ADR-0010 amendment if it causes churn.
4. **The handoff note** is bounded by the schema and refused when over size, as other schema violations are; no
   capture template admits it.
5. **The session-database reader** lives on the evaluator side only; its retention window has no default, so an
   experiment that does not set one cannot read.
6. **`changes` visibility** follows the typed Lead surface's precedent for the generic `cli` action: catalogued, not
   in the normal advertised surface.
7. **The pre-review nudge** is first an on-demand command; the stage hook comes after E5b, behind a switch.

## 5. True design gaps

**None.** These were examined and are not gaps:

- **The `changes` catalog addition.** The synthesis said the designer signs it; the record's §8 is the designer and
  operator's direction to add it, and §5 leaves exact names implementation-local.
- **`map.find` against the frozen map surface.** Resolved by using the frozen name (§4 item 1).
- **The reviewer's layout row against the operator's M4-H decision of 2026-10-07.** It ships off; wider serving earns
  itself through evaluation, as that decision requires.
- **Synthesis §8's "worth landing before M4-H" against Revision B.** Revision B governs: building may land, the
  treatment does not move, and nothing is proposed for it.
- **The R2 note has no source in this repository.** The record's §6 now states its properties.
- **The handoff note against knowledge capture triggers.** No capture template admits the field, so it never becomes
  Knowledge automatically.
- **Re-parenting.** The adopted Ticket-revision amendment already requires a replacement when the parent changes; §15
  clarifies the timing and separates promotion.

## 6. Consistency with work in flight

- **#143 (F22.1 PR B):** unchanged by this plan; D5's reviewer row and slice rendering start after it merges.
- **#148 (F21 Arm B prototype):** unchanged; knowledge reaches workers only through D12, after Arm B is measured.
- **#142 and the M4-E plan v3:** no slice changes; F15.3's role server stays out of M4-E (plan §0) and F15.8 is a
  separate lane; D9 waits for E3 and E4, D8's hook for E5b.
- **F4's plan:** takes D15.
- **M4-H's prerequisites** (F15.5/F15.6, F19's split, F25's telemetry): priority unchanged.

## 7. What changed in the register and the ledger

- **New rows:** F15.8 (the read half), F15.9 (`changes`), F35 (pack serving), F36 (weak-worker continuity).
- **Raised:** F22.3 to **M4 candidate**. **Notes added:** F4, F9, F11, F13, F15.3, F18.13, F19, F20.7, F21, F22.3,
  F30, F32, F34, E19, U1. The decisions-due E19 item names the re-freeze lines.
- **Ledger:** the adoption record is source AEA (AEA-01 to AEA-45; AEA-32, AEA-35 and AEA-44 done) and the synthesis
  source AES (AES-01 to AES-25, with what the record adopted carried by AEA ids).
