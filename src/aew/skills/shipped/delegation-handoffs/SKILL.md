---
name: delegation-handoffs
description: Prepare a cold-worker brief or verify a delegated handback, preserving exact constraints, authority and evidence. Use for an actual handoff boundary; skip direct implementation and plan decomposition alone.
metadata:
  version: '0.1.0'
  status: candidate
---

# Delegation handoffs

## Purpose

Transfer enough verified context for another worker to act correctly, then verify consequential claims before relaying them. Keep the brief smaller than the conversation it replaces.

## Task archetypes and target workers

For coordinators briefing workers, receiving reports or transferring ongoing work. Helps prevent missing qualifiers, stale artifacts, duplicated work and inflated completion claims.

## Use and non-use

Use for preparing or checking an assigned handoff. A plan describes the work; a brief supplies a particular worker's current inputs, scope and stop point. Do not invoke this skill to create unnecessary delegation.

## Inputs and outputs

Inputs: authorized task, governing decisions/findings, actual artifacts, workspace/snapshot, capabilities and integration constraints. Output a concise brief or checked handback in the supplied format. A written brief is not a dispatch or new grant of authority.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Establish who may edit, execute, commit, push, open a PR, publish or communicate externally from existing authorization; state unknown boundaries without inventing them. Respect required independence and integration constraints.

## Procedure and decision points

1. **Choose a complete assignment.** State the goal, why it matters, expected artifact and observable success. Bound owned paths/interfaces and dependencies. Separate settled requirements from proposed design and unresolved decisions. Do not split shared mutable work into competing assignments merely to claim parallelism.
2. **Verify the inputs.** Check that cited files, revisions, manifests and skill paths exist and match. Name precise sections to read and irrelevant history to skip. Provide the actual workspace/scratch location rather than an ambiguous relative path. Identify any supplied skill by path/version; if unavailable, report it instead of pretending the worker loaded it.
3. **Preserve governing wording.** Quote each consequential fix line or decision verbatim with its locator; keep your interpretation separate. Retain qualifiers, exclusions and timing conditions. Classify consequential numbers as policy/decision, measurement with conditions/date, or current snapshot. A test assertion is not automatically policy.
4. **State evidence and boundaries.** Specify expected tests/probes, source identities, inventory method, applicable CI observation, output destination and stop point. For gates, require the as-specified result before proposed deviations; widenings remain decisions for the authorized owner. Carry existing publish authority accurately, including who owns each external action; do not infer it from task responsibility. Use the [compact brief and handback fields](references/handoff-fields.md) when the host lacks them.
5. **Keep the active contract stable.** Pin skills and supplied context for the assignment. Apply feedback between tasks. If a material correction must arrive mid-task, state exactly what it supersedes and which work/evidence must be rechecked; do not silently swap inputs. Check current progress before resuming so completed work is not dispatched again.
6. **Verify before relaying.** Inspect changed artifacts and validate claims carrying the next decision: file existence, head identity, count/method, exact test scope and CI state. Sample only where it supports the stated claim; a sample cannot establish "all". Preserve reported-versus-independently-checked distinctions. Return concrete discrepancies promptly through an already authorized channel; continue independent checking.
7. **Close the feedback loop.** Record open questions, known limits and concise context/skill feedback. Ask what was missing, stale or noisy, and what specific instruction changed the work. Repeated gaps suggest a brief or skill refinement, not automatic universal policy. Stop when the next worker can act from verified inputs or the exact unresolved dependency is explicit.

## Verification and evidence

A handback should name changed head/artifacts, evidence locators, commands/results, current CI observation if applicable, remaining decisions and feedback. Read the clock for supplied timestamps. Green local tests are not CI; a worker's summary is not independent verification. Preserve the original report alongside corrections.

## Failure modes and common mistakes

Common errors: paraphrasing away a qualifier; forwarding unsupported absence/count claims; citing nonexistent paths; assuming history transfers to a cold worker; inventing publication permission; and replacing a concise brief with the full transcript.

## Abstention and escalation

Pause only the dependent dispatch or claim when essential input, authority or evidence is missing. Supply a useful draft and the smallest missing fact. Do not send messages, spawn workers or publish because this skill discusses those actions.

## Examples

Synthetic good: quote "report absent only after all retries", provide the actual reproducer and request before/after evidence. Synthetic bad: brief "return absent on missing file" and relay local green as proof of the full retry contract.
