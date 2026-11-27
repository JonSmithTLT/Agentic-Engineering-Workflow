# Research and synthesis

Evaluator-only. Sources inspected during research on 2026-10-19; linked upstream content is mutable. These are methodological sources, not proof of worker improvement. No attack payloads, installers or runtime dependencies are bundled.

| Source | Adopt | Do not inherit |
|---|---|---|
| [Atomic Red Team](https://github.com/redcanaryco/atomic-red-team/wiki/) and [test specification](https://github.com/redcanaryco/atomic-red-team/wiki/Sample-Spec) | Small repeatable scenarios, prerequisites, explicit inputs and cleanup. | Running a catalog by default, installing dependencies or treating test execution as detection evidence. |
| [MITRE adversary emulation library](https://ctid.mitre.org/resources/adversary-emulation-library) | Threat-relevant scenarios and questions about prevention, detection and response. | Broad emulation campaigns for a narrow control assignment or ATT&CK labels as proof of coverage. |
| [Promptfoo red teaming](https://www.promptfoo.dev/docs/red-team/) | Application-level probes, repeated evaluation and regression after mitigation. | A model response grade as proof about effects or adaptive discovery reused as unseen evaluation. |

The core adds the attempt/execution/effect/telemetry/alert/response distinction to existing test-design and acceptance-verification discipline. Agent trial detail is conditional. Incident response and full detection engineering are deferred; this skill validates specified controls rather than operating a SOC.

## 0.2.0 research extension

See the shared AI-security evidence and case-design mapping (`docs/skills/evals/security-boundaries/ai-security-sources.md`, an evaluator resource not yet in this repository) for AgentDojo, InjecAgent, ATLAS, NIST AI 100-2, PyRIT and garak. It records inspection depth, retained patterns and exclusions.

## Public revision 0.2.1

Consulted 2026-11-27. The [I6 profile, revision 3](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-39/I6-PROFILE.md)
records the October 19, 2026 scope. The [KP position](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-57/KP-POSITION.md),
[CAPR position](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-38/CAPR-POSITION.md)
and [review guide §10](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/implementation/review-guide.md)
supply the published October 24 reachability and disposition method.

| Public primary source | Adopted practice and fit | Adaptation |
| --- | --- | --- |
| [NIST AI RMF 1.0, NIST AI 100-1 (2023)](https://www.nist.gov/itl/ai-risk-management-framework) | Bind judgments to intended use, accountable roles, and limits of the evidence. | Apply to the assigned AEW boundary and outcome. Governance and disposition stay with AEW. |
| [NIST SP 800-53A Rev. 5 (2022)](https://csrc.nist.gov/pubs/sp/800/53/a/r5/final) | Evaluate concrete objectives against documented artifacts and relevant test results. | Use authorized static review, supplied observations and applicable ordinary checks. Scope and control ownership come from the invocation. |
| [Agent Skills specification](https://agentskills.io/specification), live on the consultation date | Keep the decision procedure portable and put host specifics behind links. | AEW controls execution and publication. Evaluator files remain outside the runtime bundle. |
