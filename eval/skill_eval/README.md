# The skill evaluation's runner

Register E135 (SYS-22). It runs the paired comparison of the [skill evaluation guide](../../docs/skills/evaluation-guide.md) for one skill that AEW's install ships, on F19's instrument (`eval/aew_eval`). It answers the row's three questions as far as a machine can: whether the skill helps a weaker model, whether such a model picks it from its description, and what its listing and its loads cost.

**Running it for real is not part of this directory.** The qualification is a release gate on E135's row, and it is the operator's act: a keyed, paid model they approve for that event, never a free one. The runner refuses a preregistration whose budget is above their limit of USD 10. That bounds one preregistration only: it sums nothing across experiments or lanes, so the total spent on the evaluation is the operator's to keep. No test here calls a provider.

## What is whose

The runner adds no measuring machinery where an owner already has one.

| Fact | Owner | The runner's use |
| --- | --- | --- |
| The preregistration, its frozen schedule and hash | `aew_eval.prereg` | `plan.shape` checks it describes a pair |
| An attempt, registered before any provider action, finalized once | `aew_eval.ledger`, `aew_eval.runner.run_cell` | `run.run` calls it cell by cell |
| A case's fixture and hash | `aew_eval.fixture` | `cases.materialize` writes F19 cases |
| The model arm: containment, key scan, harness pin, cost cap, retention | `aew_eval.raw.RawArm` | `arms.SkillRawArm` extends it at two hooks |
| What a run gets of a skill, its copy and its hash | `aew.skills.plan`, `aew.skills.deliver` | the arms' exposure |
| The skill rules and the `skills` entry | `aew.harness.opencode.projection` | the session's rules and configuration |
| Which skills a session loaded | `adapter.skill_loads`, through `collect` | `harness.exposure.loaded` |
| What a worker is told about its skills | `projection.skills_text` | `python -m skill_eval told` prints it |

## What is generic

`walk.py` and `paired.py` import nothing of the skill evaluation: they read a frozen preregistration, the ledger and the run records. `walk.py` is the schedule walked block by block under its budget, with the cap charge, the frozen retries, the lane-error stop, the neutral run names and the resumption. `paired.py` is two arms' runs as pairs, their usage differences, the blind grading packets and the paired grades. They are written to be lifted into `eval/aew_eval` as the shared walker and paired report in a following pull request; a test holds that neither imports a skill-specific module. `run.py` and `report.py` keep what is about a skill: the paired plan's check, the lane's claim, the evaluator's material, the arms, the exposure check, the loads and the selection table.

## The steps

Run from the checkout with `eval/` and `src/` on `PYTHONPATH`. Keep the cases, the evaluator's directory and the lane outside every git work tree and under the home directory.

```sh
# 1. The candidate's cases as F19 cases, and the evaluator's key. An arm sees the first directory's content only.
python -m skill_eval materialize docs/skills/candidates/adversarial-review/evals/cases.yaml \
    --cases ~/skill-eval/cases --evaluator ~/skill-eval/evaluator --answer-file ANSWER.md
# 2. Copy plan-template.yaml, fill it (the printed `cases` block goes in), and freeze it once.
python -m aew_eval.prereg freeze ~/skill-eval/plan.yaml --by NAME --out ~/skill-eval/plan.frozen.yaml
python -m skill_eval check ~/skill-eval/plan.frozen.yaml
# 3. Run the schedule. It resumes from the ledger; --limit 2 runs one pair.
python -m skill_eval run ~/skill-eval/plan.frozen.yaml --cases ~/skill-eval/cases \
    --lane ~/skill-eval/lane --evaluator ~/skill-eval/evaluator
# 4. Grade blind, then report.
python -m skill_eval packets ~/skill-eval/plan.frozen.yaml --cases ~/skill-eval/cases --lane ~/skill-eval/lane
python -m skill_eval report ~/skill-eval/plan.frozen.yaml --lane ~/skill-eval/lane \
    --evaluator ~/skill-eval/evaluator --grades ~/skill-eval/grades.jsonl
```

**Keeping the grading blind.** Give the grader a copy of each packet's `export` directory (check it against `export_sha256`), the task and the rubric, and nothing else. The lane and the frozen plan are the unblinding key: `work/<run>/skills/` shows a run's exposure, `ledger/runs/` names its arm, and the plan's `assignment.order` maps every `rNNN` to its arm. Keep all three away from the grader until the grades file is final.

A dry run with no model uses two `scripted` arms (`kind: scripted`, `steps: []` and the same three exposure keys). It qualifies the schedule, the delivery, the budget and the report, and its report is always a pilot.

## What the pair is

Two arms of one kind whose configurations are equal outside `skills`, `optional_skills`, `skill_sha256` and `told`. The candidate arm exposes exactly one skill more than the baseline. Where it names that skill sets the mode:

- **`optional_skills`: a selection trial.** The model sees the `skill` tool's listing and decides. This is how a card's `optional_skills` reach a worker.
- **`skills`: a procedure trial.** As a card's `skills:` are. Nothing makes the model load the skill unless the plan's `told` says so. `python -m skill_eval told --skills ID` prints the line a worker gets.

Skills named in both arms are the other candidates a selection trial keeps frozen (guide §3). Both arms deny every skill id but their own, so OpenCode's own skills are in neither.

Each case and repetition is one block holding both arms, in an order drawn from the frozen seed. A run is named for its place in the schedule (`r007`), so neither its id nor its folder names its arm.

## What the report says

- **Cost.** The candidate run's usage minus the baseline's, pair by pair: first-step input tokens, each token category, reported cost, steps and wall time. All complete pairs, then split by whether the candidate was loaded. An unknown value is counted as missing, never as zero. `loads` gives the candidate's loads and the bytes of its `SKILL.md` they brought in, a lower bound.
- **Selection.** Each candidate run's `loaded` beside the case's expected activation (`use`, `skip` or `abstain`) from the key: false activations, missed activations, loads of another exposed skill, and `skill` calls that loaded nothing.
- **Benefit.** Paired counts from a grader's file: both right, the candidate alone, the baseline alone, neither.
- **`pilot`** is always true today, because the only cases a model arm can run are public ones (Limits). A pilot qualifies the instrument and decides nothing. `evaluator_material_hidden` says separately whether the lane's record knows the evaluator's paths were hidden from every arm.
- **`pair.told_differs`** says whether the two arms were told different text.
- **`decision`** is always `null`.

## What the runner leaves open

These change what the evaluation means, so the runner does not choose them. Each is a field of the plan or a file the evaluator supplies.

1. **Who grades, and by what rubric.** `packets` writes what a grader may see; the grades file is theirs. A model grader is a measuring instrument with its own pins and a human-calibrated sample (guide §5, step 8), and no grader is built here.
2. **The answer.** A review or an investigation ends in text, which F19's run record does not carry (the session database is kept under F19's retention rules, and its evaluator-side reader is not built). `--answer-file NAME` adds one sentence to every task, the same in both arms, asking for the final answer in that file, so it is in the exported tree. Without it, a grader has only the changed files.
3. **The model, its effort and the harness pin.** The plan's, frozen. The runner refuses a model arm with no key variable.
4. **The sample, the uncertainty method and the decision rule.** The report is descriptive. Whether a skill is qualified, by what margin and at what cost, is the plan's to state before the runs and the operator's to adopt.
5. **What the arm is told.** `told`, verbatim, or nothing.
6. **The agent.** The model arm is F19's `raw` arm: OpenCode's own `build` agent, not a worker under an AEW role card. A run under the card's own projection needs F19's `aew` arm, which is not built.

## Limits

- **Public cases make a pilot.** The cases under `docs/skills/candidates/` are development material and their oracles are public. F19 refuses a held-out case on a model arm until its evaluator/arm-host split exists, so a benefit claim on private cases waits for that.
- **Hidden means the filesystem.** On Linux a contained arm is refused unless its layout hides the evaluator's directory, the cases and the directory the cases' source file is in (its oracles and rubric). An arm that is not contained (Windows, or `contain: false`) can read what its user can, and `evaluator_material_hidden` is false. Nothing here limits an arm's network. The check is computed from the lists F19's layout hides; it does not open the paths from inside a layout.
- **The baseline can reach the candidate's shipped text on disk.** The check above covers the evaluator's paths, not AEW's own install. The shipped skills sit in the installed package, under the interpreter's prefix, which a contained arm's layout keeps readable, and an arm that is not contained can read them anywhere. So "absent" for the baseline means not listed, not offered and not copied into its run; a baseline that went looking through the interpreter's files could find the text. The guide's "A has no access to it" (§5, step 4) is not met to that extent.
- **The budget counts what the harness reports.** A reported cost of 0 is charged 0. A run's cap is enforced by the arm between polls, so one run can end somewhat above it. The sums are floating point, so a pair that fits the budget exactly can be refused; that errs on the safe side.
- **A host-side failure stops the walk, and still costs its attempt.** A failed delivery, a refused session or any error around the arm ends the walk at that cell (it resumes once the host is fixed). The attempt it stopped on is counted, and under `max_retries: 0` that cell is not run again.
- **The listing is not read back.** A run records what was delivered and re-hashed, and what the session loaded. It does not ask the server what the `skill` tool listed. The first live step of a qualification is a model-free check that the pinned OpenCode lists exactly an arm's exposed ids under these rules; no OpenCode binary was at hand when this was built, and the tests use the repository's fake server, which applies no skill rules.
- **A case with no artifact files cannot run.** F19 builds a case from a fixture tree and refuses an empty one, so `materialize` refuses such a case by name; leave it out with `--only`.
- **One candidate per experiment.** A bundle of skills is another experiment (guide §3).
