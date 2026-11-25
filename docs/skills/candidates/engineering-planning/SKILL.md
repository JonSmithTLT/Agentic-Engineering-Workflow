---
name: engineering-planning
description: Turn established engineering requirements into a bounded implementation plan with coherent interfaces, dependencies, risks, and verification. Use for changes requiring coordinated decisions; skip direct edits with an already sufficient plan.
metadata:
  version: '0.2.0'
  status: candidate
---

# Engineering planning

## Purpose

Resolve the technical decisions an implementer cannot safely infer from its own task. Produce a plan another worker can execute and a verifier can challenge, without writing the implementation in advance or replacing the requirements.

## Task archetypes and target workers

For cross-component features, migrations, substantial repairs, and revisions to an existing plan. Helps planners and leads that omit interface dependencies, split work by file instead of deliverable, or bury unresolved decisions in confident task lists.

## Use and non-use

Use when sequencing, shared interfaces, architecture tradeoffs, or verification need explicit design. Skip a bounded direct edit or an already sufficient plan; follow the existing assignment. An unresolved product outcome needs clarification before dependent technical commitments, not a more elaborate plan.

## Inputs and outputs

Inputs: authoritative requirements, current source and constraints, relevant design decisions, existing checks, and scope. Output the goal/non-goals, source basis, chosen approach with consequential tradeoffs, ordered work units, interfaces/dependencies, verification, and open risks. Use the project's plan format and destination; do not invent engine states or dispatch instructions.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Identify the inspected snapshot including local changes and the requirement version. Inspect relevant entrypoints, consumers, build/test conventions, and state boundaries before naming existing paths. Label proposed new paths and interfaces as proposed.

## Procedure and decision points

1. **Map requirements to effects.** Identify the components, external interfaces, durable state, and failure behavior each requirement touches. Reuse existing requirement IDs or source locators. Separate required behavior from optional improvements; record unsupported assumptions without treating them as decisions.
2. **Resolve consequential choices.** Compare alternatives only where compatibility, recovery, performance, testability, or maintenance materially differ. Recommend an approach with its tradeoff and evidence. For a critical unknown, specify a bounded investigation and the observation that chooses the next branch. For prototype gates, report the result under the original specification first. List scope widenings as separate owner decisions and check that each does not make the gate pass by construction. Do not schedule dependent implementation as ready while the deciding fact is missing.
3. **Define shared contracts.** Specify consumed and produced data, API/error semantics, ownership, ordering, and version behavior where they cross task boundaries. Keep names and types consistent. If a static model mirrors a runtime registry, plan equality checks in both directions from the first draft, including duplicate identities before conversion to a mapping. Derive from the owner where possible; a second handwritten list is not independent evidence. Preserve existing interfaces unless change is required; define migration, coexistence, and recovery when data or public contracts change. Do not promise rollback after irreversible effects without a real recovery mechanism.
4. **Decompose by checkable outcome.** Each work unit should produce a coherent result with identified paths/components and a way to assess it. Attach setup and documentation to the result they enable. Leave local implementation freedom where it does not threaten a shared contract. Avoid tasks such as "handle edge cases" or an exhaustive transcript of code to type. For claims about every member of a class, read [mechanical inventories](references/mechanical-inventories.md); handwritten examples cannot establish completeness.
5. **Order real dependencies.** Name the artifact/interface each dependency supplies and when it becomes usable under the project's integration rules. Check for cycles and incompatible shared-file edits. Claim parallelism only for independently usable inputs and nonconflicting mutation boundaries; separate branches alone do not establish independence. A local successful patch is not automatically an integrated prerequisite.
6. **Plan evidence alongside work.** Map each requirement to an implementation unit and a verification method with expected observations. Distinguish unit behavior from integration, installed artifact, target-platform, and recovery checks. Include negative cases and the most consequential uncovered failure modes. Use known commands when available; label proposed checks rather than inventing runnable test names. Respect existing required checks and budgets.
7. **Challenge the handoff.** Read each unit as a worker with only its declared inputs. Can it identify what to consume, change, preserve, and demonstrate? Check interface consistency and requirement coverage in both directions; justify units with no requirement as necessary support or remove them. Self-check each repaired finding across its defect class before resubmitting. On a second same-kind finding, change the discovery/checking method rather than appending another instance. If scope or assumptions change, revise affected units and evidence links together. Stop with an executable plan or explicitly gated unresolved branch.

## Verification and evidence

Cite the source/configuration supporting material constraints and the inspected snapshot. A check listed in a plan is proposed, not executed. Expose requirements with no implementation or verification path, unavailable environments, and irreversible steps. A plan's internal consistency is not acceptance of the plan or proof the system works.

## Failure modes and common mistakes

- Freezing implementation details that belong to the implementer while leaving shared interfaces unspecified.
- Calling work independent despite a schema, generated artifact, or integration dependency.
- Hiding research inside an implementation task with no decision criterion.
- Silently changing requirements to suit the design or claiming that a down migration guarantees data recovery.

## Abstention and escalation

Pause only the plan branch depending on an unresolved requirement, contract conflict, or unavailable decisive evidence. Name the missing decision, who supplies it through the current workflow, and what can proceed independently. Do not create tasks, assign workers, or approve the plan solely because the skill describes a decomposition.

## Examples

Synthetic good: add a versioned reader before enabling a new persisted format, specify how old data remains readable, and test mixed-version recovery. Synthetic bad: assign reader and writer changes in parallel, enable the writer first, and list "rollback if needed" without checking whether old readers can consume new data.
