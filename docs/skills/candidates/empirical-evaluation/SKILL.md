---
name: empirical-evaluation
description: Design or analyze controlled comparisons of models, prompts, tools or system configurations with calibrated outcomes, uncertainty and cost. Use when evidence will choose between alternatives; skip ordinary regression testing and anecdotal checks.
metadata:
  version: '0.1.0'
  status: candidate
---

# Empirical evaluation

## Purpose

Design a measurement that can change a stated decision, then distinguish observed effect from noise, confounding and cost. An inconclusive result is preferable to an unsupported winner.

## Task archetypes and target workers

For evaluators and researchers comparing configurations, worker profiles, context/tool budgets or procedural changes. This is experimental design, not an implementation test suite or an acceptance authority.

## Use and non-use

Use for planned experiments or assessment of comparative results. Skip routine test execution and single-case debugging. For supplied data alone, analyze its limits without retroactively claiming preregistration or launching new trials.

## Inputs and outputs

Inputs: decision, alternatives, target task population, available runtimes, data permissions, outcome measures and run budget. Output a frozen protocol, reproducible trial records or evidence-qualified analysis using the host's format.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Verify actual served model/tool versions through the pinned runtime, not a stale catalog. Use permitted public/synthetic fixtures where provider retention or data terms are unresolved. Do not purchase capacity, export private data or start paid runs merely because a protocol names them.

## Procedure and decision points

1. **Write the decision before the experiment.** Specify the question, primary outcome with units, practical improvement/regression thresholds, arms, task population, analysis method, budget and stopping rule. Label exploratory work honestly. Freeze these before confirmatory runs; timestamp amendments and separate their results.
2. **Make arms comparable.** Pin model/harness/skill/configuration/artifact identities. Keep task inputs, tools, environment and execution limits equivalent except for the intended treatment. If comparing whole systems with different capabilities, say so; do not attribute the difference to one model or skill. Separate development data from untouched holdouts.
3. **Control variation.** Pair arms on the same independent tasks; randomize or counterbalance order and block on relevant environments/model strata. Reset state between trials. Repeat stochastic trials where needed, but do not count repeated runs of one task as independent new tasks. Choose sample size for the desired precision and expected variability; a tiny pilot estimates feasibility, not general superiority.
4. **Validate the measurement.** Use outcome checks where possible; calibrate human/model judges against known good and bad outputs, blind arm identity and check disagreements or position bias. Test that the grader rejects broken work and accepts correct work. Separate task success, instruction compliance, critical failures and unavailable execution rather than averaging everything into one flattering score.
5. **Ablate mechanisms.** Predict the changed outcome before removing one mechanism. Verify the intervention actually happened and controls outside its claimed scope remain clean. A multi-factor design can test interactions if planned; one-at-a-time ablations do not establish absence of interactions. Use isolated copies and verify restoration, never reset a dirty workspace. For model/context/tool comparisons read [comparison design](references/comparison-design.md).
6. **Run within the declared budget.** Track all trials, failures, timeouts, retries, missing outcomes, latency, tokens/tool calls and actual or explicitly estimated cost. Stop at the approved cap; report incomplete precision. Do not peek repeatedly and stop at the first favorable result unless a valid sequential rule was specified.
7. **Report effect with uncertainty.** Report denominators, paired differences and uncertainty appropriate to the sampling unit, per-model/task strata, and critical failure counts. Separate statistical uncertainty from generalization limits. Show cost alongside effectiveness and the binding case for any universal claim. Explain what additional evidence could reverse the decision. Stop with supported improvement, regression, equivalence within a predeclared margin, or inconclusive evidence.

## Verification and evidence

Retain the protocol version, dataset split, trial identities/settings, raw outcome records, grader versions and analysis command. Report exclusions and missing data instead of silently dropping them. Do not claim zero failures proves zero risk or overlapping intervals prove equivalence. Source hashes and a valid schema do not establish treatment effectiveness.

## Failure modes and common mistakes

Common errors: measuring context fit instead of task success; changing prompts and models together then crediting one; tuning on holdouts; counting retries as independent samples; hiding failed runs from cost; or setting a limit from a prototype size and calling it measured.

## Abstention and escalation

If runtime availability, outcome validity, data permission, budget or comparable samples are missing, return the protocol or qualified analysis and exact missing input. Do not invent scores, prices, uncertainty intervals or experimental approval.

## Examples

Synthetic good: pair old/new prompts on frozen tasks, retain unsuccessful attempts, and report outcome difference with task-level uncertainty and total cost. Synthetic bad: try each on one easy task, discard a timeout and declare the cheaper successful call the winner.
