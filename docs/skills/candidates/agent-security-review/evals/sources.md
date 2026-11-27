# Research and synthesis

Evaluator-only. Sources inspected during research on 2026-10-19; linked upstream content is mutable. No source's popularity or advertised efficacy is treated as measured skill quality. The procedure is independently authored; no upstream scripts or dependencies are bundled.

| Source | Adopt | Do not inherit |
|---|---|---|
| [Event4u agent-security-review](https://github.com/event4u-app/agent-config/blob/main/src/skills/agent-security-review/SKILL.md) | Review assembled instructions, tools, hooks, permissions and memory; map attack chains to defensive gaps. | Package-specific audit command, mandatory council dispatch, fixed banners and vendor-specific routing. |
| [Promptfoo application red teaming](https://www.promptfoo.dev/docs/red-team/) | Test application/tool effects and distinguish model behavior from application boundaries. | Universal safety claims from a benchmark score; unbounded generation or a required vendor. |
| [OWASP agentic security risks](https://genai.owasp.org/download/52117/) | Coverage prompts for tool misuse, privilege boundaries and composed agent risks. | An exhaustive taxonomy in worker context or an automatic finding from a category match. |

Existing adversarial-review already supplies counterexample/disproof reasoning. The proposed incremental value is the loaded agent surface, provenance/persistence and cross-capability chain, not another generic review persona. No operational incident-response scope is added.

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
