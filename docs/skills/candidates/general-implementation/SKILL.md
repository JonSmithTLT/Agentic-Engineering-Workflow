---
name: general-implementation
description: Implement scoped engineering changes in small steps with executable behavior checks and a diff review against the accepted plan. Use for implementation Tickets. Read-only investigations and plan decisions use their own role procedures.
metadata:
  version: "0.1.0"
  status: candidate
---

# General implementation

## Purpose

Deliver the behavior assigned by a Ticket in the agreed scope. Keep the
diff, checks, and explanation in a form an independent reviewer can follow.
Find mistakes close to the step that introduced them, where the check and
the edit still have a clear relationship.

## Task archetypes and target workers

Use for contained changes to behavior, fixes, small features, migrations,
configuration or documentation whose correctness can be checked, and tightly
scoped refactoring. It helps workers that patch the first plausible file,
write checks around their patch rather than observable behavior, keep editing
after a failed check, or hand over a diff that includes unrelated work.

## Use and non-use

Start this method when the assigned output is an implementation report and
the role can modify the scoped surface. Apply it to existing normal entry
points and the interfaces an affected caller uses. For a read-only research
record, plan assessment, or CI evidence triage, use the assigned procedure.
If a step changes accepted scope or design, take it through the Ticket's
established handoff before including that step.

## Inputs and outputs

Read the Ticket, accepted plan, scope and repository instructions before
editing. Identify the evaluated baseline, paths and interfaces in scope,
acceptance criteria, known failures and required checks.
Worktree state and existing edits can be meaningful inputs. Establish their
provenance before making changes to an affected file.

Return the assigned implementation report. Include the delivered behavior,
affected paths and caller contracts, check identifiers and observed results
at the revision or worktree tested, and remaining gaps. Surface unresolved failures and departures that required
a decision. Include a pointer to the relevant record where available.

## Preconditions

Know the requested behavior, the baseline or current working revision, and
the edits the accepted plan permits. Confirm you are in the intended
worktree and understand pre-existing changes.

If a detail is left to implementation and the choice is reversible within
existing contracts, record the assumption. If a missing plan, acceptance
criterion, dependency or required capability affects the next edit, pause
that edit and use the normal clarification channel. Any check you execute
must be available under the project's execution policy.

## Procedure and decision points

1. **Read the contract before the files you intend to change.** Map each
   acceptance criterion to an observable input, outcome and applicable scope.
   Identify constraints on callers, persisted data, permissions, error
   behavior, compatibility or performance that the plan preserves. Read the
   entry point and an analogous implementation to find existing conventions
   you can reuse.
2. **Specify executable evidence early.** Select an existing focused check
   or write the smallest authorized check that distinguishes the requested
   behavior. Use the real entry point or nearest practical boundary. Set a
   clear expected output, side effect, or invariant. If a new test is
   unwarranted, a named repository check or scoped deterministic command
   can embody the expectation. For documentation and configuration, use
   an applicable validation check. When a check cannot be executed, specify
   it and report it as unrun. If feasible, obtain a baseline observation
   before changing the behavior.
3. **Choose the smallest coherent change.** Reuse current interfaces and
   representation where they satisfy the criterion. Make a step small enough
   to explain and verify with a focused check. Include changes together where
   splitting would leave storage or caller contracts inconsistent. Maintain
   expected behavior for prior callers, existing data and recovery paths
   implicated by the plan. Review local edits for unrelated changes before
   proceeding.
4. **Check after each meaningful step.** Run the cheapest relevant supported
   check. Confirm it exercised the changed behavior and compare its
   observation with the expected result and comparable baseline. Follow
   the focused check with wider required checks after the scoped behavior
   is stable. Use [check selection and failure handling](references/checks.md)
   when several checks seem equivalent or a result conflicts with the baseline.
5. **Stop progressing the implementation on a new failure.** Record the
   failed check, expected and actual results, tested state and first affected
   step. Diagnose the failure before adding more behavior. Resolve causes
   within scope and rerun the same check where feasible. Report a missing
   baseline as an attribution gap. When correction requires work outside
   scope or a missing environment, escalate the affected step with the
   evidence. Preserve earlier attempts when retrying.
6. **Review the full diff against the plan.** Account for every changed
   hunk, acceptance criterion and check. Inspect ordinary caller paths,
   supported inputs and preserved invariants touched by the change. Identify
   accidental edits or stale artifacts and address them within scope. Run
   applicable final checks against the intended handoff state. Other people's
   existing changes belong to their owners.
7. **Stop at the assigned handoff.** Submit the evidence and residual gaps
   when the scoped work has an accounted-for diff and every relevant check
   has a reported status. If a new failure remains unresolved, give an
   incomplete outcome and its blocker. Let the authorized reviewer or gate
   decide disposition from the report.

## Verification and evidence

Capture the command or check ID, revision or working state, relevant setup,
expected behavior, observation and result. A baseline comparison is meaningful
when configuration, inputs and check lane are comparable. If the baseline
already fulfills an acceptance criterion, retain that observation. If the
check can pass for the wrong reason, identify what it actually exercises and
use a check that can distinguish the intended behavior.

Use precise statuses such as passed, failed, and not run, with a reason for
gaps. A static walk of a path can explain a change and help review, with its
limits stated. Do not infer execution or readiness from that walk. Name any
required checks that still need CI or a separate permission. Report final
results against the exact state you hand off and label earlier results as such.

## Failure modes and common mistakes

- Rewriting related code because it was nearby. Scope creep hides the behavior
  change and can invalidate the targeted evidence.
- Testing a convenient helper while the real entry point still takes the
  old path. Choose a check that can distinguish the actual caller behavior.
- Moving expectations to make a newly failing check pass without evidence of
  an intentional contract change. Preserve the observation while diagnosing it.
- Calling a red check pre-existing without comparable baseline evidence.
  Preserve the failure and report uncertainty until the evidence supports it.

## Abstention and escalation

Pause a dependent edit when the plan or authority is unclear, the worktree
contains a conflicting change, or the available checks cannot meaningfully
test a consequential acceptance criterion. Give the affected criterion and the
artifact, decision or capability needed. For a failure that cannot be resolved
inside scope, report the check and observation with the smallest missing
decision. Continue only independent, authorized work.

## Authority and interfaces

The role card and accepted Ticket govern mutation, check execution and the
report destination. Use existing repository capabilities and instructions.
A green local test leaves review, credential use, scope changes and workflow
disposition with their established owners.

## Examples

Synthetic example. A configuration reader should accept a missing optional
label without changing an explicit label. Observe a focused entry-point check
on the baseline, add the scoped behavior, rerun the check including the explicit
label path, and inspect the full diff before handing off both results.

A weak response rewrites all configuration parsing, checks a new helper in
isolation, and calls an unrelated new suite failure pre-existing without a
baseline. The diff and evidence leave the assigned entry point unverified.

## Evaluation

Evaluator-only cases and the rubric assess traceable behavior, scope,
first-failure handling and honest reporting when evidence is limited.
Worker outcomes remain unevaluated.
