# One evaluation instrument: folding the research plan (E389) into F19, and modernising F19

> **Filing status (2026-11-26).** Research proposal, not adopted design (ledger FRP). Filed as the analyst wrote it;
> only this block was added. It is what E389 asked for, and E389 closed into F19 with it. The operator answered seven
> questions the Lead put on it, on 2026-11-26, in the words "Yes to all 7 on the F19 proposal"; each question and that
> answer are recorded in [F19's note of 2026-11-26](../implementation/notes.d/F19/2026-11-26-docs-f19-refinement-decisions.md),
> and nothing else here is decided. The designer's points D-1 to D-8 (section 6) are open, and so are the operator's
> items that were not among the seven: the worker profile and its re-qualification (O-6), and whether E368's rewrite is
> held as the treatment (O-7, first half). O-9 was not among the seven either: section 3.2's three blockers were
> checked against the register and the board when this was filed, and SYS-01's entry was corrected, as fact, for what
> was verified. A recommendation below is the analyst's unless that note says the operator took it.

**For:** the operator and the designer. **Date:** 2026-11-26. **Status:** a proposal from a read-only study. Nothing was
built, run, pushed or changed.

**Basis.** `origin/main` at `a21e49cd` (the working checkout was at `eece01e5`, 43 commits behind, so every path and
line below was read from `origin/main`). The research plan and its baseline were read from
`origin/docs/projectarchitect-research` at `37dc5bf6` (PR #604, open). The skill evaluation runner was read from
`origin/feat/e135-skill-evaluation-runner` at `a9984ba6` (PR #607, draft). The recovery section was read from PR #614's
description (draft, head `18afc3bc`).

**How to read it.** A sentence with a `file:line`, a document section or a register row is a fact read there. A
sentence marked *(inference)* is my conclusion from those facts. A sentence marked *(proposal)* is a suggestion for
the operator or the designer to take or refuse. "The research plan" means
`docs/research/projectarchitect-concepts-and-evaluation-2026-11-25.md`; "R0" means
`docs/research/projectarchitect-r0-baseline-2026-11-26.md`.

---

## 1. Where things stand, as facts

### 1.1 What F19 can do today, end to end

**One kind of cell can run on a model today: a `raw` cell of a case that is not held out, on one host.** The path is:

- the preregistration is frozen with a canonical hash, and a run whose inputs changed is refused
  (`eval/aew_eval/prereg.py:94-146`);
- the attempt is registered in the append-only ledger before the arm starts (`eval/aew_eval/runner.py:172-175`);
- the `raw` arm runs OpenCode's own `build` agent on the pinned model, with the case's task as its only message, on
  Linux inside a bubblewrap layout built from the product's containment modules (`eval/aew_eval/raw.py:1-34`,
  `:274-285`, `:326-349`);
- the run is ended when OpenCode's own reported cost passes the arm's `cap_usd`, and a run whose cost is unknown is
  charged its cap (`raw.py:464-465`, `:494`, `:174`, `:540`);
- scoring is deferred: the hidden oracle scores the exported tree afterwards, in its own process
  (`runner.py:260-293`, `eval/aew_eval/hidden.py`).

This path has run for real once: the lower-bound lane on 2026-10-10, $0.066 for one profile's whole qualification and
$0.22 for six runs of another (register row F19, Notes, "Run 2026-10-10").

**What that path is not.**

- **Not the product.** The agent is OpenCode's `build` agent, not a worker under an AEW role card with an AEW pack.
  The `aew` arm kind is in the schema (`eval/aew_eval/schema/preregistration.schema.json:29`) and is refused by the
  runner because it is not built (`eval/aew_eval/arms.py:8-11`, `:109-111`).
- **Not metered as plan v5 means it.** The cost is what the harness reports. The spend module's own text says the
  counted cost of a Q7 run comes from a metering proxy's ledger, or from F25's settled figure as a lower bound
  (`eval/aew_eval/spend.py:20-25`). Neither feed exists: the proxy is slice S18 and F25's reader is slice S14, both
  "not built" (`docs/implementation/implementation-status.md`, section "The evaluation instrument (register F19)").
- **Not sealed as plan v5 means it.** The preregistration hash is a seal on the plan. Slice S12, "the seals", is not
  built (same section).
- **No budget across attempts in the instrument.** `run_cell` runs one cell and has no budget argument
  (`runner.py:105-107`). The lower-bound lane keeps its budget in its own driver
  (`eval/experiments/lower-bound-qualification/qualify.py:948-957`, `:995-1012`).
- **No held-out case on a model arm.** The runner refuses it until the evaluator/arm-host split is finished
  (`runner.py:140-143`).
- **No model arm through the split.** The released-cell path takes the scripted arm only
  (`eval/aew_eval/campaign.py:50`, `:149`).
- **No arm under the run supervisor.** The supervisor (S8a) drives an arm through a driver that slices S9 and S13 are
  to build (`eval/aew_eval/supervisor.py:1-5`); the four arm helpers are a contract only
  (`eval/aew_eval/helpers.py:1-18`).
- **Pinned to an older harness in places.** The lower-bound preregistrations pin OpenCode 2.0.18
  (`eval/experiments/lower-bound-qualification/prereg.yaml:32`); the product's tested version is 2.2.6
  (`src/aew/harness/opencode/capabilities.py:15`). A raw cell today needs a new experiment id on the current pin.
  *(inference)*

**So, exactly:** a harness-alone cell on a public or synthetic case can run today, registered, capped per run and
scored blind. No cell that runs any part of AEW with a model can run today. What is missing for that is one thing: an
arm that launches an AEW role run.

### 1.2 What each existing experiment actually uses

| Experiment | Uses from `aew_eval` | Brings its own |
|---|---|---|
| `lower-bound-qualification` | Preregistration, attempt ledger, `run_cell`, the raw arm, profiles, retention, hidden scoring (`qualify.py:63-65`, `:1015`, `:1138`) | A 1,266-line driver. Its "floor" half runs AEW's live lane under pytest and records trials in its own `floor.json`, not the attempt ledger (`qualify.py:794-804`, `:844-860`). Its budget, its stop rules and its behaviour scoring are in the driver (`qualify.py:948-1012`, `:1065-1160`). |
| `verifier-disposition` | Preregistration, attempt ledger, `run_cell` with deferred scoring (`tests/integration/test_eval_verifier_disposition_rehearsal.py:121-135`) | Its arm is a class defined in the test and put into the instrument's arm table for the test's duration (same file, `:50-62`, `:129`). Its grader is the experiment's own file, not the hidden channel (`eval/experiments/verifier-disposition/plan.yaml`, `scoring.hidden_channel: evaluator/disposition_grader.py`). No driver outside pytest. Scripted only, budget 0. |
| `context-pack-rehearsal` | Preregistration, attempt ledger, `run_cell`, `score_run` through the hidden channel (`tests/integration/test_eval_context_pack_rehearsal.py:250-272`, `:308`) | Its arm is also a test-local class swapped into the arm table (`:175-232`, `:266`). It launches the product's real OpenCode adapter against the fake server (`:136-143`). No driver outside pytest. Scripted only, budget 0. |

None of the three uses `analysis.py`. That module is Q7's fixed-cell rule and nothing else
(`eval/aew_eval/analysis.py:139-171`, `:308-340`, `:728`).

### 1.3 Does a split already exist?

**No second system exists on `main`. A seam does, and it is the place a second system would grow.**

- Every experiment goes through F19's preregistration, attempt ledger and `run_cell`. That part is one instrument.
- The layer above one cell is missing from the instrument, so each experiment writes its own. The adopted design
  lists `collect.py`, `metrics.py` and `report.py` in the package
  (`docs/design/evaluation-component-design-v0.2.md` §2); none exists in `eval/aew_eval/`. The result is three
  private copies of "walk the schedule, keep the budget, stop on a lane error, report": `qualify.py`, the two
  rehearsals' test bodies, and now PR #607's `eval/skill_eval/run.py` and `report.py`.
- There is no declared way to add an arm. Two experiments replace the `scripted` entry of `arms.ARMS` from a test;
  PR #607 does the same from a context manager (`eval/skill_eval/run.py`, `with arms.installed()`).
- PR #607 says of itself that it "owns no measurement machinery of its own" and lists each fact's owner
  (`eval/skill_eval/README.md`, "What is whose"). That is accurate for the ledger, the fixture and the arm. Its
  schedule walker and its paired report are new, and they are general.

*(inference)* The research plan, had it run as written, would have added a fourth driver beside these. The risk the
operator named is real, but it sits in the missing run-and-report layer, not in the core.

---

## 2. What to take from the research plan

The research plan's three experiments are not new to F19. F19's own matrix already names `r8-pack-arms` (pack
content), `r2b-coherence` (working-state support, with an "interrupted" family) and `r9-intent-surface`
(`docs/research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md` §9; delta item D14 in
`docs/implementation/agent-effectiveness-implementation-delta-2026-10-09.md`). Experiment A is a sharper `r8`,
Experiment C a sharper `r2b`. *(inference)* So the plan lands as refinements of cells F19 already owns.

### 2.1 Rules of the instrument

| From the research plan | Where F19 stands | Where it lands *(proposal)* |
|---|---|---|
| Judge a brief by the recipient's verified outcome (plan §1, §5.1; concept C1) | F19's probes already take "the independently verified, correctly accepted outcome" as primary (delta D14). What is new is the consequence run: a second worker acts on the first one's output, and only that result is scored | A rule: a cell that changes what an agent is given is scored on what the receiving agent then delivers, never on the text. Byte savings are a diagnostic (R0, "Where E368's rewrite should use C1") |
| Count every attempt and every participant (plan §8.5 "Total effort"; R0 "Accounting") | Every attempt is counted (design v0.2 §1.1 principles 3 and 5). Participants are not: the run record's `cost` is an untyped object and one attempt is one arm run (`eval/aew_eval/schema/eval-run.schema.json`, `cost`) | A rule plus a schema field: one top-level attempt lists its participants (parent, worker, helper, downstream run), each with its own usage. Designer's decision D-5 |
| Scripted checks before paid runs (plan §8.1 "a known solution should pass"; R0 "functional first") | Already practice: all three experiments have a model-free rehearsal and known-answer controls, and the lower-bound lane's freeze needs its oracle validation (`qualify.py:10-11`) | Make it a rule: a `treatment_effect` preregistration is not frozen until its model-free pass and its oracle's known-good and known-bad controls are on record |
| Thresholds set before any result (plan §8.5; R0 "Predeclared decision criteria") | The preregistration has a free `thresholds` object (`preregistration.schema.json`, `thresholds`); Q7 has its sealed analysis plan | A typed block for small cells: the quality tolerance, the minimum useful benefit per measure, and the conditions that fail the treatment whatever else. R0's numbers are the first candidates |
| Four decision outcomes (plan §1) | Not present. PR #607's report has `decision: null` always (`eval/skill_eval/README.md`, "What the report says") | A closed field on the analysis record: sufficient as it is; a narrow change is justified; inconclusive, with the named follow-up; not useful for this task class. The operator adopts it; the instrument only computes which the thresholds select |
| Unknown is never zero; billed cost, tokens, price estimates and counterfactual savings in separate fields (plan §8.5) | Already F19's and F25's rule (`raw.py:32-33`; F25's IF10-14 states in its register notes) | Keep. Add the plan's one new point: preparation cost (map generation, fixture builds) is reported apart from the run and included in the total |
| A hidden check never penalises a requirement the task did not state (plan §8.1) | Practice in the context-pack rehearsal: each criterion names the source that states it (`eval/experiments/context-pack-rehearsal/evaluator/README.md`) | A fixture rule: every oracle criterion cites the released text that states it |
| Change one thing; freeze revision, model, tools, policy and budget (plan §5.1, §8.1) | F19 principle 7 and 8 (design v0.2 §1.1) | Nothing to add |
| The approved cap: $0.50 and 20 minutes per attempt, 132 attempts, $75, a stop for review at half (R0 "Run accounting and resource cap") | Budgets are per preregistration (`profiles.budget_usd`) | The class limit for feature cells. Each cell's preregistration takes its share |

### 2.2 A cell type: small feature cells beside the large arm comparison

*(proposal)* F19 gets a second, smaller kind of cell next to Q7's AEW-against-raw comparison:

- **A feature cell:** two or three arms that differ in one thing an AEW agent is given or offered (a pack section, a
  skill, a map slice, a message), one role run per attempt, a hidden oracle on the result, a paired report against
  typed thresholds, one of four outcomes.
- The research plan's **Experiment A** is this cell with pack variants. **Experiment C**'s model trial (the plan's
  case 5 and R0's C-F5) is this cell with a replacement worker. The skill evaluation (PR #607) is this cell with
  skill exposure. The verifier-disposition rehearsal is this cell with a verifier.
- The research plan's **Experiment B** needs two participants in one attempt (an investigator Ticket, then the
  consumer; R0 "A multi-file retrieval task"). It is the same cell once participants are counted. It comes later.

### 2.3 Fixtures

Take R0's fixture table as F19's fixture backlog, in the instrument's case format (`aew/eval-case/v1`):

- **Exist today:** the lower-bound lane's seeded cases (R0's A-F1), the context-pack rehearsal's REPORT-1 (A-F3), the
  verifier-disposition cases VD-1 to VD-3 (A-F6).
- **New, each small:** a two-module change (A-F2), a consumed discovery record with an open question (A-F4, A-F5), a
  re-review with an open finding (A-F7), a predecessor's partial work (A-F8, shared with C-F4). PR #614's integration
  test already builds A-F8's state through the CLI (PR #614, "Tests").
- **Free, no model:** R0's C-F1 to C-F4 and C-F6 are functional tests over scripted roles. They belong in the test
  suite, not in a paid cell.

### 2.4 What to leave out, and why

- **The plan's own phases and work packages (R1 to R5) as a process.** F19's preregistration, freeze, run, score and
  analysis already are that process. Keeping both is the two-systems outcome.
- **E389 as a place experiments run.** *(proposal)* Its content becomes F19 cells. Whether the row stays as the
  backlog's row or closes into F19 is the operator's (O-3).
- **A retrieval helper, an outline index, a decision store, a status digest (C5 to C7).** R0 already declines them
  ("Not proposed"). Experiment B's helper arm is an investigator Ticket, which exists.
- **The outside project's savings model, quota formulas, line caps and cache timings** (plan §7, §10.2). They are
  another system's parameters, and the plan itself says not to carry them.
- **"Eight fixtures, three repetitions" as a rule.** The plan calls it a planning starting point (§8.1). Each cell
  states its own size.
- **Experiment C's decision on D1.** The operator has decided the recovery section is built (R0, status lines 16-18).
  The cell measures it; it decides nothing.

---

## 3. What in F19 to modernise

### 3.1 The order is upside down for the question now being asked

F19's feature probes are all placed "after M4-H" (delta D14: "Depends on: M4-H's gate"; synthesis §8 step 7). M4-H
needs slices S5 to S18, about 12 to 15 pull requests by the board's own estimate
(`docs/implementation/systems.yaml`, SYS-01 `remaining`). The operator's question, "does this part earn its place?",
is the probes' question, not the gate's. *(proposal)* Put the feature cells first and leave the large comparison
frozen. That is a re-ordering inside F19, not a new system.

### 3.2 Blockers that are no longer what the board says

SYS-01 says its critical path waits on rows held in HOLD-19 and HOLD-21, and S18 on HOLD-20 (`systems.yaml`, SYS-01
`remaining` and `reason`). The register now says:

- **HOLD-21 closed on 2026-11-06.** F25 is restored at V-01 (rows HOLD-21, F25). What S14 waits for is F25's slices
  L3 and L4, and F25's own note says those "feed the frozen F19" (F25, note of 2026-11-26). *(inference)* Each side
  waits for the other; no hold is in the way.
- **HOLD-20 closed on 2026-11-06.** F18.15 merged into E97, the relay's meter, with the words "one meter, no second
  metering proxy" (rows HOLD-20, F18.15, E97's note of 2026-11-06). E97 is a V-01 build item and is not built
  (`systems.yaml`, SYS-31, `designed_only`).
- **HOLD-19 holds one row, F46.** F15.5 closed into STG-14 (rows HOLD-19, F15.5). The steering system's entry says
  "Nothing is held: E7c and E6b were superseded or lapsed on 2026-11-06" (`systems.yaml`, SYS-04 `reason`).
  *(inference)* S13's "after M4-E's E7c" names a slice that will not land. SYS-01's own text already points at the
  replacement: "the G3-backed confirmation A-37 points it at", and G3 is on and used (`systems.yaml`, SYS-20).

*(inference)* None of the three blockers is real as written. Two are design work the designer must redo against
today's product (S13's ceremony, S18's meter). One is a circular wait (S14). SYS-01's text needs correcting whatever
else is decided.

### 3.3 Slices the product has made smaller or unnecessary

- **S18, the metering, key-injecting proxy.** The designer already ruled it temporary and a client of the gateway's
  hook (F19, note of 2026-10-11, AIR-24). The product now routes a contained run's provider traffic through its own
  relay and journals each request with an id and an outcome, though not usage (E97, note of 2026-11-24;
  `src/aew/harness/containment/relay.py`). *(proposal)* Do not build S18. Q7's counted cost waits for E97's meter.
  Feature cells use the cost the run already records, with the per-attempt cap charged when it is unknown, as the
  lower-bound lane did.
- **S8b's helpers and S17's host image, for feature cells.** The helpers exist so an evaluator uid can read an arm
  uid's data on a dedicated arm host (`helpers.py:1-12`). A feature cell on a public fixture runs on one host inside
  the product's sandbox, as the raw arm and the context-pack rehearsal already do. *(inference)* They stay needed for
  Q7 only.
- **S5 to S7 (preflight, host control, the frozen classifier), for feature cells.** They serve held-out isolation on
  a separate arm host (ADR-0018, D1). The lower-bound lane's pattern covers a case that is not held out: no oracle on
  the host while a model runs, and the oracle arrives only to score (`qualify.py:27-29`).
- **The `aew` arm "by generalizing the M3 driver"** (`arms.py:10`). The M3 driver gives its Lead a long hand-written
  prompt of shell commands (`eval/m3/dogfood/dogfood.py:145`). The product's Lead now works through a typed tool
  catalog that is on and used (`systems.yaml`, SYS-06). *(inference)* An A arm built from the M3 driver would measure
  a Lead the product no longer ships. S13 needs a new plan that launches the product's own Lead.
- **The responder's delivery for the R arm** is written against OpenCode 2.0.18's operations
  (`eval/aew_eval/responder.py:19-20`, `:106`). The pin is 2.2.6. It needs re-checking before S9.
- **Free profiles.** The matrix assumes "free OpenCode profiles cost almost nothing" (synthesis §9). The operator
  decided on 2026-11-06 that AEW does not rely on free models (E135, note of 2026-11-06). Every model run is keyed
  and paid.
- **The session reader** (delta D2; F19 row, "Revision C") is not built. R0's measure "additional source reads per
  verified completion" depends on it (R0, "Accounting"). PR #607 already reads which skills a session loaded through
  the adapter (`eval/skill_eval/README.md`, "What is whose"). *(inference)* A first cell should choose thresholds on
  measures that exist today: verified completion, cost, tokens, steps, wall time.

### 3.4 What the instrument is missing for feature cells

Three things, each small *(proposal)*:

1. **A role-run arm.** One AEW role run (implementer, verifier, reviewer) with a model, launched the way the product
   launches it. Three places name this same gap: the runner's refusal of `aew` (`arms.py:10-11`), the
   verifier-disposition README ("Not yet built": a verifier dispatched through AEW and launched by the adapter), and
   PR #607 ("needs F19's `aew` arm, which is not built"). It is far smaller than plan v5's A arm, which is a whole
   headless Lead with an operator ceremony per run.
2. **The run-and-report layer the design already lists** (design v0.2 §2: `collect`, `metrics`, `report`): walk a
   frozen schedule, keep the budget, resume from the ledger, stop on a lane error, pair the arms, apply the
   thresholds. PR #607's `run.py` is this already, apart from three skill-specific calls.
3. **A declared way to add an arm**, in place of swapping an entry of `arms.ARMS`.

### 3.5 How PR #607 fits, so it is not a third system

PR #607 is built on F19 and says so. To keep it there *(proposal)*:

- **Allow its change to the frozen `raw.py`.** It adds two hooks so the skill arm reuses the raw arm's containment,
  key scan, harness pin, cost cap and retention; the alternative it names is copying about 100 lines (PR #607, "Where
  this touches other work"). The freeze does not cover it, so it is the operator's to allow (O-2).
- **Lift its schedule walker and its paired report into `aew_eval`** in the same pull request as, or the one after,
  the role-run arm. Then the skill evaluation and the pack cell share one walker and one report, and `skill_eval`
  keeps only what is about skills: the case format, the exposure and the selection measure.
- **Record it under SYS-01.** The pull request already adds `depends_on: SYS-01` to SYS-22 (PR #607, same section).
- **Give its report the four outcomes** in place of `decision: null`, once the thresholds block exists.
- Its limit of USD 10 (E135) stays its own preregistered budget.

---

## 4. The smallest first step that gives a real value answer

### 4.1 Recommendation

**A pack cell on the context-pack rehearsal's fixture: does what AEW puts in a worker's pack change what the worker
delivers?** First with the three pack variants that already exist, then with E368's core-plus-pointers pack as the
arm that decides E368's rewrite.

Why this one:

- **Most of it exists and already runs through F19.** The fixture (five files, with a superseded spelling as a trap),
  the hidden oracle with four criteria, six known-answer controls, the preregistration and the delivery checks are in
  `eval/experiments/context-pack-rehearsal/` and `tests/integration/test_eval_context_pack_rehearsal.py`.
- **Its arms are built from the product's own pack builder.** B is today's dispatched pack, regenerated and compared
  byte for byte. A is the same pack with only the ticket, role, guardrails, authority and checks. C adds the facts
  themselves (same test, `:53-93`; the experiment's README table).
- **It answers a question the operator is deciding now.** E368 is on the Now list, and its rewrite is held as this
  experiment's treatment on the Lead's recommendation (E368, note of 2026-11-26 on the research branch).
- **The one slice it needs is the slice two other experiments wait for** (3.4, item 1).

What the first run can and cannot say. With arms A, B and C on one public fixture it is a pilot: it says whether a
lower-bound worker does better with today's pack than with the bare ticket, and whether facts in the pack beat
pointers to them. It also tells us whether the fixture discriminates at all. R0's rule applies: if every arm passes
nearly every time, the answer is "inconclusive, raise discrimination", and that is found for under a dollar before
E368's arm is paid for. A decision on E368 needs the rewrite as an arm and more than one fixture.

### 4.2 Why not the other two candidates first

- **The recovery section (F36, PR #614).** It is built and the operator has decided it stays, so a cell changes no
  decision. It needs a new fixture and a second worker run per attempt. *(proposal)* Second, on the same arm, as soon
  as the pack cell has run.
- **Dropped open questions (E198).** Its fix (R0's D2) is not built, and whether to build it first or test it first
  is still the operator's (E198, note of 2026-11-26). It also needs a new fixture (A-F4). Third.

### 4.3 What it needs

| Step | What | Size *(estimate)* |
|---|---|---|
| 1 | **The role-run arm** in `aew_eval`: launch one AEW role run with a real OpenCode and a keyed model, inside the product's sandbox; refuse before registering on a bad pin or a missing key; take the cost from the run's usage record; end the run at its cap; charge the cap when the cost is unknown. Tested against the fake OpenCode, as the raw arm is | 1 PR, about the size of `raw.py` plus its tests |
| 2 | **The shared walker and paired report** in `aew_eval`, lifted from PR #607, with the typed thresholds and the four outcomes | 1 PR; smaller if PR #607 merges first |
| 3 | **The cell itself:** a preregistration for the pack cell (arms, seed, thresholds, budget), its model-free pass, and the oracle moved to where no arm can read it | 1 small PR |
| 4 | **Re-qualify the worker profile on OpenCode 2.2.6.** The lower-bound lane qualified `opencode/gpt-5-nano#high` on 2.0.18 | no PR; one paid run of the existing lane, about $0.07 at the earlier rate |

Outside F19: E368's rewrite, as text the arm can deliver, for the deciding run.

**One design point must be settled before step 1** (designer, D-2). The rehearsal delivers a pack variant by replacing
the launch contract's pack text and calling the adapter directly (test `:136-143`, `:189`). That worker has no custody
bridge, so a real one could not submit the report its pack asks for. The product's own launch gives the bridge but
takes its pack from the engine (`src/aew/engine/harness_ops.py:406`), so it cannot be handed a variant. The choices
are in section 6.

### 4.4 Fixtures and spend

- **Pilot:** REPORT-1 only. Three arms, five repetitions: 15 attempts.
- **Deciding run for E368:** today's pack against the rewrite on REPORT-1 and the lower-bound lane's three seeded
  cases, three repetitions: 24 attempts. R0's full Experiment A is 48.

| Run | Attempts | Worst case at $0.50 | Expected *(inference from the lower-bound lane's $0.22 for six runs)* | Worst-case wall time at 20 minutes |
|---|---|---|---|---|
| Profile re-qualification | one lane run | n/a | about $0.07 | under an hour |
| Pilot | 15 | $7.50 | under $1 | 5 hours |
| E368 deciding run | 24 | $12 | about $1 | 8 hours |

All of it is inside the approved 132 attempts and $75. Paid runs wait for the operator's return; steps 1 to 3 need no
model and can be done before then.

---

## 5. A value map

Ordered by how cheaply each could be answered. "Role-run arm" means step 1 of section 4.3. Costs are worst cases at
the approved cap unless marked; all are *(estimates)*.

| # | Doubted feature (system) | The question | Kind of cell | Needs | Rough cost |
|---|---|---|---|---|---|
| 1 | Containment's cost (SYS-02) | What does the sandbox add to a launch, and how often does its self-test refuse a good launch? | A measurement with no model, in `tools/perf`'s style | Nothing new in F19 | $0 |
| 2 | Recovery after interruption, functional half (F36; R0's C-F1 to C-F4, C-F6) | Does a successor get the required state in each interruption case? | Scripted tests, no model | Nothing new in F19 | $0 |
| 3 | Context packs (E368; `src/aew/knowledge/context.py`) | Does today's pack beat the bare ticket? Does core-plus-pointers hold the outcome at lower cost? | Feature cell, pack variants | Role-run arm; E368's rewrite for the deciding run | $7.50 pilot; $12 to $24 deciding |
| 4 | Specialist skills (SYS-22, E135) | Does a skill help a weak model, does the model pick it, what does it cost? | Paired exposure cell on the raw arm | PR #607 merged; private cases for a benefit claim | at most $10 (the operator's limit) |
| 5 | Project maps in packs (SYS-07) | Does the structural-map slice cut orientation cost without hurting the outcome? | Feature cell, the `structural` switch off and on (`systems.yaml`, SYS-07, `turning_on_changes`) | Role-run arm; a fixture where finding the code is the hard part (the lower-bound lane's 480-file repository) | $9 to $18 |
| 6 | Recovery section, model half (F36, PR #614) | Does a replacement worker repeat less and finish as often? | Feature cell, pack with and without the section | Role-run arm; the A-F8 fixture; a first run that leaves partial work | $9 to $18 |
| 7 | Open questions carried into the pack (E198) | Does a worker act wrongly on a question its input left open? | Feature cell | Role-run arm; D2 built; the A-F4 fixture | $9 to $12 |
| 8 | Verification and review gates (the Contract's "Independent review") | Does a verifier or reviewer catch a seeded defect the implementer's own checks pass, and how often does it reject good work? | Role-disposition cell: the verifier-disposition cases with a model verifier | Role-run arm for the verifier role; fresh private variants (the experiment's README, "Not yet built") | $9 for 18 attempts |
| 9 | Plan assessment (SYS-43) | Does an assessor flag a planted wrong premise, and how often does it block a sound plan? | Role-disposition cell on seeded plans | Role-run arm with the assessor's card; new seeded-plan fixtures; the gate is partly built and off | $9 to $18, after the fixtures |
| 10 | Knowledge system (SYS-14) | Does raw-history search answer questions the checkout cannot, at what cost? | Feature cell, search off and on | Workers' search (E253, not built); a history snapshot fixture (F19 row, "F21's Arm B prototype") | not before E253 |
| 11 | Question-scoped retrieval (research plan, Experiment B) | For which question classes does an investigator Ticket beat direct reads? | Two-participant feature cell | Participants in the run record (D-5); the pinned search tool on the host (R0, "Preflight for B") | $24 for 48 attempts |
| 12 | Messaging (SYS-13) | Does a mid-run message change the outcome, against none? | F19's messaging arms need a live Lead (F19 row, "F9-A1 adoption") | A Lead arm; or, as a cheaper stand-in *(proposal)*, one fixed scripted message to a model worker | high with a Lead; about $9 with the stand-in |
| 13 | Steering (SYS-04) | Does RUN save operator attention without unsafe steps? | Not an F19 cell: the measured RUN trial is already folded into Session B (`systems.yaml`, SYS-04, `finish_line`) | The trial | inside Session B |
| 14 | AEW as a whole against the harness alone (Q7, M4-H) | Does the whole workflow earn its cost? | The large arm comparison: 144 primary runs (Q7 v0.3.1 §14, "12 R and 12 A runs per cell") | S5 to S18 re-planned (section 3), E97's meter, a Lead arm | 12 or more PRs, then the sealed budget |

---

## 6. Decisions needed

### The operator's

| # | Question | Recommendation |
|---|---|---|
| O-1 | Unfreeze F19 for feature cells only: the role-run arm, the shared walker and report, the thresholds and outcomes? | Yes. Leave S5 to S18 and Q7 frozen. This is three pull requests, none of which the frozen slices depend on |
| O-2 | Allow PR #607's two hooks in the frozen `raw.py`? | Yes. It is the difference between extending the instrument and copying it |
| O-3 | What becomes of E389? | Keep its content as F19's feature-cell backlog. Either close the row into F19 by a note, or keep it and change its Work to say every run is an F19 preregistration and there is no other runner. The first is cleaner |
| O-4 | The order of cells | Pack cell pilot; E368 deciding run; skills (PR #607); recovery section; maps; verifier. Rows 1 and 2 of the value map are free and can go at any time |
| O-5 | Does the approved cap ($0.50, 20 minutes, 132 attempts, $75, review at half) apply to F19 feature cells as a class, and is the skill evaluation's $10 inside it or beside it? | Apply it to the class. Keep the $10 beside it, since it was approved separately |
| O-6 | The worker profile: `opencode/gpt-5-nano#high`, keyed and paid, re-qualified on 2.2.6 first? | Yes to both. It is the profile already shown to lose requirements on longer tasks, which is what makes a pack cell discriminate |
| O-7 | Is E368's rewrite held until its cell can run (today the Lead's recommendation, not a ruling)? Is E198's fix built first or tested first? | Hold E368's rewrite as the treatment. Build E198's fix behind the cell as well, since it changes what a planner sees |
| O-8 | Q7 and M4-H | Keep frozen. Decide after the first three cells whether the large comparison is still wanted, and have S13 and S18 re-planned only then |
| O-9 | SYS-01's entry still cites HOLD-19, HOLD-20 and HOLD-21 as blockers | Ask the Lead to correct it from the register (section 3.2) |

### The designer's

| # | Question | Recommendation |
|---|---|---|
| D-1 | Is the role-run arm a new arm kind beside `aew`, `raw` and `scripted`? | Yes, a new kind. `aew` stays reserved for the whole-workflow arm with a Lead, so a feature cell is never mistaken for Q7's treatment |
| D-2 | How does a feature cell express its treatment? (a) Two pinned AEW commits, each arm running the product's own launch; (b) one commit, pack text replaced at the adapter, as the rehearsal does, with no custody bridge for the worker; (c) a product switch | (c) where a switch exists (maps, messaging, skills). (a) for a change that is a commit (the recovery section, E368's rewrite). (b) only for the pilot's evaluator-built variants, with the missing bridge stated as a limit of that run |
| D-3 | Is harness-reported cost, with the cap charged when unknown, admissible for feature cells? `spend.py:20-25` rules "layer (a)" out for counted Q7 runs | Yes for feature cells, recorded as a lower bound and labelled. Q7's rule is unchanged and waits for E97 |
| D-4 | S13's operator ceremony was to stand on E7c's confirmation, which lapsed. What does it stand on now? | G3's trusted-origin approval, as SYS-01's own text suggests. Not needed for any feature cell, so not urgent |
| D-5 | How does one attempt record several participants (a consequence run, a helper)? | A `participants` list in the run record, each with its own usage; the attempt stays one ledger entry. Needed for Experiment B and the recovery cell, not for the pack cell |
| D-6 | Typed thresholds and the four outcomes: fields of the preregistration and the analysis record, or a convention inside `thresholds`? | Fields, in a new schema version, so a report can refuse a plan that has none |
| D-7 | May a feature cell on a public fixture with a private oracle support a decision, or is it always a pilot? PR #607 says public cases make a pilot | A decision-grade cell needs an oracle no arm can read and a fixture the worker's model has not been tuned on. The lower-bound lane's pattern gives the first. Say which fixtures meet the second |
| D-8 | Drop S18 as a separate proxy for good? | Yes, in favour of E97's meter, as AIR-24 and the hold match already point |

---

## 7. What I could not verify

- **Plan v5 itself.** It is "a working plan and not in this repository"
  (`docs/implementation/adr/0018-evaluator-arm-host-split.md:15`). What each slice holds is known here only from
  `implementation-status.md`, ADR-0018 and the module docstrings. The same is true of F25's plan v4 and of the
  spend "layers" (a), (b) and (c), which I read only in `spend.py`.
- **Nothing was run.** No test, no model, no tool. "Can run today" in 1.1 rests on reading the code and on the
  recorded run of 2026-10-10 under OpenCode 2.0.18. The raw arm was not re-run on 2.2.6.
- **The private oracles.** The lower-bound lane's oracles and any held-out material are outside this repository.
- **The two draft pull requests.** #607 and #614 were read as branch content and description. Their CI state was not
  checked; #607 showed a merge conflict with `main` when read.
- **E7c's lapse.** It is cited from SYS-04's `reason` text. The record of 2026-11-06 it rests on is in the design
  workspace and was not seen.
- **Whether a real worker launched as the rehearsal launches it could do useful work without a bridge** (D-2, choice
  b). The rehearsal used the fake server, which does not try.
- **Whether the pinned OpenCode lists exactly an arm's exposed skills.** PR #607 states this as its own unverified
  point.
- **The expected spend.** It is scaled from the lower-bound lane's rates on other tasks and an older harness. The
  worst-case figures do not depend on it.
- **The Lead's tool ceiling.** I did not find a figure in the source to cite, so the proposal makes no claim about it.
- **Sizes in pull requests** are estimates from the size of the neighbouring modules.
