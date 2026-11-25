---
name: requirements-clarification
description: Resolve consequential ambiguity in an engineering request and express observable acceptance criteria, constraints, and exclusions. Use before dependent design or implementation; skip requests already clear from supplied context.
metadata:
  version: '0.2.0'
  status: candidate
---

# Requirements clarification

## Purpose

Make the intended outcome precise enough to implement and verify without inventing product decisions. Keep clarification proportional to the uncertainty; a clear request needs no interview.

## Task archetypes and target workers

For feature intake, contradictory specifications, unclear change requests, and missing failure semantics. Helps leads, planners, and implementers that either guess consequential behavior or ask questions already answered in context. Applicable to any engineering project.

## Use and non-use

Use when plausible interpretations produce materially different behavior, scope, compatibility, or acceptance decisions. Skip when supplied facts or a small discovery read settle the question; continue the assignment. A routine implementation choice within established conventions is not automatically a requirements gap.

## Inputs and outputs

Inputs: user intent, current requirements and decisions, relevant existing behavior, scope, and constraints. Output only what is needed: a concise outcome, testable criteria with source locators, exclusions, resolved decisions, and remaining questions or labelled assumptions. Reuse existing identifiers and the supplied output format; do not create a second requirements store.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Establish which sources govern the request. Current behavior and old tests can explain the system but do not automatically define desired behavior. Preserve explicit technical constraints as requirements when the user or governing source specifies them.

## Procedure and decision points

1. **Read before asking.** Inspect the request, relevant decisions, and the smallest useful project slice. Extract actor, trigger, desired outcome, affected scope, and constraints. Distinguish supplied facts from observations, proposals, and unknowns. Do not ask the user to rediscover a value already in configuration.
2. **Find the decision that changes the work.** Describe competing interpretations and their consequence. Prioritize uncertainty about data loss, permissions, externally visible behavior, compatibility, cost, and failure recovery. Leave ordinary reversible implementation choices to the worker unless constrained.
3. **Ask a discriminating question.** Ask the smallest set of questions that eliminates consequential alternatives. For each consequential decision, include the question, measured facts with units/source (or explicitly unknown values), options and costs, recommendation, what it blocks, and what can proceed. Keep this compact; allow another answer. Label recommendations as proposals. Avoid broad questionnaires and repeated confirmation of answers or authority already supplied.
4. **Continue independent work.** While a required answer is missing, pause only decisions that depend on it. Continue authorized discovery or other settled work. If the user delegates a choice, make and record it within that delegation. Silence is not agreement; do not silently turn an unresolved product decision into an accepted criterion. Record the owner's answer verbatim with its source; keep your interpretation separate. If it suggests a broader rule, label that class reading and seek confirmation only for the consequential extension not already authorized; do not re-ask each settled instance.
5. **Express what can be observed.** For each agreed requirement, identify the starting condition, action, expected result, and relevant failure or recovery behavior. Use short examples, rules, or Given/When/Then where they clarify meaning. Specify units, boundaries, and measurement conditions for numeric goals; request an actual target instead of inventing one. Name what must not happen when it changes acceptance.
6. **Check consistency and scope.** Compare criteria against the request and governing decisions. Check exact boundaries, empty or missing input, state changes, and interacting requirements where relevant. Keep desired behavior separate from a proposed mechanism; retain mandated mechanisms. When an answer conflicts with an earlier record, present both verbatim with their sources and seek resolution unless explicit supersession already settles it. Recency alone does not establish precedence.
7. **Hand off and stop.** Summarize the settled outcome, criteria, exclusions, and material open decisions. State which dependent work remains blocked and why. Stop when the implementer and verifier can distinguish an acceptable result from a plausible wrong one; do not force approval of a new document when the existing assignment already authorizes proceeding.

## Verification and evidence

Trace consequential criteria to the user answer or governing source and identify its revision when supplied. Challenge each criterion with a concrete result that should fail it. If two readers could reasonably disagree on that result, narrow the criterion or retain the ambiguity. No implementation or test execution is implied by a well-written requirement.

## Failure modes and common mistakes

- Replacing "fast" with an invented latency target or "safe" with an arbitrary architecture.
- Promoting current implementation behavior, an example, or an unaccepted suggestion into a requirement.
- Removing an explicit platform or protocol constraint because it sounds like an implementation detail.
- Blocking a precise request with a generic interview, or treating unanswered questions as consent.

## Abstention and escalation

When essential intent or source precedence cannot be established, provide the supported criteria and the exact conflicting alternatives. Seek the missing decision through the existing channel. Do not settle a product tradeoff by modifying code, weakening acceptance, or rewriting the governing source.

## Examples

Synthetic good: "delete old reports" becomes a question about archive versus permanent deletion and which timestamp defines age; an already specified timezone is retained without asking again. Synthetic bad: choose 30 days and permanent deletion because those are common defaults. That choice creates retention policy the request never supplied.
