---
name: plan-review
description: Assess whether a proposed plan meets its requirements, respects interfaces and dependencies, and can be verified before work starts. Use for read-only plan assessment. Patch review and check execution use their assigned roles.
metadata:
  version: "0.1.0"
  status: candidate
---

# Plan review

## Purpose

Judge whether the proposed work is sufficiently specified to implement and
verify within the assigned Ticket. Locate missing decisions before a worker
needs them. A useful assessment points to the plan text and its governing
source, shows the consequence, and explains what would make each open item
decidable.

## Task archetypes and target workers

Use for pre-work review of implementation, migration, integration, and
verification plans. It helps assessors distinguish a real gap from a
personal preference, recognize a check that cannot demonstrate the stated
outcome, and evaluate order and ownership before any work runs. The procedure
also applies when the assessor can read only a supplied plan and context.

## Use and non-use

Apply when the assignment is a plan assessment. Read the named plan and
supporting evidence as supplied or through authorized read access. Use the
assigned review standard where the project provides one. Cases such as code
review after implementation, executing a smoke check, or writing a replacement
plan belong to their own assignments. If the material includes a patch as
context, assess what the plan covers and what it leaves open.

## Inputs and outputs

Take the Ticket's requirements and acceptance criteria, the exact candidate
plan, scope, affected contracts, and available baseline
evidence. Use the role's assigned plan assessment output. Identify the plan
version and requirements reviewed. For each finding cite the plan anchor,
governing source or missing premise, and impact on implementation or evidence.
Give a concrete condition the plan should meet. Distinguish an unresolved
material decision from a detail implementation can choose within an
existing contract.

Record what can be judged from supplied artifacts and where a conclusion is
conditional. Check commands described by the plan are proposed evidence.
A plan assessment can judge what a check could demonstrate and which
preconditions it needs.

## Preconditions

Identify the candidate plan version and controlling requirements. Resolve
differences between the Ticket and plan without assuming which newer-looking
file supersedes an adopted source. If essential material is absent, inspect
the unaffected parts and state the dependency.
This method needs no execution. Use authorized exact code search or
supplied snapshots where a plan claim needs a static anchor. Project tools,
tests, network services, fixtures and preview access may be conditions for
the people named in the plan. Their availability is a subject of assessment.

## Procedure and decision points

1. **Trace requirements to planned work and proof.** Map each consequential
   acceptance criterion to a planned change and a check with a discriminating
   outcome. Identify requirements the plan omits, steps outside approved
   scope, and vague claims whose meaning differs across affected users. An
   existing contract can supply details when the plan points to the applicable
   part and version.
2. **Check the interfaces and preserved behavior.** Name the affected entry
   points, producers, consumers and data contracts. Inspect how the plan
   handles compatibility, existing state, and error or retry paths when they
   are relevant. Distinguish a question under the plan author's control from
   a promise owned by another component or role. Cite what the plan and
   available contract actually commit to.
3. **Walk the dependency order on paper.** For each externally dependent
   step identify the required artifact, decision, access or verified condition,
   its owner, and when it must exist. Read the sequence forward for handoffs
   and backward from acceptance for hidden prerequisites. Where rolling
   deployment or partial failure matters, check the intermediate states.
   Reordering is a finding when the current order can leave the next actor
   without its input or violate a contract.
4. **Check risks and decision triggers.** Focus on credible failure or
   ambiguity with a concrete consequence. Inspect the plan's detection,
   response, recovery or escalation conditions. A dependency listed with no
   owner or readiness signal may need a decision before work. Details outside
   the affected surface need no speculative controls.
5. **Read proposed verification as a reviewer.** For each material check,
   look for the target behavior, normal entry point, subject revision or
   artifact, environment, expected result, owner and stage. Determine if the
   same check could pass while the requirement is violated. Inspect coverage
   of changed behavior and meaningful preserved behavior. A check that needs
   a browser, runner, fixture or external approval needs an available owner
   or a stated conditional limitation. See [review questions](references/review-questions.md)
   for multi-step changes and handoffs.
6. **Test findings against the strongest reading of the text.** Re-read the
   relevant step and its references. A linked contract, accepted follow-on
   or clearly delegated choice may already answer the concern. If source
   evidence conflicts, narrow the finding to the decision that remains.
   Explain impact concretely and describe a resolution condition within scope.
7. **Stop at an evidence-backed assessment.** Finish when the applicable
   requirements, interfaces, order, risk and verification have an accounted-for
   result. State which material findings require resolution under the supplied
   criteria, or give the review outcome the evidence supports. For unavailable
   source evidence, report the limit and the next decision the owner needs.

## Verification and evidence

Point to plan headings or step identifiers and the source holding each
requirement or contract. Include revision or version when it distinguishes
the assessment's subject. Separate evidence inspected from checks proposed
for another role and results from earlier work. Any supplied execution result
has its own tested revision and scope. Use it only for the proposition it can
support.

For each finding, ask whether a plan author could locate the problem quickly
and know when a revision satisfies it. A high-impact finding should state
who or what gets a wrong result, loses a required input, or lacks decisive
evidence.
## Failure modes and common mistakes

- Treating a list of steps as evidence that their dependencies exist. The plan
  needs a way to tell when each step can start.
- Treating “tests pass” as proof of an acceptance criterion without checking
  what the tests exercise and which result distinguishes success.
- Rewriting the plan during assessment. Give the owner a specific required
  outcome or decision and use the established handoff.
- Treating a planned command as an executed one. Preserve the status and the
  person or environment that would be able to run it.

## Abstention and escalation

If the requirement, candidate revision or adopted contract is missing or
conflicts with another supplied source, identify the exact unresolved question
and leave its dependent conclusions open. Report the parts you can assess and
the source or owner decision that would permit a fuller assessment. Stop before
assuming execution, access or mutation that the assessor was never assigned.
Escalate a material scope or authority question via the review channel supplied
by the invocation.

## Authority and interfaces

The assessment role consumes the plan, Ticket, context and authorized
read evidence, and submits a plan assessment. The plan can name other
people's future edits, capabilities and verification. It does not change
the assessor's permissions. Your review judgment supplies evidence to the
workflow. Plan changes, execution, credentials and acceptance remain with
their existing owners.

## Examples

Synthetic example. A client rollout requires a versioned response field.
The plan deploys the client before the server and verifies only that the
server builds. Cite the compatibility requirement and both steps. Ask the
author to specify a compatible sequence and a check that observes a supported
client decoding the response, with a runner and stage.

A weak response calls the plan ready because it lists a build. The check
would also pass with a missing field and gives no evidence for the dependency
between deployment steps.

## Evaluation

Evaluator-only cases and the rubric check requirement traceability, actionable
findings, justified abstention and correct handling of proposed verification.
Expected benefit is earlier detection of genuine plan gaps from readable
evidence. Worker outcomes remain unevaluated.
