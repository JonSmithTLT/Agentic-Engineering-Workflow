---
name: security-control-validation
description: Validate a specific security control with bounded adversarial scenarios and evidence of prevention, detection, or containment. Use for control acceptance and remediation checks; skip broad vulnerability discovery, ordinary test reporting, and incident response.
metadata:
  version: '0.2.0'
  status: candidate
---

# Security control validation

## Purpose

Determine which claimed defensive outcomes hold for a specific subject and environment. Separate attempted activity, actual execution, protected effects, telemetry, alerts and response; success at one stage does not establish another.

## Task archetypes and target workers

For verifiers and test authors evaluating authorization, isolation, data protection, agent boundaries or detection controls. Helps workers that mistake broken attack fixtures for prevention, missing telemetry for safety, or an alert for containment.

## Use and non-use

Use when a named control or remediation has a security claim to test. Discovering unspecified vulnerabilities belongs to security review. Routine test summaries and active incident handling do not need this procedure. For AEW-managed work, read [AEW validation](references/aew-validation.md). For repeated model-mediated trials, read [agent trials](references/agent-trials.md).

## Inputs and outputs

Inputs: authoritative claim, subject/configuration identity, relevant threat scenario, permitted environment/actions, available observations and budget. Output a claim-to-evidence record through the supplied format: scenario, prerequisites, expected outcomes, observations, supported verdict and limitations. Existing acceptance criteria and decision ownership remain external.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Establish an isolated target, synthetic data, permitted destinations, bounded effects, cleanup ownership and stopping condition before execution. Inspect test dependencies and scripts. If the needed effect is unavailable, use static evidence or propose a check; do not substitute a live target or disable a defense without authorization.

## Procedure and decision points

1. **Make the claim observable.** Name the protected action/data, actor, target and boundary. Separate prevention, detection and containment requirements. Bind the scenario to the assigned threat model; distinguish a steered agent using granted tools from an independently malicious host process. Use supplied timing thresholds and conditions; do not invent them. Identify which facts would distinguish an enforced denial from a fixture that never reached the control.
2. **Bind the experiment.** Pin code/build, configuration, role/principal, environment and relevant tool/model versions. Choose a realistic minimal scenario and record prerequisites. Reuse adequate evidence for the same subject; evidence from another snapshot needs an established equivalence. Define the permitted attempt/time/cost budget and cleanup before running.
3. **Validate the fixture and observations.** Establish that the operation reaches the intended boundary. Measure legitimate-task completion both without and under injected content. Include a legitimate allowed case and, where permitted, a known vulnerable fixture or controlled ablation that demonstrates the probe can expose failure. Never weaken the real target merely to produce a control. Check observation coverage and collection health. A missing dependency, wrong identity, dead service or disconnected sensor invalidates the dependent inference.
4. **Observe the whole relevant chain.** Record attempt, execution, protected effect, telemetry, alert and response separately, marking unavailable stages unknown. Correlate observations to the same case, principal, subject and time window. Inspect final effects rather than trusting exit status or a refusal message. Distinguish a sensor event from a delivered alert and a requested response from completed containment. A later alert cannot undo an earlier forbidden effect.
5. **Challenge the result.** Compare attack and legitimate controls under matched conditions. For a repair, run the same discriminating cases against an isolated baseline and repaired subject when available; report missing baseline evidence. Cover relevant alternate entrypoints and variants of the same failed boundary. Preserve surprises and failed attempts; investigate contradictions before assigning a verdict.
6. **Conclude and clean up.** Report pass, fail or inconclusive per claim unless the host supplies different terms. An invalid experiment is not a product pass or a demonstrated defect. Complete authorized cleanup and verify residual artifacts/processes; report cleanup failures. Stop at the agreed scope/budget and state remaining coverage. Provide bounded evidence, not a universal security guarantee or a workflow approval.

## Verification and evidence

Keep case identity, exact inputs/commands, subject identity, observations and collection gaps reproducible with synthetic data. Separate fresh execution, supplied logs, source analysis and proposed tests. Claims about absence require adequate observation coverage. Report detection latency only with meaningful timestamps and clock assumptions; no timing requirement means no invented timing verdict.

## Failure modes and common mistakes

- Calling an unavailable executable or unreachable endpoint a successful defense.
- Declaring prevention because the model refuses while a tool already performed the action.
- Equating no alert with no activity, or a queued response with completed containment.
- Counting repeated trials as independent systems or hiding failures behind the best run.

## Abstention and escalation

Identify the exact missing prerequisite and affected claim; continue independent checks. If isolation, permissions or observation coverage cannot support the experiment, stop that execution and return a precise proposed check. Do not grant capabilities, publish findings externally, or repair the submitted target unless separately assigned.

## Examples

Synthetic good: an unauthorized write succeeds and a correlated alert arrives afterward. Report prevention failed and detection observed; containment remains unknown without response evidence. Synthetic bad: report the defense passed because the dashboard shows an alert, ignoring the persisted unauthorized write.
