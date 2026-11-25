---
name: ci-evidence-triage
description: Establish CI state for an exact revision and attempt, reconcile logs and checks, and attribute failures against a comparable baseline. Use when a handoff or judgment depends on CI; skip local-only debugging.
metadata:
  version: '0.1.0'
  status: candidate
---

# Ci evidence triage

## Purpose

Keep observed CI qualification separate from code-review judgment, local test results and failure attribution. Make uncertainty visible before it becomes a false completion claim.

## Task archetypes and target workers

For builders after a push, reviewers using CI evidence, and coordinators consuming check reports. Applies across CI providers; provider mechanics are conditional.

## Use and non-use

Use when CI state or failure origin matters to the assignment. Skip when no CI is involved. After establishing a specific failure and its identity, use the normal debugging process for the cause; this skill does not prescribe a repair or merge.

## Inputs and outputs

Inputs: repository, requested source identity, required checks, run/job metadata, logs and suitable baseline evidence. Output a timestamped observation of checks, run/attempt identities, failure differences, attribution and gaps in the existing report format.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Establish required checks from governing configuration, not whichever jobs happen to appear. Use authorized read access. A request to inspect CI does not authorize reruns, cancellation, workflow edits or publishing.

## Procedure and decision points

1. **Bind the observation.** Record repository, requested head, event, actual tested revision/ref, workflow identity, run ID and attempt. Determine whether the check tests branch code, a generated merge, or another event-specific subject. A nearby green commit or same branch name is not evidence for this head. Read an actual clock for observation time.
2. **Inventory required outcomes.** Record each required check and matrix identity as passed, failed, pending, cancelled, skipped, missing or unavailable, preserving provider status/conclusion. Apply the project's qualification rules; never silently equate skipped, cancelled or absent with success. Keep code-review and CI judgments separate.
3. **Acquire the matching evidence.** Bind jobs and logs to the same attempt. A latest view can hide the failed attempt. Incomplete runs or expired/unavailable logs may prevent retrieval; an empty failed-log response is not a pass. Use permitted job-level or attempt-specific retrieval, or one bounded provider wait followed by an explicit pending result. Avoid sleep/poll loops. For GitHub Actions, read [attempt-aware retrieval](references/github-actions.md).
4. **Compare like with like.** Compare test-level failure sets and diagnostic signatures against the same check, platform, relevant tool/configuration and suitable base. Retain raw logs; normalize incidental timestamps/paths only when they cannot carry the defect. Explain added, removed or changed failures separately. If the baseline or environment is incomparable, attribution remains UNKNOWN.
5. **Separate intermittency from origin.** A matching base failure supports a pre-existing classification for that signature, not a waiver or proof that the change adds nothing. A rerun pass shows intermittency, not harmlessness; changed code can introduce a timing-sensitive regression. If a rerun is already authorized, use a bounded retry and retain every attempt. Diagnose persistent or intermittent failures with a comparable reproduction; reproduce CI-only failures on the relevant platform/base/changed subject where available.
6. **Report without laundering uncertainty.** Cite failing required checks, actual log evidence and supported attribution separately. Leave UNKNOWN where causality is unestablished. Recheck head identity before handing back; drift invalidates coverage of the newer head. Stop at a supported observation or a precise evidence gap, not repeated retries until green.

## Verification and evidence

Retain command/API or UI source, observed time, subject/run/attempt/job IDs, check matrix and meaningful excerpts/artifacts. Label local reproductions separately from provider results. Compare normalized failure signatures without discarding raw assertions. A known baseline failure still fails a required check unless governing policy explicitly says otherwise.

## Failure modes and common mistakes

Common errors: quoting the latest green run for an older head; confusing attempts; treating no logs as no failures; blaming all red CI on a known flake; or forwarding local green as completed CI.

## Abstention and escalation

If logs, required-check policy, tested identity or comparable base evidence is unavailable, report the known check states and what remains unknown. Do not skip tests, weaken gates or obtain new access merely to obtain a green report.

## Examples

Synthetic good: head H attempt 2 has one failed job and one running job; report both and keep attribution unknown until comparable logs exist. Synthetic bad: attempt 1 passed on an older head, so report the current change green.
