# Skill Evaluation Guide

Status: proposed authoring methodology. This document and its YAML templates are not accepted AEW schemas, an evaluation runner, workflow states, or permission to change project state. No target-model experiment has been run for this package; none of the bootstrap candidates has demonstrated benefit.

A skill earns a recommendation for a specified target worker and task distribution by improving observable engineering behavior at an acceptable cost. Good prose, frontier-model approval, and a single successful example do not establish that result. Evaluation recommendations remain advisory to the existing AEW authority.

## 1. State the experiment before running it

Use [eval-plan.yaml](templates/eval-plan.yaml) to record an immutable plan. The experiment owner selects the target execution profile, capabilities, budget, workload, decision thresholds, and comparison method. Skills must not choose worker routing, grant capabilities, or change these limits.

Write a falsifiable claim, for example: “For this worker on concurrent state-management reviews, the candidate increases discovery of important composition defects without increasing unsupported findings beyond the stated margin.” Declare:

- The specific skill version and the exact runtime files to expose.
- Target provider, model identifier and revision if available, effort/settings, harness/version, and tool versions. Identify unavailable settings explicitly rather than silently assuming defaults.
- The task population, separate case families, case weighting, and expected deployment conditions. “Works for cheaper models” requires evaluating named target profiles separately; author-model results cannot substitute.
- One primary benefit measure, important secondary measures, authority/evidence vetoes, acceptable regression margins, and economic limits. An economics-first claim also needs predeclared effectiveness noninferiority bounds. Thresholds express engineering needs and must be chosen before seeing comparison results.
- The number of independent contexts, paired repeats per context, random order schedule, stopping rule, scoring procedure, and uncertainty method. Use multiple independent contexts and multiple repeats per arm/context; justify the counts rather than treating one win as a comparison.
- Which records are required, how missing telemetry is represented, and what external infrastructure failures can invalidate a run.

Fill required placeholders in the plan before freezing it. An unknown measurement may be declared unavailable, with a reason and a narrower claim; an unknown required threshold or target profile is an incomplete plan. Version and hash the completed plan. Changes after outcomes are visible create a new exploratory experiment, not a silent amendment to the original claim.

## 2. The A/B comparison contract

For each case, target profile, and repeat:

| Controlled item | A: baseline | B: candidate |
| --- | --- | --- |
| Task and initial project fixtures | Identical exact bytes | Identical exact bytes |
| Role, authority, credentials policy | Same existing authority | Same existing authority |
| Context, tools, grants, network policy | Same fixed inputs and actual availability | Same fixed inputs and actual availability |
| Model, effort, settings, limits | Same selected profile | Same selected profile |
| Other procedural instructions | Same pinned baseline | Same pinned baseline |
| Candidate procedure | Absent and inaccessible | Only the declared runtime package |
| Initial session and workspace | Fresh session, reset fixture | Fresh session, reset fixture |

The candidate text and its attributable context cost are the treatment. Do not remove useful baseline context to equalize token count. Give both arms the same input/output/step/time limits, and record whether B's additional text causes truncation, compaction, or exhaustion. These are costs of the proposed deployment, not failures to hide. If a study instead varies limits, label that a separate experiment with a different claim.

Pin hashes for baseline messages, task, role card, context pack, initial fixtures, tool configuration, relevant reference inputs, candidate package, plan, case/oracle version, and grader instructions. A revision label alone is insufficient when files can be dirty. These experiment hashes support reproducibility; they do not replace AEW's evaluated-snapshot fingerprint or evidence semantics.

Record intended and observed configuration separately. Capture the actual prompt/messages or an access-controlled exact artifact, delivered file manifest, requested and observed model/settings, runtime skill reads, tool calls, and session identity. “Skill installed” does not prove the model received or used it. Distinguish availability, bytes delivered/read, and observable procedural behavior. If actual exposure or actual model identity cannot be verified, report that limit; do not claim the missing measurement is confirmed.

No result in either arm permits an otherwise unauthorized operation. Use isolated fixtures and capabilities appropriate to the assigned task. A review experiment stays a review experiment even if the worker proposes a fix.

## 3. Evaluate selection and procedure separately

**Procedure trial:** The experiment supplies the full runtime skill in B and no skill in A. This tests whether the procedure helps when available in context; it does not validate a selector. Include irrelevant and insufficient-context cases even here: B should decline the procedure when its stated preconditions fail. Reading supplied text is unavoidable overhead; unnecessary tools or additional work are avoidable behavior to measure.

**Selection trial:** Give B only the discovery metadata and a permitted way to retrieve the runtime package. Freeze the selector behavior and all other skill candidates. Record whether the candidate was selected, whether its content was retrieved, and the subsequent result. A has the same baseline and other candidates, with this candidate absent. The result measures the combined selection-and-use mechanism. Never report a selection result as a pure procedure effect. If no harness-neutral retrieval mechanism exists, leave this trial unrun and list selection as an open question.

In a selection trial, score activation using the evaluator's oracle: `use`, `skip`, or `abstain`. `Skip` means finish the ordinary bounded task without invoking this procedure. `Abstain` means the needed inputs, evidence, or authority are missing; identify the gap and leave the conclusion unresolved. Neither means failing a legitimate small task merely because the skill is irrelevant. Track false activations, missed useful activations, and improper continuation separately. A self-reported “used skill” statement alone is not proof of exposure or adherence.

## 4. Build cases that test useful distinctions

Use several independent case families, including normal work, a difficult intended-use case, a superficially alarming but correct case, missing inputs/capabilities, explicit authority limits, and a case where the skill should not add analysis or action. For adversarial review, include ordering, retries, crash/reconstruction, stale authority/evidence, and compositions of individually legal operations. Keep correct implementations among these cases so that “always report a defect” loses.

Each case needs task inputs, a reproducible fixture, an answerable oracle, and evidence requirements. Distinguish an actual defect from a plausible risk requiring missing information. Include acceptable alternative solutions and findings; do not reward matching one author's wording. Predetermine how duplicate findings, partly correct findings, severity disagreements, and out-of-scope discoveries will be adjudicated. Independent review should resolve contested oracle facts before outcomes are unblinded where practical.

The bootstrap files use proposed authoring notation:

```yaml
format: aew-skill-cases/v1
skill: skill-name
cases:
  - id: unique-case-id
    split: development # or holdout-candidate; a label cannot create privacy
    purpose: Evaluator-only reason this case exists.
    worker:
      task: The task delivered to the worker.
      context: Task-specific facts delivered to the worker.
      artifacts:
        relative/path.txt: |
          Exact initial fixture bytes.
      capabilities: [read fixture files]
      constraints: [Do not modify fixture files.]
    oracle:
      activation: use # use, skip, or abstain
      required_findings: []
      forbidden_findings: []
      evidence_requirements: []
      allowed_alternatives: []
```

The notation is not an AEW runtime schema. `purpose`, `split`, the entire `oracle`, rubrics, solutions, evaluator notes, and plan/result records are evaluator-only. The **entire `evals/` directory is evaluator-only**. Never pass a raw case YAML or the whole candidate directory to a worker.

All cases shipped in this public package are development material, including any labeled `holdout-candidate`. A real holdout is authored or selected independently, withheld from skill authors and tuning, and checked for near-duplicates of runtime examples and development fixtures. Record who could access it. Freeze the candidate before revealing holdout results. Once those results influence a revision, that holdout is development evidence for the revision; obtain another private set for a new confirmatory claim.

Vary causal structure, artifact names, language, scale, and distractors; renaming one fixture does not make independent contexts. Do not count repeated stochastic runs on one fixture as new case coverage. Multiple model profiles are separate strata; a positive strong-model result cannot mask a regression for the cheaper intended worker.

## 5. Runner-neutral manual recipe

This recipe can be executed by a human or a future runner. It requires no new AEW command or integration.

1. **Freeze materials.** Complete the plan, confirm the oracle and rubric, and record exact SHA-256 file digests. Create a separate evaluator directory holding cases, oracle, plan, order schedule, transcripts, and results. Keep it inaccessible through every worker-visible tool, filesystem root, search index, and retrieval surface. Do not launch a worker from a checkout that exposes these files.
2. **Build the runtime package.** Copy `SKILL.md` plus only explicitly approved runtime `examples/` and `references/` files into an isolated package. List every copied relative path and hash. Exclude `evals/`, rubrics, solutions, plans, results, private cases, and author notes. Inspect runtime references for answer leakage. Reject absolute paths, `..` traversal, and symlinks escaping the package. Resolve each reference needed to execute the procedure within the allowed package or document it as unavailable before running. Links explicitly labeled evaluator-only may remain in `SKILL.md` for authors; their targets are deliberately omitted from the runtime package and are not missing worker inputs. Workers must not follow them or retrieve substitutes.
3. **Materialize the case.** Copy only `worker.artifacts` into a fresh temporary fixture root. Preserve the literal bytes and record a manifest/hash. Deliver only `worker.task`, `worker.context`, `worker.capabilities`, and `worker.constraints` as task instructions. Capabilities are descriptions; the experiment owner must separately arrange and verify actual tool availability and grants. Do not expose the case's evaluator-facing ID if it leaks its answer. Keep an immutable master copy for resets.
4. **Prepare both arms.** Produce two fresh copies of the same fixture and identical baseline messages. B receives the runtime package by the predeclared exposure mechanism; A has no access to it. A must also lack copies cached in memory, retrieval indexes, global instruction files, prior transcripts, or a shared checkout. Record the exact messages and file visibility manifest for each arm. Use neutral run names so graders need not infer the arm.
5. **Randomize before execution.** For every case/profile/repeat, assign A→B or B→A with a recorded random seed or recorded draw. Balance order where feasible and randomize case order. Run paired arms close enough in time to limit service drift. Where exposed, fix settings and record sampling seeds; equal seeds do not guarantee deterministic matching. Control cache policy, background concurrency, dependencies, and network snapshots where possible; record unavoidable differences.
6. **Run independently.** Start a new session with no inherited history for each arm of each repeat. Reset fixture, side effects, tool state, and task memory each time. Do not show a worker the other arm, rubric, oracle, or a prior result. Enforce the same stopping limits. Preserve ordinary model failures, abstentions, timeouts, and retries as outcomes. Never silently restart a bad result until it passes.
7. **Capture raw records.** Save delivered inputs, initial and final artifact manifests, transcript/tool output, final answer, termination reason, timestamps, usage/cost data, and actual exposure/configuration evidence. Use [eval-result.yaml](templates/eval-result.yaml) once per arm. Hash artifacts, retain originals, and distinguish machine telemetry, human observation, model claims, and unavailable values. Record all interventions and deviations, including failed launches.
8. **Score blind where possible.** An evaluator receives the output and needed fixture/trace evidence with arm labels removed; candidate instructions and treatment-revealing transcript portions can remain masked unless needed to assess a boundary violation. Apply the frozen rubric to both arms identically. Run any task acceptance checks on the produced artifacts under the same conditions. Record disagreements and adjudication. A model grader is a declared measuring instrument with pinned prompts/settings and a human-calibrated sample, not ground truth.
9. **Analyze all planned pairs.** Join records by case/profile/repeat, inspect configuration/exposure validity, calculate paired differences, and report each case family as well as totals. Mark missing pairs and the reasons. An independently demonstrated infrastructure failure may invalidate a pair under the frozen exclusion policy; retain the original record and replace both arms consistently. A skill-caused timeout, oversized prompt, unnecessary tool chain, bad selection, or violated constraint is an outcome, not an exclusion.
10. **Make a bounded recommendation.** Report effect size, uncertainty, failures, evidence quality, economics, and coverage. Recommend retain-as-candidate, revise, reject, or consideration for a named baseline and workload. Preserve the full comparison history. No recommendation approves an AEW Ticket, ingests evidence, changes a role, or authorizes a workflow transition.

For a dry run, use public cases to verify packaging, telemetry, and scoring. Mark it a pilot. For a benefit claim, predeclare multiple distinct contexts and enough repeats to characterize run variability. Choose sample size from the smallest useful improvement and tolerated uncertainty, using pilot variability if needed. Even many repeats on one context cannot support a broad claim. If the budget cannot support informative sampling, retain candidate status and report the uncertainty rather than weakening the claim after seeing results.

## 6. Choose measurements with operational definitions

Select measures relevant to the actual task, recording denominators and unavailable telemetry. A review skill usually needs important-finding recall, false findings, missed findings, evidence validity, and cost. A debugging skill usually needs correct causal diagnosis, successful distinguishing verification, harmful fixes, and rework. An investigation skill usually needs answer correctness, coverage of relevant paths, evidence freshness, and unnecessary exploration. Use the following registry rather than a weighted “quality score.”

| Measure | Operational definition / record |
| --- | --- |
| Task correctness | Fraction of planned runs satisfying the frozen task rubric; record individual required criteria and failure reasons. A short correct abstention can satisfy an insufficient-context case. |
| Acceptance-test success | Passed/failed/not run for each predetermined task check on the final artifact digest; report run-level all-required-pass rate and individual check results. Do not substitute test count for correctness. |
| Defects introduced | Distinct new, confirmed defects attributable to the output/change against the original fixture, grouped by predeclared severity; include the reproducer. Zero for an uninspected patch is not established. |
| Important findings | Distinct true important issues found, matched to oracle issue IDs or separately adjudicated discoveries; one issue mentioned five times counts once. |
| False or irrelevant findings | Distinct unsupported, incorrect, or out-of-scope reported issues, with reasons. Separate cautious unresolved hypotheses from claims of confirmed defects. Report precision only when there are reported findings; otherwise undefined, not 100%. |
| Missed findings / recall | Oracle important issues absent from a run and found/eligible important issues. Record issue severity; an empty positive oracle makes recall undefined and is useful for measuring false positives instead. |
| Retries | Repeated attempts after failure, grouped by launch, model continuation, tool, or verification retry. Count all costs; define what starts a new attempt. |
| Rework | Additional edits/attempts needed after initial submission to meet the frozen task criteria, under a fixed follow-up protocol. Record zero only when observed; otherwise not measured. |
| Token use / context size | Provider-reported input, output, cached, and other usage categories without double counting; tokenizer-estimated initial/peak context when available. State the estimator and unit. Separate initial skill bytes/tokens from downstream trace growth and billed totals. |
| Wall-clock time | End-to-end time from dispatch to terminal outcome including retries; optionally separate queue, execution, and human waiting. Record timeout censoring; do not treat the limit as successful completion time. |
| Human intervention | Count and duration of help events under a fixed intervention policy, with reason and exact supplied content. Include grading time separately from worker assistance. |
| Verification success | Required verification performed with reproducible command/probe, observed result, relevant snapshot, and limitations; distinguish a passing outcome from merely suggesting a test. |
| Unnecessary tool calls | Calls beyond the declared task need, adjudicated against a predeclared rule (for example, repository-wide searches after the answer is fully evidenced). Record category and trace IDs; expensive calls are not automatically unnecessary. |
| Unnecessary invocations | Extra worker/agent invocations beyond the fixed task protocol, if observable; include their time and usage. Report unavailable if the harness hides them. |
| Evidence quality / freshness | Required conclusions supported by actual observations with precise locations, exact input/output or reproduction details, snapshot identity, and known limits. Count unsupported conclusions and stale/cross-snapshot citations separately. |
| Activation behavior | Correct use/skip/abstain rate by oracle class, with false activations and inappropriate continuation. State whether retrieval was actually available and measured. |
| Authority violations | Each instruction, claim, attempted action, or completed action that exceeds the run's role/grants or asserts unauthorized project-state decisions; include trace evidence and distinguish refused attempts from completed effects. |

Evidence is fresh only for the artifact/snapshot it describes. If a worker changes the fixture after checking it, the prior pass does not establish the final artifact's correctness. A fabricated command result or unverifiable “all tests passed” statement is an evidence failure even if the answer happens to be right. Experiment artifacts never stand in for AEW gate evidence.

## 7. Cost and uncertainty are part of the result

Separate four quantities:

1. **Static payload:** runtime skill file bytes and tokens actually delivered, plus discovery metadata in selection trials. Record the tokenizer/estimator, delivery count, and any truncation. Files merely available on disk are not all input tokens.
2. **Total measured execution:** all billed token categories, tool/service charges where available, elapsed time, extra invocations, and human intervention across every attempt in each arm. Repeatedly supplied text is already in billed input totals; do not add static payload tokens to that total again.
3. **Incremental effect:** B minus A in paired total usage/cost/time, alongside effectiveness differences. Increased skill context may reduce downstream search or retries; both changes belong in the total effect. A provider's reported cached-token categories may be subsets of input; document the billing interpretation.
4. **Authoring and maintenance:** separate one-time preparation/evaluation cost from recurring execution cost. Any amortized break-even estimate must state the deployment volume, currency/date/rates, and assumptions. Without prices, report token/time effects and avoid invented monetary savings.

Report cost per satisfactory authorized outcome with total costs of failed attempts in the numerator; when there are no satisfactory outcomes it is undefined, not zero. Compare it with failure rate, severity, and total workload cost so cheap repeated failure cannot look economical. If usage is unavailable or a run is censored, report missingness or a defensible bound; never record zero.

For each target profile, show raw per-case paired outcomes, case-family summaries, mean/median changes where appropriate, spread, and severe regressions. Predeclare the uncertainty method. A paired bootstrap over **independent contexts**, preserving their repeated runs, can estimate uncertainty when there are enough contexts; do not bootstrap every repeat as though it were a new task. Binary outcomes can also be reported as paired discordant counts with an appropriate interval. Small samples need candid descriptive results and wide/inconclusive intervals, not a significance claim. Report any multiple-comparison/selection limitations when testing many variants or outcomes.

Decision rules should be conjunctive and understandable:

- **Improvement:** the predeclared primary practical improvement is supported at the declared uncertainty level; required correctness/evidence floors, regression margins, and economic limits hold; no authority veto occurs. State the exact evaluated model/workload scope.
- **Regression:** a predeclared unacceptable loss or new severe failure mode is observed. Report the affected cases even if a different average improved. An observed B authority violation or fabricated required evidence blocks recommending that candidate version for a trusted baseline; it cannot be averaged away by speed or recall. A violation in A is also recorded and investigated, not treated as permission for B.
- **Neutral / no demonstrated benefit:** effectiveness is equivalent within declared practical bounds, or improvement is too uncertain, too costly, contradicted by guardrails, or not measured. Distinguish demonstrated equivalence from an underpowered/inconclusive result. “No run” is always no demonstrated benefit.

An unacceptable point estimate with high uncertainty is a concerning inconclusive result unless the frozen rule makes that observation itself a veto. Do not rename uncertainty as proof of regression or proof of safety. Conversely, observing no violations in a finite sample does not establish that violations are impossible.

## 8. Candidate review and preserved history

These are documentation dispositions, not AEW states:

| Stage | Review artifact / possible recommendation |
| --- | --- |
| Candidate draft | Versioned skill, runtime manifest, development cases, rubric; no success claim. |
| Static and architectural review | Check procedure quality, scope, authority, context/capability separation, reference safety, and eval leakage. Revise/reject obvious boundary violations before experiments. |
| Target-model evaluation | Frozen plan, paired raw records, scoring/adjudication, aggregate report, private holdout where required for the intended claim. |
| Recommendation | Consider for a named baseline, revise, reject, or retain as unevaluated/inconclusive candidate. Existing project authority decides any actual adoption. |

Keep old candidate bytes, case versions, plans, raw records, scoring revisions, and recommendations; do not rewrite a failed result after editing the skill. A procedure, example, metadata, or reference change gets a new version/digest and a new evaluation scope. Reuse prior evidence only with an explicit argument about which behavior remained unchanged; critical boundaries and affected cases still need reevaluation. Revisit results after meaningful model, context, capability, workload, or harness changes. Deprecation is guidance to future authors/operators and does not revoke existing AEW authority or alter historical evidence.

Adoption, runtime loading, discovery behavior, evidence retention location, accepted provenance plumbing, and experiment-budget policy remain project decisions. This proposed methodology neither implements those decisions nor asserts that current AEW already supports them.
