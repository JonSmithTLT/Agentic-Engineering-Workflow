# Plan review sources

Consulted 2026-11-27. AEW assigns a read-only assessor with a plan assessment
output.

| Public primary source | Adopted practice and fit | Adaptation |
| --- | --- | --- |
| [Google, Improving Design Reviews at Google, ICSE 2023](https://research.google/pubs/improving-design-reviews-at-google/) | Review design before implementation with a decision tied to the design artifact. Keep review findings legible to the plan owner. | Use AEW's assessor output, review boundary and decision ownership. Do not import Google's review tooling. |
| [GitHub spec-kit checklist](https://github.com/github/spec-kit/blob/main/templates/checklist-template.md) and [Agent Skills specification](https://agentskills.io/specification), live on the consultation date | Treat the requirements and plan as reviewable artifacts and test for unclear or unverifiable requirements. Keep authority and tooling outside the skill. | Inspect proposed checks and their dependencies on paper. Tests and implementation belong to separately assigned workers. |
| [AEW adversarial-review plan-review reference](../../../../../src/aew/skills/shipped/adversarial-review/references/plan-review.md), candidate text in the November 26, 2026 repository baseline | Preserve requirement coverage, dependency and discriminating verification questions. | Replace the code-review entrypoint on the assessor card with a standalone read-only procedure. |
