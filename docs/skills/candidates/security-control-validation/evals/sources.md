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
