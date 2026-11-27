---
name: security-control-validation
description: Assess a named defensive control with static inspection, supplied evidence and ordinary checks. Skip vulnerability discovery and incident response.
metadata:
  version: '0.2.2'
  status: candidate
---

# Security control validation

## Purpose

Determine what evidence supports a particular defensive claim for a named
subject and environment. Separate enforcement decisions, effect observations,
telemetry, alert delivery and response. Report a bounded conclusion and any
independent claims that remain unverified.

## Task archetypes and target workers

Use for review of authorization, isolation, data handling, audit and detection
controls, or a named repair's evidence. Helps workers who confuse an unavailable
dependency with prevention, an event with a delivered alert, or an alert with
containment. For AEW, read [AEW validation](references/aew-validation.md).
For supplied observations involving a model, read
[model-mediated evidence](references/agent-trials.md).

## Use and non-use

Apply when the assignment names a control and a property to assess. General
security discovery, ordinary test reporting and live incident response have
separate procedures. Limit conclusions to the assigned claim and available
authorized evidence.

## Inputs and outputs

Read the control claim, adopted scope, subject revision, configuration,
actor, affected boundary, permitted evidence and observation coverage.
Return the expected result, evidence identity, observed result, supported
verdict and limits for each claim. Use the assigned verification format
and acceptance criteria.

## Preconditions

Establish the evidence scope and comparability before assessing results.
For any assigned execution, use existing authorized ordinary control checks
with task-owned benign data, supported interfaces and bounded effects.
Confirm the relevant environment and observations. Use static analysis
and supplied results when execution or collection is unavailable.

## Procedure and decision points

1. **Make the claim observable.** Name the protected effect, actor and
   enforcing boundary. Distinguish prevention, detection and response.
   Record the expected result and any timing requirement defined by the
   governing source. Make the environment and scope part of the claim.
2. **Bind the evidence.** Record the build, relevant policy and configuration,
   role or principal, environment, and check or observation identity.
   Inspect the supported control path and locate the final enforcement and
   effect observation. Where evidence comes from a different configuration,
   verify the scope of any equivalence before relying on it.
3. **Check eligibility and collection.** Confirm that the evidence exercised
   the intended control, including the applicable principal and ordinary allowed
   behavior. A broken setup, unavailable service, absent collector or unclear
   identity weakens or invalidates dependent inferences. Identify which relevant
   observations are missing.
4. **Assess stages independently.** Correlate available observations to the
   same check, actor, subject and time window. Read the enforcement decision
   and effect where each is observable. Assess delivery or completed response
   separately from emitted telemetry. Keep contradictory and incomplete
   observations visible.
5. **Report and stop.** Give a verdict per claim using the assigned criteria.
   State the exact gap when an observation cannot distinguish an enforced
   result from an incomplete setup. Preserve the limits of static evidence,
   earlier results, and fresh checks. Finish the assigned validation when
   each claim has an outcome and a documented evidence boundary.

## Verification and evidence

Capture the check ID, version, relevant setup, expected outcome, actual
observations and limitations. Mark earlier results and proposed checks
clearly. State what collection can observe before drawing conclusions from
absence. Calculate timing only from the available events and clock assumptions.
Tie any remediation conclusion to evidence from the repaired subject.

## Failure modes and common mistakes

- Giving the control credit when a check never reached it.
- Treating a missing alert as evidence of no effect.
- Counting a requested response as completed containment.
- Citing a successful check from a different revision without comparison.

## Abstention and escalation

Report the missing prerequisite and dependent claim. Continue independent
review of available evidence. When the evidence is inconclusive, state
which control outcome needs observation and who owns the next decision.

## Authority and interfaces

The assigned role and project execution policy govern access and permitted
checks. Stay with the authorized evidence and existing ordinary control checks.
Use the assigned handoff and keep sensitive material in its designated channel.

## Examples

Synthetic good example. An existing access test records that a principal with
the expected policy can read a demo setting. A related audit record is present.
Report those observations and leave alert delivery unverified because there is
no delivery receipt. A weak response uses the audit record alone to certify
every claimed control outcome.

## Evaluation

Evaluator-only cases and rubric cover evidence eligibility, stage-specific
verdicts and abstention. Worker outcomes remain unevaluated.
