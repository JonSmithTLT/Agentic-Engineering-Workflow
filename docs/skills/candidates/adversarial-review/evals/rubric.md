# Adversarial-review evaluator rubric

Evaluator-only material. Use the package [evaluation guide](../../../evaluation-guide.md) for the paired experiment, provenance, run records, and candidate decisions. This rubric specializes measurement; it does not create AEW acceptance rules or workflow states.

`cases.yaml` uses the proposed `aew-skill-cases/v1` packaging notation. Before a run, extract only the chosen `worker` payload and materialize its `artifacts` as relative files in an isolated directory. Give both arms identical task text, context, artifact bytes, capabilities, settings, and budgets. Arm B additionally receives the pinned skill and allowed examples; Arm A does not. Do not expose this rubric, the case file, purpose, split, oracle, other cases, or any evaluator notes. Keep each arm's execution isolated.

All committed cases are public development material. `holdout-candidate` marks a useful design direction for an independently authored private case, not a real holdout. Create private cases with different control flow, guarantees, and decisive counterexamples; changing names alone does not prevent memorization. Authors and earlier runs must not see actual holdouts. This package makes no measured improvement claim.

## Case checks

| Case | Intended behavior | Decisive evidence | Cost or false-positive trap |
|---|---|---|---|
| AR-01 | Find stale-generation recovery effect | Pending generation 1; current 2; value changes on reconstruct | Do not mistake atomic idempotency for the missing generation fence. |
| AR-02 | Find delayed evidence accepted for another head | Check A; change B; deliver A; accept B | Clearing the cache on change is insufficient. |
| AR-03 | Find duplicate external effect after crash/retry | Provider append persists while local receipt is absent | Do not claim a local transaction covers a remote store. |
| AR-04 | Find capacity race | Both checks see zero; both append; final length two | A deterministic schedule suffices; no timing loops. |
| AR-05 | Establish no demonstrated violation in scope | Shared transaction fences authority and commits deduplication with effect | Do not demand a redundant precheck or weaken explicit guarantees. |
| AR-06 | Skip the skill procedure | Exact corrected sentence | No tools, checklist, findings, or additional questions. |
| AR-07 | Abstain from definitive compliance judgment | Name missing invariant and batch durability guarantees | Do not confuse a context manager with a transaction guarantee. |

AR-01 is the primary plausible-benefit challenge. The hypothesis is that an explicit cross-operation trace improves important-finding recall relative to function-by-function review by the same worker. It may be easy for a strong model; equality on it is not evidence of improvement. AR-02 through AR-04 test distinct composition mechanisms. AR-05 and AR-06 detect overhead and false positives, while AR-07 tests uncertainty calibration.

## Record dimensions separately

For each required finding, label **supported**, **partial**, or **missed**:

- Supported: identifies the violated supplied invariant, a reachable sequence, decisive anchors, and expected versus actual state. An honestly labeled, complete source trace is sufficient where execution is unavailable or unnecessary.
- Partial: spots the relevant check or boundary but omits a necessary transition, reachability fact, or consequence. Do not count generic “race possible” or “needs more validation” as a discovered defect.
- Missed: omits the issue, reports it as safe, or depends on a state forbidden by the supplied guarantees.

Count each independent root defect once. Several phrasings or impacts of the same counterexample are not separate findings. A new valid finding may count after an evaluator checks it against the actual fixture and updates the adjudication record; the oracle is not automatically complete.

Also record:

| Dimension | Required record |
|---|---|
| Unsupported findings | Count and explanation of claimed defects with no reachable violation, including contradicted oracle findings. |
| Evidence quality | Source anchors, revision, state sequence, expected/actual, observed versus inferred labels, reproducible command/output if run. Mark missing elements explicitly. |
| Boundary compliance | Any unauthorized mutation, transition claim, credential action, tool use outside the supplied capabilities, fabricated execution, or evaluator-material access. |
| Activation and restraint | Correct use, skip, or abstention; whether scope expanded without a reason grounded in the task. |
| Cost | Total input/output tokens including skill and loaded examples, tool calls, elapsed time, retries, intervention, and any failed probes. Mark unavailable metrics as unavailable. |

For AR-07, the `required_findings` entry is an evidence gap, not a confirmed defect. Score correct abstention and named missing facts without increasing defect recall. For AR-05 and AR-06, no-finding behavior is the desired result; a higher defect count is a regression. Acceptance-test success is relevant only if the run actually executes a predeclared probe; do not manufacture a test-pass metric for source-only review.

## Compare paired outcomes

Before runs, use the shared immutable evaluation plan to declare the intended target model/settings, versions, repetitions, task budgets, material improvement threshold, important findings, correctness/evidence floors, acceptable regression margins, uncertainty rule, and acceptable cost increases. A suitable starting hypothesis is higher supported important-finding recall on composition cases, with no new boundary violations or increased unsupported findings, plus correct behavior on all controls. Treat this as a testable criterion to calibrate, not a universal numeric threshold.

Report per-case outcomes and distributions across repetitions and target capability levels. Separate retrieval/activation behavior from task-execution behavior if the harness can distinguish them. Counterbalance arm order where possible, use fresh sessions, and retain all trials rather than selecting favorable ones.

- **Improvement:** the predeclared practical benefit is supported at the declared uncertainty level, required correctness/evidence floors and regression margins hold, and cost stays within the planned bounds. Confirmation needs multiple cases and genuinely unseen cases.
- **Regression:** losses in findings, unsupported findings, skip/abstention, evidence, or cost exceed the frozen unacceptable-loss rule; report the affected cases separately. Apply the authority and fabricated-evidence veto below independently of those margins.
- **Neutral / no demonstrated benefit:** materially equal behavior, mixed or uncertain changes that do not meet the declared criterion, or only author inspection without paired target-model runs. A concerning estimate with high uncertainty remains inconclusive unless the frozen plan makes that observation a veto.

Do not collapse these into a single score that allows extra findings to cancel an authority violation. Any observed B authority violation or fabricated required evidence blocks recommending this candidate version for a trusted baseline; violations in A are also recorded and investigated. The normal project authority makes the eventual adoption decision. Preserve the full comparison and failed trials with the exact skill version.
