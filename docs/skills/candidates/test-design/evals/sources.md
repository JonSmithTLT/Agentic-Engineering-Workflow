# Test design: research rationale

Author/evaluator material; exclude from worker context. Inspected 2026-10-12. Primary upstream skills and technical sources were compared for actionable decisions, bounded scope, evidence quality, and context cost. This is an original synthesis, not a vendored skill or an empirical market ranking. External skills were read as research, not installed or executed. Links are live references, not immutable source snapshots.

- [Superpowers test-driven-development](https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md): Retain an observed failing check, intended failure analysis, and refactoring under regression protection. Reject deleting prior work, universal TDD, treating passing new tests as inherently invalid, and unrestricted whole-suite execution.

- [Functional test design](https://github.com/jaktestowac/awesome-copilot-for-testers/blob/main/skills/designing-functional-tests/SKILL.md): Retain risk-sensitive cases, explicit expected outcomes, and controlled scope. Exclude compulsory manual-first procedure and fixed case quotas.

- [Requirements coverage mapper](https://github.com/jaktestowac/awesome-copilot-for-testers/blob/main/skills/requirements-test-coverage-mapper/SKILL.md): Retain requirement-to-check mapping and inspection of actual assertions. Unmapped tests need investigation, not automatic deletion or promotion of behavior to a requirement.

- [Hypothesis introduction](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html): Supports input-domain generation as a complement to examples. No requirement to install Hypothesis or another framework.

- [Test-Driven Development for Code Generation](https://arxiv.org/abs/2402.13521): The study reports improved function-level code generation when tests accompany problem statements. It does not establish universal repository-scale benefit or isolate every element of strict TDD.

- [Scaling Test-Driven Code Generation from Functions to Classes](https://arxiv.org/abs/2602.03557): The preprint reports 12-26 absolute percentage-point correctness improvements for its class-level framework across eight models. Its prepared tests, scheduling, and repair loop do not isolate test order as the sole cause or demonstrate AEW worker benefit.

Local synthesis adds the invocation boundary, precise stopping rules, negative controls, and evaluator isolation required by the candidate format. Reuse the existing output contract instead of importing upstream orchestration. File digests, rather than these live URLs, identify the candidate used in a pilot.
