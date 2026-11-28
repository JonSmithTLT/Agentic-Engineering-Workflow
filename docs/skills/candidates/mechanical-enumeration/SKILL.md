---
name: mechanical-enumeration
description: Enumerate a defined class reproducibly and account for exclusions, unresolved inputs, and search blind spots. Use for all/every/none-remain claims or repeated missed instances; skip single-symbol lookups.
metadata:
  version: '0.1.0'
  status: candidate
---

# Mechanical enumeration

## Purpose

Produce an auditable inventory whose completeness claim is no broader than its method. Separate structural coverage from semantic reachability and correctness.

## Task archetypes and target workers

For planners, reviewers, implementers and verifiers making complete-class claims, reconciling registries, or repairing repeated omissions.

## Use and non-use

Use when a list feeds a completeness claim or enforced guard. Ordinary navigation needs only an ordinary lookup. Do not turn a bounded investigation into a repository-wide audit.

## Inputs and outputs

Inputs: class definition, scope, source snapshot, relevant runtime/configuration and existing detector. Output the reproducible search, stable inventory/dispositions, controls, disagreements and coverage limits through the existing artifact format.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Pin source and tool/parser versions, including relevant dirty bytes. Inspect supplied scanners before execution; use task-owned scratch space. Do not execute application imports merely to discover a registry without inspecting their side effects.

## Procedure and decision points

1. **Define membership and the universe.** State the invariant, what constitutes one instance, paths/file types/revision, and unit of identity. Enumerate the input universe first; every exclusion needs a reason and an account of what it hides. Distinguish finite structural classes from semantic claims a bounded scan cannot prove complete.
2. **Choose a method that sees the class.** Use text search for discovery and textual facts; use syntax, decoded values, binding resolution or data flow when structure or aliases matter. Include relevant writing/reading positions rather than one convenient spelling. For code bindings, graphs or cross-parse identities, read [semantic search](references/semantic-search.md).
3. **Make uncertainty explicit.** Emit separate member, nonmember, excluded and unknown dispositions. Parse failures, unreadable files, unresolved dynamic values and exhausted analysis bounds are unknowns with reasons, never empty successful results. Keep candidate over-approximations separate from established members.
4. **Check independently.** For inventories feeding an enforced check, use two detectors with meaningfully different failure modes and reconcile their sets in both directions at the finest common identity. Disagreement or unknown input blocks a complete result until resolved. Agreement alone is insufficient: document shared blind spots and probe concrete instances. If an independent check is unavailable, report that evidence gap rather than relabelling one detector as two.
5. **Plant discriminating controls.** Exercise a known member, a lookalike nonmember, and a missing required member. Challenge every accepting branch with an invalid near-miss, including exceptions or widened scope. Controls must run inside the real configuration/discovery boundary. For a static registry model, check missing and extra members, relevant fields, and duplicate keys before mapping construction.
6. **Publish reproducible evidence.** Sort output deterministically; retain script, command, tool versions, input identity, output and hashes together in the permitted location. Derive plan tables from this output, and reuse enumeration in guards while independently checking its blind spots. Preserve hash-cited artifacts; a revision gets a new identity. Commit only through the assigned workflow.
7. **Respond to a miss by changing the method.** Add a control for the missed form, repair the blind spot and rerun the entire in-scope class. Do not merely append another row or rerun unchanged grep. A stable re-review may reuse a validated method; explain what now detects the previously missed mechanism. Stop with every input disposition accounted for or an explicit incomplete inventory.

## Verification and evidence

Report input count, analyzed/excluded/unknown counts, member identities, detector differences, control outcomes and method limits. Identity includes snapshot, path, source span and structural discriminator where needed. Hashes establish byte identity, not correctness. A complete finite inventory is not proof that every candidate executes or violates the invariant.

## Failure modes and common mistakes

Common errors: filtering inputs by the anticipated answer; silently swallowing parser errors; counting objects instead of sites; treating two wrappers of one scanner as independent; collapsing duplicate keys; and claiming semantic completeness from a lexical or bounded graph search.

## Abstention and escalation

When scope, parser support or dynamic semantics cannot be established, return the partial inventory and exact unknowns. Propose the smallest stronger observation. Do not widen the assignment or execute untrusted code to force an answer.

## Examples

Synthetic good: reconcile declared handlers against registered handlers in both directions, retaining an unresolved dynamic registration explicitly. Synthetic bad: grep handler names, drop the unparseable file and announce that no registrations remain missing.
