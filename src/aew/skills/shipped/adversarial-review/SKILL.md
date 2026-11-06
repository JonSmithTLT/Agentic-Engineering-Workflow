---
name: adversarial-review
description: Review code, plans, or fixes for reachable invariant violations across state, information flow, and shared effects. Use for an assigned behavioral review with concrete artifacts and contracts; skip cosmetic-only work.
metadata:
  version: '0.6.0'
  status: candidate
---

# Adversarial review

## Purpose

Find supported defects by constructing a counterexample, trying to disprove it, and testing the smallest observation that separates safe from unsafe behavior. Complete relevant defect classes within the assigned scope rather than stopping at the first witness.

## Task archetypes and target workers

For first-pass code review, plan review, and re-review of fixes. Helps reviewers that trust a plausible local check, miss alternate paths, or mistake a green probe for coverage of the full mechanism. Project facts and role decisions come from the assignment.

## Use and non-use

Use when the assigned change affects a behavioral guarantee. Skip cosmetic edits and direct explanations; do not expand them into an audit. Read only the applicable techniques:

- [State and hub routes](references/state-and-hubs.md): state machines, recovery, retries, or concurrent transitions.
- [Information flow](references/information-flow.md): projection, redaction, filtering, or claims of unchanged/broader protection.
- [Plan review](references/plan-review.md): proposed changes, inventories, companion scripts, or overlapping plans.
- [Re-review](references/re-review.md): fixes or deltas against a previous reviewed head.
- [Tool/config changes](references/tool-config-changes.md): versions, flags, configuration discovery, or enforcement commands.

## Inputs and outputs

Inputs: assigned scope, governing contracts, current artifacts and identity, permitted operations, and any prior review/baseline. **Map evidence into the host's required finding format; do not introduce a competing template.** Preserve its severity, location, guarantee, scenario, remedy, reproduction, confidence, and verdict requirements where specified.

For each supported finding convey the violated invariant, reachable witness, decisive anchors, expected versus actual result, evidence basis, and minimal correction or discriminating regression. Keep unresolved hypotheses separate. Report what held, the class members checked, exclusions, and remaining gaps. These are review content, not new workflow states.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Pin the actual source/plan revision and relevant dirty bytes, not an agent identifier or an assumed latest version. Establish the comparison base explicitly; if an intermediate version was never supplied, do not claim to have reviewed its delta.

Inspect supplied scripts before execution. Use permitted isolated copies of the pinned subject and a task-owned scratch location. Parameterize reusable probes by checkout, document invocation, and retain relevant outputs. Never reset or mutate the review target to test a theory; a hash binds bytes but does not make a script safe or correct.

## Procedure and decision points

### 1. Establish the invariant and normal behavior

Name the protected property, its authoritative source, and the boundary at which it must hold. Include relevant identity, version, information channels, or resource lifetime. Label assumptions explicitly. Trace a normal operation first; if it contradicts the proposed model, correct the model before constructing hostile inputs or sequences.

### 2. Map the effect and alternate paths

Trace the guarded entry to the actual shared effect and its consumers. Check callers and registration/dispatch, plus relevant recovery, batch, error, and cleanup paths. A symbol match is a lead; a claimed route needs an established caller, registration, or supported operation. For each relevant path identify inputs/checks, visible effects, guard at the effect boundary, and failure behavior.

### 3. Construct and try to disprove the counterexample

State the smallest input or operation sequence that would violate the invariant, with relevant intermediate state and expected outcome. Then inspect downstream defenses: atomic transactions, fencing, serialization, durable deduplication, validation, or final-channel filtering. A missing earlier check is not a defect if the effect boundary enforces the property. Discard disproved candidates; keep a conditional claim unresolved when essential semantics or reachability are unknown.

### 4. Check the whole relevant class

Define membership by the violated property and semantic values, not comments, names, or the first spelling found. When a claim covers a table, package, or all entrypoints, enumerate that domain mechanically where permitted. Search decoded literals and resolved constants as well as raw text when representation can hide members.

Check the checker: derive rows from source tables where possible; assert uniqueness before constructing keyed maps; report excluded rows and pattern blind spots. Cite external rules or hand-coded semantics to their source locations and verify them separately. An over-approximate graph is a candidate set, not proof every edge executes. Give each candidate a supported disposition and report the full in-scope set; do not hand-copy a supposedly exhaustive count. Without execution, label the enumeration static and disclose its limits.

### 5. Run a discriminating probe

Before running, predict which baseline, proposed defense, or ablation should fail or pass, and why. Use a minimal disposable fixture with deterministic ordering, explicit initial state, and assertions on the real invariant/effect. Controlled pauses or faults establish causality; sleeps and retries until green do not.

Where the claim is comparative, freeze the relevant baseline and run the same seeded inputs against both subjects. A surprise is evidence against the reviewer's model: inspect the actual mechanism and revise the claim before accepting or rejecting it. Preserve exact commands, subject identities, outputs, and limitations. Execution unavailability does not preclude a complete source counterexample, but it precludes claiming reproduction.

### 6. Assess the fix surface and cost

For a new shared helper/owner, inspect existing callers for changed outputs, errors, side effects, and timing. Compare representative before/after workloads on relevant supported platforms when cost matters. Include success and failure/absent-resource paths; per-call overhead can compound across loops or whole jobs. Use the project's actual budget or measurements, not an invented performance threshold. Mark unmeasured platform costs as unknown.

### 7. Report the complete supported result

Raise all supported findings and required nits in this pass; group shared root causes without hiding affected members or distinct mechanisms. Recheck anchors and subject identity. Stop after assigned coverage and discovered in-scope classes have been accounted for, not after a fixed number of sequences or the first finding. A supplied budget/access limit can end inspection, but requires explicit incomplete coverage, never an unqualified complete-review claim. Do not expand into unrelated subsystems.

## Verification and evidence

Distinguish **source trace**, **mechanical enumeration**, **runtime probe**, and **differential/ablation** evidence in the host's report fields. A table walk can establish a structural property without proving runtime reachability; report its algorithm, inputs, output, and coverage. An unrun script is proposed evidence. A behavioral finding still needs a reachable witness and no unresolved assumption carrying the conclusion.

A passing result applies to the inspected subject and exercised mechanism. Compare evidence inputs after drift. For CI failures, compare the same relevant check on a suitable base/environment before attributing a regression; pre-existing failure is not a new defect, and a green different-platform run is not a control.

## Failure modes and common mistakes

- Reporting a missing check without inspecting the final enforcement boundary.
- Stopping at one member of a defect class, or calling a scan complete despite excluded forms.
- Treating a hand-maintained checker, plan inventory, or de-duplicated dictionary as authoritative source.
- Accepting all-green probes without checking what each assertion can distinguish.
- Letting the skill's reporting vocabulary replace the repository's format or gates.

## Abstention and escalation

Name the exact missing fact, the dependent conclusion, evidence already established, and the smallest permitted next check. Continue independent inspection. Do not invent isolation, scheduler, persistence, contract, or platform semantics. A source-confirmed defect need not wait for unavailable execution, but unavailable semantics cannot be replaced by a worst-case guess.

## Examples

Synthetic good: a queue validates a generation at enqueue, but registered recovery applies the queued effect after revocation; an effect-time fence, if present, disproves the defect. Synthetic bad: report a recovery bypass from an unused helper's name without establishing dispatch. If a worked state trace is needed, read [recovery fence](examples/good/recovery-fence.md); [unsupported claims](examples/bad/unreachable-and-authoritative.md) contrasts the failure mode.
