# AEW Bounded Recovery Policy Design v0.1

**Status:** APPROVED — LIMITED SLICE  
**Date:** 2026-10-05  
**Owner:** F15.2 runner + execution policy  
**Implements now:** R5 rows 1 and 3 only  
**Not adopted by this design:** rows 4, 6, 8 and any new failure taxonomy

## 1. Purpose

Permit narrowly mechanical recovery where AEW can prove that no judgment is being replayed, while preserving every failed attempt and adverse signal.

AEW keeps its existing three layers of failure description:

- harness/run outcome;
- engine refusal/reason code;
- Lead verification classification.

This design adds recovery rules, not another cause taxonomy.

## 2. Universal recovery invariants

Automatic recovery is allowed only when all of the following hold:

1. the recovery action is MECHANICAL or already POLICY_RESOLVED;
2. no unresolved judgment input is required;
3. the applicable bound has not been consumed;
4. policy/authority bindings are still valid;
5. prior run/attempt records remain visible;
6. recovery cannot erase a blocked report, finding, anomaly, or other adverse evidence;
7. a second failure after the automatic bound returns control to the Lead.

A timeout alone never releases a lease or re-grants authority.

## 3. Adopted rule R5-1 — one `STALE_REVISION` retry

When a stage step receives `STALE_REVISION`, the runner may recompute legality and retry exactly once iff:

- the step's effective class is MECHANICAL or POLICY_RESOLVED;
- the stage's effective class remains non-judgment-bearing;
- the execution-policy digest is unchanged;
- authority remains valid;
- recomputed projection still marks the intended action legal/available under the typed-surface rule.

The retry is the same semantic stage step at the new revision, not a replay of model judgment.

History records:

```text
completed_steps[].retried_after_stale_revision = true
```

A second `STALE_REVISION`, `STALE_POLICY`, `STALE_AUTHORITY`, new blocker, new anomaly, or judgment requirement stops recovery.

This rule implements the already-accepted typed-surface stale-revision rule; it does not introduce a new policy decision.

## 4. Adopted rule R5-3 — one pre-work launch relaunch

A run that fails before the harness actually begins work may be relaunched once when execution policy permits it.

Eligibility requires all of:

- run outcome is `launch_failed`;
- the invocation is still active;
- no model work/evidence/report has been produced by that run;
- the workspace/base binding is unchanged;
- dispatch decision digest is unchanged;
- the same invocation contract remains valid;
- the failure is not `CONTAINMENT_UNAVAILABLE`;
- the per-invocation relaunch bound has not been consumed.

The relaunch:

- uses the same invocation contract and credential-lifetime rules;
- creates a **new run id**;
- retains the failed run and reason in `inv.runs[]`;
- does not increment a Ticket attempt as though a new strategy were chosen;
- does not change Ticket state merely because a relaunch occurred.

If the second launch fails, the Lead gets an attention item and no further automatic relaunch occurs.

## 5. Execution policy

The approved v1 block is:

```yaml
recovery:
  relaunch_launch_failed: 0
```

Values:

- `0`: Lead-mediated relaunch only;
- `1`: engine may perform the single eligible mechanical relaunch described above.

Migration/default is `0` so existing projects retain current behavior. Personal dogfood or F19/M4-H may opt into `1`.

The setting is part of the execution-policy digest; changing it mid-stage produces normal `STALE_POLICY`.

The one `STALE_REVISION` retry is not controlled by this flag because it is already the typed-surface runner rule.

## 6. Adverse evidence and laundering prevention

The engine must never treat automatic recovery as proof that a prior failure is irrelevant.

- Every failed run remains in invocation history.
- Any existing blocked report, unresolved finding, high-severity anomaly, or required disposition on the Ticket prevents later recovery mechanisms from silently advancing the Ticket.
- Recovery does not delete workspace/run directories that are needed to inspect a failure.
- A launch failure that may have performed work is not eligible for this row; it requires Lead inspection.

The broader lost/dirty logic belongs to deferred R5 rows 4/5 and is not authority here.

## 7. Explicitly non-automatic failures

This approved slice does not automatically recover:

- `GATE_UNSATISFIED`;
- `ILLEGAL_TRANSITION`;
- `USAGE`;
- `STALE_POLICY`;
- `STALE_AUTHORITY`;
- verification failure before Lead classification;
- plan/design defects;
- contract violations;
- poisoned plan premises;
- execution-premise contradictions;
- environmental/evidence blockers;
- a run that ended without evidence after changing files;
- tool/refusal loops or STALLED health;
- lost/crashed runs that require a new attempt.

Those conditions remain with their existing authority owner.

## 8. Deferred recovery rows

The following research proposals stay non-governing until later adoption:

- row 4 `REDISPATCH_IF_LOST`;
- row 6 policy-resolved Investigator after a blocked report;
- row 8 `max_fix_attempts` / automatic fix-loop cap.

Their eventual evaluation may reuse the `recovery:` namespace, but their keys must not be accepted by production policy as active authority until separately adopted.

## 9. Conformance tests

R5-1 tests:

- exactly one eligible stale-revision retry;
- legality is recomputed at the new revision;
- policy/authority drift blocks retry;
- judgment-bearing stages never retry;
- the retry marker is durable.

R5-3 tests:

- seeded pre-work transient launch failure relaunches exactly once when policy is `1`;
- failed run remains in history and relaunch uses a new run id;
- second failure stops;
- policy `0` preserves Lead-mediated behavior;
- `CONTAINMENT_UNAVAILABLE` never auto-relaunches;
- any evidence/work signal makes the run ineligible;
- changed dispatch/base binding makes the run ineligible.

A false recovery across a judgment boundary is a release blocker.

## 10. Evaluation

M4-H records `STALE_REVISION`, launch failure, and lost-run base rates per cell.

F19 evaluates whether the bounded rules reduce Lead turns/time-to-correct-disposition without false recovery. Product recovery occurs inside the counted run and must not be hidden as a free experiment retry.

No evidence from row 1 or row 3 is sufficient to auto-promote rows 4, 6, or 8.
