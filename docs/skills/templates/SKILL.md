---
name: replace-with-skill-name
description: Replace with the engineering procedure, its task trigger, and a meaningful exclusion.
metadata:
  version: "0.1.0"
  status: candidate
---

# Replace with skill title

This is an unfilled authoring template. Copy into a named candidate directory and
replace the prompts below; do not install this template as a skill.

## Purpose

State the reusable engineering outcome and what the skill does not own. Name one
observable behavior that should improve over the same worker without this skill.

## Task archetypes and target workers

Name recurring task classes and target-worker characteristics. Describe the
reasoning step a less capable worker tends to miss. Do not select a provider,
model, effort setting, or role; those come from the invocation/experiment.

## Use and non-use

- Use when: concrete signals that the procedure will help.
- Do not use when: a realistic adjacent request where the procedure adds cost.
- If irrelevant: follow the original assignment without extra probes or work.

## Inputs and outputs

Minimum inputs: task question, scope, supplied snapshot/artifacts, applicable
contracts, permitted capabilities, output contract and destination. Narrow this
list to the procedure's actual needs; do not embed their current project values.

Output: define the compact engineering result and its evidence/unknowns. Map it
into the invocation's existing output contract; this worksheet defines no new
AEW evidence kind and does not replace required fields.

## Preconditions

Identify what must be known before inspection, execution, or mutation. Separate
required inputs from optional aids. If a prerequisite is absent, identify the
affected claim/action and either proceed with a bounded partial result or stop
that action; do not invent a tool, contract, credential, or permission.

## Procedure and decision points

1. Identify the task-specific question and the observation that would answer it.
2. Replace this generic step with a concrete domain action and its checkpoint.
3. At each branch, state the condition, next action, and what would disconfirm
   the current explanation. Prefer a small table if it makes the choice clearer.
4. Stop when the bounded question is answered, the next step exceeds scope or
   capability, or the supplied budget is reached. Report uncovered paths.

Replace all generic steps with useful procedure before calling this a candidate.

## Verification and evidence

For each material claim: bind the artifact/revision or supplied snapshot, cite the
source location, describe the trace or performed check, and distinguish expected
from observed behavior. Identify unrun checks, inference, stale inputs, and
limits. Explain the procedure-specific counterexample or negative control.

## Failure modes and common mistakes

List attractive wrong approaches and their consequences, including a false
positive, a likely omission, and an anti-pattern specific to this procedure.
Explain the correction instead of merely saying "be careful."

## Abstention and escalation

State the conditions that require stopping a dependent action. Return the
partial evidence, missing fact or capability, and the smallest question needed
to continue through the invocation's normal channel. No automatic dispatch,
authority acquisition, workflow transition, or permission expansion follows.

## Authority and interfaces

- Role card: supplies responsibility and authority; this skill adds technique.
- Context pack: supplies current facts, contracts, snapshot, scope and output
  requirements. Report contradictions; do not resolve them by inventing policy.
- Capabilities: use only granted, available tools within their allowed effects.
  A shell or test command can mutate state even when named as a diagnostic.
- Authority: do not approve/close/integrate work, waive review or verification,
  ingest your own evidence, obtain credentials, or redefine workflow semantics
  on the strength of this skill. Any legitimate role operation still uses
  existing AEW authority and the assignment's explicit output contract.
- Project truth: do not write a new persistent store of current task state or
  treat procedural notes as accepted project decisions.

Add any procedure-specific authority trap and its safe alternative.

## Examples

Include or link one concrete good example and one attractive-but-wrong example.
Explain the difference. Label examples synthetic and read external examples only
when needed; do not load an evaluation answer key as procedural context.

## Evaluation

State the expected improvement hypothesis, primary outcome, cost tradeoff,
regression/veto conditions, and target-worker evidence status. Link evaluator-only
`evals/cases.yaml` and `evals/rubric.md` after creating them. Include use, non-use,
and abstention cases. Expected benefit is unmeasured until a controlled target-
worker comparison demonstrates it; authors must not claim success from prose.
