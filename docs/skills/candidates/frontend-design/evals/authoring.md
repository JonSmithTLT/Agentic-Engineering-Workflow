# Authoring and evaluation notes

Evaluator-only; exclude all evals material from worker context.

## Authority and interfaces

Assignment supplies scope, role, permissions, artifacts, and output format. The skill supplies design technique. It does not install plugins, select a stack against the project's constraints, deploy a site, approve evidence, or change workflow state.

## Evaluation

Candidate 0.3.0 awaits a worker pilot. Version 0.2.0 received an author-side settings field report; it was not a controlled comparison or human-usability study. Hypothesis: purpose-specific design choices plus state and rendered checks improve usability and visual coherence without prescribing a house aesthetic or excessive context use. See [cases](cases.yaml), [rubric](rubric.md), and [research](sources.md). Compare the same worker on no-skill, prior-skill, and replacement arms where a frozen prior artifact is available. Hold tools, project input, time budget, assets, and task wording constant. Randomize order and blind visual judges to arm identity. Record total tokens, tools, completion time, and correctness as well as entrypoint size.

Prior local SKILL.md SHA-256 before replacement: `d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3`. Its full text is not duplicated into the runtime package. A hash alone cannot reconstruct it; a prior-skill arm requires independently retained matching bytes. Do not substitute a later upstream version and call it the same baseline.

Public synthetic cases are development fixtures, not unseen holdouts. Freeze private representative tasks before an adoption pilot. Fabricated evidence, invented product claims, scope violations, or broken primary flows veto adoption; preregister acceptable quality/cost tradeoffs. Structure checks do not demonstrate worker improvement.

## Web developer review refinement

Version 0.2.0 explicitly defers to maintained design/behavior/domain contracts, preserves supplied data meaning and uncertainty, and adds shared-component case FD-09 across three screens, themes, and zoom. See the [premium composition assessment](premium-compatibility.md) for resolver evidence and outstanding compatibility work. Neither the candidate nor premium installation was switched by this refinement.

## Settings field-report refinement

Version 0.3.0 incorporates an author-side field report for frontend-design 0.2.0, whose entrypoint digest was `69e52feb459bba5e13c2dbf2ee006f9e8cdd340eb4bf0fafe7080aa18c39a4f0`. Reported useful behavior included preserving uncertainty, respecting maintained identity, and requiring rendered inspection. Independent review of that implementation exposed lifecycle and fixture gaps, motivating the new conditional guidance and synthetic cases. No premium/upstream skill was loaded in that reported use. These are reported observations, not independently replayed trials or evidence of comparative superiority. Project-specific ownership and acceptance details remain in context packs.

## 0.3.1

The candidate records display or headless tooling and authorized preview
access as preconditions for browser checks. Report “not run” with the reason
when they are unavailable. Restores the complete Apache 2.0 terms and pins the
runtime bytes. The evaluator suite is retained and worker outcomes remain
unevaluated for this revision.
