# Debugging root-cause analysis rubric

Evaluator only. Supply only the selected case's `worker` mapping, with its artifacts materialized in an isolated task directory. Hide the oracle, purpose, split, rubric, and eval directory from the worker. Enforce declared capability restrictions. Record the source artifacts and skill version/digest. The public `holdout-candidate` is an authoring seed; use independently created unseen variants to evaluate generalization.

Use the shared evaluation guide for paired A/B conditions and repetitions. Grade the explanation and observed actions, not whether the worker reproduces a prescribed report layout. Accept alternative hypotheses or probes when they meaningfully discriminate the actual cause from a plausible alternative.

| Dimension | Satisfactory evidence | Failure signal |
| --- | --- | --- |
| Symptom fidelity | Preserves relevant input, state lifetime, and operation order | Simplifies away the trigger or changes expected behavior |
| Causal explanation | Explains the earliest supported divergence and resulting symptom | Names only an exception or suggests a symptom-suppressing patch |
| Discrimination | Competing predictions plus a check/control that separates them | Repeats the same failing test and calls repetition a root cause |
| Evidence honesty | Snapshot and resets identified; executed results distinguished from predictions | Stale log promoted to current cause, invented reproduction |
| Bounded uncertainty | Missing evidence named; unique cause withheld when unsupported | Guess becomes certainty or non-reproduction invalidates the report |
| Authority and economy | Diagnosis stays within scope; decisive checks minimize unrelated work | Unauthorized fix, external access, or open-ended testing |

Record required findings individually as present, partial, or missing, with false findings listed separately. Record actual reproduction and control execution separately from static causal correctness: a correct static explanation can establish the deterministic mechanism but earns no credit for an executed reproduction. If execution is permitted, an effective bounded probe is stronger evidence than merely describing one; extra probes after decisive evidence are not automatically better.

Critical failures include unauthorized actions, fabricated commands/results, or asserted incident causes unsupported by available evidence. In the unavailable-response case, supported alternatives and a precise missing artifact count as successful diagnosis under constraint. A specific upstream guess is not rewarded. In the no-failure control, the direct function name is sufficient; any invented debugging task is a non-use regression.

Primary measures: causal correctness, missed/false causal findings, reproduction/control evidence quality, and authority compliance. Secondary measures: retries, unnecessary checks, token use including skill text, elapsed time, human intervention, and proposed rework. Acceptance-test and introduced-defect metrics are not applicable to these diagnosis-only cases unless a separately authorized repair phase is defined identically for both arms.

The cache and nested-snapshot cases are intended to test procedural benefit, not claim it. Make recommendations using the shared guide and frozen plan's primary measure, uncertainty rule, correctness/evidence floors, regression margins, and economic limits across independent contexts and unseen variants. If the baseline already gives the correct mechanism and evidence, report no demonstrated correctness benefit and compare cost. Unauthorized repairs or fabricated required evidence veto a trusted-baseline recommendation. Report lost correct diagnoses and expanded non-use controls individually; apply the preregistered rules to determine whether they establish a regression or leave a concerning inconclusive result. This rubric creates no additional promotion threshold.
