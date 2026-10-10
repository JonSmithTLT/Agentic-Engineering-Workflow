# Agent effectiveness and model leverage: synthesis

v0.1 — 2026-10-09 — Fable. Threads: `R8-context-compilation.md`, `R9-intent-capability-resolution.md`,
`R2B-working-state.md`, `E1-E2-integration.md`. Evidence: `R-corpus-evidence.md` (the kept M3 run trees and the 68
dogfood records, read-only probes in `probes/`), `seams-supervision-and-evaluation.md` (the supervision and evaluation
seams at origin/main `099a4df`), `external-evidence.md` (50 external sources, 2023–2026). Brief:
`00-research-threads-v0.1.md` and `00-researcher-prompt-v0.1.md`.

**Status:** research input, not governing. Written sanitized so it can move into the AEW repository under the
ingestion gate; it names no private project. Model names are evaluation targets.

---

## 1. Executive recommendation

AEW does not need a new product layer for agent effectiveness. It needs to **finish three substrates it has already
designed, connect them to the pack and the worker bridge it already has, and measure five small things.** Every
mechanism the brief proposes resolves to an existing owner: the context "compiler" is the pack generator with three
missing inputs; the intent surface is `map.*`, `knowledge.*` and `aew-run`; working state is the already-recommended
handoff note plus an AEW-authored recitation; the completeness nudge is the first slice of `aew impact`; delta-first
attention is one typed query over the outbox. No new store, no new authority, no new component, one catalog addition
for the designer, and a handful of operational knobs on the execution profile.

Three findings should change how the operator reads the brief:

1. **The platform should own the structure, not the model.** The one controlled study of model-maintained working
   state found it hurt six of ten models at long horizons and helped none; the studies that show large gains for
   weak models are platform-owned scaffolds (explicit planning +11.6 points for a 30B-class model; typed tools +15 to
   +23 points). AEW's Deterministic Work Conservation principle is therefore also the right answer to R2-B: derive what
   can be derived, restate it, and ask the model to maintain nothing.
2. **Helpers beside raw tools, with presentation tuned per profile; never a facade in front of a strong model.**
   Typed tools *forced* on frontier models cost them 22–25 points and 19–72% more tokens in the 2026 bash-only
   study, while the same tools gave 30B-class models +15 to +23 points; a free LSP was used 0–6% of the time for
   localisation by strong models and chosen about half the time for reference tasks, where it helped. So the typed
   operations, maps, Knowledge and raw tools are all *available* to every profile, and only the presentation (how
   much orientation is in the pack, whether typed operations are advertised first) is a per-profile operational
   knob. The brief's hope that Astra "rationally prefers" the helper for ordinary questions is likely to be
   falsified; the measured question is which policy makes each capability class spend the most inference on
   engineering, and the stop conditions already cover the answer "raw-first for the frontier profile".
3. **AEW's own telemetry cannot measure most of the brief's secondary metrics**, by design: the run log records tool
   names, never inputs (M3-D3). The corpus probe found the inputs intact in the harness's own session database inside
   every kept run directory (paths, patterns, commands, millisecond timestamps, outputs), so the instrumentation every
   probe here needs is an evaluator-side **reader** of that file under F19's hidden-evaluator rules, not new capture.
   It is still an operator decision, because the database holds model-issued commands and tool outputs and exists only
   while `local/` is kept.

The corpus (`R-corpus-evidence.md`: 68 dogfood records, 75 role runs with full tool arguments, two models, a 12-file
fixture, no weak-model run) confirms the brief's framing without confirming its hypotheses. Orientation cost is real
and small: a median 1 call and 3 s to the first relevant file, and **0 calls when the Ticket named the file**, which
makes declared anchors the orientation that works. Reviewers, whose pack has the diff but no layout, read
non-existent guessed paths 17 times in 11 of 16 runs. The one costly orientation failure was the Lead's: its shell
allow-list refused `git ls-files`, it declared a template scope without the code's directory, and an implementer run
and a Ticket were lost. Drift, re-reads and "missed related file" findings are all zero on runs of 5–12 steps; the
Lead re-reads full state rarely (identical reads within 30 s: 0) and spends 61% of its wall time blocked in
`harness wait`, with 29–31 of 35 commands mechanical. The two gate-passing failures AEW has recorded were a *missing
environment binding* (M3-D6) and a *wrong plan* (T4), both mandatory-tier defects that richer orientation would not
have fixed and the second of which richer orientation would have made more convincing. Anchoring is the risk AEW has
seen; thin orientation is the risk the brief predicts for weaker models; both are arms of the same experiment.

## 2. R8 — Task context compilation

**Disposition:** NO CHANGE to ownership; IMPLEMENTATION-LOCAL serving policy, rendering convention, budget and
orientation knobs, independence filter; BUILD the three planned inputs (F22.1 PR B, T5-D) in R8's order; PROBE the pack
arms in T5-E on Q7's families; REJECT a named compiler and automatic Knowledge injection before M6b Arm B is measured.

**Architecture (R8 §3–§6).** The owner is `ContextPacks` + `knowledge/context.py`: deterministic, hashed sources,
tiered budget (E29), role-shaped by archetype `context.knowledge`, independence by construction. What is added:

- a per-role, per-tier **serving-policy table** as archetype data (mandatory / opportunistic / on-demand /
  prohibited; R8 §4), test-enforced;
- a **rendering convention** for derived sections: `source, revision, freshness, coverage` in the heading, one flat
  item per line with an `expand:` pointer to the typed operation, degraded sections as one labelled line, criteria
  repeated last under `orientation: explicit`;
- the **budget actually passed** from the execution profile (`context.budget_chars`, `context.orientation_max_chars`,
  `context.orientation: minimal|standard|explicit`), all `operational` under F15.4;
- the **independence filter** at two points (the pack's prohibited rows; a source-kind exclusion on the reviewer's and
  verifier's Knowledge request binding), with sentinel tests; reviewers keep canonical same-Ticket history
  (K-IMPL-1);
- inputs in order of value per cost: structural rows for scope paths with freshness (F22.1 PR B, the switch), the
  reviewer's layout row and the structural map in the Lead's resume (the two rows the corpus itself justifies), tests
  naming scope paths and constraint locators (T5-D), L1 symbol rows for plan `affected_paths` (T5-B, deferred until
  the repository's language has an extension), Knowledge only as a tool until Arm B is measured.

**Experiment (R8 §7):** arms A (today), B (structural switch), C (B + test and constraint locators), D (C + Knowledge
tool), E (C under `explicit` with a profile budget); cases from Q7 F1/F2 plus small-task, stale-orientation,
partial-map and wrong-plan controls; weak and strong profiles; primary measure correctly accepted outcome; stop if
nothing beyond B moves outcomes or orientation cost, and fail any arm that raises stale reliance or anchoring.

## 3. R9 — Intent-level capability resolution

**Disposition:** NO CHANGE to the designs; IMPLEMENTATION-LOCAL result envelope, exact-first `map.find`,
`check.suggest` and `evidence.show` on the bridge, presentation knob; BUILD the `aew-run` read half ahead of M6a and
T5-D; PROBE three presentation arms; REJECT a single semantic facade, a free-text `repo.related`, a `repo.search`
operation, and worker-side `work.inspect`.

**Architecture (R9 §2–§5).** Eleven operations in three namespaces, ten already designed:

```text
map.find  map.symbol  map.callers  map.callees  map.tests_for  map.constraints  map.changed     (T5)
knowledge.search  knowledge.get                                                                 (M6b Arm B)
evidence.show  check.suggest   (+ whoami, check.run, submit)                                     (aew-run)
```

One result envelope (T5 §7.2's terminal state, coverage, freshness, evidence locators, omitted counts) across all
three; resolution exact → stored relation → labelled weaker evidence → `NOT_SUPPORTED`, never to a model; provider
choice below the operation, in F13; delivery by adding rows to `bridge.OPERATIONS` and the F15.3 stdio server, the
credential staying supervisor-side; raw tools unchanged and the `repo.*` names as L0 awareness text; `tools.
presentation: typed-first | neutral | raw-first` on the profile.

**Experiment (R9 §7):** arms raw / both / typed-first on a deterministic question set (locate, tests, impact, history,
validation, unsupported) plus Q7 F1 tasks; weak, mid and strong profiles; voluntary typed use measured from bridge
outcome counts under ordinary discoverability only; stop if the strong profile is better raw and the weak profile does
not improve.

## 4. R2-B — Weak-model working state

**Disposition:** NO CHANGE; BUILD the R2 handoff note (reaffirmed, still unbuilt); IMPLEMENTATION-LOCAL recitation,
deterministic progress block in `harness_status`, repetition field in H1's note; PROBE recitation on Q7 F2; DEFER the
worker-published `working_note` to F9-B; REJECT a model-maintained structured state, mandatory refresh, and any
working-state store.

**Architecture (R2-B §3).** Split the brief's fields: goal, criteria and plan tasks are durable and restated by AEW; progress
(changed vs `affected_paths`, checks recorded) is derived; facts and hypotheses are the model's and stay in its scratch
or its ≤ 2 KiB handoff note. A **recitation** (criteria, plan tasks, progress, last note, open findings, "say which
criterion your current step serves") is assembled by the supervisor at zero model cost and delivered through the inbox
on a runtime trigger (calls or elapsed), recorded like `harness send`; under F9-A it becomes a durable `instruction`.
Trivial Tickets never cross the trigger. Drift is measured by trajectory shape (length, variance, tool-name repetition),
which AEW's existing telemetry supports.

**Experiment (R2-B §6):** arms none / note / recite / recite + Lead progress view; cases from Q7 F2 plus seeded
multi-criteria, disproven-hypothesis, interrupted, cross-ticket, distractor and a trivial control; stop if recitation
does not reduce repetition, forgotten criteria or restarts, or raises stale-note reliance.

## 5. E1 and E2 — integration recommendations

**E1** (E1-E2 §E1): the first slice of F30's `aew impact --changed`, showing only relations that clear a 10% effective
false-positive bar (tests naming a changed symbol or path, changed generated or vendored files, schema and constraint
locators naming a changed symbol, git co-change above a support and confidence threshold, compiler-known callers when a
semantic extension exists), uncertainty first, at most eight items with the omitted count; the worker dispositions each
item in `self_review.related_surfaces` (`unaffected | addressed | unsure`); the reviewer's pack renders the same surface
by hash; F9-C turns undispositioned items into a candidate reason. Never a gate. Probe on Q7 F1 with a localized
control; drop any relation above the bar; stay on-demand if the dismissal rate exceeds 25% or nothing is caught.

**E2** (E1-E2 §E2): one typed `changes {since_revision, since_observed?}` query over `outbox.read_transitions` plus
the projection's derived deltas (newly available actions, newly bound decisions, run and health transitions, new
submissions and check results, commits since per worktree, the R2-B progress block, F9 messages when they exist), a
suppression list, an always-present section (decisions required, blockers, supervision candidates), one line per item
with an `expand:` ref, a size cap; `status` and `resume` unchanged as the full view; the cursor is the revision the
Lead already holds, the second cursor is U1/H1's telemetry watermark. No store. Probe as the Lead-surface factor in
F9-D's A/B/C/D; default-on only after measurement.

## 6. Overlaps and contradictions among the mechanisms

| Overlap | Resolution |
|---|---|
| R8's opportunistic rows and R9's on-demand operations deliver the same data | The pack is L0/L1 for **declared** anchors only (scope paths, plan `affected_paths`, the diff); everything else is a tool; every pack row carries the operation that expands it, so nothing is paid twice |
| E1's surface, R8's reviewer in-scope/outside row, F9-C's coverage reason | One computation (`aew impact --changed`, `surface_sha256`), three consumers |
| R2-B's progress block, E1's changed-vs-plan, E2's commits-since | One diff of the worktree against the plan, computed in `harness_status`, reused |
| E2's `changes`, F20.7's `/events`, `harness_wait` | One outbox reader, one cursor |
| R9's `work.inspect` and E2 | Lead-only; a worker never inspects a peer |
| R8's model-aware context vs rule 10 (no model-name semantics) | Operational profile knobs (`context.orientation`, `tools.presentation`); the probe maps profiles to levels |
| E1's dispositions vs R8/R2-B's "keep weak-worker ceremony down" | The localized control in E1's probe sets a token bound; above it E1 stays on demand |
| R9's "Astra should prefer the helper" vs recall §18 "do not force lookup" and the frontier evidence | Measure preference under ordinary discoverability only; expect it to fail for strong profiles; `raw-first` presentation for them |
| R2-B's recitation vs F9's "no forced standups" (F9-A1 invariant 20) | Recitation is a bounded message on an observable trigger, not a supervision act; it costs no Lead tokens |
| R8 §5's independence filter vs the adoption decision's "lookup is a normal capability for all roles" | Reviewers and verifiers keep the capability; the request binding filters implementer prose kinds for the Ticket under review, nothing else |

**Contradictions with the brief:** (i) the brief treats a richer pack as the default direction; the T4 case and the
context-rot evidence say richer context can poison, so B (the structural switch) is the only candidate default before
measurement; (ii) the brief lists `repo.related` and `repo.search`; both are rejected as operations; (iii) the brief
asks whether working state should be model-maintained; the evidence says no.

## 7. Changes required to existing AEW designs

None governing. What is required, by owner:

| Change | Kind | Owner |
|---|---|---|
| Archetype schema: `context.orientation` tiers beside `context.knowledge`; a conformance test per role | implementation (ADR-0006 territory, not an amendment) | roles |
| Execution profile schema: `context.budget_chars`, `context.orientation_max_chars`, `context.orientation`, `tools.presentation`, `recitation.{calls, elapsed_s, every}`, all classified `operational` | implementation (ADR-0010; F15.4 classification) | policy |
| Evidence schema: optional `handoff_note` (R2), `self_review.related_surfaces[]` and `surface_sha256` (E1) | implementation | evidence schema |
| `bridge.OPERATIONS`: read rows for `map.*`, `knowledge.*`, `evidence.show`, `check.suggest`; the `aew-run` stdio server (F15.3) | implementation, **sequencing change** (read half before M6a) | F15.3 |
| Typed Lead surface catalog: one query tool `changes` (or `since` on `status`) | **catalog addition the designer signs** (typed Lead surface v0.2 §3.1 is the v1 catalog) | designer |
| H1 implementation note: a `repetition` field; the telemetry watermark returned as `observed_through` | implementation note addition | U1/H1 |
| F30 (`aew impact`) first slice scoped to the E1 relations; the reviewer row | register row refinement | F30, T5-D |
| F19: an evaluator-side reader of the run's harness session database (tool arguments, timestamps, outputs); `metrics.py` functions for orientation, repetition, omissions, Lead reads (the corpus probes are their first draft) | implementation, **operator decision** on reading and retention | F19 |
| Register: F22.3 (T5-D) priority raised; F15.3 split into read half and typed `submit`; F9-A1 ingested (it is untracked and un-ingested today) | register and ledger | operator, designer |
| E19 re-freeze notes: KC §15.4 locations delivered as labelled locators; WC §10.1 excludes implementer working state; a role's handoff note is a bounded claim for its successor (WC §9.10 analogue) | editorial, at the re-freeze | designer |

## 8. Implementation sequencing

Ordered by dependency and value, each step shippable alone:

1. **Now, no new design:** F22.1 PR B (structural slice, switch off by default; the resume row answers the Lead's
   layout question) → the reviewer's layout row → wire the pack budget and `context.orientation` from the profile
   (E29 completion) → the R2 handoff note and its two conformance tests → the derived-section rendering convention →
   the F19 session-database reader (operator decision first; the corpus probes are its draft).
2. **T5-D** (test index, constraint locators) → `aew impact --changed` first slice with the generated and co-change
   relations (both need only PR A and git) → E1's report field and contract line → the reviewer's in-scope/outside row.
3. **F15.3 read half** (`aew-run` stdio server; bridge rows for `map.find/symbol/tests_for/constraints/changed`,
   `evidence.show`, `check.suggest`; the envelope) → R9's arms become runnable.
4. **After M4-E E3/E4** (journal and guards): the `changes` query on the Lead surface; steering and usage as derived
   kinds; U1/H1 with the watermark and `repetition`; the recitation trigger reads health.
5. **F9-A** messaging → recitation as a durable message; **F9-B** `working_note`; **F9-C** candidates ride `changes`.
6. **M6b Arm B** → `knowledge.search/get` on the bridge → R8 arm D and R9's history questions.
7. **Evaluation:** T5-E pack arms (R8) and R9 arms after M4-H on Q7's families with a weak and a strong profile;
   R2-B on F2; E1 on F1; E2 inside F9-D.

Nothing here gates M4-H; steps 1–2 are the only ones worth landing before it, and only because the structural switch
and the test index make the M4-H AEW arm representative of the product (T5 §13.2).

## 9. F19 evaluation matrix

| Experiment | Factor | Arms | Families / controls | Profiles | Primary | Key secondary | Prerequisite | Stop |
|---|---|---|---|---|---|---|---|---|
| `r8-pack-arms` | pack content and budget | A today, B structural, C + locators, D + Knowledge tool, E explicit | Q7 F1, F2; m3 small; seeded stale-orientation, partial-map, tests-heavy; T4 replay; reviewer independence | weak, strong | correctly accepted | orientation calls/tokens, repo-wide searches, missed surfaces, stale reliance, anchoring, pack chars | PR B; T5-D for C; Arm B for D; F19 capture | nothing beyond B moves outcome or cost |
| `r9-intent-surface` | tool presentation | raw, both, typed-first | deterministic question set (6 kinds); Q7 F1 tasks | weak, mid, strong | correct answer; correctly accepted | tool calls/question, voluntary typed use, escape rate, coverage misreads | F15.3 read half; T5-D; map-covered repo | strong better raw and weak not improved |
| `r2b-coherence` | working-state support | none, note, recite, recite + Lead view | Q7 F2; seeded multi-criteria, disproven, interrupted, cross-ticket, distractor; m3 trivial control | weak, strong | correctly accepted | forgotten criteria, repeated n-grams, repeated reads, restarts, stale-note reliance, recitations | handoff note; recitation; F19 capture; F9-A for D | no drift reduction or stale reliance up |
| `e1-completeness-nudge` | completion self-check | none, on-demand, self-check, + radius 1 | Q7 F1, F2; seeded tests-heavy, new-file; m3 localized control | weak, strong | correctly accepted | omissions caught, effective FP rate per relation, dismissal rate, disposition cost | `aew impact --changed`; report field | FP > 10% on control, dismissal > 25%, or zero catches |
| `e2-delta-first` | Lead read surface | full, delta available, delta-first | Q7 F1/F2 at 3 parallel Tickets; seeded blocker, sibling finding; m3 single control | Astra-class Lead, weak workers | correctly accepted per Ticket | Lead tokens and turns per Ticket, full reads, time to react, missed developments | `changes`; U1; U4 or evaluator accounting; F9-D harness | missed developments up or `status` after > ½ of `changes` |

Common rules: one factor per experiment (F19 principle 7); cases from the M4-H families only while unexposed
(decision 7); hidden-evaluator scoring under the held-out isolation rule; `aew_facts` from `aew history log --since`;
cost from F25 projections; every new metric a named, versioned function in `metrics.py`. **Profiles are capability
classes, not models** (designer addendum, §13): `frontier`, `mid`, `lower-bound`; the "weak, strong" columns above
read `lower-bound, frontier`, with `mid` added where budget permits. Each run records `{provider, model, harness,
effective_profile, qualification_state}` in the F19 run record's `profile{requested, observed}` block. Results are
reported per class as *raw vs assisted*, never as a leaderboard across classes (§13.3).

**The lower-bound lane comes first.** The corpus contains none of the failure behaviour that motivated this work
(§1), and free OpenCode profiles cost almost nothing, so the seeded lower-bound task set (§13.4) runs before the
M4-H-family cases, on non-held-out fixtures, to establish that the behaviours exist and that the metrics detect them.
A lane in which the lower-bound profile shows none of the eight behaviours cannot tell AEW whether the scaffolding
helps, and the next-cheaper profile is tried.

## 10. BUILD / PROBE / DEFER / REJECT

**BUILD**
1. F22.1 PR B as planned (the structural slice and switch) — R8 arm B.
2. T5-D test index and constraint locators, priority raised — R8 C, R9 `tests_for`/`constraints`, E1.
3. The R2 handoff note and its conformance tests — R2-B.
4. `aew impact --changed` first slice (generated, co-change, tests-by-name, schema/constraint locators) with
   `self_review.related_surfaces` — E1.
5. `aew-run` read half ahead of M6a (bridge rows, stdio server, result envelope, `map.find`, `check.suggest`,
   `evidence.show`) — R9.
6. Pack budget and orientation knobs; serving-policy table; rendering convention; independence filter — R8.
7. The recitation (supervisor-assembled, inbox-delivered, recorded) with operational thresholds — R2-B.
8. The `changes` query over the outbox (after E3/E4; the designer signs the catalog addition) — E2.
9. The F19 evaluator-side reader of the run's harness session database, and the metric functions the corpus probes
   drafted (operator decision) — all probes.
10. The reviewer's layout row and the structural map in the Lead's resume, with F22.1 PR B — the two pack rows the
    corpus itself justifies.

**PROBE** (preregistered on F19, after M4-H): `r8-pack-arms`, `r9-intent-surface`, `r2b-coherence`,
`e1-completeness-nudge`, `e2-delta-first` (§9).

**DEFER**
- L1 symbol rows in packs until T5-B covers the repository's language.
- Knowledge in packs (`CONTEXT_ROUTING`) until M6b Arm B is measured (adoption decision §7).
- Worker-published `working_note` until F9-B; supervision candidates until F9-C; the `repetition` field until U1/H1.
- Impact anomalies and scheduler recommendations in the delta until the anomaly record (M4-E) and F11 (M5).
- Default-on for `typed-first`, `explicit` orientation and `delta-first` until their probes report.
- A crash-surviving attention cursor until takeover semantics need it.

**REJECT**
- A named context compiler or router component.
- Automatic Knowledge injection before Arm B.
- A single semantic facade; free-text `repo.related`; a `repo.search` operation; worker-side `work.inspect`.
- Model-maintained structured working state; mandatory self-refresh; a working-state store or record kind; Lead
  access to raw scratch or harness sessions.
- A completeness gate or a relation-derived required test.
- A second event log or state store for attention; stored past projections.
- Model-name semantics anywhere in policy.

## 11. Operator decisions genuinely required

1. **The concrete profiles and their budget.** Laguna is not a prerequisite (designer addendum). What the probes need
   named and qualified at preregistration is: one frontier profile; one mid profile on the operator's OpenAI API
   account; one or more OpenCode free lower-bound profiles. Which models, how many lower-bound profiles, and what
   budget the three-class lanes get beyond M4-H's single-model gate are the operator's call; nothing else in this
   synthesis depends on the choice.
2. **Evaluator-side reading of the run's harness session database.** The file already exists in every run directory
   (`harness/xdg-data/opencode/opencode.db`) and holds the paths, commands, timestamps and tool outputs AEW's own log
   excludes by design (M3-D3). The corpus probes read it immutable and read-only for this research. Making that a
   standing F19 metric source means an evaluator process reads model-issued commands and outputs after every
   experimental run, and means `local/` must be retained until scoring; AEW itself would still never read it
   (ADR-0009). Whether that is acceptable, and for how long the databases are kept, is the operator's to set.
3. **Pulling the `aew-run` read half ahead of M6a.** F15.3 is scheduled at M6; its read half has no dependency on the
   M6a registry. Landing it with T5-D changes a milestone's scope, which is the operator's authority.

Everything else here is implementation-local or the designer's (the `changes` catalog addition; the E19 editorial
lines; F9-A1's ingestion).

## 12. The simplest system that captures most of the benefit

Five small things, no new component:

1. **A pack with locators, and a Lead that can name files.** Today's pack, plus for the paths in scope: the
   structural rows with freshness, the tests that name them, the constraints that mention them, each line with the
   operation that expands it, under a profile budget, criteria repeated last for weak profiles; the reviewer gets the
   layout of the diff's directories; the Lead gets the structural map in `resume` and `map.find`, so Tickets name
   their files, which is the one orientation the corpus shows removes the cost entirely.
2. **Seven typed reads for workers** through the bridge that exists: `map.find/symbol/tests_for/constraints/changed`,
   `evidence.show`, `check.suggest`, with one envelope that always says what it did not cover; raw tools untouched.
3. **A recitation on long runs**, assembled from the pack and the diff, delivered through the inbox, and the handoff
   note on attempt two. Nothing the model must maintain.
4. **One `aew impact --changed`** at completion, high-precision relations only, dispositions in the report, the same
   list in the reviewer's pack.
5. **One `changes` query** for the Lead over the outbox, with the decisions that are its own always on top.

That is what the brief's "better deterministic context + navigation + knowledge access + capability routing +
working-state support + completion feedback + Lead attention projection" reduces to once the existing designs are
counted. The measurement that decides whether any of it earns a default is one F19 lane per item on Q7's task
families with one weak and one strong profile. If the lane shows nothing beyond the structural slice, the right
outcome is to keep the slice and stop.

## 13. Designer addendum (2026-10-09): profiles, presentation and the lower-bound lane

The addendum (`00-designer-addendum-v0.1.md`) arrived after the first draft of this synthesis. It confirms the
profile-neutral knobs already proposed (`context.orientation`, `tools.presentation`; no model names anywhere) and
changes the evaluation plan in four ways, applied here and in each thread note's preregistration sketch.

### 13.1 Profiles are capability classes

| Class | Reference behaviour | Source for the current environment | Role in the probes |
|---|---|---|---|
| `frontier` | strong reasoning, strong independent navigation (Astra-class) | the operator's frontier lane | conservation of frontier effort; detection of scaffolding that harms |
| `mid` | capable general coding/reasoning model | the operator's OpenAI API account, where qualified | the "is a stronger worker cheaper than rescuing a weaker one" comparison |
| `lower-bound` | inexpensive or free models through OpenCode | OpenCode free profiles | amplification: how much deterministic scaffolding compensates |

Every preregistered run records `{provider, model, harness, effective_profile, qualification_state}`; the F19 run
record already has `profile{requested, observed, mismatch}` and `harness{name, version, …}`, so this is a field-level
rule, not a schema change. A free OpenCode model is a lower-bound target and is never reported as a Laguna
substitute; if Laguna becomes available it runs through the same suite under the same class rules.

### 13.2 Helpers beside raw tools; presentation per profile; availability constant

Nothing in R8, R9 or R2-B removes a capability from any profile. The frontier profile has raw tools, typed helpers,
maps, Knowledge and high-signal context all available and chooses; the lower-bound profile has the same set with
deterministic assistance made prominent (explicit orientation, typed helpers first, locators, tests/mocks/constraints
surfaced, Knowledge advertised, recitation on long tasks, completion-impact assistance, raw tools as the escape
hatch). The two knobs are the whole mechanism:

```yaml
context.orientation:  minimal | standard | explicit      # R8 §4
tools.presentation:   raw-first | neutral | typed-first  # R9 §5
```

Mapping a class to a setting (the addendum's expectation: frontier → `raw-first/minimal`, lower-bound →
`typed-first/explicit`) is a measured deployment policy, recorded in the execution profile as `operational` fields
(F15.4), never workflow semantics. R9's "typed surface is a weak-model intervention" is read accordingly: the
*presentation* is the intervention; the operations exist for everyone.

### 13.3 Reporting contract

Every experiment reports, per capability class, **raw vs assisted** (the same model with and without the arm's AEW
assistance), and never a cross-class leaderboard as its headline:

```text
lower-bound raw      vs  lower-bound + AEW assistance        → amplification
mid raw              vs  mid + AEW assistance                 → the middle of the curve
frontier raw         vs  frontier + optional AEW assistance   → conservation, or harm
```

plus one cross-class number that the addendum asks for explicitly: **cost per correctly accepted outcome**, including
Lead interventions and rework, so that "a stronger worker is cheaper overall than repeatedly rescuing a weaker one"
is a measured statement. Q7 §6.3 already defines the estimator (total cost over total correct outcomes, cell-stratified
bootstrap, undefined where an arm has no successes); intervention burden is F9-A1 §20's `unnecessary interventions`
and `Lead tokens`. The interaction the addendum names, capability class × context policy × tool presentation ×
deterministic assistance, is what the five probes jointly estimate; no single probe varies more than one factor
(F19 principle 7), so the interaction is read across them with the class as a blocking variable.

### 13.4 The lower-bound lane: tasks that expose the eight behaviours

The corpus shows none of these behaviours (§1), so the lane is built to provoke them, on a fixture larger than the
12-file ledger (a repository with at least several hundred files and more than one plausible search root; the Q7
corpus's repository scope, or a sanitized public project of that size), with seeded cases that are not held out:

| Behaviour (addendum) | Seeded case | Probe that measures it | Metric (F19 `metrics.py`) |
|---|---|---|---|
| poor repository navigation | the Ticket names a symptom, not a file; the code is three directories deep | `r8-pack-arms`, `r9-intent-surface` | `tool_calls_before_first_relevant_source`, `irrelevant_files_opened` |
| bad search-root selection | two directories share a module name; the wrong one is nearer the root | `r9-intent-surface` | `wrong_root_or_unbounded_search_count` |
| failure to locate tests/mocks | the test exercises the path only through a fixture in a `conftest.py` | `r8-pack-arms` (C), `r9` (`tests_for`), `e1` | `missed_related_surfaces`, `tests_found_rate` |
| incomplete cross-file changes | Q7 F1 shape: a plausible local fix; the sibling module and its schema must change | `e1-completeness-nudge`, `r8` | `omissions_caught`, hidden preservation checks |
| requirement loss on longer tasks | four goal-backwards criteria, one only reachable after a 40-call investigation | `r2b-coherence` | `forgotten_criteria` |
| repeated exploration | a misleading early grep hit; the real definition is elsewhere | `r2b-coherence`, `r8` | `repeated_file_reads`, `repeated_tool_ngrams` |
| weak tool selection | a question answerable by `map.tests_for` in one call, by grep in five | `r9-intent-surface` (arms both / typed-first) | `tool_calls_per_question`, `voluntary_typed_use_rate` |
| difficulty recovering after distraction | an irrelevant failing test in the suite; a stale TODO naming the wrong fix | `r2b-coherence` (distractor-*) | `task_restarts`, `contradictory_actions`, `stale_note_reliance` |

Order of work for the lane: run the lower-bound profile **raw** on the seeded set first; a profile that shows none of
the eight behaviours is not a lower bound for this purpose and the next-cheaper profile is tried; then run the
assisted arms. This lane does not touch the M4-H held-out corpus and can start as soon as the F19 session-database
reader and the seeded fixtures exist, before M4-H.

**Designer's confirmation (2026-10-09), binding for the lane:**

- The lane may use a non-M4-H fixture and may begin before M4-H; no sequencing delay is required.
- Prefer an **independent sanitized/public or synthetic representative repository** of the required size and shape.
- **Pre-gate results are qualification and instrumentation evidence only.** They establish that the eight behaviours
  occur under the lower-bound profile and that the metrics detect them; they are never reported as M4-H or F19
  treatment-effect evidence. Every pre-gate run record is marked `purpose: qualification` in its preregistration,
  and no pre-gate experiment id is reused for a treatment-effect experiment.
- **The Q7 sealed tasks stay completely unexposed.** The Q7 repository itself is used pre-gate only if a specific
  repository-integration probe genuinely requires it (for example T5 map generation at the Q7 repository's scale),
  and that use is recorded explicitly as an exposure in `exposure.yaml` with the probe's reason, under the held-out
  isolation decision of 2026-10-06.

### 13.5 Evaluation priority for the current environment

A: one frontier profile. B: one OpenAI API mid profile. C: one or more OpenCode free lower-bound profiles. The
lower-bound lane (13.4) is the cheapest and the one the corpus most lacks, so it is scheduled first; the frontier lane
is what decides the `raw-first/minimal` defaults and runs on the same seeded set plus the M4-H families after the
gate; the mid lane is added where budget permits and is what makes the cost-per-correct-outcome comparison across
classes meaningful. Pre-gate lower-bound results qualify the lane and its instrumentation; the treatment-effect
claims of §9 come from post-gate runs only (13.4).
