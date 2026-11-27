# Authoring and evaluation notes

Evaluator-only; never include evals/ in worker context.

## Status and hypothesis

Candidate 0.1.0, authored 2026-10-19. No worker pilot or effectiveness result is claimed. Research and static package checks establish a trial candidate, not adoption evidence. Hypothesis: this procedure improves security-boundary judgments beyond adversarial-review, with acceptable context and tool cost.

## AEW interfaces

The role/card owns responsibility and evidence permissions; the context pack supplies the subject and governing requirements; effective capabilities determine available actions. The skill supplies procedure. No card, grant, loader, dispatch policy, publishing rule or engine state is changed. AEW-specific references are conditional and are navigation aids, not frozen capability contracts. They apply to work hosted by AEW without assuming the target project is AEW.

Local grounding inspected at HEAD e0193d5bbb9950088b0308e4fb6f9649517c8e28: role/card ADR-0006; the adopted 2026-10-09 worker-tool delivery/independence decision; snapshot ADR-0002; src/aew/surface/contract.py exposure versus callability; src/aew/surface/mcp.py broker transport; src/aew/surface/availability.py legality projection. The capability-discovery design is a proposal and was not treated as an available API. This inspection is not a security audit or a claim of complete implementation conformance.

## Trial design

Use [cases](cases.yaml), [rubric](rubric.md), [sources](sources.md) and the runtime manifest. Materialize only worker artifacts under a disposable case directory; pass only the worker mapping and selected runtime files. Case purpose/oracle and all evals files stay evaluator-side. Supplied logs are synthetic captured evidence, not executed tests. Public cases are development material, never private holdouts.

Compare the same worker with no skill, with adversarial-review, and with this candidate under matched context, capabilities and budgets. Test natural selection separately from forced loading. Measure optional AEW-reference cost separately; do not force every existing skill into the comparator. Use separately authored holdouts including a non-AEW project.

Predeclare acceptable accuracy and cost margins. Record supported defects/outcomes, false findings, missed distinctions, activation errors, unauthorized actions, tokens, tools and time. Preserve errors and inconclusive results. Fabricated execution, leaked answer keys, credential access or unauthorized external effects invalidate the run; repeated behavioral regressions veto adoption. If existing skills perform equally well at lower cost, prefer a conditional reference over another skill.

## Package validation, 2026-10-20

Both candidate entrypoints passed skill-creator quick_validate. The targeted repository documentation-link check passed all 12 selected documents, including the skills index. Case checks confirmed eight unique cases per candidate (six use, one skip, one abstain), required worker/oracle fields, relative artifact paths and parseable embedded JSON. All runtime digests matched their manifests; UTF-8/LF and whitespace checks passed. These are static package checks, not worker runs or executed security probes.

## Review revision 0.2.0, 2026-10-20

Adds five cases (13 total): three executable multi-step synthetic task fixtures, threat-model discrimination, and AEW event-attribution limits. Fixtures adapt AgentDojo stateful-task/utility and InjecAgent staged-theft patterns; they do not reproduce either benchmark or measure an agent resisting an injection. The worker under evaluation reviews or validates the target; it is not the simulated victim. Compare the standalone review skill with adversarial-review plus the AEW reference before retaining a separate skill. Shared evaluator scoring lives in docs/skills/evals/security-boundaries/rubric.md, which is not yet in this repository.

The October 19 threat boundary is user-relayed review evidence. Searches did not locate the original ruling; no source document or adoption status is invented. Runtime references explicitly preserve that qualification. Current files remain uncommitted in the shared checkout; no commit-ready or independent-review status is claimed.

0.2.0 validation: both skill validators passed; 14 targeted Markdown link checks passed. All 26 cases parsed; six embedded executable fixtures were each checked against three target versions (18 version checks), including benign/injected task completion and clean resets. Runtime hashes matched. Full command/stdout/stderr/exit-code records are saved in the private research review addendum. These checks are not independent review or worker-effectiveness evidence.

## 0.2.1

The public runtime text follows the adopted scope and uses defensive source
inspection, existing evidence and ordinary control checks. The cases are
synthetic and worker outcomes remain unevaluated.
