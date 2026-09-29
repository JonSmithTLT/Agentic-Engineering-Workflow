---
name: debugging-root-cause-analysis
description: Diagnose a reproducible engineering failure by comparing competing causes and running permitted discriminating checks. Use for unexplained incorrect behavior; skip factual lookups and tasks without a failure to explain.
metadata:
  version: '0.1.0'
  status: candidate
---

# Debugging root-cause analysis

## Purpose

Produce a supported causal explanation of a failure, or identify the smallest missing evidence needed to choose between causes. A plausible fix is not proof of a cause.

## Task archetypes and target workers

Use for deterministic defects, state/order-dependent failures, failed checks, and incident diagnosis within the supplied authority. Intended for workers that can inspect source and interpret checks but tend to anchor on the last exception, change several variables at once, or patch before reproducing. The skill does not select a model or effort setting.

## Use and non-use

Use when observed behavior conflicts with an expectation and the cause is unsettled. Skip for direct lookups, simple requested edits with an established explanation, and requests without a failure. Do not manufacture a debugging investigation merely because code is present. For urgent containment, follow the assignment's existing procedure; diagnosis does not grant incident-control authority.

## Inputs and outputs

Inputs: expected versus observed behavior; failing input/sequence; source and environment identity; relevant logs/tests; scope, authority, and available capabilities. Distinguish a user report from a reproduced observation.

Output: symptom and reproduction status; competing explanations and their predictions; decisive evidence; supported causal chain; remaining uncertainty; and a proposed minimal regression probe or next discriminating check. Use the invocation's existing evidence/output contract. Proposed repairs are recommendations unless implementation is separately authorized.

## Preconditions

Identify the inspected revision, local changes, environment, and permitted execution surface. Confirm that running a test will not silently contact external services, write protected state, or require ungranted credentials. Use isolated fixtures or existing safe checks when authorized. If only static reads are permitted, provide static analysis and proposed checks without claiming reproduction.

## Procedure and decision points

1. **State the disagreement precisely.** Record the expected result, actual result, triggering input/operation sequence, and evidence origin. Match logs and test results to the source/environment they describe. Stale logs can suggest a hypothesis; they do not establish the current failure.
2. **Seek the smallest faithful reproduction.** Preserve meaningful order, shared state, retries, timing, and configuration. Reduce irrelevant setup without removing the suspected interaction. Run it only within granted capabilities. If it does not reproduce, report that result and check input/environment differences before changing code.
3. **List competing explanations.** Usually two or three plausible hypotheses are sufficient; do not force extras when evidence is decisive. For each record the mechanism, expected observation if true, and a check whose outcome differs from the leading alternative. Include environment/input mismatch when reproduction differs from the report.
4. **Choose a discriminating check.** Prefer a cheap check that separates hypotheses: fresh versus reused state, reversed operation order, one changed input dimension, or inspection of the value before/after a boundary. Hold other variables fixed. An assertion that merely repeats the symptom does not explain it.
5. **Use a negative control.** Run or propose a comparable case where the hypothesized trigger is absent. If it fails identically, reconsider the mechanism or the test. A changed outcome supports a hypothesis only when the changed factor is relevant and other conditions are controlled.
6. **Trace symptom to cause.** Follow the bad value/state backwards to the earliest supported divergence from the expected invariant. Separate the **proximate failure** (for example, a wrong cached return) from the **causal mechanism** (a key omits an input that determines the value). Explain why that mechanism predicts both the failing sequence and the control. Record contributing conditions separately; avoid claiming a unique root cause when several mechanisms remain possible.
7. **Test the explanation, then stop.** Seek the smallest additional observation that could falsify the leading explanation. If it survives relevant checks, report the causal chain with limits. If checks disagree, revise the hypothesis instead of accumulating speculative fixes. Stop when the assignment's question is answered or a named evidence/capability gap prevents the next discriminating check.
8. **Hand off a regression probe or permitted repair.** Specify input sequence, expected assertion, relevant control, and isolation/reset needs. Apply a repair only if the current assignment already authorizes it; then rerun the reproduction and relevant control at the changed snapshot. A local passing check never supplies workflow approval or replaces required verification.

## Verification and evidence

For executed checks record command/action, relevant inputs/order, source/environment identity, result, and whether state was reset. Keep failed reproduction attempts and contradictory results when they affect the conclusion. Label static predictions, reported observations, and executed observations separately. Source inspection can prove a small deterministic mechanism without execution, but it cannot honestly be described as a reproduced incident.

Confidence follows the evidence: an observed failure plus a discriminating control and a source-backed mechanism is stronger than a symptom-compatible guess. “Changing this makes the test pass” is insufficient if the change also alters unrelated behavior or suppresses the assertion.

## Failure modes and common mistakes

- Fixing the final exception while leaving the bad state transition intact.
- Re-running a single request after a state-dependent failure and losing the trigger.
- Changing configuration, dependencies, and code together so the result cannot distinguish causes.
- Treating an old incident log as evidence for the current revision.
- Interpreting a non-reproduction as proof that the original report was false.
- Blaming a network/library component without checking an in-process alternative.
- Reporting a proposed command as executed or a diagnosis as verified workflow evidence.

## Abstention and escalation

When data, environment, safe execution, or authority is missing, report the evidence-supported alternatives and the smallest authorized check/artifact that would distinguish them. Do not fetch secrets, mutate production, bypass a test restriction, or broaden the assignment. For an unsafe reproduction, describe its required preconditions and use a permitted isolated substitute only if it preserves the relevant mechanism; disclose the substitution and remaining gap.

## Authority and interfaces

The **role card** determines responsibility and authority; the **context pack** provides this task's facts; the **skill** provides diagnostic technique; **capabilities** determine available permitted actions. This procedure supplies no credentials, role changes, model routing, approval, state transitions, or new evidence type. Required reviews and verification remain governed by AEW. A diagnosis report or regression-probe suggestion does not independently accept a plan or complete a Ticket.

## Examples

See [the order-dependent cache diagnosis](examples/good/discriminating-cache-check.md) for competing predictions and a control. See [the symptom-only fix](examples/bad/symptom-only-fix.md) for an attractive wrong approach. Both are synthetic teaching examples, not current project context.

## Evaluation

Candidate only; no target-worker benefit is claimed. Hypothesis: competing predictions and negative controls improve causal diagnosis while reducing symptom-only conclusions. The primary outcome is a correct supported mechanism, or a justified unresolved conclusion when blocked. Compare executed discrimination, false causal claims, and cost separately; extra context and checks must satisfy the frozen evaluation plan's economic limits. Authority violations or fabricated evidence veto a recommendation; other losses use its preregistered floors and margins. [Cases](evals/cases.yaml) and [rubric](evals/rubric.md) are evaluator-only; do not load them as worker context. Include a non-debugging control and blocked-execution case. Public holdout-candidate cases are seeds for fresh unseen variants.
