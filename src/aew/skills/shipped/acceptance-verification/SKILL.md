---
name: acceptance-verification
description: Verify a specific engineering artifact against authoritative acceptance criteria with requirement-level evidence and explicit gaps. Use for independent outcome verification; skip implementation, test authoring alone, and approval or release decisions.
metadata:
  version: '0.1.0'
  status: candidate
---

# Acceptance verification

## Purpose

Determine whether the requested outcome holds for the identified artifact and environment. Start from the requirement, then evaluate the available proof. An implementation report, completed plan, or green suite alone does not establish acceptance.

## Task archetypes and target workers

For feature acceptance, repair verification, integration checks, and release-candidate evidence. Helps verifiers that repeat the implementer's checks, overlook missing criteria, or generalize local success to other artifacts and platforms. Verification reports inform the existing decision process.

## Use and non-use

Use when a specific artifact must be compared with authoritative desired behavior. Skip pure test design, implementation, and requests that only need a factual test-result summary. Do not turn verification into a repair assignment or a new approval process.

## Inputs and outputs

Inputs: governing requirements/criteria, artifact identity, relevant implementation evidence, permitted verification environment, and scope. Output a compact criterion-to-evidence record: criterion/source, check and environment, observation, verdict, and limitation. Include unchecked items and an overall bounded conclusion through the supplied reporting contract.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Preserve the required review independence. Identify exact source/build identity, local modifications, configuration, dependencies, and required target environment. Evidence for another snapshot is a lead unless an allowed equivalence is established. Do not mutate the submitted implementation while evaluating it.

## Procedure and decision points

1. **Reconstruct the acceptance basis.** Read the original desired outcome and governing criteria before accepting the implementation's interpretation. Separate mandatory criteria, optional proposals, and unresolved statements. Split compound criteria only to expose their parts while preserving the original obligation. Reuse source identifiers; never invent a threshold to make a vague criterion executable.
2. **Work backward from the outcome.** For each criterion, identify the observation that would demonstrate it and the plausible failure that a superficial check would miss. Cover relevant failure, recovery, and forbidden-effect conditions. A successful response may not prove a durable write; a parent exit may not prove descendant cleanup; unit imports may not prove an installed package works.
3. **Map and challenge the evidence.** Inspect what existing tests actually assert, which paths they exercise, and whether they ran against the submitted artifact. Distinguish source reasoning, supplied logs, fresh execution, and inference. Check exclusions, skips, stale results, mocks replacing the required effect, and environmental differences. Reuse adequate evidence when permitted; do not rerun checks merely because a new message began.
4. **Close the decisive gaps.** Run the smallest permitted check at the boundary needed by the criterion, plus required verification checks. Derive an independent case from the contract when the implementer's evidence leaves a material alternative open. Use disposable fixtures and controlled fault/order seams. A unit substitute for an unavailable real boundary is partial evidence, not the same check. Record exact commands, results, and cleanup.
5. **Judge each criterion.** Use the invocation's verdict vocabulary. Otherwise report pass for adequate supporting evidence, fail for a demonstrated contradiction, and inconclusive for insufficient or ambiguous evidence; add a blocked reason when an unavailable prerequisite prevents a check. Missing evidence is not itself a demonstrated implementation failure. Never promote a partially checked criterion to pass.
6. **Check completeness and identity.** Account for every in-scope criterion, including those not executed. Inspect adjacent behavior only when needed to assess the same acceptance obligation; flag unexpected behavior without silently expanding the specification. If source, artifact, or environment changed, identify invalidated checks and refresh them within scope. Do not average a failed or unresolved mandatory criterion into an overall pass.
7. **Report and stop.** Return the evidence map, exact failed observations, unresolved gaps, and bounded conclusion. Suggest the smallest next check or missing decision when useful. Do not fix the submission, rewrite acceptance to match it, classify the workflow's remediation route, or mark work accepted on the strength of this report.

## Verification and evidence

Each verdict must identify the artifact, criterion source, observation, and environment supporting it. A pass is limited to the criteria and conditions actually established. Explain evidence reuse and provenance; when execution is unavailable, source reasoning may settle a static property but cannot establish an unobserved runtime effect. An invalid fixture or unavailable service leaves the affected claim unresolved rather than automatically proving a product defect.

## Failure modes and common mistakes

- Treating "all planned tasks done" or a suite pass as proof of requirements the suite never checks.
- Calling missing evidence a confirmed defect, or treating unknown behavior as success.
- Running against a developer checkout while claiming the distributed artifact or another platform was verified.
- Weakening criteria, modifying implementation, or relying on the author's explanation instead of checking evidence.

## Abstention and escalation

When the acceptance source, artifact identity, capability, or decisive environment is unavailable, report the supported partial result and precise blocker. Seek the missing input through the existing channel. Keep pass/fail/inconclusive evidence separate from whoever decides acceptance, rework, or release.

## Examples

Synthetic good: a save endpoint returns success, but a fresh process cannot read the saved item; verification reports a persistence failure against the identified build. Synthetic bad: cite mocked repository calls and a 200 response as proof of durability. If restarting the system is unavailable, durability is inconclusive rather than automatically failed.
