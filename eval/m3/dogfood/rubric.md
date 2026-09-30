# M3 dogfood: pre-registered rubric

Fixed on 2026-09-28, before any paid run, together with the tasks (`dogfood.py`, `fixture/`), the hidden tests
(`hidden.py`) and the Lead's brief (in `dogfood.py`). The results are reported against this rubric in
`docs/implementation/m3-dogfood-report.md`, whatever they turn out to be. If a rule has to change after a paid run,
the change and its reason go in the report, and earlier runs are not re-scored silently.

## The question

Does AEW make real engineering work better, not merely more elaborate? Better means a higher chance that the
result is correct and in scope, with defects caught before integration and the work able to survive losing the
harness. More elaborate means more cost, time and steps for the same result. Both are measured, and neither is
assumed.

## What is compared

- **AEW mode.** A headless model Lead (the production `aew-lead` agent) in a Lead session. It gets only the
  operator's objective and the brief. Every role is a real model run through the production OpenCode adapter.
- **Raw mode.** OpenCode's own `build` agent on the same model and effort, with the objective as its prompt.
- **The same for both:** the same repository, the same isolation (private OpenCode state; no user configuration,
  plugins, LSP or formatter), the provider key only in OpenCode's server, and the same curated shell environment.

## Tasks

| Task | Kind | Starting point | Raw baseline |
|---|---|---|---|
| T1 | tiny fix (Class 0 is appropriate) | negative amounts formatted `$-15.00` | yes |
| T2 | multi-file feature | `--category` for `summary`, with README | yes |
| T3 | bug that needs investigation | monthly summaries omit each month's last day; the objective states only the symptom | yes |
| T4 | wrong initial hypothesis | the operator blames float arithmetic; the cause is amount parsing (`23.4` read as 23.04) | yes |
| T5 | review with a seeded defect | a plausible `split_amount` whose shares do not add up; its own tests pass | yes (asked to review and fix) |
| T6 | resume after losing the Lead's harness | T2's objective; once the Lead has launched its first role run, its OpenCode is killed and its state is wiped, and a fresh session resumes from AEW alone (amendment A2) | T2's |
| T1C0 | tiny fix, operator-directed Class 0 (amendment A3) | T1's objective plus one operator sentence: "It is a trivial, low-risk fix: handle it as a Class 0 Ticket." | T1's |
| T1, T2, T3 with `--no-guide` | the Lead without its guide (amendment A4's before arm) | as T1, T2, T3 | as T1, T2, T3 |

## Per-run measures

1. **Outcome** (primary): the hidden test on the result.
   - AEW mode: the integrated commit on `main`. If nothing was integrated, the Ticket workspace is also judged and
     reported as "correct but not integrated", which is not a pass.
   - Raw mode: the working tree.
   - The project's own tests are recorded alongside.
2. **Reached DONE** (AEW mode): whether AEW's own gates let the work through.
3. **Scope:** changed paths outside `ledger/`, `tests/` and `README.md`.
4. **Interventions:** nudges (at most two; AEW mode only, when the Lead ends its turn with work open) and any
   manual action.
   - T5's scripted setup and T6's scripted harness loss are part of the scenario, not interventions.
5. **Cost:** as OpenCode reports it, and recomputed from tokens at catalog prices, split into the Lead (control
   overhead) and the roles.
6. **Tokens, wall time, steps, invocations and runs;** relaunches and runs whose evidence was never ingested
   (waste).
7. **Defects caught:** review findings and verification results, and for T5 whether the seeded defect was caught
   before integration and by whom.
8. **Safety:**
   - no AEW credential and no provider key in any file the run left;
   - the AEW checkout untouched.

## Hypotheses (stated before the runs)

- **H1 (overhead):** on T1 and T2 both modes pass. AEW costs several times more than raw (Lead plus review and
  verification), and takes longer.
- **H2 (quality):** on T3, T4 and T5, AEW mode's hidden-test outcome is at least as good as raw mode's. On T5 in
  particular, AEW's independent review catches the seeded defect before integration more reliably than a raw
  session asked to review.
- **H3 (resilience):** in T6 the resumed Lead continues from AEW's state alone, without redoing accepted work, and
  reaches DONE.
- **H4 (asymmetry):** in the model comparison, a cheap implementer with a strong reviewer and verifier does no
  worse on correctness than the reverse, at lower cost.

Each hypothesis is reported as supported, not supported, or inconclusive (too few runs). No composite score is
computed.

## Amendments

**A1, 2026-09-28.** Made after the first paid run (T1 in AEW mode on GPT-5.6 Luna, at `55412aa`), before any other paid run. The reasons are the companion design review's M3 hardening blockers (`docs/implementation/m3-companion-review-triage.md`) and what T1 showed.

- **B1, intent ingress.** AEW gained `--fields FILE|-`, which passes any command's option values as data. The Lead's system text, the role preamble and this dogfood's brief now tell models to pass free text that way, or with quoted heredocs. In T1 the shell had corrupted a Ticket goal and a classify reason (`$1` expanded).
- **B2, the containment label.** Runs and `doctor` now state `workdir separation only`.
- **B3, failure names.** Observed failures are classified by the classes in `docs/design/failure-class-registry.md`. A failure that no class covers is reported as unmapped.
- **Also between the two runs:** M3-D9, where AEW now refuses a comma inside a scope glob.

T1's first record stays as it is. It is a result on the code before hardening, and its AEW commit is `55412aa` (that record predates the `aew_commit` field). It is not re-scored. T1's later trials run on the hardened code.

**A2, 2026-09-29, after the GPT-5.6 Luna set.** T6's trigger for losing the Lead's harness was "a role run has been running for 60 s". It never fired: every Luna role run finished sooner, so both Luna T6 runs were effectively T2 repeats. They are reported as such, not as T6 results. The trigger is now "the Lead has launched its first role run", which fires whatever the model's speed. T6 is rerun on the fixed driver.

**A3, 2026-09-29, after the Sol set and before any T1C0 run.** The M3 audit (X4) and the designer: T1 was meant to exercise the Class 0 path, and never did. On the hardened code, the Leads chose Class 1 or 2 for all 30 Tickets across 26 runs, T1's 4 included, although the brief says "Class 0 is for trivial, low-risk changes". Two questions, answered separately:

- **Calibration** (recorded from the runs above, not rerun): unprompted, no Lead chose Class 0, even for a one-line fix. This is recorded as an explicit issue for the designer (`future-work.md` Q10). It is consistent with the fail-closed classification the companion review asks for (F6), and it is also why every T1 paid for review and verification.
- **The path:** with the operator directing Class 0 (task T1C0), does the Class 0 path work end to end? Two trials, AEW mode, GPT-5.6 Luna (the cheap model), the same brief and caps. Recorded: the class the Lead chose, the role runs, the gates, the hidden test, cost, wall time and refusals (the instrumented command log, audit T3). The path works if a trial reaches DONE with the hidden test passing and runs only what Class 0 requires: local checks, then the post-integration verification. A Lead choosing another class despite the instruction is a calibration result, not a failure of the path.

T1C0 is not compared with T1 for quality or cost: its instruction differs.

**A4, 2026-09-30, before any of its runs: the Lead's guide, before and after.** F16 gave the Lead a guide to how AEW works in its project (`aew guide`), in its system text. The operator asked for a run that shows whether the Lead acts differently with it.

- **Arms.** Both on the same code, identical except for the guide: *before* (`--no-guide`, the Lead's system text without it) and *after* (with it). The earlier runs are not the "before" arm, because the refusal hints (audit X1, X2), the neutral class example (X4a) and other fixes landed since.
- **Tasks and model.** T1 (the tiny fix: does the class choice change?), T2 (the multi-file feature) and T3 (the investigation), in AEW mode on GPT-5.6 Luna, with the same brief, caps and limits. Two trials per task and arm: 12 runs, about USD 0.5. The arms alternate (before, after, before, after) so that time drift does not favour one.
- **Recorded per run,** from the run record and the instrumented command log (audit T3): the class of every Ticket; the refused `aew` commands and their error codes; `--help` lookups; Lead steps; the Lead's and the run's cost; wall time; role runs; DONE and the hidden test.
- **Stated before the runs.** G1: with the guide, fewer refused commands and fewer `--help` lookups per session. G2: with the guide, T1's Leads choose Class 0 at least once, which they never did before (the guide gives no eligibility criteria beyond the Workflow Contract's, Q10). G3: outcomes, DONE and the hidden test, are no worse. G4: the Lead's steps and cost; the longer system text costs more per step and fewer corrections cost less, and the net is reported either way.
- **Limits.** Two trials per cell show direction, not significance. Counts are reported as they are, and a result against a hypothesis is reported as such.

## Budget and stopping

- The operator's budget is USD 10 for the paid runs.
- Every run has a cost cap (default USD 1.50) after which its Lead and runs are stopped.
- The first paid run (T1, AEW mode, GPT-5.6 Luna) is measured before anything else runs. The operator then approves
  the rest against a projection.
- Every paid run is reported, including failures, runs stopped by the cap, and runs that failed because of a
  defect in the driver.
