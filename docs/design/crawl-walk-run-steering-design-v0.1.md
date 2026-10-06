# AEW Crawl / Walk / Run Steering Design v0.1

**Status:** APPROVED  
**Date:** 2026-10-05  
**Owner:** F15.2 runner loop + execution policy + operator confirmation surface  
**Implements:** R4  
**Authority class:** Operator confirmation policy over already-legal, non-judgment-bearing actions.

## 1. Purpose

Give the operator one understandable autonomy control without creating multiple AEW state machines.

Crawl, Walk, and Run change only whether the engine pauses for operator confirmation before executing an action that `ActionProjection` already marks:

- `availability == AVAILABLE`; and
- `auto_runnable == true`.

They do not decide legality and do not classify judgment.

## 2. Hard invariant

Steering mode MUST NOT be read by:

- dispatch guards;
- transition guards;
- gates;
- plan assurance;
- risk-class logic;
- lint;
- evidence acceptance;
- verification classification;
- publication legality.

All three modes must have an identical stop set. Only their confirmation set may differ.

`BLOCKED`, `UNKNOWN`, judgment-bearing, or non-auto-runnable actions are never made runnable by steering.

## 3. Semantics

For an eligible action `a`:

```text
eligible(a) =
    a.availability == AVAILABLE
    and a.auto_runnable == true
```

`confirm_before(a)` is:

| Mode | Predicate | Operator meaning |
|---|---|---|
| `crawl` | always true | AEW prepares every eligible step and waits before executing it |
| `walk` | true when side effects include `workspace`, `harness_process`, `credential`, or `authoritative_ref` | AEW handles bookkeeping itself and asks before agent/repository/process/ref effects |
| `run` | always false | AEW executes every eligible action and stops for judgments, blockers, unknowns, and anomalies |

Walk uses the existing `PrimitiveSpec.side_effect_class`. It introduces no new effect taxonomy.

## 4. Judgment boundary

Any explicit judgment-bearing input or override makes the effective action non-auto-runnable. No mode may auto-execute it.

Examples that remain judgment-bearing in all modes include accepted judgment paths such as verification classification and publication unless an already-approved conditional authorization (for example `PUBLISH_IF_CLEAN`) has independently made the projected action auto-runnable.

Run never grants such an authorization by itself.

## 5. Scope

The mode is:

- a **project default** in execution policy; and
- optionally overridden for the current **Lead session/generation** by a recorded decision.

It is **not per Ticket**.

Risk class decides which obligations/gates exist. Steering mode decides who confirms the legal non-judgment-bearing steps between them. These concerns must remain separate.

## 6. Policy and command surface

Execution policy:

```yaml
steering:
  mode: crawl | walk | run
```

The setting is part of the policy digest.

Lead-session change:

```text
aew lead mode <crawl|walk|run>
```

A mode change is recorded with the Lead generation and current revision. It takes effect on the next projection recomputation.

Migration rule: a repository that has no `steering.mode` retains legacy/manual runner behavior until explicitly migrated. Absence is a compatibility state, not a fourth mode. Personal dogfood should set `walk` while M4-H measures operator behavior.

## 7. Auto-run loop

F15.2 adds one runner loop:

1. compute/read the current `ActionProjection`;
2. stop if there is a decision, blocker, unknown, disqualifying anomaly, stale policy/authority, or no eligible action;
3. select the next eligible action according to the stage contract;
4. apply `confirm_before(action)`;
5. if confirmation is required, surface an operator attention item and wait;
6. otherwise execute the action as the normal staged primitive with `expect_rev` and the stage-intent journal;
7. recompute the projection after the committed step.

Every auto-executed action is attributable to:

- the action projection/reference;
- the steering mode/policy digest;
- the Lead generation that established the session policy;
- the normal stage intent and revision.

The loop must not bypass primitive execution paths.

## 8. Mode change during work

- A committed/running step is unaffected.
- `crawl -> run` may make a pending confirmation unnecessary; the next loop tick may execute it and attributes the execution to the recorded mode change.
- `run -> crawl` stops future unconfirmed execution on the next loop tick.
- Existing harness work is not interrupted merely because the mode became more restrictive.

Stopping a run remains a separate Lead judgment.

## 9. Operator confirmation

When confirmation is required, the existing operator channel is used. The terminal command is conceptually:

```text
aew confirm <action-ref>
```

The confirmation authorizes only the referenced currently-projected action at the expected revision/policy binding. If the projection is stale, normal stale rules apply.

Browser write-side confirmation is out of scope for this design; dashboard surfaces remain read/attention surfaces unless separately adopted.

## 10. Interaction with existing mechanisms

- Class 3 under Run still has all required review/verification gates and judgments.
- Class 0 under Crawl still has its Class 0 gate set; Crawl merely adds confirmations to eligible steps.
- Explicit Lead overrides remain judgment-bearing and therefore require judgment in every mode.
- Plan assurance failures remain blockers.
- `UNKNOWN` is never runnable.
- High-severity anomalies remain surfaced and stop the loop through the existing obligation path.
- `PUBLISH_IF_CLEAN` and other accepted conditional authorizations remain independent mechanisms; steering only consumes the resulting projection.

## 11. Conformance tests

The implementation must prove:

- identical stop sets across Crawl, Walk, and Run on the same projection sequence;
- zero execution of non-`auto_runnable` actions;
- zero execution of `UNKNOWN` actions;
- protected-condition overlap stops all modes for the same reason;
- a high-severity anomaly stops all modes for the same reason;
- changing mode never changes a guard/gate/transition result;
- a repository grep/static boundary test shows legality/gate modules do not import steering mode;
- policy drift mid-step produces normal `STALE_POLICY`;
- every auto-run step remains in normal stage/history records.

Any false advance is a release blocker.

## 12. Evaluation and default policy

The mechanism is approved now. The global product default is not yet frozen.

M4-H/F19 must measure operator confirmations, blocked time, Lead actions, false advances, judgment capture, anomaly catch, task outcome, and human time.

For personal dogfood, **Walk** is the approved test default because it exercises the confirmation path while avoiding confirmation of pure bookkeeping.

Crawl is explicitly not the universal default.
