# Authoring and evaluation notes

Evaluator-only; exclude the entire evals directory from worker context.

## Authority and interfaces

The assignment supplies audience, purpose, format and action permissions; context supplies authoritative facts. This skill supplies writing technique. It does not authorize publication, sending a message, executing destructive documentation examples, rewriting governing policy or accepting engineering evidence. It complements planning, review and handoffs without replacing their procedures.

## Hypothesis and evidence status

Candidate 0.2.1 has no worker-effectiveness results recorded here. Hypothesis: reader/task-first organization, connected explanations and source-faithful claims improve comprehension and action accuracy while reducing unnecessary reading. A shorter output alone is not success. The supplied Lead report establishes candidate failure modes, not this skill's causal effect. See [research](sources.md), [cases](cases.yaml) and [rubric](rubric.md).

## Pilot design

Compare the same worker with and without the skill on matched prompts and fixed source artifacts. Add a selected existing writing skill as a separate comparator when its exact bytes are available. Hold tools, source access, task budget and requested depth constant. Freeze runtime digests, including conditionally loaded references. Test natural activation separately from forced loading and include exact-copy, routine-reply and code-only negative controls.

Use private equivalents of the public cases for confirmation. Suggested applied pilots: a task-oriented operator guide assessed through an actual usability task; and scoped PR/change descriptions assessed against their diff and recorded checks. Freeze source snapshots and score factual fidelity separately from reader preference. A task using real product actions needs the existing authorization and an appropriate test environment.

Blind readers/graders to the generating arm. Use comprehension questions or task completion, time to find the answer, consequential misunderstanding, unsupported claims, unnecessary follow-up questions, and total writing/reading cost. Calibrate judges on known accurate/incorrect summaries. Report disagreements, per-task effects and uncertainty. Do not treat an LLM saying its own writing is clear as reader evidence.

Predeclare acceptable factual error and cost limits with the evaluation owner. Changed authority, lost consequential qualifiers, fabricated verification and unsafe invented recovery steps veto adoption even when readers prefer the prose. Public development cases are not unseen holdouts. Structure validation and fixture execution are not worker-effectiveness results.

## Designer static review, 2026-10-13

The supplied review of 0.1.0 identified a distinction missing from general source ownership: normative authority versus implemented facts and verification evidence. Version 0.2.0 adds that distinction, artifact-purpose classification, one conditional contract reference and four regression cases. It does not adopt project-specific authority hierarchy or expand into contract engineering. The review is static expert feedback, not measured worker effectiveness. The 0.1.0 runtime manifest remains a historical record; use the 0.2.0 manifest for this revision.

## Trial disposition and activation clarification, 2026-10-13

The supplied designer disposition approves 0.2.0 for trial use during architectural re-baselining (TW2-D1), requests explicit requirements/contracts/ADR activation (TW2-D2), preserves separation from project-specific authority and comprehensive contract engineering (TW2-D3), and retains candidate status pending representative effectiveness evidence (TW2-D4).

Version 0.2.1 applies the supplied description verbatim and leaves the general procedure and conditional references unchanged. Trial use does not need to wait for effectiveness evaluation, and this evaluation process is not a prerequisite for foundational requirements work. Trial approval is not demonstrated effectiveness or production adoption. No project-specific authority model is added to runtime instructions.

The description change may affect natural activation even though the procedure is unchanged. Include requirements, contracts and ADR prompts plus the existing negative controls in subsequent routing trials. Preserve the 0.2.0 manifest as historical evidence; use the 0.2.1 manifest for the current package.
